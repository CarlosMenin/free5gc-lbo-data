# Campanha A x B - perfil `vr-extremo` - backhaul com fundo a 80%

**Carga:** 100 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 80% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (100 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~91.3% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 29 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Execucoes refeitas:** 1 por falha de infraestrutura (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade nunca e' refeita.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.741 ± 0.196 | 0.588 ± 0.009 | +1.152 ± 0.197 | [+1.078; +1.227] | +1.169 | 65.8% | 29/29 |
| Atraso de rede p95 (ms) | 2.760 ± 0.588 | 1.029 ± 0.038 | +1.731 ± 0.592 | [+1.506; +1.956] | +1.638 | 61.5% | 29/29 |
| Atraso de rede p99 (ms) | 6.928 ± 8.325 | 2.549 ± 0.187 | +4.379 ± 8.332 | [+1.211; +7.548] | +1.866 | 46.7% | 29/29 |
| Atraso de rede (media) (ms) | 1.919 ± 0.336 | 0.676 ± 0.010 | +1.244 ± 0.339 | [+1.115; +1.372] | +1.192 | 63.9% | 29/29 |
| Jitter de rede (us) | 537.7 ± 217.0 | 320.9 ± 175.4 | +216.8 ± 257.1 | [+119.0; +314.6] | +185.2 | 31.5% | 23/29 |
| Motion-to-photon p50 (ms) | 11.982 ± 0.248 | 10.945 ± 0.078 | +1.037 ± 0.263 | [+0.937; +1.137] | +0.991 | 8.6% | 29/29 |
| Motion-to-photon p95 (ms) | 13.942 ± 0.425 | 12.755 ± 0.084 | +1.187 ± 0.448 | [+1.017; +1.357] | +1.120 | 8.4% | 29/29 |
| Perda de pacotes DL (%) | 0.889 ± 0.007 | 0.888 ± 0.006 | +0.001 ± 0.009 | [-0.002; +0.005] | +0.000 | 0.1% | 15/29 |
| Quadros incompletos (%) | 26.63 ± 1.11 | 29.79 ± 0.40 | -3.16 ± 1.30 | [-3.65; -2.66] | -2.85 | -12.1% | 0/29 |
| Vazao DL (Mbps) | 99.25 ± 0.02 | 99.24 ± 0.01 | +0.02 ± 0.02 | [+0.01; +0.03] | +0.02 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 29 par(es) (alfa 5%, poder 80%): **0.106 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (29 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.588 ± 0.009 | 2.257 ± 0.184 | +1.669 ± 0.183 | [+1.599; +1.738] | 283.7% |
| Atraso de rede p95 (ms) | 1.029 ± 0.038 | 5.948 ± 0.239 | +4.920 ± 0.250 | [+4.825; +5.015] | 479.2% |
| Atraso de rede p99 (ms) | 2.549 ± 0.187 | 8.503 ± 0.440 | +5.954 ± 0.474 | [+5.774; +6.134] | 235.3% |
| Atraso de rede (media) (ms) | 0.676 ± 0.010 | 2.865 ± 0.180 | +2.189 ± 0.182 | [+2.120; +2.258] | 324.1% |
| Jitter de rede (us) | 320.9 ± 175.4 | 1889.8 ± 320.9 | +1568.9 ± 357.5 | [+1433.0; +1704.8] | 701.9% |
| Motion-to-photon p50 (ms) | 10.945 ± 0.078 | 13.021 ± 0.194 | +2.076 ± 0.196 | [+2.001; +2.151] | 19.0% |
| Motion-to-photon p95 (ms) | 12.755 ± 0.084 | 17.406 ± 0.189 | +4.651 ± 0.199 | [+4.575; +4.726] | 36.5% |
| Perda de pacotes DL (%) | 0.888 ± 0.006 | 0.909 ± 0.014 | +0.021 ± 0.015 | [+0.015; +0.026] | 2.3% |
| Quadros incompletos (%) | 29.79 ± 0.40 | 23.75 ± 1.21 | -6.04 ± 1.26 | [-6.52; -5.56] | -20.3% |
| Vazao DL (Mbps) | 99.24 ± 0.01 | 99.22 ± 0.02 | -0.01 ± 0.02 | [-0.02; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 697 | 705 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 696 | 705 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 692 | 702 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 705 | 698 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 699 | 704 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 703 | 701 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 708 | 704 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 697 | 702 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 713 | 706 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 706 | 695 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 707 | 703 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 709 | 706 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 700 | 697 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 699 | 705 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 702 | 708 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 701 | 697 |
| 17 | A>B | 2501 | 0 | sim | sim | sim | 704 | 702 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 705 | 709 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 700 | 701 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 702 | 701 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 694 | 693 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 702 | 708 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 694 | 699 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 699 | 698 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 703 | 710 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 705 | 706 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 701 | 699 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 697 | 705 |
| 29 | A>B | 2501 | falhou | sim | - | nao | 696 | - |
| 30 | B>A | 2501 | 0 | sim | sim | sim | 701 | 702 |
