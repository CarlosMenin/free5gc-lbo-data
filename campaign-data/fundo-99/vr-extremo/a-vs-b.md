# Campanha A x B - perfil `vr-extremo` - backhaul com fundo a 99%

**Carga:** 100 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 99% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (100 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~110.3% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 28 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 5 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

**Execucoes refeitas:** 1 por falha de infraestrutura (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade nunca e' refeita.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 5.666 ± 0.414 | 0.583 ± 0.008 | +5.083 ± 0.413 | [+4.923; +5.243] | +5.013 | 89.7% | 28/28 |
| Atraso de rede p95 (ms) | 6.481 ± 0.952 | 1.021 ± 0.045 | +5.460 ± 0.944 | [+5.094; +5.826] | +5.221 | 84.0% | 28/28 |
| Atraso de rede p99 (ms) | 10.777 ± 9.349 | 2.568 ± 0.333 | +8.209 ± 9.406 | [+4.562; +11.857] | +5.230 | 68.8% | 28/28 |
| Atraso de rede (media) (ms) | 5.664 ± 0.536 | 0.672 ± 0.010 | +4.992 ± 0.536 | [+4.784; +5.200] | +4.940 | 88.0% | 28/28 |
| Jitter de rede (us) | 275.4 ± 108.1 | 358.5 ± 273.3 | -83.0 ± 273.4 | [-189.0; +23.0] | +12.3 | -44.4% | 14/28 |
| Motion-to-photon p50 (ms) | 15.826 ± 0.425 | 10.987 ± 0.071 | +4.838 ± 0.414 | [+4.678; +4.999] | +4.794 | 30.5% | 28/28 |
| Motion-to-photon p95 (ms) | 18.062 ± 0.968 | 12.808 ± 0.089 | +5.253 ± 0.957 | [+4.882; +5.625] | +4.971 | 28.9% | 28/28 |
| Perda de pacotes DL (%) | 1.847 ± 0.177 | 0.889 ± 0.006 | +0.958 ± 0.177 | [+0.890; +1.027] | +0.928 | 51.5% | 28/28 |
| Quadros incompletos (%) | 75.70 ± 2.75 | 29.81 ± 0.29 | +45.88 ± 2.79 | [+44.80; +46.96] | +45.66 | 60.6% | 28/28 |
| Vazao DL (Mbps) | 98.35 ± 0.19 | 99.24 ± 0.01 | -0.88 ± 0.19 | [-0.95; -0.81] | -0.86 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 28 par(es) (alfa 5%, poder 80%): **0.227 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (24 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.583 ± 0.008 | 4.832 ± 1.234 | +4.249 ± 1.236 | [+3.727; +4.772] | 730.1% |
| Atraso de rede p95 (ms) | 1.024 ± 0.047 | 8.676 ± 1.758 | +7.652 ± 1.775 | [+6.902; +8.402] | 751.5% |
| Atraso de rede p99 (ms) | 2.594 ± 0.342 | 14.101 ± 10.322 | +11.507 ± 10.344 | [+7.138; +15.875] | 454.3% |
| Atraso de rede (media) (ms) | 0.673 ± 0.011 | 5.411 ± 1.261 | +4.739 ± 1.263 | [+4.205; +5.272] | 705.3% |
| Jitter de rede (us) | 362.1 ± 293.0 | 1215.3 ± 485.9 | +853.1 ± 569.6 | [+612.5; +1093.7] | 429.8% |
| Motion-to-photon p50 (ms) | 10.981 ± 0.070 | 15.554 ± 1.140 | +4.573 ± 1.137 | [+4.093; +5.053] | 41.6% |
| Motion-to-photon p95 (ms) | 12.804 ± 0.088 | 20.061 ± 1.706 | +7.257 ± 1.695 | [+6.541; +7.973] | 56.7% |
| Perda de pacotes DL (%) | 0.888 ± 0.006 | 1.739 ± 0.070 | +0.851 ± 0.071 | [+0.821; +0.882] | 95.9% |
| Quadros incompletos (%) | 29.79 ± 0.29 | 72.98 ± 1.50 | +43.19 ± 1.58 | [+42.52; +43.85] | 145.0% |
| Vazao DL (Mbps) | 99.24 ± 0.01 | 98.46 ± 0.07 | -0.78 ± 0.08 | [-0.81; -0.75] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 803 | 842 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 804 | 839 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 801 | 838 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 804 | 838 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 803 | 843 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 798 | 836 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 804 | 840 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 803 | 839 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 804 | 837 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 800 | 838 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 801 | 840 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 802 | 842 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 801 | 841 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 801 | 838 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 804 | 838 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 802 | 839 |
| 17 | A>B | 2501 | falhou | sim | - | nao | 807 | - |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 806 | 843 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 803 | 838 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 805 | 841 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 800 | 818 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 804 | 828 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 801 | 817 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 805 | 843 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 806 | 840 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 801 | 826 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 799 | 842 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 805 | 833 |
| 29 | A>B | 2501 | 0 | sim | sim | sim | 801 | 856 |
| 30 | B>A | 2501 | 0 | nao | sim | nao | 805 | 840 |
