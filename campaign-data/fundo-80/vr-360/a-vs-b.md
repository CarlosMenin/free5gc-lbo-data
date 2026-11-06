# Campanha A x B - perfil `vr-360` - backhaul com fundo a 80%

**Carga:** 25 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 80% da capacidade medida no inicio de cada rodada (media 886 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (25 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~82.8% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.461 ± 0.133 | 1.566 ± 0.113 | +0.895 ± 0.190 | [+0.824; +0.966] | +0.950 | 36.1% | 30/30 |
| Atraso de rede p95 (ms) | 3.446 ± 0.222 | 2.228 ± 0.136 | +1.217 ± 0.276 | [+1.114; +1.320] | +1.215 | 35.0% | 30/30 |
| Atraso de rede p99 (ms) | 4.934 ± 0.327 | 3.480 ± 0.215 | +1.454 ± 0.468 | [+1.279; +1.629] | +1.501 | 29.0% | 30/30 |
| Atraso de rede (media) (ms) | 2.491 ± 0.139 | 1.567 ± 0.095 | +0.924 ± 0.189 | [+0.854; +0.995] | +0.974 | 36.8% | 30/30 |
| Jitter de rede (us) | 463.3 ± 112.7 | 328.6 ± 90.2 | +134.7 ± 137.1 | [+83.5; +185.9] | +153.9 | 24.8% | 24/30 |
| Motion-to-photon p50 (ms) | 18.829 ± 2.063 | 18.673 ± 2.434 | +0.156 ± 3.364 | [-1.100; +1.412] | -0.350 | -0.4% | 14/30 |
| Motion-to-photon p95 (ms) | 19.494 ± 1.964 | 19.407 ± 2.320 | +0.088 ± 3.120 | [-1.077; +1.253] | -0.554 | -0.5% | 14/30 |
| Perda de pacotes DL (%) | 0.079 ± 0.019 | 0.012 ± 0.010 | +0.067 ± 0.021 | [+0.059; +0.075] | +0.064 | 84.1% | 30/30 |
| Quadros incompletos (%) | 0.74 ± 0.17 | 0.02 ± 0.01 | +0.72 ± 0.17 | [+0.65; +0.78] | +0.72 | 96.8% | 30/30 |
| Vazao DL (Mbps) | 25.32 ± 0.01 | 25.34 ± 0.00 | -0.02 ± 0.01 | [-0.02; -0.01] | -0.02 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.101 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.566 ± 0.113 | 2.428 ± 0.254 | +0.863 ± 0.269 | [+0.762; +0.963] | 55.8% |
| Atraso de rede p95 (ms) | 2.228 ± 0.136 | 4.302 ± 0.478 | +2.074 ± 0.530 | [+1.876; +2.271] | 94.2% |
| Atraso de rede p99 (ms) | 3.480 ± 0.215 | 6.505 ± 0.459 | +3.025 ± 0.552 | [+2.819; +3.231] | 87.9% |
| Atraso de rede (media) (ms) | 1.567 ± 0.095 | 2.593 ± 0.273 | +1.027 ± 0.288 | [+0.919; +1.134] | 66.1% |
| Jitter de rede (us) | 328.6 ± 90.2 | 682.8 ± 157.9 | +354.2 ± 176.9 | [+288.2; +420.2] | 123.4% |
| Motion-to-photon p50 (ms) | 18.673 ± 2.434 | 18.499 ± 2.363 | -0.174 ± 4.118 | [-1.712; +1.363] | 1.6% |
| Motion-to-photon p95 (ms) | 19.407 ± 2.320 | 21.032 ± 1.740 | +1.626 ± 3.163 | [+0.445; +2.807] | 10.2% |
| Perda de pacotes DL (%) | 0.012 ± 0.010 | 0.093 ± 0.080 | +0.081 ± 0.079 | [+0.052; +0.110] | 792.9% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 1.25 ± 1.87 | +1.22 ± 1.87 | [+0.53; +1.92] | 4182.9% |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.32 ± 0.02 | -0.02 ± 0.02 | [-0.03; -0.02] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 697 | 700 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 692 | 685 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 691 | 692 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 700 | 697 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 702 | 701 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 706 | 700 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 706 | 698 |
| 8 | B>A | 1201 | 0 | sim | sim | sim | 696 | 703 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 702 | 703 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 707 | 701 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 704 | 703 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 700 | 700 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 704 | 704 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 701 | 702 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 708 | 706 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 695 | 697 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 702 | 696 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 692 | 698 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 698 | 701 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 705 | 703 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 702 | 703 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 706 | 706 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 698 | 700 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 688 | 695 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 706 | 699 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 701 | 702 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 693 | 699 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 697 | 705 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 702 | 702 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 706 | 711 |
