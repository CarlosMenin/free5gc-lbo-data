# Campaign data (Scenario A × Scenario B)

Every run of the comparative campaign of the paper. A run is one measurement
of one scenario at one background level. It lasts 60 s, and the first 5 s are
a warm-up. A round measures both scenarios at every level, in an order that
alternates between rounds. Each profile was measured in 30 rounds.

The data were written by `testbed/free5gc/scripts/campaign.py`, which calls
`run_scenario_a.py` and `run_scenario_b.py` for each run.

## Layout

```
campaign-data/
├── no-background/ background-50/ background-80/ background-95/ background-99/   background level
│   └── <profile>/                                   workload profile
│       └── round-NN/                                round NN (01 to 30)
│           ├── a/  b/                               Scenario A, Scenario B
│           │   ├── background.json                  background record (levels with background)
│           │   └── <profile>/
│           │       ├── run.json                     run record (see below)
│           │       └── run-01/
│           │           ├── <path>.csv               per-frame record
│           │           └── <path>.json              summary of the path
├── campaign-<start>.json                            each execution of the campaign script:
│                                                    command line, arguments, versions, result
└── run-file-times.csv                               original modification time of every run.json
```

`<path>` is `a-mec` (Scenario A, path to the MEC application), `b-mec`
(Scenario B, path to the MEC application) or `b-remote` (Scenario B, path to
the remote application, the control of the breakout).

The profiles are `teleoperation`, `ar-industrial`, `vr-360`, `cloud-gaming`,
`vr-cloud` and `vr-extreme` (Table I of the paper).

The analysis reads `run.json`, `background.json` and the per-frame CSV files
(`analysis/load_campaign.py`). The console logs and the summaries that the
scripts wrote while they ran are not included; the records above hold the
same data.

## Run record (`run.json`)

| Key | Meaning |
|---|---|
| `profile`, `workload` | workload profile and its load (bitrate, frame rate, pose rate, payload) |
| `duration_s`, `warmup_s` | length of the run and of the warm-up |
| `executions` | the execution of the scenario test; each run has one |
| `executions[].paths` | the summary of each measured path (same content as `run-01/<path>.json`) |
| `executions[].proof` | packet counters of the UPFs read before and after traffic is sent to each destination (verification of the data path) |
| `executions[].placement` | node of each component during the run (see the host names in the top README) |
| `executions[].warnings` | warnings of the run; a warning of scope `campaign` invalidates it |
| `executions[].attempts` | attempts of the run (session establishment) |
| `failures` | executions that did not complete |

## Background record (`background.json`)

| Key | Meaning |
|---|---|
| `mode`, `level` | source of the background (`gtp`: subscriber traffic through the GTP-U tunnel) and level in % |
| `capacity_mbps`, `capacity_measurements` | capacity of the edge–core link measured at the start of the round |
| `requested_mbps`, `crossed_mbps`, `delivered_fraction` | requested background rate, rate that crossed the link, and their ratio |
| `on`, `seconds_on`, `problems` | whether the background was on, for how long, and any problem detected |
| `gtpu_origin`, `origin` | the UPF from which the GTP-U of the background came (it must be only the anchor UPF) |
| `generator_node`, `receiver_node`, `anchor_node` | nodes of the background generator, of the background cell and of the anchor UPF |

## Per-frame record (`run-01/<path>.csv`)

One line per frame completed at the client.

| Column | Unit | Meaning |
|---|---|---|
| `label` | | path (`a-mec`, `b-mec`, `b-remote`) |
| `t_s` | s | time of the frame since the start of the run; the analysis drops `t_s` < 5 (warm-up) |
| `frame_seq` | | sequence number of the frame |
| `pose_seq` | | sequence number of the pose carried by the frame |
| `m2p_us` | µs | motion-to-photon delay, t3 − t0 |
| `net_us` | µs | network delay, (t3 − t0) − (t2 − t1), Eq. (1) of the paper |
| `hold_us` | µs | time the pose spent in the server, t2 − t1 |
| `render_us`, `ai_us` | µs | rendering and inference hooks of the instrument; zero in this campaign |
| `pkts` | | packets of the frame |

## Summary of a path (`run-01/<path>.json`)

Complete and partial frames (`frames_complete`, `frames_partial`,
`frames_incomplete_pct`), `dl_packet_loss_pct`, `dl_throughput_mbps`,
`dl_continuity_pct`, the measurement window (`window`), percentiles of
`m2p_us`, `net_rtt_us` (network delay) and `hold_us`, `jitter_net_us` (RFC 3550
interarrival jitter of the network delay), and the health checks of the
receiver (`health`: socket buffer, socket drops, clock drift).

## Validity

A run counts in the comparison when its record exists, no warning of scope
`campaign` concerns the MEC path, and, at a level with background, the
background was on, at least 90% of the requested rate crossed the link, and no
problem was recorded. Whole rounds are excluded by the two rules of the paper
(capacity below 90% of the campaign median, or a delay without background more
than 25% away from the other rounds). After `reproduce.sh`, the reasons for
every excluded round and run are listed in
`analysis/out/tables/app_excl_rounds.tex` and `app_excl_runs.tex`.

## Times

The result files do not store the start and end of each run. The modification
time of each `run.json` marks the end of the run, but it is 4 h behind real
time, because the files were copied through a Windows machine. Git does not
keep modification times, so they are listed in `run-file-times.csv`, which
`analysis/load_campaign.py` reads. `infrastructure-metrics/build_windows.py`
adds the 4 h back when it places each run in time.
