# Local breakout under transport load: data and analysis

Data, analysis scripts and testbed code behind the paper

> C. E. Menin and J. A. Wickboldt, "User-Plane Placement at the Edge under
> Transport Load: A Calibrated Evaluation of Local Breakout for Network
> Management," submitted to IEEE/IFIP NOMS 2027.

The paper compares a centralized User Plane Function (UPF, Scenario A) with a
distributed UPF that breaks out edge traffic through an Uplink Classifier
(dUPF with local breakout, Scenario B). Both scenarios use the same edge
destination, and both run under background traffic of another subscriber on
the edge–core link. This repository holds every measurement of that
evaluation, the code that turns the measurements into the tables and figures
of the paper, and the code that measured them.

Related repositories:

- [free5gc-lbo](https://github.com/CarlosMenin/free5gc-lbo): the testbed
  (free5GC v4.2.3 on Kubernetes, ULCL breakout, Traffic Influence AF), with
  documentation for deploying it.
- [photonpath](https://github.com/CarlosMenin/photonpath): the closed-loop
  measurement instrument.

## Contents

| Folder | Size | What it holds |
|---|---|---|
| `campaign-data/` | 552 MB | The A × B campaign: 6 workload profiles × 5 background levels × 30 rounds × 2 scenarios = 1,800 runs of 60 s (1,795 completed), with the per-frame record of every measured path. See [`campaign-data/README.md`](campaign-data/README.md). |
| `calibration-data/` | 64 MB | Calibration of the instrument for each profile: control ladder C0/C1/C2 and validations V1–V3 (270 runs). See [`calibration-data/README.md`](calibration-data/README.md). |
| `infrastructure-metrics/` | 41 MB | CPU, memory and network series of the nodes and pods during the campaign, exported from Prometheus, with the scripts that align them with the runs. See [`infrastructure-metrics/README.md`](infrastructure-metrics/README.md). |
| `analysis/` | 6 MB | Scripts that parse the campaign, compute the paired statistics and write the tables and figures; `runs.json` (the parsed campaign) and the reference outputs in `expected/`. |
| `testbed/` | 1 MB | The code that produced the data: campaign orchestration, scenario tests, calibration, background traffic, Kubernetes manifests, AF and instrument. See [`testbed/README.md`](testbed/README.md). |
| `reproduce.sh`, `verify.py` | | Rebuild everything from the raw data and check it against the reference outputs. |

There are two ways to use this repository:

1. **Reproduce the numbers of the paper from the data.** It needs only Python
   and takes about 30 s. See [Guide 1](#guide-1-reproduce-the-paper-from-the-data).
2. **Run a measurement again on a testbed.** It needs a Kubernetes cluster
   with free5GC. See [Guide 2](#guide-2-run-a-measurement-on-a-testbed).

## Guide 1: reproduce the paper from the data

### Run everything

Requirements: Python 3.9 or later with `numpy` and `matplotlib`. No testbed is
needed.

```bash
pip install -r requirements.txt
./reproduce.sh
```

The script parses the 1,795 runs, rebuilds the tables, the figures and the
infrastructure statistics, and runs `verify.py`. `verify.py` checks that the
regenerated files are identical to the ones used in the paper, and the script
ends with `all outputs match`. If Times New Roman is not installed, the figures
may differ in fonts only.

### From the paper to the files

| Paper | Output (after `reproduce.sh`) | Script |
|---|---|---|
| Table II (network delay without background) | `analysis/out/tables/res_baseline.tex` | `analysis/tables.py` |
| Table III (effect at every background level) | `analysis/out/tables/res_summary.tex` | `analysis/tables.py` |
| Table IV (frames late for a deadline) | `analysis/out/tables/res_deadline.tex` | `analysis/tables.py` |
| Table V (traversals of the congested link) | `analysis/out/tables/res_traversal.tex` | `analysis/tables.py` |
| Tables VI and VII (calibration, Appendix B) | `analysis/out/tables/cal_results.tex`, `cal_validations.tex` | `analysis/tables.py` |
| Fig. 2 (median and 99th percentile per level) | `analysis/out/paper-figures/results-load-levels.pdf` | `analysis/paper_figures.py` |
| Fig. 3 (delay increase against offered load) | `analysis/out/paper-figures/results-offered-load.pdf` | `analysis/paper_figures.py` |
| Section IV (sample, excluded rounds and runs) | `res_validity.tex`, `app_excl_rounds.tex`, `app_excl_runs.tex` | `analysis/tables.py` |
| Section V-G (resource usage of the placements) | `infrastructure-metrics/infra-paired.json`, `infrastructure-metrics/out/res_resources.tex` | `infrastructure-metrics/infra_stats.py`, `resources_figure.py` |
| Appendix D (motion-to-photon latency) | `analysis/out/tables/app_mtp.tex` | `analysis/tables.py` |

The other files in `analysis/out/` (tables `res_load`, `res_quality`,
`app_p50` and `app_p99`, and the figures in `thesis-figures/`) belong to the
undergraduate thesis from which the paper was derived. They use the same data.

### Worked example: one row of Table II, from the raw frames

This example follows one number from the per-frame record to the table. It
takes the row `teleoperation` of Table II.

**One run.** Each run has a record (`run.json`) and one per-frame CSV per
measured path. The network delay of a frame is column `net_us`. The median of
the frames after the 5 s warm-up is the delay of the run:

```bash
python3 - <<'EOF'
import csv, json, statistics
d = "campaign-data/no-background/teleoperation/round-01/a/teleoperation/"
net = [float(r["net_us"]) for r in csv.DictReader(open(d + "run-01/a-mec.csv"))
       if float(r["t_s"]) >= 5]
print(len(net), "frames, median", statistics.median(net), "us")
print("run.json:", json.load(open(d + "run.json"))["executions"][0]["paths"]["a-mec"]["net_rtt_us"]["p50"], "us")
EOF
```

Both lines give 2117.25 µs: 3,300 frames of Scenario A in round 1, without
background.

**One round, one pair.** A round measures A and B a few minutes apart, so the
round is the unit of analysis, and the effect of the breakout is the
difference A − B within the round. `analysis/paired_stats.py` pairs the valid
runs and computes the statistics of the paper:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "analysis")
from paired_stats import pairs, kpi
k = kpi(pairs("teleoperation", 0), "net_p50", div=1000)     # level 0 = no background, in ms
print(k["n"], "pairs | A", round(k["A"], 3), "| B", round(k["B"], 3),
      "| A - B", [round(v, 3) for v in k["d"]], "| reduction", round(k["pct"], 1), "% | B wins", k["win"])
EOF
```

The output is `30 pairs | A 2.087 | B 1.446 | A - B [0.639, 0.614, 0.647] |
reduction 30.4 % | B wins 30`. This is the `teleoperation` row of
`analysis/out/tables/res_baseline.tex`: the median of A and of B, the median
paired difference with its 95% confidence interval, the median reduction, and
the rounds in which B was faster. Change the profile, the level (0, 50, 80, 95
or 99) or the indicator (for example `net_p99`) to follow the other cells of
Tables II and III.

### Pipeline

```
campaign-data/ ──load_campaign.py──▶ analysis/runs.json ──paired_stats.py──┬─▶ tables.py ─────────▶ tables
                                                                          ├─▶ paper_figures.py ──▶ Figs. 2 and 3
                                                                          └─▶ thesis_figures.py ─▶ thesis figures
calibration-data/ ────────────────────────────────────────────────────────────▶ tables.py ─────────▶ Tables VI and VII

infrastructure-metrics/
  analysis/runs.json ──build_windows.py──▶ windows.csv
  raw/ + windows.csv ──summarize_windows.py──▶ metrics-per-window.csv
  metrics-per-window.csv ──infra_stats.py──▶ infra-paired.json ──resources_figure.py──▶ figure and table
```

The statistics follow Section III-C of the paper. The round is the unit of
analysis, and the effect of the breakout is the paired difference A − B within
a round. The median of the paired differences is reported with a 95%
confidence interval from order statistics, together with a two-sided sign
test. Whole rounds are excluded when the link capacity of the round stays below
90% of the campaign median, or when the delay of a scenario without background
deviates by more than 25% from the other rounds. A run is excluded when its own
validity checks fail or, with background, when less than 90% of the requested
rate crossed the link. The rules are in `analysis/paired_stats.py` and
`analysis/load_campaign.py`; the loader applies the same validity rules as the
campaign script (`testbed/free5gc/scripts/campaign.py`).

## Guide 2: run a measurement on a testbed

[`testbed/README.md`](testbed/README.md) describes the testbed and each step in
detail. In short:

1. **Prepare the cluster.** Kubernetes with a `free5gc` namespace, the gtp5g
   kernel module on the nodes of the UPFs, and five nodes in the roles of the
   paper (UE/RAN, Edge Node, Server Node, remote server, background cell).
   Set your node names in the `nodeSelector` of the manifests.
2. **Check the manifests** (no cluster needed):

   ```bash
   cd testbed/free5gc
   pip install -r scripts/requirements.txt
   python3 scripts/validate.py
   ```

3. **Calibrate the instrument** for one profile (Section III-B):

   ```bash
   python3 scripts/calibrate_instrument.py --profile teleoperation --deploy --load-subscribers 5
   ```

4. **Measure one round** of A and B, without background and at 95%:

   ```bash
   python3 scripts/campaign.py --rounds 1 --profile teleoperation --background 0,95 --load-subscribers 5 --output my-campaign
   ```

   Each scenario is deployed from zero, the data path is verified, and each
   level is measured for 60 s. The output folder has the same layout as
   `campaign-data/`, and the script writes the A × B comparison
   (`a-vs-b.md`, `lbo-under-congestion-teleoperation.md`) next to it.

5. **Analyze it with the pipeline of the paper:**

   ```bash
   cd ../../analysis
   python3 load_campaign.py --data ../testbed/free5gc/my-campaign
   ```

   This overwrites `analysis/runs.json` with your runs, and `paired_stats.py`
   then works on them as in the worked example above. The 95% confidence
   interval of the median needs at least 6 rounds (with fewer, it is `None`);
   the paper used 30. Run `./reproduce.sh` to restore the data of the paper.

The commands of the campaign of the paper are recorded in
`campaign-data/campaign-<start>.json`. The first one was:

```bash
python3 scripts/campaign.py --rounds 30 --profile vr-cloud,teleoperation,vr-extreme --background 0,50,80,95,99 --with-remote --load-subscribers 5
```

## Notes

- **Language.** The data, the documentation and the code are in English. The
  campaign wrote its records in Portuguese. For this release, the names of
  folders, files and keys were translated with a mapping that keeps every
  value, and the code was translated in the same way (names, comments and
  messages). The tables and figures rebuilt from the English data are
  identical to those of the paper (`verify.py`). The console logs and the
  summaries that the scripts wrote while they ran are not included; the
  structured records that the analysis reads hold the same data.
- **Machine names.** The data name the machines of the testbed. Their roles, as
  in Table VIII of the paper and in the `placement` field of every run record:

  | Host name | Role |
  |---|---|
  | `brix-porvir-02` | UE/RAN emulation (UERANSIM gNB and UE, closed-loop client) |
  | `brix-porvir-03` | Background cell (UERANSIM gNB and UE of the background subscriber) |
  | `brix-porvir-05` | Edge Node (I-UPF in Scenario B, MEC application, AF) |
  | `petshopboys` | Server Node (5G core, central UPF or PSA-UPF, background generator) |
  | `metallica` | Remote server (remote application) |

- **What was changed for publication.** Measured values are untouched. The
  public campus IP addresses of the machines were replaced: in the Prometheus
  `instance` labels by the host name of the same machine, and in code comments
  by `<edge-subnet>`, `<core-subnet>`, `<campus-ip>` or `<host>`. Private
  addresses (pod, service and UE addresses) are kept. Paths in the analysis
  scripts were adapted to this layout. `analysis/load_campaign.py` reads the
  original modification time of each run record from
  `campaign-data/run-file-times.csv`, because git does not keep file times.
- **Subscriber keys.** The emulated UEs use the default test key and OPc of
  free5GC and UERANSIM.

## License

Code (`*.py`, `*.sh`, manifests): MIT, see [`LICENSE`](LICENSE).
Data (`campaign-data/`, `calibration-data/`, the data files of
`infrastructure-metrics/`, `analysis/runs.json`): CC BY 4.0, see
[`LICENSE-DATA`](LICENSE-DATA).

## Citation

See [`CITATION.cff`](CITATION.cff). Please cite the paper when you use the data.
