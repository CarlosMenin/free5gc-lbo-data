# Campaign data (Scenario A × Scenario B)

Every run of the comparative campaign of the paper. A run is one measurement
of one scenario at one background level, 60 s long, of which the first 5 s are
a warm-up. A round measures both scenarios at every level, in an order that
alternates between rounds. Each profile was measured in 30 rounds.

## Layout

```
campaign-data/
├── sem-fundo/ fundo-50/ fundo-80/ fundo-95/ fundo-99/      background level
│   └── <profile>/                                          workload profile
│       ├── a-vs-b-por-rodada.csv, a-vs-b.json, a-vs-b.md   comparison written by the campaign script
│       └── rodada-NN/                                      round NN (01 to 30)
│           ├── a/  b/                                      Scenario A, Scenario B
│           │   ├── saida.log                               console output of the run
│           │   ├── fundo.json                              background record (levels with background)
│           │   └── <profile>/
│           │       ├── campanha.json                       run record (see below)
│           │       ├── kpis-agregados.csv, resumo-por-execucao.csv, tabela-kpis.md   summaries
│           │       └── run-01/
│           │           ├── <path>.csv                      per-frame record
│           │           ├── <path>.json                     summary of the path
│           │           └── resumo-completo.json            summaries of all paths of the run
├── campanha-<start>.json / .log                            each execution of the campaign script:
│                                                           command line, arguments, versions, output
└── run-file-times.csv                                      original modification time of every campanha.json
```

`<path>` is `a-mec` (Scenario A, path to the MEC application), `b-mec`
(Scenario B, path to the MEC application) or `b-remoto` (Scenario B, path to
the remote application, the control of the breakout).

The analysis reads only `campanha.json`, `fundo.json` and the per-frame CSV
files (`analysis/load_campaign.py`). The other summaries were written by the
campaign script while it ran and are kept as they were.

## Glossary

| In the data | Meaning |
|---|---|
| `sem-fundo` | no background traffic |
| `fundo-NN` | background at NN% of the capacity of the edge–core link measured at the start of the round |
| `rodada` | round |
| `a`, `b` | Scenario A (centralized UPF), Scenario B (dUPF with local breakout) |
| `teleoperacao`, `vr-extremo` | profiles teleoperation and vr-extreme of the paper (the other profile names are the same) |
| `carga` | workload profile (bitrate, frame rate, pose rate, payload) |
| `execucao(oes)` | execution(s) of the scenario test; each run has one |
| `prova` | packet counters of the UPFs read before and after traffic is sent to each destination (verification of the data path) |
| `avisos` | warnings of the run; a warning of scope `campanha` invalidates it |
| `placement` | node of each component during the run (see the host names in the top README) |
| `tentativas` | attempts of the run (session establishment) |
| `capacidade_mbps` | capacity of the edge–core link measured at the start of the round |
| `pedido_mbps`, `cruzou_mbps`, `fracao_entregue` | requested background rate, rate that crossed the link, and their ratio |
| `ligado`, `segundos_ligado`, `problemas` | whether the background was on, for how long, and any problem detected |
| `janela`, `frames_esperados` | measurement window and number of frames expected in it |
| `saude` | health checks of the receiver (socket buffer, socket drops, clock drift) |

## Per-frame record (`run-01/<path>.csv`)

One line per frame completed at the client.

| Column | Unit | Meaning |
|---|---|---|
| `label` | | path (`a-mec`, `b-mec`, `b-remoto`) |
| `t_s` | s | time of the frame since the start of the run; the analysis drops `t_s` < 5 (warm-up) |
| `frame_seq` | | sequence number of the frame |
| `pose_seq` | | sequence number of the pose carried by the frame |
| `m2p_us` | µs | motion-to-photon delay, t3 − t0 |
| `net_us` | µs | network delay, (t3 − t0) − (t2 − t1), Eq. (1) of the paper |
| `hold_us` | µs | time the pose spent in the server, t2 − t1 |
| `render_us`, `ai_us` | µs | rendering and inference hooks of the instrument; zero in this campaign |
| `pkts` | | packets of the frame |

## Summary of a path (`run-01/<path>.json`)

Frames complete and partial, `frames_incomplete_pct`, `dl_packet_loss_pct`,
`dl_throughput_mbps`, the measurement window (`janela`), percentiles of
`m2p_us`, `net_rtt_us` (network delay) and `hold_us`, `jitter_net_us` (RFC 3550
interarrival jitter of the network delay), and the health checks (`saude`).

## Validity

A run counts in the comparison when its record exists, no warning of scope
`campanha` concerns the MEC path, and, at a level with background, the
background was on, at least 90% of the requested rate crossed the link, and no
problem was recorded. Whole rounds are excluded by the two rules of the paper
(capacity below 90% of the campaign median, or a delay without background more
than 25% away from the other rounds). The reasons for every excluded round and
run are listed in `analysis/out/tables/app_excl_rounds.tex` and
`app_excl_runs.tex` after `reproduce.sh`.

## Times

The result files do not store the start and end of each run. The modification
time of each `campanha.json` marks the end of the run but is 4 h behind real
time, because the files were copied through a Windows machine. Git does not
keep modification times, so they are listed in `run-file-times.csv`, which
`analysis/load_campaign.py` reads. `infrastructure-metrics/build_windows.py` adds the
4 h back when it places each run in time.
