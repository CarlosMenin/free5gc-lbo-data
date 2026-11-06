#!/usr/bin/env python3
"""
Brings the free5GC v4.2.3 testbed up or down in one of the two scenarios.

    python3 deploy.py up a       # Scenario A: centralized UPF (baseline)
    python3 deploy.py up b       # Scenario B: dUPF at the edge with ULCL/LBO
    python3 deploy.py down       # removes everything from the namespace
    python3 deploy.py status     # quick view of the state

WHY THE ORDER MATTERS (learned the hard way)
--------------------------------------------
Applying all NFs at once and sleeping N seconds does NOT work, and it fails in
a way that only shows up much later:

  1. the NRF comes up and accepts connections in ~1 s, but only answers once
     MongoDB is ready -- it writes the NF profile to the database;
  2. the other NFs come up at the same time, call the NRF and get 'context
     deadline exceeded' (not 'connection refused' -- the socket opens);
  3. the NF that loses this race keeps an EMPTY NF instance ID;
  4. the registration of the UE fails much later, in a place with no obvious
     relation to it:
        AUSF without ID -> UDM: "Mandatory IE [ausfInstanceId] is missing"
        AMF  without ID -> UDM: "Mandatory IE [AmfInstanceId] is missing"
     and the UE only sees "Initial Registration failed [CONGESTION]".

Hence each NF is applied in dependency order, and the next one starts only
after it CONFIRMS registration at the NRF -- the universal marker is the line
"OAuth2 setting receive from NRF:", which every NF prints exactly when the NRF
answers. If the registration does not complete, the NF is restarted once
before giving up, which is the manual fix for this state.
"""
import argparse
import re
import subprocess
import sys
import time

NS = "free5gc"

# Dependency order of the control plane. Do not reorder without a reason:
#   mongo  <- NRF (writes profiles) and webui (subscribers)
#   NRF    <- all the others
#   UDR    <- UDM;  UDM <- AUSF/AMF/SMF;  NSSF/PCF <- AMF/SMF
#   NEF    after UDR and PCF (consumes both); only mec-af depends on it
#   AMF    last among the signaling NFs (consumes almost all of them)
COMMON_CHAIN = [
    ("common/mongo.yaml", "free5gc-mongodb"),
    ("common/nrf.yaml", "free5gc-nrf"),
    ("common/udr.yaml", "free5gc-udr"),
    ("common/udm.yaml", "free5gc-udm"),
    ("common/ausf.yaml", "free5gc-ausf"),
    ("common/nssf.yaml", "free5gc-nssf"),
    ("common/pcf.yaml", "free5gc-pcf"),
    ("common/nef.yaml", "free5gc-nef"),
    ("common/amf.yaml", "free5gc-amf"),
    ("common/webui.yaml", "free5gc-webui"),
]

# UPFs first, SMF after: the SMF opens the PFCP association, so it
# finds the UPFs already up instead of depending on retransmission.
SCENARIOS = {
    "a": [("scenario-a-cupf/upf.yaml", "free5gc-upf"),
          ("scenario-a-cupf/smf.yaml", "free5gc-smf")],
    "b": [("scenario-b-dupf/i-upf.yaml", "free5gc-i-upf"),
          ("scenario-b-dupf/psa-upf.yaml", "free5gc-psa-upf"),
          ("scenario-b-dupf/smf.yaml", "free5gc-smf")],
}

# mec-service.yaml appears twice on purpose: it contains TWO
# deployments (mec-app and remote-app) and bring_up() waits for only one per entry.
# The repeated apply is idempotent. remote-app is the target of the b-remote
# measurement; without waiting for it, an Unschedulable pod would only show up
# at the end of the campaign.
# 
# mec-af after mec-service: it watches the Services with the label
# tg2.mec/lbo=true and announces the ClusterIP to the NEF (dynamic LBO). Before
# the tester only for clarity -- the rule also applies to sessions already open.
EXTRAS = [("mec/vr-app.yaml", None),
          ("mec/mec-service.yaml", "free5gc-mec-app"),
          ("mec/mec-service.yaml", "free5gc-remote-app"),
          ("mec/mec-af.yaml", "mec-af"),
          ("tester/ueransim.yaml", None)]

# NFs that speak SBI and therefore register at the NRF. The UPF is not one: it is not
# an SBI NF, it only speaks PFCP with the SMF.
REGISTER_AT_NRF = {
    "free5gc-udr", "free5gc-udm", "free5gc-ausf", "free5gc-nssf",
    "free5gc-pcf", "free5gc-nef", "free5gc-amf", "free5gc-smf", "free5gc-webui",
}

OK_MARK = "OAuth2 setting receive from NRF"
ERROR_MARK = "register to NRF Error"
NRF_READY = "SBI server started"

GREEN, RED, YELLOW, GREY, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = GREY = RESET = ""


def run(cmd, check=True, quiet=False, timeout=180):
    if not quiet:
        print(f"  {GREY}$ {cmd}{RESET}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.stdout.strip() and not quiet:
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0 and check and not quiet:
        print(f"    {RED}ERROR:{RESET} {r.stderr.strip()}", file=sys.stderr)
    return r


def strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def wait_rollout(deploy, timeout):
    r = run(f"kubectl -n {NS} rollout status deploy/{deploy} --timeout={timeout}s",
            check=False, quiet=True, timeout=timeout + 30)
    return r.returncode == 0


def registered_at_nrf(deploy):
    """True if the NF confirmed registration AFTER the last registration error.

    The order matters: an NF that failed, retried and succeeded is fine; one
    that only failed is not. Checking the presence/absence of the two markers
    does not distinguish the two cases."""
    r = run(f"kubectl -n {NS} logs deploy/{deploy} --tail=400",
            check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    last_ok = last_error = -1
    for i, line in enumerate(strip_ansi(r.stdout).splitlines()):
        if OK_MARK in line:
            last_ok = i
        elif ERROR_MARK in line:
            last_error = i
    return last_ok > last_error


def wait_registration(deploy, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if registered_at_nrf(deploy):
            return True
        time.sleep(3)
    return False


def bring_up(manifest, deploy, args):
    print(f"\n==> {manifest}")
    run(f"kubectl apply -f {manifest}")
    if not deploy:
        return

    if deploy in ("free5gc-smf", "mec-af"):
        # Config (SMF) and code (mec-af) live in ConfigMaps. If only they
        # changed, apply does NOT recreate the pod and the process keeps the old
        # version -- the LBO "does not activate" without any error. The restart forces
        # the reload; when the pod template also changed, it becomes a single rollout.
        run(f"kubectl -n {NS} rollout restart deploy/{deploy}",
            check=False, quiet=True)

    if not wait_rollout(deploy, args.timeout):
        print(f"    {RED}{deploy} was not ready within {args.timeout}s{RESET}")
        run(f"kubectl -n {NS} get pods -l app={deploy} -o wide", check=False)
        sys.exit(1)
    print(f"    {GREEN}ready{RESET}")

    if deploy == "free5gc-nrf":
        # The NRF does not register with itself: its gate is its own SBI being up.
        # It accepts connections before it can write to Mongo, so the slack
        # below is what avoids the race that breaks everything else.
        for _ in range(args.timeout // 2):
            r = run(f"kubectl -n {NS} logs deploy/{deploy} --tail=50",
                    check=False, quiet=True, timeout=60)
            if NRF_READY in strip_ansi(r.stdout):
                break
            time.sleep(2)
        print(f"    {GREEN}NRF SBI up{RESET}; slack of {args.wait_for}s before the others")
        time.sleep(args.wait_for)
        return

    if deploy in REGISTER_AT_NRF:
        if wait_registration(deploy, args.timeout):
            print(f"    {GREEN}registered at the NRF{RESET}")
        else:
            # Known state: the NF lost the race and kept an empty instance ID.
            # Restarting is the fix -- it redoes the registration from scratch.
            print(f"    {YELLOW}did not confirm registration at the NRF; restarting "
                  f"{deploy} (empty instance ID){RESET}")
            run(f"kubectl -n {NS} rollout restart deploy/{deploy}", check=False)
            wait_rollout(deploy, args.timeout)
            if wait_registration(deploy, args.timeout):
                print(f"    {GREEN}registered at the NRF after the restart{RESET}")
            else:
                print(f"    {RED}{deploy} is still not registered at the NRF. "
                      f"There is no point in going on: the registration of the UE will fail with "
                      f"MANDATORY_IE_MISSING further ahead.{RESET}")
                sys.exit(1)

    time.sleep(args.wait_for)


def up(args):
    other = "b" if args.scenario == "a" else "a"

    print(f"==> Removing the user plane of scenario {other.upper()} (if present)")
    for manifest, _ in SCENARIOS[other]:
        run(f"kubectl delete -f {manifest} --ignore-not-found=true",
            check=False, quiet=True)

    print(f"\n{'='*70}\nControl plane, in dependency order\n{'='*70}")
    for manifest, deploy in COMMON_CHAIN:
        bring_up(manifest, deploy, args)

    print(f"\n{'='*70}\nUser plane - scenario {args.scenario.upper()}\n{'='*70}")
    for manifest, deploy in SCENARIOS[args.scenario]:
        bring_up(manifest, deploy, args)

    print(f"\n{'='*70}\nMEC/remote services and tester\n{'='*70}")
    for manifest, deploy in EXTRAS:
        bring_up(manifest, deploy, args)

    print(f"\n{GREEN}==> Ready.{RESET} Check with: python3 deploy.py status")


def down():
    print("==> Removing everything from the namespace")
    all_of = EXTRAS + SCENARIOS["a"] + SCENARIOS["b"] + COMMON_CHAIN
    for manifest, _ in all_of:
        run(f"kubectl delete -f {manifest} --ignore-not-found=true",
            check=False, quiet=True)


def status():
    run(f"kubectl -n {NS} get pods -o wide")
    print()
    run(f"kubectl -n {NS} get svc")
    print()
    print("==> NFs that did NOT confirm registration at the NRF (empty ID, breaks the UE):")
    bad = [d for d in sorted(REGISTER_AT_NRF) if registered_at_nrf(d) is False]
    print("    " + (", ".join(bad) if bad else f"{GREEN}none{RESET}"))
    print()
    print("==> PFCP associations seen by the SMF (expected: 1 UPF in A, 2 in B)")
    # Filter in Python, not with grep/tail: the Windows cmd.exe has neither of them.
    r = run(f"kubectl -n {NS} logs deploy/free5gc-smf --tail=200", check=False, quiet=True)
    lines = [l for l in strip_ansi(r.stdout).splitlines()
              if re.search(r"pfcp|association", l, re.I)]
    print("    " + ("\n    ".join(lines[-20:]) if lines else "(nothing in the last 200 lines)"))
    print()
    print("==> Dynamic LBO: Services with tg2.mec/lbo=true and what mec-af announced to the NEF")
    run(f"kubectl -n {NS} get svc -l tg2.mec/lbo=true", check=False)
    run(f"kubectl -n {NS} logs deploy/mec-af --tail=8", check=False)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["up", "down", "status"])
    ap.add_argument("scenario", nargs="?", choices=["a", "b"],
                    help="required for 'up'")
    ap.add_argument("--wait-for", type=int, default=10,
                    help="slack in seconds between one NF and the next (default: 10)")
    ap.add_argument("--timeout", type=int, default=180,
                    help="timeout per NF, in seconds (default: 180)")
    args = ap.parse_args()

    if args.action == "up":
        if not args.scenario:
            ap.error("'up' requires the scenario: a (cUPF) or b (dUPF/ULCL)")
        up(args)
    elif args.action == "down":
        down()
    else:
        status()


if __name__ == "__main__":
    main()
