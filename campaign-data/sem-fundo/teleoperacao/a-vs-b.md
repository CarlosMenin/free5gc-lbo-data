# Campanha A x B - perfil `teleoperacao`

**Carga:** 8 Mbps @ 60 fps (downlink), pose a 500 Hz (uplink), MTU 1200 B.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- a-mec 2.087 ms, todas as rodadas dentro de +-25%; b-mec 1.446 ms, todas as rodadas dentro de +-25%. Rodada fora da faixa sem fundo aponta defeito no testbed (como o de 14-26/09), nao efeito do LBO: investigar antes de usar.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.076 ± 0.036 | 1.448 ± 0.016 | +0.628 ± 0.036 | [+0.615; +0.642] | +0.639 | 30.2% | 30/30 |
| Atraso de rede p95 (ms) | 2.545 ± 0.170 | 1.848 ± 0.019 | +0.697 ± 0.175 | [+0.632; +0.762] | +0.663 | 27.1% | 30/30 |
| Atraso de rede p99 (ms) | 3.542 ± 0.684 | 2.759 ± 0.129 | +0.784 ± 0.708 | [+0.520; +1.048] | +0.646 | 20.4% | 30/30 |
| Atraso de rede (media) (ms) | 2.045 ± 0.044 | 1.407 ± 0.015 | +0.638 ± 0.044 | [+0.621; +0.654] | +0.641 | 31.2% | 30/30 |
| Jitter de rede (us) | 248.5 ± 80.2 | 268.1 ± 102.4 | -19.6 ± 85.0 | [-51.3; +12.2] | -14.6 | -12.2% | 13/30 |
| Motion-to-photon p50 (ms) | 14.692 ± 0.057 | 14.096 ± 0.056 | +0.597 ± 0.085 | [+0.565; +0.628] | +0.597 | 4.1% | 30/30 |
| Motion-to-photon p95 (ms) | 15.783 ± 0.108 | 15.177 ± 0.060 | +0.606 ± 0.120 | [+0.561; +0.651] | +0.594 | 3.8% | 30/30 |
| Perda de pacotes DL (%) | 0.009 ± 0.009 | 0.012 ± 0.009 | -0.003 ± 0.011 | [-0.007; +0.001] | -0.002 | -27.7% | 11/30 |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.02 ± 0.01 | -0.00 ± 0.02 | [-0.01; +0.00] | +0.00 | 14.3% | 3/30 |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.06 ± 0.00 | +0.00 ± 0.00 | [-0.00; +0.00] | +0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.019 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.448 ± 0.016 | 2.271 ± 0.100 | +0.823 ± 0.101 | [+0.786; +0.861] | 56.9% |
| Atraso de rede p95 (ms) | 1.848 ± 0.019 | 3.003 ± 0.131 | +1.154 ± 0.127 | [+1.107; +1.202] | 62.5% |
| Atraso de rede p99 (ms) | 2.759 ± 0.129 | 4.787 ± 1.318 | +2.029 ± 1.334 | [+1.531; +2.527] | 74.1% |
| Atraso de rede (media) (ms) | 1.407 ± 0.015 | 2.280 ± 0.105 | +0.872 ± 0.105 | [+0.833; +0.912] | 62.0% |
| Jitter de rede (us) | 268.1 ± 102.4 | 421.0 ± 164.3 | +152.9 ± 160.2 | [+93.1; +212.7] | 71.1% |
| Motion-to-photon p50 (ms) | 14.096 ± 0.056 | 14.888 ± 0.108 | +0.793 ± 0.125 | [+0.746; +0.839] | 5.6% |
| Motion-to-photon p95 (ms) | 15.177 ± 0.060 | 16.149 ± 0.160 | +0.972 ± 0.179 | [+0.905; +1.039] | 6.4% |
| Perda de pacotes DL (%) | 0.012 ± 0.009 | 0.014 ± 0.009 | +0.001 ± 0.012 | [-0.003; +0.006] | 56.3% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.02 ± 0.01 | +0.00 ± 0.01 | [-0.01; +0.01] | -16.0% |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.06 ± 0.00 | -0.00 ± 0.00 | [-0.00; -0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par |
|---|---|---|---|---|---|---|
| 1 | A>B | 5001 | 0 | sim | sim | sim |
| 2 | B>A | 5000 | 0 | sim | sim | sim |
| 3 | A>B | 5001 | 0 | sim | sim | sim |
| 4 | B>A | 4999 | 0 | sim | sim | sim |
| 5 | A>B | 5001 | 0 | sim | sim | sim |
| 6 | B>A | 5001 | 0 | sim | sim | sim |
| 7 | A>B | 5001 | 0 | sim | sim | sim |
| 8 | B>A | 5001 | 0 | sim | sim | sim |
| 9 | A>B | 5001 | 0 | sim | sim | sim |
| 10 | B>A | 5001 | 0 | sim | sim | sim |
| 11 | A>B | 5001 | 0 | sim | sim | sim |
| 12 | B>A | 5001 | 0 | sim | sim | sim |
| 13 | A>B | 5001 | 0 | sim | sim | sim |
| 14 | B>A | 5000 | 0 | sim | sim | sim |
| 15 | A>B | 5001 | 0 | sim | sim | sim |
| 16 | B>A | 5001 | 0 | sim | sim | sim |
| 17 | A>B | 5001 | 0 | sim | sim | sim |
| 18 | B>A | 5001 | 0 | sim | sim | sim |
| 19 | A>B | 5001 | 0 | sim | sim | sim |
| 20 | B>A | 5000 | 0 | sim | sim | sim |
| 21 | A>B | 5001 | 0 | sim | sim | sim |
| 22 | B>A | 5001 | 0 | sim | sim | sim |
| 23 | A>B | 5001 | 0 | sim | sim | sim |
| 24 | B>A | 4999 | 0 | sim | sim | sim |
| 25 | A>B | 5000 | 0 | sim | sim | sim |
| 26 | B>A | 5001 | 0 | sim | sim | sim |
| 27 | A>B | 5001 | 0 | sim | sim | sim |
| 28 | B>A | 5001 | 0 | sim | sim | sim |
| 29 | A>B | 5001 | 0 | sim | sim | sim |
| 30 | B>A | 5001 | 0 | sim | sim | sim |
