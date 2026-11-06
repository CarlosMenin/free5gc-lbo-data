"""Figure and table of resource usage (numbers of Section V-G of the paper), for
the profiles of the detailed study.

Same style as the figures of thesis_figures.py: the round is the unit, and the
pairs are the valid pairs of the latency analysis. Reads metrics-per-window.csv
and infra-paired.json.
    python3 summarize_windows.py && python3 infra_stats.py && python3 resources_figure.py
Output: out/results-resources.pdf and out/res_resources.tex.
"""
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "analysis"))
from paired_stats import LEVELS, NAME, PROFILES, pairs   # only reads runs.json

OUT_DIR = os.path.join(HERE, "out")
os.makedirs(OUT_DIR, exist_ok=True)
APP = {"teleoperation": 8, "vr-cloud": 50, "vr-extreme": 100}
COLOR = {"a": "#2a78d6", "b": "#eb6834"}
MARK = {"a": "o", "b": "s"}
SCEN = {"a": "Scenario A (centralized UPF)", "b": "Scenario B (dUPF with LBO)"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
XL = ["none", "50", "80", "95", "99"]
XLAB = "Background load on the edge–core link (% of measured capacity)"
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "STIXGeneral"],
    "mathtext.fontset": "stix", "font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
    "ytick.major.width": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 9.5, "axes.titleweight": "bold", "legend.frameon": False, "pdf.fonttype": 42})
rng = np.random.default_rng(7)      # horizontal jitter of the points; fixed seed for identical figures
M = {(r["profile"], int(r["level"]), int(r["round"]), r["path"]): r
     for r in csv.DictReader(open(os.path.join(HERE, "metrics-per-window.csv")))}


def value(k, col):
    x = (M.get(k) or {}).get(col)
    return None if x in (None, "", "None") else float(x)


def paired_values(pf, lv, col):
    """[(A, B)] of the column in the rounds with a valid pair."""
    out = []
    for rd, _, _ in pairs(pf, lv):
        a, b = value((pf, lv, rd, "a-mec"), col), value((pf, lv, rd, "b-mec"), col)
        if a is not None and b is not None:
            out.append((a, b))
    return out


def figure():
    fig, axs = plt.subplots(2, 3, figsize=(6.4, 4.4))
    for col, pf in enumerate(PROFILES):
        ax = axs[0, col]
        ax.yaxis.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for scen, dx in (("a", -0.13), ("b", 0.13)):
            medians, q1, q3 = [], [], []
            for i, lv in enumerate(LEVELS):
                v = [p[0 if scen == "a" else 1] for p in paired_values(pf, lv, "brix05_cpu_pct")]
                ax.scatter(i + dx + rng.uniform(-0.07, 0.07, len(v)), v, s=5, color=COLOR[scen], alpha=0.28, lw=0,
                           zorder=2)
                medians.append(np.median(v))
                q1.append(np.percentile(v, 25))
                q3.append(np.percentile(v, 75))
            x = np.arange(5) + dx
            ax.vlines(x, q1, q3, color=COLOR[scen], lw=2.2, zorder=3)
            ax.plot(x, medians, color=COLOR[scen], lw=1.4, marker=MARK[scen], ms=4.2, mec="white", mew=0.8, zorder=4)
        ax.set_ylim(0, 24)
        ax.set_title(f"{NAME[pf]} ({APP[pf]} Mbps)")
        ax.set_xticks(range(5))
        ax.set_xticklabels([""] * 5)
        if col == 0:
            ax.set_ylabel("Edge Node CPU (% of 4 cores)")
        else:
            ax.set_yticklabels([])
        ax = axs[1, col]
        ax.yaxis.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.axhline(APP[pf], color=INK2, lw=0.8, ls=(0, (4, 3)), zorder=1)
        medians, q1, q3 = [], [], []
        for i, lv in enumerate(LEVELS):
            # Only the edge -> core direction: the other one carries the background and varies with it.
            v = [a - b for a, b in paired_values(pf, lv, "petshopboys_rx_mbps")]
            ax.scatter(i + rng.uniform(-0.09, 0.09, len(v)), np.maximum(v, 0), s=5, color=INK2, alpha=0.35, lw=0,
                       zorder=2)
            medians.append(np.median(v))
            q1.append(np.percentile(v, 25))
            q3.append(np.percentile(v, 75))
        ax.vlines(np.arange(5), q1, q3, color=INK, lw=2.2, zorder=3)
        ax.plot(np.arange(5), medians, color=INK, lw=1.2, marker="D", ms=3.8, mec="white", mew=0.6, zorder=4)
        ax.set_ylim(0, APP[pf] * 1.45)
        ax.set_xticks(range(5))
        ax.set_xticklabels(XL, fontsize=8.5)
        if col == 0:
            ax.set_ylabel("Edge$\\rightarrow$core traffic\nremoved, A $-$ B (Mbps)")
        if col == 1:
            ax.set_xlabel(XLAB)
    handles = [Line2D([], [], color=COLOR[c], marker=MARK[c], ms=4.5, mec="white", lw=1.4, label=SCEN[c]) for c in "ab"]
    fig.legend(handles=handles, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0), fontsize=9)
    handles = [Line2D([], [], color=INK, marker="D", ms=3.8, mec="white", lw=1.2, label="paired difference A $-$ B"),
               Line2D([], [], color=INK2, lw=0.8, ls=(0, (4, 3)), label="bitrate of the application")]
    fig.legend(handles=handles, loc="center", ncol=2, bbox_to_anchor=(0.5, 0.505), fontsize=8.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=2.6)
    fig.savefig(os.path.join(OUT_DIR, "results-resources.pdf"))
    plt.close(fig)


def table():
    R = json.load(open(os.path.join(HERE, "infra-paired.json")))
    LV = {0: "none", 50: "50\\%", 80: "80\\%", 95: "95\\%", 99: "99\\%"}
    s = lambda x, c: f"$\\pm${0:.{c}f}" if round(x, c) == 0 else (f"{x:+.{c}f}").replace("-", "$-$").replace("+", "$+$")
    L = []
    for i, pf in enumerate(PROFILES):
        if i:
            L.append("\\addlinespace")
        for lv in LEVELS:
            r = R[f"{pf}|{lv}"]
            m = lambda k: r[k]["median"]
            L.append(f"{NAME[pf] if lv == 0 else ''} & {LV[lv]} & {m('brix05_cpu_pct|A'):.1f} & {m('brix05_cpu_pct|B'):.1f} & "
                     f"{s(m('brix05_cpu_pct|B-A'), 1)} & {m('brix05_cpu_busiest_core_pct|A'):.1f} & "
                     f"{m('brix05_cpu_busiest_core_pct|B'):.1f} & {s(m('petshopboys_busy_cores|A-B'), 2)} & "
                     f"{-m('petshopboys_rx_mbps|B-A'):.0f} & {-m('petshopboys_tx_mbps|B-A'):.0f} \\\\")
    open(os.path.join(OUT_DIR, "res_resources.tex"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    figure()
    table()
    print("figure and table in", OUT_DIR)
