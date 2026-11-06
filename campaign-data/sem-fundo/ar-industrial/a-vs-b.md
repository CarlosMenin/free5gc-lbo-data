# Campanha A x B - perfil `ar-industrial`

**Carga:** 12 Mbps @ 60 fps (downlink), pose a 200 Hz (uplink), MTU 1200 B.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- a-mec 2.079 ms, FORA de +-25% nas rodadas 9 (7.857); b-mec 1.505 ms, todas as rodadas dentro de +-25%. Rodada fora da faixa sem fundo aponta defeito no testbed (como o de 14-26/09), nao efeito do LBO: investigar antes de usar.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.271 ± 1.055 | 1.504 ± 0.036 | +0.768 ± 1.053 | [+0.375; +1.161] | +0.592 | 29.4% | 30/30 |
| Atraso de rede p95 (ms) | 3.195 ± 3.253 | 1.945 ± 0.048 | +1.250 ± 3.247 | [+0.037; +2.462] | +0.665 | 27.4% | 30/30 |
| Atraso de rede p99 (ms) | 4.362 ± 3.699 | 2.921 ± 0.204 | +1.441 ± 3.670 | [+0.070; +2.811] | +0.762 | 22.6% | 29/30 |
| Atraso de rede (media) (ms) | 2.303 ± 1.235 | 1.494 ± 0.030 | +0.808 ± 1.231 | [+0.348; +1.268] | +0.600 | 29.9% | 30/30 |
| Jitter de rede (us) | 326.9 ± 167.5 | 270.0 ± 62.5 | +56.9 ± 181.4 | [-10.8; +124.6] | +49.7 | 6.4% | 18/30 |
| Motion-to-photon p50 (ms) | 17.134 ± 1.119 | 16.197 ± 0.355 | +0.936 ± 1.166 | [+0.501; +1.372] | +0.602 | 5.2% | 30/30 |
| Motion-to-photon p95 (ms) | 19.588 ± 3.052 | 18.227 ± 0.408 | +1.361 ± 3.124 | [+0.195; +2.527] | +0.706 | 5.7% | 30/30 |
| Perda de pacotes DL (%) | 0.015 ± 0.013 | 0.011 ± 0.010 | +0.004 ± 0.017 | [-0.003; +0.010] | +0.003 | 3.9% | 16/30 |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.02 ± 0.01 | +0.00 ± 0.02 | [-0.00; +0.01] | +0.00 | 28.3% | 7/30 |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.09 ± 0.00 | -0.00 ± 0.00 | [-0.00; +0.00] | -0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.557 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.504 ± 0.036 | 2.227 ± 0.034 | +0.723 ± 0.052 | [+0.704; +0.743] | 48.2% |
| Atraso de rede p95 (ms) | 1.945 ± 0.048 | 3.195 ± 0.164 | +1.249 ± 0.183 | [+1.181; +1.318] | 64.4% |
| Atraso de rede p99 (ms) | 2.921 ± 0.204 | 5.474 ± 2.471 | +2.553 ± 2.480 | [+1.627; +3.479] | 88.2% |
| Atraso de rede (media) (ms) | 1.494 ± 0.030 | 2.289 ± 0.075 | +0.794 ± 0.087 | [+0.762; +0.827] | 53.2% |
| Jitter de rede (us) | 270.0 ± 62.5 | 408.8 ± 111.1 | +138.9 ± 127.3 | [+91.3; +186.4] | 59.4% |
| Motion-to-photon p50 (ms) | 16.197 ± 0.355 | 16.858 ± 0.312 | +0.660 ± 0.506 | [+0.472; +0.849] | 4.1% |
| Motion-to-photon p95 (ms) | 18.227 ± 0.408 | 19.118 ± 0.340 | +0.891 ± 0.537 | [+0.691; +1.092] | 4.9% |
| Perda de pacotes DL (%) | 0.011 ± 0.010 | 0.016 ± 0.010 | +0.005 ± 0.013 | [+0.000; +0.010] | 144.6% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.02 ± 0.01 | +0.00 ± 0.02 | [-0.00; +0.01] | -9.5% |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.09 ± 0.00 | -0.00 ± 0.00 | [-0.00; -0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par |
|---|---|---|---|---|---|---|
| 1 | A>B | 2001 | 0 | sim | sim | sim |
| 2 | B>A | 2001 | 0 | sim | sim | sim |
| 3 | A>B | 2001 | 0 | sim | sim | sim |
| 4 | B>A | 2001 | 0 | sim | sim | sim |
| 5 | A>B | 2001 | 0 | sim | sim | sim |
| 6 | B>A | 2001 | 0 | sim | sim | sim |
| 7 | A>B | 2001 | 0 | sim | sim | sim |
| 8 | B>A | 2001 | 0 | sim | sim | sim |
| 9 | A>B | 2001 | 0 | sim | sim | sim |
| 10 | B>A | 2001 | 0 | sim | sim | sim |
| 11 | A>B | 2001 | 0 | sim | sim | sim |
| 12 | B>A | 2001 | 0 | sim | sim | sim |
| 13 | A>B | 2001 | 0 | sim | sim | sim |
| 14 | B>A | 2001 | 0 | sim | sim | sim |
| 15 | A>B | 2001 | 0 | sim | sim | sim |
| 16 | B>A | 2001 | 0 | sim | sim | sim |
| 17 | A>B | 2001 | 0 | sim | sim | sim |
| 18 | B>A | 2001 | 0 | sim | sim | sim |
| 19 | A>B | 2001 | 0 | sim | sim | sim |
| 20 | B>A | 2001 | 0 | sim | sim | sim |
| 21 | A>B | 2001 | 0 | sim | sim | sim |
| 22 | B>A | 2001 | 0 | sim | sim | sim |
| 23 | A>B | 2001 | 0 | sim | sim | sim |
| 24 | B>A | 2001 | 0 | sim | sim | sim |
| 25 | A>B | 2001 | 0 | sim | sim | sim |
| 26 | B>A | 2001 | 0 | sim | sim | sim |
| 27 | A>B | 2001 | 0 | sim | sim | sim |
| 28 | B>A | 2001 | 0 | sim | sim | sim |
| 29 | A>B | 2001 | 0 | sim | sim | sim |
| 30 | B>A | 2001 | 0 | sim | sim | sim |
