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

from paired_stats import (APP, AQUI, CAP_MED, D, EXCL, NIVEIS, NOME, PERFIS, PERFIS_TODOS, R, ic_mediana, kpi, mantida, med, ok,
                   pares)

OUT = os.path.join(AQUI, "out", "tables")
os.makedirs(OUT, exist_ok=True)
CAL = os.path.join(os.path.dirname(AQUI), "calibration-data")
LV = {0: "none", 50: "50\\%", 80: "80\\%", 95: "95\\%", 99: "99\\%"}


def n(x, c=3, sinal=False):
    if x is None:
        return "--"
    s = f"{x:+.{c}f}" if sinal else f"{x:.{c}f}"
    return s.replace("-", "$-$").replace("+", "$+$") if sinal else s.replace("-", "$-$")


def grava(nome, linhas):
    open(os.path.join(OUT, nome), "w", encoding="utf-8").write("\n".join(linhas) + "\n")


RES = {}
for pf in PERFIS_TODOS:
    for nv in NIVEIS:
        P = pares(pf, nv)
        RES[(pf, nv)] = {k: kpi(P, k, dv) for k, dv in (
            ("net_p50", 1000), ("net_p99", 1000), ("csv_p999", 1), ("jitter", 1), ("perda", 1), ("incompl", 1),
            ("m2p_p50", 1000))}
        for dl in ("3", "5", "10"):
            A = [a["mec_prazo"][dl] * 100 for _, a, b in P]
            B = [b["mec_prazo"][dl] * 100 for _, a, b in P]
            RES[(pf, nv)]["prazo" + dl] = {"A": med(A), "B": med(B)}

# ---------------------------------------------------------------- validity (6 profiles)
L = []
for pf in PERFIS_TODOS:
    a = sum(1 for rd in range(1, 31) for nv in NIVEIS if (D.get((pf, nv, rd, "a")) or {}).get("concluiu"))
    b = sum(1 for rd in range(1, 31) for nv in NIVEIS if (D.get((pf, nv, rd, "b")) or {}).get("concluiu"))
    kept = sum(1 for rd in range(1, 31) if (pf, rd) not in EXCL)
    L.append(f"{NOME[pf]} & {APP[pf]:.0f} & {a} & {b} & {kept} & " + " & ".join(str(len(pares(pf, nv))) for nv in NIVEIS)
             + " \\\\")
grava("res_validity.tex", L)

# ---------------------------------------------------------------- without background (6 profiles)
L = []
for pf in PERFIS_TODOS:
    r = RES[(pf, 0)]["net_p50"]
    L.append(f"{NOME[pf]} & {APP[pf]:.0f} & {n(r['A'])} & {n(r['B'])} & {n(r['d'][0], 3, True)} & "
             f"[{n(r['d'][1], 3, True)}, {n(r['d'][2], 3, True)}] & {r['pct']:.1f}\\% & {r['win']}/{r['n']} \\\\")
grava("res_baseline.tex", L)

# ---------------------------------------------------------------- summary per level (6 profiles)
L = []
for pf in PERFIS_TODOS:
    c = [f"{n(RES[(pf, nv)]['net_p50']['d'][0], 2, True)} ({RES[(pf, nv)]['net_p50']['pct']:.0f}\\%)" for nv in NIVEIS]
    L.append(f"{NOME[pf]} & " + " & ".join(c) + " \\\\")
grava("res_summary.tex", L)

# ---------------------------------------------------------------- effective load (6 profiles)
cap = CAP_MED
L = []
for pf in PERFIS_TODOS:
    c = []
    for nv in NIVEIS[1:]:
        v = nv + APP[pf] / cap * 100
        c.append(f"\\textbf{{{v:.1f}\\%}}" if v >= 100 else f"{v:.1f}\\%")
    L.append(f"{NOME[pf]} & {APP[pf]:.0f} & " + " & ".join(c) + " \\\\")
grava("res_load.tex", L)

# ---------------------------------------------------------------- deadline and quality (3 profiles)
L = []
cel = lambda v: "$<$0.01" if v < 0.005 else f"{v:.2f}"
for i, pf in enumerate(PERFIS):
    if i:
        L.append("\\addlinespace")
    for nv in NIVEIS:
        r = RES[(pf, nv)]
        L.append(f"{NOME[pf] if nv == 0 else ''} & {LV[nv]} & " + " & ".join(
            f"{cel(r['prazo' + dl]['A'])} & {cel(r['prazo' + dl]['B'])}" for dl in ("3", "5", "10")) + " \\\\")
grava("res_deadline.tex", L)

L = []
for i, pf in enumerate(PERFIS):
    if i:
        L.append("\\addlinespace")
    for nv in NIVEIS:
        r = RES[(pf, nv)]
        L.append(f"{NOME[pf] if nv == 0 else ''} & {LV[nv]} & {n(r['net_p99']['A'], 2)} & {n(r['net_p99']['B'], 2)} & "
                 f"{n(r['csv_p999']['A'], 2)} & {n(r['csv_p999']['B'], 2)} & {r['jitter']['A']:.0f} & "
                 f"{r['jitter']['B']:.0f} & {n(r['perda']['A'], 3)} & {n(r['perda']['B'], 3)} & "
                 f"{n(r['incompl']['A'], 2)} & {n(r['incompl']['B'], 2)} \\\\")
grava("res_quality.tex", L)


# ---------------------------------------------------------------- traversals (3 profiles)
def inc(pf, nv, cen, p, okf):
    d = []
    for rd in range(1, 31):
        r, r0 = D.get((pf, nv, rd, cen)), D.get((pf, 0, rd, cen))
        if okf(r) and okf(r0) and r.get(p + "_net_p50") is not None and r0.get(p + "_net_p50") is not None:
            d.append((r[p + "_net_p50"] - r0[p + "_net_p50"]) / 1000)
    return ic_mediana(d)


okrem = lambda r: bool(r and r["concluiu"] and r.get("f_ligado") is not False and mantida(r))
L = []
for i, pf in enumerate(PERFIS):
    if i:
        L.append("\\addlinespace")
    for nv in NIVEIS[1:]:
        am, brm, bm = inc(pf, nv, "a", "mec", ok), inc(pf, nv, "b", "remoto", okrem), inc(pf, nv, "b", "mec", ok)
        razao = "--" if brm[0] <= 0.2 else f"{am[0] / brm[0]:.1f}"
        bmu = round(bm[0] * 1000)
        L.append(f"{NOME[pf] if nv == 50 else ''} & {LV[nv]} & {n(am[0], 2, True)} & {n(brm[0], 2, True)} & "
                 + ("$\\pm$0" if bmu == 0 else n(bmu, 0, True)) + f" & {razao} \\\\")
grava("res_traversal.tex", L)


# ---------------------------------------------------------------- exclusions (appendix)
CEN = {"a": "A", "b": "B"}
L = []
for (pf, rd), e in sorted(EXCL.items(), key=lambda kv: (PERFIS_TODOS.index(kv[0][0]), kv[0][1])):
    if e[0] == "cap":
        motivo = f"Capacity {e[1]:.0f}~Mbps ($<$90\\% of the median)"
    else:
        motivo = f"Alert: {CEN[e[1]]} at {e[2]:.2f}~ms (others {e[3]:.2f}~ms)"
    L.append(f"{NOME[pf]} & {rd} & all & both & {motivo} \\\\")
grava("app_excl_rounds.tex", L)


def motivo_run(r):
    if not r or not r.get("concluiu"):
        return "Not completed (PDU session not established)"
    if r.get("f_problemas") and any("GTP-U" in p for p in r["f_problemas"]):
        return "Background not observed at its cell"
    fr = r.get("f_fracao_entregue")
    if fr is not None and r["nivel"] and fr < 0.9:
        return f"Background at {fr * 100:.0f}\\% of the requested rate"
    g = " ".join(r.get("guardas") or [])
    if "poses" in g:
        import re
        # The pattern matches the Portuguese warning recorded in the data ("received N of M poses").
        m = re.search(r"recebeu (\d+) das (\d+) poses", g)
        return f"Server received {int(m.group(1)) / int(m.group(2)) * 100:.0f}\\% of the poses"
    return "Quality check of the generator"


L = []
for pf in PERFIS_TODOS:
    for nv in NIVEIS:
        for rd in range(1, 31):
            if (pf, rd) in EXCL:
                continue
            for cen in "ab":
                r = D.get((pf, nv, rd, cen))
                if not ok(r):
                    L.append(f"{NOME[pf]} & {rd} & {LV[nv]} & {CEN[cen]} & {motivo_run(r)} \\\\")
grava("app_excl_runs.tex", L)


# ---------------------------------------------------------------- appendix tables (6 profiles)
def tab_kpi(nome, k, cv, cd):
    L = []
    for i, pf in enumerate(PERFIS_TODOS):
        if i:
            L.append("\\addlinespace")
        for nv in NIVEIS:
            r = RES[(pf, nv)][k]
            t = r["t"]
            L.append(f"{NOME[pf] if nv == 0 else ''} & {LV[nv]} & {r['n']} & {n(r['A'], cv)} & {n(r['B'], cv)} & "
                     f"{n(r['d'][0], cd, True)} & [{n(r['d'][1], cd, True)}, {n(r['d'][2], cd, True)}] & "
                     f"{n(t['media'], cd, True)} & [{n(t['ic'][0], cd, True)}, {n(t['ic'][1], cd, True)}] & "
                     f"{r['win']}/{r['n']} \\\\")
    grava(nome, L)


tab_kpi("app_p50.tex", "net_p50", 3, 3)
tab_kpi("app_p99.tex", "net_p99", 2, 2)
tab_kpi("app_mtp.tex", "m2p_p50", 2, 2)

# ---------------------------------------------------------------- calibration (6 profiles)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}
T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896, 8: 0.889}
cal = {}
for d in sorted(glob.glob(os.path.join(CAL, "2026*"))):
    j = json.load(open(os.path.join(d, "calibracao.json")))
    cal[j["args"]["perfil"]] = j
L1, L2 = [], []
for pf in PERFIS_TODOS:
    j = cal[pf]
    a = j["agregados"]
    p = {k: a[k]["net_p50"]["mediana"] for k in a}
    sd = {k: a[k]["net_p50"]["desvio"] for k in a}
    piso = max(p["C0-tester"], p["C0-borda"], p["C0-nucleo"])
    v1, v2 = sd["C2-borda"] ** 2 / 5, sd["C2-nucleo"] ** 2 / 5
    gl = (v1 + v2) ** 2 / (v1 ** 2 / 4 + v2 ** 2 / 4)
    g = max(1, min(8, int(gl)))
    mde = (T975[g] + T80[g]) * math.sqrt(v1 + v2)
    dif = p["C2-nucleo"] - p["C2-borda"]
    L1.append(f"{NOME[pf]} & {piso:.0f} & {p['C1-borda']:.0f} & {p['C1-nucleo']:.0f} & {p['C2-borda']:.0f} & "
              f"{p['C2-nucleo']:.0f} & {sd['C2-borda']:.0f} / {sd['C2-nucleo']:.0f} & {mde:.0f} & "
              f"{dif:.0f} ({dif / mde:.1f}$\\times$) \\\\")
    V1, V2, V3 = j["v1"], j["v2"], j["v3"]
    b, r = V3["caminhos"]["borda"], V3["caminhos"]["nucleo"]
    L2.append(f"{NOME[pf]} & ${V1['net_rtt']['inclinacao']:+.4f}$ & {V1['excursao_pct']:.2f}\\% & "
              f"{V2['net_rtt']['inclinacao']:.4f} & {V2['net_rtt']['intercepto']:.0f} & "
              f"${b['diferenca_us']['p50']:+.0f}$ / ${r['diferenca_us']['p50']:+.0f}$ & "
              f"{b['limite_us']['p50'][1]:.0f} \\\\")
grava("cal_results.tex", L1)
grava("cal_validations.tex", L2)
print("tables in", OUT, "| median capacity", round(cap), "Mbps")
