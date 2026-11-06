# Campanha A x B - perfil `ar-industrial` - backhaul com fundo a 50%

**Carga:** 12 Mbps @ 60 fps (downlink), pose a 200 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 50% da capacidade medida no inicio de cada rodada (media 887 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (12 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~51.4% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.988 ± 0.102 | 1.502 ± 0.032 | +0.486 ± 0.107 | [+0.446; +0.526] | +0.478 | 24.3% | 30/30 |
| Atraso de rede p95 (ms) | 2.871 ± 1.416 | 1.967 ± 0.051 | +0.904 ± 1.412 | [+0.376; +1.431] | +0.632 | 26.4% | 30/30 |
| Atraso de rede p99 (ms) | 4.456 ± 2.526 | 2.925 ± 0.159 | +1.531 ± 2.475 | [+0.607; +2.455] | +1.027 | 28.4% | 30/30 |
| Atraso de rede (media) (ms) | 2.044 ± 0.241 | 1.497 ± 0.025 | +0.547 ± 0.240 | [+0.457; +0.637] | +0.496 | 26.1% | 30/30 |
| Jitter de rede (us) | 331.5 ± 81.9 | 264.0 ± 73.7 | +67.5 ± 99.8 | [+30.2; +104.7] | +69.2 | 16.5% | 23/30 |
| Motion-to-photon p50 (ms) | 16.870 ± 0.410 | 16.377 ± 0.417 | +0.493 ± 0.632 | [+0.257; +0.729] | +0.563 | 2.9% | 22/30 |
| Motion-to-photon p95 (ms) | 19.133 ± 1.223 | 18.471 ± 0.476 | +0.662 ± 1.377 | [+0.148; +1.176] | +0.432 | 3.1% | 22/30 |
| Perda de pacotes DL (%) | 0.015 ± 0.011 | 0.013 ± 0.010 | +0.002 ± 0.013 | [-0.002; +0.007] | +0.003 | -54.9% | 17/30 |
| Quadros incompletos (%) | 0.05 ± 0.03 | 0.02 ± 0.01 | +0.03 ± 0.03 | [+0.02; +0.04] | +0.03 | 53.3% | 21/30 |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.09 ± 0.00 | -0.00 ± 0.00 | [-0.00; +0.00] | -0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.057 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.502 ± 0.032 | 2.156 ± 0.082 | +0.654 ± 0.090 | [+0.620; +0.688] | 43.6% |
| Atraso de rede p95 (ms) | 1.967 ± 0.051 | 3.172 ± 0.115 | +1.205 ± 0.125 | [+1.158; +1.251] | 61.3% |
| Atraso de rede p99 (ms) | 2.925 ± 0.159 | 4.931 ± 0.265 | +2.005 ± 0.335 | [+1.880; +2.130] | 69.1% |
| Atraso de rede (media) (ms) | 1.497 ± 0.025 | 2.216 ± 0.082 | +0.719 ± 0.081 | [+0.689; +0.749] | 48.0% |
| Jitter de rede (us) | 264.0 ± 73.7 | 461.7 ± 136.5 | +197.7 ± 176.7 | [+131.7; +263.7] | 93.6% |
| Motion-to-photon p50 (ms) | 16.377 ± 0.417 | 16.896 ± 0.382 | +0.519 ± 0.544 | [+0.316; +0.722] | 3.2% |
| Motion-to-photon p95 (ms) | 18.471 ± 0.476 | 19.138 ± 0.370 | +0.667 ± 0.517 | [+0.474; +0.860] | 3.7% |
| Perda de pacotes DL (%) | 0.013 ± 0.010 | 0.014 ± 0.009 | +0.001 ± 0.014 | [-0.004; +0.007] | 49.4% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.04 ± 0.03 | +0.02 ± 0.03 | [+0.01; +0.03] | 67.4% |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.09 ± 0.00 | -0.00 ± 0.00 | [-0.00; -0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2001 | 0 | sim | sim | sim | 446 | 447 |
| 2 | B>A | 2001 | 0 | sim | sim | sim | 440 | 436 |
| 3 | A>B | 2001 | 0 | sim | sim | sim | 447 | 446 |
| 4 | B>A | 2001 | 0 | sim | sim | sim | 443 | 444 |
| 5 | A>B | 2001 | 0 | sim | sim | sim | 446 | 446 |
| 6 | B>A | 2001 | 0 | sim | sim | sim | 445 | 445 |
| 7 | A>B | 2001 | 0 | sim | sim | sim | 441 | 442 |
| 8 | B>A | 2001 | 0 | sim | sim | sim | 444 | 444 |
| 9 | A>B | 2001 | 0 | sim | sim | sim | 444 | 444 |
| 10 | B>A | 2001 | 0 | sim | sim | sim | 443 | 443 |
| 11 | A>B | 2001 | 0 | sim | sim | sim | 445 | 445 |
| 12 | B>A | 2001 | 0 | sim | sim | sim | 441 | 442 |
| 13 | A>B | 2001 | 0 | sim | sim | sim | 446 | 446 |
| 14 | B>A | 2001 | 0 | sim | sim | sim | 443 | 442 |
| 15 | A>B | 2001 | 0 | sim | sim | sim | 445 | 446 |
| 16 | B>A | 2001 | 0 | sim | sim | sim | 446 | 446 |
| 17 | A>B | 2001 | 0 | sim | sim | sim | 444 | 444 |
| 18 | B>A | 2001 | 0 | sim | sim | sim | 446 | 447 |
| 19 | A>B | 2001 | 0 | sim | sim | sim | 428 | 428 |
| 20 | B>A | 2001 | 0 | sim | sim | sim | 442 | 442 |
| 21 | A>B | 2001 | 0 | sim | sim | sim | 443 | 444 |
| 22 | B>A | 2001 | 0 | sim | sim | sim | 442 | 442 |
| 23 | A>B | 2001 | 0 | sim | sim | sim | 446 | 446 |
| 24 | B>A | 2001 | 0 | sim | sim | sim | 446 | 446 |
| 25 | A>B | 2001 | 0 | sim | sim | sim | 443 | 443 |
| 26 | B>A | 2001 | 0 | sim | sim | sim | 445 | 445 |
| 27 | A>B | 2001 | 0 | sim | sim | sim | 443 | 443 |
| 28 | B>A | 2001 | 0 | sim | sim | sim | 439 | 439 |
| 29 | A>B | 2001 | 0 | sim | sim | sim | 445 | 444 |
| 30 | B>A | 2001 | 0 | sim | sim | sim | 439 | 440 |
