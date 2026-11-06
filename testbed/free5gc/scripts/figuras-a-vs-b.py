#!/usr/bin/env python3
"""
Figuras da campanha A x B em PNG, rotuladas em ingles, prontas para slide.
Le o que campanha-a-vs-b.py ja' gravou; nao mede nada e nao toca no cluster.

O RECORTE: so' a-mec x b-mec -- UPF centralizada contra dUPF com Local
Breakout, com o MESMO destino (a aplicacao MEC na borda) e a mesma carga. E'
a comparacao do TG1 4.4, e a unica em que so' a ancora do plano de usuario
muda de lugar. Os caminhos remotos nao entram: mudar o destino muda tambem
quantas UPFs o trafego atravessa, e a comparacao deixa de isolar o LBO.

AS TRES FIGURAS

    fig1-network-delay.png    O atraso tipico. Boxplot do p50 de CADA RODADA
                              (n = 30 por cenario), com as rodadas ao lado.
    fig2-network-jitter.png   O mesmo, para o jitter de rede.
    fig3-tail-latency.png     A CAUDA: CCDF calculada dentro de cada rodada,
                              desenhada como mediana + envelope min-max entre
                              as rodadas. E' a figura que separa os cenarios.

    A UNIDADE E' A RODADA, nao o quadro. Os ~3.580 quadros de uma rodada saem
    do mesmo deploy e sao correlacionados: juntar 107 mil quadros numa caixa
    faria a figura prometer n = 107.000 quando o n independente e' 30. Toda
    caixa aqui tem 30 pontos, e a CCDF e' calculada por rodada antes de ser
    agregada -- assim o envelope mostra a variacao ENTRE rodadas.

    O destaque no cabecalho e' pareado: mediana das diferencas DENTRO de cada
    rodada, mais em quantas rodadas o B ficou menor. Diferenca de medianas
    nao seria pareada e jogaria fora o que o desenho da campanha comprou.

Uso:
    python3 scripts/figuras-a-vs-b.py resultados-a-vs-b/teleoperacao
    python3 scripts/figuras-a-vs-b.py resultados-a-vs-b/teleoperacao --stat mean
"""
import argparse
import csv
import glob
import json
import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    sys.exit("falta matplotlib: pip3 install --user matplotlib")

# (chave, cenario, rotulo no eixo)
CAMINHOS = [("a-mec", "a", "A: centralized UPF"), ("b-mec", "b", "B: dUPF with LBO")]
STATS = {"p50": ("net_p50", "median"), "mean": ("net_media", "mean")}

# so' para o rotulo da figura; a pasta continua com o nome do perfil
NOME_EN = {"teleoperacao": "teleoperation", "ar-industrial": "industrial AR",
           "vr-cloud": "cloud VR", "vr-360": "360° VR", "vr-extremo": "extreme VR"}

# paleta categorica validada, slots 1 e 2
COR = {"a": "#eb6834", "b": "#2a78d6"}
CEN = {"a": "A: centralized UPF", "b": "B: dUPF with local breakout"}
SUP, TINTA, TINTA2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"

POS = [1.0, 2.2]


# --------------------------------------------------------------------------
# dados
# --------------------------------------------------------------------------
def le_rodadas(raiz):
    p = os.path.join(raiz, "a-vs-b-por-rodada.csv")
    if not os.path.exists(p):
        sys.exit(f"nao achei {p} -- rode campanha-a-vs-b.py --so-comparar {raiz} antes")
    with open(p) as fh:
        linhas = [r for r in csv.DictReader(fh) if r.get("par_valido") == "1"]
    if not linhas:
        sys.exit(f"nenhuma rodada com par valido em {p}")
    return linhas


def coluna(linhas, sufixo, div):
    """{chave: [(rodada, valor), ...]} para uma coluna do CSV da campanha."""
    out = {}
    for chave, _, _ in CAMINHOS:
        vs = []
        for r in linhas:
            v = r.get(f"{chave}_{sufixo}")
            if v not in (None, ""):
                vs.append((int(r["rodada"]), float(v) / div))
        out[chave] = vs
    return out


def pareado(linhas, sufixo, div):
    """Diferenca A-B DENTRO de cada rodada: mediana, % e em quantas o B ganhou."""
    d, pc = [], []
    for r in linhas:
        a, b = r.get(f"a-mec_{sufixo}"), r.get(f"b-mec_{sufixo}")
        if a in (None, "") or b in (None, ""):
            continue
        a, b = float(a), float(b)
        d.append((a - b) / div)
        if a:
            pc.append((1 - b / a) * 100)
    if not d:
        return None
    return {"n": len(d), "med": float(np.median(d)),
            "pct": float(np.median(pc)) if pc else None,
            "ganhou": sum(1 for x in d if x > 0)}


def le_quadros(raiz, perfil, chave, cen, nums):
    """{rodada: array de net_rtt em ms}, quadro a quadro."""
    out = {}
    for n in nums:
        vs = []
        alvo = os.path.join(raiz, f"rodada-{n:02d}", cen, perfil, "run-*", chave + ".csv")
        for f in sorted(glob.glob(alvo)):
            with open(f) as fh:
                for r in csv.DictReader(fh):
                    try:
                        vs.append(float(r["net_us"]) / 1000.0)
                    except (KeyError, TypeError, ValueError):
                        pass
        if vs:
            out[n] = np.array(sorted(vs))
    return out


def carga(raiz, perfil):
    for f in sorted(glob.glob(os.path.join(raiz, "rodada-*", "*", perfil, "campanha.json"))):
        with open(f) as fh:
            c = (json.load(fh) or {}).get("carga")
        if c:
            return (f'{c["bitrate_mbps"]} Mbps @ {c["fps"]} fps, '
                    f'{c["pose_hz"]} Hz pose, {c["mtu"]} B MTU')
        break
    return ""


# --------------------------------------------------------------------------
# estilo
# --------------------------------------------------------------------------
def moldura(titulo, sub, destaque, rodape, larg=8.8, alt=6.8):
    fig, ax = plt.subplots(figsize=(larg, alt))
    fig.patch.set_facecolor(SUP)
    ax.set_facecolor(SUP)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
        ax.spines[lado].set_linewidth(1)
    ax.tick_params(colors=TINTA2, labelsize=12, length=0)
    fig.text(0.068, 0.965, titulo, fontsize=18, color=TINTA, fontweight="600", va="top")
    fig.text(0.068, 0.917, sub, fontsize=12, color=TINTA2, va="top")
    if destaque:
        fig.text(0.068, 0.873, destaque, fontsize=13, color=TINTA, fontweight="600", va="top")
    for i, linha in enumerate(rodape):
        fig.text(0.068, 0.135 - i * 0.033, linha, fontsize=10.5, color=TINTA2, va="top")
    return fig, ax


def caixas(ax, vals, casas):
    """Boxplot de Tukey + as rodadas ao lado. Devolve o topo util do eixo."""
    dados = [[v for _, v in vals[c]] for c, _, _ in CAMINHOS]
    bp = ax.boxplot(dados, positions=POS, widths=0.5, patch_artist=True,
                    showfliers=False, whis=1.5, zorder=3)
    for i, (chave, cen, _) in enumerate(CAMINHOS):
        cor = COR[cen]
        bp["boxes"][i].set(edgecolor=cor, linewidth=2)
        bp["boxes"][i].set_alpha(None)
        bp["boxes"][i].set_facecolor(matplotlib.colors.to_rgba(cor, 0.12))
        bp["medians"][i].set(color=cor, linewidth=3.2)
        for k in ("whiskers", "caps"):
            for art in bp[k][2 * i:2 * i + 2]:
                art.set(color=cor, linewidth=2)

    rng = np.random.default_rng(1789)
    dentro = []
    for i, (chave, cen, _) in enumerate(CAMINHOS):
        v = np.array([x for _, x in vals[chave]])
        x = POS[i] - 0.38 + rng.uniform(-0.055, 0.055, len(v))
        ax.scatter(x, v, s=30, color=COR[cen], alpha=0.5, linewidths=0.8,
                   edgecolors=SUP, zorder=4)
        ax.annotate(f"{np.median(v):.{casas}f}", (POS[i] + 0.29, float(np.median(v))),
                    fontsize=13, color=TINTA, fontweight="600", va="center", ha="left", zorder=6)
        q1, q3 = np.percentile(v, [25, 75])
        f = 1.5 * (q3 - q1)
        d = v[(v >= q1 - f) & (v <= q3 + f)]
        dentro += [d.min(), d.max()]
    return min(dentro), max(dentro)


def marca_fora(ax, vals, topo, casas, unidade):
    """Rodada que nao cabe na escala vira triangulo no teto, com rotulo."""
    for i, (chave, cen, _) in enumerate(CAMINHOS):
        for n, v in vals[chave]:
            if v > topo:
                x = POS[i] - 0.38
                ax.scatter([x], [topo * 0.995], marker="^", s=90, color=COR[cen],
                           edgecolors=SUP, linewidths=1.2, zorder=7)
                ax.annotate(f"round {n}: {v:.{casas}f} {unidade}", (x + 0.09, topo * 0.99),
                            fontsize=10.5, color=TINTA2, va="top", ha="left", zorder=7)


def fecha_box(fig, ax, vals, topo, unidade, casas, u_txt):
    marca_fora(ax, vals, topo, casas, u_txt)
    ax.set_ylim(0, topo)
    ax.set_xticks(POS)
    ax.set_xticklabels([r for _, _, r in CAMINHOS], fontsize=13.5, color=TINTA)
    ax.set_xlim(0.42, 2.88)
    ax.set_ylabel(unidade, fontsize=12, color=TINTA2)
    ax.grid(axis="y", color=GRADE, lw=1, zorder=0)
    ax.set_axisbelow(True)
    fig.subplots_adjust(left=0.115, right=0.975, top=0.80, bottom=0.215)


def grava(fig, alvo, dpi):
    fig.savefig(alvo, dpi=dpi, facecolor=SUP)
    plt.close(fig)
    return alvo


# --------------------------------------------------------------------------
# figuras
# --------------------------------------------------------------------------
def fig_delay(linhas, stat, perfil, crg, saida, dpi):
    suf, nome = STATS[stat]
    vals = coluna(linhas, suf, 1000.0)
    par = pareado(linhas, suf, 1000.0)
    fig, ax = moldura(
        f"Network round-trip delay — one {nome} per round",
        f"{NOME_EN.get(perfil, perfil)} profile · {crg} · {len(linhas)} paired rounds",
        f"Local breakout is {par['med']:.2f} ms faster ({par['pct']:.0f}%) — "
        f"lower in {par['ganhou']} of {par['n']} rounds",
        ["Box = quartiles, line = median across rounds, whiskers = 1.5 × IQR; each dot is one round.",
         "Both scenarios serve the same MEC application at the edge, under the same load and UE:",
         "only the user-plane anchor moves. Gain above = median of within-round differences."])
    lo, hi = caixas(ax, vals, 2)
    fecha_box(fig, ax, vals, hi * 1.22, "ms", 2, "ms")
    return grava(fig, os.path.join(saida, "fig1-network-delay.png"), dpi)


def fig_jitter(linhas, perfil, crg, saida, dpi):
    vals = coluna(linhas, "jitter_net", 1.0)
    par = pareado(linhas, "jitter_net", 1.0)
    fig, ax = moldura(
        "Network jitter — one value per round",
        f"{NOME_EN.get(perfil, perfil)} profile · {crg} · {len(linhas)} paired rounds",
        f"Local breakout is {par['med']:.0f} µs steadier ({par['pct']:.0f}%) — "
        f"lower in {par['ganhou']} of {par['n']} rounds",
        ["Box = quartiles, line = median across rounds, whiskers = 1.5 × IQR; each dot is one round.",
         "Jitter = RFC 3550 interarrival jitter over the per-frame delay series (EWMA, gain 1/16).",
         "Lower and tighter is better. Gain above = median of within-round differences."])
    lo, hi = caixas(ax, vals, 0)
    fecha_box(fig, ax, vals, hi * 1.22, "µs", 0, "µs")
    return grava(fig, os.path.join(saida, "fig2-network-jitter.png"), dpi)


def fig_cauda(quadros, perfil, crg, saida, dpi):
    """CCDF por rodada: mediana + envelope min-max entre as rodadas."""
    grade = np.logspace(np.log10(0.4), np.log10(500), 400)
    faixa = {}
    for chave, _, _ in CAMINHOS:
        p99 = [float(np.percentile(v, 99)) for v in quadros[chave].values()]
        faixa[chave] = (min(p99), max(p99))

    fig, ax = moldura(
        "Tail of the network delay — how far the worst frames go",
        f"{NOME_EN.get(perfil, perfil)} profile · {crg} · {len(quadros['b-mec'])} paired rounds",
        f"Per-round p99 stays within {faixa['b-mec'][0]:.1f}–{faixa['b-mec'][1]:.1f} ms with LBO, "
        f"against {faixa['a-mec'][0]:.1f}–{faixa['a-mec'][1]:.0f} ms centralized",
        ["Line = median across rounds, band = min-to-max envelope across rounds. Both axes are logarithmic.",
         "Read it as: the fraction of frames whose round-trip delay exceeded the value on the x axis.",
         "Floor at 10⁻³ — with ~3,580 frames per round, anything rarer is a few frames and is not resolved."],
        larg=10.4, alt=6.9)

    for chave, cen, _ in CAMINHOS:
        c = np.vstack([np.array([(v > x).mean() for x in grade])
                       for _, v in sorted(quadros[chave].items())])
        med, lo, hi = np.median(c, axis=0), c.min(axis=0), c.max(axis=0)
        ax.fill_between(grade, np.maximum(lo, 1e-4), np.maximum(hi, 1e-4),
                        color=COR[cen], alpha=0.16, lw=0, zorder=2)
        ax.plot(grade, np.maximum(med, 1e-4), color=COR[cen], lw=2.4, zorder=3,
                solid_capstyle="round", label=CEN[cen])

    for y, rot in ((1e-2, "p99"), (1e-3, "p99.9")):
        ax.axhline(y, color=GRADE, lw=1, zorder=1)
        ax.annotate(rot, (445, y), fontsize=11, color=TINTA2, va="center", ha="left",
                    annotation_clip=False)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.9, 420)
    ax.set_ylim(1e-3, 1.0)
    ax.set_xlabel("network round-trip delay (ms)", fontsize=12, color=TINTA2)
    ax.set_ylabel("fraction of frames above x", fontsize=12, color=TINTA2)
    ax.set_xticks([1, 2, 5, 10, 20, 50, 100, 200, 400])
    ax.set_xticklabels(["1", "2", "5", "10", "20", "50", "100", "200", "400"])
    ax.grid(which="major", color=GRADE, lw=1, zorder=0)
    ax.set_axisbelow(True)
    lg = ax.legend(loc="lower left", frameon=False, fontsize=11.5, handlelength=1.4)
    for t in lg.get_texts():
        t.set_color(TINTA2)
    fig.subplots_adjust(left=0.095, right=0.928, top=0.80, bottom=0.245)
    return grava(fig, os.path.join(saida, "fig3-tail-latency.png"), dpi)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", help="a pasta do perfil, ex.: resultados-a-vs-b/teleoperacao")
    ap.add_argument("--stat", default="p50", choices=sorted(STATS),
                    help="o que a fig1 resume de cada rodada (default: p50; a media "
                         "de uma rodada e' refem da cauda daquela rodada)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--saida", help="default: <pasta>/figuras")
    args = ap.parse_args()

    raiz = os.path.abspath(args.pasta)
    if not os.path.isdir(raiz):
        sys.exit(f"nao existe: {raiz}")
    perfil = os.path.basename(raiz.rstrip("/"))
    saida = os.path.abspath(args.saida) if args.saida else os.path.join(raiz, "figuras")
    os.makedirs(saida, exist_ok=True)

    linhas = le_rodadas(raiz)
    nums = [int(r["rodada"]) for r in linhas]
    crg = carga(raiz, perfil)
    quadros = {c: le_quadros(raiz, perfil, c, cen, nums) for c, cen, _ in CAMINHOS}
    vazios = [c for c in quadros if not quadros[c]]
    if vazios:
        sys.exit(f'sem amostra bruta para {", ".join(vazios)} em {raiz}')

    feitos = [fig_delay(linhas, args.stat, perfil, crg, saida, args.dpi),
              fig_jitter(linhas, perfil, crg, saida, args.dpi),
              fig_cauda(quadros, perfil, crg, saida, args.dpi)]

    d, j = coluna(linhas, STATS[args.stat][0], 1000.0), coluna(linhas, "jitter_net", 1.0)
    print(f"\n{len(linhas)} rodadas pareadas, perfil {perfil}")
    print(f'  {"cenario":<8}{"delay ms":>22}{"jitter us":>20}{"p99 por rodada ms":>24}')
    for c, _, _ in CAMINHOS:
        dv = np.array([x for _, x in d[c]])
        jv = np.array([x for _, x in j[c]])
        p99 = [float(np.percentile(v, 99)) for v in quadros[c].values()]
        print(f"  {c:<8}{f'{np.median(dv):.2f} ({dv.min():.2f}..{dv.max():.2f})':>22}"
              f"{f'{np.median(jv):.0f} ({jv.min():.0f}..{jv.max():.0f})':>20}"
              f"{f'{np.median(p99):.2f} ({min(p99):.2f}..{max(p99):.2f})':>24}")
    for nome, suf, div, u in (("delay", STATS[args.stat][0], 1000.0, "ms"),
                              ("jitter", "jitter_net", 1.0, "us")):
        p = pareado(linhas, suf, div)
        print(f"  pareado {nome}: mediana {p['med']:+.2f} {u} ({p['pct']:.1f}%), "
              f"B menor em {p['ganhou']}/{p['n']} rodadas")
    print()
    for f in feitos:
        print(f"  -> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
