"""Measurement window of each run of the final campaign, in real time.

The modification time of the run.json of each run (kept in
campaign-data/run-file-times.csv and copied into runs.json) is 4 h behind real
time (effect of a copy through a Windows machine; checked against the
background traffic received by brix-porvir-03 in Prometheus). With the
correction, it marks the end of the run. Scenario A has one path (a-mec,
60.5 s); Scenario B has two in sequence (b-mec, then b-remote), with the
background on during both. The window drops the first 5 s of warm-up, as the
generator does.

    python3 build_windows.py   ->  windows.csv
"""
import csv
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(os.path.dirname(HERE), "analysis", "runs.json")
OFFSET_S = 4 * 3600            # mtime + 4 h = end of the run
DURATION, WARMUP = 60.5, 5.0   # duration of each path and warm-up dropped
GAP_B = 4.5                    # gap between b-mec and b-remote (background of 129.9 s in Scenario B)
TZ = datetime.timezone(datetime.timedelta(hours=-3))
# Interval without Prometheus data (gap of the monitoring system during the campaign).
NO_DATA = (datetime.datetime(2026, 10, 16, 1, 10, tzinfo=TZ).timestamp(),
           datetime.datetime(2026, 10, 17, 22, 0, tzinfo=TZ).timestamp())


def main():
    records = json.load(open(RUNS))["records"]
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.dirname(RUNS))
    from paired_stats import round_kept
    rows = []
    for r in records:
        if not r.get("completed") or not r.get("mtime"):
            continue
        end = r["mtime"] + OFFSET_S
        if r["scenario"] == "a":
            paths = [("a-mec", end - DURATION, end)]
        else:
            paths = [("b-mec", end - 2 * DURATION - GAP_B, end - DURATION - GAP_B), ("b-remote", end - DURATION, end)]
        for path, start, stop in paths:
            a = start + WARMUP
            rows.append({
                "profile": r["profile"], "level": r["level"], "round": r["round"], "scenario": r["scenario"],
                "path": path, "start_epoch": f"{a:.1f}", "end_epoch": f"{stop:.1f}",
                "start_local": datetime.datetime.fromtimestamp(a, TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "end_local": datetime.datetime.fromtimestamp(stop, TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "valid": int(bool(r.get("valid") if path != "b-remote" else r.get("valid_remote"))),
                "round_kept": int(round_kept(r)),
                "prometheus": int(not (NO_DATA[0] <= a <= NO_DATA[1] or NO_DATA[0] <= stop <= NO_DATA[1])),
            })
    rows.sort(key=lambda x: float(x["start_epoch"]))
    with open(os.path.join(HERE, "windows.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "windows;", sum(int(x["prometheus"]) for x in rows), "with Prometheus data")


if __name__ == "__main__":
    main()
