# Campanha A x B - perfil `cloud-gaming` - backhaul com fundo a 50%

**Carga:** 30 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 50% da capacidade medida no inicio de cada rodada (media 837 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (30 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~53.6% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 3.701 ± 7.491 | 1.495 ± 0.080 | +2.206 ± 7.462 | [-0.580; +4.992] | +0.760 | 35.4% | 30/30 |
| Atraso de rede p95 (ms) | 5.832 ± 14.006 | 2.132 ± 0.148 | +3.700 ± 13.992 | [-1.524; +8.924] | +0.962 | 34.1% | 30/30 |
| Atraso de rede p99 (ms) | 8.162 ± 21.352 | 3.332 ± 0.308 | +4.830 ± 21.407 | [-3.162; +12.823] | +0.849 | 22.3% | 28/30 |
| Atraso de rede (media) (ms) | 3.488 ± 6.195 | 1.496 ± 0.068 | +1.992 ± 6.175 | [-0.314; +4.298] | +0.768 | 36.0% | 30/30 |
| Jitter de rede (us) | 438.2 ± 171.5 | 301.8 ± 110.1 | +136.4 ± 235.0 | [+48.6; +224.1] | +97.7 | 19.0% | 23/30 |
| Motion-to-photon p50 (ms) | 19.951 ± 8.122 | 17.922 ± 2.065 | +2.029 ± 8.427 | [-1.117; +5.176] | +1.216 | 3.8% | 18/30 |
| Motion-to-photon p95 (ms) | 22.549 ± 14.014 | 18.593 ± 2.072 | +3.956 ± 14.286 | [-1.378; +9.290] | +1.624 | 8.1% | 20/30 |
| Perda de pacotes DL (%) | 0.097 ± 0.188 | 0.009 ± 0.009 | +0.088 ± 0.188 | [+0.018; +0.158] | +0.017 | -100.4% | 26/30 |
| Quadros incompletos (%) | 2.26 ± 5.53 | 0.02 ± 0.01 | +2.23 ± 5.53 | [+0.17; +4.30] | +0.21 | 80.4% | 27/30 |
| Vazao DL (Mbps) | 30.49 ± 0.06 | 30.52 ± 0.01 | -0.03 ± 0.06 | [-0.05; -0.01] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **3.950 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.495 ± 0.080 | 1.969 ± 0.230 | +0.475 ± 0.235 | [+0.387; +0.562] | 32.0% |
| Atraso de rede p95 (ms) | 2.132 ± 0.148 | 4.201 ± 0.659 | +2.070 ± 0.667 | [+1.820; +2.319] | 97.9% |
| Atraso de rede p99 (ms) | 3.332 ± 0.308 | 6.313 ± 0.685 | +2.981 ± 0.683 | [+2.726; +3.236] | 90.7% |
| Atraso de rede (media) (ms) | 1.496 ± 0.068 | 2.221 ± 0.292 | +0.725 ± 0.293 | [+0.616; +0.834] | 48.7% |
| Jitter de rede (us) | 301.8 ± 110.1 | 639.6 ± 208.6 | +337.8 ± 224.7 | [+253.9; +421.7] | 135.4% |
| Motion-to-photon p50 (ms) | 17.922 ± 2.065 | 18.808 ± 2.125 | +0.887 ± 2.793 | [-0.156; +1.929] | 6.2% |
| Motion-to-photon p95 (ms) | 18.593 ± 2.072 | 21.104 ± 1.423 | +2.510 ± 2.350 | [+1.633; +3.388] | 14.7% |
| Perda de pacotes DL (%) | 0.009 ± 0.009 | 0.066 ± 0.069 | +0.057 ± 0.068 | [+0.031; +0.082] | 845.2% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 1.26 ± 1.71 | +1.24 ± 1.71 | [+0.60; +1.88] | 4446.1% |
| Vazao DL (Mbps) | 30.52 ± 0.01 | 30.50 ± 0.02 | -0.02 ± 0.02 | [-0.03; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 300 | 288 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 388 | 387 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 378 | 378 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 444 | 443 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 393 | 391 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 450 | 448 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 446 | 447 |
| 8 | B>A | 1201 | 0 | sim | sim | sim | 435 | 434 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 445 | 445 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 438 | 438 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 404 | 408 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 433 | 438 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 246 | 248 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 388 | 389 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 445 | 446 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 443 | 441 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 417 | 417 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 435 | 435 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 442 | 442 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 392 | 392 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 447 | 447 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 428 | 428 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 448 | 447 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 444 | 442 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 444 | 444 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 447 | 448 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 443 | 444 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 397 | 398 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 445 | 446 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 445 | 444 |
