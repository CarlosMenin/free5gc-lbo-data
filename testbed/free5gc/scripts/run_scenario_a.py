#!/usr/bin/env python3
"""
End-to-end test of SCENARIO A (centralized UPF -- the baseline) on free5GC v4.2.3.
It is run_scenario_b.py adapted to Scenario A: same parameters, profiles,
campaign, health guards and report format, so that the results of the two
scenarios are comparable (a-mec x b-mec: same destination, anchor elsewhere).

It runs the whole chain, in the order in which each step depends on the previous
one, and stops at the first that fails -- because going on only produces derived
symptoms:

    1. tools and connection to the cluster
    2. validate.py (static consistency of the manifests)
    3. deployment of Scenario A                     (optional, --deploy)
    4. pods ready
    5. placement: where each piece actually landed
    6. subscribers loaded in Mongo                  (optional, --load-subscribers)
    7. PFCP association with the central UPF
    8. UERANSIM tester running (replicas come from the manifest)
    9. PDU session with an IP in the pool of the central UPF
   10. route of the destinations inside the tunnel of the UE
   11. PROOF OF THE CENTRAL ANCHORING: the central UPF counts the MEC and the remote traffic
   12. VR measurement campaign (a-mec x a-remote)
   13. collection of the results
   14. teardown of the deployments/statefulset     (when this script brought them up)

Step 11 is what defines the scenario: in Scenario A there is no breakout, so the
central UPF must count BOTH flows -- including that of mec-app, which leaves the
edge, goes up the backhaul to the core and comes back (the "trombone" that
Scenario B eliminates).

HOW THE MEASUREMENT DEFENDS ITSELF (step 12)

    Alternating order. At each execution the two paths swap places in the
                       queue. Always measuring MEC first would turn any drift
                       along the execution into a difference between paths.

    Paired gain.       The difference is computed WITHIN each execution and only
                       then aggregated. What varies between executions (a new
                       deployment, the cluster in another state) is common to both
                       measurements and cancels, instead of widening the error bar.

    Health guards.     A measurement only enters the table if it measured the
                       NETWORK: the generator sustained the cadence (frames_late),
                       managed to hand the packets to the kernel (send_dropped), the
                       kernel of the client dropped nothing due to a full queue
                       (SO_RXQ_OVFL), the clock had no NTP step, and BOTH paths lost
                       similar amounts -- only a complete frame becomes a latency
                       sample, so very different losses make the percentiles
                       incomparable.

    Exact loss.        The denominator comes from the counter of the server
                       (packets actually handed to the kernel), not from the
                       sequence interval that the client managed to observe.

CAMPAIGN OF 10 EXECUTIONS:

    python3 scripts/run_scenario_a.py --repetitions 10 --load-subscribers 5

Each execution brings the scenario up from zero, measures, collects and TEARS
DOWN the deployments and the StatefulSet before the next one -- this is what
makes the 10 repetitions independent instead of 10 measurements of the same warm
core. The namespace is never touched: it already exists, does not belong to the
experiment, and removal is always by resource NAME, never 'delete -f' or '--all'.

At the end comes the aggregated table (mean +- standard deviation across
executions) and, in results-a/:

    kpi-table.md                 table ready to paste into the text
    summary-per-execution.csv    one line per (execution, path) -- for boxplots
    kpis-aggregated.csv          the same table in CSV
    run.json                     everything raw, including discarded executions
    run-01/ ... run-10/          per-frame CSV and JSON summary of each execution

Typical use (testbed already running, one execution, tearing down nothing):

    python3 scripts/run_scenario_a.py

One execution from zero, bringing the scenario up and populating Mongo:

    python3 scripts/run_scenario_a.py --deploy --load-subscribers 5

We only tear down what we brought up ourselves: without --deploy and without
--repetitions>1 the script deletes nothing, so as not to take down a testbed
that was already up.

Only the proof of the central anchoring, without a measurement campaign (fast, ~1 min):

    python3 scripts/run_scenario_a.py --proof-only

Following step by step (stops at each stage waiting for enter):

    python3 scripts/run_scenario_a.py -p

Run it from testbed/free5gc/ or from anywhere: the paths are resolved from the
location of this file.
"""
import argparse
import ipaddress
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import traceback
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NS = "free5gc"
# DYNAMIC ClusterIPs (Kubernetes allocates them; mec-af announces that of mec-app to the NEF).
# Resolved in p10_routes() with 'kubectl get svc'.
MEC_IP = None
REMOTE_IP = None
VR_PORT = 9100
TESTER_STS = "free5gc-ueransim"
TESTER_POD = "free5gc-ueransim-0"
TUN = "uesimtun0"
GTP_IF = "upfgtp"          # interface created by gtp5g inside the UPF pod
UE_POOL_PREFIX = "60.60."          # pool of the central UPF (60.60.0.0/17 in slice 010203)
IMSI_MAIN = "imsi-208930000000000"   # matches the supi of tester/ueransim.yaml

# Deployments that Scenario A requires running. Names checked against the manifests.
DEPLOYS = [
    "free5gc-mongodb", "free5gc-nrf", "free5gc-amf", "free5gc-ausf",
    "free5gc-nssf", "free5gc-pcf", "free5gc-nef", "free5gc-udm", "free5gc-udr",
    "free5gc-smf",
    "free5gc-webui",   # step 6 depends on it: the tenantId is born at the boot of the webui
    "free5gc-upf", "free5gc-mec-app", "free5gc-remote-app",
    "mec-af",          # running as in Scenario B, so that the environment is the same
]

# Deployments exclusive to Scenario B. If they are running together with A, the SMF
# keeps orphan UPFs associated and the proof of step 11 measures the wrong topology.
DEPLOYS_SCENARIO_B = ["free5gc-i-upf", "free5gc-psa-upf"]

# SBI NFs, which register at the NRF. The UPF is not one: it only speaks PFCP with the SMF.
# An NF that comes up before the NRF can write to Mongo keeps an EMPTY NF instance
# ID -- and the symptom only shows up at the registration of the UE, as
# "Mandatory IE [ausfInstanceId/AmfInstanceId] is missing" at the UDM and
# "Initial Registration failed [CONGESTION]" at the UE.
NFS_SBI = [
    "free5gc-udr", "free5gc-udm", "free5gc-ausf", "free5gc-nssf",
    "free5gc-pcf", "free5gc-nef", "free5gc-amf", "free5gc-smf",
    # the webconsole also registers at the NRF (as an AF) and prints the same marker
    "free5gc-webui",
]
OK_MARK = "OAuth2 setting receive from NRF"
ERROR_MARK = "register to NRF Error"

# --------------------------------------------------------------------------
# LOAD PROFILES
# --------------------------------------------------------------------------
# Each profile is a use case, not a loose number. The values are the ORDER OF
# MAGNITUDE that the composition of the case requires (resolution x fps x codec
# efficiency) -- they are here with the arithmetic in plain view so that the text
# can justify them, and not to be cited as a measurement of a real product.
# 
# bitrate_mbps  downlink PER SESSION (the flow of rendered media)
# fps           frame cadence of the server
# pose_hz       pose/control uplink -- the closed loop of the use case
# mtu           UDP payload per packet; 1200 stays below the MTU of the GTP-U tunnel
# 
# Changing the profile does NOT require editing a manifest: step 3 applies the values to
# both deployments (mec-app and remote-app) and checks that both computed the
# same load. Running several at once:
#     --profile vr-cloud,cloud-gaming,teleoperation --repetitions 10
PROFILES = {
    "vr-360": {
        "bitrate_mbps": 25, "fps": 60, "pose_hz": 120, "mtu": 1200,
        "description": "Stereoscopic 360-degree video, 4K at 60 fps (~25 Mbps in HEVC). "
                     "The pose only orients the projection, so 120 Hz is enough. "
                     "It is the floor of what is called VR: no remote rendering.",
    },
    "cloud-gaming": {
        "bitrate_mbps": 30, "fps": 60, "pose_hz": 120, "mtu": 1200,
        "description": "Game rendered at the edge, 1080p60 in high-quality HEVC "
                     "(~30 Mbps). Control at 120 Hz (gamepad/mouse). "
                     "Closed loop, but tolerant to ~50 ms of motion-to-photon delay.",
    },
    "vr-cloud": {
        "bitrate_mbps": 50, "fps": 90, "pose_hz": 250, "mtu": 1200,
        "description": "Interactive VR rendered at the edge: ~2K per eye at 90 fps "
                     "(~50 Mbps in HEVC) and pose at 250 Hz, the typical IMU rate "
                     "of a headset. It is the profile of the initial design and the most demanding "
                     "case that is still realistic.",
    },
    "vr-extreme": {
        "bitrate_mbps": 100, "fps": 90, "pose_hz": 250, "mtu": 1200,
        "description": "High-fidelity VR (~4K per eye). It finds the "
                     "CEILING of the testbed: if the load does not flow, the report says "
                     "where it stopped, and that is also a result.",
    },
    "ar-industrial": {
        "bitrate_mbps": 12, "fps": 60, "pose_hz": 200, "mtu": 1200,
        "description": "Assisted AR: 1080p video with an annotation overlay "
                     "(~12 Mbps). Light downlink, but the pose must be fast "
                     "so that the overlay does not drift from the real object.",
    },
    "teleoperation": {
        "bitrate_mbps": 8, "fps": 60, "pose_hz": 500, "mtu": 1200,
        "description": "Teleoperation/telemedicine: 720p60 support video "
                     "(~8 Mbps) with the CONTROL LOOP at 500 Hz. It inverts the "
                     "pattern of the other profiles -- little downlink, very frequent "
                     "uplink -- and is the case in which network latency matters "
                     "more than throughput.",
    },
}
DEFAULT_PROFILE = "vr-cloud"

# Deployments that run vr-server and must receive the profile.
APPS_VR = ("free5gc-mec-app", "free5gc-remote-app")

# nodeID that the UPF announces in PFCP -- must match scenario-a-cupf/smf.yaml.
UPFS = {
    "upf": ("free5gc-upf", "upf.free5gc.svc.cluster.local"),
}

GREEN, RED, YELLOW, GREY, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = GREY = RESET = ""

warns = []
PAUSE = False
CONCISE = False


# --------------------------------------------------------------------------
# infrastructure
# --------------------------------------------------------------------------
class Failure(Exception):
    """Error that interrupts the test. The message is ready for the user."""


class PermanentFailure(Failure):
    """Failure that REPEATING does not solve -- usage error, missing prerequisite,
    wrong configuration. The campaign retries because the testbed fails for
    transient reasons (the NF x NRF race, the SMF that was not answering yet); but
    insisting on a scenario that was not even applied only prints the same error twice
    and suggests, falsely, that there was something to redo."""


def step(n, title_, because=""):
    """Header of the stage. 'because' explains, at runtime, what this step does
    and why it exists -- to follow along without having to read the code."""
    print(f"\n{'='*72}\n[{n:02d}] {title_}\n{'='*72}")
    if because and not CONCISE:
        for paragraph in because.strip().split("\n\n"):
            for line in textwrap.wrap(" ".join(paragraph.split()), 68):
                print(f"  {GREY}# {line}{RESET}")
            print()


def ok(msg):
    print(f"  {GREEN}OK{RESET}   {msg}")


def info(msg):
    print(f"  {GREY}..{RESET}   {msg}")


def warning(msg, scope="general"):
    """scope='campaign' marks the warnings that invalidate the COMPARISON between the
    two paths. A placement warning, for example, is relevant but does not make
    the two measurements incomparable."""
    warns.append((scope, msg))
    print(f"  {YELLOW}WARN{RESET} {msg}")


def pause(next_=""):
    """Step-by-step mode: stops after each stage to give time to read."""
    global PAUSE
    if not PAUSE:
        return
    if not sys.stdin.isatty():
        return
    tgt = f" -> {next_}" if next_ else ""
    try:
        r = input(f"\n  {GREY}[enter] continues{tgt}   "
                  f"(c = goes on without pausing, q = aborts){RESET} ").strip().lower()
    except EOFError:
        return
    if r == "q":
        raise KeyboardInterrupt
    if r == "c":
        PAUSE = False


def run(cmd, check=True, timeout=120, quiet=False, cwd=None):
    if not quiet:
        print(f"  {GREY}$ {' '.join(cmd) if isinstance(cmd, list) else cmd}{RESET}")
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                       text=True, timeout=timeout, cwd=cwd)
    if check and r.returncode != 0:
        raise Failure(f"command failed ({r.returncode}): "
                    f"{' '.join(cmd) if isinstance(cmd, list) else cmd}\n"
                    f"       {r.stderr.strip() or r.stdout.strip()}")
    return r


def kubectl(*args, **kw):
    return run(["kubectl", "-n", NS, *args], **kw)


def kexec(pod, container, *cmd, **kw):
    return kubectl("exec", pod, "-c", container, "--", *cmd, **kw)


def _cluster_ip(svc):
    r = kubectl("get", "svc", svc, "-o", "jsonpath={.spec.clusterIP}", quiet=True)
    ip = r.stdout.strip()
    if not ip or ip == "None":
        raise Failure(f"service {svc} without a ClusterIP")
    return ip


def wait_for(desc_text, cond, timeout, interval=3):
    """Calls cond() until it becomes true. cond may return (ok, detail)."""
    t0 = time.time()
    last_one = ""
    while time.time() - t0 < timeout:
        r = cond()
        val, detail = r if isinstance(r, tuple) else (r, "")
        if val:
            return detail
        if detail and detail != last_one:
            info(f"{desc_text}: {detail}")
            last_one = detail
        time.sleep(interval)
    raise Failure(f"timeout ({timeout}s) waiting for: {desc_text}"
                + (f"\n       last state: {last_one}" if last_one else ""))


# --------------------------------------------------------------------------
# 01 tools
# --------------------------------------------------------------------------
def p01_tools():
    step(1, "Tools and connection to the cluster",
          """Checks kubectl, which context is active and which nodes exist. It is the
    first thing because, with the wrong context, everything else measures the wrong
    cluster without any sign of it.""")
    if not shutil.which("kubectl"):
        raise Failure("kubectl not found in the PATH")
    r = run(["kubectl", "config", "current-context"], check=False, quiet=True)
    if r.returncode != 0:
        raise Failure("kubectl without an active context (kubectl config current-context failed)")
    ok(f"context: {r.stdout.strip()}")

    r = run(["kubectl", "get", "nodes", "-o",
             "jsonpath={range .items[*]}{.metadata.name}{'\\t'}"
             "{.status.conditions[?(@.type=='Ready')].status}{'\\n'}{end}"], quiet=True)
    node_list = [l.split("\t") for l in r.stdout.strip().splitlines() if l.strip()]
    for name_str, ready in node_list:
        state = f"{GREEN}Ready{RESET}" if ready == "True" else f"{RED}NotReady{RESET}"
        print(f"       node {name_str:<20} {state}")
    ok(f"{len(node_list)} node(s) in the cluster")


# --------------------------------------------------------------------------
# 02 validate
# --------------------------------------------------------------------------
def p02_validate(args):
    step(2, "Static consistency of the manifests (validate.py)",
          """Parses the YAML embedded in the ConfigMaps and checks the rules that free5GC only
    applies at boot: version of each config, endpoint 0.0.0.0 in a field that becomes
    an F-TEID, UPF name that must match between smfcfg and ueRouting.

    It is worth running before applying because this class of error does not show up
    as an error: the NF comes up normally and the PDU session simply never completes.""")
    if args.skip_validate:
        info("skipped (--skip-validate)")
        return
    r = subprocess.run([sys.executable, "scripts/validate.py"], cwd=BASE,
                       capture_output=True, text=True)
    output = (r.stdout + r.stderr).strip()
    print("       " + output.replace("\n", "\n       "))
    if "ModuleNotFoundError" in output:
        raise Failure("missing dependency to run validate.py:\n"
                    "       pip install -r scripts/requirements.txt\n"
                    "       (or skip this stage with --skip-validate)")
    if r.returncode != 0:
        raise Failure("validate.py rejected the manifests; fix them before applying")
    ok("manifests consistent")


# --------------------------------------------------------------------------
# 03 deployment
# --------------------------------------------------------------------------
def p03_deploy(args):
    step(3, f"Deployment of Scenario A + load profile '{args.prof}'",
          """Calls deploy.py up a, which removes the user plane of Scenario B (otherwise
    an I-UPF and a PSA-UPF stay associated with the SMF and the proof of step 11
    measures the wrong topology), applies the common control plane, the central UPF,
    the MEC/remote services and the tester, and restarts the SMF so that it rereads
    the ConfigMaps.

    Then it APPLIES THE LOAD PROFILE to both vr-servers. This happens here, and not in
    the manifest, for two reasons: the manifest would have to be edited for each
    scenario (and committed wrongly with it), and in a campaign with --repetitions the
    deployment reapplies the YAML at each execution -- a 'kubectl set env' done before
    would be undone in the middle of the campaign, without warning, and half of the
    repetitions would measure another load.""")
    if args.deploy:
        r = subprocess.run([sys.executable, "deploy.py", "up", "a"], cwd=BASE, text=True)
        if r.returncode != 0:
            raise Failure("deploy.py up a failed")
        ok("scenario A applied")
    else:
        info("deployment skipped (use --deploy to bring the scenario up before the test)")
        # Without --deploy the scenario must ALREADY be running. If it is not, the
        # 'kubectl set env' right below fails with a "deployments.apps
        # <name> not found" that does not say what to do -- and in a campaign with
        # --repetitions this also becomes "attempt 1 of 2 failed" and a deployment
        # from zero that does not exist either. Better to stop here saying why.
        lacking = sorted(set(APPS_VR) - _existing_deploys())
        if lacking:
            raise PermanentFailure(
                "the scenario is not running: missing " + ", ".join(lacking) + ".\n"
                "       Bring it up before testing, in one of two ways:\n"
                "         python3 scripts/run_scenario_a.py --deploy ...\n"
                "         python3 deploy.py up a")
    _apply_profile(args)


def _expected_load(perf):
    """What vr_server WILL compute for this profile: it closes the frame in whole
    MTU packets, so the effective rate is almost never the round target
    (8 Mbps at 60 fps become 14 packets = 8.1 Mbps). Comparing the log with the TARGET
    would make every measurement look divergent; comparing with this value detects
    what matters -- the profile that did not take."""
    frame_bytes = perf["bitrate_mbps"] * 1e6 / 8.0 / perf["fps"]
    pkts = max(1, math.ceil(frame_bytes / perf["mtu"]))
    return pkts, pkts * perf["mtu"] * 8 * perf["fps"] / 1e6


def _active_pod(deploy):
    """Name of the pod that is ACTUALLY serving: Running and without deletionTimestamp,
    the most recent one if there is more than one.

    'kubectl logs deploy/X' picks any pod among those that exist, and during a
    rollout the old one is still there in Terminating. This is how a profile change
    went unnoticed: the rollout had finished, the new pod already served 8 Mbps,
    and the reading took the old pod still at 50 Mbps -- the script went on
    believing that the profile had not been applied."""
    r = kubectl("get", "pods", "-l", f"app={deploy}", "-o", "json",
                check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    try:
        pods = json.loads(r.stdout).get("items", [])
    except json.JSONDecodeError:
        return None
    alive_n = [p for p in pods
             if not p["metadata"].get("deletionTimestamp")
             and p["status"].get("phase") == "Running"]
    if not alive_n:
        return None
    alive_n.sort(key=lambda p: p["metadata"].get("creationTimestamp", ""))
    return alive_n[-1]["metadata"]["name"]


def _profile_from_log(deploy):
    """Reads, from the log of the vr-server that is serving, the load that IT computed.

    Checking the environment variable of the Deployment would not be enough: it says
    what was requested, not what is running."""
    pod = _active_pod(deploy)
    if not pod:
        return None
    r = kubectl("logs", pod, "-c", "vr-server", "--tail=40",
                check=False, quiet=True, timeout=60)
    m = re.search(r"downlink:\s*(\d+) pkt/frame x (\d+) B x (\d+) fps\s*=\s*([\d.]+) Mbps",
                  r.stdout)
    if not m:
        return None
    return {"pod": pod, "pkts": int(m.group(1)), "mtu": int(m.group(2)),
            "fps": int(m.group(3)), "mbps": float(m.group(4))}


def _apply_profile(args):
    """Puts the profile on both vr-servers and only goes on when BOTH confirm.

    The MEC x remote comparison only holds if the load is identical on both sides;
    a rollout that took on one and not on the other produces a table that looks good
    and is wrong."""
    perf = PROFILES[args.prof]
    info(f"{args.prof}: {perf['bitrate_mbps']} Mbps @ {perf['fps']} fps, "
         f"pose {perf['pose_hz']} Hz, MTU {perf['mtu']} B")
    for line in textwrap.wrap(perf["description"], 68):
        print(f"       {GREY}{line}{RESET}")

    target_pkts, target_mbps = _expected_load(perf)
    info(f"vr_server must close this in {target_pkts} packets per frame "
         f"= {target_mbps:.1f} effective Mbps")

    def _in_profile(v):
        """Compares with the load that the server MUST compute, not with the target."""
        return bool(v) and (v["pkts"], v["mtu"], v["fps"]) == (
            target_pkts, perf["mtu"], perf["fps"])

    for deploy in APPS_VR:
        if _in_profile(_profile_from_log(deploy)):
            info(f"{deploy} is already on the profile")
            continue
        kubectl("set", "env", f"deploy/{deploy}", "-c", "vr-server",
                f"VR_BITRATE_MBPS={perf['bitrate_mbps']}",
                f"VR_FPS={perf['fps']}", f"VR_MTU={perf['mtu']}",
                f"VR_PROFILE={args.prof}", quiet=True)
        run(["kubectl", "-n", NS, "rollout", "status", f"deploy/{deploy}",
             "--timeout=180s"], check=False, quiet=True, timeout=200)

    # wait_for() returns the DETAIL of the condition (the progress string), not the
    # value -- hence the result comes out through this dict, and not through the return.
    seen = {}

    # Waits for BOTH to reach the right load. The condition is the profile applied,
    # and not "the log answered": during the rollout the old pod still serves, and
    # accepting the first reading that came back would measure the previous profile.
    def cond():
        read_n, pending = {}, []
        for deploy in APPS_VR:
            v = _profile_from_log(deploy)
            if not v:
                pending.append(f"{deploy}: no active pod reporting a load")
            elif not _in_profile(v):
                pending.append(f"{deploy}: still at {v['mbps']:.1f} Mbps @ "
                                 f"{v['fps']} fps ({v['pod']})")
            else:
                read_n[deploy] = v
        if pending:
            return False, "; ".join(pending)
        seen.update(read_n)
        return True, ""

    try:
        wait_for("both vr-servers on the new profile", cond, 240)
    except Failure as e:
        raise Failure(
            f"the profile '{args.prof}' did not reach both vr-servers.\n"
            f"       {e}\n"
            "       Without both at the SAME load, the MEC x remote comparison does not "
            "measure the UPF, it measures the difference of load.") from None

    for deploy, v in seen.items():
        print(f"       {deploy:<22} {v['pkts']} pkt/frame x {v['mtu']} B x "
              f"{v['fps']} fps = {v['mbps']:.1f} Mbps  ({v['pod']})")
    ok(f"profile '{args.prof}' active and identical on both paths "
       f"({target_mbps:.1f} effective Mbps)")


# --------------------------------------------------------------------------
# 04 pods ready
# --------------------------------------------------------------------------
def _pending_pods():
    r = kubectl("get", "pods", "-o", "json", check=False, quiet=True)
    if r.returncode != 0:
        return None, f"namespace {NS} unreachable"
    pods = json.loads(r.stdout)["items"]
    bad = []
    for p in pods:
        name_str = p["metadata"]["name"]
        phase = p["status"]["phase"]
        if phase == "Succeeded":
            continue
        ready = all(c.get("ready") for c in p["status"].get("containerStatuses", [])) \
            and p["status"].get("containerStatuses")
        if phase != "Running" or not ready:
            reason = phase
            for c in p["status"].get("conditions", []):
                if c["type"] == "PodScheduled" and c["status"] != "True":
                    reason = f"{phase}/{c.get('reason')}: {c.get('message', '')[:90]}"
            for c in p["status"].get("containerStatuses", []):
                w = c.get("state", {}).get("waiting")
                if w:
                    reason = f"{phase}/{w.get('reason')}"
            bad.append((name_str, reason))
    return pods, bad


def _registered_at_nrf(deploy):
    """True if the NF confirmed registration at the NRF AFTER the last registration error,
    False if the last marker was an error, and None when IT CANNOT BE KNOWN.

    The third case was the missing one. The markers come out at the boot of the NF; in
    a pod that has been running for a long time they leave the window of 'logs --tail'
    -- and the SMF, which logs a couple of charging lines per session, buries its own
    boot in minutes. Before, no marker gave last_ok == last_error == -1, and
    '-1 > -1' is False: "not observed" was reported as "did not register", and the
    test aborted against a perfectly healthy scenario (this happened when running
    without --deploy against an SMF 11 min old, which was serving PDU sessions
    normally).

    Querying the NRF instead is not an option: NFDiscovery asks for an OAuth2 token
    when the core has oauth on, and a test that needs a credential to say whether
    the cluster is up trades one false negative for another."""
    r = kubectl("logs", f"deploy/{deploy}", "--tail=3000", check=False, quiet=True)
    if r.returncode != 0:
        return None
    clean_text = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    last_ok = last_error = -1
    for i, line in enumerate(clean_text.splitlines()):
        if OK_MARK in line:
            last_ok = i
        elif ERROR_MARK in line:
            last_error = i
    if last_ok == -1 and last_error == -1:
        return None
    return last_ok > last_error


def _existing_deploys():
    r = kubectl("get", "deploy", "-o",
                "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
                check=False, quiet=True)
    return set(r.stdout.split())


def p04_pods(args):
    step(4, "Pods of the control and user planes ready",
          """Checks that the deployments of Scenario A exist, that nothing is left of
    Scenario B, and that no pod is pending.

    A pod stuck in Pending is almost always a nodeSelector that no node satisfies --
    remember that the selector is an AND, so a hostname + nodetype that do not match
    each other give zero nodes. When it happens, the exact reason of the scheduler is
    printed here.

    It also checks that every SBI NF completed registration at the NRF. An NF that came
    up before the NRF could write to Mongo keeps an empty instance ID, stays Running
    and only breaks at the registration of the UE -- and there the symptom has no
    obvious relation to the cause.""")

    existing = _existing_deploys()
    lacking = [d for d in DEPLOYS if d not in existing]
    if lacking:
        raise Failure(
            "deployments of Scenario A missing in the namespace: "
            + ", ".join(lacking) + "\n"
            "       Bring the scenario up first: python3 deploy.py up a  "
            "(or run this test with --deploy)")
    residue = [d for d in DEPLOYS_SCENARIO_B if d in existing]
    if residue:
        raise Failure(
            f"{', '.join(residue)} (UPFs of Scenario B) still running together with A.\n"
            "       The SMF keeps an orphan UPF associated and the proof of step 11 measures the\n"
            "       wrong topology. Run: python3 deploy.py up a")
    ok(f"{len(DEPLOYS)} deployments of Scenario A present, no residue of B")

    def cond():
        pods, bad = _pending_pods()
        if pods is None:
            return False, bad
        # the tester has its own cycle (it may be restarting); step 8 takes care of it
        bad = [x for x in bad if not x[0].startswith(TESTER_STS)]
        if not bad:
            return True, ""
        return False, "; ".join(f"{n} [{m}]" for n, m in bad[:4])

    try:
        wait_for("pods prontos", cond, args.timeout)
    except Failure:
        _pending_pods_report()
        raise
    ok("all pods ready")

    state = {d: _registered_at_nrf(d) for d in NFS_SBI}
    lost_n = [d for d, v in state.items() if v is False]
    silent = [d for d, v in state.items() if v is None]
    if silent and not lost_n:
        # Inconclusive is NOT a failure: the marker only left the window of the log. What
        # really decides is step 9 -- without registration at the NRF the PDU session does not
        # complete, and there the error shows up with its cause.
        info("no registration marker in the log of " + ", ".join(silent)
             + " (pod running for too long); step 9 is the one that confirms")
    if lost_n:
        raise Failure(
            "these NFs did not confirm registration at the NRF: " + ", ".join(lost_n) + "\n"
            "       They came up before the NRF could write to MongoDB and\n"
            "       kept an EMPTY NF instance ID. Going on from here is useless:\n"
            "       the registration of the UE fails at step 9 with 'CONGESTION', and the real\n"
            "       cause only shows up in the log of the UDM, as\n"
            "       'Mandatory IE [ausfInstanceId/AmfInstanceId] is missing'.\n"
            "       Fix: kubectl -n " + NS + " rollout restart deploy/"
            + lost_n[0] + "\n"
            "       (or bring everything up again with deploy.py, which now respects the\n"
            "       dependency order and confirms the registration of each NF)")
    ok(f"{len(NFS_SBI)} NFs with registration confirmed at the NRF")


def _pending_pods_report():
    pods, bad = _pending_pods()
    if pods is None:
        return
    for name_str, reason in bad or []:
        print(f"       {RED}{name_str}{RESET}: {reason}")
        if "Unschedulable" in reason or "FailedScheduling" in reason:
            print(f"       {YELLOW}-> no node satisfies the nodeSelector of this pod. "
                  f"Adjust the hostname in the manifest or label the node.{RESET}")


# --------------------------------------------------------------------------
# 05 placement
# --------------------------------------------------------------------------
def _node_of(label):
    r = kubectl("get", "pod", "-l", f"epc-mode={label}", "-o",
                "jsonpath={.items[0].spec.nodeName}", check=False, quiet=True)
    return r.stdout.strip() or "?"


# Bits compared to decide whether two nodes are on the SAME network segment.
# 
# Checked in the cluster: the small edge machines are all in <edge-subnet> --
# brix-porvir-01 is <campus-ip>, -02 is .<host>, -03 is .<host> -- with a
# DIRECT route between them on enp3s0, 1 hop, without going through the gateway. The core
# (petshopboys .<host>, metallica .<host>) is in <core-subnet>, behind another
# gateway, 2 hops away. Comparing the first 22 bits separates exactly these two
# groups, and that is what "leaving the edge" means here: crossing the router.
# 
# If the testbed changes its IP range, this is the only number to adjust.
SEGMENT_PREFIX = 22


def _node_ip(node_name):
    if node_name in (None, "?", ""):
        return None
    r = kubectl("get", "node", node_name, "-o",
                "jsonpath={.status.addresses[?(@.type=='InternalIP')].address}",
                check=False, quiet=True)
    return r.stdout.strip() or None


def _same_segment(a, b):
    """True/False if nodes a and b are (or are not) on the same L2 segment.

    Returns None when the IP of one of them could not be found -- then the check is
    SKIPPED, instead of becoming a false warning. Placement is a manual decision: a
    wrong warning here costs more than the missing check."""
    ia, ib = _node_ip(a), _node_ip(b)
    if not ia or not ib:
        return None
    network = ipaddress.ip_network(f"{ia}/{SEGMENT_PREFIX}", strict=False)
    return ipaddress.ip_address(ib) in network


def _gtp5g_loaded(deploy):
    """Kernel modules are NOT namespaced: /proc/modules seen from inside any container
    is that of the HOST. The gtp5g of the node can be checked without SSH and without
    an extra privileged pod -- it is enough to read from inside the UPF itself."""
    r = kubectl("exec", f"deploy/{deploy}", "--", "grep", "gtp5g", "/proc/modules",
                check=False, quiet=True, timeout=60)
    line = next((l for l in r.stdout.splitlines() if l.startswith("gtp5g")), "")
    return bool(line), line


def p05_placement():
    step(5, "Actual placement of the pieces + gtp5g on the node of the central UPF",
          """Shows on which node each piece actually landed and checks gtp5g.

    The criterion is the design of the testbed in Scenario A: the centralized UPF is
    INSIDE the Server Node, together with the control plane, on the other side of the
    backhaul from the RAN. The tester and mec-app are at the edge, exactly where they
    are in Scenario B -- that is what gives a-mec the SAME destination as b-mec.

    gtp5g is a KERNEL module: the requirement is per NODE, not per pod, and without it
    the UPF pod comes up normally while the data plane never comes to exist.

    The placement warnings do not stop the test: they say whether the latency number
    is worth anything in the comparison with Scenario B.""")
    before_check = len(warns)
    n = {k: _node_of(k) for k in
         ("ueransim", "upf", "mec-app", "remote-app", "smf", "amf")}
    for node_role, node_name in n.items():
        print(f"       {node_role:<12} {node_name}")

    core = ("smf", "amf", "upf")
    if len({n[p] for p in core if n[p] != "?"}) > 1:
        warning("the pieces of the Server Node are on DIFFERENT nodes ("
              + ", ".join(f"{p}={n[p]}" for p in core) + "). In the design the "
              "control plane and the centralized UPF share the SAME box.")
    if _same_segment(n["upf"], n["ueransim"]) is True:
        warning(f"the central UPF ({n['upf']}) is on the EDGE segment, together with the "
              f"tester ({n['ueransim']}): there is no backhaul between the RAN and the anchor, "
              "and Scenario A is no longer the centralized baseline.")
    if _same_segment(n["upf"], n["mec-app"]) is True:
        warning(f"mec-app ({n['mec-app']}) on the same segment as the central UPF: the "
              "MEC traffic does not make the edge -> core -> edge trombone, and the "
              "comparison a-mec x b-mec loses its meaning.")
    elif _same_segment(n["ueransim"], n["mec-app"]) is False:
        warning(f"mec-app ({n['mec-app']}) outside the edge segment: it is not the "
              "same destination as b-mec.")
    if _same_segment(n["ueransim"], n["remote-app"]) is True:
        warning(f"remote-app ({n['remote-app']}) on the edge segment: the remote "
              "traffic does not cross the backhaul.")
    if n["remote-app"] != "?" and n["remote-app"] == n["upf"]:
        warning(f"remote-app on the same node as the central UPF ({n['upf']}): the remote "
              "path saves the N6 hop that it pays in Scenario B, and a-remote "
              "is no longer comparable to b-remote.")
    if len(warns) == before_check:
        ok(f"placement faithful to the design (Scenario A): central UPF on "
           f"{n['upf']}, MEC at the edge on {n['mec-app']}, tester on {n['ueransim']}")

    for node_role, (deploy, _) in UPFS.items():
        loaded, line = _gtp5g_loaded(deploy)
        if not loaded:
            raise Failure(
                f"gtp5g is NOT loaded on the node of the central UPF ({n[node_role]}).\n"
                "       The UPF pod comes up anyway and the data plane never "
                "exists -- the failure is silent.\n"
                f"       On node {n[node_role]}:\n"
                "         git clone https://github.com/free5gc/gtp5g.git\n"
                "         cd gtp5g && make && sudo make install && sudo modprobe gtp5g\n"
                "       Use a version of gtp5g that compiles on the kernel of the node "
                "(kernel 6.8 requires a recent gtp5g)")
        info(f"{node_role} @ {n[node_role]}: {line.split()[0]} loaded "
             f"({'OE' if '(OE)' in line else 'in-tree'})")
    ok("gtp5g present on the node of the central UPF")
    return n

# --------------------------------------------------------------------------
# 06 subscribers
# --------------------------------------------------------------------------
def p06_subscribers(args):
    step(6, "Subscribers in MongoDB",
          """Writes the subscribers. In free5GC each UE becomes eight documents spread over
    eight collections (authentication, provisioned data, policy) -- there is no single
    collection of subscribers as in Open5GS.

    If the registration of the UE fails at step 9, this is the first suspect.""")
    if not args.load_subscribers:
        info("skipped (use --load-subscribers N to populate Mongo). "
             "If the registration of the UE fails at step 9, suspect this first.")
        return
    try:
        import pymongo  # noqa: F401
    except ImportError:
        raise Failure("pymongo not installed -- needed to load subscribers.\n"
                    "       pip install -r scripts/requirements.txt")

    port_num = args.mongo_port
    info(f"opening port-forward svc/mongo {port_num}:27017")
    pf = subprocess.Popen(["kubectl", "-n", NS, "port-forward", "svc/mongo",
                           f"{port_num}:27017"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        if pf.poll() is not None:
            raise Failure(f"port-forward died -- is the local port {port_num} already in use?")
        r = subprocess.run(
            [sys.executable, "scripts/provision_subscribers.py", "--clean",
             "--qty", str(args.load_subscribers),
             "--url", f"mongodb://localhost:{port_num}/"],
            cwd=BASE, capture_output=True, text=True)
        print("       " + (r.stdout or r.stderr).strip().replace("\n", "\n       "))
        if r.returncode != 0:
            raise Failure("provision_subscribers.py failed")
    finally:
        pf.send_signal(signal.SIGTERM)
        pf.wait(timeout=10)
    ok(f"{args.load_subscribers} subscriber(s) loaded")


# --------------------------------------------------------------------------
# 07 PFCP
# --------------------------------------------------------------------------
def _pfcp_alive(deploy):
    """True if the UPF exchanged a PFCP heartbeat with the SMF in the last seconds.

    The PFCP association is a STATE, not a boot event -- and that is what the previous
    check got wrong. It looked for the nodeID of the UPF in the log of the SMF, but
    that record comes out once, at boot, and the SMF logs a couple of charging lines
    per session: after a few minutes of traffic the kubelet has already rotated the
    file and the boot is gone (measured: 48 thousand log lines, ZERO mentions of PFCP).
    No --tail recovers what is no longer there, and the test aborted with "timeout
    waiting for the PFCP association" against a core that was serving traffic at that
    very instant.

    The heartbeat, on the contrary, repeats every few seconds while the association
    exists -- it is the proof that it is alive NOW."""
    r = kubectl("logs", f"deploy/{deploy}", "--since=40s", check=False,
                quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    return bool(re.search(r"heartbeat", r.stdout, re.I))


def p07_pfcp(args):
    step(7, "PFCP association: the SMF must see the central UPF",
          """Waits for the SMF to complete the PFCP association with the centralized UPF.

    The proof is the PFCP HEARTBEAT that the UPF exchanges with the SMF: if it is
    happening now, the association is up now. The boot marker does not work -- it
    comes out once and the log rotates.

    If the SMF came up with the config of Scenario B, it looks for the I-UPF and the
    PSA-UPF, finds neither, and this step expires.""")
    deploy = UPFS["upf"][0]

    def cond():
        if _pfcp_alive(deploy):
            return True, ""
        return False, "PFCP heartbeat not seen yet"

    wait_for("PFCP association", cond, args.timeout)
    ok("central UPF associated with the SMF (PFCP heartbeat active)")

# --------------------------------------------------------------------------
# 08 tester
# --------------------------------------------------------------------------
def _ue_registered():
    """True/False according to the rm-state of the UE; None if it cannot even be asked."""
    r = kexec(TESTER_POD, "ue", "./nr-cli", IMSI_MAIN, "-e", "status",
              check=False, quiet=True, timeout=30)
    if r.returncode != 0:
        return None
    return "RM-REGISTERED" in r.stdout


def p08_tester(args):
    step(8, "Tester UERANSIM (gNB + UE)",
          """Checks that the tester is running and that the gNB completed NG Setup with the AMF.

    The number of UEs comes from the MANIFEST, not from scaling at runtime:
    'replicas' in the StatefulSet is how many pods come up and NUM_UE in the 'ue'
    container is how many IMSIs each pod registers. To change it, edit
    tester/ueransim.yaml and apply it again.

    If the UE is not registered, the pod is recreated here. Reason: the tester comes up
    with the deployment, before Mongo has subscribers; it gets 404 from the UDR and
    T3511 gives up at the 5th attempt. After that the UE stays still forever, even
    with the subscribers already loaded -- and the log only shows CONGESTION.""")
    r = kubectl("get", "statefulset", TESTER_STS, "-o",
                "jsonpath={.spec.replicas}{'\\t'}{.status.readyReplicas}",
                check=False, quiet=True)
    if r.returncode != 0:
        raise Failure(f"StatefulSet {TESTER_STS} does not exist in namespace {NS}")
    fields = (r.stdout + "\t").split("\t")
    wanted = int(fields[0] or 0)
    if wanted == 0:
        raise Failure(
            f"the StatefulSet {TESTER_STS} has replicas: 0.\n"
            "       The number of UEs is defined in the manifest, not by scaling:\n"
            "         1) edit 'replicas' in tester/ueransim.yaml (and NUM_UE in the\n"
            "            'ue' container, if you want more than one IMSI per pod);\n"
            "         2) kubectl apply -f tester/ueransim.yaml\n"
            "       In Scenario A there is no ULCL list: the IMSIs only need to be\n"
            "       provisioned in Mongo (--load-subscribers N).")
    info(f"replicas defined in the manifest: {wanted} "
         f"(the measurements use pod {TESTER_POD})")

    # The tester comes up with the deployment, BEFORE Mongo has subscribers. It
    # tries to register, gets 404 from the UDR, and T3511 gives up at the 5th attempt
    # (~45 s) -- after that the UE stays in ATTEMPTING-REGISTRATION forever,
    # even if the subscribers arrive right after. Recreating the pod is
    # what forces a new attempt now that step 6 has populated the database.
    if _ue_registered() is False:
        info("UE is not registered (it probably gave up before the "
             "subscribers existed); recreating the pod to try again")
        kubectl("delete", "pod", TESTER_POD, "--wait=false", check=False)
        time.sleep(5)

    def cond():
        r = kubectl("get", "pod", TESTER_POD, "-o", "json", check=False, quiet=True)
        if r.returncode != 0:
            return False, "pod not created yet"
        p = json.loads(r.stdout)
        cs = p["status"].get("containerStatuses", [])
        if cs and all(c.get("ready") for c in cs):
            return True, ""
        not_ready = [c["name"] for c in cs if not c.get("ready")] or ["(creating)"]
        return False, f"containers not ready: {not_ready}"

    wait_for("tester ready", cond, args.timeout)
    ok(f"{TESTER_POD} running (node {_node_of('ueransim')})")

    r = kubectl("logs", TESTER_POD, "-c", "gnb", "--tail=40", check=False, quiet=True)
    if "NG Setup procedure is successful" in r.stdout:
        ok("NG Setup with the AMF completed")
    else:
        warning("'NG Setup procedure is successful' not found in the log of the gNB; "
              "the registration may fail at the next step")

    _check_net_sysctl()


# Socket buffer floor so that the VR load does not lose frames due to a full queue.
# 4 MB comfortably covers a whole frame in a burst plus what arrives while
# Python processes the previous one.
RMEM_MIN = 4 << 20


def _check_net_sysctl():
    """How much SO_RCVBUF the kernel ACTUALLY grants to a UDP socket, on the THREE
    nodes the VR load goes through: that of the tester (client), that of mec-app and
    that of remote-app. With the ends spread over different machines, measuring only
    the tester would hide half of the problem.

    The question is about net.core.rmem_max/wmem_max, but it can NOT be asked by
    reading /proc/sys/net/core inside the pod: since these sysctls are global (they do
    not exist per network namespace), the container runtime simply does NOT expose
    the directory -- 'cat' returns "No such file or directory". Ironically, the
    absence itself confirms that they belong to the node.

    So the measurement is the effect, not the cause: it opens a socket, asks for 8 MB,
    and sees what came back. The kernel grants min(request, rmem_max) and DOUBLES the
    value, without warning of any cap -- asking for 8 MB and getting 416 KB is silent,
    and under high load the queue overflows, the kernel drops, and the loss shows up
    in the report as if it belonged to the UPF path."""
    # PROBE -- runs inside the pod and reports what the kernel of the NODE granted.
    PROBE = ("import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);"
             "s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,8<<20);"
             "s.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,8<<20);"
             "print(s.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF),"
             "s.getsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF))")

    # The THREE points where the VR load enters and leaves the kernel. Measuring only the tester
    # would leave out exactly the side that overflows first: remote-app
    # is in the core, where there is no sudo to raise the sysctl.
    points = [
        ("tester (vr_client)", lambda: kexec(TESTER_POD, "vr-client", "python3",
                                             "-c", PROBE, check=False,
                                             quiet=True, timeout=30)),
    ]
    for node_role, deploy in (("mec-app (vr_server)", "free5gc-mec-app"),
                          ("remote-app (vr_server)", "free5gc-remote-app")):
        points.append((node_role, lambda d=deploy: kubectl(
            "exec", f"deploy/{d}", "-c", "vr-server", "--", "python3", "-c",
            PROBE, check=False, quiet=True, timeout=30)))

    shorts = []
    for desc_text, probe in points:
        r = probe()
        try:
            rcv, snd = (int(x) for x in r.stdout.split())
        except ValueError:
            warning(f"could not measure the effective SO_RCVBUF on {desc_text}; "
                  "cannot tell whether the node will cut the buffers of the VR load.")
            continue
        node_name = _node_of({"tester (vr_client)": "ueransim",
                     "mec-app (vr_server)": "mec-app",
                     "remote-app (vr_server)": "remote-app"}[desc_text])
        smallest = min(rcv, snd)
        info(f"{desc_text:<22} @ {node_name:<16} rcvbuf={rcv // 1024} kB "
             f"sndbuf={snd // 1024} kB (requested 8192 kB)")
        if smallest < RMEM_MIN:
            shorts.append((desc_text, node_name, smallest))

    if not shorts:
        ok("socket buffers sized for the VR load at the three points")
        return

    # The asymmetry is worse than the absolute value: if one side has buffer and the other
    # does not, the loss becomes unequal between the paths and the guard of step 12 rejects
    # the execution -- what looks like a result of the scenario is the sysctl.
    detail = "\n".join(f"         {d} @ {node_name}: {v // 1024} kB"
                        for d, node_name, v in shorts)
    warning(f"socket buffer below the minimum ({RMEM_MIN // 1024} kB) at "
          f"{len(shorts)} of {len(points)} points:\n{detail}\n"
          "       What overflows the queue becomes 'loss' in the report without being loss "
          "at the UPF -- and if it\n       remains on one side only, the comparison between the paths "
          "reflects a difference of loss, not of path.\n"
          "       Run ON THE NODE (they are global sysctls; the container does not see them):\n"
          "         sudo sysctl -w net.core.rmem_max=16777216 "
          "net.core.wmem_max=16777216\n"
          "       To keep it after a reboot, write it to "
          "/etc/sysctl.d/99-tg2-vr.conf. On the core nodes (petshopboys, "
          "metallica),\n       where there is no sudo, the way out is to lower the load profile "
          "until both sides lose equally.")


# --------------------------------------------------------------------------
# 09 PDU session
# --------------------------------------------------------------------------
def p09_session(args):
    step(9, "PDU session: tunnel interface with an IP from the pool of the central UPF",
          """Waits for the tunnel interface of the UE to get an IP.

    In Scenario A the IP is allocated by the single UPF, so an address in 60.60.x.x
    already proves that the path gNB -> N3 -> central UPF is complete.""")

    def cond():
        r = kexec(TESTER_POD, "ue", "ip", "-4", "-o", "addr", "show", TUN,
                  check=False, quiet=True, timeout=30)
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
        if m:
            return True, m.group(1)
        return False, f"{TUN} still without IP"

    ue_ip = wait_for("PDU session", cond, args.timeout)
    if not ue_ip.startswith(UE_POOL_PREFIX):
        warning(f"IP of the UE {ue_ip} outside the expected pool {UE_POOL_PREFIX}0.0/16 -- "
              "check the UPF pools in scenario-a-cupf/smf.yaml")
    ok(f"{TUN} = {ue_ip}")
    return ue_ip

# --------------------------------------------------------------------------
# 10 routes
# --------------------------------------------------------------------------
def p10_routes():
    step(10, "Route of the destinations INSIDE the tunnel of the UE",
          """Sends both destinations through the tunnel interface.

    Without it the traffic leaves through eth0 of the pod, reaches the destination
    through the Kubernetes network and goes through no UPF -- the test would measure
    the cluster network and return excellent and meaningless numbers.""")
    global MEC_IP, REMOTE_IP
    MEC_IP, REMOTE_IP = _cluster_ip("mec-app"), _cluster_ip("remote-app")
    info(f"ClusterIPs: mec-app={MEC_IP} (dynamic; announced to the NEF by mec-af), "
         f"remote-app={REMOTE_IP}")

    # Without this the traffic leaves through eth0 of the pod, reaches the destination through the
    # Kubernetes network and goes THROUGH NO UPF -- the test would measure the cluster network.
    # 'replace' instead of 'add' so that the script can be rerun.
    for dest in (MEC_IP, REMOTE_IP):
        kexec(TESTER_POD, "ue", "ip", "route", "replace", f"{dest}/32",
              "dev", TUN, timeout=30)
    r = kexec(TESTER_POD, "ue", "ip", "route", "show", quiet=True, timeout=30)
    for line in r.stdout.splitlines():
        if MEC_IP in line or REMOTE_IP in line:
            print(f"       {line.strip()}")
    if TUN not in r.stdout:
        raise Failure(f"routes do not point to {TUN}")
    ok("mec-app and remote-app routed through the tunnel")


# --------------------------------------------------------------------------
# GTP counters
# --------------------------------------------------------------------------
def gtp_counters(deploy):
    """RX/TX (bytes, packets) of the gtp5g interface inside the UPF pod."""
    r = kubectl("exec", f"deploy/{deploy}", "--", "cat", "/proc/net/dev",
                check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        raise Failure(f"could not read /proc/net/dev in {deploy}: {r.stderr.strip()}")
    ifaces = {}
    for line in r.stdout.splitlines():
        m = re.match(r"\s*([^:]+):\s*(.*)$", line)
        if not m:
            continue
        fields = m.group(2).split()
        if len(fields) >= 10:
            ifaces[m.group(1).strip()] = {
                "rx_bytes": int(fields[0]), "rx_pkts": int(fields[1]),
                "tx_bytes": int(fields[8]), "tx_pkts": int(fields[9]),
            }
    if GTP_IF not in ifaces:
        raise Failure(f"interface '{GTP_IF}' does not exist in {deploy}. "
                    f"Interfaces vistas: {sorted(ifaces)}.\n"
                    "       Without it gtp5g did not create the data plane "
                    "(module loaded on the node? 'lsmod | grep gtp5g')")
    return ifaces[GTP_IF]


def tun_counters():
    """RX/TX of uesimtun0, the tunnel interface of the UE inside the tester pod.

    It closes a blind spot of the diagnosis: if the upfgtp of the central UPF does
    not count the traffic, the counter of the UPF alone does not distinguish "the UE
    stopped emitting" from "the UE emitted and the packet vanished before the UPF".
    The tx here is what the UE actually put in the tunnel."""
    r = kexec(TESTER_POD, "ue", "cat", "/proc/net/dev", check=False, quiet=True,
              timeout=30)
    for line in r.stdout.splitlines():
        m = re.match(r"\s*" + TUN + r":\s*(.*)$", line)
        if m:
            c = m.group(1).split()
            if len(c) >= 10:
                return {"rx_bytes": int(c[0]), "rx_pkts": int(c[1]),
                        "tx_bytes": int(c[8]), "tx_pkts": int(c[9])}
    return None


def delta(before, after):
    return {k: after[k] - before[k] for k in before}


def vr_client(target_ip, ue_ip, dur, label, warmup, csv=None, jsonf=None,
              timeout_extra=60, pose_hz=None):
    cmd = ["python3", "/opt/vr/vr_client.py",
           "--server", f"{target_ip}:{VR_PORT}", "--bind", ue_ip,
           "--duration", str(dur), "--warmup", str(warmup), "--label", label]
    # The pose is part of the PROFILE (the control loop of the use case), so it
    # comes as an argument and not from VR_POSE_HZ of the container -- otherwise changing
    # scenario would change the media and leave the uplink at the value of another case.
    if pose_hz:
        cmd += ["--pose-hz", str(pose_hz)]
    if csv:
        cmd += ["--csv", csv]
    if jsonf:
        cmd += ["--json", jsonf]
    r = kexec(TESTER_POD, "vr-client", *cmd, check=False,
              timeout=dur + timeout_extra)
    try:
        raw_value = r.stdout
        summ = json.loads(raw_value[raw_value.index("{"):raw_value.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        raise Failure(f"vr_client did not return JSON (rc={r.returncode}).\n"
                    f"       stdout: {r.stdout.strip()[:400]}\n"
                    f"       stderr: {r.stderr.strip()[:400]}")
    return summ


def server_metrics(deploy):
    """Reads /metrics of the vr-server AT ONCE and sums the series of each metric.

    A single 'kubectl exec' per reading: with one call per metric, the two readings
    (before and after the run) would stretch the window of the counters far beyond
    the run, and the rates derived from them would be diluted."""
    r = kubectl("exec", f"deploy/{deploy}", "-c", "vr-server", "--", "python3", "-c",
                "import urllib.request as u;"
                "print(u.urlopen('http://127.0.0.1:9101/metrics').read().decode())",
                check=False, quiet=True, timeout=60)
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


def _d(before, after, name_str):
    """Delta of a counter between two readings; None if one is missing."""
    if not before or not after or name_str not in before or name_str not in after:
        return None
    return after[name_str] - before[name_str]


def target_fps(deploy):
    """VR_FPS declared in the deployment; 90 is the default of vr_server."""
    r = kubectl("get", "deploy", deploy, "-o",
                "jsonpath={.spec.template.spec.containers[?(@.name=='vr-server')]"
                ".env[?(@.name=='VR_FPS')].value}", check=False, quiet=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 90.0




# --------------------------------------------------------------------------
# 11 proof of the central anchoring
# --------------------------------------------------------------------------
def p11_anchor_proof(ue_ip, args):
    step(11, "PROOF OF THE CENTRAL ANCHORING (the test that defines Scenario A)",
          """Generates traffic to mec-app and then to remote-app, reading the counter of
    the GTP interface of the central UPF before and after each run.

    It is the mirror of the proof of Scenario B. There, the PSA-UPF had to stay STILL
    under MEC traffic. Here there is NO breakout: the central UPF must count BOTH
    flows -- under traffic to mec-app it rises as much as under traffic to
    remote-app. The MEC packet crosses the backhaul to the core and comes back to the
    edge. This trombone is exactly what Scenario B eliminates.

    If the central UPF stays still under MEC traffic, some alternative path exists
    -- and it could only be a user plane of Scenario B still running.""")

    outcomes = {}
    for name_str, tgt in (("mec", MEC_IP), ("remote", REMOTE_IP)):
        before = {k: gtp_counters(d) for k, (d, _) in UPFS.items()}
        info(f"generating {args.proof_duration}s of traffic to {tgt} ({name_str})")
        summ = vr_client(tgt, ue_ip, args.proof_duration, f"proof-{name_str}",
                           warmup=1, pose_hz=PROFILES[args.prof]["pose_hz"])
        after = {k: gtp_counters(d) for k, (d, _) in UPFS.items()}
        d = {k: delta(before[k], after[k]) for k in before}
        outcomes[name_str] = {"delta": d, "frames": summ["frames_complete"],
                            "poses": summ.get("ul_packets_tx")}

        if not summ["frames_complete"]:
            raise Failure(
                f"no complete frame came back from {tgt}. The data plane is not "
                "passing.\n"
                "       Suspects, in this order: (a) route of the tunnel (step 10); "
                "(b) ip_forward=0 at the UPF;\n"
                "       (c) gtp5g missing on the node; (d) the target pod is not ready;\n"
                "       (e) the Traffic Influence rule of mec-af changed the session -- "
                f"kubectl -n {NS} logs deploy/free5gc-smf | grep -i influence")

        u = d["upf"]
        print(f"       {name_str:<7} upf       rx={u['rx_pkts']:>8} pkts / "
              f"{u['rx_bytes']/1e6:>8.2f} MB   "
              f"tx={u['tx_pkts']:>8} pkts / {u['tx_bytes']/1e6:>8.2f} MB")
        print()

    for name_str, tag in (("mec", "MEC traffic"), ("remote", "remote traffic")):
        rx = outcomes[name_str]["delta"]["upf"]["rx_pkts"]
        poses = outcomes[name_str]["poses"]
        if rx == 0:
            raise Failure(
                f"the central UPF stayed STILL under {tag}: the traffic did not go through it.\n"
                "       In Scenario A only this path exists. Suspects: a leftover "
                "free5gc-i-upf or free5gc-psa-upf of Scenario B,\n"
                "       or the SMF came up with the config of B (step 07 should have caught it).")
        if poses and rx < 0.9 * poses:
            raise Failure(
                f"the central UPF saw {rx} packets under {tag}, against {poses} poses "
                f"sent ({rx / poses * 100:.0f}%).\n"
                "       Part of the uplink went through another path or was lost before "
                "the anchor.")

    upf_mec = outcomes["mec"]["delta"]["upf"]["rx_pkts"]
    upf_remote = outcomes["remote"]["delta"]["upf"]["rx_pkts"]
    ok(f"CENTRAL ANCHORING CONFIRMED: the central UPF saw {upf_mec} pkts under "
       f"MEC traffic and {upf_remote} under remote traffic -- the edge traffic goes up "
       "to the core")
    return outcomes

# --------------------------------------------------------------------------
# 12 campaign
# --------------------------------------------------------------------------
# Measured paths. The ORDER in which they are measured alternates at each execution (see
# p12_campaign): always running mec-before-remote would make any drift along
# the execution (warm cache, thermal, a neighboring pod waking up) always fall
# on the same side, and it would appear in the table as a difference between the paths.
PATH_NAMES = (("a-mec", "mec", "free5gc-mec-app"),
            ("a-remote", "remote", "free5gc-remote-app"))

# Difference of loss between the two paths, in percentage points, above
# which the latency COMPARISON no longer holds. The reason is survivorship
# bias: only COMPLETE frames produce latency samples, so the path that loses more
# has its samples filtered exactly at the instants of a full queue -- and comes out
# with an artificially better latency. Comparing 0.1% with 4% of loss is not
# comparing two paths, it is comparing two different samples.
LOSS_DIFF_THRESHOLD_PP = 1.0

# Fraction of the requested window that must have had downlink. Below it the flow
# was interrupted, and neither the loss nor the throughput reveal it on their own.
CONTINUITY_THRESHOLD_PCT = 95.0

# Above this fraction of late frames the report comments that the pacing is
# tight. It does NOT invalidate the run: see the comment in _evaluate_measurement.
FRAMES_LATE_THRESHOLD_PCT = 1.0

# Drops due to a full queue (socket of the client or netns of the tester) that the run
# tolerates before it stops holding, in % of the received downlink. Below it the
# loss is residual and does not move the percentiles; above it, the measurement
# starts describing the measuring tool.
LOCAL_DROP_THRESHOLD_PCT = 0.5


def p12_campaign(ue_ip, args, idx=1):
    step(12, f"VR measurement campaign ({args.dur}s per path)",
          """Runs the real VR load against both destinations, with the same profile.

    Reports net_rtt (uplink out + downlink back -- the part that the placement of the
    UPF addresses) separately from m2p (motion-to-photon, what the user feels, which
    includes the wait for the next frame). Reporting only one of the two misleads:
    m2p alone dilutes the effect, net_rtt alone hides the experience.

    The order of the two paths ALTERNATES at each execution, so that no drift along
    the execution always falls on the same side.

    After measuring, it checks whether the run MEASURED THE NETWORK: whether the
    generator sustained the cadence, whether it managed to hand all packets to the
    kernel, whether the kernel of the client dropped nothing due to a full queue and
    whether both paths lost similar amounts. If any of them fails: the point is about
    the testbed, not about the UPF.""")
    if args.proof_only:
        info("skipped (--proof-only)")
        return {}

    # --path-names mec: the A x B campaign only compares the MEC path of both
    # scenarios, and the remote one would cost a whole run per execution without entering
    # the figure. The guard of loss between paths (_evaluate_pair) drops out by itself.
    measure = [c for c in PATH_NAMES
             if getattr(args, "paths", "all") == "all" or c[1] == "mec"]
    order = measure if idx % 2 else list(reversed(measure))
    info("order of this execution: " + " -> ".join(n for n, _, _ in order))
    ips = {"mec": MEC_IP, "remote": REMOTE_IP}   # resolved in step 10

    campaign = {}
    for pos, (name_str, key_name, deploy) in enumerate(order, 1):
        tgt = ips[key_name]
        m0 = server_metrics(deploy)
        # GTP counters of the central UPF also in the campaign, and not only in the proof
        # of step 11: if the uplink dies in the middle of the run, these deltas
        # separate "the UE stopped emitting" from "the UPF stopped receiving" from "the UPF
        # received and did not deliver to the server".
        g0 = {k: gtp_counters(d) for k, (d, _) in UPFS.items()}
        g0["ue-tun"] = tun_counters()
        info(f"{name_str}: {args.dur}s against {tgt}")
        summ = vr_client(tgt, ue_ip, args.dur, name_str, warmup=args.warmup,
                           csv=f"/data/{name_str}.csv", jsonf=f"/data/{name_str}.json",
                           pose_hz=PROFILES[args.prof]["pose_hz"])
        m1 = server_metrics(deploy)
        g1 = {k: gtp_counters(d) for k, (d, _) in UPFS.items()}
        g1["ue-tun"] = tun_counters()
        summ["_gtp"] = {k: delta(g0[k], g1[k])
                          for k in g0 if g0[k] and g1.get(k)}

        summ["_order"] = pos
        summ["_srv"] = srv = {
            k: _d(m0, m1, f"vr_server_{k}") for k in (
                "frames_sent_total", "frame_packets_total", "frames_late_total",
                "frames_truncated_total", "send_dropped_total",
                # The two that were missing when the downlink of the remote path
                # died in the middle of the first run on the edge machine. The server only
                # emits frames while the session exists, and the session dies after
                # --session-timeout without poses: comparing the poses that the client
                # SENT with those that the server RECEIVED tells, in one number, whether
                # what broke was the uplink.
                "pose_packets_total", "sessions_expired_total")
        }
        srv["pace_window_seconds"] = (m1 or {}).get("vr_server_pace_window_seconds")
        srv["sndbuf_bytes"] = (m1 or {}).get("vr_server_sock_sndbuf_bytes")

        # fps that the server REALLY emitted. frames_late alone is not enough:
        # a server may emit FEWER frames than it should and still declare itself
        # punctual, and then the measured latency is that of another load, not the configured one.
        # The divisor is the window of the uplink (when the session existed at the server),
        # and not the wall clock of the client, which includes the final draining.
        window = summ.get("ul_window_s") or summ["duration_s"]
        summ["_server_fps"] = (
            None if srv["frames_sent_total"] is None or not window
            else srv["frames_sent_total"] / window)
        # EXACT loss: denominator = packets that the server handed to the kernel.
        # That of the client is a floor, because a frame lost entirely does not enter the
        # sequence interval that it can observe.
        pk = srv["frame_packets_total"]
        summ["dl_packet_loss_srv_pct"] = (
            None if not pk else
            round(max(0.0, 1 - summ["dl_packets_rx_run"] / pk) * 100, 4))
        campaign[name_str] = summ
        _evaluate_measurement(name_str, deploy, summ, srv, args)

    _evaluate_pair(campaign)
    return campaign


def _evaluate_measurement(name_str, deploy, summ, srv, args):
    """Guards of ONE run. Each one answers 'is this measurement about the network?'."""
    net, m2p = summ["net_rtt_us"], summ["m2p_us"]
    health = summ.get("health", {})
    lost = summ.get("dl_packet_loss_srv_pct")
    if lost is None:
        lost = summ["dl_packet_loss_pct"]
    print(f"       net_rtt p50={num(net['p50'])} us  p95={num(net['p95'])} us"
          f" | m2p p50={num(m2p['p50'])} us"
          f" | hold p50={num(summ.get('hold_us', {}).get('p50'))} us"
          f" | loss={num(lost, 3)}%"
          f" | dl={num(summ['dl_throughput_mbps'], 2)} Mbps"
          f" | continuity={num(summ.get('dl_continuity_pct'), 1)}%")

    # Order of the points along the path, so that the line reads from the left
    # (UE) to the right (core).
    gtp = summ.get("_gtp") or {}
    if gtp:
        print("       path " + "   ".join(
            f"{k}: rx={gtp[k]['rx_pkts']} tx={gtp[k]['tx_pkts']}"
            for k in ("ue-tun", "upf") if k in gtp))

    # The poses that LEFT the client against those that REACHED the server. It is the
    # direct measurement of the uplink, and the only one that separates "the generator stopped" from "the
    # path stopped" -- the downlink loss does not see that.
    env, rec = summ.get("ul_packets_tx"), srv.get("pose_packets_total")
    if env and rec is not None and rec < 0.95 * env:
        warning(f"{name_str}: the server received {rec:.0f} of the {env} poses sent "
              f"({rec / env * 100:.0f}%). The UPLINK of this path did not deliver; "
              "compare the GTP counters to find the hop where it stopped.",
              scope="campaign")

    fps_target = target_fps(deploy)
    real = summ.get("_server_fps")
    if real is not None and real < 0.9 * fps_target:
        warning(f"{name_str}: the server emitted {real:.0f} fps against the "
              f"{fps_target:.0f} configured. The load that flowed is not the "
              "one requested, so the latency of this run is not "
              "comparable with that of the other path.", scope="campaign")

    # Continuity: the guard that was missing. A server that STOPS emitting leaves
    # no gap in the sequence, so the packet loss stays at zero and the
    # run goes unnoticed by all the other guards.
    cont = summ.get("dl_continuity_pct")
    if cont is not None and cont < CONTINUITY_THRESHOLD_PCT:
        j = summ.get("window", {})
        warning(f"{name_str}: the downlink existed in only {cont:.0f}% of the window "
              f"({j.get('span_s')} s of {j.get('nominal_s')} s requested) -- the flow "
              "was INTERRUPTED, it is not packet loss. See "
              "sessions_expired and pose_packets to tell whether "
              "the uplink failed.", scope="campaign")

    # Expired session = the server spent --session-timeout without receiving a pose.
    if srv.get("sessions_expired_total"):
        env = summ.get("ul_packets_tx")
        rec = srv.get("pose_packets_total")
        detail = ""
        if env and rec is not None:
            detail = (f" The client sent {env} poses and the server received "
                       f"{rec:.0f} ({rec / env * 100:.0f}%).")
        warning(f"{name_str}: the session expired {srv['sessions_expired_total']:.0f} time(s) "
              "at the server -- it received no pose for longer than "
              f"--session-timeout and stopped emitting frames.{detail} The problem "
              "is in the UPLINK of the path, not in the generator.", scope="campaign")

    if srv["frames_late_total"] is None:
        warning(f"{name_str}: could not read /metrics of {deploy}. Without it the "
              "discard rule does not apply -- it cannot be known whether the "
              "bottleneck was the Python generator or the network path.",
              scope="campaign")
    elif srv["frames_late_total"]:
        # frames_late counts the cycles in which tx_loop overran the period. With
        # the pacing taking 80% of the period this happens easily -- and it
        # does NOT mean that the load stopped flowing: the clock of the generator is
        # absolute, so a late cycle is compensated by the next one and the
        # mean rate holds.
        # 
        # Measured at 50 Mbps/90 fps: 371 late frames out of 5400 (6.9%) in a run
        # that delivered 90.0 fps, 50.10 Mbps, 100% continuity and 0.010%
        # loss. Invalidating that would throw away a good measurement.
        # 
        # What answers "did the configured load flow?" is the delivered fps, the
        # continuity and the loss -- all of them own guards above. Here there is only
        # the record, because the delay of the generator enters the hold (and leaves the
        # net_rtt in the subtraction) and is identical on both paths.
        sent = srv.get("frames_sent_total") or 0
        frac = srv["frames_late_total"] / sent * 100 if sent else 100.0
        msg = (f"{name_str}: {srv['frames_late_total']:.0f} late frames out of "
               f"{sent:.0f} ({frac:.2f}%)")
        if frac > FRAMES_LATE_THRESHOLD_PCT:
            info(msg + " -- the pacing is tight in this profile. It does not invalidate "
                 "the run (what decides that is the delivered fps, the continuity "
                 "and the loss); for more slack, lower VR_PACE_DUTY.")
        else:
            info(msg + " -- within the scheduling noise of the node.")

    # Packets that the SERVER never handed to the kernel: they are not network loss, and
    # without this guard they would enter the figure as if they were.
    if srv.get("send_dropped_total"):
        warning(f"{name_str}: vr-server could not queue "
              f"{srv['send_dropped_total']:.0f} packets (full sndbuf). The loss "
              "of this run was born in the generator, not on the UPF path.",
              scope="campaign")

    # Drops due to a full queue, of the socket of the client and of the netns of the tester. Both
    # enter as a FRACTION of the received packets, and not as "any value above
    # zero invalidates": at 50 Mbps there are ~313 thousand packets per run, and
    # 94 drops (0.03%) do not move any percentile -- discarding the execution
    # because of them threw away a good measurement. What really compromises the
    # comparison is MATERIAL loss, and even more material loss that is UNEQUAL between
    # the paths, which has its own guard in _evaluate_pair.
    received = summ.get("dl_packets_rx_run") or 0

    def _fraction(n):
        return (n / received * 100) if received else 100.0

    ovfl = health.get("dl_sock_drops")
    if ovfl is None:
        ovfl = health.get("dl_sock_overflow_pkts")
    if ovfl:
        f = _fraction(ovfl)
        msg = (f"{name_str}: the kernel of the client dropped {ovfl} packets due to a full queue "
               f"of the socket ({f:.3f}% of the downlink)")
        if f > LOCAL_DROP_THRESHOLD_PCT:
            warning(msg + ". The bottleneck is vr_client, not the network. Raise "
                  "net.core.rmem_max on the node or lower the load.", scope="campaign")
        else:
            info(msg + " -- residual; it does not invalidate the run.")
    if health.get("udp_rcvbuf_errors"):
        n = health["udp_rcvbuf_errors"]
        f = _fraction(n)
        msg = (f"{name_str}: {n} UDP buffer overflows in the namespace of the tester "
               f"({f:.3f}% of the downlink); since vr-client shares the netns with "
               "nr-gnb and nr-ue, it is loss INSIDE UERANSIM")
        if f > LOCAL_DROP_THRESHOLD_PCT:
            warning(msg + ". At this magnitude it distorts the percentiles: lower the "
                  "load or raise net.core.rmem_max on the node.", scope="campaign")
        else:
            info(msg + " -- residual; it does not invalidate the run.")

    hz = summ.get("ul_pose_hz_real")
    if hz is not None and hz < 0.9 * summ["pose_hz"]:
        warning(f"{name_str}: the pose uplink ran at {hz:.0f} Hz against the "
              f"{summ['pose_hz']:.0f} requested -- the client did not sustain its "
              "own sending, and the motion-to-photon delay is inflated by stale poses.",
              scope="campaign")

    if abs(health.get("clock_drift_us") or 0) > 1000:
        warning(f"{name_str}: CLOCK_REALTIME moved {health['clock_drift_us']:.0f} us "
              "beyond the monotonic clock during the run (NTP adjustment). The "
              "latency samples are shifted.", scope="campaign")

    if health.get("rx_timestamp_kernel") is False:
        warning(f"{name_str}: no kernel timestamp at the client. The reported "
              "latency includes the time vr_client spent off the CPU.")


def _evaluate_pair(campaign):
    """The guard that only makes sense with BOTH paths at hand."""
    a, b = campaign.get("a-mec"), campaign.get("a-remote")
    if not a or not b:
        return
    pa = a.get("dl_packet_loss_srv_pct")
    pb = b.get("dl_packet_loss_srv_pct")
    if pa is None or pb is None:
        pa, pb = a["dl_packet_loss_pct"], b["dl_packet_loss_pct"]
    if abs(pa - pb) > LOSS_DIFF_THRESHOLD_PP:
        warning(f"loss very different between the paths ({pa:.2f}% on the MEC path against "
              f"{pb:.2f}% on the remote path). Only COMPLETE frames become latency "
              "samples, so the path that loses more drops exactly the "
              "samples of the instants with a full queue and looks better than "
              "it is. The comparison of this execution does not hold.", scope="campaign")


# --------------------------------------------------------------------------
# 13 collection
# --------------------------------------------------------------------------
def p13_collect(args, campaign=None):
    step(13, "Collection of the results",
          """Brings the CSV (one line per frame) and the JSON summaries from inside the pod
    to the local machine, which is the input of the distribution plots.

    It also writes a full-summary.json with what the client does NOT know: the deltas
    of the counters of the server and the order in which the two paths ran. The JSON
    that the client itself writes inside the pod is written before that exists, so
    on its own it does not explain a discard.""")
    if args.proof_only:
        info("skipped (--proof-only)")
        return
    os.makedirs(args.output, exist_ok=True)
    # RELATIVE destination, from inside the folder: on Windows kubectl reads
    # "C:\Users\..." as <pod>:<path> and refuses the copy ("one of src or
    # dest must be a local file specification").
    r = run(["kubectl", "-n", NS, "cp", f"{TESTER_POD}:/data", ".",
             "-c", "vr-client"], check=False, timeout=180, cwd=args.output)
    if r.returncode != 0:
        warning(f"kubectl cp failed: {r.stderr.strip()[:200]}")
        return
    if campaign:
        with open(os.path.join(args.output, "full-summary.json"), "w", encoding="utf-8") as fh:
            json.dump(campaign, fh, indent=2)
    filenames = sorted(os.listdir(args.output))
    ok(f"{len(filenames)} file(s) in {args.output}: {', '.join(filenames)}")


# --------------------------------------------------------------------------
# 14 teardown
# --------------------------------------------------------------------------
def _scenario_pods():
    """Pods created by our Deployments/StatefulSet (prefix free5gc-)."""
    r = kubectl("get", "pods", "-o",
                "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
                check=False, quiet=True)
    return [p for p in r.stdout.split() if p.startswith("free5gc-")]


def teardown(args):
    """Deletes the Deployments and the StatefulSet of the scenario. THE NAMESPACE IS NOT TOUCHED.

    Removal is by NAME -- never 'kubectl delete -f file' and never '--all'. So there
    is no way to take along an object that is not ours: the free5gc namespace already
    exists in the cluster, does not belong to this experiment and cannot be recreated
    (the testbed account does not even have permission for that).

    Services, ConfigMaps and the PVC of Mongo stay up on purpose: they do not
    influence the measurement, and keeping the PVC keeps the subscribers loaded
    between one execution and the next."""
    step(14, "Tearing down the scenario (deployments and statefulset)",
          """Each repetition of the campaign must start from zero. Without tearing down, the
    next execution would measure a core that has been up for a long time, with warm
    caches and old sessions -- and the repetitions would no longer be independent.

    Only the Deployments and the StatefulSet go, and always by name. Services,
    ConfigMaps and the PVC of Mongo stay; the namespace is never touched.""")
    targets = DEPLOYS + DEPLOYS_SCENARIO_B
    kubectl("delete", "deploy", *targets, "--ignore-not-found=true",
            "--wait=false", check=False, quiet=True)
    kubectl("delete", "statefulset", TESTER_STS, "--ignore-not-found=true",
            "--wait=false", check=False, quiet=True)

    def cond():
        remaining = _scenario_pods()
        if not remaining:
            return True, ""
        return False, f"{len(remaining)} pod(s) still terminating"

    try:
        wait_for("pods to terminate", cond, args.teardown_timeout, interval=5)
        ok("deployments and statefulset removed; namespace preserved")
    except Failure:
        warning("not all pods terminated in time; the next execution may "
              "start with residue from the previous one")


# --------------------------------------------------------------------------
# report of ONE execution
# --------------------------------------------------------------------------
def num(v, decimals=1):
    """Rounds for the table. Without it a p95 like 20402.41999999998 overflows
    the width of the column and sticks to the next number."""
    return "-" if v is None else f"{v:.{decimals}f}"


def execution_summary(res):
    """Compact summary of an execution -- in a campaign of 10 the full report per
    execution would flood the terminal."""
    proof = res["proof"]
    upf_mec = proof["mec"]["delta"]["upf"]["rx_pkts"]
    upf_remote = proof["remote"]["delta"]["upf"]["rx_pkts"]
    print(f"\n  Proof of the central anchoring: UPF saw {upf_mec} pkts under MEC traffic "
          f"and {upf_remote} under remote traffic")

    c = res["campaign"]
    if not c:
        return
    print(f"    {'path':<12}{'net p50':>11}{'net p95':>11}{'m2p p50':>11}"
          f"{'hold p50':>11}{'loss %':>9}{'cont %':>8}{'Mbps':>8}{'fps':>6}{'drops':>7}")
    for name_str in ("a-mec", "a-remote"):
        s = c.get(name_str)
        if not s:
            continue
        lost = s.get("dl_packet_loss_srv_pct")
        if lost is None:
            lost = s["dl_packet_loss_pct"]
        sa = s.get("health", {})
        ovfl = sa.get("dl_sock_drops")
        if ovfl is None:
            ovfl = sa.get("dl_sock_overflow_pkts")
        print(f"    {name_str:<12}{num(s['net_rtt_us']['p50']):>11}"
              f"{num(s['net_rtt_us']['p95']):>11}{num(s['m2p_us']['p50']):>11}"
              f"{num(s.get('hold_us', {}).get('p50')):>11}"
              f"{num(lost, 2):>9}"
              f"{num(s.get('dl_continuity_pct'), 1):>8}"
              f"{num(s['dl_throughput_mbps'], 2):>8}"
              f"{num(s.get('_server_fps'), 0):>6}"
              f"{('-' if ovfl is None else ovfl):>7}")
    mec = c.get("a-mec", {}).get("net_rtt_us", {}).get("p50")
    rem = c.get("a-remote", {}).get("net_rtt_us", {}).get("p50")


# --------------------------------------------------------------------------
# aggregation of the campaign
# --------------------------------------------------------------------------
# (label, path inside the vr_client summary, divisor, unit, decimals,
#  lower_is_better). lower_is_better=None marks the line as informative: it makes
# no sense to talk about a "gain" of throughput, which by construction is equal on both sides.
KPIS = [
    ("Network delay (mean)",   ("net_rtt_us", "mean"), 1000.0, "ms", 3, True),
    ("Network delay p50",       ("net_rtt_us", "p50"),  1000.0, "ms", 3, True),
    ("Network delay p95",       ("net_rtt_us", "p95"),  1000.0, "ms", 3, True),
    ("Network delay p99",       ("net_rtt_us", "p99"),  1000.0, "ms", 3, True),
    ("Motion-to-photon (mean)", ("m2p_us", "mean"),     1000.0, "ms", 3, True),
    ("Motion-to-photon p50",     ("m2p_us", "p50"),      1000.0, "ms", 3, True),
    ("Motion-to-photon p95",     ("m2p_us", "p95"),      1000.0, "ms", 3, True),
    ("Network jitter",           ("jitter_net_us",),        1.0, "us", 1, True),
    ("Jitter motion-to-photon",  ("jitter_us",),            1.0, "us", 1, True),
    # Time INSIDE the server. It is not a network KPI: it enters the table so that the
    # reader can check that m2p = net + hold and see how much of the m2p is the pacing window
    # of the generator (identical on both sides) and not the path.
    ("Time in the server p50",    ("hold_us", "p50"),     1000.0, "ms", 3, None),
    ("DL packet loss",      ("dl_packet_loss_srv_pct",), 1.0, "%",  3, True),
    ("DL continuity",       ("dl_continuity_pct",),      1.0, "%",  2, None),
    ("Incomplete frames",       ("frames_incomplete_pct",),  1.0, "%",  3, True),
    ("DL throughput",                 ("dl_throughput_mbps",),   1.0, "Mbps", 2, None),
]


def _value(summ, path_name):
    v = summ
    for key_name in path_name:
        if not isinstance(v, dict):
            return None
        v = v.get(key_name)
    return v if isinstance(v, (int, float)) else None


def _mean_sd(value_list):
    """Mean and sample standard deviation. With a single execution the sd is 0 -- which
    is honest: there is no measured dispersion, there is no dispersion to report."""
    vs = [v for v in value_list if v is not None]
    if not vs:
        return None, None
    mean = sum(vs) / len(vs)
    if len(vs) < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in vs) / (len(vs) - 1)
    return mean, var ** 0.5


def kpi_lines(executions):
    """One line per KPI: (label, (mec, sd), (remote, sd), gain, unit, decimals).

    The gain is PAIRED: the difference is computed WITHIN each execution and only
    then aggregated (mean +- sd of the differences). The two runs of an execution see
    the same cluster, in the same state, minutes apart -- so the variation that exists
    BETWEEN executions (new deployment, pods elsewhere in the scheduler queue) is
    common to both and cancels in the subtraction. Subtracting means of different
    executions would put that whole variation inside the error bar of the gain, and a
    real effect of hundreds of microseconds could vanish inside it."""
    lines = []
    for tag, path_name, div, unit, decimals, lower_is_better in KPIS:
        cell = {}
        for which_side in ("a-mec", "a-remote"):
            vs = [_value(e["campaign"].get(which_side, {}), path_name) for e in executions]
            m, std = _mean_sd(vs)
            cell[which_side] = (None if m is None else m / div,
                         None if std is None else std / div)
        gain = None
        if lower_is_better:
            diffs, pcts = [], []
            for e in executions:
                mec = _value(e["campaign"].get("a-mec", {}), path_name)
                rem = _value(e["campaign"].get("a-remote", {}), path_name)
                if mec is None or not rem:
                    continue
                diffs.append((rem - mec) / div)
                pcts.append((1 - mec / rem) * 100)
            if diffs:
                md, dpd = _mean_sd(diffs)
                gain = (md, dpd, sum(pcts) / len(pcts), len(diffs))
        lines.append((tag, cell["a-mec"], cell["a-remote"], gain, unit, decimals))
    return lines


def kpi_table(executions):
    print(f"\n  KPIs of {len(executions)} execution(s) aggregated "
          f"-- mean +- standard deviation BETWEEN executions:\n")
    print(f"    {'KPI':<26}{'MEC via core':>21}{'Remote path':>21}")
    print(f"    {'-' * 26}{'-' * 21}{'-' * 21}")
    for tag, (m, mdp), (r, rdp), gain, un, c in kpi_lines(executions):
        cm = "-" if m is None else f"{m:.{c}f}+-{mdp:.{c}f} {un}"
        cr = "-" if r is None else f"{r:.{c}f}+-{rdp:.{c}f} {un}"
        print(f"    {tag:<26}{cm:>21}{cr:>21}")
    print(f"\n    {GREY}In Scenario A both paths go through the same central UPF. "
          f"The comparison with Scenario B comes from campaign.py.{RESET}")


EXEC_COLUMNS = [
    "scenario", "execution", "path", "order_in_execution",
    "net_mean_us", "net_p50_us", "net_p95_us",
    "net_p99_us", "net_min_us", "net_max_us", "m2p_mean_us", "m2p_p50_us",
    "m2p_p95_us", "m2p_p99_us", "hold_p50_us", "jitter_net_us", "jitter_m2p_us",
    "dl_loss_pct", "dl_loss_srv_pct", "dl_continuity_pct",
    "frames_incomplete_pct", "dl_mbps",
    "server_fps", "frames_complete", "frames_in_stats",
    # Health of the measurement: without these columns it cannot be defended, later, that the
    # line measured the network and not the measuring tool itself.
    "srv_frames_late", "srv_send_dropped", "srv_sessions_expired",
    "srv_pose_packets", "cli_sock_drops", "cli_sock_overflow",
    "cli_udp_rcvbuf_errors", "cli_ctxt_switches", "clock_drift_us",
    "ts_kernel", "pace_window_ms", "ul_pose_hz_real",
    "upf_rx_pkts", "campaign_warnings", "valid",
]
SIDES = (("a-mec", "mec"), ("a-remote", "remote"))


def _exec_line(res, which_side, proof_side, valid):
    s = res["campaign"].get(which_side, {})
    d = res["proof"][proof_side]["delta"]
    n_warn = len([1 for e, _ in res["warnings"] if e == "campaign"])
    srv = s.get("_srv") or {}
    pw = srv.get("pace_window_seconds")
    return [
        res.get("profile", ""), res["execution"], which_side, s.get("_order"),
        _value(s, ("net_rtt_us", "mean")), _value(s, ("net_rtt_us", "p50")),
        _value(s, ("net_rtt_us", "p95")), _value(s, ("net_rtt_us", "p99")),
        _value(s, ("net_rtt_us", "min")), _value(s, ("net_rtt_us", "max")),
        _value(s, ("m2p_us", "mean")), _value(s, ("m2p_us", "p50")),
        _value(s, ("m2p_us", "p95")), _value(s, ("m2p_us", "p99")),
        _value(s, ("hold_us", "p50")),
        _value(s, ("jitter_net_us",)), _value(s, ("jitter_us",)),
        _value(s, ("dl_packet_loss_pct",)), _value(s, ("dl_packet_loss_srv_pct",)),
        _value(s, ("dl_continuity_pct",)),
        _value(s, ("frames_incomplete_pct",)), _value(s, ("dl_throughput_mbps",)),
        _value(s, ("_server_fps",)), _value(s, ("frames_complete",)),
        _value(s, ("frames_in_stats",)),
        srv.get("frames_late_total"), srv.get("send_dropped_total"),
        srv.get("sessions_expired_total"), srv.get("pose_packets_total"),
        _value(s, ("health", "dl_sock_drops")),
        _value(s, ("health", "dl_sock_overflow_pkts")),
        _value(s, ("health", "udp_rcvbuf_errors")),
        _value(s, ("health", "ctxt_switches_involuntary")),
        _value(s, ("health", "clock_drift_us")),
        1 if s.get("health", {}).get("rx_timestamp_kernel") else 0,
        None if pw is None else round(pw * 1000, 3),
        _value(s, ("ul_pose_hz_real",)),
        d["upf"]["rx_pkts"], n_warn,
        1 if valid else 0,
    ]


def write_per_execution(path_name, executions, valid_n):
    """One line per (execution, path), with ALL executions -- including the discarded
    ones, marked with valid=0.

    It is the raw data file: filtering here would hide from the author himself what
    was left out. The analysis decides whether to use only the valid ones, and for
    that the column 'valid' is enough."""
    valid_ids = {id(e) for e in valid_n}
    with open(path_name, "w", encoding="utf-8") as fh:
        fh.write(",".join(EXEC_COLUMNS) + "\n")
        for res in executions:
            for which_side, proof_side in SIDES:
                if which_side not in res["campaign"]:
                    continue
                vals = _exec_line(res, which_side, proof_side, id(res) in valid_ids)
                fh.write(",".join("" if v is None else str(v) for v in vals) + "\n")


def write_aggregate(path_name, executions):
    with open(path_name, "w", encoding="utf-8") as fh:
        fh.write("kpi,unit,mec_mean,mec_sd,remote_mean,remote_sd,"
                 "paired_gain_mean,paired_gain_sd,gain_pct,"
                 "n_executions\n")
        for tag, (m, mdp), (r, rdp), gain, un, _ in kpi_lines(executions):
            g_abs = "" if gain is None else f"{gain[0]:.6f}"
            g_sd = "" if gain is None else f"{gain[1]:.6f}"
            g_pct = "" if gain is None else f"{gain[2]:.3f}"
            fh.write(f'"{tag}",{un},'
                     f'{"" if m is None else f"{m:.6f}"},'
                     f'{"" if mdp is None else f"{mdp:.6f}"},'
                     f'{"" if r is None else f"{r:.6f}"},'
                     f'{"" if rdp is None else f"{rdp:.6f}"},'
                     f'{g_abs},{g_sd},{g_pct},{len(executions)}\n')


def write_markdown(path_name, executions, discarded, args):
    n = len(executions)
    placement = executions[0].get("placement", {})
    with open(path_name, "w", encoding="utf-8") as fh:
        prof = getattr(args, "profile", DEFAULT_PROFILE)
        pf = PROFILES.get(prof, {})
        fh.write(f"# Scenario A - centralized UPF (baseline) - profile `{prof}`\n\n")
        if pf:
            fh.write(f"**Load:** {pf['bitrate_mbps']} Mbps @ {pf['fps']} fps "
                     f"per session (downlink), pose/control at {pf['pose_hz']} Hz "
                     f"(uplink), MTU {pf['mtu']} B.\n\n")
            fh.write(f"> {pf['description']}\n\n")
        fh.write(f"Campaign of **{n} independent execution(s)**. Each execution "
                 "brings the scenario up from zero, measures and tears down the deployments before the "
                 "next one.\n\n")
        fh.write(f"- Duration per path: {args.dur:g} s "
                 f"(the first {args.warmup:g} s discarded)\n")
        fh.write("- Load: VR application (downlink of frames + uplink of poses), "
                 "identical on both paths\n")
        if placement:
            fh.write("- Placement: "
                     + ", ".join(f"{k}={v}" for k, v in placement.items()) + "\n")
        if discarded:
            fh.write(f"- **{discarded} execution(s) discarded** due to a "
                     "campaign warning (the two runs were not equivalent)\n")
        fh.write("\nValues: mean +- standard deviation across the executions.\n\n")

        fh.write("| KPI | MEC via core | Remote path |\n")
        fh.write("|---|---|---|\n")
        for tag, (m, mdp), (r, rdp), gain, un, c in kpi_lines(executions):
            cm = "-" if m is None else f"{m:.{c}f} ± {mdp:.{c}f} {un}"
            cr = "-" if r is None else f"{r:.{c}f} ± {rdp:.{c}f} {un}"
            fh.write(f"| {tag} | {cm} | {cr} |\n")
        fh.write("\nIn Scenario A both paths go through the same central UPF. "
                 "The comparison with Scenario B (a-mec x b-mec) comes from "
                 "`campaign.py`.\n")

        fh.write("\n## Proof of the central anchoring\n\n")
        fh.write("Packets received on the GTP interface of the central UPF during the "
                 "traffic of each path. In Scenario A there is no breakout: the "
                 "central UPF counts BOTH flows, including that of MEC, which goes up to the "
                 "core and comes back to the edge.\n\n")
        fh.write("| Execution | Central UPF (MEC) | Central UPF (remote) |\n"
                 "|---|---|---|\n")
        for res in executions:
            d = res["proof"]
            fh.write(f"| {res['execution']} "
                     f"| {d['mec']['delta']['upf']['rx_pkts']} "
                     f"| {d['remote']['delta']['upf']['rx_pkts']} |\n")
        fh.write("\nThe two columns moving together = all traffic anchored in the "
                 "core. It is the baseline against which Scenario B is "
                 "compared (a-mec x b-mec: same destination, anchor elsewhere"
                 ").\n\n")
        fh.write("## How to read the two latency blocks\n\n")
        fh.write("The **network delay** is the uplink out plus the downlink back: "
                 "the part that the placement of the UPF actually addresses. The "
                 "**motion-to-photon** delay also includes the **time in the "
                 "server** (the wait for the next render instant plus the "
                 "window in which the generator spreads the packets of the frame). The "
                 "identity `m2p = network delay + time in the server` holds, and the "
                 "table shows all three precisely so that it can be "
                 "checked. Reporting only one of the two misleads: m2p alone "
                 "dilutes the effect of the UPF placement, the network delay alone hides "
                 "what the user feels.\n\n")
        fh.write("The time in the server is equal on both paths by construction "
                 "(same profile, same code, same pacing window): it "
                 "shifts the m2p of both sides by the same amount and neither creates nor "
                 "hides a difference between them.\n\n")

        fh.write("## What validates each measurement\n\n")
        fh.write("A run only enters the table if it measured the NETWORK, and not the "
                 "measuring tool itself. The columns of `summary-per-execution.csv` that "
                 "support this:\n\n")
        fh.write("- `srv_frames_late` / `srv_send_dropped`: the generator did not "
                 "sustain the cadence, or could not hand the packets to the "
                 "kernel. Loss born in the server, not on the path.\n")
        fh.write("- `cli_sock_overflow` (SO_RXQ_OVFL): packets that ARRIVED and the "
                 "kernel of the client dropped due to a full queue. It is loss of the "
                 "client; it cannot be read as loss of the UPF.\n")
        fh.write("- `cli_udp_rcvbuf_errors`: UDP buffer overflow in the namespace "
                 "of the tester, which vr-client shares with nr-gnb and nr-ue -- "
                 "it points to loss inside UERANSIM itself.\n")
        fh.write("- `dl_loss_srv_pct`: loss with the denominator coming from the "
                 "counter of the server (packets actually handed to the kernel), and "
                 "not from the sequence interval that the client observed, which "
                 "does not see a frame lost entirely at the edges.\n")
        fh.write("- `ts_kernel`: 1 when the timestamps came from the kernel "
                 "(SO_TIMESTAMPNS). With 0, the reported latency also carries the "
                 "time the processes spent off the CPU.\n")
        fh.write("- `frames_incomplete_pct`: only COMPLETE frames become latency "
                 "samples. If the two paths lose very "
                 "different amounts, the percentiles are not comparable -- the one that loses "
                 "more drops the samples of the bad instants and looks better "
                 "than it is. Such executions leave the table.\n")


def campaign_report(executions, failures, args):
    prof = getattr(args, "profile", DEFAULT_PROFILE)
    pf = PROFILES.get(prof, {})
    step(99, f"CAMPAIGN SUMMARY - profile '{prof}' "
              f"({pf.get('bitrate_mbps', '?')} Mbps @ {pf.get('fps', '?')} fps, "
              f"pose {pf.get('pose_hz', '?')} Hz)")

    valid_n = [e for e in executions
               if not [1 for sc, _ in e["warnings"] if sc == "campaign"]]
    valid_ids = {id(e) for e in valid_n}
    with_warning = len(executions) - len(valid_n)
    # The raw CSV always carries all executions. What the flag changes is only
    # which ones enter the mean of the table.
    all_ = getattr(args, "include_discarded", False)
    use_ = executions if all_ else valid_n
    outside = len(executions) - len(use_)

    extra = " (aggregated anyway: --include-discarded)" if all_ and with_warning else ""
    print(f"  {len(executions)} execution(s) completed, "
          f"{len(failures)} failure(s), {with_warning} with a campaign warning{extra}\n")

    print(f"    {'exec':<6}{'net p50 mec':>13}{'net p50 remote':>16}"
          f"{'UPF under MEC':>13}{'status':>16}")
    for e in executions:
        c = e["campaign"]
        mec = c.get("a-mec", {}).get("net_rtt_us", {}).get("p50")
        rem = c.get("a-remote", {}).get("net_rtt_us", {}).get("p50")
        psa = e["proof"]["mec"]["delta"]["upf"]["rx_pkts"]
        st = ("ok" if id(e) in valid_ids
              else ("warning (used)" if all_ else "discarded"))
        print(f"    {e['execution']:<6}{num(mec):>13}{num(rem):>16}"
              f"{psa:>13}{st:>16}")
    for i, msg in failures:
        print(f"    {i:<6}{RED}failed{RESET}: {msg.splitlines()[0][:60]}")

    # The RAW data always come out, and before any giving up. In the first
    # campaign on the edge machine both runs were discarded and this block came
    # after the 'return' -- the deltas of the server, the health and the CSV per execution
    # were lost exactly when they were the only way to find out
    # WHY they had been discarded.
    os.makedirs(args.output, exist_ok=True)
    p_exec = os.path.join(args.output, "summary-per-execution.csv")
    p_json = os.path.join(args.output, "run.json")
    write_per_execution(p_exec, executions, valid_n)
    with open(p_json, "w", encoding="utf-8") as fh:
        json.dump({"profile": getattr(args, "profile", None),
                   "workload": PROFILES.get(getattr(args, "profile", ""), {}),
                   "executions": executions, "failures": failures,
                   "duration_s": args.dur, "warmup_s": args.warmup,
                   "repetitions": args.repetitions}, fh, indent=2)

    if not use_:
        print(f"\n  {YELLOW}No valid execution to aggregate.{RESET} All of them "
              "had a campaign warning, that is, the two runs were not "
              "equivalent to each other.")
        print(f"  The raw data are in {args.output}: "
              f"{os.path.basename(p_exec)} and {os.path.basename(p_json)} -- the "
              "health columns say what invalidated each one.")
        return

    # With --proof-only there is no VR campaign: what is left is the proof of step 11, which was already
    # printed above. Building a KPI table of dashes only helps nobody.
    if not any(e["campaign"] for e in use_):
        print(f"\n  {GREY}--proof-only: no VR campaign, there are no KPIs to aggregate. "
              f"Raw data in {p_json}{RESET}")
        return

    kpi_table(use_)

    p_agg = os.path.join(args.output, "kpis-aggregated.csv")
    p_md = os.path.join(args.output, "kpi-table.md")
    write_aggregate(p_agg, use_)
    write_markdown(p_md, use_, outside, args)

    print(f"\n  Files in {args.output}:")
    for p in (p_md, p_exec, p_agg, p_json):
        print(f"    {os.path.basename(p)}")
    print(f"\n  The table ready for the text is in "
          f"{os.path.basename(p_md)}; the data per execution, in "
          f"{os.path.basename(p_exec)}.")

    if outside:
        warning(f"{outside} execution(s) were left out of the aggregation. They "
              "are in run.json, but do not enter the table: in them the "
              "generator did not sustain the configured load, so the two "
              "paths did not carry the same traffic.")


def _mean_gain(valid_n):
    """Mean paired gain of net_rtt p50, in us, among the valid executions."""
    diffs = []
    for e in valid_n:
        mec = _value(e["campaign"].get("a-mec", {}), ("net_rtt_us", "p50"))
        rem = _value(e["campaign"].get("a-remote", {}), ("net_rtt_us", "p50"))
        if mec is not None and rem:
            diffs.append((rem - mec, (1 - mec / rem) * 100))
    if not diffs:
        return None
    return (sum(d for d, _ in diffs) / len(diffs),
            sum(p for _, p in diffs) / len(diffs), len(diffs))


def _scenario_table(summ, root):
    """Closes the sweep showing the scenarios side by side.

    Lists, profile by profile, how many executions completed. The comparison with
    Scenario B comes from campaign.py. The number per scenario is already in the folder
    of each one; here they appear together."""
    print(f"\n{'=' * 72}\nMEASURED SCENARIOS\n{'=' * 72}\n")
    print(f"  {'scenario':<16}{'load':>16}{'exec':>6}{'failures':>8}")
    print(f"  {'-' * 16}{'-' * 16}{'-' * 6}{'-' * 8}")
    lines = []
    for prof, n_exec, n_failures, gain in summ:
        p = PROFILES[prof]
        workload = f"{p['bitrate_mbps']} Mbps/{p['fps']}fps"
        if gain is None:
            cell = "-"
            lines.append((prof, workload, n_exec, n_failures, "", "", ""))
        else:
            us, pct, n = gain
            cell = f"{us / 1000:.3f} ms ({pct:.1f}%)"
            lines.append((prof, workload, n_exec, n_failures,
                           f"{us / 1000:.4f}", f"{pct:.2f}", n))
        print(f"  {prof:<16}{workload:>16}{n_exec:>6}{n_failures:>8}")
    print(f"\n  {GREY}The comparison with Scenario B comes from campaign.py.{RESET}")

    os.makedirs(root, exist_ok=True)
    path_name = os.path.join(root, "scenarios.csv")
    with open(path_name, "w", encoding="utf-8") as fh:
        fh.write("scenario,bitrate_mbps,fps,pose_hz,executions,failures,"
                 "gain_net_p50_ms,gain_pct,valid_executions\n")
        for prof, workload, n_exec, n_failures, g_ms, g_pct, n_val in lines:
            p = PROFILES[prof]
            fh.write(f"{prof},{p['bitrate_mbps']},{p['fps']},{p['pose_hz']},"
                     f"{n_exec},{n_failures},{g_ms},{g_pct},{n_val}\n")
    print(f"\n  Comparison between scenarios: {path_name}")
    for prof, *_ in summ:
        print(f"    {os.path.join(root, prof)}/")


# --------------------------------------------------------------------------
# one complete execution
# --------------------------------------------------------------------------
def execute_once(args, idx, run_output, should_deploy):
    """Runs the whole experiment once and returns the record of the execution."""
    global warns
    warns = []

    args_run = argparse.Namespace(**vars(args))
    args_run.output = run_output
    args_run.deploy = should_deploy

    p03_deploy(args_run)
    pause("04 pods prontos")
    p04_pods(args_run)
    pause("05 placement + gtp5g")
    placement = p05_placement()
    pause("06 subscribers in Mongo")
    p06_subscribers(args_run)
    pause("07 PFCP association")
    p07_pfcp(args_run)
    pause("08 tester UERANSIM")
    p08_tester(args_run)
    pause("09 PDU session")
    ue_ip = p09_session(args_run)
    pause("10 tunnel route")
    p10_routes()
    pause("11 PROOF OF THE CENTRAL ANCHORING")
    proof = p11_anchor_proof(ue_ip, args_run)
    pause("12 VR campaign")
    campaign = p12_campaign(ue_ip, args_run, idx)
    pause("13 collection of the results")
    p13_collect(args_run, campaign)

    return {"execution": idx, "proof": proof, "campaign": campaign,
            "placement": placement, "warnings": list(warns),
            "output": run_output}


# --------------------------------------------------------------------------
def main():
    global NS, PAUSE, CONCISE
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attempts", type=int, default=2, metavar="N",
                    help="how many times to try each execution before counting it "
                         "as a failure. Each attempt redoes the scenario from zero, "
                         "so it serves for transient failures of the testbed (the race "
                         "NF x NRF, an SMF that was not answering yet). Use 1 so as "
                         "not to repeat (default: 2)")
    ap.add_argument("--repetitions", type=int, default=1, metavar="N",
                    help="how many times to repeat the whole experiment. With N>1 "
                         "each repetition brings the scenario up from zero, measures and tears down "
                         "the deployments before the next one (default: 1)")
    ap.add_argument("--deploy", action="store_true",
                    help="runs 'deploy.py up a' before the test (implicit when "
                         "--repetitions > 1)")
    ap.add_argument("--include-discarded", action="store_true",
                    help="aggregates ALL executions in the table, including those that "
                         "had a campaign warning (by default they stay only "
                         "in the raw CSV and in run.json)")
    ap.add_argument("--no-teardown", action="store_true",
                    help="does not delete the deployments at the end of each execution "
                         "(useful to inspect the scenario afterwards)")
    ap.add_argument("--teardown-timeout", type=int, default=300,
                    help="maximum wait (s) for the pods to terminate (default: 300)")
    ap.add_argument("--load-subscribers", type=int, default=0, metavar="N",
                    help="populates Mongo with N subscribers (via port-forward)")
    ap.add_argument("--duration", type=float, default=60,
                    help="seconds per run of the VR campaign (default: 60)")
    ap.add_argument("--warmup", type=float, default=5,
                    help="seconds dropped at the start of each run (default: 5)")
    ap.add_argument("--proof-duration", type=float, default=10,
                    help="seconds of traffic per path in the proof of the central anchoring (default: 10)")
    ap.add_argument("--path-names", choices=("all", "mec"), default="all",
                    help="paths measured in the campaign of step 12: 'all' (MEC and remote, "
                         "default) or only 'mec'. The proof of step 11 always uses both")
    ap.add_argument("--proof-only", action="store_true",
                    help="stops after the proof of the central anchoring, without a measurement campaign")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, metavar="NAME[,NAME...]",
                    help="load profile(s) to measure. Several separated by "
                         "commas run independent campaigns, one after the "
                         "other, each in its own folder. Available: "
                         + ", ".join(PROFILES) + f" (default: {DEFAULT_PROFILE})")
    ap.add_argument("--list-profiles", action="store_true",
                    help="shows the available profiles with the load of each one and exits")
    ap.add_argument("--output", default=os.path.join(BASE, "results-a"),
                    help="ROOT directory of the results; each profile gets a "
                         "subfolder with its own name, so campaigns of "
                         "different scenarios do not overwrite each other")
    ap.add_argument("--timeout", type=int, default=300,
                    help="timeout (s) of each wait (default: 300)")
    ap.add_argument("--mongo-port", type=int, default=27017)
    ap.add_argument("--namespace", default=NS)
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--step-by-step", "-p", action="store_true",
                    help="pauses after each step and waits for enter")
    ap.add_argument("--concise", action="store_true",
                    help="omits the explanatory comments of each step")
    args = ap.parse_args()
    NS = args.namespace
    PAUSE = args.step_by_step
    CONCISE = args.concise

    if args.list_profiles:
        print("\nAvailable load profiles:\n")
        for name_str, p in PROFILES.items():
            mark = "  (default)" if name_str == DEFAULT_PROFILE else ""
            print(f"  {name_str}{mark}")
            print(f"    {p['bitrate_mbps']} Mbps @ {p['fps']} fps  |  "
                  f"pose {p['pose_hz']} Hz  |  MTU {p['mtu']} B")
            for line in textwrap.wrap(p["description"], 68):
                print(f"      {line}")
            print()
        return 0

    if args.repetitions < 1:
        ap.error("--repetitions must be >= 1")
    if args.attempts < 1:
        ap.error("--attempts must be >= 1")
    profiles = [x.strip() for x in args.prof.split(",") if x.strip()]
    unknown = [x for x in profiles if x not in PROFILES]
    if unknown:
        ap.error("unknown profile: " + ", ".join(unknown)
                 + "\nAvailable: " + ", ".join(PROFILES)
                 + "\nUse --list-profiles to see the load of each one.")

    # A campaign with repetitions ALWAYS brings the scenario up. And we only tear down what
    # we brought up ourselves: running against a testbed that was already up must
    # not delete the deployments of whoever was using it.
    deploy_up = args.deploy or args.repetitions > 1
    teardown_at_end = deploy_up and not args.no_teardown

    t0 = time.time()
    try:
        p01_tools()
        pause("02 validate.py")
        p02_validate(args)
    except Failure as e:
        print(f"\n{RED}FAILED{RESET}: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    if len(profiles) > 1:
        print(f"\n{'#' * 72}\n# {len(profiles)} SCENARIOS: " + ", ".join(profiles)
              + f"\n# {args.repetitions} execution(s) each, "
              f"{args.dur:g}s per path\n{'#' * 72}")

    # One COMPLETE campaign per profile, each in its own folder. Running in series and
    # not interleaved is on purpose: interleaving scenarios would make the difference
    # between them also carry the drift of the cluster over the hours.
    overall_result = 0
    scenario_summary = []
    # initialized here too, and not only inside the loop of profiles:
    # the final summary reads this variable after the loop.
    interrupted = False
    for prof in profiles:
        args_p = argparse.Namespace(**vars(args))
        args_p.prof = prof
        # The folder carries the NAME OF THE SCENARIO: campaigns of different profiles
        # coexist without one deleting the other, and the name of the directory already says
        # which load produced those numbers.
        args_p.output = os.path.join(args.output, prof)

        if len(profiles) > 1:
            print(f"\n{'#' * 72}\n# SCENARIO: {prof}\n"
                  f"# {PROFILES[prof]['bitrate_mbps']} Mbps @ "
                  f"{PROFILES[prof]['fps']} fps, pose "
                  f"{PROFILES[prof]['pose_hz']} Hz -> {args_p.output}\n"
                  f"{'#' * 72}")
        elif args.repetitions > 1:
            print(f"\n{'#' * 72}\n# CAMPAIGN '{prof}': {args.repetitions} "
                  f"executions of {args.dur:g}s per path\n"
                  f"# each execution: deployment -> measurement -> collection -> teardown\n"
                  f"# results in {args_p.output}\n{'#' * 72}")

        executions, failures = [], []
        interrupted = False
        consecutive = 0    # consecutive failures; 3 of them = systemic problem
        for i in range(1, args.repetitions + 1):
            if args.repetitions > 1:
                print(f"\n{'#' * 72}\n# [{prof}] EXECUTION {i} of {args.repetitions}"
                      f"{'  (' + str(len(failures)) + ' failure(s) so far)' if failures else ''}"
                      f"\n{'#' * 72}")
            run_output = os.path.join(args_p.output, f"run-{i:02d}")
            res, err = None, None
            # An execution may fail for a transient reason of the testbed
            # itself -- the NF x NRF race, an SMF that was not answering yet
            # when the UE asked for the PDU session. In a long campaign, counting this
            # as a permanent failure would waste the ~19 min of deployment that
            # were just spent. Each attempt redoes the scenario from zero
            # (the teardown runs in finally), so the repetition does not inherit the
            # state that broke.
            permanent = False
            for att in range(1, args.attempts + 1):
                t_run = time.time()
                try:
                    res = execute_once(args_p, i, run_output, deploy_up)
                    res["seconds"] = round(time.time() - t_run, 1)
                    res["profile"] = prof
                    res["attempts"] = att
                    err = None
                except PermanentFailure as e:
                    err, permanent = str(e), True
                except Failure as e:
                    err = str(e)
                except Exception as e:                    # noqa: BLE001
                    # UNEXPECTED error (bug of the script, kubectl that vanished in
                    # the middle, malformed JSON). It goes with a traceback to the record.
                    err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                except KeyboardInterrupt:
                    print("\ninterrupted", file=sys.stderr)
                    interrupted = True
                finally:
                    if teardown_at_end:
                        try:
                            teardown(args_p)
                        except Exception as exc:          # noqa: BLE001
                            print(f"  {YELLOW}teardown failed: {exc}{RESET}",
                                  file=sys.stderr)
                if interrupted or err is None or permanent:
                    break
                if att < args.attempts:
                    print(f"\n{YELLOW}[{prof}] execution {i}: attempt {att} of "
                          f"{args.attempts} failed{RESET} ({err.splitlines()[0]})"
                          f"\n  redoing the scenario from zero...", file=sys.stderr)
            if interrupted:
                break

            if res is not None and err is None:
                executions.append(res)
                consecutive = 0
                execution_summary(res)
                extra = (f" (at attempt {res['attempts']})"
                         if res.get("attempts", 1) > 1 else "")
                print(f"\n  {GREEN}execution {i} completed{RESET}{extra} in "
                      f"{res['seconds']:.0f}s -> {run_output}")
            else:
                # 'tent', and not args.attempts: a PermanentFailure leaves at the
                # first one, and saying "after 2 attempts" would be false.
                print(f"\n{RED}[{prof}] EXECUTION {i} FAILED{RESET} after "
                      f"{att} attempt(s): {err}", file=sys.stderr)
                failures.append((i, err))
                consecutive += 1
            # In a long, unattended campaign, three consecutive failures are not
            # bad luck: it is something systemic (gtp5g missing, a node without CPU, an empty
            # database). Insisting only burns another hour of deployment to collect the
            # same error.
            if consecutive >= 3 and args.repetitions > 3:
                print(f"\n{RED}3 consecutive executions failed in '{prof}' -- "
                      f"aborting this scenario.{RESET}", file=sys.stderr)
                break

        if not executions:
            print(f"\n{RED}[{prof}] no execution completed.{RESET}",
                  file=sys.stderr)
            scenario_summary.append((prof, 0, len(failures), None))
            overall_result = 1
        else:
            campaign_report(executions, failures, args_p)
            valid_n = [e for e in executions
                       if not [1 for sc, _ in e["warnings"] if sc == "campaign"]]
            scenario_summary.append((prof, len(executions), len(failures),
                                    _mean_gain(valid_n)))
            if failures:
                overall_result = 1
        if interrupted:
            overall_result = 130
            break

    if len(profiles) > 1:
        _scenario_table(scenario_summary, args.output)

    # The final line must tell the TRUTH. It once came out green with zero
    # completed executions -- the exit code was right (1), but whoever reads
    # the terminal sees "VALIDATED" and believes it. In a long, unattended campaign
    # it is the difference between repeating the test and writing the analysis on nothing.
    completed = sum(c for _, c, _, _ in scenario_summary)
    total_failures = sum(f for _, _, f, _ in scenario_summary)
    elapsed = f"{time.time() - t0:.0f}s"
    if interrupted:
        print(f"\n{YELLOW}SCENARIO A INTERRUPTED{RESET} -- {completed} execution(s) "
              f"completed in {elapsed}")
    elif completed == 0:
        print(f"\n{RED}SCENARIO A NOT VALIDATED{RESET} -- no execution completed "
              f"({total_failures} failure(s)) in {elapsed}")
    elif total_failures:
        print(f"\n{YELLOW}SCENARIO A VALIDATED WITH FAILURES{RESET} -- {completed} "
              f"execution(s) completed, {total_failures} failure(s), "
              f"{len(profiles)} scenario(s) in {elapsed}")
    else:
        print(f"\n{GREEN}SCENARIO A VALIDATED{RESET} -- {completed} execution(s) "
              f"in {len(profiles)} scenario(s), {elapsed}")
    return overall_result


if __name__ == "__main__":
    sys.exit(main())
