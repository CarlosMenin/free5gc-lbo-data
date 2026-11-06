# Campanha A x B - perfil `vr-extremo` - backhaul com fundo a 95%

**Carga:** 100 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 95% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (100 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~106.3% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 28 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 4 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 5.835 ± 0.585 | 0.581 ± 0.009 | +5.254 ± 0.584 | [+5.027; +5.481] | +5.241 | 89.9% | 28/28 |
| Atraso de rede p95 (ms) | 6.770 ± 1.274 | 1.017 ± 0.026 | +5.753 ± 1.272 | [+5.260; +6.246] | +5.480 | 84.6% | 28/28 |
| Atraso de rede p99 (ms) | 7.921 ± 1.459 | 2.524 ± 0.274 | +5.398 ± 1.474 | [+4.826; +5.969] | +4.937 | 67.3% | 28/28 |
| Atraso de rede (media) (ms) | 5.829 ± 0.699 | 0.669 ± 0.010 | +5.160 ± 0.699 | [+4.889; +5.431] | +5.180 | 88.4% | 28/28 |
| Jitter de rede (us) | 336.9 ± 157.9 | 330.1 ± 255.4 | +6.8 ± 346.5 | [-127.6; +141.2] | +78.2 | -35.5% | 18/28 |
| Motion-to-photon p50 (ms) | 16.045 ± 0.682 | 10.984 ± 0.079 | +5.061 ± 0.684 | [+4.796; +5.327] | +4.968 | 31.4% | 28/28 |
| Motion-to-photon p95 (ms) | 18.340 ± 1.108 | 12.807 ± 0.097 | +5.533 ± 1.115 | [+5.101; +5.966] | +5.197 | 29.9% | 28/28 |
| Perda de pacotes DL (%) | 1.820 ± 0.132 | 0.888 ± 0.006 | +0.932 ± 0.131 | [+0.881; +0.983] | +0.915 | 51.0% | 28/28 |
| Quadros incompletos (%) | 74.64 ± 2.58 | 30.02 ± 0.35 | +44.62 ± 2.72 | [+43.57; +45.68] | +44.30 | 59.7% | 28/28 |
| Vazao DL (Mbps) | 98.39 ± 0.13 | 99.24 ± 0.01 | -0.84 ± 0.13 | [-0.90; -0.79] | -0.83 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 28 par(es) (alfa 5%, poder 80%): **0.321 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (25 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.582 ± 0.009 | 4.599 ± 0.963 | +4.017 ± 0.965 | [+3.619; +4.415] | 690.6% |
| Atraso de rede p95 (ms) | 1.019 ± 0.027 | 8.203 ± 1.100 | +7.184 ± 1.109 | [+6.727; +7.642] | 706.7% |
| Atraso de rede p99 (ms) | 2.551 ± 0.272 | 10.983 ± 1.740 | +8.431 ± 1.875 | [+7.657; +9.205] | 338.9% |
| Atraso de rede (media) (ms) | 0.670 ± 0.009 | 5.106 ± 0.968 | +4.435 ± 0.971 | [+4.035; +4.836] | 662.4% |
| Jitter de rede (us) | 348.0 ± 264.7 | 1267.5 ± 447.5 | +919.5 ± 522.7 | [+703.7; +1135.3] | 424.6% |
| Motion-to-photon p50 (ms) | 10.984 ± 0.078 | 15.370 ± 0.936 | +4.386 ± 0.924 | [+4.004; +4.767] | 39.9% |
| Motion-to-photon p95 (ms) | 12.806 ± 0.086 | 19.496 ± 1.118 | +6.690 ± 1.107 | [+6.233; +7.147] | 52.2% |
| Perda de pacotes DL (%) | 0.888 ± 0.006 | 1.698 ± 0.078 | +0.811 ± 0.080 | [+0.778; +0.844] | 91.4% |
| Quadros incompletos (%) | 30.02 ± 0.36 | 71.43 ± 2.17 | +41.41 ± 2.15 | [+40.52; +42.30] | 138.0% |
| Vazao DL (Mbps) | 99.23 ± 0.01 | 98.51 ± 0.08 | -0.73 ± 0.08 | [-0.76; -0.70] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 804 | 817 |
| 2 | B>A | 2499 | 0 | sim | sim | sim | 803 | 821 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 801 | 819 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 800 | 818 |
| 5 | A>B | 2500 | 0 | sim | sim | sim | 802 | 821 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 802 | 816 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 803 | 819 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 800 | 818 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 804 | 816 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 801 | 816 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 801 | 812 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 804 | 815 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 802 | 822 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 801 | 817 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 804 | 818 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 800 | 813 |
| 17 | A>B | 2501 | 0 | sim | nao | nao | 806 | 588 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 798 | 818 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 803 | 813 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 803 | 819 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 803 | 810 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 803 | 818 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 802 | 810 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 800 | 821 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 803 | 797 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 802 | 824 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 798 | 819 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 804 | 815 |
| 29 | A>B | 2501 | 0 | sim | sim | sim | 802 | 819 |
| 30 | B>A | 2501 | 0 | nao | sim | nao | 801 | 817 |
