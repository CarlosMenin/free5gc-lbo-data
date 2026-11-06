# Campanha A x B - perfil `ar-industrial` - backhaul com fundo a 99%

**Carga:** 12 Mbps @ 60 fps (downlink), pose a 200 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 99% da capacidade medida no inicio de cada rodada (media 887 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (12 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~100.4% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.657 ± 0.184 | 1.504 ± 0.033 | +1.153 ± 0.184 | [+1.084; +1.222] | +1.178 | 43.1% | 30/30 |
| Atraso de rede p95 (ms) | 6.219 ± 0.824 | 1.951 ± 0.052 | +4.268 ± 0.823 | [+3.961; +4.575] | +4.197 | 68.2% | 30/30 |
| Atraso de rede p99 (ms) | 6.965 ± 1.722 | 2.965 ± 0.188 | +4.000 ± 1.720 | [+3.358; +4.642] | +3.653 | 56.2% | 30/30 |
| Atraso de rede (media) (ms) | 3.235 ± 0.251 | 1.499 ± 0.029 | +1.735 ± 0.256 | [+1.640; +1.831] | +1.726 | 53.4% | 30/30 |
| Jitter de rede (us) | 465.8 ± 138.5 | 280.6 ± 98.2 | +185.2 ± 160.7 | [+125.2; +245.2] | +172.8 | 35.3% | 27/30 |
| Motion-to-photon p50 (ms) | 17.955 ± 0.346 | 16.199 ± 0.383 | +1.755 ± 0.560 | [+1.546; +1.964] | +1.730 | 9.7% | 30/30 |
| Motion-to-photon p95 (ms) | 21.831 ± 0.910 | 18.355 ± 0.438 | +3.476 ± 0.948 | [+3.122; +3.830] | +3.393 | 15.8% | 30/30 |
| Perda de pacotes DL (%) | 0.313 ± 0.071 | 0.010 ± 0.009 | +0.303 ± 0.073 | [+0.275; +0.330] | +0.313 | 96.3% | 30/30 |
| Quadros incompletos (%) | 4.08 ± 1.05 | 0.02 ± 0.01 | +4.06 ± 1.05 | [+3.66; +4.45] | +4.01 | 99.4% | 30/30 |
| Vazao DL (Mbps) | 12.06 ± 0.01 | 12.09 ± 0.00 | -0.04 ± 0.01 | [-0.04; -0.03] | -0.04 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.098 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.504 ± 0.033 | 2.693 ± 0.268 | +1.189 ± 0.273 | [+1.087; +1.290] | 79.2% |
| Atraso de rede p95 (ms) | 1.951 ± 0.052 | 7.846 ± 15.648 | +5.895 ± 15.649 | [+0.052; +11.738] | 302.5% |
| Atraso de rede p99 (ms) | 2.965 ± 0.188 | 12.443 ± 27.303 | +9.478 ± 27.302 | [-0.715; +19.672] | 320.2% |
| Atraso de rede (media) (ms) | 1.499 ± 0.029 | 3.247 ± 1.459 | +1.748 ± 1.464 | [+1.201; +2.294] | 116.9% |
| Jitter de rede (us) | 280.6 ± 98.2 | 559.5 ± 286.7 | +278.9 ± 271.1 | [+177.7; +380.1] | 112.5% |
| Motion-to-photon p50 (ms) | 16.199 ± 0.383 | 17.536 ± 0.474 | +1.336 ± 0.688 | [+1.079; +1.593] | 8.3% |
| Motion-to-photon p95 (ms) | 18.355 ± 0.438 | 23.593 ± 15.304 | +5.238 ± 15.205 | [-0.439; +10.915] | 28.1% |
| Perda de pacotes DL (%) | 0.010 ± 0.009 | 0.304 ± 0.081 | +0.294 ± 0.086 | [+0.262; +0.326] | 4257.5% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 4.07 ± 1.08 | +4.04 ± 1.08 | [+3.64; +4.45] | 14010.7% |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.06 ± 0.01 | -0.04 ± 0.01 | [-0.04; -0.03] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2001 | 0 | sim | sim | sim | 882 | 880 |
| 2 | B>A | 2001 | 0 | sim | sim | sim | 855 | 864 |
| 3 | A>B | 2001 | 0 | sim | sim | sim | 878 | 876 |
| 4 | B>A | 2001 | 0 | sim | sim | sim | 871 | 872 |
| 5 | A>B | 2001 | 0 | sim | sim | sim | 880 | 878 |
| 6 | B>A | 2001 | 0 | sim | sim | sim | 878 | 879 |
| 7 | A>B | 2001 | 0 | sim | sim | sim | 865 | 863 |
| 8 | B>A | 2001 | 0 | sim | sim | sim | 875 | 866 |
| 9 | A>B | 2001 | 0 | sim | sim | sim | 870 | 875 |
| 10 | B>A | 2001 | 0 | sim | sim | sim | 868 | 863 |
| 11 | A>B | 2001 | 0 | sim | sim | sim | 873 | 876 |
| 12 | B>A | 2001 | 0 | sim | sim | sim | 870 | 865 |
| 13 | A>B | 2001 | 0 | sim | sim | sim | 879 | 874 |
| 14 | B>A | 2001 | 0 | sim | sim | sim | 869 | 869 |
| 15 | A>B | 2001 | 0 | sim | sim | sim | 878 | 876 |
| 16 | B>A | 2001 | 0 | sim | sim | sim | 880 | 879 |
| 17 | A>B | 2001 | 0 | sim | sim | sim | 866 | 874 |
| 18 | B>A | 2001 | 0 | sim | sim | sim | 876 | 877 |
| 19 | A>B | 2001 | 0 | sim | sim | sim | 838 | 842 |
| 20 | B>A | 2001 | 0 | sim | sim | sim | 870 | 872 |
| 21 | A>B | 2001 | 0 | sim | sim | sim | 871 | 872 |
| 22 | B>A | 2001 | 0 | sim | sim | sim | 868 | 872 |
| 23 | A>B | 2001 | 0 | sim | sim | sim | 880 | 871 |
| 24 | B>A | 2001 | 0 | sim | sim | sim | 876 | 879 |
| 25 | A>B | 2001 | 0 | sim | sim | sim | 874 | 877 |
| 26 | B>A | 2001 | 0 | sim | sim | sim | 877 | 878 |
| 27 | A>B | 2001 | 0 | sim | sim | sim | 871 | 867 |
| 28 | B>A | 2001 | 0 | sim | sim | sim | 856 | 854 |
| 29 | A>B | 2001 | 0 | sim | sim | sim | 872 | 873 |
| 30 | B>A | 2001 | 0 | sim | sim | sim | 859 | 870 |
