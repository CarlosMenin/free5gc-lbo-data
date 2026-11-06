# Campanha A x B - perfil `vr-extremo`

**Carga:** 100 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 28 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Execucoes refeitas:** 2 por falha de infraestrutura (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade nunca e' refeita.

**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- a-mec 1.357 ms, todas as rodadas dentro de +-25%; b-mec 0.581 ms, todas as rodadas dentro de +-25%. Rodada fora da faixa sem fundo aponta defeito no testbed (como o de 14-26/09), nao efeito do LBO: investigar antes de usar.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.348 ± 0.049 | 0.582 ± 0.010 | +0.766 ± 0.047 | [+0.748; +0.784] | +0.771 | 56.8% | 28/28 |
| Atraso de rede p95 (ms) | 1.855 ± 0.206 | 1.022 ± 0.034 | +0.833 ± 0.204 | [+0.754; +0.912] | +0.786 | 44.4% | 28/28 |
| Atraso de rede p99 (ms) | 4.589 ± 6.817 | 2.610 ± 0.270 | +1.979 ± 6.814 | [-0.664; +4.621] | +0.387 | 17.2% | 25/28 |
| Atraso de rede (media) (ms) | 1.462 ± 0.209 | 0.673 ± 0.011 | +0.790 ± 0.210 | [+0.708; +0.871] | +0.754 | 53.4% | 28/28 |
| Jitter de rede (us) | 327.2 ± 177.0 | 340.9 ± 213.8 | -13.7 ± 307.1 | [-132.8; +105.4] | +17.5 | -27.6% | 15/28 |
| Motion-to-photon p50 (ms) | 11.548 ± 0.102 | 10.967 ± 0.096 | +0.581 ± 0.141 | [+0.526; +0.635] | +0.615 | 5.0% | 28/28 |
| Motion-to-photon p95 (ms) | 13.368 ± 0.115 | 12.785 ± 0.104 | +0.582 ± 0.148 | [+0.525; +0.640] | +0.556 | 4.4% | 28/28 |
| Perda de pacotes DL (%) | 0.888 ± 0.008 | 0.890 ± 0.009 | -0.002 ± 0.012 | [-0.006; +0.003] | -0.000 | -0.2% | 11/28 |
| Quadros incompletos (%) | 29.29 ± 0.32 | 29.74 ± 0.35 | -0.45 ± 0.45 | [-0.62; -0.27] | -0.46 | -1.5% | 7/28 |
| Vazao DL (Mbps) | 99.23 ± 0.01 | 99.24 ± 0.01 | -0.00 ± 0.02 | [-0.01; +0.00] | -0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 28 par(es) (alfa 5%, poder 80%): **0.026 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (28 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.582 ± 0.010 | 1.876 ± 0.045 | +1.294 ± 0.045 | [+1.277; +1.311] | 222.4% |
| Atraso de rede p95 (ms) | 1.022 ± 0.034 | 5.576 ± 0.123 | +4.554 ± 0.130 | [+4.503; +4.604] | 446.1% |
| Atraso de rede p99 (ms) | 2.610 ± 0.270 | 8.054 ± 0.299 | +5.444 ± 0.436 | [+5.275; +5.613] | 212.2% |
| Atraso de rede (media) (ms) | 0.673 ± 0.011 | 2.510 ± 0.044 | +1.837 ± 0.045 | [+1.820; +1.855] | 273.2% |
| Jitter de rede (us) | 340.9 ± 213.8 | 1987.3 ± 436.3 | +1646.4 ± 461.0 | [+1467.6; +1825.2] | 687.1% |
| Motion-to-photon p50 (ms) | 10.967 ± 0.096 | 12.692 ± 0.058 | +1.724 ± 0.125 | [+1.676; +1.773] | 15.7% |
| Motion-to-photon p95 (ms) | 12.785 ± 0.104 | 17.063 ± 0.117 | +4.277 ± 0.169 | [+4.212; +4.343] | 33.5% |
| Perda de pacotes DL (%) | 0.890 ± 0.009 | 0.907 ± 0.013 | +0.017 ± 0.013 | [+0.012; +0.022] | 1.9% |
| Quadros incompletos (%) | 29.74 ± 0.35 | 25.22 ± 0.65 | -4.51 ± 0.66 | [-4.77; -4.26] | -15.2% |
| Vazao DL (Mbps) | 99.24 ± 0.01 | 99.21 ± 0.01 | -0.02 ± 0.01 | [-0.03; -0.02] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par |
|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim |
| 2 | B>A | 2501 | 0 | sim | sim | sim |
| 3 | A>B | 2501 | 0 | sim | sim | sim |
| 4 | B>A | 2501 | 0 | sim | sim | sim |
| 5 | A>B | 2501 | 0 | sim | sim | sim |
| 6 | B>A | 2501 | 0 | sim | sim | sim |
| 7 | A>B | 2501 | 0 | sim | sim | sim |
| 8 | B>A | 2501 | 0 | sim | sim | sim |
| 9 | A>B | 2501 | 0 | sim | sim | sim |
| 10 | B>A | 2501 | 0 | sim | sim | sim |
| 11 | A>B | 2501 | 0 | sim | sim | sim |
| 12 | B>A | 2501 | 0 | sim | sim | sim |
| 13 | A>B | 2501 | 0 | sim | sim | sim |
| 14 | B>A | 2501 | 0 | sim | sim | sim |
| 15 | A>B | 2501 | 0 | sim | sim | sim |
| 16 | B>A | 2501 | 0 | sim | sim | sim |
| 17 | A>B | 2501 | falhou | sim | - | nao |
| 18 | B>A | 2501 | 0 | sim | sim | sim |
| 19 | A>B | 2501 | 0 | sim | sim | sim |
| 20 | B>A | 2501 | 0 | sim | sim | sim |
| 21 | A>B | 2501 | 0 | sim | sim | sim |
| 22 | B>A | 2501 | 0 | sim | sim | sim |
| 23 | A>B | 2501 | 0 | sim | sim | sim |
| 24 | B>A | 2501 | 0 | sim | sim | sim |
| 25 | A>B | 2501 | 0 | sim | sim | sim |
| 26 | B>A | 2501 | 0 | sim | sim | sim |
| 27 | A>B | 2501 | 0 | sim | sim | sim |
| 28 | B>A | 2500 | 0 | sim | sim | sim |
| 29 | A>B | 2501 | falhou | sim | - | nao |
| 30 | B>A | 2501 | 0 | sim | sim | sim |
