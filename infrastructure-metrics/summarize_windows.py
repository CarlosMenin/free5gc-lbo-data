"""Mean CPU, memory and network in each measurement window (windows.csv).

Counters: difference between the first and the last sample inside the window,
divided by the interval (with a sample every 30 s, it covers 30 s of the 55 s
measured).
    python3 summarize_windows.py   ->  metrics-per-window.csv
"""
import collections
import csv
import gzip
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
NODES = ["brix-porvir-02", "brix-porvir-03", "brix-porvir-05", "petshopboys", "metallica"]
SHORT = {"brix-porvir-02": "brix02", "brix-porvir-03": "brix03", "brix-porvir-05": "brix05",
         "petshopboys": "petshopboys", "metallica": "metallica"}
NIC = {"brix-porvir-02": "enp3s0", "brix-porvir-03": "enp3s0", "brix-porvir-05": "enp3s0",
       "petshopboys": "eno1", "metallica": "eno1"}
NCPU = {"brix-porvir-02": 4, "brix-porvir-03": 4, "brix-porvir-05": 4, "petshopboys": 80, "metallica": 40}
ROLES = {  # (pod prefix, container) -> column
    ("free5gc-upf-", "upf"): "central_upf", ("free5gc-i-upf-", "upf"): "i_upf", ("free5gc-psa-upf-", "upf"): "psa_upf",
    ("free5gc-mec-app-", "vr-server"): "mec_vr_server", ("free5gc-remote-app-", "vr-server"): "remote_vr_server",
    ("free5gc-ueransim-", "gnb"): "ueransim_gnb", ("free5gc-ueransim-", "ue"): "ueransim_ue",
    ("free5gc-ueransim-", "vr-client"): "vr_client", ("background-ueransim-", "gnb"): "background_gnb",
}


def load_series(name, key):
    """Series of a raw file, grouped by key(row): {key: (timestamps, values)}."""
    s = collections.defaultdict(lambda: ([], []))
    with gzip.open(os.path.join(RAW, name + ".csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            k = key(r)
            if k is None:
                continue
            s[k][0].append(int(r["ts"]))
            s[k][1].append(float(r["value"]))
    return {k: (np.array(t), np.array(v)) for k, (t, v) in s.items()}


def rate(series, a, f):
    """Rate of a counter between the first and the last sample inside [a, f] (or around it)."""
    t, v = series
    i, j = np.searchsorted(t, a), np.searchsorted(t, f, side="right") - 1
    if j - i < 1 or t[j] - t[i] < 25:
        i, j = max(np.searchsorted(t, a) - 1, 0), min(np.searchsorted(t, f), len(t) - 1)
        if j <= i or t[j] - t[i] > 120:
            return None
    d = v[j] - v[i]
    return d / (t[j] - t[i]) if d >= 0 else None


def mean(series, a, f):
    t, v = series
    i, j = np.searchsorted(t, a), np.searchsorted(t, f, side="right")
    return float(v[i:j].mean()) if j > i else None


def main():
    cpu = load_series("node_cpu_by_mode", lambda r: (r["nodename"], r["mode"]))
    core = load_series("node_cpu_per_core_brix", lambda r: (r["nodename"], r["cpu"], r["mode"]))
    mem = load_series("node_memory", lambda r: (r["nodename"], r["__name__"]))
    net = load_series("node_network",
                      lambda r: (r["nodename"], r["__name__"]) if r["device"] == NIC.get(r["nodename"]) else None)

    def role(r):
        for (prefix, container), col in ROLES.items():
            if r["pod"].startswith(prefix) and r["container"] == container:
                return (col, r["pod"])
        return None
    pods = load_series("pod_cpu", role)
    podmem = load_series("pod_memory", role)

    out_rows = []
    for w in csv.DictReader(open(os.path.join(HERE, "windows.csv"))):
        if w["prometheus"] != "1":
            continue
        a, f = float(w["start_epoch"]), float(w["end_epoch"])
        row = dict(w)
        for n in NODES:
            c = SHORT[n]
            idle = rate(cpu[(n, "idle")], a, f) if (n, "idle") in cpu else None
            row[f"{c}_cpu_pct"] = None if idle is None else round(100 * (1 - idle / NCPU[n]), 2)
            if n.startswith("brix"):
                busy = []
                for k in range(NCPU[n]):
                    o = rate(core[(n, str(k), "idle")], a, f) if (n, str(k), "idle") in core else None
                    if o is not None:
                        busy.append(100 * (1 - min(o, 1.0)))
                row[f"{c}_cpu_busiest_core_pct"] = round(max(busy), 2) if busy else None
            total, avail = mem.get((n, "node_memory_MemTotal_bytes")), mem.get((n, "node_memory_MemAvailable_bytes"))
            mt, ma = (mean(total, a, f) if total else None), (mean(avail, a, f) if avail else None)
            row[f"{c}_mem_used_gib"] = None if mt is None or ma is None else round((mt - ma) / 2**30, 3)
            for d, k in (("rx", "node_network_receive_bytes_total"), ("tx", "node_network_transmit_bytes_total")):
                x = rate(net[(n, k)], a, f) if (n, k) in net else None
                row[f"{c}_{d}_mbps"] = None if x is None else round(x * 8 / 1e6, 2)
        for col in sorted(set(ROLES.values())):
            total_cpu, total_mem, found = 0.0, 0.0, False
            for (cc, pod), s in pods.items():
                if cc != col or s[0][0] > f or s[0][-1] < a:
                    continue
                x = rate(s, a, f)
                if x is not None:
                    total_cpu += x
                    found = True
                m = podmem.get((cc, pod))
                if m is not None:
                    y = mean(m, a, f)
                    total_mem += y or 0
            row[f"{col}_cpu_cores"] = round(total_cpu, 4) if found else None
            row[f"{col}_mem_mib"] = round(total_mem / 2**20, 1) if found else None
        out_rows.append(row)
    cols = list(out_rows[0])
    with open(os.path.join(HERE, "metrics-per-window.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print(len(out_rows), "windows summarized,", len(cols), "columns")


if __name__ == "__main__":
    main()
