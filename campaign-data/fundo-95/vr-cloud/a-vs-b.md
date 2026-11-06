# Campanha A x B - perfil `vr-cloud` - backhaul com fundo a 95%

**Carga:** 50 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 95% da capacidade medida no inicio de cada rodada (media 890 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (50 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~100.6% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 29 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.453 ± 0.290 | 0.952 ± 0.018 | +1.502 ± 0.296 | [+1.389; +1.614] | +1.475 | 60.6% | 29/29 |
| Atraso de rede p95 (ms) | 5.353 ± 0.347 | 1.460 ± 0.040 | +3.893 ± 0.352 | [+3.760; +4.027] | +3.865 | 72.6% | 29/29 |
| Atraso de rede p99 (ms) | 6.529 ± 2.717 | 2.163 ± 0.134 | +4.366 ± 2.751 | [+3.319; +5.412] | +3.806 | 64.7% | 29/29 |
| Atraso de rede (media) (ms) | 2.924 ± 0.308 | 0.966 ± 0.018 | +1.958 ± 0.313 | [+1.839; +2.077] | +1.910 | 66.6% | 29/29 |
| Jitter de rede (us) | 344.5 ± 81.8 | 212.9 ± 53.9 | +131.7 ± 110.6 | [+89.6; +173.7] | +130.4 | 33.6% | 24/29 |
| Motion-to-photon p50 (ms) | 12.703 ± 0.286 | 10.979 ± 0.041 | +1.724 ± 0.286 | [+1.615; +1.833] | +1.716 | 13.5% | 29/29 |
| Motion-to-photon p95 (ms) | 15.935 ± 0.448 | 12.821 ± 0.060 | +3.114 ± 0.438 | [+2.947; +3.280] | +3.085 | 19.5% | 29/29 |
| Perda de pacotes DL (%) | 0.271 ± 0.090 | 0.008 ± 0.007 | +0.262 ± 0.092 | [+0.228; +0.297] | +0.256 | 96.5% | 29/29 |
| Quadros incompletos (%) | 4.99 ± 1.93 | 0.02 ± 0.01 | +4.98 ± 1.93 | [+4.25; +5.71] | +4.44 | 99.6% | 29/29 |
| Vazao DL (Mbps) | 49.97 ± 0.05 | 50.11 ± 0.01 | -0.14 ± 0.05 | [-0.16; -0.12] | -0.12 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 29 par(es) (alfa 5%, poder 80%): **0.159 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (29 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.952 ± 0.018 | 2.214 ± 0.345 | +1.262 ± 0.346 | [+1.130; +1.394] | 132.8% |
| Atraso de rede p95 (ms) | 1.460 ± 0.040 | 4.371 ± 0.336 | +2.912 ± 0.344 | [+2.781; +3.042] | 199.7% |
| Atraso de rede p99 (ms) | 2.163 ± 0.134 | 6.359 ± 0.375 | +4.196 ± 0.417 | [+4.037; +4.355] | 195.2% |
| Atraso de rede (media) (ms) | 0.966 ± 0.018 | 2.513 ± 0.292 | +1.547 ± 0.296 | [+1.434; +1.659] | 160.3% |
| Jitter de rede (us) | 212.9 ± 53.9 | 571.3 ± 164.1 | +358.4 ± 180.2 | [+289.8; +426.9] | 190.3% |
| Motion-to-photon p50 (ms) | 10.979 ± 0.041 | 12.388 ± 0.258 | +1.409 ± 0.250 | [+1.314; +1.504] | 12.8% |
| Motion-to-photon p95 (ms) | 12.821 ± 0.060 | 15.284 ± 0.336 | +2.463 ± 0.328 | [+2.338; +2.588] | 19.2% |
| Perda de pacotes DL (%) | 0.008 ± 0.007 | 0.281 ± 0.149 | +0.272 ± 0.151 | [+0.215; +0.330] | 13386.3% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 5.64 ± 4.06 | +5.63 ± 4.06 | [+4.09; +7.17] | 26341.2% |
| Vazao DL (Mbps) | 50.11 ± 0.01 | 49.97 ± 0.08 | -0.14 ± 0.08 | [-0.17; -0.11] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 821 | 836 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 829 | 832 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 842 | 836 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 833 | 833 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 824 | 839 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 835 | 829 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 841 | 830 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 834 | 826 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 830 | 835 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 842 | 835 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 815 | 836 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 836 | 836 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 823 | 843 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 841 | 818 |
| 15 | A>B | 2501 | 0 | sim | nao | nao | 835 | 746 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 842 | 827 |
| 17 | A>B | 2501 | 0 | sim | sim | sim | 841 | 842 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 830 | 838 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 840 | 822 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 859 | 845 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 835 | 838 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 836 | 835 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 843 | 834 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 846 | 843 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 826 | 839 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 853 | 840 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 832 | 834 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 839 | 840 |
| 29 | A>B | 2501 | 0 | sim | sim | sim | 836 | 840 |
| 30 | B>A | 2501 | 0 | sim | sim | sim | 840 | 832 |
