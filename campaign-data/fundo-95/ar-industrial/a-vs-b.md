# Campanha A x B - perfil `ar-industrial` - backhaul com fundo a 95%

**Carga:** 12 Mbps @ 60 fps (downlink), pose a 200 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 95% da capacidade medida no inicio de cada rodada (media 887 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (12 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~96.4% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.384 ± 0.228 | 1.502 ± 0.030 | +0.881 ± 0.231 | [+0.795; +0.968] | +0.881 | 36.4% | 30/30 |
| Atraso de rede p95 (ms) | 4.712 ± 0.514 | 1.952 ± 0.042 | +2.760 ± 0.517 | [+2.567; +2.953] | +2.790 | 58.1% | 30/30 |
| Atraso de rede p99 (ms) | 8.533 ± 12.614 | 2.900 ± 0.183 | +5.632 ± 12.668 | [+0.903; +10.362] | +3.352 | 54.6% | 30/30 |
| Atraso de rede (media) (ms) | 2.622 ± 0.451 | 1.496 ± 0.023 | +1.125 ± 0.453 | [+0.956; +1.295] | +1.076 | 41.8% | 30/30 |
| Jitter de rede (us) | 439.5 ± 156.7 | 273.0 ± 71.1 | +166.4 ± 165.2 | [+104.7; +228.1] | +154.3 | 30.3% | 25/30 |
| Motion-to-photon p50 (ms) | 17.473 ± 0.438 | 16.317 ± 0.422 | +1.156 ± 0.599 | [+0.932; +1.379] | +1.124 | 6.6% | 30/30 |
| Motion-to-photon p95 (ms) | 19.940 ± 0.453 | 18.475 ± 0.434 | +1.465 ± 0.603 | [+1.240; +1.690] | +1.293 | 7.3% | 30/30 |
| Perda de pacotes DL (%) | 0.139 ± 0.028 | 0.012 ± 0.011 | +0.127 ± 0.030 | [+0.116; +0.139] | +0.126 | 91.1% | 30/30 |
| Quadros incompletos (%) | 1.46 ± 0.27 | 0.02 ± 0.01 | +1.44 ± 0.27 | [+1.34; +1.54] | +1.47 | 98.7% | 30/30 |
| Vazao DL (Mbps) | 12.08 ± 0.00 | 12.09 ± 0.00 | -0.02 ± 0.00 | [-0.02; -0.01] | -0.02 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.122 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.502 ± 0.030 | 2.473 ± 0.236 | +0.970 ± 0.232 | [+0.884; +1.057] | 64.6% |
| Atraso de rede p95 (ms) | 1.952 ± 0.042 | 4.223 ± 0.326 | +2.271 ± 0.346 | [+2.142; +2.400] | 116.6% |
| Atraso de rede p99 (ms) | 2.900 ± 0.183 | 5.517 ± 0.307 | +2.617 ± 0.372 | [+2.478; +2.756] | 91.1% |
| Atraso de rede (media) (ms) | 1.496 ± 0.023 | 2.615 ± 0.223 | +1.119 ± 0.223 | [+1.036; +1.202] | 74.8% |
| Jitter de rede (us) | 273.0 ± 71.1 | 516.1 ± 145.8 | +243.1 ± 164.5 | [+181.7; +304.5] | 100.5% |
| Motion-to-photon p50 (ms) | 16.317 ± 0.422 | 17.280 ± 0.512 | +0.963 ± 0.773 | [+0.674; +1.251] | 6.0% |
| Motion-to-photon p95 (ms) | 18.475 ± 0.434 | 19.729 ± 0.362 | +1.254 ± 0.614 | [+1.025; +1.483] | 6.9% |
| Perda de pacotes DL (%) | 0.012 ± 0.011 | 0.143 ± 0.026 | +0.131 ± 0.027 | [+0.121; +0.141] | 1034.5% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 1.50 ± 0.32 | +1.49 ± 0.32 | [+1.37; +1.60] | 5361.2% |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.08 ± 0.00 | -0.02 ± 0.00 | [-0.02; -0.02] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2001 | 0 | sim | sim | sim | 841 | 840 |
| 2 | B>A | 2001 | 0 | sim | sim | sim | 827 | 830 |
| 3 | A>B | 2001 | 0 | sim | sim | sim | 827 | 818 |
| 4 | B>A | 2001 | 0 | sim | sim | sim | 825 | 816 |
| 5 | A>B | 2001 | 0 | sim | sim | sim | 828 | 830 |
| 6 | B>A | 2001 | 0 | sim | sim | sim | 834 | 843 |
| 7 | A>B | 2001 | 0 | sim | sim | sim | 828 | 818 |
| 8 | B>A | 2001 | 0 | sim | sim | sim | 835 | 830 |
| 9 | A>B | 2001 | 0 | sim | sim | sim | 824 | 840 |
| 10 | B>A | 2001 | 0 | sim | sim | sim | 830 | 830 |
| 11 | A>B | 2001 | 0 | sim | sim | sim | 836 | 831 |
| 12 | B>A | 2001 | 0 | sim | sim | sim | 841 | 830 |
| 13 | A>B | 2001 | 0 | sim | sim | sim | 845 | 839 |
| 14 | B>A | 2001 | 0 | sim | sim | sim | 833 | 836 |
| 15 | A>B | 2001 | 0 | sim | sim | sim | 831 | 830 |
| 16 | B>A | 2001 | 0 | sim | sim | sim | 836 | 838 |
| 17 | A>B | 2001 | 0 | sim | sim | sim | 838 | 824 |
| 18 | B>A | 2001 | 0 | sim | sim | sim | 826 | 841 |
| 19 | A>B | 2001 | 0 | sim | sim | sim | 800 | 802 |
| 20 | B>A | 2001 | 0 | sim | sim | sim | 833 | 829 |
| 21 | A>B | 2001 | 0 | sim | sim | sim | 830 | 829 |
| 22 | B>A | 2001 | 0 | sim | sim | sim | 837 | 822 |
| 23 | A>B | 2001 | 0 | sim | sim | sim | 844 | 841 |
| 24 | B>A | 2001 | 0 | sim | sim | sim | 846 | 839 |
| 25 | A>B | 2001 | 0 | sim | sim | sim | 836 | 826 |
| 26 | B>A | 2001 | 0 | sim | sim | sim | 839 | 835 |
| 27 | A>B | 2001 | 0 | sim | sim | sim | 822 | 833 |
| 28 | B>A | 2001 | 0 | sim | sim | sim | 832 | 823 |
| 29 | A>B | 2001 | 0 | sim | sim | sim | 840 | 824 |
| 30 | B>A | 2001 | 0 | sim | sim | sim | 817 | 812 |
