"""Figure and table of resource usage (thesis Sec. 5.8; numbers of Section V-G of the paper),
for the profiles of the detailed study.

Same style as the figures of thesis_figures.py: the round is the unit, and the
pairs are the valid pairs of the latency analysis. Reads metricas-por-janela.csv
and infra-pareado.json.
    python3 summarize_windows.py && python3 infra_stats.py && python3 resources_figure.py
Output: out/results-resources.pdf and out/res_resources.tex.
"""
import csv, json, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "analysis"))
from paired_stats import NIVEIS, NOME, PERFIS, pares   # only reads dados.json

MONO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(MONO, exist_ok=True)
APP = {"teleoperacao": 8, "vr-cloud": 50, "vr-extremo": 100}
COR = {"a": "#2a78d6", "b": "#eb6834"}
MK = {"a": "o", "b": "s"}
CEN = {"a": "Scenario A (centralized UPF)", "b": "Scenario B (dUPF with LBO)"}
DIR = {"rx": ("Edge$\\rightarrow$core", "#0b0b0b", "^"), "tx": ("Core$\\rightarrow$edge", "#8a8986", "v")}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
XL = ["none", "50", "80", "95", "99"]
XLAB = "Background load on the edge–core link (% of measured capacity)"
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "STIXGeneral"],
    "mathtext.fontset": "stix", "font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
    "ytick.major.width": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 9.5, "axes.titleweight": "bold", "legend.frameon": False, "pdf.fonttype": 42})
rng = np.random.default_rng(7)
M = {(r["perfil"], int(r["nivel"]), int(r["rodada"]), r["caminho"]): r
     for r in csv.DictReader(open(os.path.join(AQUI, "metricas-por-janela.csv")))}


def val(k, col):
    x = (M.get(k) or {}).get(col)
    return None if x in (None, "", "None") else float(x)


def pareados(pf, nv, col):
    """[(A, B)] of the column in the rounds with a valid pair."""
    out = []
    for rd, _, _ in pares(pf, nv):
        a, b = val((pf, nv, rd, "a-mec"), col), val((pf, nv, rd, "b-mec"), col)
        if a is not None and b is not None:
            out.append((a, b))
    return out


def figura():
    fig, axs = plt.subplots(2, 3, figsize=(6.4, 4.4))
    for col, pf in enumerate(PERFIS):
        ax = axs[0, col]
        ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
        for cen, dx in (("a", -0.13), ("b", 0.13)):
            meds, q1, q3 = [], [], []
            for i, nv in enumerate(NIVEIS):
                v = [p[0 if cen == "a" else 1] for p in pareados(pf, nv, "brix05_cpu_pct")]
                ax.scatter(i + dx + rng.uniform(-0.07, 0.07, len(v)), v, s=5, color=COR[cen], alpha=0.28, lw=0, zorder=2)
                meds.append(np.median(v)); q1.append(np.percentile(v, 25)); q3.append(np.percentile(v, 75))
            x = np.arange(5) + dx
            ax.vlines(x, q1, q3, color=COR[cen], lw=2.2, zorder=3)
            ax.plot(x, meds, color=COR[cen], lw=1.4, marker=MK[cen], ms=4.2, mec="white", mew=0.8, zorder=4)
        ax.set_ylim(0, 24)
        ax.set_title(f"{NOME[pf]} ({APP[pf]} Mbps)")
        ax.set_xticks(range(5)); ax.set_xticklabels([""] * 5)
        if col == 0:
            ax.set_ylabel("Edge Node CPU (% of 4 cores)")
        else:
            ax.set_yticklabels([])
        ax = axs[1, col]
        ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
        ax.axhline(APP[pf], color=INK2, lw=0.8, ls=(0, (4, 3)), zorder=1)
        meds, q1, q3 = [], [], []
        for i, nv in enumerate(NIVEIS):
            # only the edge -> core direction: the other carries the background and varies with it
            v = [a - b for a, b in pareados(pf, nv, "petshopboys_rx_mbps")]
            ax.scatter(i + rng.uniform(-0.09, 0.09, len(v)), np.maximum(v, 0), s=5, color=INK2, alpha=0.35, lw=0, zorder=2)
            meds.append(np.median(v)); q1.append(np.percentile(v, 25)); q3.append(np.percentile(v, 75))
        ax.vlines(np.arange(5), q1, q3, color=INK, lw=2.2, zorder=3)
        ax.plot(np.arange(5), meds, color=INK, lw=1.2, marker="D", ms=3.8, mec="white", mew=0.6, zorder=4)
        ax.set_ylim(0, APP[pf] * 1.45)
        ax.set_xticks(range(5)); ax.set_xticklabels(XL, fontsize=8.5)
        if col == 0:
            ax.set_ylabel("Edge$\\rightarrow$core traffic\nremoved, A $-$ B (Mbps)")
        if col == 1:
            ax.set_xlabel(XLAB)
    hs = [Line2D([], [], color=COR[c], marker=MK[c], ms=4.5, mec="white", lw=1.4, label=CEN[c]) for c in "ab"]
    fig.legend(handles=hs, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0), fontsize=9)
    hs = [Line2D([], [], color=INK, marker="D", ms=3.8, mec="white", lw=1.2, label="paired difference A $-$ B"),
          Line2D([], [], color=INK2, lw=0.8, ls=(0, (4, 3)), label="bitrate of the application")]
    fig.legend(handles=hs, loc="center", ncol=2, bbox_to_anchor=(0.5, 0.505), fontsize=8.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=2.6)
    fig.savefig(os.path.join(MONO, "results-resources.pdf"))
    plt.close(fig)


def tabela():
    R = json.load(open(os.path.join(AQUI, "infra-pareado.json")))
    LV = {0: "none", 50: "50\\%", 80: "80\\%", 95: "95\\%", 99: "99\\%"}
    s = lambda x, c: f"$\\pm${0:.{c}f}" if round(x, c) == 0 else (f"{x:+.{c}f}").replace("-", "$-$").replace("+", "$+$")
    L = []
    for i, pf in enumerate(PERFIS):
        if i:
            L.append("\\addlinespace")
        for nv in NIVEIS:
            r = R[f"{pf}|{nv}"]
            m = lambda k: r[k]["mediana"]
            L.append(f"{NOME[pf] if nv == 0 else ''} & {LV[nv]} & {m('brix05_cpu_pct|A'):.1f} & {m('brix05_cpu_pct|B'):.1f} & "
                     f"{s(m('brix05_cpu_pct|B-A'), 1)} & {m('brix05_cpu_nucleo_max_pct|A'):.1f} & {m('brix05_cpu_nucleo_max_pct|B'):.1f} & "
                     f"{s(m('petshopboys_ocupado_nucleos|A-B'), 2)} & {-m('petshopboys_rx_mbps|B-A'):.0f} & {-m('petshopboys_tx_mbps|B-A'):.0f} \\\\")
    os.makedirs(os.path.join(AQUI, "out"), exist_ok=True)
    open(os.path.join(AQUI, "out", "res_resources.tex"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    figura()
    tabela()
    print("figure in", MONO, "and table in out/res_resources.tex")
