#!/usr/bin/env python3
"""
Background traffic THROUGH THE USER PLANE: iperf3 going down through the GTP-U
tunnel to a second UERANSIM on brix-porvir-03 (background/background-gtp.yaml).

    background-generator (petshopboys) --N6--> anchor UPF --GTP-U--> background gNB (brix-03)
                                               A: upf  |  B: psa-upf

It is the library of the campaign (campaign.py --background-source gtp) and
the tool to set up and check the background by hand. The scenario (A or B)
must be running: the background UE registers at its AMF.

    python3 scripts/background_gtp.py up --scenario b      # applies, provisions the UE, opens the session
    python3 scripts/background_gtp.py proof --scenario b   # 6 s at 50 Mbps: where the background went
    python3 scripts/background_gtp.py capacity             # iperf3 TCP petshopboys -> brix-03
    python3 scripts/background_gtp.py on --mbps 300 --seconds 20
    python3 scripts/background_gtp.py status
    python3 scripts/background_gtp.py down

UNIT OF THE NUMBERS
    The background datagram has 1356 B so that the GTP-U packet on the wire has
    the SAME size (1428 B of IP) as the 1400 B datagram of the direct background
    (background/iperf.yaml). The Mbps "requested" and "crossed" are counted in
    this standard -- packets x 1400 B -- and so mean the same thing as in the
    earlier campaign with direct background: same level = same packet and same
    packet rate on the link. iperf receives the adjusted rate (iperf_rate).
    "gtpu_ip_mbps" is what actually passed, in IP bytes of the GTP-U packet.

WHAT COUNTS AS "CROSSED THE LINK"
    The counters of the BACKGROUND-GTPU chain in the netns of the background pod:
    every GTP-U that reaches the pod goes through it BEFORE nr-gnb, including
    what it discards. UERANSIM cannot handle the background rate (see the
    manifest) and only receives a trickle; the rest has already crossed the link
    when it is dropped. iperf3 on the UE side sees huge loss, and that is expected.
"""
import argparse
import importlib.util
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
MANIFEST = os.path.join(BASE, "background", "background-gtp.yaml")

NS = "free5gc"
GENERATOR = "background-generator"       # source of the background, on the node of the anchor UPF
BG_GTP = "background-ueransim"        # background gNB + UE + iperf, on brix-porvir-03
PORT = 5201                    # background server at the generator (and of the capacity at the background pod)
LOOPBACK_PORT = 5202           # CPU control of the pilot, on the loopback of the generator
TUN = "uesimtun0"
CHAIN = "BACKGROUND-GTPU"

DATAGRAM = 1356                # UDP payload: 1428 B of IP in the GTP-U packet
DATAGRAM_EQUIV = 1400          # the one of the direct background -- the unit of the Mbps
# iperf3 -P: each flow well below what one thread generates (same as the direct background).
MBPS_PER_FLOW = 250
# AMBR of the background UE. The default of provision_subscribers.py (100 Mbps of session
# downlink) would become a ceiling for the background if gtp5g QoS is on at the node.
AMBR = "5 Gbps"
MONGO_PORT = 27018             # != 27017, which step 6 of the tests uses

# epc-mode of the relevant pods, per scenario.
ANCHOR = {"a": "upf", "b": "psa-upf"}           # UPF from which the background leaves
EDGE = {"a": None, "b": "i-upf"}                # dUPF that the background must NOT touch
DEPLOY_UPF = {"upf": "free5gc-upf", "psa-upf": "free5gc-psa-upf", "i-upf": "free5gc-i-upf"}
SEGMENT_PREFIX = 22           # the same segment criterion as the tests


class GtpBackgroundError(Exception):
    pass


# --------------------------------------------------------------------------
# the background UE, read from the manifest ITSELF (a single source for IMSI, keys
# and slice -- provisioning something different from what UERANSIM uses would fail silently)
# --------------------------------------------------------------------------
def _ue_from_manifest():
    for d in yaml.safe_load_all(open(MANIFEST, encoding="utf-8")):
        if d and d.get("kind") == "ConfigMap":
            raw = (d.get("data") or {}).get("ue.yaml")
            if raw:
                # BaseLoader: everything as string, otherwise 'sd: 0x112233' becomes an integer.
                ue = yaml.load(raw, Loader=yaml.BaseLoader)
                s = ue["sessions"][0]["slice"]
                sd = s["sd"].lower()
                return {"supi": ue["supi"], "key": ue["key"], "opc": ue["op"],
                        "amf": ue["amf"], "sst": int(s["sst"], 0),
                        "sd": f"{int(sd, 16):06x}" if sd.startswith("0x") else sd.zfill(6),
                        "dnn": ue["sessions"][0]["apn"]}
    raise GtpBackgroundError(f"ue.yaml not found in {MANIFEST}")


UE = _ue_from_manifest()
IMSI = UE["supi"]


# --------------------------------------------------------------------------
# kubectl
# --------------------------------------------------------------------------
def kubectl(*a, timeout=120):
    try:
        # explicit utf-8: on Windows the default is cp1252, and the kubectl output is utf-8.
        return subprocess.run(["kubectl", "-n", NS, *a], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(a, 124, "", f"timeout ({timeout}s)")


def exec_pod(deploy, container, *cmd, timeout=60):
    args = ["exec", f"deploy/{deploy}"] + (["-c", container] if container else []) + ["--", *cmd]
    return kubectl(*args, timeout=timeout)


def pod(selector):
    """(node, ip) of the first Running pod with the selector; (None, None) if there is none."""
    r = kubectl("get", "pod", "-l", selector, "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].spec.nodeName} {.items[0].status.podIP}")
    parts = r.stdout.split()
    return (parts[0], parts[1]) if len(parts) == 2 else (None, None)


def _node_ip(node_name):
    if not node_name:
        return None
    r = kubectl("get", "node", node_name, "-o",
                "jsonpath={.status.addresses[?(@.type=='InternalIP')].address}")
    return r.stdout.strip() or None


def same_segment(a, b):
    ia, ib = _node_ip(a), _node_ip(b)
    if not ia or not ib:
        return None
    return ipaddress.ip_address(ib) in ipaddress.ip_network(f"{ia}/{SEGMENT_PREFIX}",
                                                            strict=False)


def json_of(txt):
    try:
        return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except ValueError:
        return {"error": (txt or "no output").strip()[:300]}


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------
def apply(timeout=300):
    r = kubectl("apply", "-f", MANIFEST)
    if r.returncode:
        raise GtpBackgroundError(f"kubectl apply of the background failed: {r.stderr.strip()[:300]}")
    for dep in (GENERATOR, BG_GTP):
        r = kubectl("rollout", "status", f"deploy/{dep}", f"--timeout={timeout}s",
                    timeout=timeout + 30)
        if r.returncode:
            raise GtpBackgroundError(f"{dep} was not ready: {(r.stderr or r.stdout).strip()[:300]}")


def bring_down():
    kubectl("delete", "-f", MANIFEST, "--ignore-not-found=true", "--wait=false", timeout=60)


def placement(scenario):
    """Where each piece is NOW. Raises GtpBackgroundError if the design does not hold:
    a generator outside the node of the anchor does not leave through the NIC of the
    UPF, and a background inside the experiment would worsen the measurement through CPU."""
    gen_node, ip_gen = pod(f"app={GENERATOR}")
    bg_node, ip_bg = pod(f"app={BG_GTP}")
    anc_node, _ = pod(f"epc-mode={ANCHOR[scenario]}")
    experiment = {p: pod(f"epc-mode={p}")[0] for p in ("ueransim", "mec-app", "i-upf")}
    if not ip_gen or not ip_bg:
        raise GtpBackgroundError("the background pods are not Running (apply background/background-gtp.yaml)")
    if not anc_node:
        raise GtpBackgroundError(f"the anchor UPF of scenario {scenario.upper()} "
                        f"(epc-mode={ANCHOR[scenario]}) is not running")
    if gen_node != anc_node:
        raise GtpBackgroundError(f"the generator is on {gen_node} and the anchor UPF on {anc_node}: "
                        "adjust the nodeSelector of background-generator in background/background-gtp.yaml")
    inside = [p for p, node_name in experiment.items() if node_name and node_name == bg_node]
    if inside:
        raise GtpBackgroundError(f"the background UERANSIM landed on {bg_node}, which hosts "
                        f"{', '.join(inside)} of the experiment: choose another small machine in "
                        "background/background-gtp.yaml")
    if experiment["ueransim"] and same_segment(bg_node, experiment["ueransim"]) is False:
        raise GtpBackgroundError(f"the background UERANSIM ({bg_node}) is not in the segment of the edge machines: the "
                        "background would not descend the same core -> edge link as the test")
    return {"generator_node": gen_node, "generator_ip": ip_gen, "background_node": bg_node,
            "background_ip": ip_bg, "anchor_node": anc_node}


def provision(port_num=MONGO_PORT):
    """Writes the background UE to Mongo, REPLACING whatever has the same
    IMSI. Step 6 of the tests runs provision_subscribers.py --clean, which deletes every
    subscriber -- hence this runs after it, at each setup."""
    try:
        import pymongo
    except ImportError:
        raise GtpBackgroundError("pymongo not installed: pip install -r scripts/requirements.txt")
    spec = importlib.util.spec_from_file_location("provision_subscribers",
                                                  os.path.join(HERE, "provision_subscribers.py"))
    ins = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ins)
    pf = subprocess.Popen(["kubectl", "-n", NS, "port-forward", "svc/mongo", f"{port_num}:27017"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        if pf.poll() is not None:
            raise GtpBackgroundError(f"port-forward of mongo died (local port {port_num} in use?)")
        db = pymongo.MongoClient(f"mongodb://localhost:{port_num}/",
                                 serverSelectionTimeoutMS=15000)["free5gc"]
        try:
            tenant = ins.resolve_tenant_id(db, None)
        except SystemExit as e:
            raise GtpBackgroundError(str(e))
        a = argparse.Namespace(sst=UE["sst"], sd=UE["sd"], dnn=UE["dnn"], plmn="20893",
                               key=UE["key"], opc=UE["opc"], amf=UE["amf"],
                               sqn="000000000023", tenant_id=tenant,
                               ue_ambr_ul=AMBR, ue_ambr_dl=AMBR,
                               sess_ambr_ul=AMBR, sess_ambr_dl=AMBR)
        for coll, doc in ins.make_docs(IMSI, a).items():
            db[coll].delete_many({"ueId": IMSI})
            db[coll].insert_one(doc)
    finally:
        pf.terminate()
        try:
            pf.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pf.kill()


def ue_ip():
    r = exec_pod(BG_GTP, "ue", "ip", "-4", "-o", "addr", "show", TUN, timeout=30)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
    return m.group(1) if m else None


def ue_registered():
    r = exec_pod(BG_GTP, "ue", "./nr-cli", IMSI, "-e", "status", timeout=30)
    if r.returncode:
        return None
    return "RM-REGISTERED" in r.stdout


def core(scenario):
    """The pods that hold the session of the background UE: AMF, SMF and the anchor
    UPF. A recreated pod gets a new name, so this tuple changes at each
    deployment of the scenario. It tells whether the session of the UE still exists
    on the core side -- UERANSIM does not know: after the core goes down it stays
    RM-REGISTERED with an IP on uesimtun0 (in one campaign, the background of B
    was turned on in a UE opened in the core of A and no packet passed)."""
    name_list = []
    for node_role in ("amf", "smf", ANCHOR[scenario]):
        r = kubectl("get", "pod", "-l", f"epc-mode={node_role}",
                    "--field-selector=status.phase=Running",
                    "-o", "jsonpath={.items[*].metadata.name}")
        name_list.append(" ".join(sorted(r.stdout.split())) or None)
    return tuple(name_list)


def restart_ue(timeout=180):
    """Recreates the background pod and waits for the PDU session. It always
    recreates: after a deployment the old gNB kept the SCTP of an AMF that no
    longer exists, and a UE that only LOOKS registered would be worse than none."""
    kubectl("rollout", "restart", f"deploy/{BG_GTP}")
    r = kubectl("rollout", "status", f"deploy/{BG_GTP}", f"--timeout={timeout}s",
                timeout=timeout + 30)
    if r.returncode:
        raise GtpBackgroundError(f"{BG_GTP} did not come back: {(r.stderr or r.stdout).strip()[:300]}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        ip = ue_ip()
        if ip:
            return ip
        time.sleep(3)
    log = kubectl("logs", f"deploy/{BG_GTP}", "-c", "ue", "--tail=15").stdout.strip()
    raise GtpBackgroundError(f"background UE without a PDU session after {timeout}s ({TUN} without IP). "
                    f"Last lines of nr-ue:\n{log}")


def prepare(scenario, timeout=300, mongo_port=MONGO_PORT, log=print):
    """Everything that must happen AFTER the deployment and BEFORE turning the background on."""
    apply(timeout)
    est = placement(scenario)
    log(f"  background: generator on {est['generator_node']} (anchor {ANCHOR[scenario]} on "
        f"{est['anchor_node']}), background UERANSIM on {est['background_node']}")
    provision(mongo_port)
    ue = restart_ue(timeout)
    # Again: the recreated pod has ANOTHER IP, and the capacity is measured up to it. With
    # the placement from before the restart, the capacity iperf hung
    # on an IP that no longer existed (pilot of B).
    est = placement(scenario)
    est.update(ue_ip=ue, scenario=scenario)
    log(f"  background: UE {IMSI} with a PDU session, {TUN} = {est['ue_ip']}")
    return est


def current_state(scenario):
    """The state of a background ALREADY set up (for the command line)."""
    est = placement(scenario)
    est["ue_ip"] = ue_ip()
    est["scenario"] = scenario
    if not est["ue_ip"]:
        raise GtpBackgroundError(f"background UE without a session ({TUN} without IP): run 'up' first")
    return est


# --------------------------------------------------------------------------
# counters
# --------------------------------------------------------------------------
def if_counters(deploy, container, iface):
    """rx/tx (bytes, packets) of an interface, read from /proc/net/dev of the pod."""
    r = exec_pod(deploy, container, "cat", "/proc/net/dev")
    for line in r.stdout.splitlines():
        m = re.match(r"\s*([^:]+):\s*(.*)$", line)
        if m and m.group(1).strip() == iface:
            c = m.group(2).split()
            return {"rx_bytes": int(c[0]), "rx_pkts": int(c[1]),
                    "tx_bytes": int(c[8]), "tx_pkts": int(c[9])}
    return None


def gtpu_counters():
    """Counters of the BACKGROUND-GTPU chain, in the order of the rules of the manifest:
    small (pass), delivered to UERANSIM (limit), dropped."""
    r = exec_pod(BG_GTP, "iperf", "iptables", "-nvx", "-L", CHAIN)
    rules = []
    for line in r.stdout.splitlines():
        c = line.split()
        if len(c) >= 3 and c[0].isdigit() and c[1].isdigit():
            rules.append((int(c[0]), int(c[1])))
    if len(rules) != 3:
        return None
    (pp, pb), (ep, eb), (std, db) = rules
    return {"small_pkts": pp, "large_pkts": ep + std, "large_bytes": eb + db,
            "delivered_pkts": ep, "dropped_pkts": std}


def delta(a, b):
    if a is None or b is None:
        return None
    return {k: b[k] - a[k] for k in a}


def qos_gtp5g(scenario):
    """/proc/gtp5g/qos of the anchor node (kernel module: it belongs to the HOST). '1' =
    gtp5g applies the AMBR -- hence the background UE has a high AMBR."""
    r = exec_pod(DEPLOY_UPF[ANCHOR[scenario]], None, "cat", "/proc/gtp5g/qos", timeout=30)
    return r.stdout.strip() or None


def gtpu_origin(seconds=4):
    """{ip: packets} of the ORIGIN of the large GTP-U that reaches the background pod.
    It is the proof of the path: it must be ONLY the pod of the anchor UPF."""
    r = exec_pod(BG_GTP, "iperf", "timeout", str(seconds), "tcpdump", "-n", "-l", "-i", "eth0",
           "-c", "30", "udp dst port 2152 and greater 1000", timeout=seconds + 30)
    origins = {}
    # Origin by IP, without assuming the source port that gtp5g uses.
    for m in re.finditer(r"IP (\d+\.\d+\.\d+\.\d+)\.\d+ > \d+\.\d+\.\d+\.\d+\.2152\b",
                         r.stdout):
        origins[m.group(1)] = origins.get(m.group(1), 0) + 1
    return origins


def upf_ips(node_role):
    """IPs from which the GTP-U of a UPF may reach the gNB: the pod IP AND the
    ClusterIP of the Service (same name as the epc-mode). N3 is addressed to the
    ClusterIP (endpoints of smfcfg); kube-proxy DNATs the uplink to the
    pod, and the downlink from the UPF to the gNB -- same ports, 2152 <-> 2152 --
    falls in conntrack as the REPLY of that flow and leaves with the source
    translated back to the ClusterIP. Seen in the pilot of B: the background
    arrived from 10.108.124.178, the ClusterIP of psa-upf, and not from the pod."""
    _, ip_pod = pod(f"epc-mode={node_role}")
    r = kubectl("get", "svc", node_role, "-o", "jsonpath={.spec.clusterIP}")
    return {ip for ip in (ip_pod, r.stdout.strip()) if ip}


def check_origin(scenario, origins):
    """(ok, text). ok None = nothing arrived to judge."""
    anc = upf_ips(ANCHOR[scenario])
    edge = upf_ips(EDGE[scenario]) if EDGE[scenario] else set()
    if not origins:
        return None, "no background GTP-U captured in the background UE pod"
    name_list = {**{ip: EDGE[scenario] for ip in edge}, **{ip: ANCHOR[scenario] for ip in anc}}
    desc = ", ".join(f"{name_list.get(ip, ip)} via {ip} ({n})" for ip, n in sorted(origins.items()))
    if anc and set(origins) <= anc:
        return True, f"background GTP-U came only from {ANCHOR[scenario]}: {desc}"
    return False, (f"background GTP-U came from {desc}; expected only from {ANCHOR[scenario]} "
                   f"({', '.join(sorted(anc)) or '?'})"
                   + (" -- the background is going through the Edge Node" if set(origins) & edge else ""))


# --------------------------------------------------------------------------
# background
# --------------------------------------------------------------------------
def iperf_rate(requested_mbps):
    """Payload rate for iperf with a 1356 B datagram that puts on the wire the
    SAME packet rate as the request in 1400 B datagrams."""
    return requested_mbps * DATAGRAM / DATAGRAM_EQUIV


def capacity(est, seconds=10):
    """iperf3 TCP, 4 flows, from the generator to the background pod, OUTSIDE the tunnel:
    the same wire petshopboys -> brix-03 that the background GTP-U travels."""
    for attempt in (1, 2):
        r = exec_pod(GENERATOR, "iperf", "iperf3", "-c", est["background_ip"], "-p", str(PORT),
               "-P", "4", "-t", str(seconds), "-J", timeout=seconds + 60)
        j = json_of(r.stdout) if r.stdout.strip() else {
            "error": f"kubectl exec rc={r.returncode}: {(r.stderr or 'no output').strip()[:300]}"}
        if "busy" in str(j.get("error", "")) and attempt == 1:
            time.sleep(10)
            continue
        break
    rec = ((j.get("end") or {}).get("sum_received") or {}).get("bits_per_second")
    if j.get("error") or not rec:
        raise GtpBackgroundError(f"could not measure the capacity up to {est['background_ip']}: "
                        f"{j.get('error', 'no throughput received')}")
    return rec / 1e6


def stop_proc():
    """Stops the background on both sides. The client (at the UE) notifies the server and
    exits; also killing the server at the generator guarantees that nothing keeps sending if
    the control was lost -- the loop of the manifest restarts it in 1 s."""
    exec_pod(BG_GTP, "iperf", "pkill", "-f", "^iperf3 -c", timeout=30)
    exec_pod(GENERATOR, "iperf", "pkill", "-f", f"^iperf3 -s -p {PORT}$", timeout=30)
    exec_pod(GENERATOR, "iperf", "pkill", "-f", "^iperf3 -c", timeout=30)   # CPU control
    time.sleep(2)


def turn_on(est, requested_mbps, seconds):
    """Turns the background on (UDP, generator -> UE, through the tunnel). requested in Mbps
    in the 1400 B standard (see the header). Returns the state for turn_off()."""
    rate = iperf_rate(requested_mbps)
    flows = max(1, math.ceil(rate / MBPS_PER_FLOW))
    cmd = ["kubectl", "-n", NS, "exec", f"deploy/{BG_GTP}", "-c", "iperf", "--",
           "iperf3", "-c", est["generator_ip"], "-p", str(PORT), "-B", est["ue_ip"],
           "-R", "-u", "-b", f"{rate / flows:.1f}M", "-l", str(DATAGRAM),
           "-P", str(flows), "-t", str(math.ceil(seconds)), "-J"]
    before = {"gtpu": gtpu_counters(), "generator": if_counters(GENERATOR, "iperf", "eth0")}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    return {"proc": proc, "before": before, "t0": time.time(), "requested_mbps": requested_mbps,
            "iperf_rate_mbps": rate, "flows": flows}


def turn_off(on_, wait_s=None):
    """Turns off and returns what the background did. wait_s: waits for iperf to finish
    by itself (pilot); None: stops now (campaign, at the end of the measurement)."""
    proc = on_["proc"]
    output = ""
    if wait_s is not None:
        try:
            output, _ = proc.communicate(timeout=wait_s + 60)
        except subprocess.TimeoutExpired:
            proc.kill()
    t_end = time.time()
    stop_proc()
    if wait_s is None:
        try:
            output, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    sec = t_end - on_["t0"]
    g = delta(on_["before"]["gtpu"], gtpu_counters())
    e = delta(on_["before"]["generator"], if_counters(GENERATOR, "iperf", "eth0"))
    reg = {"mode": "gtp", "requested_mbps": on_["requested_mbps"],
           "iperf_rate_mbps": round(on_["iperf_rate_mbps"], 1), "datagram": DATAGRAM,
           "flows": on_["flows"], "seconds_on": round(sec, 1),
           "sent_mbps": None, "crossed_mbps": None, "gtpu_ip_mbps": None, "gtpu_pkts": None,
           "path_loss_pct": None, "delivered_to_ue_pkts": None, "dropped_at_background_ue_pkts": None}
    mbps = lambda pkts: pkts * DATAGRAM_EQUIV * 8 / sec / 1e6   # noqa: E731
    if e and sec > 0:
        reg["sent_mbps"] = mbps(e["tx_pkts"])
    if g and sec > 0:
        reg["crossed_mbps"] = mbps(g["large_pkts"])
        reg["gtpu_pkts"] = g["large_pkts"]
        reg["gtpu_ip_mbps"] = g["large_bytes"] * 8 / sec / 1e6
        reg["delivered_to_ue_pkts"] = g["delivered_pkts"]
        reg["dropped_at_background_ue_pkts"] = g["dropped_pkts"]
        if e and e["tx_pkts"]:
            reg["path_loss_pct"] = max(0.0, 1 - g["large_pkts"] / e["tx_pkts"]) * 100
    j = json_of(output) if output else {}
    if j.get("error"):
        reg["iperf_error"] = j["error"]
    elif not output and wait_s is not None:
        reg["iperf_error"] = "iperf without output (timeout)"
    return reg


def start_loopback(requested_mbps, seconds):
    """CPU control of the pilot: the SAME background load, from the generator to its
    own loopback. The generator works the same and nothing goes out to the network."""
    rate = iperf_rate(requested_mbps)
    flows = max(1, math.ceil(rate / MBPS_PER_FLOW))
    cmd = ["kubectl", "-n", NS, "exec", f"deploy/{GENERATOR}", "-c", "iperf", "--",
           "iperf3", "-c", "127.0.0.1", "-p", str(LOOPBACK_PORT), "-u",
           "-b", f"{rate / flows:.1f}M", "-l", str(DATAGRAM), "-P", str(flows),
           "-t", str(math.ceil(seconds)), "-J"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")


def path_proof(est, mbps=50, seconds=6, log=print):
    """Short background WITHOUT traffic of the experiment, to see where it goes:
      - the origin of the GTP-U that reaches the background pod (tcpdump): only the anchor;
      - in B, eth0 of the I-UPF idle: the background does not touch the Edge Node;
      - upfgtp of the anchor counting what went down (the UPF encapsulated the background).
    Returns (problems, details)."""
    scen = est["scenario"]
    anc = DEPLOY_UPF[ANCHOR[scen]]
    edge = DEPLOY_UPF[EDGE[scen]] if EDGE[scen] else None
    a0 = if_counters(anc, None, "upfgtp")
    b0 = if_counters(edge, None, "eth0") if edge else None
    on_ = turn_on(est, mbps, seconds)
    time.sleep(2)
    origins = gtpu_origin()
    reg = turn_off(on_, wait_s=seconds)
    da = delta(a0, if_counters(anc, None, "upfgtp"))
    db = delta(b0, if_counters(edge, None, "eth0")) if edge else None
    ok, txt = check_origin(scen, origins)
    problems = [] if ok else [txt]
    det = {"origins": origins, "origin": txt, "background_source": reg, "anchor_upfgtp": da,
           "edge_eth0": db, "qos_gtp5g": qos_gtp5g(scen)}
    gtpu_bytes = (reg["gtpu_ip_mbps"] or 0) * 1e6 / 8 * reg["seconds_on"]
    if not reg["gtpu_pkts"]:
        problems.append("no background packet reached the background pod"
                         + (f" (iperf: {reg['iperf_error']})" if reg.get("iperf_error") else ""))
    elif da is None or da["tx_pkts"] < 0.5 * reg["gtpu_pkts"]:
        problems.append(f"upfgtp of {ANCHOR[scen]} did not count the background: it did not leave through the "
                         "anchor UPF")
    if db is not None and gtpu_bytes and db["rx_bytes"] > 0.1 * gtpu_bytes:
        problems.append(f"eth0 of {EDGE[scen]} received {db['rx_bytes'] / 1e6:.1f} MB during "
                         f"the proof ({gtpu_bytes / 1e6:.1f} MB of background): the background goes through the "
                         "Edge Node")
    log(f"  background: {txt}")
    log(f"  background: {mbps:g} Mbps requested, {reg['crossed_mbps'] or 0:.1f} crossed; "
        f"upfgtp of {ANCHOR[scen]} TX +{(da or {}).get('tx_pkts', '?')} pkts"
        + (f"; eth0 of {EDGE[scen]} RX +{db['rx_bytes'] / 1e3:.0f} kB" if db else "")
        + f"; /proc/gtp5g/qos = {det['qos_gtp5g']}")
    return problems, det


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------
def status():
    for app in (GENERATOR, BG_GTP):
        node_name, ip = pod(f"app={app}")
        print(f"  {app:<16} {node_name or '-'} {ip or '(not Running)'}")
    if pod(f"app={BG_GTP}")[1]:
        print(f"  UE {IMSI}: {TUN} = {ue_ip() or '(no IP)'}; registered: {ue_registered()}")
        g = gtpu_counters()
        if g:
            print(f"  chain {CHAIN}: {g['large_pkts']} background packets, "
                  f"{g['delivered_pkts']} delivered to UERANSIM, "
                  f"{g['dropped_pkts']} dropped, {g['small_pkts']} small")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("up", "proof", "capacity", "on", "status", "down"))
    ap.add_argument("--scenario", choices=("a", "b"),
                    help="the running scenario (up, proof, on; default: the one with a UPF running)")
    ap.add_argument("--mbps", type=float, default=50,
                    help="on/proof: background in Mbps in the 1400 B standard (default: 50)")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--mongo-port", type=int, default=MONGO_PORT)
    args = ap.parse_args()

    scen = args.scenario
    if args.action in ("up", "proof", "on") and not scen:
        scen = "b" if pod("epc-mode=psa-upf")[0] else ("a" if pod("epc-mode=upf")[0] else None)
        if not scen:
            ap.error("no scenario running (neither upf nor psa-upf): bring one up with deploy.py")
        print(f"  running scenario: {scen.upper()}")
    try:
        if args.action == "up":
            prepare(scen, args.timeout, args.mongo_port)
        elif args.action == "proof":
            problems, _ = path_proof(current_state(scen), args.mbps)
            for p in problems:
                print(f"  PROBLEM: {p}")
            print("  background path OK" if not problems else "  background path WRONG")
            return 1 if problems else 0
        elif args.action == "capacity":
            est = placement(scen or ("b" if pod("epc-mode=psa-upf")[0] else "a"))
            print(f"  usable capacity {est['generator_node']} -> {est['background_node']}: "
                  f"{capacity(est):.0f} Mbps")
        elif args.action == "on":
            on_ = turn_on(current_state(scen), args.mbps, args.seconds)
            print(f"  background on: {args.mbps:g} Mbps for {args.seconds:g}s "
                  f"({on_['flows']} flow(s), iperf at {on_['iperf_rate_mbps']:.1f} Mbps)")
            try:
                reg = turn_off(on_, wait_s=args.seconds)
            except KeyboardInterrupt:
                reg = turn_off(on_)
            print(json.dumps(reg, indent=2))
        elif args.action == "status":
            status()
        else:
            stop_proc()
            bring_down()
            print("  background removed")
    except GtpBackgroundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
