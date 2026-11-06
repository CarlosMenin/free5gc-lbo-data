# Local breakout under transport load: data and analysis

Data, analysis scripts and testbed code behind the paper

> C. E. Menin and J. A. Wickboldt, "User-Plane Placement at the Edge under
> Transport Load: A Calibrated Evaluation of Local Breakout for Network
> Management," submitted to IEEE/IFIP NOMS 2027.

The paper compares a centralized User Plane Function (UPF, Scenario A) with a
distributed UPF that breaks out edge traffic through an Uplink Classifier
(dUPF with local breakout, Scenario B), with the same edge destination in both
scenarios, under background traffic of another subscriber on the edge–core
link. This repository holds every measurement of that evaluation and the code
that turns it into the tables and figures of the paper.

Related repositories:

- [free5gc-lbo](https://github.com/CarlosMenin/free5gc-lbo): the testbed
  (free5GC v4.2.3 on Kubernetes, ULCL breakout, Traffic Influence AF), with
  documentation for deploying it.
- [photonpath](https://github.com/CarlosMenin/photonpath): the closed-loop
  measurement instrument.

## Contents

| Folder | Size | What it holds |
|---|---|---|
| `campaign-data/` | 642 MB | The A × B campaign: 6 workload profiles × 5 background levels × 30 rounds × 2 scenarios = 1,800 runs of 60 s (1,795 completed), with the per-frame record of every measured path. See [`campaign-data/README.md`](campaign-data/README.md). |
| `calibration-data/` | 65 MB | Calibration of the instrument for each profile: control ladder C0/C1/C2 and validations V1–V3 (270 runs). See [`calibration-data/README.md`](calibration-data/README.md). |
| `infrastructure-metrics/` | 41 MB | CPU, memory and network series of the nodes and pods during the campaign, exported from Prometheus, with the scripts that align them with the runs. See [`infrastructure-metrics/README.md`](infrastructure-metrics/README.md). |
| `analysis/` | 6 MB | Scripts that parse the campaign, compute the paired statistics and write the tables and figures; `dados.json` (parsed campaign) and the reference outputs in `expected/`. |
| `testbed/` | 1 MB | Snapshot of the code that produced the data: campaign orchestration, calibration, background traffic, scenario tests, Kubernetes manifests, AF and instrument. See [`testbed/README.md`](testbed/README.md). |
| `reproduce.sh`, `verify.py` | | Rebuild everything from the raw data and check it against the reference outputs. |

## Quick start (about 30 s)

Requirements: Python 3.9 or later with `numpy` and `matplotlib`
(`pip install -r requirements.txt`). No testbed is needed to reproduce the
analysis.

```bash
./reproduce.sh
```

The script parses the 1,795 runs, rebuilds the tables, the figures and the
infrastructure statistics, and runs `verify.py`, which checks that the
regenerated files are identical to the ones used in the paper. It ends with
`all outputs match`. Figures may differ only in fonts if Times New Roman is not
installed.

## From the paper to the files

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
| Section V-G (resource usage of the placements) | `infrastructure-metrics/infra-pareado.json`, `infrastructure-metrics/out/res_resources.tex` | `infrastructure-metrics/infra_stats.py`, `resources_figure.py` |
| Appendix D (motion-to-photon latency) | `analysis/out/tables/app_mtp.tex` | `analysis/tables.py` |

The other files in `analysis/out/` (tables `res_load`, `res_quality`,
`app_p50`, `app_p99` and the figures in `thesis-figures/`) belong to the
undergraduate thesis from which the paper was derived and use the same data.

## Pipeline

```
campaign-data/ ──load_campaign.py──▶ analysis/dados.json ──paired_stats.py──┬─▶ tables.py ─────────▶ tables
                                                                           ├─▶ paper_figures.py ──▶ Figs. 2 and 3
                                                                           └─▶ thesis_figures.py ─▶ thesis figures
calibration-data/ ─────────────────────────────────────────────────────────────▶ tables.py ─────────▶ Tables VI and VII

infrastructure-metrics/
  analysis/dados.json ──build_windows.py──▶ janelas.csv
  brutos/ + janelas.csv ──summarize_windows.py──▶ metricas-por-janela.csv
  metricas-por-janela.csv ──infra_stats.py──▶ infra-pareado.json ──resources_figure.py──▶ figure and table
```

Statistics follow Section III-C of the paper: the round is the unit of
analysis; the effect of the breakout is the paired difference A − B within a
round; the median of the paired differences is reported with a 95% confidence
interval from order statistics, together with a two-sided sign test. Whole
rounds are excluded when the link capacity of the round stays below 90% of the
campaign median or when the delay of a scenario without background deviates by
more than 25% from the other rounds. A run is excluded when its own validity
checks fail or, with background, when less than 90% of the requested rate
crossed the link. The rules are in `analysis/paired_stats.py` and in the loader of
`testbed/free5gc/scripts/campanha-a-vs-b.py`.

## Notes

- **Language.** The documentation and the comments and messages of the analysis
  scripts are in English. Variable names in the scripts, the names of folders,
  files and JSON keys inside the data, and the testbed code are in Portuguese,
  as recorded during the campaign. The glossary in
  [`campaign-data/README.md`](campaign-data/README.md) translates the data, and
  the docstring of `analysis/paired_stats.py` translates the main variable
  names.
- **Machine names.** The data name the machines of the testbed. Their roles, as
  in Table VIII of the paper:

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
  scripts were adapted to this layout, and `analysis/load_campaign.py` reads the
  original modification time of each run record from
  `campaign-data/run-file-times.csv`, because git does not keep file times.
  `verify.py` confirms that the outputs did not change.
- **Subscriber keys.** The emulated UEs use the default test key and OPc of
  free5GC and UERANSIM.

## License

Code (`*.py`, `*.sh`, manifests): MIT, see [`LICENSE`](LICENSE).
Data (`campaign-data/`, `calibration-data/`, `infrastructure-metrics/` data
files, `analysis/dados.json`): CC BY 4.0, see [`LICENSE-DATA`](LICENSE-DATA).

## Citation

See [`CITATION.cff`](CITATION.cff). Please cite the paper when using the data.
