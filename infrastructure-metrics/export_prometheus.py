"""Export from the Prometheus of the cluster the CPU, memory and network metrics of
the period of the final campaign and of the calibrations, before the 30-day
retention deletes them. Only reads from Prometheus. Needs the cluster.

    kubectl -n monitoring port-forward svc/prometheus-prometheus 19090:9090
    python3 export_prometheus.py [group ...]     (no arguments: all groups)

Output: raw/<group>.csv.gz (ts in epoch UTC, labels, value), one file per group,
and raw/summary.json (queries, lines and series of each group).
"""
import csv
import datetime
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request

PROM = "http://127.0.0.1:19090/api/v1/query_range"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw")
TZ = datetime.timezone(datetime.timedelta(hours=-3))
START = datetime.datetime(2026, 10, 10, 0, 0, tzinfo=TZ).timestamp()
END = datetime.datetime(2026, 10, 19, 0, 0, tzinfo=TZ).timestamp()
STEP = 30                      # = scrape interval of Prometheus
BLOCK = 86400                  # one day per query: < 11,000 points, within the sample limit
NODES = "brix-porvir-02|brix-porvir-03|brix-porvir-05|petshopboys|metallica"
BRIX = "brix-porvir-02|brix-porvir-03|brix-porvir-05"
J = " * on(instance) group_left(nodename) node_uname_info{nodename=~\"%s\"}"
DEV = 'device=~"enp3s0|eno1|vxlan.calico"'
NS = 'namespace="free5gc"'

GROUPS = {
    "node_cpu_by_mode": [("node_cpu_seconds_total", 'sum by (nodename, mode) (node_cpu_seconds_total' + J % NODES + ')')],
    "node_cpu_per_core_brix": [("node_cpu_seconds_total", 'node_cpu_seconds_total' + J % BRIX)],
    "node_memory": [("node_memory_%s_bytes" % m, 'node_memory_%s_bytes' % m + J % NODES)
                    for m in ("MemTotal", "MemAvailable", "MemFree", "Buffers", "Cached")],
    "node_network": [("node_network_%s_%s_total" % (d, k), 'node_network_%s_%s_total{%s}' % (d, k, DEV) + J % NODES)
                     for d in ("receive", "transmit") for k in ("bytes", "packets", "drop", "errs")],
    "node_load": [("node_load1", 'node_load1' + J % NODES)],
    "node_softnet": [("node_softnet_%s_total" % k, 'sum by (nodename) (node_softnet_%s_total' % k + J % NODES + ')')
                     for k in ("dropped", "times_squeezed")],
    "pod_cpu": [("container_cpu_usage_seconds_total",
                 'sum by (node, pod, container) (container_cpu_usage_seconds_total{%s, container!=""})' % NS)],
    "pod_cpu_throttled": [("container_cpu_cfs_throttled_seconds_total",
                           'sum by (node, pod, container) (container_cpu_cfs_throttled_seconds_total{%s, container!=""})' % NS)],
    "pod_memory": [("container_memory_working_set_bytes",
                    'max by (node, pod, container) (container_memory_working_set_bytes{%s, container!=""})' % NS)],
    "pod_network": [("container_network_%s_total" % k, 'sum by (node, pod, interface) (container_network_%s_total{%s})' % (k, NS))
                    for k in ("receive_bytes", "transmit_bytes", "receive_packets", "transmit_packets",
                              "receive_packets_dropped", "transmit_packets_dropped")],
}


def query(expr, a, b):
    url = PROM + "?" + urllib.parse.urlencode({"query": expr, "start": a, "end": b, "step": STEP})
    for attempt in range(4):
        try:
            r = json.load(urllib.request.urlopen(url, timeout=600))
            if r.get("status") == "success":
                return r["data"]["result"]
            raise RuntimeError(r)
        except Exception as e:
            body = e.read()[:300] if hasattr(e, "read") else b""
            print(f"  error (attempt {attempt + 1}): {e} {body}", flush=True)
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {}
    only = set(sys.argv[1:])
    for name, exprs in GROUPS.items():
        if only and name not in only:
            continue
        lines = []
        labels = set()
        for metric, expr in exprs:
            a = START
            while a < END:
                b = min(a + BLOCK, END)
                for s in query(expr, a, b - STEP if b < END else b):
                    m = dict(s["metric"])
                    m["__name__"] = metric
                    labels |= set(m)
                    for t, v in s["values"]:
                        lines.append((float(t), m, v))
                a = b
        cols = ["__name__"] + sorted(labels - {"__name__"})
        path = os.path.join(OUT, name + ".csv.gz")
        with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ts"] + cols + ["value"])
            for t, m, v in lines:
                w.writerow([f"{t:.0f}"] + [m.get(c, "") for c in cols] + [v])
        summary[name] = {"lines": len(lines), "series": len({tuple(sorted(m.items())) for _, m, _ in lines}),
                         "queries": [e for _, e in exprs]}
        print(f"{name:24} {len(lines):9d} lines  {summary[name]['series']:5d} series", flush=True)
    summary["_period"] = {"start": datetime.datetime.fromtimestamp(START, TZ).isoformat(),
                          "end": datetime.datetime.fromtimestamp(END, TZ).isoformat(), "step_s": STEP,
                          "exported_at": datetime.datetime.now(TZ).isoformat()}
    path = os.path.join(OUT, "summary.json")
    if only and os.path.exists(path):
        previous = json.load(open(path))
        previous.update(summary)
        summary = previous
    json.dump(summary, open(path, "w"), indent=1)


if __name__ == "__main__":
    main()
