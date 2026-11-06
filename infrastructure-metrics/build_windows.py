"""Measurement window of each run of the final campaign, in real time.

The modification time of the campanha.json of each run (kept in
campaign-data/run-file-times.csv and copied into dados.json) is 4 h behind
real time (effect of a copy through a Windows machine; checked against the
background traffic received by brix-porvir-03 in Prometheus). With the
correction, it marks the end of the run. Scenario A has one path (a-mec,
60.5 s); Scenario B has two in sequence (b-mec, then b-remoto), with the
background on during both. The window drops the first 5 s of warm-up, as the
generator does.

    python3 build_windows.py   ->  janelas.csv
"""
import csv, datetime, json, os

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(os.path.dirname(AQUI), "analysis", "dados.json")
DESLOC = 4 * 3600            # mtime + 4 h = end of the run
DUR, AQUEC = 60.5, 5.0       # duration of each path and warm-up dropped
INTERV_B = 4.5               # gap between b-mec and b-remoto (background of 129.9 s in Scenario B)
LACUNA = (datetime.datetime(2026, 10, 16, 1, 10, tzinfo=datetime.timezone(datetime.timedelta(hours=-3))).timestamp(),
          datetime.datetime(2026, 10, 17, 22, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-3))).timestamp())
TZ = datetime.timezone(datetime.timedelta(hours=-3))


def main():
    regs = json.load(open(DADOS))["regs"]
    import sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.dirname(DADOS))
    from paired_stats import mantida
    linhas = []
    for r in regs:
        if not r.get("concluiu") or not r.get("mtime"):
            continue
        fim = r["mtime"] + DESLOC
        if r["cen"] == "a":
            cams = [("a-mec", fim - DUR, fim)]
        else:
            cams = [("b-mec", fim - 2 * DUR - INTERV_B, fim - DUR - INTERV_B), ("b-remoto", fim - DUR, fim)]
        for cam, ini, f in cams:
            a = ini + AQUEC
            linhas.append({
                "perfil": r["perfil"], "nivel": r["nivel"], "rodada": r["rodada"], "cenario": r["cen"], "caminho": cam,
                "inicio_epoch": f"{a:.1f}", "fim_epoch": f"{f:.1f}",
                "inicio_local": datetime.datetime.fromtimestamp(a, TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "fim_local": datetime.datetime.fromtimestamp(f, TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "valida": int(bool(r.get("valida") if cam != "b-remoto" else r.get("valida_remoto"))),
                "rodada_mantida": int(mantida(r)),
                "prometheus": int(not (LACUNA[0] <= a <= LACUNA[1] or LACUNA[0] <= f <= LACUNA[1])),
            })
    linhas.sort(key=lambda x: float(x["inicio_epoch"]))
    with open(os.path.join(AQUI, "janelas.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0]))
        w.writeheader(); w.writerows(linhas)
    print(len(linhas), "windows;", sum(int(x["prometheus"]) for x in linhas), "with Prometheus data")


if __name__ == "__main__":
    main()
