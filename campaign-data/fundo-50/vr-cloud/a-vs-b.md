# Campanha A x B - perfil `vr-cloud` - backhaul com fundo a 50%

**Carga:** 50 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 50% da capacidade medida no inicio de cada rodada (media 890 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (50 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~55.6% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.531 ± 0.073 | 0.949 ± 0.019 | +0.582 ± 0.077 | [+0.553; +0.611] | +0.569 | 37.9% | 30/30 |
| Atraso de rede p95 (ms) | 2.953 ± 4.304 | 1.462 ± 0.036 | +1.491 ± 4.305 | [-0.117; +3.098] | +0.719 | 34.3% | 30/30 |
| Atraso de rede p99 (ms) | 3.867 ± 4.610 | 2.194 ± 0.128 | +1.673 ± 4.604 | [-0.046; +3.391] | +0.817 | 29.4% | 30/30 |
| Atraso de rede (media) (ms) | 1.794 ± 1.199 | 0.965 ± 0.018 | +0.829 ± 1.194 | [+0.383; +1.275] | +0.604 | 40.3% | 30/30 |
| Jitter de rede (us) | 264.1 ± 117.3 | 225.6 ± 86.9 | +38.6 ± 141.3 | [-14.2; +91.3] | +29.3 | 2.0% | 20/30 |
| Motion-to-photon p50 (ms) | 11.564 ± 0.225 | 10.992 ± 0.055 | +0.572 ± 0.228 | [+0.487; +0.657] | +0.529 | 4.9% | 30/30 |
| Motion-to-photon p95 (ms) | 14.125 ± 4.073 | 12.853 ± 0.060 | +1.271 ± 4.071 | [-0.249; +2.791] | +0.565 | 5.9% | 30/30 |
| Perda de pacotes DL (%) | 0.020 ± 0.011 | 0.008 ± 0.007 | +0.012 ± 0.011 | [+0.008; +0.016] | +0.013 | 20.9% | 26/30 |
| Quadros incompletos (%) | 0.16 ± 0.07 | 0.02 ± 0.01 | +0.15 ± 0.07 | [+0.12; +0.17] | +0.16 | 87.9% | 30/30 |
| Vazao DL (Mbps) | 50.10 ± 0.01 | 50.11 ± 0.01 | -0.01 ± 0.01 | [-0.01; -0.01] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.041 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.949 ± 0.019 | 1.443 ± 0.073 | +0.494 ± 0.066 | [+0.469; +0.518] | 52.0% |
| Atraso de rede p95 (ms) | 1.462 ± 0.036 | 3.484 ± 0.123 | +2.021 ± 0.132 | [+1.972; +2.070] | 138.4% |
| Atraso de rede p99 (ms) | 2.194 ± 0.128 | 5.275 ± 0.177 | +3.080 ± 0.247 | [+2.988; +3.173] | 141.3% |
| Atraso de rede (media) (ms) | 0.965 ± 0.018 | 1.682 ± 0.073 | +0.717 ± 0.069 | [+0.691; +0.743] | 74.3% |
| Jitter de rede (us) | 225.6 ± 86.9 | 515.1 ± 183.4 | +289.6 ± 190.9 | [+218.3; +360.8] | 152.0% |
| Motion-to-photon p50 (ms) | 10.992 ± 0.055 | 11.624 ± 0.082 | +0.632 ± 0.099 | [+0.595; +0.669] | 5.7% |
| Motion-to-photon p95 (ms) | 12.853 ± 0.060 | 14.277 ± 0.132 | +1.424 ± 0.146 | [+1.370; +1.478] | 11.1% |
| Perda de pacotes DL (%) | 0.008 ± 0.007 | 0.018 ± 0.007 | +0.010 ± 0.010 | [+0.006; +0.013] | 413.1% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.18 ± 0.09 | +0.16 ± 0.09 | [+0.13; +0.19] | 834.6% |
| Vazao DL (Mbps) | 50.11 ± 0.01 | 50.09 ± 0.01 | -0.01 ± 0.01 | [-0.02; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 444 | 443 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 445 | 446 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 443 | 444 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 447 | 445 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 444 | 445 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 445 | 446 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 446 | 446 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 442 | 442 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 444 | 446 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 446 | 446 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 443 | 444 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 446 | 446 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 17 | A>B | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 444 | 444 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 445 | 446 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 446 | 445 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 445 | 444 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 446 | 446 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 446 | 445 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 446 | 446 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 445 | 444 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 445 | 445 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 445 | 444 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 445 | 446 |
| 29 | A>B | 2501 | 0 | sim | sim | sim | 445 | 444 |
| 30 | B>A | 2501 | 0 | sim | sim | sim | 445 | 445 |
