# Campanha A x B - perfil `vr-cloud`

**Carga:** 50 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- a-mec 1.556 ms, todas as rodadas dentro de +-25%; b-mec 0.947 ms, todas as rodadas dentro de +-25%. Rodada fora da faixa sem fundo aponta defeito no testbed (como o de 14-26/09), nao efeito do LBO: investigar antes de usar.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.560 ± 0.022 | 0.950 ± 0.016 | +0.610 ± 0.027 | [+0.600; +0.620] | +0.609 | 39.1% | 30/30 |
| Atraso de rede p95 (ms) | 2.141 ± 0.020 | 1.466 ± 0.036 | +0.674 ± 0.044 | [+0.658; +0.691] | +0.669 | 31.5% | 30/30 |
| Atraso de rede p99 (ms) | 2.899 ± 0.107 | 2.186 ± 0.103 | +0.713 ± 0.156 | [+0.655; +0.772] | +0.756 | 24.5% | 30/30 |
| Atraso de rede (media) (ms) | 1.591 ± 0.021 | 0.965 ± 0.015 | +0.626 ± 0.026 | [+0.616; +0.636] | +0.622 | 39.3% | 30/30 |
| Jitter de rede (us) | 256.2 ± 101.9 | 213.0 ± 92.7 | +43.2 ± 135.4 | [-7.3; +93.8] | +37.4 | 8.2% | 18/30 |
| Motion-to-photon p50 (ms) | 11.550 ± 0.049 | 10.981 ± 0.043 | +0.569 ± 0.064 | [+0.545; +0.593] | +0.572 | 4.9% | 30/30 |
| Motion-to-photon p95 (ms) | 13.408 ± 0.080 | 12.836 ± 0.060 | +0.571 ± 0.087 | [+0.539; +0.604] | +0.571 | 4.3% | 30/30 |
| Perda de pacotes DL (%) | 0.008 ± 0.006 | 0.006 ± 0.006 | +0.002 ± 0.008 | [-0.001; +0.005] | +0.000 | -68.3% | 14/30 |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.01 ± 0.01 | +0.00 ± 0.01 | [-0.00; +0.01] | +0.00 | 28.0% | 7/30 |
| Vazao DL (Mbps) | 50.11 ± 0.00 | 50.11 ± 0.00 | -0.00 ± 0.01 | [-0.00; +0.00] | +0.00 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.014 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.950 ± 0.016 | 1.450 ± 0.016 | +0.500 ± 0.019 | [+0.493; +0.507] | 52.7% |
| Atraso de rede p95 (ms) | 1.466 ± 0.036 | 3.423 ± 0.086 | +1.956 ± 0.093 | [+1.921; +1.991] | 133.5% |
| Atraso de rede p99 (ms) | 2.186 ± 0.103 | 5.283 ± 0.130 | +3.098 ± 0.156 | [+3.040; +3.156] | 142.2% |
| Atraso de rede (media) (ms) | 0.965 ± 0.015 | 1.679 ± 0.021 | +0.714 ± 0.023 | [+0.705; +0.723] | 74.0% |
| Jitter de rede (us) | 213.0 ± 92.7 | 487.1 ± 190.5 | +274.1 ± 220.8 | [+191.7; +356.5] | 158.8% |
| Motion-to-photon p50 (ms) | 10.981 ± 0.043 | 11.611 ± 0.039 | +0.630 ± 0.059 | [+0.608; +0.652] | 5.7% |
| Motion-to-photon p95 (ms) | 12.836 ± 0.060 | 14.242 ± 0.118 | +1.406 ± 0.131 | [+1.357; +1.455] | 11.0% |
| Perda de pacotes DL (%) | 0.006 ± 0.006 | 0.008 ± 0.007 | +0.003 ± 0.009 | [-0.001; +0.006] | 234.0% |
| Quadros incompletos (%) | 0.01 ± 0.01 | 0.01 ± 0.01 | +0.00 ± 0.01 | [-0.00; +0.00] | -23.8% |
| Vazao DL (Mbps) | 50.11 ± 0.00 | 50.10 ± 0.00 | -0.01 ± 0.01 | [-0.01; -0.01] | - |

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
| 17 | A>B | 2501 | 0 | sim | sim | sim |
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
| 28 | B>A | 2501 | 0 | sim | sim | sim |
| 29 | A>B | 2501 | 0 | sim | sim | sim |
| 30 | B>A | 2501 | 0 | sim | sim | sim |
