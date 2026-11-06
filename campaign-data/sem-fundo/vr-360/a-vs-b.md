# Campanha A x B - perfil `vr-360`

**Carga:** 25 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- a-mec 2.107 ms, todas as rodadas dentro de +-25%; b-mec 1.560 ms, todas as rodadas dentro de +-25%. Rodada fora da faixa sem fundo aponta defeito no testbed (como o de 14-26/09), nao efeito do LBO: investigar antes de usar.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.102 ± 0.108 | 1.582 ± 0.111 | +0.520 ± 0.127 | [+0.472; +0.567] | +0.528 | 24.6% | 30/30 |
| Atraso de rede p95 (ms) | 5.391 ± 5.999 | 2.266 ± 0.142 | +3.125 ± 5.935 | [+0.909; +5.341] | +0.565 | 30.3% | 30/30 |
| Atraso de rede p99 (ms) | 7.329 ± 7.752 | 3.531 ± 0.300 | +3.797 ± 7.672 | [+0.933; +6.662] | +0.584 | 23.9% | 28/30 |
| Atraso de rede (media) (ms) | 2.475 ± 0.970 | 1.582 ± 0.091 | +0.894 ± 0.940 | [+0.542; +1.245] | +0.558 | 30.7% | 30/30 |
| Jitter de rede (us) | 395.1 ± 206.0 | 354.8 ± 173.2 | +40.3 ± 287.8 | [-67.2; +147.7] | +56.5 | -8.4% | 18/30 |
| Motion-to-photon p50 (ms) | 18.784 ± 2.366 | 18.516 ± 2.331 | +0.268 ± 3.550 | [-1.057; +1.593] | +0.336 | -0.4% | 15/30 |
| Motion-to-photon p95 (ms) | 22.154 ± 6.352 | 19.266 ± 2.233 | +2.888 ± 6.788 | [+0.353; +5.422] | +1.050 | 7.8% | 19/30 |
| Perda de pacotes DL (%) | 0.017 ± 0.012 | 0.013 ± 0.010 | +0.004 ± 0.015 | [-0.001; +0.009] | +0.001 | -34.8% | 15/30 |
| Quadros incompletos (%) | 0.04 ± 0.05 | 0.02 ± 0.01 | +0.02 ± 0.05 | [+0.00; +0.04] | +0.00 | 30.8% | 10/30 |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.34 ± 0.00 | -0.00 ± 0.00 | [-0.00; +0.00] | +0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.067 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.582 ± 0.111 | 2.066 ± 0.104 | +0.484 ± 0.157 | [+0.425; +0.542] | 31.2% |
| Atraso de rede p95 (ms) | 2.266 ± 0.142 | 4.035 ± 0.642 | +1.769 ± 0.627 | [+1.535; +2.003] | 78.4% |
| Atraso de rede p99 (ms) | 3.531 ± 0.300 | 7.081 ± 4.866 | +3.550 ± 4.769 | [+1.770; +5.331] | 98.4% |
| Atraso de rede (media) (ms) | 1.582 ± 0.091 | 2.271 ± 0.253 | +0.690 ± 0.251 | [+0.596; +0.783] | 43.9% |
| Jitter de rede (us) | 354.8 ± 173.2 | 541.2 ± 239.6 | +186.4 ± 305.2 | [+72.4; +300.3] | 79.0% |
| Motion-to-photon p50 (ms) | 18.516 ± 2.331 | 18.118 ± 2.514 | -0.397 ± 3.225 | [-1.602; +0.807] | -0.7% |
| Motion-to-photon p95 (ms) | 19.266 ± 2.233 | 21.224 ± 2.069 | +1.958 ± 2.428 | [+1.052; +2.865] | 11.2% |
| Perda de pacotes DL (%) | 0.013 ± 0.010 | 0.013 ± 0.010 | +0.000 ± 0.014 | [-0.005; +0.006] | -10.4% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.04 ± 0.05 | +0.02 ± 0.05 | [-0.00; +0.04] | 53.4% |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.34 ± 0.01 | -0.00 ± 0.01 | [-0.01; -0.00] | - |

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
