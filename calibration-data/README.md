# Calibration of the instrument

One folder per workload profile (`<start time>-<profile>`), produced by
`testbed/free5gc/scripts/calibrate_instrument.py` with the placement of the
campaign. Each step was repeated five times, in runs of 60 s with a warm-up of
5 s. Section III-B and Appendix B of the paper describe the procedure; the
paper reports the results in Section V-A and Tables VI and VII.

## Files

- `calibration.json`: everything the calibration measured: arguments
  (`args`), context, placement, aggregated results (`aggregates`), the three
  validations (`v1`, `v2`, `v3`), every run (`records`), warnings and
  duration.
- `csv/`: the per-frame record of every calibration run, with the columns
  described in [`../campaign-data/README.md`](../campaign-data/README.md).

## Steps (file names in `csv/`)

| Prefix | Step | What it measures |
|---|---|---|
| `C0-tester`, `C0-edge`, `C0-remote` | C0 | client and server in the same container (loopback): a calibration instance on the UE/RAN node (`tester`), the MEC application on the Edge Node (`edge`), and the remote application on the remote server (`remote`); the largest of the three is the floor of the instrument |
| `C1-edge`, `C1-remote` | C1 | from the UE/RAN node to the MEC application (`edge`, edge path) and to the remote application (`remote`, remote path) over the cluster network, without the 5G user plane |
| `C2-edge`, `C2-remote` | C2 | the same two paths through the 5G user plane (PDU session) |
| `V1-render-<x>ms` | V1 | a sleep of x ms injected in the server must not change the network delay |
| `V2-netem-<x>ms` | V2 | a delay of x ms injected with the Linux traffic-control emulator must increase the network delay by twice x |
| `V3-C1-edge`, `V3-C1-remote` | V3 | concurrent ICMP echoes on the same paths must agree with the network delay |

`-rN` is the repetition. The tables of Appendix B are rebuilt by
`analysis/tables.py` (`cal_results.tex`, `cal_validations.tex`).

## Running it again

```bash
cd testbed/free5gc
python3 scripts/calibrate_instrument.py --profile vr-cloud --deploy --load-subscribers 5
```

These are the arguments recorded in `args` of each `calibration.json`
(5 repetitions of 60 s, warm-up of 5 s). The output goes to
`testbed/free5gc/calibration/<start time>-<profile>/`, with the same layout as
the folders here (`--output` chooses another folder). See
[`../testbed/README.md`](../testbed/README.md) for the requirements.
