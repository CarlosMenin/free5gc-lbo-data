#!/usr/bin/env python3
"""
Calibration of the measurement instrument.

WHAT IT IS FOR
    It guarantees that the numbers of the campaign come from the NETWORK and not
    from the tool. The underlying question: taking the network out of the path,
    what is left? What is left is the FLOOR of the instrument -- Python, kernel,
    scheduler, timestamping. A difference between paths smaller than the noise
    of this floor cannot be attributed to the network, and the analysis must
    know where that line is.

THE CONTROL LADDER (each step adds back one layer)

    C0  NO NETWORK    client and server in the SAME pod, over 127.0.0.1. No
                      wire, no Kubernetes, no 5G: it is the floor. Measured on
                      the three machines the measurement goes through:
                        C0-tester  UE/RAN     calibration instance in the tester
                        C0-edge    Edge Node  the real vr-server of mec-app
                        C0-remote  remote     the real vr-server of remote-app
    C1  NETWORK, NO 5G  from the tester pod directly to the POD IP of the server,
                      through eth0: Calico, switch and router, no UPF.
                        C1-edge -> mec-app         C1-remote -> remote-app
    C2  FULL 5G       the exact path of the campaign: UE IP, uesimtun0, gNB,
                      GTP-U, UPF(s), ClusterIP.
                        C2-edge -> mec-app         C2-remote -> remote-app

    C1 - C0 = cost of the cluster network     C2 - C1 = cost of the 5G user plane

    Each run PROVES the path it took: the counters of uesimtun0 and of the
    upfgtp of both UPFs must stay still in C0/C1 and move in C2 -- and, in C2,
    the PSA-UPF must stay still on the edge path and move on the remote path.

ACCURACY VALIDATIONS (known input -> expected output)

    A low floor does not prove that the instrument measures CORRECTLY. Hence:

    V1  sleep injected in the server: net_rtt must NOT move. Proves that
        server time does not leak into "network". The hold is in the report, but
        only as information -- it carries the pacing window and the phase between
        pose and frame, which have nothing to do with the subtraction being verified.
    V2  delay injected with tc netem on the loopback of the tester, only on the
        calibration port: net_rtt must rise by exactly 2x the delay (round
        trip). Proves that the instrument measures network delay without distortion.
    V3  independent witness: ping (ICMP, outside our code) on the C1 paths.
        net_rtt cannot be smaller than ping, and the difference must be of the
        order of the C0 floor.

REPETITION
    Each step runs --repetitions times with a ROTATING order, so that no drift
    always falls on the same step. The deviation between repetitions is the
    noise against which the difference between paths is compared in the report.

Prerequisite: Scenario B running (--deploy, or 'python3 deploy.py up b'). The
script does NOT tear down the scenario and returns the loopback of the tester
as it found it.

    python3 scripts/calibrate_instrument.py --profile teleoperation --load-subscribers 5
    python3 scripts/calibrate_instrument.py --profile vr-cloud --repetitions 5 --duration 60
"""
import argparse
import datetime
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import textwrap
import time

# Reuses the whole test of Scenario B -- deployment, placement, PDU session,
# routes, path counters. The calibration only holds if it runs in the SAME environment
# as the campaign, and the way to guarantee that is to call the SAME functions.
HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "scenario_b_test", os.path.join(HERE, "run_scenario_b.py"))
tcb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tcb)

Failure = tcb.Failure
ok, info, warning, num = tcb.ok, tcb.info, tcb.warning, tcb.num

CAL_PORT = 9200            # calibration instance, inside the tester pod
CAL_METRICS = 9201
SRV_METRICS = 9101         # real vr-server (mec-app and remote-app)

CLI = ("pod", tcb.TESTER_POD, "vr-client")
MEC = ("deploy", "free5gc-mec-app", "vr-server")
REM = ("deploy", "free5gc-remote-app", "vr-server")

# Tolerances of the accuracy validations.
SLOPE_TOL = 0.10   # V2 (net_rtt x injected delay): slope 1 +- 10%
LEAK_TOL = 0.05    # V1: net_rtt must not respond to the sleep of the server
                        # -- neither in trend (slope) nor in excursion
                        # total, both against the largest injected sleep
R2_MIN = 0.98           # V2: the response to the delay must be linear
PATH_THRESHOLD_PCT = 1.0  # C0/C1: tunnel and UPFs may see at most 1% of the poses

# qdisc of V2. A handle of our own, never to be confused with a qdisc that is not ours.
HANDLE_TC = "7a"
_netem_container = None     # != None while there is a netem of ours on the loopback


# --------------------------------------------------------------------------
# utilities
# --------------------------------------------------------------------------
def stage(tag, title_, because=""):
    """Same look as step() of the test, but with a free label (C, V1...)."""
    print(f"\n{'=' * 72}\n[{tag}] {title_}\n{'=' * 72}")
    if because and not tcb.CONCISE:
        for pair in because.strip().split("\n\n"):
            for line in textwrap.wrap(" ".join(pair.split()), 68):
                print(f"  {tcb.GREY}# {line}{tcb.RESET}")
            print()


def exec_in(where, *cmd, timeout=60):
    kind_, name_str, container = where
    tgt = name_str if kind_ == "pod" else f"deploy/{name_str}"
    return tcb.kubectl("exec", tgt, "-c", container, "--", *cmd,
                       check=False, quiet=True, timeout=timeout)


def metric_set(where, port_num):
    """/metrics of a vr-server read from INSIDE the pod, in a single call."""
    r = exec_in(where, "python3", "-c",
                "import urllib.request as u;"
                f"print(u.urlopen('http://127.0.0.1:{port_num}/metrics',timeout=5)"
                ".read().decode())", timeout=40)
    if r.returncode != 0:
        return None
    vals = {}
    for line in r.stdout.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name_str = line.split("{", 1)[0].split(None, 1)[0]
        try:
            vals[name_str] = vals.get(name_str, 0.0) + float(line.rsplit(None, 1)[1])
        except (IndexError, ValueError):
            pass
    return vals


SERVER_COUNTERS = ("frames_sent_total", "frame_packets_total", "frames_late_total",
                  "send_dropped_total", "pose_packets_total",
                  "sessions_expired_total")


def srv_delta(m0, m1):
    if m0 is None or m1 is None:
        return None
    return {k: m1.get(f"vr_server_{k}", 0.0) - m0.get(f"vr_server_{k}", 0.0)
            for k in SERVER_COUNTERS}


def active_pod(epc_mode):
    """(name, ip) of the Running pod that is NOT being deleted -- after a profile
    change the old pod still shows up for a few seconds."""
    r = tcb.kubectl("get", "pod", "-l", f"epc-mode={epc_mode}", "-o",
                    "jsonpath={range .items[*]}{.metadata.name}{'|'}"
                    "{.metadata.deletionTimestamp}{'|'}{.status.phase}{'|'}"
                    "{.status.podIP}{'\\n'}{end}", quiet=True)
    for line in r.stdout.splitlines():
        name_str, deleting, phase, ip = (line.split("|") + ["", "", "", ""])[:4]
        if name_str and not deleting and phase == "Running" and ip:
            return name_str, ip
    raise Failure(f"no Running pod with epc-mode={epc_mode}")


# --------------------------------------------------------------------------
# calibration instance of vr-server (loopback of the tester)
# --------------------------------------------------------------------------
_CAL_SEARCH = """
import os, signal, sys
found = []
for p in os.listdir('/proc'):
    if not p.isdigit():
        continue
    try:
        c = open('/proc/%s/cmdline' % p, 'rb').read()
    except OSError:
        continue
    if b'vr_server.py' in c and b'--port\\x00PORT' in c:
        found.append(p)
        if 'kill' in sys.argv[1:]:
            os.kill(int(p), signal.SIGTERM)
print(' '.join(found))
""".replace("PORT", str(CAL_PORT))


def stop_cal_server():
    # The python:3.12-slim image has no pkill/ps: the search goes through /proc.
    return exec_in(CLI, "python3", "-c", _CAL_SEARCH, "kill",
                   timeout=30).stdout.split()


def start_cal_server(prof, render_ms=0.0, render_sleep=False):
    """Starts a vr-server on 127.0.0.1 with the SAME profile as the campaign and returns
    the startup log (from which comes the pacing slack used by V1).

    render_sleep goes through an ENVIRONMENT VARIABLE, not a flag, on purpose: an
    old vr-app ConfigMap ignores the variable and starts normally, while an
    unknown flag would crash the server with an argparse error. V1 checks
    whether the variable was obeyed, by reading the banner of the log."""
    stop_cal_server()
    p = tcb.PROFILES[prof]
    line = (f"VR_RENDER_SLEEP={1 if render_sleep else 0} "
             f"nohup python3 -u /opt/vr/vr_server.py --bind 127.0.0.1 "
             f"--port {CAL_PORT} --metrics-port {CAL_METRICS} "
             f"--bitrate-mbps {p['bitrate_mbps']} --fps {p['fps']} "
             f"--mtu {p['mtu']} --render-ms {render_ms} "
             f"--role calibration --profile {prof} "
             "</dev/null >/tmp/cal-server.log 2>&1 &")
    r = exec_in(CLI, "sh", "-c", line, timeout=30)
    if r.returncode != 0:
        raise Failure(f"could not start the calibration server: "
                    f"{r.stderr.strip()[:300]}")
    tcb.wait_for("calibration server answering",
               lambda: (metric_set(CLI, CAL_METRICS) is not None, "starting"),
               30, interval=1)
    return exec_in(CLI, "cat", "/tmp/cal-server.log", timeout=20).stdout


def slack_ms(log, fps):
    """How much of the period is left AFTER the pacing. The render injected by V1 must
    fit in it, otherwise the generator falls behind and V1 measures the generator."""
    period = 1000.0 / fps
    m = re.search(r"pacing: (\d+) bursts of \d+ pkt every ([\d.]+) ms", log)
    if m:
        return max(0.0, period - (int(m.group(1)) - 1) * float(m.group(2)))
    return period if "OFF" in log else period * 0.2


# --------------------------------------------------------------------------
# one measurement
# --------------------------------------------------------------------------
def client_side(where, srv_side, bind, tag, args, csv=None):
    cmd = ["python3", "/opt/vr/vr_client.py", "--server", srv_side,
           "--bind", bind, "--duration", str(args.dur),
           "--warmup", str(args.warmup),
           "--pose-hz", str(tcb.PROFILES[args.prof]["pose_hz"]),
           "--label", tag]
    if csv:
        cmd += ["--csv", csv]
    r = exec_in(where, *cmd, timeout=args.dur + 90)
    try:
        b = r.stdout
        return json.loads(b[b.index("{"):b.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        raise Failure(f"vr_client did not return JSON (rc={r.returncode}): "
                    f"{r.stderr.strip()[-300:]}")


def path_snapshot():
    f = {"ue-tun": tcb.tun_counters()}
    for node_role, (deploy, _) in tcb.UPFS.items():
        try:
            f[node_role] = tcb.gtp_counters(deploy)
        except Failure:
            f[node_role] = None
    return f


def path_delta(a, b):
    return {k: (tcb.delta(a[k], b[k]) if a.get(k) and b.get(k) else None)
            for k in a}


def check_path(expected, d, res):
    """The step only holds if the traffic took the path that the step declares."""
    poses = res.get("ul_packets_tx") or 0
    if not poses:
        return ["the client did not send any pose"]

    def cont(k, field):
        return None if not d.get(k) else d[k][field]

    probs = []
    tun = cont("ue-tun", "tx_pkts")
    iupf, psa = cont("i-upf", "rx_pkts"), cont("psa-upf", "rx_pkts")
    if expected == "no-5g":
        for tag, v in (("uesimtun0", tun), ("I-UPF", iupf), ("PSA-UPF", psa)):
            if v is not None and v > poses * PATH_THRESHOLD_PCT / 100:
                probs.append(f"{tag} counted {v} packets ({v / poses * 100:.1f}% "
                             "of the poses): this step should be OUTSIDE 5G")
        return probs
    if tun is not None and tun < 0.95 * poses:
        probs.append(f"uesimtun0 saw {tun} of {poses} poses: part of the traffic "
                     "did not enter the tunnel")
    if expected == "edge":
        if iupf is not None and iupf < 0.9 * poses:
            probs.append(f"I-UPF decapsulated {iupf} of {poses} poses: the local "
                         "breakout did not happen")
        if psa is not None and psa > 0.02 * poses:
            probs.append(f"PSA-UPF saw {psa} packets: edge traffic went up to the core")
    elif psa is not None and psa < 0.9 * poses:
        probs.append(f"PSA-UPF saw {psa} of {poses} poses: the remote traffic did not "
                     "reach the central anchor")
    return probs


def health(res, srv, target_fps):
    """The same guards as the campaign: did the run measure the network, not the testbed?"""
    probs = []
    if not res.get("frames_complete"):
        probs.append("no complete frame came back")
    sa = res.get("health") or {}
    if sa.get("rx_timestamp_kernel") is False:
        probs.append("no kernel timestamp: it is not the calibrated instrument")
    window = res.get("ul_window_s") or res.get("duration_s")
    if srv is None:
        probs.append("could not read /metrics of the server")
    else:
        if window and target_fps:
            fps = srv["frames_sent_total"] / window
            if fps < 0.9 * target_fps:
                probs.append(f"server emitted {fps:.0f} of {target_fps:.0f} fps")
        if srv["send_dropped_total"]:
            probs.append(f"server dropped {srv['send_dropped_total']:.0f} "
                         "packets on sending (full sndbuf)")
        if srv["sessions_expired_total"]:
            probs.append("the session expired at the server (the uplink stopped)")
    cont = res.get("dl_continuity_pct")
    if cont is not None and cont < tcb.CONTINUITY_THRESHOLD_PCT:
        probs.append(f"downlink existed in only {cont:.0f}% of the window")
    rec = res.get("dl_packets_rx_run") or 0
    drops = sa.get("dl_sock_drops")
    if drops is None:
        drops = sa.get("dl_sock_overflow_pkts")
    for where, n in (("socket queue of the client", drops),
                    ("UDP buffer of the netns of the client", sa.get("udp_rcvbuf_errors"))):
        if n and rec and n / rec * 100 > tcb.LOCAL_DROP_THRESHOLD_PCT:
            probs.append(f"{n} drops in the {where} ({n / rec * 100:.2f}% of the downlink)")
    if abs(sa.get("clock_drift_us") or 0) > 1000:
        probs.append(f"CLOCK_REALTIME moved {sa['clock_drift_us']:.0f} us "
                     "(NTP step in the middle of the run)")
    return probs


def extract(reg):
    r, srv = reg["summary"], reg["server_metrics"]
    lost = r.get("dl_packet_loss_pct")
    if srv and srv.get("frame_packets_total"):
        lost = max(0.0, 1 - (r.get("dl_packets_rx_run") or 0)
                    / srv["frame_packets_total"]) * 100
    return {"net_min": r["net_rtt_us"]["min"],
            "net_p50": r["net_rtt_us"]["p50"], "net_p95": r["net_rtt_us"]["p95"],
            "net_p99": r["net_rtt_us"]["p99"], "jitter_net": r.get("jitter_net_us"),
            "m2p_p50": r["m2p_us"]["p50"], "hold_p50": r["hold_us"]["p50"],
            "loss_pct": lost, "mbps": r.get("dl_throughput_mbps")}


def measure(name_str, expected, cli, srv_side, bind, srv, srv_port, target_fps,
          args, tag, csv, before=None, after=None):
    """before/after: called RIGHT NEXT to the client, without the counter readings
    in between -- V3 uses this to mark the window on the clock of the node itself."""
    m0, c0 = metric_set(srv, srv_port), path_snapshot()
    mark_start = before() if before else None
    t_start = time.time()
    res = client_side(cli, srv_side, bind, tag, args, csv)
    t_end = time.time()
    mark_end = after() if after else None
    m1, c1 = metric_set(srv, srv_port), path_snapshot()
    dsrv, dcam = srv_delta(m0, m1), path_delta(c0, c1)
    probs = health(res, dsrv, target_fps) + check_path(expected, dcam, res)
    reg = {"step": name_str, "run_label": tag, "expected": expected,
           "target_server": srv_side, "bind": bind, "target_fps": target_fps,
           # clock window of the run: it is what allows crossing this measurement
           # with Prometheus, Loki or Grafana later.
           "start_epoch": round(t_start, 3), "end_epoch": round(t_end, 3),
           "node_marks": [mark_start, mark_end],
           "summary": res, "server_metrics": dsrv, "path": dcam,
           "problems": probs, "valid": not probs}
    reg["metrics"] = e = extract(reg)
    state = (f"{tcb.GREEN}ok{tcb.RESET}" if not probs
              else f"{tcb.RED}INVALID{tcb.RESET}")
    print(f"       {tag:<22} net p50={num(e['net_p50'])} p99={num(e['net_p99'])} us"
          f"  jitter={num(e['jitter_net'])} us  loss={num(e['loss_pct'], 3)}%"
          f"  {num(e['mbps'], 2)} Mbps  [{state}]")
    for p in probs:
        print(f"         {tcb.YELLOW}- {p}{tcb.RESET}")
    return reg


def remote_csv(where, tag):
    return (f"/data/calibration/{tag}.csv" if where[0] == "pod"
            else f"/tmp/{tag}.csv")


def copy_csv(where, remote, output, tag):
    kind_, name_str, container = where
    try:
        pod = name_str if kind_ == "pod" else active_pod(name_str.replace("free5gc-", ""))[0]
    except Failure:
        return
    destination = os.path.join(output, "csv", f"{tag}.csv")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    # Relative destination, from inside the folder: on Windows kubectl reads "C:\..."
    # as <pod>:<path> and refuses the copy.
    r = tcb.run(["kubectl", "-n", tcb.NS, "cp", f"{pod}:{remote}", os.path.basename(destination),
                 "-c", container], check=False, quiet=True, timeout=120,
                cwd=os.path.dirname(destination))
    if r.returncode != 0:
        info(f"csv of {tag} not copied: {r.stderr.strip()[:120]}")


def measure_or_record(name_str, *a, **kw):
    try:
        return measure(name_str, *a, **kw)
    except Failure as e:
        reason = str(e).splitlines()[0]
        print(f"       {kw['run_label']:<22} {tcb.RED}FAILED{tcb.RESET}: {reason}")
        return {"step": name_str, "run_label": kw["run_label"], "valid": False,
                "problems": [reason], "error": str(e)}


# --------------------------------------------------------------------------
# control ladder
# --------------------------------------------------------------------------
def ladder(args, ctx, records):
    fps_mec, fps_rem = tcb.target_fps("free5gc-mec-app"), tcb.target_fps("free5gc-remote-app")
    fps_cal = tcb.PROFILES[args.prof]["fps"]
    loop_cal, loop_srv = f"127.0.0.1:{CAL_PORT}", f"127.0.0.1:{tcb.VR_PORT}"
    ladder_steps = [
        ("C0-tester", "no-5g", CLI, loop_cal, "127.0.0.1", CLI, CAL_METRICS, fps_cal),
        ("C0-edge", "no-5g", MEC, loop_srv, "127.0.0.1", MEC, SRV_METRICS, fps_mec),
        ("C0-remote", "no-5g", REM, loop_srv, "127.0.0.1", REM, SRV_METRICS, fps_rem),
        ("C1-edge", "no-5g", CLI, f"{ctx['ip_mec']}:{tcb.VR_PORT}",
         ctx["ip_tester"], MEC, SRV_METRICS, fps_mec),
        ("C1-remote", "no-5g", CLI, f"{ctx['ip_remote']}:{tcb.VR_PORT}",
         ctx["ip_tester"], REM, SRV_METRICS, fps_rem),
    ]
    if ctx["ue_ip"]:
        ladder_steps += [
            ("C2-edge", "edge", CLI, f"{ctx['mec_cluster_ip']}:{tcb.VR_PORT}",
             ctx["ue_ip"], MEC, SRV_METRICS, fps_mec),
            ("C2-remote", "remote", CLI, f"{ctx['remote_cluster_ip']}:{tcb.VR_PORT}",
             ctx["ue_ip"], REM, SRV_METRICS, fps_rem),
        ]
    stage("C", f"Control ladder: {len(ladder_steps)} steps x {args.repetitions} "
               f"repetitions, {args.dur:g}s each",
          """C0 removes the whole network (loopback in the pod itself), C1 adds back the
    cluster network without any UPF, C2 is the 5G path of the campaign. The difference
    between neighboring steps gives an owner to each part of the delay.

    The order ROTATES at each repetition, and each run checks through the counters
    of uesimtun0 and of the UPFs that the traffic took the path the step declares.
    A run that fails a guard is recorded as invalid -- in a calibration, a
    failure is also a result.""")
    for rep in range(args.repetitions):
        k = rep % len(ladder_steps)
        order = ladder_steps[k:] + ladder_steps[:k]
        info(f"repetition {rep + 1}/{args.repetitions}: "
             + " -> ".join(d[0] for d in order))
        for name_str, expected, cli, tgt, bind, srv, port_num, fps in order:
            tag = f"{name_str}-r{rep + 1}"
            csv = remote_csv(cli, tag)
            if name_str == "C0-tester":
                start_cal_server(args.prof, 0)
            try:
                reg = measure_or_record(name_str, expected, cli, tgt, bind, srv, port_num,
                                       fps, args, tag=tag, csv=csv)
            finally:
                if name_str == "C0-tester":
                    stop_cal_server()
            reg["repetition"] = rep + 1
            records.append(reg)
            copy_csv(cli, csv, args.output, tag)
            time.sleep(args.pause)


def aggregate(value_list):
    v = [x for x in value_list if x is not None]
    if not v:
        return None
    return {"n": len(v), "median": statistics.median(v), "min": min(v),
            "max": max(v), "sd": statistics.stdev(v) if len(v) > 1 else None}


STEP_ORDER = ["C0-tester", "C0-edge", "C0-remote", "C1-edge", "C1-remote",
                 "C2-edge", "C2-remote"]
KEYS = ("net_min", "net_p50", "net_p95", "net_p99", "jitter_net", "m2p_p50", "hold_p50",
          "loss_pct", "mbps")


def aggregate_steps(records):
    ag = {}
    for name_str in STEP_ORDER:
        regs = [r for r in records if r["step"] == name_str]
        if not regs:
            continue
        val = [r for r in regs if r["valid"]]
        ag[name_str] = {"runs": len(regs), "valid_runs": len(val)}
        for c in KEYS:
            ag[name_str][c] = aggregate([r["metrics"][c] for r in val])
    return ag


# Quantiles of the Student t: two-sided 95% (alpha 5%) and one-sided 80% (power 80%).
# With 3 repetitions per side the normal approximation (1.96 + 0.84 = 2.8) underestimates
# the minimum detectable difference by up to 2x; the table corrects this without scipy.
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}
_T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896,
        8: 0.889, 9: 0.883, 10: 0.879, 12: 0.873, 15: 0.866, 20: 0.860, 30: 0.854}


def _t_quantile(table, gl, normal):
    if gl is None or gl > 30:
        return normal
    # df rounded DOWN: the conservative side
    return table[max(k for k in table if k <= max(1, int(gl)))]


def min_detectable_effect(s1, n1, s2, n2):
    """MDE of two independent samples with different variances (Welch).
    Returns (mde, degrees_of_freedom)."""
    a, b = s1 ** 2 / n1, s2 ** 2 / n2
    den = (a ** 2 / (n1 - 1) if n1 > 1 else 0) + (b ** 2 / (n2 - 1) if n2 > 1 else 0)
    gl = (a + b) ** 2 / den if den else None
    factor = _t_quantile(_T975, gl, 1.960) + _t_quantile(_T80, gl, 0.842)
    return factor * math.sqrt(a + b), gl


def regression(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - a * mx
    sst = sum((y - my) ** 2 for y in ys)
    ssr = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    return {"slope": a, "intercept": b, "r2": 1 - ssr / sst if sst else 1.0}


# --------------------------------------------------------------------------
# V1 -- injected render
# --------------------------------------------------------------------------
def v1_render(args, records):
    stage("V1", "Accuracy: SERVER time must not leak into 'network'",
          """Makes the server SLEEP a known time before sending the frame
    (VR_RENDER_SLEEP=1) and verifies ONE thing: net_rtt must not move. The
    client computes net_rtt = m2p - hold; if the sleep of the server appears in
    net_rtt, the subtraction is wrong and processing time is being counted as
    network -- the error that would invalidate the whole campaign. With V2
    (network delay must APPEAR in net_rtt), it closes the pair: the instrument
    responds to what is network and ignores what is not.

    The hold is printed, but it does NOT enter the criterion. It is dominated by
    the pacing window and by the phase between the pose and frame cadences, which
    change from run to run by ~1 ms -- noise larger than the few milliseconds that
    can be injected. Requiring a slope of 1.00 from it failed two good calibrations
    (1.32 on ar-industrial, with the render burning CPU, and 0.68 on vr-360,
    already with sleep and R2 of 0.79) with nothing wrong in the measurement: in
    both, net_rtt stayed still.

    The sleep values come from the slack that the pacing leaves in the period:
    above it the generator falls behind, and the validation would measure the generator.""")
    fps = tcb.PROFILES[args.prof]["fps"]
    log = start_cal_server(args.prof, 0, render_sleep=True)
    if "[sleep]" not in log:
        warning("vr-server ignored VR_RENDER_SLEEP: the vr-app ConfigMap of the "
              "cluster predates this version. Apply "
              "'kubectl apply -f mec/vr-app.yaml' and wait for the kubelet "
              "to sync (~1 min). V1 will run with CPU burning: "
              "net_rtt still holds, the printed hold does not.",
              scope="calibration")
    slack = slack_ms(log, fps)
    renders = args.render_ms or [0.0] + [round(slack * f, 2) for f in (0.2, 0.4, 0.6)]
    info(f"slack of the period after the pacing: {slack:.2f} ms -> renders {renders} ms")
    points = []
    try:
        for R in renders:
            start_cal_server(args.prof, R, render_sleep=True)
            tag = f"V1-render-{R:g}ms"
            csv = remote_csv(CLI, tag)
            reg = measure_or_record("V1", "no-5g", CLI, f"127.0.0.1:{CAL_PORT}",
                                   "127.0.0.1", CLI, CAL_METRICS, fps, args,
                                   tag=tag, csv=csv)
            reg["render_ms"] = R
            records.append(reg)
            points.append(reg)
            copy_csv(CLI, csv, args.output, tag)
            time.sleep(args.pause)
    finally:
        stop_cal_server()
    val = [p for p in points if p["valid"]]
    if len(val) < 3:
        warning("V1 with fewer than 3 valid points: cannot fit the line",
              scope="calibration")
        return {"executed": True, "passed": False, "reason": "not enough points"}
    xs = [p["render_ms"] * 1000 for p in val]
    nets = [p["metrics"]["net_p50"] for p in val]
    rh = regression(xs, [p["metrics"]["hold_p50"] for p in val])
    rn = regression(xs, nets)
    # Two readings of the SAME criterion ("net_rtt does not move"), because with
    # few points the line alone is fragile: the slope says whether there is a trend
    # and the excursion says whether the total variation fits in the noise. Both are compared
    # with the LARGEST injected sleep -- it is against it that "not moving" means something.
    injected = max(xs) if xs else 0.0
    excursion = max(nets) - min(nets) if nets else 0.0
    pct = (excursion / injected * 100) if injected else None
    passed = (rn is not None and abs(rn["slope"]) <= LEAK_TOL
                and (pct is None or pct <= LEAK_TOL * 100))
    print(f"\n       net_rtt p50 = {rn['slope']:+.3f} x sleep + {rn['intercept']:.0f} us"
          f"   (expected 0.000)   [CRITERION]")
    if pct is not None:
        print(f"       excursion of net_rtt p50: {excursion:.0f} us for "
              f"{injected:.0f} us of injected sleep ({pct:.1f}%; limit "
              f"{LEAK_TOL * 100:.0f}%)   [CRITERION]")
    print(f"       hold p50    = {rh['slope']:.3f} x sleep + {rh['intercept']:.0f} us"
          f"   (R2={rh['r2']:.3f})   [informative: carries pacing and the phase of the pose]")
    (ok if passed else warning)(
        "V1 PASSED: the sleep of the server did not appear in net_rtt" if passed
        else "V1 FAILED: the sleep of the server leaked into net_rtt")
    return {"executed": True, "passed": bool(passed), "renders_ms": renders,
            "hold": rh, "net_rtt": rn, "excursion_net_us": excursion,
            "max_sleep_us": injected, "excursion_pct": pct}


# --------------------------------------------------------------------------
# V2 -- network delay injected with netem
# --------------------------------------------------------------------------
def container_with(tool):
    for c in ("ue", "gnb"):
        r = tcb.kexec(tcb.TESTER_POD, c, "sh", "-c", f"command -v {tool}",
                      check=False, quiet=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return c
    return None


def tc(container, *a, timeout=20):
    return tcb.kexec(tcb.TESTER_POD, container, "tc", *a, check=False,
                     quiet=True, timeout=timeout)


def remove_netem(container):
    global _netem_container
    tc(container, "qdisc", "del", "dev", "lo", "root")
    _netem_container = None


def apply_netem(container, delay_ms):
    """prio on the loopback with everything in band 1 (no delay) and a u32 filter that
    sends ONLY the calibration port to band 3, where the netem is. The simulated
    radio link between nr-gnb and nr-ue also goes through the loopback of this
    pod, and must not get any delay."""
    global _netem_container
    remove_netem(container)
    h = HANDLE_TC
    steps = [
        ["qdisc", "add", "dev", "lo", "root", "handle", f"{h}:", "prio",
         "bands", "3", "priomap"] + ["0"] * 16,
        ["qdisc", "add", "dev", "lo", "parent", f"{h}:3", "handle", f"{h}3:",
         "netem", "delay", f"{delay_ms}ms", "limit", "100000"],
        ["filter", "add", "dev", "lo", "parent", f"{h}:", "protocol", "ip",
         "prio", "1", "u32", "match", "ip", "dport", str(CAL_PORT), "0xffff",
         "flowid", f"{h}:3"],
        ["filter", "add", "dev", "lo", "parent", f"{h}:", "protocol", "ip",
         "prio", "2", "u32", "match", "ip", "sport", str(CAL_PORT), "0xffff",
         "flowid", f"{h}:3"],
    ]
    _netem_container = container
    for p in steps:
        r = tc(container, *p)
        if r.returncode != 0:
            remove_netem(container)
            return (r.stderr or r.stdout).strip()
    return None


def netem_packets(container):
    r = tc(container, "-s", "qdisc", "show", "dev", "lo")
    m = re.search(rf"qdisc netem {HANDLE_TC}3:.*?Sent \d+ bytes (\d+) pkt", r.stdout, re.S)
    return int(m.group(1)) if m else None


def v2_netem(args, records):
    stage("V2", "Accuracy: a KNOWN network delay must be measured 1:1",
          """Injects delay with tc netem on the loopback of the tester, filtered only by
    the calibration port -- outbound (poses) and back (frames). A delay D per
    direction must appear as exactly 2D more in net_rtt. The line
    net_rtt x 2D must have slope 1 and be linear: it is the proof that the
    instrument measures network delay without gain, saturation or a hidden offset.

    The netem counter confirms that the calibration packets actually went
    through the delayed queue. The loopback returns to its original state at the
    end, even with an error or Ctrl+C.""")
    c = container_with("tc")
    if not c:
        warning("V2 NOT EXECUTED: 'tc' does not exist in the ue/gnb containers of the tester. "
              "Manual alternative on brix-porvir-02 (it has sudo): sudo nsenter -t "
              "<pid do nr-ue> -n tc qdisc add dev lo ...", scope="calibration")
        return {"executed": False, "reason": "tc missing in the tester image"}
    current = tc(c, "qdisc", "show", "dev", "lo").stdout
    if f"qdisc prio {HANDLE_TC}:" in current:
        info("a qdisc from a previous calibration was left on the loopback; removing it")
        remove_netem(c)
    elif "noqueue" not in current:
        warning(f"V2 NOT EXECUTED: the loopback of the tester already has a qdisc that is not "
              f"from this calibration ({current.strip()[:80]}). Not overwriting it.",
              scope="calibration")
        return {"executed": False, "reason": "foreign qdisc on the loopback"}
    fps = tcb.PROFILES[args.prof]["fps"]
    delays = args.delay_ms or [0.0, 1.0, 2.0, 5.0]
    points = []
    try:
        start_cal_server(args.prof, 0)
        for D in delays:
            err = apply_netem(c, D)
            if err:
                hint = (" -- load the module on brix-porvir-02: sudo modprobe sch_netem"
                        if "unknown" in err.lower() or "not found" in err.lower() else "")
                warning(f"V2 NOT EXECUTED: tc refused netem ({err[:120]}){hint}",
                      scope="calibration")
                return {"executed": False, "reason": f"tc: {err[:200]}"}
            tag = f"V2-netem-{D:g}ms"
            csv = remote_csv(CLI, tag)
            reg = measure_or_record("V2", "no-5g", CLI, f"127.0.0.1:{CAL_PORT}",
                                   "127.0.0.1", CLI, CAL_METRICS, fps, args,
                                   tag=tag, csv=csv)
            reg["delay_ms"] = D
            reg["netem_pkts"] = netem_packets(c)
            remove_netem(c)
            info(f"netem delayed {reg['netem_pkts']} calibration packets")
            records.append(reg)
            points.append(reg)
            copy_csv(CLI, csv, args.output, tag)
            time.sleep(args.pause)
    finally:
        if _netem_container:
            remove_netem(_netem_container)
        stop_cal_server()
    val = [p for p in points if p["valid"] and p.get("netem_pkts")]
    if len(val) < 3:
        warning("V2 with fewer than 3 valid points", scope="calibration")
        return {"executed": True, "passed": False, "reason": "not enough points"}
    xs = [2 * p["delay_ms"] * 1000 for p in val]
    rn = regression(xs, [p["metrics"]["net_p50"] for p in val])
    passed = (rn and abs(rn["slope"] - 1) <= SLOPE_TOL
                and rn["r2"] >= R2_MIN)
    print(f"\n       net_rtt p50 = {rn['slope']:.3f} x (2 x delay) + "
          f"{rn['intercept']:.0f} us   (expected 1.000; R2={rn['r2']:.4f})")
    for p in val:
        expected = 2 * p["delay_ms"] * 1000 + rn["intercept"]
        print(f"       delay {p['delay_ms']:>4g} ms/direction: measured "
              f"{p['metrics']['net_p50']:>8.0f} us, line {expected:>8.0f} us")
    (ok if passed else warning)(
        "V2 PASSED: the injected delay appears 1:1 in net_rtt" if passed
        else "V2 FAILED: the instrument does not reproduce the injected delay")
    return {"executed": True, "passed": bool(passed), "delays_ms": delays,
            "net_rtt": rn}


# --------------------------------------------------------------------------
# V3 -- independent witness (ping)
# --------------------------------------------------------------------------
def _pct(value_list, q):
    v = sorted(value_list)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def v3_ping(args, ctx, ag, records):
    stage("V3", "Independent witness: ICMP at the SAME instant and on the same path as C1",
          """ping is not our code and answers inside the kernel of the destination, with no
    Python at all: it is a LOWER bound of net_rtt on the same path. It runs
    AT THE SAME TIME as a C1 flow -- an idle ping is no comparison, because an
    idle small machine is slower than one under load (the CPU sleeps between
    packets and takes time to wake up).

    The replies are cut to the post-warm-up window of the client, marked on the
    clock of the node itself. The comparison is like with like: minimum with minimum
    (the floor of the path, no queue) and median with median. The expected difference
    is of the order of a C0 floor -- what the Python of both ends adds to ICMP.""")
    c = container_with("ping")
    if not c:
        warning("V3 NOT EXECUTED: 'ping' does not exist in the ue/gnb containers of the tester",
              scope="calibration")
        return {"executed": False, "reason": "ping missing"}

    def floor(key_name):
        vals = [ag[n][key_name]["median"] for n in ("C0-tester", "C0-edge", "C0-remote")
                if ag.get(n) and ag[n].get(key_name)]
        return max(vals) if vals else None
    floor_min, floor_p50 = floor("net_min"), floor("net_p50")
    if floor_min is None or floor_p50 is None:
        warning("V3 NOT EXECUTED: no valid C0 floor to compare with", scope="calibration")
        return {"executed": False, "reason": "no C0 floor"}

    def node_clock():
        r = tcb.kexec(tcb.TESTER_POD, c, "date", "+%s.%N", check=False,
                      quiet=True, timeout=20)
        try:
            return float(r.stdout.strip())
        except ValueError:
            return None

    # Size of the ping: the SAME total of bytes per round trip that the
    # instrument puts on the wire (a pose of 128 B + a frame packet of MTU B).
    # With the default ping of 84 B the comparison mixed serialization delay
    # -- ~10 us per store-and-forward hop for each 1228 B on 1 GbE -- with
    # the overhead of the instrument. The IP+ICMP and IP+UDP headers are equal (28 B).
    ping_size = (128 + tcb.PROFILES[args.prof]["mtu"]) // 2
    info(f"ping with {ping_size} B of payload: same bytes per round trip as "
         f"pose + frame packet")
    fps = {"edge": tcb.target_fps("free5gc-mec-app"),
           "remote": tcb.target_fps("free5gc-remote-app")}
    targets = (("edge", ctx["ip_mec"], MEC), ("remote", ctx["ip_remote"], REM))
    outcome, consistent = {}, True
    for which_side, ip, srv in targets:
        filename, pidf = f"/tmp/v3-ping-{which_side}.txt", f"/tmp/v3-ping-{which_side}.pid"
        due = int(args.dur + 60)      # safety ceiling; the normal end is SIGINT
        tcb.kexec(tcb.TESTER_POD, c, "sh", "-c",
                  f"ping -D -s {ping_size} -i 0.02 -w {due} {ip} </dev/null >{filename} 2>&1 & "
                  f"echo $! >{pidf}", check=True, quiet=True, timeout=30)
        tag = f"V3-C1-{which_side}"
        csv = remote_csv(CLI, tag)
        reg = measure_or_record("V3", "no-5g", CLI, f"{ip}:{tcb.VR_PORT}",
                               ctx["ip_tester"], srv, SRV_METRICS, fps[which_side], args,
                               tag=tag, csv=csv, before=node_clock,
                               after=node_clock)
        records.append(reg)
        copy_csv(CLI, csv, args.output, tag)
        # SIGINT makes iputils close at once and print the statistics; the
        # wait only checks the final line, without fetching the file at every turn.
        tcb.kexec(tcb.TESTER_POD, c, "sh", "-c", f"kill -INT $(cat {pidf}) 2>/dev/null",
                  check=False, quiet=True, timeout=20)
        tcb.wait_for(f"ping to {ip} to end",
                   lambda: tcb.kexec(tcb.TESTER_POD, c, "grep", "-q", "statistics",
                                     filename, check=False, quiet=True,
                                     timeout=20).returncode == 0,
                   due + 30, interval=1)
        txt = tcb.kexec(tcb.TESTER_POD, c, "cat", filename, check=False,
                          quiet=True, timeout=30).stdout
        sample_list = [(float(m.group(1)), float(m.group(2)) * 1000)
                    for m in re.finditer(r"^\[(\d+\.\d+)\].*time=([\d.]+) ms",
                                         txt, re.M)]
        start_on_node, end_on_node = (reg.get("node_marks") or [None, None])
        window = sample_list
        if start_on_node and end_on_node:
            window = [a for a in sample_list
                      if start_on_node + args.warmup + 0.5 <= a[0] <= end_on_node - 1.0]
        if len(window) < 50:
            warning(f"V3 {which_side}: only {len(window)} ping replies inside the window "
                  f"of the client ({len(sample_list)} in total)", scope="calibration")
            consistent = False
            continue
        rtts = [a[1] for a in window]
        p_min, p_p50, p_p95 = min(rtts), statistics.median(rtts), _pct(rtts, 0.95)
        if not reg.get("valid"):
            consistent = False
            outcome[which_side] = {"ip": ip, "reason": "invalid C1 run"}
            continue
        n_min, n_p50 = reg["metrics"]["net_min"], reg["metrics"]["net_p50"]
        d_min, d_p50 = n_min - p_min, n_p50 - p_p50
        TOL = 50.0      # resolution of ping (1 us) + scheduling noise
        ok_min = -TOL <= d_min <= 2 * floor_min + TOL
        ok_p50 = -TOL <= d_p50 <= 2 * floor_p50 + TOL
        consistent = consistent and ok_min and ok_p50
        outcome[which_side] = {
            "ip": ip, "replies_in_window": len(rtts),
            "ping_us": {"min": p_min, "p50": p_p50, "p95": p_p95},
            "net_rtt_us": {"min": n_min, "p50": n_p50},
            "difference_us": {"min": d_min, "p50": d_p50},
            "limit_us": {"min": [-TOL, 2 * floor_min + TOL],
                          "p50": [-TOL, 2 * floor_p50 + TOL]},
            "consistent": ok_min and ok_p50}
        for rot, n, p, d, floor_, okk in (("min", n_min, p_min, d_min, floor_min, ok_min),
                                        ("p50", n_p50, p_p50, d_p50, floor_p50, ok_p50)):
            print(f"       C1-{which_side:<7}{rot}: net_rtt={n:>6.0f}  ping={p:>6.0f}  "
                  f"difference={d:>+5.0f} us  (accepted -{TOL:.0f}..{2 * floor_ + TOL:.0f})"
                  f"  [{'consistent' if okk else 'INCONSISTENT'}]")
        info(f"{len(rtts)} ping replies simultaneous with the flow; ping p95 {p_p95:.0f} us")
        time.sleep(args.pause)
    (ok if consistent else warning)(
        "V3 CONSISTENT: instrument and independent witness agree within the floor"
        if consistent else "V3 INCONSISTENT: the instrument disagrees with the independent witness")
    return {"executed": True, "consistent": consistent, "ping_size_b": ping_size,
            "floor_min_us": floor_min,
            "floor_p50_us": floor_p50, "paths": outcome}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def report(args, ctx, placement, ag, v1, v2, v3):
    L = []
    L.append(f"CALIBRATION OF THE INSTRUMENT -- profile {args.prof}, "
             f"{args.repetitions} repetitions of {args.dur:g}s (warm-up {args.warmup:g}s)")
    L.append(f"placement: {json.dumps(placement)}")
    L.append("")
    L.append("1. CONTROL LADDER  (net_rtt in us; median across repetitions [min-max])")
    L.append(f"   {'step':<11}{'valid':>8}{'net min':>9}  {'net p50':>20}{'sd':>8}{'net p99':>9}"
             f"{'jitter':>8}{'loss %':>9}{'Mbps':>7}")
    for name_str in STEP_ORDER:
        a = ag.get(name_str)
        if not a:
            continue
        p50 = a["net_p50"]

        def med(k, decimals=0):
            return num(a[k]["median"], decimals) if a.get(k) else "-"
        band = (f"{p50['median']:.0f} [{p50['min']:.0f}-{p50['max']:.0f}]"
                 if p50 else "-")
        dev_ = num(p50["sd"], 0) if p50 and p50["sd"] is not None else "-"
        L.append(f"   {name_str:<11}{a['valid_runs']:>4}/{a['runs']:<3}{med('net_min'):>9}  {band:>20}{dev_:>8}"
                 f"{med('net_p99'):>9}{med('jitter_net'):>8}{med('loss_pct', 3):>9}"
                 f"{med('mbps', 2):>7}")

    def m(n):
        return ag[n]["net_p50"]["median"] if ag.get(n) and ag[n]["net_p50"] else None
    floors = {n: m(n) for n in ("C0-tester", "C0-edge", "C0-remote") if m(n) is not None}
    floor = max(floors.values()) if floors else None
    L.append("")
    L.append("2. DECOMPOSITION OF net_rtt p50  (us)")
    L.append(f"   instrument floor (largest C0): {num(floor, 0)}   per machine: "
             + ", ".join(f"{k}={v:.0f}" for k, v in floors.items()))
    L.append(f"   {'path':<8}{'C1 net no 5G':>16}{'C2 5G':>10}{'net - floor':>14}"
             f"{'5G (C2-C1)':>13}")
    for which_side in ("edge", "remote"):
        c1, c2 = m(f"C1-{which_side}"), m(f"C2-{which_side}")
        L.append(f"   {which_side:<8}{num(c1, 0):>16}{num(c2, 0):>10}"
                 f"{num(None if c1 is None or floor is None else c1 - floor, 0):>14}"
                 f"{num(None if c1 is None or c2 is None else c2 - c1, 0):>13}")

    L.append("")
    L.append("3. NOISE x EFFECT")
    b, n = ag.get("C2-edge"), ag.get("C2-remote")
    effect = None
    if b and n and b["net_p50"] and n["net_p50"]:
        effect = n["net_p50"]["median"] - b["net_p50"]["median"]
        sb, sn = b["net_p50"]["sd"], n["net_p50"]["sd"]
        L.append(f"   remote application (2 UPFs) in net_rtt p50 (C2-remote - C2-edge): "
                 f"{effect:.0f} us")
        L.append("   (it is not the gain of the LBO: that comes from a-mec x b-mec, in "
                 "campaign.py)")
        if sb is not None and sn is not None:
            mde, gl = min_detectable_effect(sb, b["net_p50"]["n"],
                                                 sn, n["net_p50"]["n"])
            L.append(f"   deviation between repetitions: edge {sb:.0f} us, remote {sn:.0f} us")
            L.append(f"   minimum detectable difference (alpha 5%, power 80%, Student t, "
                     f"Welch df = {num(gl, 1)}): {mde:.0f} us"
                     + (f" -> effect = {effect / mde:.1f}x this difference" if mde else ""))
        else:
            L.append("   (deviation unavailable: run with --repetitions >= 2)")
    s0 = ag.get("C0-tester", {}).get("net_p50")
    if s0 and s0["sd"] is not None:
        L.append(f"   noise of the instrument itself (sd of p50 in C0-tester): {s0['sd']:.0f} us")

    L.append("")
    L.append("4. ACCURACY VALIDATIONS")
    for rot, v, key_name in (("V1 sleep at the server -> net_rtt still", v1, "passed"),
                          ("V2 netem -> net_rtt 1:1", v2, "passed"),
                          ("V3 simultaneous ping (witness)", v3, "consistent")):
        if not v or not v.get("executed"):
            state = f"NOT EXECUTED ({(v or {}).get('reason', 'skipped')})"
        else:
            state = "OK" if v.get(key_name) else "FAILED"
        L.append(f"   {rot:<34} {state}")
    return L


# --------------------------------------------------------------------------
def main():
    global _netem_container
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    lists = lambda s: [float(x) for x in s.split(",") if x.strip()]  # noqa: E731
    ap.add_argument("--profile", default=tcb.DEFAULT_PROFILE, choices=sorted(tcb.PROFILES))
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--duration", type=float, default=30)
    ap.add_argument("--warmup", type=float, default=5)
    ap.add_argument("--pause", type=float, default=3,
                    help="seconds between runs (the previous session ends)")
    ap.add_argument("--render-ms", type=lists, default=None,
                    help="renders of V1, e.g. 0,1,2,3 (default: fractions of the slack)")
    ap.add_argument("--delay-ms", type=lists, default=None,
                    help="delays of V2 per direction, e.g. 0,1,2,5")
    ap.add_argument("--ping-n", type=int, default=500)
    ap.add_argument("--skip-5g", action="store_true", help="without the C2 steps")
    ap.add_argument("--skip-v1", action="store_true")
    ap.add_argument("--skip-v2", action="store_true")
    ap.add_argument("--skip-v3", action="store_true")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--load-subscribers", type=int, default=0, metavar="N")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--mongo-port", type=int, default=27017)
    ap.add_argument("--namespace", default=tcb.NS)
    ap.add_argument("--output", default=None)
    ap.add_argument("--concise", action="store_true")
    args = ap.parse_args()

    tcb.NS, tcb.CONCISE, tcb.PAUSE = args.namespace, args.concise, False
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    args.output = args.output or os.path.join(tcb.BASE, "calibration",
                                            f"{stamp}-{args.prof}")
    # Namespace with the fields that steps 01-10 of the test of Scenario B read.
    targs = argparse.Namespace(
        attempts=1, repetitions=1, deploy=args.deploy, include_discarded=False,
        no_teardown=True, teardown_timeout=300,
        load_subscribers=args.load_subscribers, dur=args.dur,
        warmup=args.warmup, proof_duration=10, proof_only=False, prof=args.prof,
        list_profiles=False, output=args.output, timeout=args.timeout,
        mongo_port=args.mongo_port, namespace=args.namespace,
        skip_validate=False, step_by_step=False, concise=args.concise)

    t0 = time.time()
    records, ctx, placement, ag = [], {}, {}, {}
    v1 = v2 = v3 = None
    rc, interrupted, err = 0, False, None
    try:
        tcb.p01_tools()
        tcb.p02_validate(targs)
        tcb.p03_deploy(targs)
        tcb.p04_pods(targs)
        placement = tcb.p05_placement()
        if not args.skip_5g:
            tcb.p06_subscribers(targs)
            tcb.p07_pfcp(targs)
        tcb.p08_tester(targs)
        ue_ip = None
        if not args.skip_5g:
            ue_ip = tcb.p09_session(targs)
            tcb.p10_routes()
        _, ip_mec = active_pod("mec-app")
        _, ip_remote = active_pod("remote-app")
        ip_tester = tcb.kubectl("get", "pod", tcb.TESTER_POD, "-o",
                                "jsonpath={.status.podIP}", quiet=True).stdout.strip()
        ctx = {"ip_tester": ip_tester, "ip_mec": ip_mec, "ip_remote": ip_remote,
               "ue_ip": ue_ip, "mec_cluster_ip": tcb.MEC_IP,
               "remote_cluster_ip": tcb.REMOTE_IP}
        info(f"tester eth0={ip_tester}  mec-app pod={ip_mec}  remote-app pod={ip_remote}"
             f"  UE={ue_ip}")
        exec_in(CLI, "mkdir", "-p", "/data/calibration")
        os.makedirs(args.output, exist_ok=True)

        ladder(args, ctx, records)
        ag = aggregate_steps(records)
        v1 = None if args.skip_v1 else v1_render(args, records)
        v2 = None if args.skip_v2 else v2_netem(args, records)
        v3 = None if args.skip_v3 else v3_ping(args, ctx, ag, records)
    except Failure as e:
        err = str(e)
        print(f"\n{tcb.RED}FAILED:{tcb.RESET} {err}", file=sys.stderr)
        rc = 1
    except KeyboardInterrupt:
        interrupted, rc = True, 130
        print("\ninterrupted", file=sys.stderr)
    finally:
        # The loopback of the tester and the calibration server return to their
        # original state on any exit -- a netem forgotten on lo would delay the
        # next campaign without anyone knowing.
        try:
            if _netem_container:
                remove_netem(_netem_container)
            stop_cal_server()
        except Exception as exc:                          # noqa: BLE001
            print(f"  {tcb.YELLOW}cleanup failed: {exc}{tcb.RESET}", file=sys.stderr)

    ag = ag or aggregate_steps(records)
    lines = report(args, ctx, placement, ag, v1, v2, v3) if records else []
    if lines:
        print(f"\n{'#' * 72}")
        for line in lines:
            print(line)
        print("#" * 72)
    if records or err:
        os.makedirs(args.output, exist_ok=True)
        with open(os.path.join(args.output, "calibration.json"), "w", encoding="utf-8") as fh:
            json.dump({"args": vars(args), "context": ctx, "placement": placement,
                       "aggregates": ag, "v1": v1, "v2": v2, "v3": v3,
                       "records": records, "warnings": tcb.warns, "error": err,
                       "seconds": round(time.time() - t0, 1)}, fh, indent=2)
        with open(os.path.join(args.output, "report.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        info(f"results in {args.output}")

    # The final line tells the truth, without rounding to the good side.
    measurements = [r for r in records if r["step"].startswith("C")]
    invalid = [r["run_label"] for r in measurements if not r["valid"]]
    failures = [n for n, v, k in (("V1", v1, "passed"), ("V2", v2, "passed"),
                                 ("V3", v3, "consistent"))
              if v and v.get("executed") and not v.get(k)]
    missing = [n for n, v in (("V1", v1), ("V2", v2), ("V3", v3))
                if not v or not v.get("executed")]
    elapsed = f"{time.time() - t0:.0f}s"
    if interrupted:
        print(f"\n{tcb.YELLOW}CALIBRATION INTERRUPTED{tcb.RESET} -- {len(measurements)} runs in {elapsed}")
    elif err or not measurements:
        print(f"\n{tcb.RED}CALIBRATION NOT COMPLETED{tcb.RESET} -- {len(measurements)} runs in {elapsed}")
        rc = rc or 1
    elif invalid or failures:
        print(f"\n{tcb.RED}INSTRUMENT NOT CALIBRATED{tcb.RESET} -- "
              f"{len(invalid)} invalid run(s), failed validations: "
              f"{', '.join(failures) or 'none'} ({elapsed})")
        rc = 1
    elif missing:
        print(f"\n{tcb.YELLOW}INSTRUMENT PARTIALLY CALIBRATED{tcb.RESET} -- "
              f"{len(measurements)} valid runs; not executed: {', '.join(missing)} ({elapsed})")
        rc = 3
    else:
        print(f"\n{tcb.GREEN}INSTRUMENT CALIBRATED{tcb.RESET} -- {len(measurements)} runs "
              f"valid, V1, V2 and V3 passed ({elapsed})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
