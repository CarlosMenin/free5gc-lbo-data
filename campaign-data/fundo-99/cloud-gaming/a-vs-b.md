# Campanha A x B - perfil `cloud-gaming` - backhaul com fundo a 99%

**Carga:** 30 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 99% da capacidade medida no inicio de cada rodada (media 837 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (30 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~102.6% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 29 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 12 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 4.993 ± 1.471 | 1.497 ± 0.078 | +3.496 ± 1.468 | [+2.938; +4.055] | +4.240 | 66.1% | 29/29 |
| Atraso de rede p95 (ms) | 6.380 ± 1.091 | 2.130 ± 0.140 | +4.251 ± 1.075 | [+3.842; +4.659] | +4.499 | 65.5% | 29/29 |
| Atraso de rede p99 (ms) | 7.442 ± 1.170 | 3.369 ± 0.353 | +4.073 ± 1.155 | [+3.634; +4.512] | +4.408 | 53.8% | 29/29 |
| Atraso de rede (media) (ms) | 4.977 ± 1.365 | 1.498 ± 0.070 | +3.479 ± 1.358 | [+2.963; +3.996] | +4.005 | 66.9% | 29/29 |
| Jitter de rede (us) | 514.6 ± 132.1 | 305.2 ± 103.2 | +209.4 ± 154.8 | [+150.6; +268.3] | +173.8 | 38.0% | 28/29 |
| Motion-to-photon p50 (ms) | 21.626 ± 2.571 | 18.067 ± 2.319 | +3.559 ± 2.544 | [+2.591; +4.527] | +3.936 | 15.9% | 26/29 |
| Motion-to-photon p95 (ms) | 23.015 ± 3.026 | 18.746 ± 2.294 | +4.269 ± 3.770 | [+2.836; +5.703] | +4.294 | 17.4% | 25/29 |
| Perda de pacotes DL (%) | 1.414 ± 1.071 | 0.013 ± 0.010 | +1.401 ± 1.070 | [+0.994; +1.808] | +1.179 | 97.5% | 29/29 |
| Quadros incompletos (%) | 32.15 ± 22.61 | 0.02 ± 0.01 | +32.12 ± 22.61 | [+23.52; +40.72] | +28.97 | 99.7% | 29/29 |
| Vazao DL (Mbps) | 30.11 ± 0.32 | 30.52 ± 0.01 | -0.41 ± 0.32 | [-0.53; -0.29] | -0.36 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 29 par(es) (alfa 5%, poder 80%): **0.792 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (18 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.482 ± 0.068 | 2.886 ± 0.538 | +1.404 ± 0.574 | [+1.119; +1.689] | 95.8% |
| Atraso de rede p95 (ms) | 2.116 ± 0.140 | 5.027 ± 0.519 | +2.911 ± 0.533 | [+2.646; +3.176] | 138.5% |
| Atraso de rede p99 (ms) | 3.313 ± 0.354 | 7.191 ± 0.514 | +3.879 ± 0.681 | [+3.540; +4.217] | 119.8% |
| Atraso de rede (media) (ms) | 1.486 ± 0.060 | 3.070 ± 0.479 | +1.584 ± 0.508 | [+1.331; +1.837] | 107.4% |
| Jitter de rede (us) | 338.9 ± 137.7 | 911.7 ± 316.0 | +572.8 ± 331.9 | [+407.7; +737.8] | 202.3% |
| Motion-to-photon p50 (ms) | 17.854 ± 2.300 | 19.519 ± 2.118 | +1.666 ± 3.518 | [-0.084; +3.415] | 11.6% |
| Motion-to-photon p95 (ms) | 18.335 ± 2.179 | 21.895 ± 1.466 | +3.560 ± 2.767 | [+2.184; +4.936] | 21.2% |
| Perda de pacotes DL (%) | 0.012 ± 0.010 | 0.493 ± 0.237 | +0.481 ± 0.238 | [+0.363; +0.600] | 5965.2% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 11.85 ± 7.16 | +11.83 ± 7.15 | [+8.27; +15.39] | 44602.6% |
| Vazao DL (Mbps) | 30.52 ± 0.01 | 30.38 ± 0.07 | -0.15 ± 0.07 | [-0.18; -0.11] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 543 | 588 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 745 | 745 |
| 3 | A>B | 1201 | 0 | nao | sim | nao | 527 | 729 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 870 | 861 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 752 | 753 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 864 | 882 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 865 | 875 |
| 8 | B>A | 1201 | 0 | sim | sim | sim | 851 | 853 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 862 | 869 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 857 | 788 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 792 | 785 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 834 | 835 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 486 | 492 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 747 | 749 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 865 | 871 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 854 | 864 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 818 | 810 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 849 | 855 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 872 | 863 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 750 | 756 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 868 | 873 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 856 | 833 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 858 | 880 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 866 | 874 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 861 | 870 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 872 | 875 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 863 | 867 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 777 | 768 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 860 | 873 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 870 | 874 |
