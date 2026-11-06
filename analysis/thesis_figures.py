"""Figures of the undergraduate thesis (in English), in the style of the original calibration figure.

Output: out/thesis-figures/. The paper uses its own versions of two of them,
drawn at column width by paper_figures.py.
    python3 load_campaign.py && python3 thesis_figures.py
"""
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

from paired_stats import (APP, AQUI, D, GRADE, NIVEIS, NOME, PERFIS, PERFIS_TODOS, ic_mediana, kpi, ok, pares)

MONO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "thesis-figures")
os.makedirs(MONO, exist_ok=True)
CAL = os.path.join(os.path.dirname(AQUI), "calibration-data")
MBPS = {"teleoperacao": 8, "ar-industrial": 12, "vr-360": 25, "cloud-gaming": 30, "vr-cloud": 50, "vr-extremo": 100}
COR = {"a": "#2a78d6", "b": "#eb6834"}
MK = {"a": "o", "b": "s"}
CEN = {"a": "Scenario A (centralized UPF)", "b": "Scenario B (dUPF with LBO)"}
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


def grade(ax, eixo="y"):
    if eixo in ("y", "both"):
        ax.yaxis.grid(True, color=GRID, lw=0.6)
    if eixo in ("x", "both"):
        ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def logy(ax, lo, hi, ticks, fmt=lambda v: f"{v:g}"):
    ax.set_yscale("log")
    ax.set_ylim(lo, hi)
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt(v)))
    ax.yaxis.set_minor_formatter(NullFormatter())


def serie(pf, nv, cen, k, div=1.0):
    return [D[(pf, nv, rd, cen)]["mec_" + k] / div for rd in range(1, 31) if ok(D.get((pf, nv, rd, cen)))]


def legenda(fig, y):
    hs = [Line2D([], [], color=COR[c], marker=MK[c], ms=4.5, mec="white", lw=1.4, label=CEN[c]) for c in "ab"]
    fig.legend(handles=hs, loc="upper center", ncol=2, bbox_to_anchor=(0.5, y), fontsize=9)


# ---------------------------------------------------------------- calibration (6 profiles)
def calibracao():
    ag = {}
    for d in sorted(glob.glob(os.path.join(CAL, "2026*"))):
        j = json.load(open(os.path.join(d, "calibracao.json")))
        ag[j["args"]["perfil"]] = {k: v["net_p50"]["mediana"] for k, v in j["agregados"].items()}
    cores = ["#2a78d6", "#eb6834", "#1baf7a"]
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    y, ticks, rot = 0, [], []
    for pf in PERFIS_TODOS:
        p = ag[pf]
        piso = max(p["C0-tester"], p["C0-borda"], p["C0-nucleo"])
        topo = y
        for cam, rotulo in (("borda", "edge (1 UPF)"), ("nucleo", "remote (2 UPFs)")):
            seg = [piso, p[f"C1-{cam}"] - piso, p[f"C2-{cam}"] - p[f"C1-{cam}"]]
            esq = 0
            for s, c in zip(seg, cores):
                ax.barh(y, s, left=esq, color=c, height=0.62, edgecolor="white", lw=0.8)
                esq += s
            ax.text(esq + 25, y, f"{p[f'C2-{cam}']:,.0f}", va="center", fontsize=8.5)
            ticks.append(y)
            rot.append(rotulo)
            y -= 0.85
        t = ax.text(0, topo + 0.52, NOME[pf], fontweight="bold", fontsize=9, va="bottom")
        ax.annotate(f"  ({MBPS[pf]} Mbps downlink)", xy=(1, 0), xycoords=t, va="bottom", fontsize=8.5, color=INK2)
        y -= 0.75
    ax.set_yticks(ticks)
    ax.set_yticklabels(rot, fontsize=8.5)
    ax.set_xlim(0, 2600)
    ax.set_ylim(y + 0.35, 1.0)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("Median network delay (p50, $\\mu$s)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    grade(ax, "x")
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for c in cores]
    fig.legend(hs, ["Instrument floor (C0)", "Cluster network (C1 $-$ C0)", "5G user plane (C2 $-$ C1)"],
               loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.01), fontsize=8.5)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(os.path.join(MONO, "calibration-decomposition.pdf"))
    plt.close(fig)


# ---------------------------------------------------------------- median and 99th percentile per level (3 profiles)
def niveis():
    fig, axs = plt.subplots(2, 3, figsize=(6.4, 4.7), sharey="row")
    for lin, k in enumerate(("net_p50", "net_p99")):
        for col, pf in enumerate(PERFIS):
            ax = axs[lin, col]
            grade(ax)
            for cen, dx in (("a", -0.13), ("b", 0.13)):
                meds, q1, q3 = [], [], []
                for i, nv in enumerate(NIVEIS):
                    v = serie(pf, nv, cen, k, 1000)
                    ax.scatter(i + dx + rng.uniform(-0.07, 0.07, len(v)), v, s=5, color=COR[cen], alpha=0.28,
                               lw=0, zorder=2)
                    meds.append(np.median(v))
                    q1.append(np.percentile(v, 25))
                    q3.append(np.percentile(v, 75))
                x = np.arange(5) + dx
                ax.vlines(x, q1, q3, color=COR[cen], lw=2.2, zorder=3)
                ax.plot(x, meds, color=COR[cen], lw=1.4, marker=MK[cen], ms=4.2, mec="white", mew=0.8, zorder=4)
            if lin == 0:
                ax.set_ylim(0, 8)
                ax.set_title(NOME[pf])
            else:
                logy(ax, 1, 60, [1, 2, 5, 10, 20, 50])
            ax.set_xticks(range(5))
            ax.set_xticklabels(XL if lin else [""] * 5, fontsize=8.5)
            if col == 0:
                ax.set_ylabel("Median network delay (ms)" if lin == 0 else "99th percentile (ms, log)")
            if lin == 1 and col == 1:
                ax.set_xlabel(XLAB)
    legenda(fig, 1.01)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(os.path.join(MONO, "results-load-levels.pdf"))
    plt.close(fig)


# ---------------------------------------------------------------- paired difference (6 profiles)
def pareada():
    fig, axs = plt.subplots(2, 3, figsize=(6.4, 4.6), sharey=True)
    for idx, pf in enumerate(PERFIS_TODOS):
        ax = axs[idx // 3, idx % 3]
        grade(ax)
        ax.axhline(0, color=INK2, lw=0.8)
        for i, nv in enumerate(NIVEIS):
            d = [(a["mec_net_p50"] - b["mec_net_p50"]) / 1000 for _, a, b in pares(pf, nv)]
            dv = np.minimum(d, 6.85)
            ax.scatter(i + rng.uniform(-0.16, 0.16, len(d)), dv, s=6, color=INK2, alpha=0.45, lw=0, zorder=2)
            m, lo, hi = ic_mediana(d)
            ax.vlines(i + 0.28, lo, min(hi, 6.85), color=INK, lw=2.0, zorder=3)
            ax.plot([i + 0.28], [m], marker="D", ms=4, color=INK, mec="white", mew=0.7, zorder=4)
            ax.annotate(f"{sum(1 for x in d if x > 0)}/{len(d)}", (i, -0.6), ha="center", fontsize=6.5, color=INK2)
        ax.set_ylim(-0.85, 7)
        ax.set_xticks(range(5))
        ax.set_xticklabels(XL, fontsize=8)
        ax.set_title(f"{NOME[pf]} ({MBPS[pf]} Mbps)")
        if idx % 3 == 0:
            ax.set_ylabel("A $-$ B, median delay (ms)")
        if idx == 4:
            ax.set_xlabel(XLAB)
    fig.tight_layout()
    fig.savefig(os.path.join(MONO, "results-paired-difference.pdf"))
    plt.close(fig)


# ---------------------------------------------------------------- offered load (6 profiles)
def carga():
    fig, ax = plt.subplots(figsize=(6.3, 3.3))
    grade(ax)
    mkp = {"teleoperacao": "o", "ar-industrial": "v", "vr-360": "D", "cloud-gaming": "P", "vr-cloud": "s",
           "vr-extremo": "^"}
    for cen in ("b", "a"):
        for pf in PERFIS_TODOS:
            xs, ys = [], []
            for nv in NIVEIS[1:]:
                for rd in range(1, 31):
                    r, r0 = D.get((pf, nv, rd, cen)), D.get((pf, 0, rd, cen))
                    if not (ok(r) and ok(r0)) or not r.get("f_pedido_mbps"):
                        continue
                    xs.append((r["f_pedido_mbps"] + (APP[pf] if cen == "a" else 0)) / r["f_capacidade_mbps"] * 100)
                    ys.append((r["mec_net_p50"] - r0["mec_net_p50"]) / 1000)
            ax.scatter(xs, np.clip(ys, -0.6, 6.7), s=14 if cen == "a" else 11, marker=mkp[pf],
                       facecolor=COR[cen] if cen == "a" else "none",
                       edgecolor=COR[cen] if cen == "b" else "white", lw=0.5 if cen == "a" else 0.8,
                       alpha=0.7, zorder=3 if cen == "a" else 2)
    ax.axvline(100, color=INK2, lw=0.8, ls=(0, (4, 3)))
    ax.annotate("link capacity", (100, 6.2), xytext=(-4, 0), textcoords="offset points", ha="right",
                fontsize=8, color=INK2)
    ax.set_xlim(45, 113)
    ax.set_ylim(-0.6, 6.8)
    ax.set_xlabel("Load offered to the core$\\rightarrow$edge direction during the measurement (% of capacity)")
    ax.set_ylabel("Increase of the median\nnetwork delay (ms)")
    hs = [Line2D([], [], ls="", marker="o", color=COR["a"], mec="white", ms=6,
                 label="Scenario A (background + application)"),
          Line2D([], [], ls="", marker="o", mfc="none", mec=COR["b"], ms=5.5, mew=1,
                 label="Scenario B (background only)")]
    hs += [Line2D([], [], ls="", marker=mkp[pf], color=INK2, mfc="none", ms=5, label=NOME[pf]) for pf in PERFIS_TODOS]
    ax.legend(handles=hs, loc="upper left", fontsize=7.5, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(MONO, "results-offered-load.pdf"))
    plt.close(fig)


# ---------------------------------------------------------------- benefit against application bitrate (6 profiles)
def taxa():
    azuis = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
    x = np.array([MBPS[pf] for pf in PERFIS_TODOS], dtype=float)
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.9))
    for j, nv in enumerate(NIVEIS):
        m, lo, hi, pc = [], [], [], []
        for pf in PERFIS_TODOS:
            k = kpi(pares(pf, nv), "net_p50", 1000)
            m.append(k["d"][0])
            lo.append(k["d"][1])
            hi.append(k["d"][2])
            pc.append(k["pct"])
        m, lo, hi = np.array(m), np.array(lo), np.array(hi)
        rot = "none" if nv == 0 else f"{nv}%"
        axs[0].errorbar(x, m, yerr=[m - lo, hi - m], color=azuis[j], lw=1.4, marker="o", ms=4, mec="white",
                        mew=0.7, capsize=2, elinewidth=0.9, label=rot)
        axs[1].plot(x, pc, color=azuis[j], lw=1.4, marker="o", ms=4, mec="white", mew=0.7, label=rot)
    for ax, yl, lim in ((axs[0], "A $-$ B, median network delay (ms)", (0, 6)),
                        (axs[1], "Reduction with LBO (%)", (0, 100))):
        grade(ax, "y")
        ax.set_xscale("log")
        ax.set_xlim(6.5, 125)
        ax.xaxis.set_major_locator(FixedLocator(list(MBPS.values())))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis="x", labelsize=7.5)
        ax.set_ylim(*lim)
        ax.set_ylabel(yl)
        ax.set_xlabel("Application downlink (Mbps, log)")
    axs[0].legend(title="Background", fontsize=7.5, title_fontsize=7.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(MONO, "results-bitrate.pdf"))
    plt.close(fig)


# ---------------------------------------------------------------- deadline (3 profiles)
def prazo():
    lv = (0, 80, 99)
    fig, axs = plt.subplots(3, 3, figsize=(6.4, 6.3), sharex=True, sharey=True)
    sel = (GRADE >= 0.5) & (GRADE <= 60)
    rot = {1e-4: "0.01%", 1e-3: "0.1%", 1e-2: "1%", 1e-1: "10%", 1: "100%"}
    for lin, nv in enumerate(lv):
        for col, pf in enumerate(PERFIS):
            ax = axs[lin, col]
            grade(ax, "both")
            for cen in "ab":
                M = np.array([D[(pf, nv, rd, cen)]["mec_naopronto"] for rd in range(1, 31)
                              if ok(D.get((pf, nv, rd, cen)))])
                M = np.clip(M, 1e-4, 1)
                m, lo, hi = np.median(M, 0), np.percentile(M, 10, 0), np.percentile(M, 90, 0)
                ax.fill_between(GRADE[sel], lo[sel], hi[sel], color=COR[cen], alpha=0.18, lw=0)
                ax.plot(GRADE[sel], m[sel], color=COR[cen], lw=1.5)
            ax.set_xscale("log")
            ax.set_xlim(0.5, 60)
            ax.xaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5, 10, 20, 50]))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
            ax.xaxis.set_minor_formatter(NullFormatter())
            logy(ax, 1e-4, 1.5, [1e-4, 1e-3, 1e-2, 1e-1, 1], lambda v: rot.get(v, ""))
            if lin == 0:
                ax.set_title(NOME[pf])
            if col == 0:
                ax.set_ylabel(("no background" if nv == 0 else f"background {nv}%") + "\n\nframes not ready")
            if lin == 2 and col == 1:
                ax.set_xlabel("Deadline $D$ for the network delay (ms, log)")
    legenda(fig, 1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(os.path.join(MONO, "results-frame-deadline.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    calibracao()
    niveis()
    pareada()
    carga()
    taxa()
    prazo()
    print("figures in", MONO)
