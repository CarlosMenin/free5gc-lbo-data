# Testbed code used in the campaign

The code that produced the data of this repository: the campaign
orchestration, the scenario tests, the calibration, the background traffic,
the Kubernetes manifests, the Application Function (AF) and the closed-loop
instrument. It is not needed to reproduce the analysis (see Guide 1 in the top
README). This page explains how to run a measurement again.

## Layout

```
testbed/
├── free5gc/
│   ├── common/             free5GC network functions shared by both scenarios (AMF, NRF, AUSF, UDM, UDR, PCF, NSSF, NEF, MongoDB, web console)
│   ├── scenario-a-cupf/    Scenario A: SMF and central UPF
│   ├── scenario-b-dupf/    Scenario B: SMF, I-UPF (ULCL) at the edge and PSA-UPF in the core
│   ├── mec/                MEC and remote applications (closed-loop server), their services, and the AF
│   ├── background/         background traffic: the background subscriber (GTP-U) and the direct iperf3 mode
│   ├── tester/             UERANSIM (gNB and UE) and the closed-loop client
│   ├── deploy.py           deployment of a scenario, in dependency order
│   └── scripts/
│       ├── campaign.py              the campaign: rounds, levels, alternating order, background, checks
│       ├── run_scenario_a.py        one run of Scenario A, with the verification of the data path
│       ├── run_scenario_b.py        one run of Scenario B, with the verification of the data path
│       ├── background_gtp.py        background subscriber traffic through its own GTP-U tunnel
│       ├── calibrate_instrument.py  calibration of the instrument (C0/C1/C2, V1–V3)
│       ├── validate.py              checks the manifests against the rules free5GC v4.2.3 applies at runtime
│       ├── gen_uerouting.py         generates the ULCL routing (ue-routing-info) of Scenario B for N UEs
│       ├── provision_subscribers.py provisions subscribers in the MongoDB of free5GC
│       └── requirements.txt
├── mec-af/                 the AF (Traffic Influence subscription at the NEF) and the generator of its manifest
└── mec-vr/                 the closed-loop instrument (client, server, clock) and the generator of its ConfigMap
```

`mec/mec-af.yaml` and `mec/vr-app.yaml` are generated: after changing a file
in `mec-af/` or `mec-vr/`, run `python3 mec-af/gen_manifest.py` or
`python3 mec-vr/gen_configmap.py --all`.

## Requirements

- A Kubernetes cluster (the campaign used server v1.33.2 and kubectl v1.25.4)
  with an existing `free5gc` namespace. The scripts never create or delete the
  namespace; they remove only the objects they created, by name.
- The free5GC v4.2.3 container images and `free5gc/ueransim:v4.2.3`.
- The gtp5g kernel module on the nodes of the UPFs (`lsmod | grep gtp5g`).
  The tests check it before they measure.
- The Prometheus Operator, for the `ServiceMonitor` objects of the manifests
  (only for the infrastructure metrics).
- `sudo` on the UE/RAN node and on the Edge Node, to raise the socket buffers
  of the instrument before a campaign:

  ```bash
  sudo sysctl -w net.core.rmem_max=16777216 net.core.wmem_max=16777216
  ```

- On the machine that runs `kubectl`: Python 3.9 or later and
  `pip install -r free5gc/scripts/requirements.txt` (pymongo and PyYAML). The
  campaign ran with Python 3.10.5.

## Node roles

The placement is fixed by the `nodeSelector` (`kubernetes.io/hostname`) of the
manifests. Set the names of your nodes there:

| Role | Node in the campaign | Files |
|---|---|---|
| UE/RAN emulation | `brix-porvir-02` | `tester/ueransim.yaml` |
| Edge Node (I-UPF, MEC application, AF) | `brix-porvir-05` | `scenario-b-dupf/i-upf.yaml`, `mec/mec-service.yaml` (mec-app), `mec-af/gen_manifest.py` |
| Server Node (5G core, central UPF, PSA-UPF, background generator) | `petshopboys` | `common/*.yaml`, `scenario-a-cupf/*.yaml`, `scenario-b-dupf/smf.yaml`, `scenario-b-dupf/psa-upf.yaml`, `background/background-gtp.yaml` (background-generator) |
| Remote server (remote application) | `metallica` | `mec/mec-service.yaml` (remote-app) |
| Background cell | `brix-porvir-03` | `background/background-gtp.yaml` (background-ueransim) |

The UE/RAN node, the Edge Node and the background cell must be on the same
network segment, and the Server Node and the remote server on the other side
of the router, so that the edge–core link is a real link. The tests warn when
the placement does not follow this design. The nodes in the table are the ones
recorded in the field `placement` of every `run.json`.

## Step by step

All commands run from `testbed/free5gc/`.

**1. Check the manifests** (no cluster needed). It must end with
`Manifests consistent.`

```bash
python3 scripts/validate.py
```

**2. Check each scenario once.** Each test deploys the scenario from zero
(`--deploy`), provisions the subscribers, opens the PDU session and verifies
the data path with the packet counters of the UPFs, then tears the scenario
down. `--proof-only` stops before the measurement (about 1 min after the
deployment).

```bash
python3 scripts/run_scenario_a.py --deploy --load-subscribers 5 --proof-only
python3 scripts/run_scenario_b.py --deploy --load-subscribers 5 --proof-only
```

Scenario A must report `CENTRAL ANCHORING CONFIRMED` (the central UPF counts
both the MEC and the remote traffic). Scenario B must report `LBO CONFIRMED`
(the PSA-UPF sees no MEC traffic and sees the remote traffic). This contrast,
not a lower delay, is the proof that the breakout is in place. If a step fails,
the test prints the likely causes in order.

**3. Check the background cell** with Scenario B running. `proof` sends
background traffic and checks that its GTP-U comes only from the anchor UPF;
it must end with `background path OK`.

```bash
python3 deploy.py up b
python3 scripts/background_gtp.py up --scenario b
python3 scripts/background_gtp.py proof --scenario b
python3 scripts/background_gtp.py down
python3 deploy.py down
```

`deploy.py down` deletes the objects of every manifest of the testbed (not the
namespace).

**4. Calibrate the instrument** for each profile (Section III-B of the paper;
the output goes to `calibration/<start time>-<profile>/`):

```bash
python3 scripts/calibrate_instrument.py --profile teleoperation --deploy --load-subscribers 5
```

**5. Measure one round** of A and B. This is the smallest campaign: one round,
without background and at 95% of the capacity of the link.

```bash
python3 scripts/campaign.py --rounds 1 --profile teleoperation --background 0,95 --load-subscribers 5 --output my-campaign
```

The campaign measures the capacity of the edge–core link, deploys each
scenario once per round, and measures each level for 60 s with the background
on only during the measurement. After each run it checks the instrument (the
per-frame record, the receive buffer and the kernel timestamps) and stops if
the instrument failed. The output has the layout of `../../campaign-data/`:

```
my-campaign/
├── no-background/teleoperation/round-01/{a,b}/...     run records and per-frame CSV files
├── background-95/teleoperation/round-01/{a,b}/...     the same, with background.json
├── no-background/teleoperation/a-vs-b.md              the A x B comparison of each level
├── lbo-under-congestion-teleoperation.md               the effect of the breakout at each level
└── campaign-<start>.json, campaign-<start>.log         command, versions and console output
```

`a-vs-b.md` and `lbo-under-congestion-<profile>.md` are the tables of the
campaign script itself. `python3 scripts/campaign.py --compare-only my-campaign`
rebuilds them from the recorded runs.

**6. Analyze the runs with the pipeline of the paper:**

```bash
cd ../../analysis
python3 load_campaign.py --data ../testbed/free5gc/my-campaign
```

`paired_stats.py` then works on your runs, as in the worked example of the top
README. The 95% confidence interval of the median needs at least 6 rounds.

**7. The campaign of the paper.** The commands are recorded in
`../../campaign-data/campaign-<start>.json`. The profiles were measured in
groups, and `--first-round` resumed a group after an interruption:

```bash
python3 scripts/campaign.py --rounds 30 --profile vr-cloud,teleoperation,vr-extreme --background 0,50,80,95,99 --with-remote --load-subscribers 5
python3 scripts/campaign.py --rounds 30 --profile vr-360,cloud-gaming,ar-industrial --background 0,50,80,95,99 --with-remote --load-subscribers 5
```

A level that already has a result is skipped, so the same command continues an
interrupted campaign.

## Changes from the code that ran

The code is the code of the campaign, translated to English. The translation
changed names (variables, functions, files, folders, data keys, command-line
options), comments and messages; a check compared the syntax trees of the
original and the translated code, so the logic is the same. The deliberate
changes are:

- **File names.** `test-cenario-a.py` → `run_scenario_a.py`,
  `test-cenario-b.py` → `run_scenario_b.py`, `campanha-a-vs-b.py` →
  `campaign.py`, `ruido-gtp.py` → `background_gtp.py`,
  `calibra-instrumento.py` → `calibrate_instrument.py`, `insere-dados.py` →
  `provision_subscribers.py`, and `gen-*.py` → `gen_*.py`. The folder
  `congestao/` is now `background/`, and `ruido-gtp.yaml` is now
  `background-gtp.yaml`.
- **Kubernetes names.** The pods of the background cell (`ruido-gerador`,
  `ruido-ueransim`) are now `background-generator` and `background-ueransim`,
  the iptables chain `RUIDO-GTPU` is now `BACKGROUND-GTPU`, and the
  configuration mount path of the network functions is `/nf-config`. The
  output folders and files follow the names of `../../campaign-data/`.
- **`mec-af/gen_manifest.py`.** The manifest that ran announced only the slice
  of the experiment (`SNSSAIS=1:010203`), but the generator still produced
  both slices. The generator now produces the manifest that ran.
- **`mec-vr/gen_configmap.py`.** The target of another testbed (Open5GS) was
  removed.
- **Edge Node.** Every run recorded the I-UPF and the MEC application on
  `brix-porvir-05` (field `placement` of each `run.json`), but the manifests
  of the code named `brix-porvir-01`. The `nodeSelector` of the I-UPF, of
  mec-app and of mec-af, and the comments that name the Edge Node, now say
  `brix-porvir-05`.
- **Removed.** Development scripts that the paper does not use: a script that
  measured Scenario B alone, the pilot of the background load, and early
  figures.
- **Comments.** Public campus IP addresses were replaced by `<edge-subnet>`,
  `<core-subnet>`, `<campus-ip>` or `<host>`.

`provision_subscribers.py` and the scenario tests use the default test key and
OPc of free5GC and UERANSIM for the emulated UEs.
