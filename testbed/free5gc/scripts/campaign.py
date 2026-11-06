#!/usr/bin/env python3
"""
A x B campaign: the comparison of the evaluation -- centralized UPF (Scenario A)
against a dUPF with local breakout (Scenario B), with the SAME destination at
the edge -- with the backhaul free and congested.

HOW IT WORKS

    The campaign is made of ROUNDS. Each round runs both scenarios in sequence,
    calling run_scenario_a.py and run_scenario_b.py exactly as they are:

        round 1: A -> B      round 2: B -> A      round 3: A -> B ...

    The order alternates so that no drift of the cluster along the campaign
    always falls on the same scenario. Each round becomes a PAIR: the two
    measurements were made minutes apart, and the difference is computed within
    the pair before being aggregated.

WHAT IS MEASURED (--profile, --with-remote, --background)

    --profile accepts a list. --profile vr-cloud,vr-extreme,teleoperation runs
    ALL rounds, at all levels, of vr-cloud; then all of vr-extreme; then those
    of teleoperation. Each profile writes to its own folder
    (<output>/<level>/<profile>/) and gets its own comparison at the end.

    By default only what the comparison uses: a-mec and b-mec. --with-remote
    also measures b-remote (one more measurement per execution of B). a-remote
    is not measured in the campaign: it changes the destination without changing
    the anchor and enters neither comparison. The proof of the mechanism (step
    11 of the tests) always uses both paths.

    --background chooses the congestion levels, in % of the measured capacity:
        --background 0,80,95   the default
        --background 0,99      only no background and 99%
        --background 0         the campaign without congestion

BACKHAUL CONGESTION

    In the centralized case the MEC traffic leaves the edge, goes to the UPF in
    the core and comes back: it crosses the core -> edge link TWICE. With LBO it
    leaves at the edge and crosses it NONE. To measure what that is worth, each
    scenario goes through levels of background traffic on this link:

        no-background   the link with only the traffic of the experiment
        background-80   iperf3 UDP from the core to the edge at 80% of the capacity
        background-95   same, at 95%

    Where the background comes from (--background-source):
        gtp     (default) SUBSCRIBER traffic: iperf3 from the node of the anchor
                UPF to a second UERANSIM on brix-porvir-03, THROUGH THE GTP-U
                TUNNEL (background/background-gtp.yaml, scripts/background_gtp.py).
                In A it goes through the same central UPF as the experiment; in B,
                through the PSA-UPF, directly to the background gNB, without
                touching the Edge Node. The background UE is prepared from step 07
                of each execution (provisioning in Mongo -- step 06 deletes the
                subscribers -- and, after a deployment, a recreated pod and a new
                session), in parallel with steps 08-11.
        direct  an earlier campaign: iperf3 from the node of the anchor UPF
                (petshopboys) to brix-porvir-04, without going through a UPF
                (background/iperf.yaml).
    The capacity is measured with iperf3 TCP at the start of EACH round (with
    gtp, petshopboys -> brix-03 outside the tunnel) and holds for A and B of that
    round. A measurement below 90% of the median of the previous rounds (of this
    folder, any profile) is repeated up to 2 times, and the largest one holds;
    without a previous round, there are 2 measurements. Reason: in an earlier
    campaign, 7 of 90 rounds measured ~700 Mbps on a ~887 Mbps link, and the
    levels of 95 and 99% became 75-79% in reality. The measurements are kept in
    capacity_measurements in background.json.
    Nothing goes beyond 100%: continuous overload is not the congestion of a real network.

    The background is on only during step 12 of the test (the measurement).
    Deployment, PDU session and the proof of the mechanism happen without it.
    A pilot showed that the background and the measured traffic share the same
    queue, that the generator does not interfere through CPU and that the PFCP
    of Scenario B survives at 95%.

    Within the round each scenario comes up ONCE and goes through all levels, in
    an order that ROTATES between rounds, so that no level is always right after
    the deployment. After the last level the scenario is torn down with the same
    function the scripts use (by name; the namespace is not touched).

    A congested execution only holds if the background was really applied:
    at least 90% of the request crossed the link, counted on the UDP counters of
    the receiver (what the receiver itself dropped also crossed the link). With
    gtp, on the counters of the chain of the background pod; in addition, the
    GTP-U must have come ONLY from the anchor UPF (tcpdump in the background pod)
    and the background must have been turned on within the warm-up.

WHAT COMES OUT

    Per level, in <output>/<level>/<profile>/ (with --background 0, in
    <output>/<profile>/). The default <output> is campaign-data
    (--background-source gtp) or campaign-data-direct (--background-source direct):
        a-vs-b.md               tables ready for the text
        a-vs-b-per-round.csv    one line per round, with the KPIs of the measured paths
        a-vs-b.json             everything, raw
        round-NN/{a,b}/         the full output of each script, with output.log
                                (and background.json at the levels with background)

    Main        a-mec x b-mec     the gain of the LBO over the centralized case: same
                                  UE, same destination, same load, same background; only
                                  the anchor of the user plane changes place.
    Secondary   b-remote x b-mec  (only with --with-remote) how much longer it takes if
                                  the application is outside, with the 2 UPFs of B.

    With more than one level, in <output>/:
        lbo-under-congestion-<profile>.md   THE HIGHLIGHT: the gain of the LBO at each
                                            level and how much the congestion costs
                                            each scenario, paired within the round
        lbo-under-congestion-<profile>.csv / .json

    A pair only enters A x B if BOTH executions passed the health guards of the
    MEC path. The guards that only concern the remote path -- those of the
    b-remote measurement and "loss very different between the paths", which
    compares MEC and remote WITHIN the execution -- only remove the execution
    from the b-remote x b-mec comparison. Under congestion b-remote crosses the
    link and loses packets, b-mec does not; if that guard removed the pair, it
    would remove exactly the rounds in which the LBO shows the most (an earlier
    campaign had 0 pairs on vr-cloud at 99%).

WINDOWS

    Runs as is. Files are written in UTF-8 and the kubectl cp of the tests uses a
    relative destination (in an absolute path, "C:" becomes a pod name). Prefer
    an --output outside OneDrive: synchronization may hold a file open.

RELIABILITY (what an earlier campaign taught)

    After each execution the campaign checks the instrument: the per-frame CSV
    must have come from the tester with one line per complete frame of the
    summary (if not, it is copied again, twice); the receive buffer of the tester
    must have the minimum 4 MB; the timestamp must come from the kernel. On a
    failure, the execution is kept in <a|b>.instrument-<k> and the campaign
    STOPS, because the failure would repeat in all the following ones. Running
    the same command after fixing it continues from where it stopped.

    An execution that did not complete, or in which the background was not
    applied, is kept in <a|b>.failed-<k> and redone once at the end of the round
    (--no-retry turns this off). A measurement that fell on a quality guard is
    NEVER redone: redoing until it passes would select the good rounds.

    Each time the command runs, it writes campaign-<start>.json at the root
    (command, git commit and what was changed, versions) and campaign-<start>.log
    (everything that was printed). While it runs, the computer does not sleep.

    Baseline sentinel: after each execution WITHOUT background, the p50 of the
    MEC path is compared with the median of the previous rounds; more than 25%
    away raises an alert at once (an external defect was once only seen days
    later). The reports repeat the check at the end.

    In the reports: paired median and "B lower" next to the mean (they resist a
    bimodal round), incomplete frames (latency only counts complete frames), the
    effective load of the link in A (the traffic of the application adds to the
    background) and the baseline sentinel without background.

    A level that already has a result is skipped: if the campaign is interrupted,
    running the same command again continues from where it stopped. --first-round N
    starts at N and the comparison keeps reading everything in the folder.

Usage:
    python3 scripts/campaign.py --rounds 30 --profile vr-cloud,vr-extreme,teleoperation --background 0,50,80,95,99 --with-remote --load-subscribers 5
    python3 scripts/campaign.py --rounds 10 --profile teleoperation --load-subscribers 5
    python3 scripts/campaign.py --rounds 10 --profile teleoperation --background 0,99 --load-subscribers 5
    python3 scripts/campaign.py --rounds 10 --profile teleoperation --background 0 --with-remote --load-subscribers 5
    python3 scripts/campaign.py --rounds 10 --profile teleoperation --background-source direct --load-subscribers 5
    python3 scripts/campaign.py --compare-only campaign-data
    python3 scripts/campaign.py --compare-only campaign-data --profile teleoperation
"""
import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time

if sys.version_info < (3, 8):
    sys.exit("campaign.py needs Python 3.8 or newer")

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
SCRIPTS = {"a": os.path.join(HERE, "run_scenario_a.py"),
           "b": os.path.join(HERE, "run_scenario_b.py")}

# (key, label, path in the vr_client summary, divisor, unit, decimals, lower_is_better)
KPIS = [
    ("net_p50", "Network delay p50", ("net_rtt_us", "p50"), 1000.0, "ms", 3, True),
    ("net_p95", "Network delay p95", ("net_rtt_us", "p95"), 1000.0, "ms", 3, True),
    ("net_p99", "Network delay p99", ("net_rtt_us", "p99"), 1000.0, "ms", 3, True),
    ("net_media", "Network delay (mean)", ("net_rtt_us", "mean"), 1000.0, "ms", 3, True),
    ("jitter_net", "Network jitter", ("jitter_net_us",), 1.0, "us", 1, True),
    ("m2p_p50", "Motion-to-photon p50", ("m2p_us", "p50"), 1000.0, "ms", 3, True),
    ("m2p_p95", "Motion-to-photon p95", ("m2p_us", "p95"), 1000.0, "ms", 3, True),
    ("loss_pct", "DL packet loss", ("dl_packet_loss_srv_pct",), 1.0, "%", 3, True),
    # Latency is only computed over COMPLETE frames: with many incomplete ones,
    # the delay of the path comes out optimistic. This KPI says how much of the sample was left.
    ("incomplete_pct", "Incomplete frames", ("frames_incomplete_pct",), 1.0, "%", 2, True),
    ("throughput_mbps", "DL throughput", ("dl_throughput_mbps",), 1.0, "Mbps", 2, None),
]
# The KPIs of the highlight. p99 comes right after p50 on purpose: in the pilot the
# congestion showed up first in the TAIL, and it is the tail that teleoperation feels.
KPIS_HIGHLIGHT = ("net_p50", "net_p99", "jitter_net", "loss_pct", "incomplete_pct")

# Quantiles of the Student t (two-sided 95% and one-sided 80%). With few rounds the
# normal approximation would narrow the interval and promise more than the data give.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
        15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080,
        22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
        29: 2.045, 30: 2.042}
T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896,
       8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876, 12: 0.873, 13: 0.870, 14: 0.868,
       15: 0.866, 16: 0.865, 17: 0.863, 18: 0.862, 19: 0.861, 20: 0.860, 21: 0.859,
       22: 0.858, 23: 0.858, 24: 0.857, 25: 0.856, 26: 0.856, 27: 0.855, 28: 0.855,
       29: 0.854, 30: 0.854}

# --- background traffic (background/iperf.yaml) ---------------------------------
NS = "free5gc"
BACKGROUND_MANIFEST = os.path.join(BASE, "background", "iperf.yaml")
IPERF_SRV = "background-iperf-server"   # receiver at the edge, outside the experiment
IPERF_CLI = "background-iperf-client"    # generator on the node of the anchor UPF
IPERF_PORT = 5201
# UDP payload: fits in the MTU 1450 of the Calico VXLAN without fragmenting. It is also
# the size used to convert datagrams counted at the receiver into Mbps.
DATAGRAM = 1400
MBPS_PER_FLOW = 250
# epc-mode of the UPF through which the centralized traffic enters the core: the generator
# must be on the SAME node so as to leave through the same network card.
ANCHOR = {"a": "upf", "b": "psa-upf"}
# Fraction of the requested background that must have crossed the link for the level to hold.
MIN_BACKGROUND_DELIVERED = 0.90
# iperf asks for a long -t and is turned off when step 12 ends; this ceiling
# only exists so that it does not stay on forever if the control is lost.
BACKGROUND_MAX_S = 1800
# A capacity measured below this fraction of the median of the previous rounds is
# repeated up to CAPACITY_REPEATS more times; the largest measurement holds.
CAPACITY_MIN_FRAC = 0.90
CAPACITY_REPEATS = 2
_capacities = []   # accepted in this folder, all rounds and profiles
# --background-source gtp: the module scripts/background_gtp.py (loaded in main).
R = None
DEFAULT_OUTPUT = {"gtp": "campaign-data", "direct": "campaign-data-direct"}

GREEN, RED, YELLOW, GREY, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if os.name == "nt":
    os.system("")   # turns on ANSI sequences (colors) in the Windows console
for _flow in (sys.stdout, sys.stderr):
    # A console or file in cp1252 does not crash the campaign because of a character.
    if hasattr(_flow, "reconfigure"):
        _flow.reconfigure(errors="replace")
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = GREY = RESET = ""


class BackgroundError(Exception):
    """Problem in setting up the background: it is not the failure of ONE measurement, but
    something that would invalidate all the following levels in the same way. Stops the campaign."""


class InstrumentError(Exception):
    """The measurement instrument failed in a way that would repeat in all the following
    executions (copy of the per-frame CSV, buffer of the tester, timestamp). Stops the
    campaign the FIRST time, and not days later."""


def t_quantile(table, gl, normal):
    if gl is None or gl > 30:
        return normal
    return table[max(k for k in table if k <= max(1, int(gl)))]


def val_(summ, path_name):
    v = summ
    for k in path_name:
        if not isinstance(v, dict):
            return None
        v = v.get(k)
    return v if isinstance(v, (int, float)) else None


def mean_sd(vs):
    vs = [v for v in vs if v is not None]
    if not vs:
        return None, None
    return sum(vs) / len(vs), (statistics.stdev(vs) if len(vs) > 1 else None)


def paired(diffs):
    """Mean of the paired differences, 95% CI and minimum detectable difference."""
    n = len(diffs)
    if not n:
        return None
    m = sum(diffs) / n
    if n < 2:
        return {"n": n, "mean": m, "std": None, "ci": None, "mde": None}
    std = statistics.stdev(diffs)
    ep = std / math.sqrt(n)
    t975, t80 = t_quantile(T975, n - 1, 1.960), t_quantile(T80, n - 1, 0.842)
    return {"n": n, "mean": m, "std": std, "ci": (m - t975 * ep, m + t975 * ep),
            "mde": (t975 + t80) * ep}


def fmt(v, decimals):
    return "-" if v is None else f"{v:.{decimals}f}"


def level_name(level):
    return "no-background" if level == 0 else f"background-{level}"


def level_label(level):
    return "no background" if level == 0 else f"{level}%"


BACKGROUND_ORIGIN = {
    "direct": "iperf3 UDP from the node of the anchor UPF to a small machine outside the experiment",
    "gtp": ("iperf3 UDP through the GTP-U tunnel, from the anchor UPF (A: the central UPF; B: the "
            "PSA-UPF) to a second UERANSIM on a small machine outside the experiment"),
    "mixed": ("DIRECT and GTP-U TUNNEL background mixed in this folder -- check the "
              "background.json files before using these numbers"),
}


def background_mode(backgrounds):
    """"gtp" or "direct" from what was recorded. A background.json without "mode" is
    from the earlier campaign, which only had the direct background."""
    modes = {f.get("mode", "direct") for f in backgrounds if f}
    return "gtp" if modes == {"gtp"} else ("direct" if modes <= {"direct"} else "mixed")


def level_root(output, prof, level, legacy):
    """With --background 0 the campaign writes where it always did. With levels, each one
    gets <output>/<level>/<profile>/ -- the name of the last folder is still the
    profile, from which --compare-only takes the profile."""
    if legacy:
        return os.path.join(output, prof)
    return os.path.join(output, level_name(level), prof)


# --------------------------------------------------------------------------
# background traffic
# --------------------------------------------------------------------------
def kubectl(*a, timeout=120):
    try:
        return subprocess.run(["kubectl", "-n", NS, *a], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(a, 124, "", f"timeout ({timeout}s)")


def node_of(selector):
    r = kubectl("get", "pod", "-l", selector, "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].spec.nodeName} {.items[0].status.podIP}")
    parts = r.stdout.split()
    return (parts[0], parts[1]) if len(parts) == 2 else (None, None)


def start_iperf(timeout):
    print(f"\n  background: applying {os.path.relpath(BACKGROUND_MANIFEST, BASE)}")
    r = kubectl("apply", "-f", BACKGROUND_MANIFEST)
    if r.returncode:
        raise BackgroundError(f"kubectl apply of the background failed: {r.stderr.strip()[:300]}")
    for dep in (IPERF_SRV, IPERF_CLI):
        r = kubectl("rollout", "status", f"deploy/{dep}", f"--timeout={timeout}s",
                    timeout=timeout + 30)
        if r.returncode:
            raise BackgroundError(f"{dep} was not ready: {(r.stderr or r.stdout).strip()[:300]}")
    server_node, ip_srv = node_of(f"app={IPERF_SRV}")
    client_node, _ = node_of(f"app={IPERF_CLI}")
    if not ip_srv or not client_node:
        raise BackgroundError("the iperf pods did not become Running")
    print(f"  background: generator on {client_node}, receiver on {server_node} ({ip_srv})")
    return ip_srv


def iperf_node(dep, *cmd, timeout=60):
    return kubectl("exec", f"deploy/{dep}", "-c", "iperf", "--", *cmd, timeout=timeout)


def capacity(ip_srv, seconds):
    """iperf3 TCP, 4 flows, core -> edge. TCP rises up to the narrowest link and stops:
    the received throughput is the useful capacity of the path."""
    for attempt in (1, 2):
        r = iperf_node(IPERF_CLI, "iperf3", "-c", ip_srv, "-p", str(IPERF_PORT), "-P", "4",
                     "-t", str(seconds), "-J", timeout=seconds + 60)
        try:
            j = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
        except ValueError:
            j = {"error": (r.stderr or r.stdout or "no output").strip()[:300]}
        if "busy" in str(j.get("error", "")) and attempt == 1:
            time.sleep(10)
            continue
        break
    rec = ((j.get("end") or {}).get("sum_received") or {}).get("bits_per_second")
    if j.get("error") or not rec:
        raise BackgroundError(f"could not measure the capacity: {j.get('error', 'no throughput received')}")
    return rec / 1e6


def udp_receiver():
    """(datagrams received, datagrams with error) in the netns of the receiver. Error
    includes the drop due to a full buffer -- which also crossed the link."""
    r = iperf_node(IPERF_SRV, "cat", "/proc/net/snmp")
    lines = [l.split()[1:] for l in r.stdout.splitlines() if l.startswith("Udp:")]
    if len(lines) < 2:
        return None
    c = dict(zip(lines[0], lines[1]))
    try:
        return int(c["InDatagrams"]), int(c["InErrors"])
    except (KeyError, ValueError):
        return None


def background_on(scen, background):
    """Checks the placement AT THIS INSTANT (the scenario is running) and turns iperf on.
    A generator outside the node of the anchor would not compete for the queue of the
    application; a receiver inside the experiment would worsen B through CPU."""
    anchor_node, _ = node_of(f"epc-mode={ANCHOR[scen]}")
    client_node, _ = node_of(f"app={IPERF_CLI}")
    server_node, _ = node_of(f"app={IPERF_SRV}")
    experiment = {node_of("epc-mode=mec-app")[0], node_of("epc-mode=ueransim")[0]} - {None}
    if not anchor_node or client_node != anchor_node:
        raise BackgroundError(f"the generator is on {client_node} and the anchor UPF ({ANCHOR[scen]}) "
                        f"on {anchor_node}: adjust the nodeSelector in background/iperf.yaml")
    if server_node in experiment:
        raise BackgroundError(f"the receiver landed on {server_node}, which is part of the experiment "
                        "(Edge Node or tester): choose another small machine in background/iperf.yaml")
    flows = max(1, math.ceil(background["requested_mbps"] / MBPS_PER_FLOW))
    cmd = ["kubectl", "-n", NS, "exec", f"deploy/{IPERF_CLI}", "-c", "iperf", "--",
           "iperf3", "-c", background["ip_srv"], "-p", str(IPERF_PORT), "-u",
           "-b", f"{background['requested_mbps'] / flows:.1f}M", "-l", str(DATAGRAM),
           "-P", str(flows), "-t", str(BACKGROUND_MAX_S)]
    u0 = udp_receiver()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"proc": proc, "u0": u0, "t0": time.time(), "generator_node": client_node,
            "receiver_node": server_node, "anchor_node": anchor_node, "flows": flows}


def background_off(state, background):
    iperf_node(IPERF_CLI, "pkill", "-f", "iperf3 -c", timeout=30)
    try:
        state["proc"].wait(timeout=15)
    except subprocess.TimeoutExpired:
        state["proc"].kill()
    seconds = time.time() - state["t0"]
    u1 = udp_receiver()
    reg = {"level": background["level"], "capacity_mbps": background["capacity_mbps"],
           "requested_mbps": background["requested_mbps"], "flows": state["flows"],
           "seconds_on": round(seconds, 1), "generator_node": state["generator_node"],
           "receiver_node": state["receiver_node"], "anchor_node": state["anchor_node"],
           "on": True, "crossed_mbps": None, "receiver_drops": None,
           "delivered_fraction": None}
    if state["u0"] and u1 and seconds > 0:
        received, errs = u1[0] - state["u0"][0], u1[1] - state["u0"][1]
        reg["crossed_mbps"] = (received + errs) * DATAGRAM * 8 / seconds / 1e6
        reg["receiver_drops"] = errs
        reg["delivered_fraction"] = reg["crossed_mbps"] / background["requested_mbps"]
    return reg


# --------------------------------------------------------------------------
# background through the GTP-U tunnel (--background-source gtp)
# --------------------------------------------------------------------------
def load_background_module():
    spec = importlib.util.spec_from_file_location("background_gtp", os.path.join(HERE, "background_gtp.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def start_gtp_background(timeout):
    print(f"\n  background: applying {os.path.relpath(R.MANIFEST, BASE)} (through the GTP-U tunnel)")
    try:
        R.apply(timeout)
    except R.GtpBackgroundError as e:
        raise BackgroundError(str(e))
    g_node, _ = R.pod(f"app={R.GENERATOR}")
    r_node, _ = R.pod(f"app={R.BG_GTP}")
    print(f"  background: generator on {g_node}, background UERANSIM on {r_node} (UE {R.IMSI})")


def gtp_background_capacity(seconds):
    """Like capacity(), up to the background pod and outside the tunnel -- with the IP of
    NOW, which changes each time the pod is recreated."""
    _, ip = R.pod(f"app={R.BG_GTP}")
    if not ip:
        raise BackgroundError(f"the pod {R.BG_GTP} is not Running: no destination to measure the capacity "
                        f"(kubectl -n {NS} get pod -l app={R.BG_GTP})")
    try:
        return R.capacity({"background_ip": ip}, seconds)
    except R.GtpBackgroundError as e:
        raise BackgroundError(str(e))


def recorded_capacities(output):
    """Capacities already recorded in the background.json files of this folder: the
    reference of a resumed campaign does not restart from zero."""
    caps = []
    for f in glob.glob(os.path.join(output, "*", "*", "round-*", "*", "background.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                c = json.load(fh).get("capacity_mbps")
        except (OSError, ValueError):
            continue
        if c:
            caps.append(c)
    return caps


def round_capacity(output, prof, levels, n):
    """(capacity, measurements) already recorded in this round by a valid execution,
    or (None, None). On a resume, what is missing from the round uses the SAME capacity
    -- and therefore the same background in Mbps -- as the rest of the pair."""
    for nv in levels:
        if not nv:
            continue
        for scen in ("a", "b"):
            f = os.path.join(round_folder(level_root(output, prof, nv, False), n), scen, "background.json")
            if not os.path.exists(f):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    fj = json.load(fh)
            except (OSError, ValueError):
                continue
            if fj.get("capacity_mbps"):
                return fj["capacity_mbps"], fj.get("capacity_measurements") or [fj["capacity_mbps"]]
    return None, None


def measure_capacity(args, ip_srv):
    """(capacity of the round, all measurements). A measurement below
    CAPACITY_MIN_FRAC of the median of the previous rounds is repeated and the largest
    holds: the background is a fraction of it, and an underestimated capacity becomes a
    level lower than the nominal one without anyone seeing. Without a reference yet
    (the first rounds), there are always 2 measurements."""
    ref = statistics.median(_capacities) if len(_capacities) >= 3 else None
    minimum = 1 if ref else 2
    measures = []
    for i in range(1 + CAPACITY_REPEATS):
        measures.append(gtp_background_capacity(args.capacity_duration) if args.background_source == "gtp"
                       else capacity(ip_srv, args.capacity_duration))
        if len(measures) >= minimum and (ref is None or max(measures) >= CAPACITY_MIN_FRAC * ref):
            break
        if i < CAPACITY_REPEATS:
            if ref:
                print(f"    {YELLOW}capacity {measures[-1]:.0f} Mbps, below "
                      f"{CAPACITY_MIN_FRAC:.0%} of the median of the previous rounds ({ref:.0f}); "
                      f"measuring again{RESET}")
            time.sleep(5)
    cap = max(measures)
    if ref and cap < CAPACITY_MIN_FRAC * ref:
        print(f"    {YELLOW}warning{RESET}: the capacity stayed low in the {len(measures)} measurements "
              f"({', '.join(f'{m:.0f}' for m in measures)} Mbps); going on with {cap:.0f} -- "
              "it may be the real link")
    _capacities.append(cap)
    return cap, measures


# (AMF, SMF, anchor UPF) when the background UE opened the current session.
_session_core = None


class BackgroundSetup(threading.Thread):
    """Gets the background UE ready for step 12, in parallel with steps 08-11 of the
    test. It starts at 07 because 06 (--load-subscribers) deletes every subscriber
    from Mongo, including the background one.

    The UE of the previous execution is only reused if the CORE is the same in
    which it opened the session (the same AMF, SMF and anchor UPF pods --
    R.core) and it is still registered and with an IP. Any deployment since
    then, at any level -- including a "no background" one, which does not prepare
    the background --, recreates the pod: the gNB kept the SCTP of an AMF that no
    longer exists, and the UE only LOOKS registered. The session survives the
    provisioning deleted by step 06, which is only consulted at registration and
    session setup."""

    def __init__(self, scen, restart, timeout):
        super().__init__(daemon=True)
        self.scen, self.restart, self.timeout = scen, restart, timeout
        self.est = self.err = self.phase = self.seconds = None
        self.restarted, self.t0 = False, time.time()
        self.start()

    def run(self):
        global _session_core
        try:
            self.phase = "placement"
            R.placement(self.scen)
            self.phase = "ue"
            R.provision()
            current = R.core(self.scen)
            ip = None
            if not self.restart and current == _session_core:
                ip = R.ue_ip()
                if ip and not R.ue_registered():
                    ip = None
            if not ip:
                _session_core = None
                ip = R.restart_ue(self.timeout)
                _session_core = current
                self.restarted = True
            self.phase = "placement"
            est = R.placement(self.scen)          # the recreated pod has another IP
            est.update(ue_ip=ip, scenario=self.scen)
            self.est = est
        except Exception as e:                      # noqa: BLE001
            self.err = e
        finally:
            self.seconds = time.time() - self.t0


def gtp_background_on(scen, background, setup, wait_for):
    """Turns the background on at step 12. Does not wait for the background UE beyond
    the warm-up: the background must be on when the measured window starts."""
    t12 = time.time()
    if setup is None:
        return {"failure": "the background UE was not prepared (step 07 did not appear in this attempt)"}
    setup.join(wait_for)
    if setup.is_alive():
        return {"failure": f"the background UE was not ready in time ({time.time() - setup.t0:.0f}s "
                         "since step 07); the background was not turned on"}
    if setup.err is not None:
        if setup.phase == "placement":
            raise BackgroundError(str(setup.err))
        return {"failure": f"background UE: {setup.err}"}
    est = setup.est
    on_ = R.turn_on(est, background["requested_mbps"], BACKGROUND_MAX_S)
    delay = time.time() - t12
    # Proof of the path DURING the measurement: the GTP-U that reaches the background pod
    # must come only from the anchor UPF. In B, coming from the I-UPF, the background would
    # be going through the Edge Node and b-mec would worsen for another reason.
    time.sleep(2)
    origins = R.gtpu_origin()
    ok, txt = R.check_origin(scen, origins)
    return {"handle": on_, "est": est, "delay_s": delay, "origin_ok": ok, "origin": txt,
            "origins": origins, "setup_s": setup.seconds, "restarted": setup.restarted}


def gtp_background_off(state, background, warmup):
    reg = {"mode": "gtp", "level": background["level"], "capacity_mbps": background["capacity_mbps"],
           "requested_mbps": background["requested_mbps"], "on": False, "crossed_mbps": None,
           "delivered_fraction": None, "receiver_drops": None, "problems": []}
    if "failure" in state:
        reg["problems"].append(state["failure"])
        return reg
    reg.update(R.turn_off(state["handle"]))
    est = state["est"]
    reg.update(is_on=True, generator_node=est["generator_node"], receiver_node=est["background_node"],
               anchor_node=est["anchor_node"], bg_ue_ip=est["ue_ip"],
               delay_s=round(state["delay_s"], 1),
               setup_s=round(state["setup_s"] or 0, 1), ue_recreated=state["restarted"],
               gtpu_origin=state["origins"], origin=state["origin"])
    if reg["crossed_mbps"] is not None:
        reg["delivered_fraction"] = reg["crossed_mbps"] / background["requested_mbps"]
    if not state["origin_ok"]:
        reg["problems"].append(state["origin"])
    if state["delay_s"] > warmup:
        reg["problems"].append(f"the background was turned on {state['delay_s']:.0f}s after the start of "
                                f"step 12, outside the warm-up of {warmup:g}s")
    return reg


# --------------------------------------------------------------------------
# execution of the rounds
# --------------------------------------------------------------------------
def round_folder(root, n):
    return os.path.join(root, f"round-{n:02d}")


def remote_only_guard(msg):
    """Guard that only concerns the remote path: that of a measurement of the remote path
    ("b-remote: ...") and the one that compares MEC and remote within the execution. It
    removes the execution from the b-remote x b-mec comparison, not from A x B."""
    return msg.startswith(("a-remote:", "b-remote:", "loss very different between the paths"))


def load_run(scenario_folder, prof, level=0):
    """The execution recorded by one of the scripts, or None if it did not complete.

    _valid           holds for A x B: no campaign guard about the
                     MEC path and, with background, the background really applied
    _valid_remote    also holds for b-remote x b-mec: no campaign
                     guard, including those of the remote path"""
    p = os.path.join(scenario_folder, prof, "run.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        j = json.load(fh)
    ex = j.get("executions") or []
    if not ex:
        return None
    e = ex[0]
    guards = [m for sc, m in e.get("warnings", []) if sc == "campaign"]
    e["_valid"] = not [m for m in guards if not remote_only_guard(m)]
    e["_valid_remote"] = not guards
    e["_workload"] = j.get("workload")
    e["_background"] = None
    if level:
        # A level with background without proof that the background existed is not a level with background.
        f = os.path.join(scenario_folder, "background.json")
        fj = None
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                fj = json.load(fh)
        e["_background"] = fj
        if not (fj and fj.get("on")
                and (fj.get("delivered_fraction") or 0) >= MIN_BACKGROUND_DELIVERED
                and not fj.get("problems")):
            e["_valid"] = e["_valid_remote"] = False
    return e


_tests = {}


def test_module(scen):
    """The module of run_scenario_<scen>.py, loaded once."""
    if scen not in _tests:
        spec = importlib.util.spec_from_file_location(f"scenario_{scen}_test", SCRIPTS[scen])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _tests[scen] = mod
    return _tests[scen]


def tear_down(scen):
    """Tears down the scenario with the function of the script itself (by name, namespace
    untouched) -- the same teardown that the campaign without background always used."""
    test_module(scen).teardown(argparse.Namespace(teardown_timeout=300))


def run_scenario(scen, folder, args, prof, deploy=True, no_teardown=False, background=None):
    # The remote path only in B (--with-remote): a-remote enters no comparison.
    path_names = "all" if args.with_remote and scen == "b" else "mec"
    cmd = [sys.executable, "-u", SCRIPTS[scen], "--repetitions", "1",
           "--profile", prof, "--output", folder,
           "--duration", str(args.dur), "--warmup", str(args.warmup),
           "--proof-duration", str(args.proof_duration),
           "--attempts", str(args.attempts), "--timeout", str(args.timeout),
           "--path-names", path_names]
    if deploy:
        cmd.append("--deploy")
    if no_teardown:
        cmd.append("--no-teardown")
    if args.load_subscribers:
        cmd += ["--load-subscribers", str(args.load_subscribers)]
    if args.concise:
        cmd.append("--concise")
    os.makedirs(folder, exist_ok=True)
    last_ = ""
    # UTF-8 in the child and in the reading: on Windows the default is cp1252 on both sides.
    env = dict(os.environ, NO_COLOR="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    state, records = None, []
    gtp = bool(background) and args.background_source == "gtp"
    setup, deployed = None, False

    def turn_off(est):
        return gtp_background_off(est, background, args.warmup) if gtp else background_off(est, background)

    with open(os.path.join(folder, "output.log"), "w", encoding="utf-8") as log:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", cwd=BASE, env=env)
        try:
            for line in p.stdout:
                log.write(line)
                if re.match(r"^\[\d\d\]|^  (OK|WARN) |FAILED|^SCENARIO ", line):
                    print(f"    {scen.upper()} {line.rstrip()}")
                if line.strip():
                    last_ = line.strip()
                if gtp and re.search(r"scenario [AB] applied", line):
                    deployed = True
                step = re.match(r"^\[(\d\d)\]", line)
                if background and step:
                    n = step.group(1)
                    if gtp and n == "01":
                        deployed = False            # new attempt
                    if gtp and n == "07":
                        # After 06, which deletes the subscribers; in parallel
                        # with steps 08-11.
                        if setup is not None and setup.is_alive():
                            setup.join()
                        setup = BackgroundSetup(scen, deployed, args.timeout)
                    # The background follows step 12 (the measurement). Any other
                    # header turns it off -- including [01] of a new attempt.
                    if n == "12" and state is None:
                        if gtp:
                            state = gtp_background_on(scen, background, setup, max(1.0, args.warmup - 1))
                        else:
                            state = background_on(scen, background)
                        if "failure" in state:
                            print(f"    {RED}{scen.upper()} background NOT turned on: {state['failure']}{RESET}")
                        else:
                            print(f"    {GREY}{scen.upper()} background on: {background['requested_mbps']:.0f} "
                                  f"Mbps ({background['level']}% of {background['capacity_mbps']:.0f})"
                                  + (f"; {state['origin']}" if gtp else "") + RESET)
                    elif n != "12" and state is not None:
                        records.append(turn_off(state))
                        state = None
            rc = p.wait()
        except BaseException:
            p.terminate()
            raise
        finally:
            if state is not None:
                records.append(turn_off(state))
            if background:
                # The LAST stretch of background holds: it is the one of the attempt that wrote the result.
                reg = dict(records[-1]) if records else {
                    "level": background["level"], "capacity_mbps": background["capacity_mbps"],
                    "requested_mbps": background["requested_mbps"], "on": False}
                reg["times_on"] = len(records)
                if background.get("capacity_measurements"):
                    reg["capacity_measurements"] = [round(m, 1) for m in background["capacity_measurements"]]
                with open(os.path.join(folder, "background.json"), "w", encoding="utf-8") as fh:
                    json.dump(reg, fh, indent=2)
                if reg.get("delivered_fraction") is not None:
                    color = GREEN if reg["delivered_fraction"] >= MIN_BACKGROUND_DELIVERED else RED
                    print(f"    {color}{scen.upper()} background off: crossed "
                          f"{reg['crossed_mbps']:.0f} of {reg['requested_mbps']:.0f} Mbps "
                          f"in {reg['seconds_on']:.0f}s{RESET}")
                if reg.get("problems"):
                    print(f"    {RED}{scen.upper()} level invalid due to the background: "
                          f"{'; '.join(reg['problems'])}{RESET}")
    return rc, last_


# --------------------------------------------------------------------------
# check of the instrument and repetition of infrastructure failures
# --------------------------------------------------------------------------
def discard(folder, reason):
    """Moves an execution out of the way without deleting anything: <folder>.<reason>-<k>.
    The comparison only reads the folders a/ and b/, and the resume measures again."""
    k = 1
    while os.path.exists(f"{folder}.{reason}-{k}"):
        k += 1
    destination = f"{folder}.{reason}-{k}"
    for _ in range(5):
        try:
            os.rename(folder, destination)
            return destination
        except PermissionError:
            # Windows: OneDrive or an antivirus holding a file for a moment.
            time.sleep(3)
    os.rename(folder, destination)
    return destination


def infra_failure(folder, prof, level):
    """Reason to repeat the execution, or None.

    Only INFRASTRUCTURE failures: the execution did not complete (deployment, PFCP, PDU
    session) or the background was not applied (background UE without traffic, GTP-U
    through the wrong path, background turned on late). An execution that MEASURED and
    fell on a quality guard -- loss, pose, background that crossed less than 90% because
    the link was saturated -- stays as it is: repeating until it passes would select
    the good rounds and bias the comparison."""
    if load_run(folder, prof) is None:
        return "the execution did not complete"
    if level:
        fj = None
        f = os.path.join(folder, "background.json")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                fj = json.load(fh)
        if not fj or not fj.get("on"):
            return "the background did not turn on" + (f" ({'; '.join(fj['problems'])})"
                                          if fj and fj.get("problems") else "")
        if fj.get("problems"):
            return "the background was not applied properly (" + "; ".join(fj["problems"]) + ")"
    return None


def mismatched_csv(folder, prof, e):
    """Paths whose per-frame CSV is missing or is not from THIS execution: vr_client
    writes one line per complete frame, so the lines must be exactly the
    frames_complete of the summary. An old CSV left in /data of the tester also
    falls here."""
    bad = []
    for name_str, summ in sorted((e.get("campaign") or {}).items()):
        n = None
        for csvf in sorted(glob.glob(os.path.join(folder, prof, "run-*", name_str + ".csv"))):
            with open(csvf, encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in fh) - 1
        if n is None or n != summ.get("frames_complete"):
            bad.append(name_str)
    return bad


def copy_csv(scen, folder, prof):
    """Copies /data of the tester again, which is still running (--no-teardown).
    Relative destination for the same reason as the test: the "C:" of Windows."""
    runs = sorted(glob.glob(os.path.join(folder, prof, "run-*")))
    destination = runs[-1] if runs else os.path.join(folder, prof, "run-01")
    os.makedirs(destination, exist_ok=True)
    try:
        r = subprocess.run(["kubectl", "-n", NS, "cp", f"{test_module(scen).TESTER_POD}:/data", ".",
                            "-c", "vr-client"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180, cwd=destination)
    except subprocess.TimeoutExpired:
        return "timeout (180s)"
    return (r.stderr or r.stdout).strip()[:200] if r.returncode else ""


def check_instrument(scen, folder, prof, can_copy):
    """SYSTEMATIC problems of the instrument in an execution that completed ([] if
    none). In an earlier campaign, kubectl cp failed in all 898 executions and
    nobody noticed, because it was one warning among dozens."""
    e = load_run(folder, prof)
    if e is None:
        return []
    t = test_module(scen)
    problems = []
    for name_str, summ in sorted((e.get("campaign") or {}).items()):
        health = summ.get("health") or {}
        buf = health.get("sock_rcvbuf_bytes")
        if buf is not None and buf < t.RMEM_MIN:
            problems.append(
                f"{name_str}: vr_client kept {buf // 1024} kB of receive buffer "
                f"(minimum {t.RMEM_MIN // 1024} kB). net.core.rmem_max of the node of the tester "
                "went back to the default (reboot?). On the node: sudo sysctl -w "
                "net.core.rmem_max=16777216 net.core.wmem_max=16777216")
        if health.get("rx_timestamp_kernel") is False:
            problems.append(f"{name_str}: no kernel timestamp in vr_client; the latency "
                             "now includes the time the client spent off the CPU")
    bad, err = mismatched_csv(folder, prof, e), ""
    for attempt in range(1, 3 if can_copy else 1):
        if not bad:
            break
        print(f"    {YELLOW}{scen.upper()} per-frame CSV missing or from another execution "
              f"({', '.join(bad)}); copying again from the tester (attempt {attempt}){RESET}")
        err = copy_csv(scen, folder, prof)
        bad = mismatched_csv(folder, prof, e)
    if bad:
        problems.append(f"the per-frame CSV of {', '.join(bad)} did not come from the tester"
                         + (f" (kubectl cp: {err})" if err else "")
                         + ". Without it there is no frame-by-frame tail curve.")
    return problems


def run_checked(scen, folder, args, prof, nv, repeat, **kw):
    """Runs an execution and checks it. Returns (rc, last, reason): reason is the
    infrastructure failure that asks for a repetition (None if there is none). A problem
    of the instrument discards the execution and stops the campaign (InstrumentError)."""
    if os.path.isdir(folder):
        # Previous attempt (infrastructure failure, or --redo): no
        # mixing files of two executions in the same folder.
        stale = infra_failure(folder, prof, nv)
        destination = discard(folder, "failed" if stale else "redone")
        print(f"    {GREY}{scen.upper()} {level_name(nv)}: previous attempt kept in "
              f"{os.path.basename(destination)}{' (' + stale + ')' if stale else ''}{RESET}")
    t0 = time.time()
    rc, last_ = run_scenario(scen, folder, args, prof, **kw)
    color = GREEN if rc == 0 else RED
    print(f"    {color}{scen.upper()} {level_name(nv)} finished (rc={rc}) in "
          f"{time.time() - t0:.0f}s{RESET}: {last_}")
    reason = infra_failure(folder, prof, nv)
    if reason is None:
        problems = check_instrument(scen, folder, prof, can_copy=kw.get("no_teardown", False))
        if problems:
            destination = discard(folder, "instrument")
            raise InstrumentError(f"{scen.upper()} {level_name(nv)} in {folder}:\n  - "
                                  + "\n  - ".join(problems)
                                  + f"\n  The execution was kept in {os.path.basename(destination)} "
                                  "and will be measured again: fix it and run the same command.")
        # folder = <root of the level>/round-NN/<scen>
        m = re.match(r"round-(\d+)$", os.path.basename(os.path.dirname(folder)))
        if nv == 0 and m:
            baseline_alert(os.path.dirname(os.path.dirname(folder)), prof,
                                 int(m.group(1)), scen)
        return rc, last_, None
    if repeat:
        destination = discard(folder, "failed")
        print(f"    {YELLOW}{scen.upper()} {level_name(nv)}: {reason}; kept in "
              f"{os.path.basename(destination)} and repeated at the end of the round{RESET}")
        return rc, last_, reason
    print(f"    {RED}{scen.upper()} {level_name(nv)}: {reason} again; left for the "
          f"next time the command runs{RESET}")
    return rc, last_, None


def baseline_alert(root, prof, n, scen, band=0.25):
    """LIVE sentinel: the p50 without background of this round against the median of the
    previous rounds of the same scenario. An external defect (a-mec 5 to 20x slower)
    was once only seen later; here it shows up at once."""
    pname = f"{scen}-mec"
    vs = {}
    for d in glob.glob(os.path.join(root, "round-*")):
        m = re.match(r"round-(\d+)$", os.path.basename(d))
        e = load_run(os.path.join(d, scen), prof) if m else None
        v = val_(camp(e, pname), ("net_rtt_us", "p50")) if e and e["_valid"] else None
        if v is not None:
            vs[int(m.group(1))] = v / 1000
    current = vs.pop(n, None)
    if current is None or len(vs) < 3:
        return
    ref = statistics.median(vs.values())
    if abs(current / ref - 1) > band:
        print(f"    {RED}SENTINEL: {pname} without background in this round = {current:.3f} ms, against "
              f"{ref:.3f} ms of median in the previous rounds ({current / ref - 1:+.0%}). Without background "
              "this is not an effect of the LBO: check the testbed (an earlier external defect started "
              f"like this). The campaign continues.{RESET}")


def prepare_background(args, levels, legacy, profiles):
    """Prints what will be measured and starts the background generator, ONCE for
    all profiles. Returns the IP of the receiver of the direct background (None with gtp)."""
    print(f"\n  profiles, in this order: {', '.join(profiles)} ({args.rounds} rounds each)")
    print(f"  measured paths: {'a-mec, b-mec and b-remote' if args.with_remote else 'a-mec and b-mec'}"
          + ("" if legacy else "   levels: " + ", ".join(level_label(nv) for nv in levels)
             + "   background: " + ("through the GTP-U tunnel" if args.background_source == "gtp" else "direct")))
    if max(levels) >= 95:
        print(f"  {YELLOW}warning{RESET}: in Scenario A the traffic of the application itself adds to the background "
              f"on the link; at {max(levels)}%, in the heavy profiles, the load exceeds the capacity and the "
              "queue stays full all the time (high loss and few complete frames in A).")
    if legacy:
        return None
    if args.background_source == "gtp":
        start_gtp_background(args.timeout)
        return None
    return start_iperf(args.timeout)


def rounds(args, output, levels, legacy, prof, ip_srv):
    for n in range(args.first_round, args.rounds + 1):
        order = ("a", "b") if n % 2 else ("b", "a")
        k = (n - 1) % len(levels)
        level_order = levels[k:] + levels[:k]
        print(f"\n{'#' * 72}\n# {prof} -- ROUND {n} of {args.rounds}: "
              f"{order[0].upper()} -> {order[1].upper()}"
              + ("" if legacy else "   levels: " + " -> ".join(level_name(x) for x in level_order))
              + f"\n{'#' * 72}")
        cap, measures = None, None
        for scen in order:
            def folder(nv):
                return os.path.join(round_folder(level_root(output, prof, nv, legacy), n), scen)
            # Pending: never measured, or measured with an infrastructure failure (did not
            # complete, background not applied) -- including from an earlier time when the
            # command ran. The old attempt is kept, not deleted.
            pending = [nv for nv in level_order
                         if args.redo or infra_failure(folder(nv), prof, nv) is not None]
            if not pending:
                print(f"    {scen.upper()} already measured in this round; skipping")
                continue
            if legacy:
                # The usual campaign: comes up from zero, measures, tears down (hence
                # the CSV cannot be copied again afterwards).
                _, _, reason = run_checked(scen, folder(0), args, prof, 0, args.retry_failures)
                if reason:
                    run_checked(scen, folder(0), args, prof, 0, False)
                continue
            if cap is None and any(pending):
                cap, measures = round_capacity(output, prof, levels, n)
                if cap:
                    print(f"    capacity of this round, already recorded: {cap:.0f} Mbps (resume)")
                else:
                    cap, measures = measure_capacity(args, ip_srv)
                    print(f"    useful capacity core -> edge in this round: {cap:.0f} Mbps"
                          + (f" (measurements: {', '.join(f'{m:.0f}' for m in measures)})"
                             if len(measures) > 1 else ""))
            needs_deploy, ar_node = True, False
            # An infrastructure failure is repeated ONCE, at the end of the round,
            # after the other levels (the rotating order stays as planned).
            queue, repeated = list(pending), set()
            try:
                while queue:
                    nv = queue.pop(0)
                    background = None if nv == 0 else {
                        "level": nv, "capacity_mbps": cap, "capacity_measurements": measures,
                        "requested_mbps": cap * nv / 100, "ip_srv": ip_srv}
                    print(f"\n    {scen.upper()} -- {level_name(nv)}"
                          + (" (deploy)" if needs_deploy else " (same deployment)")
                          + (" (repetition)" if nv in repeated else ""))
                    repeat = args.retry_failures and nv not in repeated
                    ar_node = True
                    rc, last_, reason = run_checked(
                        scen, folder(nv), args, prof, nv, repeat,
                        deploy=needs_deploy, no_teardown=True, background=background)
                    # An execution that failed may have left the scenario broken: the
                    # next level comes up from zero instead of inheriting the state.
                    needs_deploy = rc != 0
                    if reason:
                        repeated.add(nv)
                        queue.append(nv)
            finally:
                if ar_node:
                    tear_down(scen)


# --------------------------------------------------------------------------
# comparison of one level
# --------------------------------------------------------------------------
def compare(root, prof, level=0):
    nums = sorted(int(m.group(1)) for d in os.listdir(root)
                  if (m := re.match(r"round-(\d+)$", d)))
    lines = []
    for n in nums:
        pr = round_folder(root, n)
        a = load_run(os.path.join(pr, "a"), prof, level)
        b = load_run(os.path.join(pr, "b"), prof, level)
        lines.append({"round": n, "order": "A>B" if n % 2 else "B>A", "a": a, "b": b,
                       "pair_valid": bool(a and b and a["_valid"] and b["_valid"])})
    if not lines:
        return None

    primary, secondary = [], []
    for key_name, rot, pname, div, un, decimals, smallest in KPIS:
        pairs = [r for r in lines if r["pair_valid"]]
        av = [val_(camp(r["a"], "a-mec"), pname) for r in pairs]
        bv = [val_(camp(r["b"], "b-mec"), pname) for r in pairs]
        diffs = [(x - y) / div for x, y in zip(av, bv) if x is not None and y is not None]
        pcts = [(1 - y / x) * 100 for x, y in zip(av, bv) if x and y is not None]
        ma, da = mean_sd([x / div for x in av if x is not None])
        mb, db = mean_sd([y / div for y in bv if y is not None])
        primary.append({"kpi": key_name, "run_label": rot, "unit": un, "decimals": decimals,
                          "a": (ma, da), "b": (mb, db), "diff": paired(diffs),
                          "pct": (sum(pcts) / len(pcts)) if pcts and smallest else None,
                          # The median resists a bimodal round (at 95% a queue
                          # that saturates in some rounds and not in others).
                          "median": statistics.median(diffs) if diffs else None,
                          "b_better": sum(1 for d in diffs if d > 0) if smallest else None})

        bs = [r for r in lines if r["b"] and r["b"]["_valid_remote"]]
        mec = [val_(camp(r["b"], "b-mec"), pname) for r in bs]
        rem = [val_(camp(r["b"], "b-remote"), pname) for r in bs]
        diffs2 = [(y - x) / div for x, y in zip(mec, rem) if x is not None and y is not None]
        pcts2 = [(y / x - 1) * 100 for x, y in zip(mec, rem) if x and y is not None]
        mm, dm = mean_sd([x / div for x in mec if x is not None])
        mr, dr = mean_sd([y / div for y in rem if y is not None])
        secondary.append({"kpi": key_name, "run_label": rot, "unit": un, "decimals": decimals,
                           "mec": (mm, dm), "remote": (mr, dr), "diff": paired(diffs2),
                           "pct": (sum(pcts2) / len(pcts2)) if pcts2 and smallest else None})
    return {"lines": lines, "primary": primary, "secondary": secondary}


def has_remote(res):
    """There is a secondary comparison only if b-remote was measured."""
    return any(camp(r["b"], "b-remote") for r in res["lines"])


def n_secondary(res):
    return sum(1 for r in res["lines"]
               if r["b"] and r["b"]["_valid_remote"] and camp(r["b"], "b-remote"))


NO_SECONDARY = ("No execution of B passed the guard of loss between paths at this "
                  "level. Under congestion b-remote crosses the link and loses packets, b-mec does not; with "
                  "such different losses only the complete frames become samples, and the "
                  "comparison between the two no longer holds. A x B above is not affected.")


def camp(e, path_name):
    return (e or {}).get("campaign", {}).get(path_name, {})


def cell_k(md, decimals):
    m, d = md
    return "-" if m is None else (f"{m:.{decimals}f}" if d is None else f"{m:.{decimals}f} ± {d:.{decimals}f}")


def cell_diff(k):
    d = k["diff"]
    if not d:
        return "-", "-"
    c = k["decimals"]
    base = f"{d['mean']:+.{c}f}" + ("" if d["std"] is None else f" ± {d['std']:.{c}f}")
    ic = "-" if not d["ci"] else f"[{d['ci'][0]:+.{c}f}; {d['ci'][1]:+.{c}f}]"
    return base, ic


def cell_med(k):
    return "-" if k.get("median") is None else f"{k['median']:+.{k['decimals']}f}"


def cell_below(k):
    return "-" if not k["diff"] or k["b_better"] is None else f"{k['b_better']}/{k['diff']['n']}"


DROP_LABEL = {"failed": "infrastructure failure", "instrument": "instrument failure",
                   "redone": "--redo"}


def discarded(root):
    """Executions moved out of the way by this campaign, by reason."""
    c = {}
    for d in glob.glob(os.path.join(root, "round-*", "*.*-*")):
        m = re.match(r"[ab]\.(\w+)-\d+$", os.path.basename(d))
        if m and os.path.isdir(d):
            c[m.group(1)] = c.get(m.group(1), 0) + 1
    return c


def baseline(res, band=0.25):
    """Rounds in which the p50 without background moved more than `band` away from the median
    of the scenario itself. It is the sentinel of an external defect, as when a-mec
    once became 5 to 20x slower without anything of ours having changed."""
    out = []
    for scen, pname in (("a", "a-mec"), ("b", "b-mec")):
        vs = [(r["round"], val_(camp(r[scen], pname), ("net_rtt_us", "p50")))
              for r in res["lines"] if r[scen] and r[scen]["_valid"]]
        vs = [(n, v / 1000) for n, v in vs if v is not None]
        if len(vs) < 3:
            continue
        m = statistics.median(v for _, v in vs)
        outside = [(n, v) for n, v in vs if abs(v / m - 1) > band]
        out.append((pname, m, outside))
    return out


def proof(e, upf):
    try:
        return e["proof"]["mec"]["delta"][upf]["rx_pkts"]
    except (KeyError, TypeError):
        return None


def background_crossed(e):
    f = (e or {}).get("_background") or {}
    return f.get("crossed_mbps")


def legacy_args(args, level):
    return level == 0 and getattr(args, "_legacy", True)


def emit(root, prof, res, args, level=0):
    lines = res["lines"]
    n_pairs = sum(1 for r in lines if r["pair_valid"])
    workload = next((r[c]["_workload"] for r in lines for c in ("a", "b") if r[c] and r[c].get("_workload")), None)
    caps = [e["_background"]["capacity_mbps"] for r in lines for e in (r["a"], r["b"])
            if e and e.get("_background") and e["_background"].get("capacity_mbps")]

    remote_only = sum(1 for r in lines for e in (r["a"], r["b"])
                    if e and e["_valid"] and not e["_valid_remote"])
    with open(os.path.join(root, "a-vs-b.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# A x B campaign - profile `{prof}`"
                 + ("" if not level else f" - backhaul with background at {level}%") + "\n\n")
        if workload:
            fh.write(f"**Load:** {workload['bitrate_mbps']} Mbps @ {workload['fps']} fps (downlink), "
                     f"pose at {workload['pose_hz']} Hz (uplink), MTU {workload['mtu']} B.\n\n")
        if level:
            mode_ = background_mode([e["_background"] for r in lines for e in (r["a"], r["b"])
                               if e and e.get("_background")])
            fh.write(f"**Background on the backhaul:** {BACKGROUND_ORIGIN[mode_]}, at {level}% of the capacity "
                     "measured at the start of each round"
                     + (f" (mean {sum(caps) / len(caps):.0f} Mbps)" if caps else "")
                     + ". On only during the measurement; an execution in which less than "
                     f"{MIN_BACKGROUND_DELIVERED * 100:.0f}% of the background crossed the link does not hold.\n\n")
            if workload and caps:
                ef = level + workload["bitrate_mbps"] / (sum(caps) / len(caps)) * 100
                fh.write(f"**Effective load in A:** in the centralized case the downlink of the application itself "
                         f"({workload['bitrate_mbps']} Mbps) goes down the same link as the background, "
                         f"so the load of the link during the measurement of a-mec is ~{ef:.1f}% of the "
                         "capacity"
                         + (". **Above 100%: in A this is overload, not only congestion** -- the "
                            "queue stays full all the time, the delay locks at the ceiling of the buffer and the "
                            "excess becomes loss." if ef >= 100 else ".")
                         + " In B, b-mec does not cross the link.\n\n")
        deploy = ("Each scenario comes up from zero and is torn down at the end." if legacy_args(args, level)
                  else "Each scenario comes up once per round and goes through all background levels, "
                       "in an order that rotates between rounds.")
        fh.write(f"{len(lines)} round(s), alternating order (A->B, B->A, ...). {deploy} "
                 f"**Valid pairs: {n_pairs} of {len(lines)}** -- a pair only enters if both "
                 "executions passed the health guards of the MEC path."
                 + (f" {remote_only} execution(s) triggered only guards of the remote path: they hold "
                    "for A x B and stay out of the b-remote x b-mec comparison." if remote_only else "")
                 + "\n\n")
        desc = discarded(root)
        if desc:
            fh.write("**Executions redone:** "
                     + ", ".join(f"{n} due to {DROP_LABEL.get(m, m)}" for m, n in sorted(desc.items()))
                     + " (folders `round-NN/<a|b>.<reason>-<k>`, kept for diagnosis). "
                     "Only what did not measure is redone; a measurement that fell on a quality guard "
                     "is never redone.\n\n")
        if not level:
            base = baseline(res)
            if base:
                fh.write("**Baseline (sentinel):** p50 without background, median across rounds -- "
                         + "; ".join(f"{pname} {m:.3f} ms" + (
                             f", OUTSIDE +-25% in rounds {', '.join(f'{n} ({v:.3f})' for n, v in outside)}"
                             if outside else ", all rounds within +-25%")
                                     for pname, m, outside in base)
                         + ". A round outside the band without background points to a defect of the testbed "
                         "(as observed once), not an effect of the LBO: investigate before using it.\n\n")

        fh.write("## LBO against the centralized UPF (a-mec x b-mec)\n\n")
        fh.write("Same UE, same destination (mec-app at the edge), same load: only the anchor "
                 "of the user plane changes. Difference = A - B, computed within each "
                 "round; **positive = the LBO is faster**. Values: mean ± "
                 "standard deviation across rounds.\n\n")
        fh.write("| KPI | A: centralized UPF | B: dUPF with LBO | A - B (paired) | 95% CI | "
                 "A - B (median) | LBO lower | B lower |\n")
        fh.write("|---|---|---|---|---|---|---|---|\n")
        for k in res["primary"]:
            diff, ic = cell_diff(k)
            pct = "-" if k["pct"] is None else f"{k['pct']:.1f}%"
            fh.write(f"| {k['run_label']} ({k['unit']}) | {cell_k(k['a'], k['decimals'])} | "
                     f"{cell_k(k['b'], k['decimals'])} | {diff} | {ic} | {cell_med(k)} | {pct} | "
                     f"{cell_below(k)} |\n")
        p50 = next(k for k in res["primary"] if k["kpi"] == "net_p50")["diff"]
        if p50 and p50["mde"] is not None:
            fh.write(f"\nMinimum detectable difference in the network delay p50 with {p50['n']} pair(s) "
                     f"(alpha 5%, power 80%): **{p50['mde']:.3f} ms**. Smaller differences "
                     "cannot be claimed with this campaign.\n\n")

        if has_remote(res) and not n_secondary(res):
            fh.write("## Application outside in Scenario B (b-remote x b-mec)\n\n" + NO_SECONDARY + "\n\n")
        elif has_remote(res):
            fh.write("## Application outside in Scenario B (b-remote x b-mec)\n\n")
            fh.write("How much longer it takes when the application is in the core, crossing the "
                     "2 UPFs of Scenario B. Difference = remote - MEC, within each execution of B "
                     f"({n_secondary(res)} execution(s) without any guard, not even those of the remote path).\n\n")
            fh.write("| KPI | B: MEC (LBO) | B: remote (2 UPFs) | remote - MEC | 95% CI | extra outside |\n")
            fh.write("|---|---|---|---|---|---|\n")
            for k in res["secondary"]:
                diff, ic = cell_diff(k)
                pct = "-" if k["pct"] is None else f"{k['pct']:.1f}%"
                fh.write(f"| {k['run_label']} ({k['unit']}) | {cell_k(k['mec'], k['decimals'])} | "
                         f"{cell_k(k['remote'], k['decimals'])} | {diff} | {ic} | {pct} |\n")

        fh.write("\n## Proof of the mechanism in each round\n\n")
        fh.write("Packets that the anchor UPF saw under MEC traffic. In A the central UPF "
                 "must count the traffic (trombone); in B the PSA-UPF must stay at zero "
                 "(breakout at the edge).\n\n")
        extra = " A: background crossed (Mbps) | B: background crossed (Mbps) |" if level else ""
        fh.write("| Round | Order | A: central UPF under MEC | B: PSA-UPF under MEC | A valid | B valid | Pair |"
                 + extra + "\n")
        fh.write("|---|---|---|---|---|---|---|" + ("---|---|" if level else "") + "\n")
        for r in lines:
            fh.write(f"| {r['round']} | {r['order']} | {proof(r['a'], 'upf') if r['a'] else 'failed'} | "
                     f"{proof(r['b'], 'psa-upf') if r['b'] else 'failed'} | "
                     f"{'-' if not r['a'] else ('yes' if r['a']['_valid'] else 'no')} | "
                     f"{'-' if not r['b'] else ('yes' if r['b']['_valid'] else 'no')} | "
                     f"{'yes' if r['pair_valid'] else 'no'} |"
                     + (f" {fmt(background_crossed(r['a']), 0)} | {fmt(background_crossed(r['b']), 0)} |"
                        if level else "") + "\n")

    # Only the paths that were measured: the campaign no longer measures a-remote.
    path_names = tuple((scen, pname) for scen, pname in (("a", "a-mec"), ("a", "a-remote"),
                                                 ("b", "b-mec"), ("b", "b-remote"))
                     if pname.endswith("mec") or any(camp(r[scen], pname) for r in lines))
    with open(os.path.join(root, "a-vs-b-per-round.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["round", "order", "a_valid", "b_valid", "pair_valid",
                    "a_upf_rx_under_mec", "b_psa_rx_under_mec"]
                   + [f"{pname}_{k[0]}" for _, pname in path_names for k in KPIS]
                   + ["background_level_pct", "a_background_crossed_mbps", "b_background_crossed_mbps"])
        for r in lines:
            row = [r["round"], r["order"],
                   "" if not r["a"] else int(r["a"]["_valid"]),
                   "" if not r["b"] else int(r["b"]["_valid"]), int(r["pair_valid"]),
                   proof(r["a"], "upf") if r["a"] else "", proof(r["b"], "psa-upf") if r["b"] else ""]
            for scen, pname in path_names:
                summ = (r[scen] or {}).get("campaign", {}).get(pname, {})
                row += ["" if val_(summ, k[2]) is None else val_(summ, k[2]) for k in KPIS]
            row += [level, "" if background_crossed(r["a"]) is None else round(background_crossed(r["a"]), 1),
                    "" if background_crossed(r["b"]) is None else round(background_crossed(r["b"]), 1)]
            w.writerow(row)

    with open(os.path.join(root, "a-vs-b.json"), "w", encoding="utf-8") as fh:
        json.dump({"profile": prof, "background_level_pct": level, "rounds": len(lines),
                   "valid_pairs": n_pairs,
                   "primary": res["primary"], "secondary": res["secondary"],
                   "per_round": [{"round": r["round"], "order": r["order"],
                                   "a_valid": bool(r["a"] and r["a"]["_valid"]),
                                   "b_valid": bool(r["b"] and r["b"]["_valid"]),
                                   "b_valid_remote": bool(r["b"] and r["b"]["_valid_remote"]),
                                   "pair_valid": r["pair_valid"],
                                   "a_background": (r["a"] or {}).get("_background"),
                                   "b_background": (r["b"] or {}).get("_background")} for r in lines]},
                  fh, indent=2)
    return n_pairs


def show(res, n_pairs):
    print(f"\n{'=' * 72}\nLBO against the centralized UPF (a-mec x b-mec) -- {n_pairs} valid pair(s)\n{'=' * 72}")
    print(f"  {'KPI':<26}{'A: centralized':>18}{'B: LBO':>18}{'A - B':>14}{'CI 95%':>22}")
    for k in res["primary"]:
        diff, ic = cell_diff(k)
        print(f"  {k['run_label'] + ' (' + k['unit'] + ')':<26}{fmt(k['a'][0], k['decimals']):>18}"
              f"{fmt(k['b'][0], k['decimals']):>18}{diff.split(' ')[0]:>14}{ic:>22}")
    if not has_remote(res):
        return
    print(f"\n{'=' * 72}\nApplication outside in Scenario B (b-remote x b-mec)\n{'=' * 72}")
    if not n_secondary(res):
        print("  " + NO_SECONDARY)
        return
    print(f"  {'KPI':<26}{'B: MEC':>18}{'B: remote':>18}{'remote - MEC':>14}{'95% CI':>22}")
    for k in res["secondary"]:
        diff, ic = cell_diff(k)
        print(f"  {k['run_label'] + ' (' + k['unit'] + ')':<26}{fmt(k['mec'][0], k['decimals']):>18}"
              f"{fmt(k['remote'][0], k['decimals']):>18}{diff.split(' ')[0]:>14}{ic:>22}")


# --------------------------------------------------------------------------
# the highlight: LBO under congestion, across the levels
# --------------------------------------------------------------------------
def kpi_def(key_name):
    return next(k for k in KPIS if k[0] == key_name)


def compare_levels(per_level, levels):
    """Joins the levels round by round.

    gain       A - B at each level (the same number as the a-vs-b.md of that level,
               plus in how many rounds B was lower)
    cost       how much each scenario worsened from no background to the level, WITHIN
               the same round and the same deployment
    spared     (worsening of A) - (worsening of B) in the same round: how much of the
               congestion the centralized case absorbs and the LBO does not. It is the
               statistic that answers "does the LBO isolate the application from the backhaul?"."""
    gain, cost = [], []
    for nv in levels:
        res = per_level.get(nv)
        if not res:
            continue
        for k in res["primary"]:
            if k["kpi"] in KPIS_HIGHLIGHT:
                gain.append({"level": nv, **k})
    base = per_level.get(0)
    if base:
        per_round0 = {r["round"]: r for r in base["lines"]}
        for nv in levels:
            if nv == 0 or nv not in per_level:
                continue
            for key_name in KPIS_HIGHLIGHT:
                _, rot, pname, div, un, decimals, _ = kpi_def(key_name)
                worsening = {"a": [], "b": []}
                spared = []
                for r in per_level[nv]["lines"]:
                    r0 = per_round0.get(r["round"])
                    if not r0:
                        continue
                    d = {}
                    for scen, path_name in (("a", "a-mec"), ("b", "b-mec")):
                        e, e0 = r[scen], r0[scen]
                        if e and e0 and e["_valid"] and e0["_valid"]:
                            x, x0 = val_(camp(e, path_name), pname), val_(camp(e0, path_name), pname)
                            if x is not None and x0 is not None:
                                d[scen] = (x - x0) / div
                                worsening[scen].append(d[scen])
                    if "a" in d and "b" in d:
                        spared.append(d["a"] - d["b"])
                cost.append({"level": nv, "kpi": key_name, "run_label": rot, "unit": un,
                              "decimals": decimals, "worsening_a": paired(worsening["a"]),
                              "worsening_b": paired(worsening["b"]), "spared": paired(spared)})
    return {"gain": gain, "cost": cost}


def cell_p(d, decimals, with_ci=False):
    if not d:
        return "-"
    s = f"{d['mean']:+.{decimals}f}" + ("" if d["std"] is None else f" ± {d['std']:.{decimals}f}")
    if with_ci and d["ci"]:
        s += f" [{d['ci'][0]:+.{decimals}f}; {d['ci'][1]:+.{decimals}f}]"
    return s


def emit_highlight(output, prof, per_level, levels, dest):
    name_str = f"lbo-under-congestion-{prof}"
    all_items = [r for nv in levels if per_level.get(nv) for r in per_level[nv]["lines"]]
    workload = next((e["_workload"] for r in all_items for e in (r["a"], r["b"]) if e and e.get("_workload")), None)
    backgrounds = [e["_background"] for r in all_items for e in (r["a"], r["b"]) if e and e.get("_background")]
    caps = [f["capacity_mbps"] for f in backgrounds if f.get("capacity_mbps")]
    n_rounds = sorted({r["round"] for r in all_items})
    mode_ = background_mode(backgrounds)

    with open(os.path.join(output, name_str + ".md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Local breakout under backhaul congestion - profile `{prof}`\n\n")
        fh.write("**The question.** In the centralized scenario (A), the traffic of the MEC application leaves "
                 "the edge, goes to the UPF in the core and comes back: it crosses the core -> edge link "
                 "**twice**. With local breakout (B), it leaves at the edge itself and crosses it "
                 "**none**. What happens to each one when this link "
                 "is congested?\n\n")
        fh.write(f"**How it was measured.** {len(n_rounds)} round(s), alternating A/B order. In each "
                 "round both scenarios go through the same levels of background traffic: "
                 + BACKGROUND_ORIGIN[mode_] + ", a "
                 + " and ".join(", ".join(f"{nv}%" for nv in levels if nv).rsplit(", ", 1))
                 + " of the capacity measured at the start of the round"
                 + (f" (mean {sum(caps) / len(caps):.0f} Mbps)" if caps else "") + ". "
                 "Differences computed within the round before aggregating.")
        if workload:
            fh.write(f" Load of the application: {workload['bitrate_mbps']} Mbps @ {workload['fps']} fps "
                     f"in the downlink, pose at {workload['pose_hz']} Hz.")
        fh.write("\n\n")

        fh.write("## 1. The gain of the LBO at each congestion level (a-mec x b-mec)\n\n")
        fh.write("A - B paired within the round: **positive = the LBO is faster**. "
                 "\"B lower\" counts in how many rounds B was below A. Values: mean ± "
                 "standard deviation across rounds.\n\n")
        fh.write("| Backhaul | KPI | A: centralized | B: LBO | A - B (paired) | CI 95% | "
                 "A - B (median) | LBO lower | B lower |\n")
        fh.write("|---|---|---|---|---|---|---|---|---|\n")
        for nv in levels:
            level_lines = [g for g in dest["gain"] if g["level"] == nv]
            for i, g in enumerate(level_lines):
                diff, ic = cell_diff(g)
                pct = "-" if g["pct"] is None else f"{g['pct']:.1f}%"
                ab = "-" if not g["diff"] or g["b_better"] is None else f"{g['b_better']}/{g['diff']['n']}"
                fh.write(f"| {'**' + level_label(nv) + '**' if i == 0 else ''} | "
                         f"{g['run_label']} ({g['unit']}) | {cell_k(g['a'], g['decimals'])} | "
                         f"{cell_k(g['b'], g['decimals'])} | {diff} | {ic} | {cell_med(g)} | {pct} | {ab} |\n")

        if dest["cost"]:
            fh.write("\n## 2. How much the congestion costs each scenario\n\n")
            fh.write("Difference against the level without background, within the SAME round and the SAME "
                     "deployment (mean ± standard deviation). The last column is what the LBO spares: "
                     "how much the centralized case worsens **more** than the LBO, with 95% CI. If the "
                     "interval does not cross zero, the difference can be claimed with this campaign.\n\n")
            fh.write("| Backhaul | KPI | A worsens | B worsens | A worsens more than B [95% CI] |\n")
            fh.write("|---|---|---|---|---|\n")
            for nv in levels:
                level_lines = [c for c in dest["cost"] if c["level"] == nv]
                for i, c in enumerate(level_lines):
                    fh.write(f"| {'**' + level_label(nv) + '**' if i == 0 else ''} | "
                             f"{c['run_label']} ({c['unit']}) | {cell_p(c['worsening_a'], c['decimals'])} | "
                             f"{cell_p(c['worsening_b'], c['decimals'])} | "
                             f"{cell_p(c['spared'], c['decimals'], with_ci=True)} |\n")

        fh.write("\n## 3. Validity per level\n\n")
        fh.write("| Backhaul | Rounds | Valid pairs | Requested background (Mbps) | Background that crossed the link (Mbps) |\n")
        fh.write("|---|---|---|---|---|\n")
        for nv in levels:
            res = per_level.get(nv)
            if not res:
                continue
            fs = [e["_background"] for r in res["lines"] for e in (r["a"], r["b"]) if e and e.get("_background")]
            req = mean_sd([f.get("requested_mbps") for f in fs])
            raw_text = mean_sd([f.get("crossed_mbps") for f in fs])
            fh.write(f"| {level_label(nv)} | {len(res['lines'])} | "
                     f"{sum(1 for r in res['lines'] if r['pair_valid'])} | "
                     f"{cell_k(req, 0) if nv else '-'} | {cell_k(raw_text, 0) if nv else '-'} |\n")
        fh.write("\nComplete tables (all KPIs and proof of the mechanism per round) in `" + "`, `".join(f"{level_name(nv)}/{prof}/a-vs-b.md" for nv in levels)
                 + "`.\n\n")

        fh.write("## Limitations to declare\n\n")
        fh.write("- The background is fixed-rate UDP. Real traffic is mostly TCP/QUIC, which "
                 "backs off under loss; the levels stay below 100% so as not to turn congestion "
                 "into continuous overload.\n")
        fh.write("- The transport of the testbed has no QoS: in an operator network, low-latency traffic "
                 "and the control plane would use priority queues, which would reduce the damage to "
                 "the centralized UPF.\n")
        fh.write("- The backhaul of the testbed has ~20 us of propagation; in a regional core the "
                 "distance adds a few ms that do not appear here and that also weigh against the "
                 "centralized UPF.\n")
        if mode_ == "gtp":
            fh.write("- The background is subscriber traffic and goes through the anchor UPF. In A it is "
                     "the SAME central UPF as the experiment, so the worsening of A adds congestion of the "
                     "backhaul and load on the shared UPF -- as in a real core. The background "
                     "UE belongs to another slice (1/112233), without LBO, in a second cell.\n")
            fh.write("- UERANSIM does not absorb the background rate (50-100 Mbps per session): the "
                     "excess is dropped in the background pod AFTER crossing the link. The "
                     "link sees the whole load; the background UE receives a fraction of it.\n")
        else:
            fh.write("- The background does not go through the UPFs: it measures the congestion of the transport, not the load of "
                     "other users on the user plane.\n")
        fh.write("- The link belongs to the university network; third-party traffic enters as noise, "
                 "which the pairing by round and the alternating order help to cancel.\n")

    with open(os.path.join(output, name_str + ".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["round", "background_level_pct", "a_valid", "b_valid", "pair_valid",
                    "capacity_mbps", "a_background_crossed_mbps", "b_background_crossed_mbps"]
                   + [f"{pname}_{k}" for pname in ("a-mec", "b-mec") for k in KPIS_HIGHLIGHT])
        for nv in levels:
            for r in (per_level.get(nv) or {}).get("lines", []):
                fa, fb = (r["a"] or {}).get("_background") or {}, (r["b"] or {}).get("_background") or {}
                row = [r["round"], nv, "" if not r["a"] else int(r["a"]["_valid"]),
                       "" if not r["b"] else int(r["b"]["_valid"]), int(r["pair_valid"]),
                       fa.get("capacity_mbps") or fb.get("capacity_mbps") or "",
                       fa.get("crossed_mbps") or "", fb.get("crossed_mbps") or ""]
                for scen, pname in (("a", "a-mec"), ("b", "b-mec")):
                    for key_name in KPIS_HIGHLIGHT:
                        v = val_(camp(r[scen], pname), kpi_def(key_name)[2])
                        row.append("" if v is None else v)
                w.writerow(row)

    with open(os.path.join(output, name_str + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"profile": prof, "background_levels_pct": levels, "rounds": n_rounds,
                   "gain": dest["gain"], "cost": dest["cost"]}, fh, indent=2)
    return name_str


def show_highlight(levels, dest):
    print(f"\n{'=' * 72}\nLOCAL BREAKOUT UNDER BACKHAUL CONGESTION (a-mec x b-mec)\n{'=' * 72}")
    print(f"  {'backhaul':<10}{'KPI':<24}{'A: central':>12}{'B: LBO':>12}{'A - B':>10}"
          f"{'CI 95%':>22}{'B lower':>10}")
    for nv in levels:
        for i, g in enumerate(x for x in dest["gain"] if x["level"] == nv):
            diff, ic = cell_diff(g)
            ab = "-" if not g["diff"] or g["b_better"] is None else f"{g['b_better']}/{g['diff']['n']}"
            print(f"  {level_label(nv) if i == 0 else '':<10}{g['run_label'] + ' (' + g['unit'] + ')':<24}"
                  f"{fmt(g['a'][0], g['decimals']):>12}{fmt(g['b'][0], g['decimals']):>12}"
                  f"{diff.split(' ')[0]:>10}{ic:>22}{ab:>10}")
    if dest["cost"]:
        print("\n  how much the congestion costs (against no background, in the same round)")
        print(f"  {'backhaul':<10}{'KPI':<24}{'A worsening':>12}{'B worsening':>12}"
              f"   A worsens more than B [95% CI]")
        for c in dest["cost"]:
            pa, pb = c["worsening_a"], c["worsening_b"]
            print(f"  {level_label(c['level']):<10}{c['run_label'] + ' (' + c['unit'] + ')':<24}"
                  f"{fmt(pa['mean'] if pa else None, c['decimals']):>12}"
                  f"{fmt(pb['mean'] if pb else None, c['decimals']):>12}"
                  f"   {cell_p(c['spared'], c['decimals'], with_ci=True)}")


# --------------------------------------------------------------------------
def levels_in(folder):
    """Levels recorded in the root of a campaign with background (no-background, background-80...)."""
    findings = []
    for d in os.listdir(folder):
        if d == "no-background":
            findings.append(0)
        elif (m := re.match(r"background-(\d+)$", d)):
            findings.append(int(m.group(1)))
    return sorted(findings)


# --------------------------------------------------------------------------
# record of the campaign (reproducibility)
# --------------------------------------------------------------------------
class Tee:
    """Copies everything the campaign prints to a file, without the colors."""

    def __init__(self, flow, fh):
        self.flow, self.fh = flow, fh

    def write(self, s):
        self.flow.write(s)
        if not self.fh.closed:
            self.fh.write(re.sub(r"\x1b\[[0-9;]*m", "", s))
        return len(s)

    def flush(self):
        self.flow.flush()
        if not self.fh.closed:
            self.fh.flush()

    def __getattr__(self, name_str):
        return getattr(self.flow, name_str)


def output_of(cmd, cwd=None, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_version():
    commit = output_of(["git", "rev-parse", "HEAD"], cwd=BASE)
    if not commit:
        return None
    changed = output_of(["git", "status", "--porcelain", "--", "."], cwd=BASE) or ""
    return {"commit": commit, "changed": [l[3:] for l in changed.splitlines()][:50]}


def kubectl_version():
    try:
        j = json.loads(output_of(["kubectl", "version", "-o", "json"]) or "")
    except ValueError:
        return None
    return {k: (j.get(k) or {}).get("gitVersion") for k in ("clientVersion", "serverVersion")}


def open_record(output, args, profiles, levels):
    """campaign-<start>.json and campaign-<start>.log at the root of the campaign. Each
    time the command runs (resumes included) it creates a new pair."""
    base = os.path.join(output, f"campaign-{time.strftime('%Y%m%d-%H%M%S')}")
    reg = {"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "end": None,
           "command": [os.path.basename(sys.argv[0])] + sys.argv[1:],
           "args": {k: v for k, v in vars(args).items() if not k.startswith("_")},
           "profiles": profiles, "background_levels_pct": levels,
           "python": sys.version.split()[0], "platform": platform.platform(),
           "git": git_version(), "kubectl": kubectl_version(), "result": None}
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2)
    log = open(base + ".log", "w", encoding="utf-8", buffering=1)
    sys.stdout, sys.stderr = Tee(sys.stdout, log), Tee(sys.stderr, log)
    print(f"  record of this command: {os.path.basename(base)}.json and .log")
    return base, reg, log


def close_record(base, reg, log, outcome):
    reg.update(end_t=time.strftime("%Y-%m-%dT%H:%M:%S%z"), outcome=outcome)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2)
    for name_str in ("stdout", "stderr"):
        flow = getattr(sys, name_str)
        flow.flush()
        if isinstance(flow, Tee):
            setattr(sys, name_str, flow.flow)
    log.close()


def keep_awake():
    """A campaign of days with nobody watching: the computer must not sleep in the
    middle. Holds only while this process exists."""
    if os.name == "nt":
        try:
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except (AttributeError, OSError):
            pass
    elif shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def report(args, output, prof, levels, legacy, t0):
    """Compares and writes the reports of ONE profile. Returns the exit code."""
    per_level, pairs, totals = {}, {}, {}
    for nv in levels:
        root = level_root(output, prof, nv, legacy)
        res = compare(root, prof, nv) if os.path.isdir(root) else None
        if not res:
            continue
        per_level[nv] = res
        pairs[nv] = emit(root, prof, res, args, nv)
        totals[nv] = len(res["lines"])
    if not per_level:
        print(f"\n{RED}A x B CAMPAIGN NOT COMPLETED{RESET} ({prof}) -- no round in {output}")
        return 1

    if legacy:
        show(per_level[0], pairs[0])
        print(f"\n  Files in {level_root(output, prof, 0, True)}: a-vs-b.md, "
              "a-vs-b-per-round.csv, a-vs-b.json")
    else:
        dest = compare_levels(per_level, levels)
        name_str = emit_highlight(output, prof, per_level, levels, dest)
        show_highlight(levels, dest)
        print(f"\n  Highlight in {output}: {name_str}.md, .csv, .json")
        print("  Complete tables per level: "
              + ", ".join(f"{level_name(nv)}/{prof}/a-vs-b.md" for nv in per_level))

    elapsed = f"{time.time() - t0:.0f}s"
    if legacy:
        n_pairs, total = pairs[0], totals[0]
        if n_pairs == 0:
            print(f"\n{RED}A x B CAMPAIGN WITHOUT A VALID PAIR{RESET} ({prof}) -- {total} round(s), "
                  f"none with valid A and B ({elapsed})")
            return 1
        if n_pairs < total:
            print(f"\n{YELLOW}A x B CAMPAIGN WITH FAILURES{RESET} ({prof}) -- {n_pairs} of {total} "
                  f"round(s) with a valid pair ({elapsed})")
            return 1
        print(f"\n{GREEN}A x B CAMPAIGN COMPLETED{RESET} ({prof}) -- {n_pairs} valid pair(s) ({elapsed})")
        return 0
    summ = ", ".join(f"{level_label(nv)} {pairs[nv]}/{totals[nv]}" for nv in per_level)
    if not any(pairs.values()):
        print(f"\n{RED}A x B CAMPAIGN WITHOUT A VALID PAIR{RESET} ({prof}) -- valid pairs: {summ} ({elapsed})")
        return 1
    lacking = [nv for nv in levels if nv not in per_level]
    if any(pairs[nv] < totals[nv] for nv in per_level) or lacking:
        print(f"\n{YELLOW}A x B CAMPAIGN WITH FAILURES{RESET} ({prof}) -- valid pairs: {summ}"
              + (f"; no result: {', '.join(level_label(nv) for nv in lacking)}" if lacking else "")
              + f" ({elapsed})")
        return 1
    print(f"\n{GREEN}A x B CAMPAIGN COMPLETED{RESET} ({prof}) -- valid pairs: {summ} ({elapsed})")
    return 0


def main():
    global R
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=5, metavar="N",
                    help="how many A+B rounds per profile (default: 5)")
    ap.add_argument("--profile", default=None, metavar="PROFILES",
                    help="load profile, the same name accepted by both scripts, or a list "
                         "separated by commas, running one whole profile at a time, in the order "
                         "given (e.g. vr-cloud,vr-extreme,teleoperation). Default: vr-cloud; with "
                         "--compare-only, all profiles of the folder")
    ap.add_argument("--background", default="0,80,95", metavar="PCTS",
                    help="background traffic levels on the backhaul, in %% of the measured capacity, "
                         "from 0 to 99 (default: 0,80,95). E.g. --background 0,99 only no background and 99%%; "
                         "--background 0 is the campaign without congestion")
    ap.add_argument("--background-source", choices=("gtp", "direct"), default="gtp",
                    help="where the background comes from: gtp (default) through the GTP-U tunnel to the background "
                         "UERANSIM on brix-porvir-03 (background/background-gtp.yaml); direct: "
                         "iperf3 to brix-porvir-04 without going through a UPF (earlier campaign)")
    ap.add_argument("--with-remote", action="store_true",
                    help="also measures b-remote (default: only a-mec and b-mec). a-remote is not "
                         "measured by the campaign")
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--warmup", type=float, default=5)
    ap.add_argument("--proof-duration", type=float, default=10)
    ap.add_argument("--capacity-duration", type=int, default=10, metavar="S",
                    help="seconds of the iperf3 TCP that measures the capacity at each round")
    ap.add_argument("--load-subscribers", type=int, default=0, metavar="N")
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--concise", action="store_true")
    ap.add_argument("--first-round", type=int, default=1, metavar="N",
                    help="starts at round N instead of 1, in all profiles (default: 1); the "
                         "earlier rounds are not touched, but still enter the comparison")
    ap.add_argument("--redo", action="store_true",
                    help="measures again even what already has a result")
    ap.add_argument("--no-retry", dest="retry_failures", action="store_false",
                    help="does not redo the execution that did not complete or in which the background was not "
                         "applied (default: redoes it once, at the end of the round)")
    ap.add_argument("--output", default=None,
                    help="root (default: campaign-data with --background-source gtp, "
                         "campaign-data-direct with --background-source direct, "
                         "campaign-data-no-background with --background 0)")
    ap.add_argument("--compare-only", metavar="FOLDER",
                    help="runs nothing: only compares what is already recorded. With background, the "
                         "root (e.g. campaign-data); without background, the folder of the profile "
                         "(e.g. campaign-data-no-background/teleoperation)")
    args = ap.parse_args()

    try:
        levels = sorted({int(x) for x in args.background.split(",") if x.strip()})
    except ValueError:
        ap.error("--background accepts integers separated by commas, e.g. 0,80,95")
    if not levels or min(levels) < 0 or max(levels) >= 100:
        ap.error("--background: each level in [0, 100) -- nothing above the capacity")
    requests = list(dict.fromkeys(p.strip() for p in (args.prof or "").split(",") if p.strip()))

    t0 = time.time()
    rec_entry, stopped_at = None, None
    if args.compare_only:
        folder = os.path.abspath(args.compare_only)
        if not os.path.isdir(folder):
            ap.error(f"does not exist: {folder}")
        findings = levels_in(folder)
        if findings:
            levels, legacy, output = findings, False, folder
            sub = os.path.join(folder, level_name(levels[0]))
            found = sorted(d for d in os.listdir(sub) if os.path.isdir(os.path.join(sub, d)))
            missing_n = [p for p in requests if p not in found]
            if missing_n:
                ap.error(f"no result for {', '.join(missing_n)} in {folder} "
                         f"(found: {', '.join(found)})")
            profiles = requests or found
            if not profiles:
                ap.error(f"no profile in {sub}")
        else:
            levels, legacy = [0], True
            profiles = [os.path.basename(folder)]
            output = os.path.dirname(folder)
    else:
        if args.rounds < 1:
            ap.error("--rounds must be >= 1")
        if args.first_round < 1:
            ap.error("--first-round must be >= 1")
        if args.first_round > args.rounds:
            ap.error(f"--first-round {args.first_round} is greater than --rounds "
                     f"{args.rounds}: there is no round to measure")
        profiles = requests or ["vr-cloud"]
        # A wrong name must stop NOW, and not hours later, when the campaign
        # reaches the profile.
        known = getattr(test_module("a"), "PROFILES", {})
        wrong = [p for p in profiles if p not in known]
        if wrong:
            ap.error(f"unknown profile: {', '.join(wrong)} "
                     f"(known: {', '.join(sorted(known))})")
        legacy = levels == [0]
        if not legacy and 0 not in levels:
            ap.error("--background must include 0: without the level without background there is nothing to "
                     "measure how much the congestion costs each scenario against")
        output = args.output or os.path.join(
            BASE, "campaign-data-no-background" if legacy else DEFAULT_OUTPUT[args.background_source])
        if not legacy and args.background_source == "gtp":
            R = load_background_module()
        existing = [] if legacy or not os.path.isdir(output) else levels_in(output)
        if existing and existing != levels:
            # Mixing levels of different campaigns breaks the pairing: the
            # "no background" already recorded was measured in ANOTHER deployment, another day, and the
            # resume would skip it. A campaign with other levels goes to another folder.
            if args.output:
                ap.error(f"{output} already has a campaign with the levels "
                         f"{', '.join(level_label(x) for x in existing)}. The requested levels "
                         "are different: use another --output so as not to mix different deployments")
            output = f"{output}-{'-'.join(str(x) for x in levels)}"
            print(f"{YELLOW}the default folder already has another campaign "
                  f"({', '.join(level_label(x) for x in existing)}); this one goes to "
                  f"{os.path.relpath(output, BASE)}{RESET}")
        for prof in profiles:
            for nv in levels:
                os.makedirs(level_root(output, prof, nv, legacy), exist_ok=True)
        rec_entry = open_record(output, args, profiles, levels)
        keep_awake()
        available = shutil.disk_usage(output).free
        if available < 2 << 30:
            print(f"  {YELLOW}warning{RESET}: only {available / 2 ** 30:.1f} GB free in {output}; a "
                  "complete campaign with per-frame CSV takes a few hundred MB")
        if not (rec_entry[1].get("kubectl") or {}).get("serverVersion"):
            print(f"  {YELLOW}warning{RESET}: kubectl did not answer with the cluster version in 20 s. "
                  "If the cluster is unreachable, the first deployment will fail.")
        _capacities.extend(recorded_capacities(output))
        try:
            ip_srv = prepare_background(args, levels, legacy, profiles)
            for i, prof in enumerate(profiles, 1):
                if len(profiles) > 1:
                    print(f"\n{'=' * 72}\n= PROFILE {i} of {len(profiles)}: {prof}\n{'=' * 72}")
                rounds(args, output, levels, legacy, prof, ip_srv)
        except KeyboardInterrupt:
            stopped_at = "interrupted"
            print(f"\n{YELLOW}interrupted{RESET}: run the same command to continue from where it stopped",
                  file=sys.stderr)
        except BackgroundError as e:
            stopped_at = "background"
            print(f"\n{RED}CAMPAIGN STOPPED: problem in the background traffic{RESET}\n  {e}",
                  file=sys.stderr)
        except InstrumentError as e:
            stopped_at = "instrument"
            print(f"\n{RED}CAMPAIGN STOPPED: problem in the measurement instrument{RESET}\n  {e}",
                  file=sys.stderr)

    args._legacy = legacy
    exit_codes = {}
    for prof in profiles:
        if len(profiles) > 1:
            print(f"\n{'#' * 72}\n# RESULT: {prof}\n{'#' * 72}")
        exit_codes[prof] = report(args, output, prof, levels, legacy, t0)
    exit_code = max([*exit_codes.values(), 1 if stopped_at else 0])
    if rec_entry:
        close_record(*rec_entry, {"stopped_at": stopped_at, "exit_code_by_profile": exit_codes,
                                   "exit_code": exit_code})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
