"""Paired A x B statistics of the infrastructure metrics, for the profiles of the
detailed study (which have complete metrics). Same design as the latency
analysis: the round is the unit, the pairs are the valid pairs of that analysis,
and the median is given with a 95% CI from order statistics.
    python3 infra_stats.py   ->  infra-paired.json (and a summary on screen)

Keys of infra-paired.json: "<profile>|<level>" -> "<column>|A", "|B", "|B-A" or
"|A-B" -> {n, median, ci}. Columns: brix05 = Edge Node, brix02 = UE/RAN node,
petshopboys = Server Node; *_cpu_pct = % of all cores, *_cpu_busiest_core_pct =
busiest core, *_cores = cores, *_mem_used_gib = memory used, *_rx_mbps /
*_tx_mbps = traffic of the physical interface.
"""
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "analysis"))
from paired_stats import LEVELS, PROFILES, median_ci, pairs   # only reads runs.json
from summarize_windows import load_series, rate

M = {(r["profile"], int(r["level"]), int(r["round"]), r["path"]): r
     for r in csv.DictReader(open(os.path.join(HERE, "metrics-per-window.csv")))}
W = {(r["profile"], int(r["level"]), int(r["round"]), r["path"]): (float(r["start_epoch"]), float(r["end_epoch"]))
     for r in csv.DictReader(open(os.path.join(HERE, "windows.csv")))}
cpu = load_series("node_cpu_by_mode",
                  lambda r: (r["nodename"], r["mode"]) if r["nodename"] in ("brix-porvir-05", "petshopboys") else None)


def mode_rate(node, mode, k):
    """CPU seconds per second of one mode of a node during the window k (cores)."""
    a, f = W[k]
    return rate(cpu[(node, mode)], a, f)


def value(k, col):
    x = M[k].get(col)
    return None if x in (None, "", "None") else float(x)


res = {}
for pf in PROFILES:
    for lv in LEVELS:
        acc = defaultdict(list)
        for rd, _, _ in pairs(pf, lv):
            ka, kb = (pf, lv, rd, "a-mec"), (pf, lv, rd, "b-mec")
            if ka not in M or kb not in M:
                continue
            for col in ("brix05_cpu_pct", "brix05_cpu_busiest_core_pct", "brix02_cpu_pct", "brix02_cpu_busiest_core_pct",
                        "petshopboys_cpu_pct", "petshopboys_rx_mbps", "petshopboys_tx_mbps", "brix05_rx_mbps",
                        "brix05_tx_mbps", "brix05_mem_used_gib"):
                a, b = value(ka, col), value(kb, col)
                if a is not None and b is not None:
                    acc[col + "|A"].append(a)
                    acc[col + "|B"].append(b)
                    acc[col + "|B-A"].append(b - a)
            for m in ("user", "system", "softirq"):
                a, b = mode_rate("brix-porvir-05", m, ka), mode_rate("brix-porvir-05", m, kb)
                if a is not None and b is not None:
                    acc["brix05_" + m + "_cores|B-A"].append(b - a)
            a, b = mode_rate("petshopboys", "idle", ka), mode_rate("petshopboys", "idle", kb)
            if a is not None and b is not None:
                acc["petshopboys_busy_cores|A-B"].append(b - a)   # idle B - idle A = busy A - busy B
        res[f"{pf}|{lv}"] = {k: dict(n=len(x), median=float(np.median(x)), ci=list(median_ci(x)[1:]))
                             for k, x in acc.items() if x}
json.dump(res, open(os.path.join(HERE, "infra-paired.json"), "w"), indent=1)
if __name__ == "__main__":
    for pf in PROFILES:
        for lv in LEVELS:
            r = res[f"{pf}|{lv}"]
            g = lambda k, c=2: f"{r[k]['median']:.{c}f}" if k in r else "-"
            gi = lambda k, c=2: f"{r[k]['median']:+.{c}f} [{r[k]['ci'][0]:+.{c}f},{r[k]['ci'][1]:+.{c}f}]" if k in r else "-"
            print(f"{pf:13} {lv:2d} n={r['brix05_cpu_pct|B-A']['n']:2d} | Edge Node A {g('brix05_cpu_pct|A',1)}% B {g('brix05_cpu_pct|B',1)}% d {gi('brix05_cpu_pct|B-A',1)}"
                  f" | busiest core A {g('brix05_cpu_busiest_core_pct|A',1)} B {g('brix05_cpu_busiest_core_pct|B',1)}"
                  f" | modes B-A user {gi('brix05_user_cores|B-A',3)} sys {gi('brix05_system_cores|B-A',3)} softirq {gi('brix05_softirq_cores|B-A',3)}")
            print(f"{'':16} UE/RAN node A {g('brix02_cpu_pct|A',1)} B {g('brix02_cpu_pct|B',1)} (busiest core {g('brix02_cpu_busiest_core_pct|A',1)}/{g('brix02_cpu_busiest_core_pct|B',1)})"
                  f" | Server Node busy A-B {gi('petshopboys_busy_cores|A-B',3)} cores | rx B-A {gi('petshopboys_rx_mbps|B-A',1)} tx B-A {gi('petshopboys_tx_mbps|B-A',1)} Mbps"
                  f" | Edge Node memory A {g('brix05_mem_used_gib|A',2)} B {g('brix05_mem_used_gib|B',2)} GiB")
