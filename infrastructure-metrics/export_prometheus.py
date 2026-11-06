"""Export from the Prometheus of the cluster the CPU, memory and network metrics of
the period of the final campaign and of the calibrations, before the 30-day
retention deletes them. Only reads from Prometheus. Needs the cluster.

    kubectl -n monitoring port-forward svc/prometheus-prometheus 19090:9090
    python3 export_prometheus.py [group ...]     (no arguments: all groups)
Output: brutos/*.csv.gz (ts in epoch UTC, labels, value), one file per group.
"""
import csv, datetime, gzip, json, os, sys, time, urllib.parse, urllib.request

PROM = "http://127.0.0.1:19090/api/v1/query_range"
AQUI = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(AQUI, "brutos")
TZ = datetime.timezone(datetime.timedelta(hours=-3))
INI = datetime.datetime(2026, 10, 10, 0, 0, tzinfo=TZ).timestamp()
FIM = datetime.datetime(2026, 10, 19, 0, 0, tzinfo=TZ).timestamp()
PASSO = 30                     # = scrape interval of Prometheus
BLOCO = 86400                  # one day per query: < 11,000 points, within the sample limit
NOS = "brix-porvir-02|brix-porvir-03|brix-porvir-05|petshopboys|metallica"
BRIX = "brix-porvir-02|brix-porvir-03|brix-porvir-05"
J = " * on(instance) group_left(nodename) node_uname_info{nodename=~\"%s\"}"
DEV = 'device=~"enp3s0|eno1|vxlan.calico"'
NS = 'namespace="free5gc"'

GRUPOS = {
    "no_cpu_por_modo": [("node_cpu_seconds_total", 'sum by (nodename, mode) (node_cpu_seconds_total' + J % NOS + ')')],
    "no_cpu_por_nucleo_brix": [("node_cpu_seconds_total", 'node_cpu_seconds_total' + J % BRIX)],
    "no_memoria": [("node_memory_%s_bytes" % m, 'node_memory_%s_bytes' % m + J % NOS)
                   for m in ("MemTotal", "MemAvailable", "MemFree", "Buffers", "Cached")],
    "no_rede": [("node_network_%s_%s_total" % (d, k), 'node_network_%s_%s_total{%s}' % (d, k, DEV) + J % NOS)
                for d in ("receive", "transmit") for k in ("bytes", "packets", "drop", "errs")],
    "no_load": [("node_load1", 'node_load1' + J % NOS)],
    "no_softnet": [("node_softnet_%s_total" % k, 'sum by (nodename) (node_softnet_%s_total' % k + J % NOS + ')')
                   for k in ("dropped", "times_squeezed")],
    "pod_cpu": [("container_cpu_usage_seconds_total",
                 'sum by (node, pod, container) (container_cpu_usage_seconds_total{%s, container!=""})' % NS)],
    "pod_cpu_throttled": [("container_cpu_cfs_throttled_seconds_total",
                           'sum by (node, pod, container) (container_cpu_cfs_throttled_seconds_total{%s, container!=""})' % NS)],
    "pod_memoria": [("container_memory_working_set_bytes",
                     'max by (node, pod, container) (container_memory_working_set_bytes{%s, container!=""})' % NS)],
    "pod_rede": [("container_network_%s_total" % k, 'sum by (node, pod, interface) (container_network_%s_total{%s})' % (k, NS))
                 for k in ("receive_bytes", "transmit_bytes", "receive_packets", "transmit_packets",
                           "receive_packets_dropped", "transmit_packets_dropped")],
}


def consulta(expr, a, b):
    url = PROM + "?" + urllib.parse.urlencode({"query": expr, "start": a, "end": b, "step": PASSO})
    for tentativa in range(4):
        try:
            r = json.load(urllib.request.urlopen(url, timeout=600))
            if r.get("status") == "success":
                return r["data"]["result"]
            raise RuntimeError(r)
        except Exception as e:
            corpo = e.read()[:300] if hasattr(e, "read") else b""
            print(f"  error (attempt {tentativa + 1}): {e} {corpo}", flush=True)
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))


def main():
    os.makedirs(OUT, exist_ok=True)
    resumo = {}
    so = set(sys.argv[1:])
    for nome, exprs in GRUPOS.items():
        if so and nome not in so:
            continue
        linhas = []
        rotulos = set()
        for metrica, expr in exprs:
            a = INI
            while a < FIM:
                b = min(a + BLOCO, FIM)
                for s in consulta(expr, a, b - PASSO if b < FIM else b):
                    m = dict(s["metric"])
                    m["__name__"] = metrica
                    rotulos |= set(m)
                    for t, v in s["values"]:
                        linhas.append((float(t), m, v))
                a = b
        cols = ["__name__"] + sorted(rotulos - {"__name__"})
        caminho = os.path.join(OUT, nome + ".csv.gz")
        with gzip.open(caminho, "wt", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ts"] + cols + ["valor"])
            for t, m, v in linhas:
                w.writerow([f"{t:.0f}"] + [m.get(c, "") for c in cols] + [v])
        resumo[nome] = {"linhas": len(linhas), "series": len({tuple(sorted(m.items())) for _, m, _ in linhas}),
                        "consultas": [e for _, e in exprs]}
        print(f"{nome:24} {len(linhas):9d} lines  {resumo[nome]['series']:5d} series", flush=True)
    resumo["_periodo"] = {"inicio": datetime.datetime.fromtimestamp(INI, TZ).isoformat(),
                          "fim": datetime.datetime.fromtimestamp(FIM, TZ).isoformat(), "passo_s": PASSO,
                          "exportado_em": datetime.datetime.now(TZ).isoformat()}
    caminho = os.path.join(OUT, "resumo.json")
    if so and os.path.exists(caminho):
        antigo = json.load(open(caminho))
        antigo.update(resumo)
        resumo = antigo
    json.dump(resumo, open(caminho, "w"), indent=1)


if __name__ == "__main__":
    main()
