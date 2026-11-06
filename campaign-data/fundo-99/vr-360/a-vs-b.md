# Campanha A x B - perfil `vr-360` - backhaul com fundo a 99%

**Carga:** 25 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 99% da capacidade medida no inicio de cada rodada (media 886 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (25 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~101.8% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 27 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 4 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

**Execucoes refeitas:** 1 por falha de infraestrutura (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade nunca e' refeita.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 4.871 ± 0.917 | 1.618 ± 0.105 | +3.254 ± 0.918 | [+2.890; +3.617] | +3.543 | 65.4% | 27/27 |
| Atraso de rede p95 (ms) | 7.332 ± 1.194 | 2.233 ± 0.149 | +5.099 ± 1.235 | [+4.611; +5.588] | +4.647 | 68.8% | 27/27 |
| Atraso de rede p99 (ms) | 8.914 ± 1.979 | 3.457 ± 0.239 | +5.457 ± 2.051 | [+4.645; +6.268] | +4.717 | 59.5% | 27/27 |
| Atraso de rede (media) (ms) | 4.823 ± 0.721 | 1.606 ± 0.090 | +3.217 ± 0.724 | [+2.931; +3.503] | +3.352 | 65.9% | 27/27 |
| Jitter de rede (us) | 534.7 ± 127.8 | 347.3 ± 147.7 | +187.4 ± 171.7 | [+119.5; +255.4] | +205.8 | 33.0% | 24/27 |
| Motion-to-photon p50 (ms) | 21.400 ± 2.568 | 18.118 ± 2.522 | +3.281 ± 3.978 | [+1.707; +4.856] | +3.268 | 13.8% | 20/27 |
| Motion-to-photon p95 (ms) | 23.753 ± 2.417 | 19.169 ± 2.420 | +4.584 ± 3.329 | [+3.267; +5.901] | +4.734 | 18.5% | 25/27 |
| Perda de pacotes DL (%) | 0.815 ± 0.539 | 0.014 ± 0.010 | +0.800 ± 0.539 | [+0.587; +1.014] | +0.665 | 97.7% | 27/27 |
| Quadros incompletos (%) | 14.60 ± 6.40 | 0.02 ± 0.01 | +14.58 ± 6.40 | [+12.05; +17.11] | +13.58 | 99.8% | 27/27 |
| Vazao DL (Mbps) | 25.17 ± 0.06 | 25.34 ± 0.00 | -0.17 ± 0.06 | [-0.20; -0.15] | -0.17 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 27 par(es) (alfa 5%, poder 80%): **0.515 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (24 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.612 ± 0.109 | 3.651 ± 0.502 | +2.039 ± 0.511 | [+1.823; +2.255] | 127.4% |
| Atraso de rede p95 (ms) | 2.215 ± 0.146 | 5.829 ± 0.580 | +3.614 ± 0.623 | [+3.350; +3.877] | 164.5% |
| Atraso de rede p99 (ms) | 3.428 ± 0.263 | 7.949 ± 0.575 | +4.521 ± 0.690 | [+4.229; +4.812] | 133.6% |
| Atraso de rede (media) (ms) | 1.599 ± 0.092 | 3.773 ± 0.467 | +2.174 ± 0.475 | [+1.973; +2.374] | 136.6% |
| Jitter de rede (us) | 346.8 ± 155.2 | 780.4 ± 296.9 | +433.6 ± 355.2 | [+283.6; +583.6] | 169.9% |
| Motion-to-photon p50 (ms) | 17.988 ± 2.595 | 20.333 ± 1.836 | +2.345 ± 3.241 | [+0.977; +3.714] | 15.4% |
| Motion-to-photon p95 (ms) | 19.111 ± 2.514 | 22.680 ± 1.312 | +3.569 ± 3.198 | [+2.218; +4.920] | 21.0% |
| Perda de pacotes DL (%) | 0.014 ± 0.010 | 0.617 ± 0.222 | +0.603 ± 0.223 | [+0.509; +0.698] | 4939.0% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 13.47 ± 5.28 | +13.45 ± 5.28 | [+11.22; +15.68] | 46965.8% |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.18 ± 0.06 | -0.16 ± 0.06 | [-0.18; -0.13] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | nao | sim | nao | 868 | 865 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 844 | 858 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 854 | 848 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 876 | 874 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 876 | 867 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 877 | 872 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 872 | 876 |
| 8 | B>A | 1201 | 0 | sim | nao | nao | 871 | 0 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 875 | 879 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 874 | 871 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 867 | 871 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 859 | 869 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 870 | 871 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 861 | 869 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 869 | 869 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 862 | 855 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 866 | 869 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 865 | 864 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 857 | 856 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 859 | 869 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 866 | 869 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 875 | 868 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 877 | 875 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 856 | 856 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 869 | 868 |
| 26 | B>A | 1201 | 0 | sim | nao | nao | 873 | 729 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 871 | 873 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 871 | 874 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 869 | 872 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 873 | 878 |
