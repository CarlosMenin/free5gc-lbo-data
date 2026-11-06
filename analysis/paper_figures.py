"""Figs. 2 and 3 of the paper, drawn at column width with 8 pt text.

Fig. 2 (results-load-levels.pdf): median and 99th percentile of the network
delay of both scenarios at each background level, for the three profiles of
the detailed study. Fig. 3 (results-offered-load.pdf): increase of the median
network delay of every run with background against the load offered to the
core-to-edge direction of the link.

Output: out/paper-figures/.
    python3 load_campaign.py && python3 paper_figures.py
"""
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

from paired_stats import ALL_PROFILES, APP, D, LEVELS, NAME, PROFILES, ok

OUT_DIR = os.path.join(HERE, "out", "paper-figures")
os.makedirs(OUT_DIR, exist_ok=True)
COLUMN = 250.19702 / 72.27          # \columnwidth of the paper (in): inserted without scaling
FONT = 8
COLOR = {"a": "#2a78d6", "b": "#eb6834"}
MARK = {"a": "o", "b": "s"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
XL = ["0", "50", "80", "95", "99"]   # "none" does not fit at 8 pt; 0% = no background
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "STIXGeneral"],
    "mathtext.fontset": "stix", "font.size": FONT, "axes.titlesize": FONT, "axes.labelsize": FONT,
    "xtick.labelsize": FONT, "ytick.labelsize": FONT, "legend.fontsize": FONT,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2.5,
    "ytick.major.size": 2.5, "xtick.major.pad": 1.5, "ytick.major.pad": 1.5, "axes.labelpad": 2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlepad": 3,
    "legend.frameon": False, "pdf.fonttype": 42})
rng = np.random.default_rng(7)      # horizontal jitter of the points; fixed seed for identical figures


def add_grid(ax):
    ax.yaxis.grid(True, color=GRID, lw=0.5)
    ax.set_axisbelow(True)


def series(pf, lv, scen, k):
    """Indicator k (ms) of the MEC path of every valid run of a profile, level and scenario."""
    return [D[(pf, lv, rd, scen)]["mec_" + k] / 1000 for rd in range(1, 31) if ok(D.get((pf, lv, rd, scen)))]


def load_levels(height=2.50):
    fig, axs = plt.subplots(2, 3, figsize=(COLUMN, height), sharey="row")
    for row, k in enumerate(("net_p50", "net_p99")):
        for col, pf in enumerate(PROFILES):
            ax = axs[row, col]
            add_grid(ax)
            for scen, dx in (("a", -0.16), ("b", 0.16)):
                medians, q1, q3 = [], [], []
                for i, lv in enumerate(LEVELS):
                    v = series(pf, lv, scen, k)
                    ax.scatter(i + dx + rng.uniform(-0.07, 0.07, len(v)), v, s=2.5, color=COLOR[scen], alpha=0.28,
                               lw=0, zorder=2)
                    medians.append(np.median(v))
                    q1.append(np.percentile(v, 25))
                    q3.append(np.percentile(v, 75))
                x = np.arange(5) + dx
                ax.vlines(x, q1, q3, color=COLOR[scen], lw=1.6, zorder=3)
                ax.plot(x, medians, color=COLOR[scen], lw=1.0, marker=MARK[scen], ms=2.8, mec="white", mew=0.5,
                        zorder=4)
            ax.set_xlim(-0.5, 4.5)
            if row == 0:
                ax.set_ylim(0, 8)
                ax.yaxis.set_major_locator(FixedLocator([0, 2, 4, 6, 8]))
                ax.set_title(NAME[pf])
            else:
                ax.set_yscale("log")
                ax.set_ylim(1, 60)
                ax.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50]))
                ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
                ax.yaxis.set_minor_formatter(NullFormatter())
            ax.set_xticks(range(5))
            ax.set_xticklabels(XL if row else [""] * 5)
            if col == 0:
                ax.set_ylabel("Median (ms)" if row == 0 else "99th percentile (ms)")
    fig.supxlabel("Background load on the edge–core link (% of capacity)", fontsize=FONT, y=0.005)
    handles = [Line2D([], [], color=COLOR[c], marker=MARK[c], ms=3.2, mec="white", lw=1.0, label=lab)
               for c, lab in (("a", "Scenario A (centralized UPF)"), ("b", "Scenario B (dUPF with LBO)"))]
    fig.legend(handles=handles, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0), handlelength=1.6,
               columnspacing=1.2, handletextpad=0.4, borderaxespad=0.1)
    fig.subplots_adjust(left=0.115, right=0.995, top=0.855, bottom=0.135, wspace=0.10, hspace=0.12)
    fig.savefig(os.path.join(OUT_DIR, "results-load-levels.pdf"))
    plt.close(fig)


def offered_load(height=1.80):
    fig, ax = plt.subplots(figsize=(COLUMN, height))
    add_grid(ax)
    ax.xaxis.grid(True, color=GRID, lw=0.5)
    marker = {"teleoperation": "o", "ar-industrial": "v", "vr-360": "D", "cloud-gaming": "P", "vr-cloud": "s",
              "vr-extreme": "^"}
    for scen in ("b", "a"):
        for pf in ALL_PROFILES:
            xs, ys = [], []
            for lv in LEVELS[1:]:
                for rd in range(1, 31):
                    r, r0 = D.get((pf, lv, rd, scen)), D.get((pf, 0, rd, scen))
                    if not (ok(r) and ok(r0)) or not r.get("bg_requested_mbps"):
                        continue
                    # Offered load: requested background, plus the application downlink in Scenario A.
                    xs.append((r["bg_requested_mbps"] + (APP[pf] if scen == "a" else 0)) / r["bg_capacity_mbps"] * 100)
                    ys.append((r["mec_net_p50"] - r0["mec_net_p50"]) / 1000)
            ax.scatter(xs, np.clip(ys, -0.6, 6.7), s=7 if scen == "a" else 5.5, marker=marker[pf],
                       facecolor=COLOR[scen] if scen == "a" else "none",
                       edgecolor=COLOR[scen] if scen == "b" else "white", lw=0.35 if scen == "a" else 0.6,
                       alpha=0.7, zorder=3 if scen == "a" else 2)
    ax.axvline(100, color=INK2, lw=0.7, ls=(0, (4, 3)))
    ax.annotate("link\ncapacity", (100, 6.5), xytext=(3, 0), textcoords="offset points", ha="left", va="top",
                fontsize=FONT, color=INK2, linespacing=0.95)
    ax.set_xlim(45, 113)
    ax.set_ylim(-0.6, 6.8)
    ax.yaxis.set_major_locator(FixedLocator([0, 2, 4, 6]))
    ax.set_xlabel("Load offered to the core$\\rightarrow$edge direction (% of capacity)")
    ax.set_ylabel("Increase of the median\nnetwork delay (ms)", linespacing=0.95)
    handles = [Line2D([], [], ls="", marker="o", color=COLOR["a"], mec="white", ms=4, label="A (background + app.)"),
               Line2D([], [], ls="", marker="o", mfc="none", mec=COLOR["b"], ms=3.6, mew=0.7,
                      label="B (background only)")]
    handles += [Line2D([], [], ls="", marker=marker[pf], color=INK2, mfc="none", ms=3.4, mew=0.6, label=NAME[pf])
                for pf in ALL_PROFILES]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 0.95), ncol=2, handlelength=0.9,
              handletextpad=0.35, columnspacing=0.8, labelspacing=0.2, borderaxespad=0.2)
    fig.subplots_adjust(left=0.135, right=0.99, top=0.985, bottom=0.215)
    fig.savefig(os.path.join(OUT_DIR, "results-offered-load.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    load_levels()
    offered_load()
    print("figures in", OUT_DIR)
