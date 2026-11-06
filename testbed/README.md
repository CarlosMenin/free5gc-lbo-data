# Testbed code used in the campaign

A snapshot of the code that produced the data of this repository, kept as it
was run, so that every result can be traced to the code that measured it. It
is not needed to reproduce the analysis. To deploy the testbed, use the
maintained and documented repositories:

- [free5gc-lbo](https://github.com/CarlosMenin/free5gc-lbo): manifests,
  deployment, ULCL configuration, Traffic Influence AF and verification.
- [photonpath](https://github.com/CarlosMenin/photonpath): the closed-loop
  instrument.

Running these scripts requires the Kubernetes cluster of the paper (free5GC
v4.2.3 container images, the gtp5g kernel module on the UPF nodes, UERANSIM,
iperf3) and the node names of the top-level README.

## Layout

```
testbed/
├── free5gc/
│   ├── common/             free5GC network functions shared by both scenarios (AMF, NRF, AUSF, UDM, UDR, PCF, NSSF, NEF, MongoDB, web console)
│   ├── scenario-a-cupf/    Scenario A: SMF and central UPF
│   ├── scenario-b-dupf/    Scenario B: SMF, I-UPF (ULCL) at the edge and PSA-UPF in the core
│   ├── mec/                MEC and remote applications (closed-loop server), their services, and the AF
│   ├── congestao/          background traffic: iperf3 and the background subscriber (GTP-U)
│   ├── tester/             UERANSIM (gNB and UE) and the closed-loop client
│   ├── deploy.py           deployment of a scenario
│   └── scripts/
│       ├── campanha-a-vs-b.py     the campaign: rounds, levels, alternating order, background, checks
│       ├── test-cenario-a.py      one run of Scenario A, with the verification of the data path
│       ├── test-cenario-b.py      one run of Scenario B, with the verification of the data path
│       ├── ruido-gtp.py           background subscriber traffic through its own GTP-U tunnel
│       ├── calibra-instrumento.py calibration of the instrument (C0/C1/C2, V1–V3)
│       ├── validate.py            checks the manifests against the rules free5GC v4.2.3 applies at runtime
│       ├── gen-uerouting.py       generates the ULCL routing (ue-routing-info) of Scenario B for N UEs
│       ├── insere-dados.py        provisions subscribers in the MongoDB of free5GC
│       ├── rodar-cenario-b.py     brings Scenario B up and measures the breakout alone (development)
│       └── piloto-congestao.py, figuras-a-vs-b.py
│                                  pilot of the background load and early slide figures; not used in the paper
├── mec-af/                 the Application Function (Traffic Influence subscription at the NEF)
└── mec-vr/                 the closed-loop instrument as deployed (client, server, clock)
```

## Notes

- Comments are in Portuguese.
- Public campus IP addresses in comments were replaced by `<edge-subnet>`,
  `<core-subnet>`, `<campus-ip>` or `<host>`. Nothing else was changed.
- `insere-dados.py` and the scenario tests use the default test key and OPc
  of free5GC and UERANSIM for the emulated UEs.
- `analysis/load_campaign.py` imports the loader of `campanha-a-vs-b.py`, so that the
  validity rules of the analysis are the same as those of the campaign.
