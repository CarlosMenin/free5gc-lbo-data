# Campanha A x B - perfil `cloud-gaming`

**Carga:** 30 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- a-mec 2.134 ms, FORA de +-25% nas rodadas 12 (3.254), 13 (3.586); b-mec 1.487 ms, todas as rodadas dentro de +-25%. Rodada fora da faixa sem fundo aponta defeito no testbed (como o de 14-26/09), nao efeito do LBO: investigar antes de usar.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.222 ± 0.338 | 1.504 ± 0.092 | +0.718 ± 0.340 | [+0.591; +0.845] | +0.681 | 31.3% | 30/30 |
| Atraso de rede p95 (ms) | 4.209 ± 5.002 | 2.120 ± 0.151 | +2.089 ± 4.988 | [+0.227; +3.951] | +0.972 | 35.5% | 30/30 |
| Atraso de rede p99 (ms) | 5.551 ± 6.108 | 3.306 ± 0.310 | +2.246 ± 6.117 | [-0.038; +4.530] | +1.043 | 26.4% | 29/30 |
| Atraso de rede (media) (ms) | 2.424 ± 0.881 | 1.504 ± 0.084 | +0.920 ± 0.862 | [+0.598; +1.242] | +0.730 | 34.4% | 30/30 |
| Jitter de rede (us) | 421.0 ± 325.4 | 306.7 ± 109.7 | +114.4 ± 368.0 | [-23.1; +251.8] | +24.8 | 6.5% | 18/30 |
| Motion-to-photon p50 (ms) | 18.863 ± 2.362 | 17.924 ± 2.293 | +0.939 ± 3.209 | [-0.259; +2.137] | +0.480 | 3.6% | 17/30 |
| Motion-to-photon p95 (ms) | 21.310 ± 5.524 | 18.756 ± 2.279 | +2.554 ± 5.976 | [+0.323; +4.785] | +1.958 | 8.7% | 22/30 |
| Perda de pacotes DL (%) | 0.067 ± 0.160 | 0.010 ± 0.009 | +0.058 ± 0.158 | [-0.002; +0.117] | +0.011 | -18.5% | 21/30 |
| Quadros incompletos (%) | 1.01 ± 2.67 | 0.02 ± 0.01 | +0.99 ± 2.67 | [-0.01; +1.99] | +0.06 | 56.3% | 18/30 |
| Vazao DL (Mbps) | 30.50 ± 0.05 | 30.52 ± 0.01 | -0.02 ± 0.05 | [-0.04; +0.00] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.180 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.504 ± 0.092 | 1.954 ± 0.160 | +0.449 ± 0.183 | [+0.381; +0.518] | 30.3% |
| Atraso de rede p95 (ms) | 2.120 ± 0.151 | 6.284 ± 11.760 | +4.164 ± 11.761 | [-0.227; +8.555] | 197.3% |
| Atraso de rede p99 (ms) | 3.306 ± 0.310 | 11.145 ± 26.247 | +7.840 ± 26.278 | [-1.972; +17.651] | 246.0% |
| Atraso de rede (media) (ms) | 1.504 ± 0.084 | 2.425 ± 1.305 | +0.922 ± 1.298 | [+0.437; +1.406] | 61.2% |
| Jitter de rede (us) | 306.7 ± 109.7 | 613.4 ± 160.1 | +306.7 ± 222.3 | [+223.8; +389.7] | 127.3% |
| Motion-to-photon p50 (ms) | 17.924 ± 2.293 | 18.492 ± 2.102 | +0.568 ± 2.897 | [-0.514; +1.649] | 4.6% |
| Motion-to-photon p95 (ms) | 18.756 ± 2.279 | 23.111 ± 12.400 | +4.355 ± 12.776 | [-0.415; +9.125] | 25.4% |
| Perda de pacotes DL (%) | 0.010 ± 0.009 | 0.032 ± 0.065 | +0.023 ± 0.063 | [-0.001; +0.046] | 364.3% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.55 ± 1.63 | +0.53 ± 1.63 | [-0.08; +1.14] | 2255.7% |
| Vazao DL (Mbps) | 30.52 ± 0.01 | 30.51 ± 0.02 | -0.01 ± 0.02 | [-0.02; +0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par |
|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim |
| 2 | B>A | 1201 | 0 | sim | sim | sim |
| 3 | A>B | 1201 | 0 | sim | sim | sim |
| 4 | B>A | 1201 | 0 | sim | sim | sim |
| 5 | A>B | 1201 | 0 | sim | sim | sim |
| 6 | B>A | 1201 | 0 | sim | sim | sim |
| 7 | A>B | 1201 | 0 | sim | sim | sim |
| 8 | B>A | 1201 | 0 | sim | sim | sim |
| 9 | A>B | 1201 | 0 | sim | sim | sim |
| 10 | B>A | 1201 | 0 | sim | sim | sim |
| 11 | A>B | 1201 | 0 | sim | sim | sim |
| 12 | B>A | 1201 | 0 | sim | sim | sim |
| 13 | A>B | 1201 | 0 | sim | sim | sim |
| 14 | B>A | 1201 | 0 | sim | sim | sim |
| 15 | A>B | 1201 | 0 | sim | sim | sim |
| 16 | B>A | 1201 | 0 | sim | sim | sim |
| 17 | A>B | 1201 | 0 | sim | sim | sim |
| 18 | B>A | 1201 | 0 | sim | sim | sim |
| 19 | A>B | 1201 | 0 | sim | sim | sim |
| 20 | B>A | 1201 | 0 | sim | sim | sim |
| 21 | A>B | 1201 | 0 | sim | sim | sim |
| 22 | B>A | 1201 | 0 | sim | sim | sim |
| 23 | A>B | 1201 | 0 | sim | sim | sim |
| 24 | B>A | 1201 | 0 | sim | sim | sim |
| 25 | A>B | 1201 | 0 | sim | sim | sim |
| 26 | B>A | 1201 | 0 | sim | sim | sim |
| 27 | A>B | 1201 | 0 | sim | sim | sim |
| 28 | B>A | 1201 | 0 | sim | sim | sim |
| 29 | A>B | 1201 | 0 | sim | sim | sim |
| 30 | B>A | 1201 | 0 | sim | sim | sim |
