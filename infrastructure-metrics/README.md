# Infrastructure metrics of the campaign (Prometheus)

CPU, memory and network of the nodes and pods during the A × B campaign,
exported from the Prometheus of the cluster after the campaign. The export only
read from Prometheus. Section V-G and Appendix C of the paper use these data.

## Files

- `brutos/*.csv.gz`: raw series covering the whole campaign, one line per
  sample. Column `ts` is in epoch UTC. The step is 30 s, equal to the scrape
  interval. Counters (`*_total`, `*_seconds_total`) are cumulative: a rate is
  the difference between two samples divided by the interval.
  - `no_cpu_por_modo`: CPU seconds per mode, summed over the cores of each node.
  - `no_cpu_por_nucleo_brix`: the same, per core, on the three small edge machines.
  - `no_memoria`: MemTotal, MemAvailable, MemFree, Buffers and Cached.
  - `no_rede`: bytes, packets, drops and errors per interface (`enp3s0` on
    the `brix-porvir-*` machines, `eno1` on `petshopboys` and `metallica`,
    `vxlan.calico` on all).
  - `no_load`, `no_softnet`: 1-minute load; softnet drops and squeezes.
  - `pod_cpu`, `pod_memoria`, `pod_rede`: cAdvisor metrics of the `free5gc`
    namespace, per node, pod and container (or interface). Pod names change
    at every deployment.
  - `pod_cpu_throttled`: empty, because the free5GC pods have no CPU limit.
  - `resumo.json`: the queries used and the lines and series of each file.
- `janelas.csv`: the measurement window of each run in real time, per path
  (`a-mec`, `b-mec`, `b-remoto`), without the 5 s of warm-up, with flags for
  run validity, round kept in the analysis, and Prometheus data available.
- `metricas-por-janela.csv`: the mean of each window with data: CPU of each
  node (% of all cores and, on the small edge machines, the busiest core),
  memory used, traffic on the physical interface (Mbps), and CPU and memory of
  the main pods (UPFs, VR servers, gNB, UE and client of UERANSIM, gNB of the
  background cell).
- `infra-pareado.json`: paired statistics per profile and level (A − B or
  B − A, median across rounds, 95% CI), written by `infra_stats.py`.
- `expected/res_resources.tex`: the reference table of resource usage.

## Scripts, in order

| Script | Input | Output |
|---|---|---|
| `export_prometheus.py` | Prometheus API (needs the cluster) | `brutos/` |
| `build_windows.py` | `../analysis/dados.json` | `janelas.csv` |
| `summarize_windows.py` | `brutos/`, `janelas.csv` | `metricas-por-janela.csv` |
| `infra_stats.py` | `metricas-por-janela.csv`, `janelas.csv`, `../analysis/dados.json` | `infra-pareado.json` |
| `resources_figure.py` | `metricas-por-janela.csv`, `infra-pareado.json` | `out/results-resources.pdf`, `out/res_resources.tex` |

`../reproduce.sh` runs all of them except `export_prometheus.py`.

## CPU of the UPFs

The pods `free5gc-upf`, `free5gc-i-upf` and `free5gc-psa-upf` show almost no
CPU time, because forwarding runs in the gtp5g kernel module, and that time is
accounted to the node (modes `system` and `softirq`), not to the container. The
cost of a UPF must be read on the CPU of the node.

Nodes: `brix-porvir-02` (UE/RAN emulation), `brix-porvir-03` (background
cell), `brix-porvir-05` (Edge Node), `petshopboys` (Server Node, core) and
`metallica` (remote application).

## Times of the runs

The result files do not store the start and end of each run. The window comes
from the modification time of the `campanha.json` of each run
(`../campaign-data/run-file-times.csv`), which is **4 h behind** real time
because of a copy through a Windows machine. With this correction, it marks the
end of the run. The position of every window was checked against the
background traffic received by `brix-porvir-03`: in the three profiles with
complete metrics, the rate inside the window matched the requested level
within 25% in 1,334 of the 1,340 windows. The precision is about 15 s, half the
scrape interval.

## Gaps

- Prometheus stored no data for part of the campaign (a gap in every series,
  including `up`). The whole cloud-gaming profile, 15 runs of ar-industrial and
  10 runs of vr-360 have no metrics; column `prometheus` of `janelas.csv` marks
  them with 0. The resource usage is therefore reported for the teleoperation,
  vr-cloud and vr-extreme profiles.
- The per-pod metrics (cAdvisor) have additional gaps on the small edge
  machines and on `metallica`.
- With a sample every 30 s, each 60 s run has two samples: enough for means
  per run and per level, not for the dynamics within a run.

## Changes for publication

The `instance` label of the node-exporter series held the public IP address
and port of each machine; it now holds the host name of the same machine
(for example `brix-porvir-02:9100`). No value was changed, and the outputs of
the scripts are identical before and after the change.
