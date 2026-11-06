"""Paired A x B statistics of the infrastructure metrics (profiles of the detailed
study, which have complete metrics). Same design as the latency analysis: the
round is the unit, the pairs are the valid pairs of that analysis, and the
median is given with a CI from order statistics.
    python3 infra_stats.py   ->  infra-pareado.json (and a summary on screen)

Keys of infra-pareado.json: "<profile>|<level>" -> "<column>|A", "|B", "|B-A"
or "|A-B" -> {n, mediana (median), ic (95% CI)}. Columns: brix05 = Edge Node,
brix02 = UE/RAN node, petshopboys = Server Node; *_cpu_pct = % of all cores,
*_cpu_nucleo_max_pct = busiest core, *_nucleos = cores, *_mem_usada_gib = memory
used, *_rx_mbps / *_tx_mbps = traffic of the physical interface.
"""
import csv, gzip, json, math, os, sys
from collections import defaultdict
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "analysis"))
from paired_stats import NIVEIS, PERFIS, ic_mediana, pares   # only reads dados.json
from summarize_windows import carrega, taxa

M = {(r["perfil"], int(r["nivel"]), int(r["rodada"]), r["caminho"]): r
     for r in csv.DictReader(open(os.path.join(AQUI, "metricas-por-janela.csv")))}
J = {(r["perfil"], int(r["nivel"]), int(r["rodada"]), r["caminho"]): (float(r["inicio_epoch"]), float(r["fim_epoch"]))
     for r in csv.DictReader(open(os.path.join(AQUI, "janelas.csv")))}
cpu = carrega("no_cpu_por_modo", lambda r: (r["nodename"], r["mode"]) if r["nodename"] in ("brix-porvir-05", "petshopboys") else None)


def modo(no, m, k):
    a, f = J[k]
    x = taxa(cpu[(no, m)], a, f)
    return x


def v(k, col):
    x = M[k].get(col)
    return None if x in (None, "", "None") else float(x)


res = {}
for pf in PERFIS:
    for nv in NIVEIS:
        lin = defaultdict(list)
        for rd, _, _ in pares(pf, nv):
            ka, kb = (pf, nv, rd, "a-mec"), (pf, nv, rd, "b-mec")
            if ka not in M or kb not in M:
                continue
            for col in ("brix05_cpu_pct", "brix05_cpu_nucleo_max_pct", "brix02_cpu_pct", "brix02_cpu_nucleo_max_pct",
                        "petshopboys_cpu_pct", "petshopboys_rx_mbps", "petshopboys_tx_mbps", "brix05_rx_mbps",
                        "brix05_tx_mbps", "brix05_mem_usada_gib"):
                a, b = v(ka, col), v(kb, col)
                if a is not None and b is not None:
                    lin[col + "|A"].append(a); lin[col + "|B"].append(b); lin[col + "|B-A"].append(b - a)
            for m in ("user", "system", "softirq"):
                a, b = modo("brix-porvir-05", m, ka), modo("brix-porvir-05", m, kb)
                if a is not None and b is not None:
                    lin["brix05_" + m + "_nucleos|B-A"].append(b - a)
            a, b = modo("petshopboys", "idle", ka), modo("petshopboys", "idle", kb)
            if a is not None and b is not None:
                lin["petshopboys_ocupado_nucleos|A-B"].append(b - a)   # idle B - idle A = busy A - busy B
        res[f"{pf}|{nv}"] = {k: dict(n=len(x), mediana=float(np.median(x)), ic=list(ic_mediana(x)[1:]))
                             for k, x in lin.items() if x}
json.dump(res, open(os.path.join(AQUI, "infra-pareado.json"), "w"), indent=1)
if __name__ == "__main__":
    for pf in PERFIS:
        for nv in NIVEIS:
            r = res[f"{pf}|{nv}"]
            g = lambda k, c=2: f"{r[k]['mediana']:.{c}f}" if k in r else "-"
            gi = lambda k, c=2: f"{r[k]['mediana']:+.{c}f} [{r[k]['ic'][0]:+.{c}f},{r[k]['ic'][1]:+.{c}f}]" if k in r else "-"
            print(f"{pf:12} {nv:2d} n={r['brix05_cpu_pct|B-A']['n']:2d} | brix05 A {g('brix05_cpu_pct|A',1)}% B {g('brix05_cpu_pct|B',1)}% d {gi('brix05_cpu_pct|B-A',1)}"
                  f" | busiest core A {g('brix05_cpu_nucleo_max_pct|A',1)} B {g('brix05_cpu_nucleo_max_pct|B',1)}"
                  f" | modos B-A user {gi('brix05_user_nucleos|B-A',3)} sys {gi('brix05_system_nucleos|B-A',3)} softirq {gi('brix05_softirq_nucleos|B-A',3)}")
            print(f"{'':15} brix02 A {g('brix02_cpu_pct|A',1)} B {g('brix02_cpu_pct|B',1)} (busiest core {g('brix02_cpu_nucleo_max_pct|A',1)}/{g('brix02_cpu_nucleo_max_pct|B',1)})"
                  f" | petshop busy A-B {gi('petshopboys_ocupado_nucleos|A-B',3)} cores | petshop rx B-A {gi('petshopboys_rx_mbps|B-A',1)} tx B-A {gi('petshopboys_tx_mbps|B-A',1)} Mbps"
                  f" | mem brix05 A {g('brix05_mem_usada_gib|A',2)} B {g('brix05_mem_usada_gib|B',2)}")
