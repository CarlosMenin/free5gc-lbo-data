"""Flatten the A x B campaign and process the per-frame records.

Reads campaign-data/ and writes runs.json next to this script: one record per
run (level, profile, round, scenario) with the summary of each measured path,
the UPF counters of the path verification, the background record, and, from
the per-frame CSV files, the median and 99.9th percentile of the network delay
and the fraction of frames not complete within each deadline.

Validity follows the campaign script (testbed/free5gc/scripts/campaign.py):
`valid` is the validity for A x B on the MEC path, `valid_remote` also for
b-remote x b-mec. File times come from campaign-data/run-file-times.csv,
because git does not keep them.

    python3 load_campaign.py                       # the campaign of the paper
    python3 load_campaign.py --data <folder>       # a campaign you ran (output of campaign.py)

For a campaign of your own, a run without an entry in run-file-times.csv takes the
modification time of its run.json.
"""
import argparse
import csv
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_ap = argparse.ArgumentParser(description="Flatten an A x B campaign into analysis/runs.json.")
_ap.add_argument("--data", default=os.path.join(os.path.dirname(HERE), "campaign-data"),
                 help="campaign folder, as written by testbed/free5gc/scripts/campaign.py "
                      "(default: ../campaign-data)")
ROOT = os.path.abspath(_ap.parse_args().data)
LEVEL_DIRS = {"no-background": 0, "background-50": 50, "background-80": 80, "background-95": 95, "background-99": 99}
DEADLINE_GRID = np.logspace(np.log10(0.2), np.log10(300), 120)   # ms, grid of deadlines for the curves
DEADLINES = [1, 2, 3, 5, 10, 20, 50]                              # ms, deadlines of the tables
MIN_BACKGROUND_DELIVERED = 0.90     # same threshold as the campaign script
WARMUP_S = 5.0
# Original modification time of each run.json (git does not keep it); it places the run in time.
_TIMES = os.path.join(ROOT, "run-file-times.csv")
MTIME = ({r["run_json"]: float(r["mtime_epoch"]) for r in csv.DictReader(open(_TIMES))}
         if os.path.exists(_TIMES) else {})
BACKGROUND_FIELDS = ("capacity_mbps", "capacity_measurements", "requested_mbps", "crossed_mbps", "delivered_fraction",
                     "path_loss_pct", "problems", "on", "seconds_on", "ue_recreated", "delay_s")
PATH_FIELDS = (("net_p50", ("net_rtt_us", "p50")), ("net_p95", ("net_rtt_us", "p95")),
               ("net_p99", ("net_rtt_us", "p99")), ("net_max", ("net_rtt_us", "max")),
               ("net_mean", ("net_rtt_us", "mean")), ("m2p_p50", ("m2p_us", "p50")),
               ("m2p_p95", ("m2p_us", "p95")), ("hold_p50", ("hold_us", "p50")),
               ("jitter", ("jitter_net_us",)), ("loss", ("dl_packet_loss_srv_pct",)),
               ("incomplete", ("frames_incomplete_pct",)), ("throughput", ("dl_throughput_mbps",)),
               ("fr_complete", ("frames_complete",)), ("fr_stats", ("frames_in_stats",)),
               ("fr_expected", ("window", "frames_expected")), ("rcvbuf", ("health", "sock_rcvbuf_bytes")),
               ("sock_drops", ("health", "dl_sock_drops")), ("drift", ("health", "clock_drift_us")))


def get(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def remote_only(msg):
    """A warning about the remote path only: it removes the run from b-remote x b-mec, not from A x B."""
    return msg.startswith(("a-remote:", "b-remote:", "loss very different between the paths"))


def load_run(scenario_dir, profile, level):
    """The run record of one scenario, with its validity, or None if the run did not complete."""
    p = os.path.join(scenario_dir, profile, "run.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        j = json.load(fh)
    executions = j.get("executions") or []
    if not executions:
        return None
    e = executions[0]
    guards = [m for scope, m in e.get("warnings", []) if scope == "campaign"]
    e["_valid"] = not [m for m in guards if not remote_only(m)]
    e["_valid_remote"] = not guards
    e["_background"] = None
    if level:
        # A level with background without proof that the background existed is not a level with background.
        f = os.path.join(scenario_dir, "background.json")
        bg = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None
        e["_background"] = bg
        if not (bg and bg.get("on") and (bg.get("delivered_fraction") or 0) >= MIN_BACKGROUND_DELIVERED
                and not bg.get("problems")):
            e["_valid"] = e["_valid_remote"] = False
    return e


def frames(scenario_dir, profile, label):
    f = glob.glob(os.path.join(scenario_dir, profile, "run-*", label + ".csv"))
    if not f:
        return None
    return np.loadtxt(f[0], delimiter=",", skiprows=1, usecols=(1, 5), ndmin=2)   # t_s, net_us


records = []
for level_dir, level in LEVEL_DIRS.items():
    for profile_dir in sorted(glob.glob(os.path.join(ROOT, level_dir, "*"))):
        profile = os.path.basename(profile_dir)
        for round_dir in sorted(glob.glob(os.path.join(profile_dir, "round-*"))):
            rnd = int(round_dir.rsplit("-", 1)[1])
            for scen in "ab":
                scenario_dir = os.path.join(round_dir, scen)
                e = load_run(scenario_dir, profile, level)
                if e is None:
                    records.append(dict(level=level, profile=profile, round=rnd, scenario=scen, completed=False))
                    continue
                r = dict(level=level, profile=profile, round=rnd, scenario=scen, completed=True,
                         valid=e["_valid"], valid_remote=e["_valid_remote"],
                         guards=[m[:120] for scope, m in e.get("warnings", []) if scope == "campaign"],
                         placement=e.get("placement"), attempts=e.get("attempts"),
                         proof_anchor=get(e, "proof", "mec", "delta", "upf" if scen == "a" else "psa-upf", "rx_pkts"),
                         proof_iupf=get(e, "proof", "mec", "delta", "i-upf", "rx_pkts"),
                         proof_remote_psa=get(e, "proof", "remote", "delta", "psa-upf", "rx_pkts"),
                         mtime=MTIME.get(os.path.relpath(os.path.join(scenario_dir, profile, "run.json"), ROOT),
                                         os.path.getmtime(os.path.join(scenario_dir, profile, "run.json"))))
                bg = e.get("_background") or {}
                for k in BACKGROUND_FIELDS:
                    r["bg_" + k] = bg.get(k)
                for label, d in (e.get("paths") or {}).items():
                    p = label.split("-")[1] + "_"                        # "mec_" or "remote_"
                    for k, keys in PATH_FIELDS:
                        r[p + k] = get(d, *keys)
                    q = frames(scenario_dir, profile, label)
                    if q is None:
                        r[p + "csv"] = False
                        continue
                    net = np.sort(q[q[:, 0] >= WARMUP_S, 1] / 1000.0)    # network delay after the warm-up, ms
                    expected = r[p + "fr_expected"] or len(net)
                    r[p + "csv"] = True
                    r[p + "csv_n"] = int(len(net))
                    r[p + "csv_p50"] = float(np.percentile(net, 50)) if len(net) else None
                    r[p + "csv_p999"] = float(np.percentile(net, 99.9)) if len(net) else None
                    idx = np.searchsorted(net, DEADLINE_GRID, side="right")
                    r[p + "not_ready"] = (1 - idx / expected).clip(0, 1).round(6).tolist()
                    r[p + "deadline"] = {str(dl): float(1 - np.searchsorted(net, dl, side="right") / expected)
                                         for dl in DEADLINES}
                records.append(r)
json.dump({"grid": DEADLINE_GRID.tolist(), "deadlines": DEADLINES, "records": records},
          open(os.path.join(HERE, "runs.json"), "w"))
print(len(records), "records;", sum(r["completed"] for r in records), "completed runs")
