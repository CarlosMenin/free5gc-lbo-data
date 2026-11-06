"""Tables of the paper and of the thesis, generated from the data to avoid transcription.

Output: out/tables/*.tex (bodies of the tabular environments). The paper uses
res_baseline (Table II), res_summary (Table III), res_deadline (Table IV),
res_traversal (Table V), cal_results and cal_validations (Tables VI and VII),
res_validity, app_excl_rounds and app_excl_runs (Section IV) and app_mtp
(Appendix D).
    python3 load_campaign.py && python3 tables.py
"""
import glob
import json
import math
import os
import re

from paired_stats import (ALL_PROFILES, APP, CAP_MEDIAN, D, EXCLUDED, HERE, LEVELS, NAME, PROFILES, kpi, med,
                          median_ci, ok, pairs, round_kept)

OUT = os.path.join(HERE, "out", "tables")
os.makedirs(OUT, exist_ok=True)
CAL_DIR = os.path.join(os.path.dirname(HERE), "calibration-data")
LV = {0: "none", 50: "50\\%", 80: "80\\%", 95: "95\\%", 99: "99\\%"}
SCEN = {"a": "A", "b": "B"}


def n(x, c=3, signed=False):
    """Number in LaTeX: c decimals, with the sign written in math mode."""
    if x is None:
        return "--"
    s = f"{x:+.{c}f}" if signed else f"{x:.{c}f}"
    return s.replace("-", "$-$").replace("+", "$+$") if signed else s.replace("-", "$-$")


def write_table(name, lines):
    open(os.path.join(OUT, name), "w", encoding="utf-8").write("\n".join(lines) + "\n")


RES = {}
for pf in ALL_PROFILES:
    for lv in LEVELS:
        P = pairs(pf, lv)
        RES[(pf, lv)] = {k: kpi(P, k, div) for k, div in (
            ("net_p50", 1000), ("net_p99", 1000), ("csv_p999", 1), ("jitter", 1), ("loss", 1), ("incomplete", 1),
            ("m2p_p50", 1000))}
        for dl in ("3", "5", "10"):
            A = [a["mec_deadline"][dl] * 100 for _, a, b in P]
            B = [b["mec_deadline"][dl] * 100 for _, a, b in P]
            RES[(pf, lv)]["deadline" + dl] = {"A": med(A), "B": med(B)}

# ---------------------------------------------------------------- validity (6 profiles)
L = []
for pf in ALL_PROFILES:
    a = sum(1 for rd in range(1, 31) for lv in LEVELS if (D.get((pf, lv, rd, "a")) or {}).get("completed"))
    b = sum(1 for rd in range(1, 31) for lv in LEVELS if (D.get((pf, lv, rd, "b")) or {}).get("completed"))
    kept = sum(1 for rd in range(1, 31) if (pf, rd) not in EXCLUDED)
    L.append(f"{NAME[pf]} & {APP[pf]:.0f} & {a} & {b} & {kept} & " + " & ".join(str(len(pairs(pf, lv))) for lv in LEVELS)
             + " \\\\")
write_table("res_validity.tex", L)

# ---------------------------------------------------------------- without background (6 profiles)
L = []
for pf in ALL_PROFILES:
    r = RES[(pf, 0)]["net_p50"]
    L.append(f"{NAME[pf]} & {APP[pf]:.0f} & {n(r['A'])} & {n(r['B'])} & {n(r['d'][0], 3, True)} & "
             f"[{n(r['d'][1], 3, True)}, {n(r['d'][2], 3, True)}] & {r['pct']:.1f}\\% & {r['win']}/{r['n']} \\\\")
write_table("res_baseline.tex", L)

# ---------------------------------------------------------------- summary per level (6 profiles)
L = []
for pf in ALL_PROFILES:
    c = [f"{n(RES[(pf, lv)]['net_p50']['d'][0], 2, True)} ({RES[(pf, lv)]['net_p50']['pct']:.0f}\\%)" for lv in LEVELS]
    L.append(f"{NAME[pf]} & " + " & ".join(c) + " \\\\")
write_table("res_summary.tex", L)

# ---------------------------------------------------------------- effective load (6 profiles)
cap = CAP_MEDIAN
L = []
for pf in ALL_PROFILES:
    c = []
    for lv in LEVELS[1:]:
        v = lv + APP[pf] / cap * 100
        c.append(f"\\textbf{{{v:.1f}\\%}}" if v >= 100 else f"{v:.1f}\\%")
    L.append(f"{NAME[pf]} & {APP[pf]:.0f} & " + " & ".join(c) + " \\\\")
write_table("res_load.tex", L)

# ---------------------------------------------------------------- deadline and quality (3 profiles)
L = []
cell = lambda v: "$<$0.01" if v < 0.005 else f"{v:.2f}"
for i, pf in enumerate(PROFILES):
    if i:
        L.append("\\addlinespace")
    for lv in LEVELS:
        r = RES[(pf, lv)]
        L.append(f"{NAME[pf] if lv == 0 else ''} & {LV[lv]} & " + " & ".join(
            f"{cell(r['deadline' + dl]['A'])} & {cell(r['deadline' + dl]['B'])}" for dl in ("3", "5", "10")) + " \\\\")
write_table("res_deadline.tex", L)

L = []
for i, pf in enumerate(PROFILES):
    if i:
        L.append("\\addlinespace")
    for lv in LEVELS:
        r = RES[(pf, lv)]
        L.append(f"{NAME[pf] if lv == 0 else ''} & {LV[lv]} & {n(r['net_p99']['A'], 2)} & {n(r['net_p99']['B'], 2)} & "
                 f"{n(r['csv_p999']['A'], 2)} & {n(r['csv_p999']['B'], 2)} & {r['jitter']['A']:.0f} & "
                 f"{r['jitter']['B']:.0f} & {n(r['loss']['A'], 3)} & {n(r['loss']['B'], 3)} & "
                 f"{n(r['incomplete']['A'], 2)} & {n(r['incomplete']['B'], 2)} \\\\")
write_table("res_quality.tex", L)


# ---------------------------------------------------------------- traversals (3 profiles)
def increase(pf, lv, scen, path, okf):
    """Median (with CI) of the increase of the median delay of a path over the same round without background."""
    d = []
    for rd in range(1, 31):
        r, r0 = D.get((pf, lv, rd, scen)), D.get((pf, 0, rd, scen))
        if okf(r) and okf(r0) and r.get(path + "_net_p50") is not None and r0.get(path + "_net_p50") is not None:
            d.append((r[path + "_net_p50"] - r0[path + "_net_p50"]) / 1000)
    return median_ci(d)


ok_remote_path = lambda r: bool(r and r["completed"] and r.get("bg_on") is not False and round_kept(r))
L = []
for i, pf in enumerate(PROFILES):
    if i:
        L.append("\\addlinespace")
    for lv in LEVELS[1:]:
        a_mec = increase(pf, lv, "a", "mec", ok)
        b_remote = increase(pf, lv, "b", "remote", ok_remote_path)
        b_mec = increase(pf, lv, "b", "mec", ok)
        ratio = "--" if b_remote[0] <= 0.2 else f"{a_mec[0] / b_remote[0]:.1f}"
        b_mec_us = round(b_mec[0] * 1000)
        L.append(f"{NAME[pf] if lv == 50 else ''} & {LV[lv]} & {n(a_mec[0], 2, True)} & {n(b_remote[0], 2, True)} & "
                 + ("$\\pm$0" if b_mec_us == 0 else n(b_mec_us, 0, True)) + f" & {ratio} \\\\")
write_table("res_traversal.tex", L)


# ---------------------------------------------------------------- exclusions (appendix)
L = []
for (pf, rd), e in sorted(EXCLUDED.items(), key=lambda kv: (ALL_PROFILES.index(kv[0][0]), kv[0][1])):
    if e[0] == "capacity":
        reason = f"Capacity {e[1]:.0f}~Mbps ($<$90\\% of the median)"
    else:
        reason = f"Alert: {SCEN[e[1]]} at {e[2]:.2f}~ms (others {e[3]:.2f}~ms)"
    L.append(f"{NAME[pf]} & {rd} & all & both & {reason} \\\\")
write_table("app_excl_rounds.tex", L)


def run_reason(r):
    """Why a run is not in the comparison."""
    if not r or not r.get("completed"):
        return "Not completed (PDU session not established)"
    if r.get("bg_problems") and any("GTP-U" in p for p in r["bg_problems"]):
        return "Background not observed at its cell"
    frac = r.get("bg_delivered_fraction")
    if frac is not None and r["level"] and frac < 0.9:
        return f"Background at {frac * 100:.0f}\\% of the requested rate"
    g = " ".join(r.get("guards") or [])
    if "poses" in g:
        m = re.search(r"received (\d+) of the (\d+) poses", g)
        return f"Server received {int(m.group(1)) / int(m.group(2)) * 100:.0f}\\% of the poses"
    return "Quality check of the generator"


L = []
for pf in ALL_PROFILES:
    for lv in LEVELS:
        for rd in range(1, 31):
            if (pf, rd) in EXCLUDED:
                continue
            for scen in "ab":
                r = D.get((pf, lv, rd, scen))
                if not ok(r):
                    L.append(f"{NAME[pf]} & {rd} & {LV[lv]} & {SCEN[scen]} & {run_reason(r)} \\\\")
write_table("app_excl_runs.tex", L)


# ---------------------------------------------------------------- appendix tables (6 profiles)
def kpi_table(name, k, cv, cd):
    L = []
    for i, pf in enumerate(ALL_PROFILES):
        if i:
            L.append("\\addlinespace")
        for lv in LEVELS:
            r = RES[(pf, lv)][k]
            t = r["t"]
            L.append(f"{NAME[pf] if lv == 0 else ''} & {LV[lv]} & {r['n']} & {n(r['A'], cv)} & {n(r['B'], cv)} & "
                     f"{n(r['d'][0], cd, True)} & [{n(r['d'][1], cd, True)}, {n(r['d'][2], cd, True)}] & "
                     f"{n(t['mean'], cd, True)} & [{n(t['ci'][0], cd, True)}, {n(t['ci'][1], cd, True)}] & "
                     f"{r['win']}/{r['n']} \\\\")
    write_table(name, L)


kpi_table("app_p50.tex", "net_p50", 3, 3)
kpi_table("app_p99.tex", "net_p99", 2, 2)
kpi_table("app_mtp.tex", "m2p_p50", 2, 2)

# ---------------------------------------------------------------- calibration (6 profiles)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}
T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896, 8: 0.889}
cal = {}
for d in sorted(glob.glob(os.path.join(CAL_DIR, "2026*"))):
    j = json.load(open(os.path.join(d, "calibration.json")))
    cal[j["args"]["profile"]] = j
L1, L2 = [], []
for pf in ALL_PROFILES:
    j = cal[pf]
    agg = j["aggregates"]
    p = {k: agg[k]["net_p50"]["median"] for k in agg}
    sd = {k: agg[k]["net_p50"]["sd"] for k in agg}
    floor = max(p["C0-tester"], p["C0-edge"], p["C0-remote"])
    v1, v2 = sd["C2-edge"] ** 2 / 5, sd["C2-remote"] ** 2 / 5
    dof = (v1 + v2) ** 2 / (v1 ** 2 / 4 + v2 ** 2 / 4)      # Welch-Satterthwaite
    g = max(1, min(8, int(dof)))
    mde = (T975[g] + T80[g]) * math.sqrt(v1 + v2)
    diff = p["C2-remote"] - p["C2-edge"]
    L1.append(f"{NAME[pf]} & {floor:.0f} & {p['C1-edge']:.0f} & {p['C1-remote']:.0f} & {p['C2-edge']:.0f} & "
              f"{p['C2-remote']:.0f} & {sd['C2-edge']:.0f} / {sd['C2-remote']:.0f} & {mde:.0f} & "
              f"{diff:.0f} ({diff / mde:.1f}$\\times$) \\\\")
    V1, V2, V3 = j["v1"], j["v2"], j["v3"]
    b, r = V3["paths"]["edge"], V3["paths"]["remote"]
    L2.append(f"{NAME[pf]} & ${V1['net_rtt']['slope']:+.4f}$ & {V1['excursion_pct']:.2f}\\% & "
              f"{V2['net_rtt']['slope']:.4f} & {V2['net_rtt']['intercept']:.0f} & "
              f"${b['difference_us']['p50']:+.0f}$ / ${r['difference_us']['p50']:+.0f}$ & "
              f"{b['limit_us']['p50'][1]:.0f} \\\\")
write_table("cal_results.tex", L1)
write_table("cal_validations.tex", L2)
print("tables in", OUT, "| median capacity", round(cap), "Mbps")
