# Campanha A x B - perfil `teleoperacao` - backhaul com fundo a 50%

**Carga:** 8 Mbps @ 60 fps (downlink), pose a 500 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 50% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (8 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~50.9% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.038 ± 0.081 | 1.446 ± 0.019 | +0.592 ± 0.082 | [+0.561; +0.622] | +0.605 | 28.9% | 30/30 |
| Atraso de rede p95 (ms) | 2.583 ± 0.152 | 1.854 ± 0.029 | +0.729 ± 0.150 | [+0.673; +0.785] | +0.729 | 28.0% | 30/30 |
| Atraso de rede p99 (ms) | 3.634 ± 0.545 | 2.797 ± 0.163 | +0.837 ± 0.528 | [+0.640; +1.034] | +0.711 | 22.0% | 30/30 |
| Atraso de rede (media) (ms) | 2.028 ± 0.088 | 1.409 ± 0.016 | +0.620 ± 0.088 | [+0.587; +0.652] | +0.636 | 30.4% | 30/30 |
| Jitter de rede (us) | 276.9 ± 66.1 | 262.6 ± 87.7 | +14.3 ± 117.6 | [-29.7; +58.2] | +12.5 | -0.4% | 17/30 |
| Motion-to-photon p50 (ms) | 14.691 ± 0.081 | 14.106 ± 0.053 | +0.586 ± 0.096 | [+0.550; +0.621] | +0.582 | 4.0% | 30/30 |
| Motion-to-photon p95 (ms) | 15.774 ± 0.155 | 15.174 ± 0.048 | +0.600 ± 0.156 | [+0.542; +0.658] | +0.589 | 3.8% | 30/30 |
| Perda de pacotes DL (%) | 0.010 ± 0.010 | 0.011 ± 0.009 | -0.000 ± 0.015 | [-0.006; +0.005] | -0.002 | -112.7% | 11/30 |
| Quadros incompletos (%) | 0.03 ± 0.04 | 0.02 ± 0.01 | +0.01 ± 0.04 | [-0.00; +0.03] | +0.00 | 42.4% | 12/30 |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.06 ± 0.00 | -0.00 ± 0.00 | [-0.00; +0.00] | +0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.043 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.446 ± 0.019 | 2.230 ± 0.106 | +0.784 ± 0.102 | [+0.746; +0.822] | 54.2% |
| Atraso de rede p95 (ms) | 1.854 ± 0.029 | 3.023 ± 0.113 | +1.169 ± 0.107 | [+1.129; +1.208] | 63.0% |
| Atraso de rede p99 (ms) | 2.797 ± 0.163 | 4.671 ± 0.210 | +1.874 ± 0.316 | [+1.756; +1.991] | 67.7% |
| Atraso de rede (media) (ms) | 1.409 ± 0.016 | 2.251 ± 0.097 | +0.842 ± 0.093 | [+0.807; +0.877] | 59.8% |
| Jitter de rede (us) | 262.6 ± 87.7 | 395.1 ± 146.5 | +132.4 ± 132.3 | [+83.1; +181.8] | 57.2% |
| Motion-to-photon p50 (ms) | 14.106 ± 0.053 | 14.868 ± 0.098 | +0.762 ± 0.104 | [+0.723; +0.801] | 5.4% |
| Motion-to-photon p95 (ms) | 15.174 ± 0.048 | 16.149 ± 0.122 | +0.975 ± 0.137 | [+0.924; +1.026] | 6.4% |
| Perda de pacotes DL (%) | 0.011 ± 0.009 | 0.015 ± 0.010 | +0.005 ± 0.014 | [-0.001; +0.010] | 162.2% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.06 ± 0.05 | +0.04 ± 0.05 | [+0.02; +0.06] | 56.1% |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.06 ± 0.00 | -0.00 ± 0.00 | [-0.00; -0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 4999 | 0 | sim | sim | sim | 445 | 445 |
| 2 | B>A | 5001 | 0 | sim | sim | sim | 445 | 445 |
| 3 | A>B | 5001 | 0 | sim | sim | sim | 445 | 445 |
| 4 | B>A | 5001 | 0 | sim | sim | sim | 444 | 444 |
| 5 | A>B | 5001 | 0 | sim | sim | sim | 445 | 444 |
| 6 | B>A | 4998 | 0 | sim | sim | sim | 445 | 445 |
| 7 | A>B | 5000 | 0 | sim | sim | sim | 445 | 444 |
| 8 | B>A | 5001 | 0 | sim | sim | sim | 439 | 439 |
| 9 | A>B | 5001 | 0 | sim | sim | sim | 442 | 443 |
| 10 | B>A | 5001 | 0 | sim | sim | sim | 446 | 445 |
| 11 | A>B | 5001 | 0 | sim | sim | sim | 446 | 446 |
| 12 | B>A | 5001 | 0 | sim | sim | sim | 444 | 444 |
| 13 | A>B | 5001 | 0 | sim | sim | sim | 443 | 444 |
| 14 | B>A | 5001 | 0 | sim | sim | sim | 445 | 445 |
| 15 | A>B | 5000 | 0 | sim | sim | sim | 443 | 443 |
| 16 | B>A | 5000 | 0 | sim | sim | sim | 444 | 444 |
| 17 | A>B | 5001 | 0 | sim | sim | sim | 444 | 444 |
| 18 | B>A | 5001 | 0 | sim | sim | sim | 444 | 443 |
| 19 | A>B | 5001 | 0 | sim | sim | sim | 444 | 444 |
| 20 | B>A | 5000 | 0 | sim | sim | sim | 445 | 445 |
| 21 | A>B | 5001 | 0 | sim | sim | sim | 444 | 444 |
| 22 | B>A | 5001 | 0 | sim | sim | sim | 443 | 443 |
| 23 | A>B | 5001 | 0 | sim | sim | sim | 444 | 443 |
| 24 | B>A | 4996 | 0 | sim | sim | sim | 444 | 444 |
| 25 | A>B | 5001 | 0 | sim | sim | sim | 440 | 439 |
| 26 | B>A | 5000 | 0 | sim | sim | sim | 445 | 444 |
| 27 | A>B | 5001 | 0 | sim | sim | sim | 445 | 444 |
| 28 | B>A | 5000 | 0 | sim | sim | sim | 443 | 443 |
| 29 | A>B | 5001 | 0 | sim | sim | sim | 442 | 442 |
| 30 | B>A | 5001 | 0 | sim | sim | sim | 444 | 444 |
