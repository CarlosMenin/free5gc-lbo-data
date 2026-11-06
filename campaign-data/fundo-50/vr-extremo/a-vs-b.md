# Campanha A x B - perfil `vr-extremo` - backhaul com fundo a 50%

**Carga:** 100 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 50% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (100 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~61.3% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 29 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Execucoes refeitas:** 1 por falha de infraestrutura (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade nunca e' refeita.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.462 ± 0.069 | 0.584 ± 0.013 | +0.878 ± 0.067 | [+0.852; +0.904] | +0.886 | 60.0% | 29/29 |
| Atraso de rede p95 (ms) | 2.174 ± 0.903 | 1.015 ± 0.040 | +1.159 ± 0.901 | [+0.816; +1.502] | +1.023 | 50.6% | 29/29 |
| Atraso de rede p99 (ms) | 4.278 ± 4.504 | 2.576 ± 0.252 | +1.702 ± 4.507 | [-0.012; +3.416] | +0.791 | 26.3% | 29/29 |
| Atraso de rede (media) (ms) | 1.576 ± 0.231 | 0.673 ± 0.013 | +0.903 ± 0.233 | [+0.814; +0.992] | +0.863 | 56.7% | 29/29 |
| Jitter de rede (us) | 405.2 ± 137.6 | 294.3 ± 157.6 | +110.9 ± 202.8 | [+33.8; +188.1] | +145.9 | 18.2% | 20/29 |
| Motion-to-photon p50 (ms) | 11.658 ± 0.160 | 10.955 ± 0.086 | +0.702 ± 0.191 | [+0.629; +0.775] | +0.682 | 6.0% | 29/29 |
| Motion-to-photon p95 (ms) | 13.614 ± 0.805 | 12.781 ± 0.118 | +0.833 ± 0.804 | [+0.527; +1.139] | +0.685 | 5.9% | 29/29 |
| Perda de pacotes DL (%) | 0.889 ± 0.007 | 0.889 ± 0.007 | -0.000 ± 0.009 | [-0.004; +0.004] | +0.001 | -0.0% | 16/29 |
| Quadros incompletos (%) | 28.55 ± 0.95 | 29.96 ± 0.42 | -1.41 ± 1.11 | [-1.83; -0.99] | -1.18 | -5.1% | 0/29 |
| Vazao DL (Mbps) | 99.24 ± 0.01 | 99.24 ± 0.01 | +0.00 ± 0.01 | [-0.00; +0.01] | +0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 29 par(es) (alfa 5%, poder 80%): **0.036 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (29 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.584 ± 0.013 | 1.926 ± 0.134 | +1.342 ± 0.136 | [+1.291; +1.394] | 230.1% |
| Atraso de rede p95 (ms) | 1.015 ± 0.040 | 5.575 ± 0.160 | +4.560 ± 0.175 | [+4.494; +4.626] | 450.2% |
| Atraso de rede p99 (ms) | 2.576 ± 0.252 | 8.018 ± 0.374 | +5.442 ± 0.429 | [+5.279; +5.605] | 214.3% |
| Atraso de rede (media) (ms) | 0.673 ± 0.013 | 2.549 ± 0.098 | +1.876 ± 0.100 | [+1.838; +1.914] | 279.0% |
| Jitter de rede (us) | 294.3 ± 157.6 | 2100.3 ± 414.4 | +1806.0 ± 461.3 | [+1630.6; +1981.5] | 848.3% |
| Motion-to-photon p50 (ms) | 10.955 ± 0.086 | 12.731 ± 0.098 | +1.776 ± 0.157 | [+1.716; +1.836] | 16.2% |
| Motion-to-photon p95 (ms) | 12.781 ± 0.118 | 17.094 ± 0.151 | +4.313 ± 0.178 | [+4.246; +4.381] | 33.8% |
| Perda de pacotes DL (%) | 0.889 ± 0.007 | 0.908 ± 0.010 | +0.019 ± 0.013 | [+0.014; +0.024] | 2.2% |
| Quadros incompletos (%) | 29.96 ± 0.42 | 25.37 ± 0.79 | -4.58 ± 0.86 | [-4.91; -4.26] | -15.3% |
| Vazao DL (Mbps) | 99.24 ± 0.01 | 99.22 ± 0.01 | -0.01 ± 0.02 | [-0.02; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 442 | 443 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 442 | 443 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 444 | 445 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 444 | 445 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 445 | 444 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 17 | A>B | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 446 | 446 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 440 | 440 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 435 | 436 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 445 | 444 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 442 | 441 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 444 | 443 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 444 | 445 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 446 | 445 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 29 | A>B | 2501 | falhou | sim | - | nao | 445 | - |
| 30 | B>A | 2501 | 0 | sim | sim | sim | 443 | 443 |
