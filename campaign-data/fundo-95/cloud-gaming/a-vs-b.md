# Campanha A x B - perfil `cloud-gaming` - backhaul com fundo a 95%

**Carga:** 30 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 95% da capacidade medida no inicio de cada rodada (media 837 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (30 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~98.6% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 2 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 3.556 ± 1.149 | 1.532 ± 0.096 | +2.023 ± 1.158 | [+1.591; +2.456] | +1.539 | 52.6% | 30/30 |
| Atraso de rede p95 (ms) | 5.455 ± 1.002 | 2.120 ± 0.168 | +3.335 ± 1.020 | [+2.954; +3.716] | +3.742 | 59.5% | 30/30 |
| Atraso de rede p99 (ms) | 6.388 ± 0.836 | 3.255 ± 0.357 | +3.133 ± 0.903 | [+2.796; +3.470] | +3.233 | 48.2% | 30/30 |
| Atraso de rede (media) (ms) | 3.646 ± 0.962 | 1.519 ± 0.083 | +2.127 ± 0.970 | [+1.764; +2.489] | +1.982 | 55.4% | 30/30 |
| Jitter de rede (us) | 572.4 ± 186.3 | 336.1 ± 131.2 | +236.3 ± 224.8 | [+152.4; +320.2] | +249.5 | 35.3% | 26/30 |
| Motion-to-photon p50 (ms) | 20.444 ± 2.408 | 17.405 ± 2.345 | +3.039 ± 3.592 | [+1.698; +4.380] | +3.275 | 13.5% | 24/30 |
| Motion-to-photon p95 (ms) | 22.630 ± 2.561 | 18.346 ± 2.441 | +4.284 ± 3.702 | [+2.902; +5.666] | +4.097 | 17.8% | 26/30 |
| Perda de pacotes DL (%) | 0.688 ± 0.862 | 0.010 ± 0.009 | +0.678 ± 0.863 | [+0.356; +1.000] | +0.472 | 95.6% | 30/30 |
| Quadros incompletos (%) | 13.17 ± 15.80 | 0.02 ± 0.01 | +13.15 ± 15.80 | [+7.25; +19.05] | +9.29 | 99.4% | 30/30 |
| Vazao DL (Mbps) | 30.34 ± 0.24 | 30.52 ± 0.00 | -0.19 ± 0.24 | [-0.28; -0.09] | -0.12 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.613 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (28 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.536 ± 0.098 | 2.675 ± 0.429 | +1.139 ± 0.459 | [+0.961; +1.317] | 75.1% |
| Atraso de rede p95 (ms) | 2.114 ± 0.173 | 4.772 ± 0.469 | +2.658 ± 0.508 | [+2.461; +2.855] | 127.3% |
| Atraso de rede p99 (ms) | 3.228 ± 0.354 | 7.058 ± 0.500 | +3.830 ± 0.606 | [+3.595; +4.065] | 121.1% |
| Atraso de rede (media) (ms) | 1.520 ± 0.086 | 2.878 ± 0.361 | +1.358 ± 0.385 | [+1.209; +1.508] | 90.1% |
| Jitter de rede (us) | 335.1 ± 135.1 | 836.5 ± 232.3 | +501.4 ± 228.6 | [+412.8; +590.1] | 177.3% |
| Motion-to-photon p50 (ms) | 17.135 ± 2.180 | 17.523 ± 2.106 | +0.388 ± 2.591 | [-0.617; +1.393] | 3.5% |
| Motion-to-photon p95 (ms) | 18.113 ± 2.353 | 22.115 ± 1.571 | +4.001 ± 3.063 | [+2.813; +5.189] | 24.3% |
| Perda de pacotes DL (%) | 0.010 ± 0.009 | 0.389 ± 0.251 | +0.379 ± 0.254 | [+0.280; +0.478] | 9133.2% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 8.64 ± 6.48 | +8.61 ± 6.49 | [+6.10; +11.13] | 27547.7% |
| Vazao DL (Mbps) | 30.52 ± 0.00 | 30.40 ± 0.08 | -0.12 ± 0.08 | [-0.15; -0.09] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 569 | 568 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 728 | 718 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 705 | 701 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 835 | 834 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 724 | 720 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 843 | 842 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 840 | 840 |
| 8 | B>A | 1201 | 0 | sim | sim | sim | 815 | 814 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 828 | 822 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 828 | 816 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 752 | 764 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 805 | 815 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 465 | 472 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 724 | 724 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 829 | 842 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 828 | 828 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 773 | 782 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 814 | 821 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 826 | 833 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 733 | 736 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 839 | 846 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 801 | 803 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 837 | 837 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 835 | 829 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 832 | 828 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 848 | 842 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 830 | 826 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 752 | 738 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 838 | 833 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 839 | 833 |
