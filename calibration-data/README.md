# Calibration of the instrument

One folder per workload profile (`<start time>-<profile>`), produced by
`testbed/free5gc/scripts/calibra-instrumento.py` with the placement of the
campaign. Each step was repeated five times, in runs of 60 s with a warm-up of
5 s. Section III-B and Appendix B of the paper describe the procedure; the
paper reports the results in Section V-A and Tables VI and VII.

## Files

- `calibracao.json`: everything the calibration measured: arguments,
  context, placement, aggregated results (`agregados`), the three validations
  (`v1`, `v2`, `v3`), every run (`registros`), warnings and duration.
- `relatorio.txt`: the same results as a text report (control ladder,
  decomposition of the network delay, noise against effect, validations).
- `csv/`: the per-frame record of every calibration run, with the columns
  described in [`../campaign-data/README.md`](../campaign-data/README.md).

## Steps (file names in `csv/`)

| Prefix | Step | What it measures |
|---|---|---|
| `C0-tester`, `C0-borda`, `C0-nucleo` | C0 | client and server in the same container (loopback): a calibration instance on the UE/RAN node (`tester`), the MEC application on the Edge Node (`borda`), and the remote application on the remote server (`nucleo`); the largest of the three is the floor of the instrument |
| `C1-borda`, `C1-nucleo` | C1 | from the UE/RAN node to the MEC application (`borda`, edge path) and to the remote application (`nucleo`, remote path) over the cluster network, without the 5G user plane |
| `C2-borda`, `C2-nucleo` | C2 | the same two paths through the 5G user plane (PDU session) |
| `V1-render-<x>ms` | V1 | a sleep of x ms injected in the server must not change the network delay |
| `V2-netem-<x>ms` | V2 | a delay of x ms injected with the Linux traffic-control emulator must increase the network delay by twice x |
| `V3-C1-borda`, `V3-C1-nucleo` | V3 | concurrent ICMP echoes on the same paths must agree with the network delay |

`-rN` is the repetition. The tables of Appendix B are rebuilt by
`analysis/tables.py` (`cal_results.tex`, `cal_validations.tex`).
