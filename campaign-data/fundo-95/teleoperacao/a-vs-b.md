# Campanha A x B - perfil `teleoperacao` - backhaul com fundo a 95%

**Carga:** 8 Mbps @ 60 fps (downlink), pose a 500 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 95% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (8 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~95.9% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.399 ± 0.186 | 1.445 ± 0.017 | +0.954 ± 0.179 | [+0.888; +1.021] | +0.918 | 39.5% | 30/30 |
| Atraso de rede p95 (ms) | 3.598 ± 1.045 | 1.848 ± 0.023 | +1.750 ± 1.048 | [+1.359; +2.141] | +1.479 | 46.5% | 30/30 |
| Atraso de rede p99 (ms) | 5.650 ± 2.158 | 2.769 ± 0.130 | +2.881 ± 2.169 | [+2.071; +3.691] | +2.498 | 48.3% | 30/30 |
| Atraso de rede (media) (ms) | 2.481 ± 0.243 | 1.408 ± 0.017 | +1.073 ± 0.243 | [+0.983; +1.164] | +1.015 | 42.8% | 30/30 |
| Jitter de rede (us) | 364.0 ± 106.2 | 269.8 ± 80.8 | +94.2 ± 148.7 | [+38.7; +149.7] | +115.0 | 17.1% | 22/30 |
| Motion-to-photon p50 (ms) | 15.077 ± 0.189 | 14.102 ± 0.069 | +0.974 ± 0.201 | [+0.900; +1.049] | +0.970 | 6.4% | 30/30 |
| Motion-to-photon p95 (ms) | 16.664 ± 1.007 | 15.181 ± 0.047 | +1.482 ± 1.014 | [+1.104; +1.861] | +1.332 | 8.6% | 30/30 |
| Perda de pacotes DL (%) | 0.110 ± 0.027 | 0.016 ± 0.009 | +0.094 ± 0.028 | [+0.083; +0.104] | +0.090 | 84.6% | 30/30 |
| Quadros incompletos (%) | 0.75 ± 0.18 | 0.02 ± 0.01 | +0.72 ± 0.18 | [+0.65; +0.79] | +0.72 | 96.5% | 30/30 |
| Vazao DL (Mbps) | 8.05 ± 0.00 | 8.06 ± 0.00 | -0.01 ± 0.00 | [-0.01; -0.01] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.095 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.445 ± 0.017 | 2.520 ± 0.214 | +1.075 ± 0.214 | [+0.995; +1.155] | 74.4% |
| Atraso de rede p95 (ms) | 1.848 ± 0.023 | 3.574 ± 0.266 | +1.725 ± 0.264 | [+1.627; +1.824] | 93.4% |
| Atraso de rede p99 (ms) | 2.769 ± 0.130 | 4.938 ± 0.319 | +2.169 ± 0.329 | [+2.047; +2.292] | 78.7% |
| Atraso de rede (media) (ms) | 1.408 ± 0.017 | 2.560 ± 0.203 | +1.153 ± 0.205 | [+1.076; +1.229] | 81.9% |
| Jitter de rede (us) | 269.8 ± 80.8 | 402.4 ± 100.8 | +132.6 ± 93.1 | [+97.8; +167.3] | 56.5% |
| Motion-to-photon p50 (ms) | 14.102 ± 0.069 | 15.148 ± 0.185 | +1.046 ± 0.208 | [+0.968; +1.124] | 7.4% |
| Motion-to-photon p95 (ms) | 15.181 ± 0.047 | 16.615 ± 0.255 | +1.433 ± 0.266 | [+1.334; +1.533] | 9.4% |
| Perda de pacotes DL (%) | 0.016 ± 0.009 | 0.101 ± 0.029 | +0.085 ± 0.031 | [+0.074; +0.097] | 762.1% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.72 ± 0.18 | +0.69 ± 0.18 | [+0.63; +0.76] | 2444.8% |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.05 ± 0.00 | -0.01 ± 0.00 | [-0.01; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 5001 | 0 | sim | sim | sim | 831 | 840 |
| 2 | B>A | 5000 | 0 | sim | sim | sim | 819 | 828 |
| 3 | A>B | 5000 | 0 | sim | sim | sim | 837 | 835 |
| 4 | B>A | 5001 | 0 | sim | sim | sim | 837 | 838 |
| 5 | A>B | 5000 | 0 | sim | sim | sim | 826 | 838 |
| 6 | B>A | 5001 | 0 | sim | sim | sim | 840 | 833 |
| 7 | A>B | 5001 | 0 | sim | sim | sim | 823 | 837 |
| 8 | B>A | 5001 | 0 | sim | sim | sim | 822 | 811 |
| 9 | A>B | 5001 | 0 | sim | sim | sim | 829 | 824 |
| 10 | B>A | 5001 | 0 | sim | sim | sim | 836 | 843 |
| 11 | A>B | 5001 | 0 | sim | sim | sim | 844 | 842 |
| 12 | B>A | 5001 | 0 | sim | sim | sim | 818 | 839 |
| 13 | A>B | 4999 | 0 | sim | sim | sim | 833 | 818 |
| 14 | B>A | 5001 | 0 | sim | sim | sim | 840 | 838 |
| 15 | A>B | 5000 | 0 | sim | sim | sim | 832 | 831 |
| 16 | B>A | 5001 | 0 | sim | sim | sim | 820 | 837 |
| 17 | A>B | 5001 | 0 | sim | sim | sim | 816 | 826 |
| 18 | B>A | 5000 | 0 | sim | sim | sim | 826 | 821 |
| 19 | A>B | 5001 | 0 | sim | sim | sim | 819 | 830 |
| 20 | B>A | 5001 | 0 | sim | sim | sim | 841 | 829 |
| 21 | A>B | 5001 | 0 | sim | sim | sim | 828 | 832 |
| 22 | B>A | 5001 | 0 | sim | sim | sim | 833 | 822 |
| 23 | A>B | 5001 | 0 | sim | sim | sim | 838 | 828 |
| 24 | B>A | 4999 | 0 | sim | sim | sim | 819 | 840 |
| 25 | A>B | 5001 | 0 | sim | sim | sim | 813 | 829 |
| 26 | B>A | 5001 | 0 | sim | sim | sim | 838 | 827 |
| 27 | A>B | 5001 | 0 | sim | sim | sim | 840 | 832 |
| 28 | B>A | 5001 | 0 | sim | sim | sim | 822 | 819 |
| 29 | A>B | 5001 | 0 | sim | sim | sim | 812 | 834 |
| 30 | B>A | 5001 | 0 | sim | sim | sim | 819 | 820 |
