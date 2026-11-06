"""Flatten the A x B campaign (GTP-U background) and process the per-frame CSV files.

Reads campaign-data/ and writes dados.json next to this script: one record per
run (level, profile, round, scenario) with the summaries of each path, the UPF
counters, the background record, and, from the per-frame CSV, the median and
99.9th percentile of the network delay and the fraction of frames not complete
within each deadline.

Validity uses the functions of the campaign script itself
(testbed/free5gc/scripts/campanha-a-vs-b.py): `_valida` is the validity for
A x B on the MEC path, `_valida_remoto` also for b-remoto x b-mec, so that the
numbers match the reports written during the campaign. File times come from
campaign-data/run-file-times.csv, because git does not keep them.

    python3 load_campaign.py
"""
import glob, importlib.util, json, os
import numpy as np
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.join(BASE, "campaign-data")
AQUI = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("camp", os.path.join(BASE, "testbed", "free5gc", "scripts", "campanha-a-vs-b.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
NIV = {"sem-fundo": 0, "fundo-50": 50, "fundo-80": 80, "fundo-95": 95, "fundo-99": 99}
# Original modification time of each campanha.json (git does not keep it); used to place the run in time.
import csv
MTIME = {r["campanha_json"]: float(r["mtime_epoch"]) for r in csv.DictReader(open(os.path.join(RAIZ, "run-file-times.csv")))}
GRADE = np.logspace(np.log10(0.2), np.log10(300), 120)          # ms, grid of deadlines for the curves
PRAZOS = [1, 2, 3, 5, 10, 20, 50]                                 # ms, deadlines of the tables

def g(d, *ks):
    for k in ks:
        if not isinstance(d, dict): return None
        d = d.get(k)
    return d

def quadros(pasta, perfil, nome):
    f = glob.glob(os.path.join(pasta, perfil, "run-*", nome + ".csv"))
    if not f: return None
    return np.loadtxt(f[0], delimiter=",", skiprows=1, usecols=(1, 5), ndmin=2)

regs = []
for nvdir, nv in NIV.items():
    for pdir in sorted(glob.glob(os.path.join(RAIZ, nvdir, "*"))):
        pf = os.path.basename(pdir)
        for rdir in sorted(glob.glob(os.path.join(pdir, "rodada-*"))):
            rd = int(rdir.rsplit("-", 1)[1])
            for cen in "ab":
                pasta = os.path.join(rdir, cen)
                e = C.carrega(pasta, pf, nv)
                if e is None:
                    regs.append(dict(nivel=nv, perfil=pf, rodada=rd, cen=cen, concluiu=False)); continue
                r = dict(nivel=nv, perfil=pf, rodada=rd, cen=cen, concluiu=True,
                         valida=e["_valida"], valida_remoto=e["_valida_remoto"],
                         guardas=[m[:120] for esc, m in e.get("avisos", []) if esc == "campanha"],
                         placement=e.get("placement"), tentativas=e.get("tentativas"),
                         prova_ancora=g(e, "prova", "mec", "delta", "upf" if cen == "a" else "psa-upf", "rx_pkts"),
                         prova_iupf=g(e, "prova", "mec", "delta", "i-upf", "rx_pkts"),
                         prova_rem_psa=g(e, "prova", "remoto", "delta", "psa-upf", "rx_pkts"),
                         mtime=MTIME[os.path.relpath(os.path.join(pasta, pf, "campanha.json"), RAIZ)])
                fj = e.get("_fundo") or {}
                for k in ("capacidade_mbps", "capacidade_medidas", "pedido_mbps", "cruzou_mbps", "fracao_entregue",
                          "perda_caminho_pct", "problemas", "ligado", "segundos_ligado", "ue_recriado", "atraso_s"):
                    r["f_" + k] = fj.get(k)
                for nome, d in (e.get("campanha") or {}).items():
                    p = nome.split("-")[1] + "_"
                    for k, cam in (("net_p50", ("net_rtt_us", "p50")), ("net_p95", ("net_rtt_us", "p95")),
                                   ("net_p99", ("net_rtt_us", "p99")), ("net_max", ("net_rtt_us", "max")),
                                   ("net_mean", ("net_rtt_us", "mean")), ("m2p_p50", ("m2p_us", "p50")),
                                   ("m2p_p95", ("m2p_us", "p95")), ("hold_p50", ("hold_us", "p50")),
                                   ("jitter", ("jitter_net_us",)), ("perda", ("dl_packet_loss_srv_pct",)),
                                   ("incompl", ("frames_incomplete_pct",)), ("vazao", ("dl_throughput_mbps",)),
                                   ("fr_compl", ("frames_complete",)), ("fr_stats", ("frames_in_stats",)),
                                   ("fr_esper", ("janela", "frames_esperados")), ("rcvbuf", ("saude", "sock_rcvbuf_bytes")),
                                   ("sock_drops", ("saude", "dl_sock_drops")), ("drift", ("saude", "clock_drift_us"))):
                        r[p + k] = g(d, *cam)
                    q = quadros(pasta, pf, nome)
                    if q is None:
                        r[p + "csv"] = False; continue
                    net = np.sort(q[q[:, 0] >= 5.0, 1] / 1000.0)
                    esper = r[p + "fr_esper"] or len(net)
                    r[p + "csv"] = True
                    r[p + "csv_n"] = int(len(net))
                    r[p + "csv_p50"] = float(np.percentile(net, 50)) if len(net) else None
                    r[p + "csv_p999"] = float(np.percentile(net, 99.9)) if len(net) else None
                    idx = np.searchsorted(net, GRADE, side="right")
                    r[p + "naopronto"] = (1 - idx / esper).clip(0, 1).round(6).tolist()
                    r[p + "prazo"] = {str(D): float(1 - np.searchsorted(net, D, side="right") / esper) for D in PRAZOS}
                regs.append(r)
json.dump({"grade": GRADE.tolist(), "prazos": PRAZOS, "regs": regs}, open(os.path.join(AQUI, "dados.json"), "w"))
print(len(regs), "records;", sum(r["concluiu"] for r in regs), "completed runs")
