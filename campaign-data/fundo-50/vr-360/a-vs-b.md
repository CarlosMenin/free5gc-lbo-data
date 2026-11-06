# Campanha A x B - perfil `vr-360` - backhaul com fundo a 50%

**Carga:** 25 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 50% da capacidade medida no inicio de cada rodada (media 886 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (25 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~52.8% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 29 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Execucoes refeitas:** 1 por falha de infraestrutura (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade nunca e' refeita.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.181 ± 0.095 | 1.577 ± 0.096 | +0.604 ± 0.131 | [+0.554; +0.654] | +0.600 | 27.6% | 29/29 |
| Atraso de rede p95 (ms) | 3.358 ± 1.988 | 2.241 ± 0.140 | +1.117 ± 1.964 | [+0.370; +1.864] | +0.758 | 26.9% | 29/29 |
| Atraso de rede p99 (ms) | 4.921 ± 3.125 | 3.495 ± 0.278 | +1.426 ± 3.106 | [+0.245; +2.607] | +0.709 | 19.6% | 28/29 |
| Atraso de rede (media) (ms) | 2.243 ± 0.314 | 1.577 ± 0.081 | +0.665 ± 0.326 | [+0.541; +0.789] | +0.610 | 28.8% | 29/29 |
| Jitter de rede (us) | 397.8 ± 102.8 | 344.3 ± 132.7 | +53.5 ± 159.5 | [-7.1; +114.1] | +54.9 | 8.6% | 20/29 |
| Motion-to-photon p50 (ms) | 18.238 ± 1.942 | 18.904 ± 2.305 | -0.666 ± 2.977 | [-1.798; +0.466] | -0.193 | -4.8% | 12/29 |
| Motion-to-photon p95 (ms) | 19.234 ± 3.402 | 19.364 ± 2.272 | -0.129 ± 4.017 | [-1.657; +1.398] | -0.283 | -2.8% | 13/29 |
| Perda de pacotes DL (%) | 0.016 ± 0.010 | 0.016 ± 0.009 | -0.000 ± 0.014 | [-0.006; +0.005] | -0.003 | -106.1% | 13/29 |
| Quadros incompletos (%) | 0.12 ± 0.10 | 0.03 ± 0.01 | +0.10 ± 0.10 | [+0.06; +0.14] | +0.08 | 68.3% | 26/29 |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.34 ± 0.00 | -0.00 ± 0.00 | [-0.00; +0.00] | +0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 29 par(es) (alfa 5%, poder 80%): **0.071 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (29 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.577 ± 0.096 | 2.118 ± 0.117 | +0.542 ± 0.133 | [+0.491; +0.592] | 34.7% |
| Atraso de rede p95 (ms) | 2.241 ± 0.140 | 4.018 ± 0.344 | +1.776 ± 0.392 | [+1.627; +1.926] | 80.1% |
| Atraso de rede p99 (ms) | 3.495 ± 0.278 | 6.278 ± 0.341 | +2.784 ± 0.420 | [+2.624; +2.944] | 80.7% |
| Atraso de rede (media) (ms) | 1.577 ± 0.081 | 2.300 ± 0.128 | +0.722 ± 0.141 | [+0.669; +0.776] | 46.1% |
| Jitter de rede (us) | 344.3 ± 132.7 | 619.8 ± 193.4 | +275.5 ± 234.2 | [+186.4; +364.5] | 99.1% |
| Motion-to-photon p50 (ms) | 18.904 ± 2.305 | 18.610 ± 2.561 | -0.294 ± 3.419 | [-1.595; +1.006] | -0.0% |
| Motion-to-photon p95 (ms) | 19.364 ± 2.272 | 21.306 ± 1.589 | +1.942 ± 2.750 | [+0.897; +2.988] | 11.6% |
| Perda de pacotes DL (%) | 0.016 ± 0.009 | 0.019 ± 0.014 | +0.003 ± 0.015 | [-0.002; +0.009] | 83.8% |
| Quadros incompletos (%) | 0.03 ± 0.01 | 0.14 ± 0.14 | +0.11 ± 0.14 | [+0.05; +0.16] | 393.0% |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.33 ± 0.01 | -0.01 ± 0.01 | [-0.01; -0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 443 | 444 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 437 | 437 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 435 | 435 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 444 | 445 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 445 | 445 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 444 | 445 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 8 | B>A | 1201 | 0 | sim | nao | nao | 443 | 0 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 445 | 445 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 446 | 446 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 442 | 441 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 439 | 439 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 443 | 443 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 441 | 441 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 440 | 440 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 442 | 442 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 442 | 442 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 445 | 445 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 445 | 445 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 435 | 435 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 446 | 446 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 443 | 444 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 443 | 444 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 442 | 443 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 448 | 449 |
