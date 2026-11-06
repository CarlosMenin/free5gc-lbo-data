"""Mean CPU, memory and network in each measurement window (janelas.csv).

Counters: difference between the first and the last sample inside the window,
divided by the interval (with a sample every 30 s, it covers 30 s of the 55 s
measured).
    python3 summarize_windows.py   ->  metricas-por-janela.csv
"""
import collections, csv, gzip, os, re
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(AQUI, "brutos")
NOS = ["brix-porvir-02", "brix-porvir-03", "brix-porvir-05", "petshopboys", "metallica"]
CURTO = {"brix-porvir-02": "brix02", "brix-porvir-03": "brix03", "brix-porvir-05": "brix05",
         "petshopboys": "petshopboys", "metallica": "metallica"}
NIC = {"brix-porvir-02": "enp3s0", "brix-porvir-03": "enp3s0", "brix-porvir-05": "enp3s0",
       "petshopboys": "eno1", "metallica": "eno1"}
NCPU = {"brix-porvir-02": 4, "brix-porvir-03": 4, "brix-porvir-05": 4, "petshopboys": 80, "metallica": 40}
PAPEIS = {  # pod prefix, container -> column
    ("free5gc-upf-", "upf"): "upf_central", ("free5gc-i-upf-", "upf"): "i_upf", ("free5gc-psa-upf-", "upf"): "psa_upf",
    ("free5gc-mec-app-", "vr-server"): "mec_vr_server", ("free5gc-remote-app-", "vr-server"): "remoto_vr_server",
    ("free5gc-ueransim-", "gnb"): "ueransim_gnb", ("free5gc-ueransim-", "ue"): "ueransim_ue",
    ("free5gc-ueransim-", "vr-client"): "vr_client", ("ruido-ueransim-", "gnb"): "ruido_gnb",
}


def carrega(nome, chave):
    s = collections.defaultdict(lambda: ([], []))
    with gzip.open(os.path.join(BR, nome + ".csv.gz"), "rt") as fh:
        for r in csv.DictReader(fh):
            k = chave(r)
            if k is None:
                continue
            s[k][0].append(int(r["ts"])); s[k][1].append(float(r["valor"]))
    return {k: (np.array(t), np.array(v)) for k, (t, v) in s.items()}


def taxa(serie, a, f):
    t, v = serie
    i, j = np.searchsorted(t, a), np.searchsorted(t, f, side="right") - 1
    if j - i < 1 or t[j] - t[i] < 25:
        i, j = max(np.searchsorted(t, a) - 1, 0), min(np.searchsorted(t, f), len(t) - 1)
        if j <= i or t[j] - t[i] > 120:
            return None
    d = v[j] - v[i]
    return d / (t[j] - t[i]) if d >= 0 else None


def media(serie, a, f):
    t, v = serie
    i, j = np.searchsorted(t, a), np.searchsorted(t, f, side="right")
    return float(v[i:j].mean()) if j > i else None


def main():
    cpu = carrega("no_cpu_por_modo", lambda r: (r["nodename"], r["mode"]))
    nuc = carrega("no_cpu_por_nucleo_brix", lambda r: (r["nodename"], r["cpu"], r["mode"]))
    mem = carrega("no_memoria", lambda r: (r["nodename"], r["__name__"]))
    rede = carrega("no_rede", lambda r: (r["nodename"], r["__name__"]) if r["device"] == NIC.get(r["nodename"]) else None)

    def papel(r):
        for (pref, cont), col in PAPEIS.items():
            if r["pod"].startswith(pref) and r["container"] == cont:
                return (col, r["pod"])
        return None
    pods = carrega("pod_cpu", papel)
    podmem = carrega("pod_memoria", papel)

    saida = []
    for w in csv.DictReader(open(os.path.join(AQUI, "janelas.csv"))):
        if w["prometheus"] != "1":
            continue
        a, f = float(w["inicio_epoch"]), float(w["fim_epoch"])
        lin = dict(w)
        for n in NOS:
            c = CURTO[n]
            ociosa = taxa(cpu[(n, "idle")], a, f) if (n, "idle") in cpu else None
            lin[f"{c}_cpu_pct"] = None if ociosa is None else round(100 * (1 - ociosa / NCPU[n]), 2)
            if n.startswith("brix"):
                ocup = []
                for k in range(NCPU[n]):
                    o = taxa(nuc[(n, str(k), "idle")], a, f) if (n, str(k), "idle") in nuc else None
                    if o is not None:
                        ocup.append(100 * (1 - min(o, 1.0)))
                lin[f"{c}_cpu_nucleo_max_pct"] = round(max(ocup), 2) if ocup else None
            tot, disp = mem.get((n, "node_memory_MemTotal_bytes")), mem.get((n, "node_memory_MemAvailable_bytes"))
            mt, md = (media(tot, a, f) if tot else None), (media(disp, a, f) if disp else None)
            lin[f"{c}_mem_usada_gib"] = None if mt is None or md is None else round((mt - md) / 2**30, 3)
            for d, k in (("rx", "node_network_receive_bytes_total"), ("tx", "node_network_transmit_bytes_total")):
                x = taxa(rede[(n, k)], a, f) if (n, k) in rede else None
                lin[f"{c}_{d}_mbps"] = None if x is None else round(x * 8 / 1e6, 2)
        for col in sorted(set(PAPEIS.values())):
            soma, ms, achou = 0.0, 0.0, False
            for (cc, pod), s in pods.items():
                if cc != col or s[0][0] > f or s[0][-1] < a:
                    continue
                x = taxa(s, a, f)
                if x is not None:
                    soma += x; achou = True
                m = podmem.get((cc, pod))
                if m is not None:
                    y = media(m, a, f)
                    ms += y or 0
            lin[f"{col}_cpu_nucleos"] = round(soma, 4) if achou else None
            lin[f"{col}_mem_mib"] = round(ms / 2**20, 1) if achou else None
        saida.append(lin)
    cols = list(saida[0])
    with open(os.path.join(AQUI, "metricas-por-janela.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader(); w.writerows(saida)
    print(len(saida), "windows summarized,", len(cols), "columns")


if __name__ == "__main__":
    main()
