# Campanha A x B - perfil `vr-360` - backhaul com fundo a 95%

**Carga:** 25 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 95% da capacidade medida no inicio de cada rodada (media 886 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (25 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~97.8% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 2 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 3.122 ± 1.023 | 1.592 ± 0.112 | +1.530 ± 1.070 | [+1.131; +1.930] | +1.316 | 45.4% | 30/30 |
| Atraso de rede p95 (ms) | 5.984 ± 2.881 | 2.270 ± 0.124 | +3.714 ± 2.872 | [+2.642; +4.786] | +2.980 | 57.9% | 30/30 |
| Atraso de rede p99 (ms) | 7.756 ± 3.892 | 3.558 ± 0.259 | +4.198 ± 3.855 | [+2.759; +5.637] | +2.862 | 48.5% | 30/30 |
| Atraso de rede (media) (ms) | 3.340 ± 1.113 | 1.590 ± 0.088 | +1.750 ± 1.139 | [+1.325; +2.175] | +1.458 | 49.1% | 30/30 |
| Jitter de rede (us) | 575.4 ± 208.8 | 359.1 ± 216.0 | +216.4 ± 313.3 | [+99.4; +333.4] | +211.5 | 28.8% | 25/30 |
| Motion-to-photon p50 (ms) | 20.121 ± 2.547 | 18.366 ± 1.921 | +1.755 ± 3.212 | [+0.556; +2.954] | +1.372 | 7.2% | 21/30 |
| Motion-to-photon p95 (ms) | 22.476 ± 3.238 | 18.821 ± 1.913 | +3.656 ± 3.430 | [+2.375; +4.936] | +3.395 | 14.9% | 26/30 |
| Perda de pacotes DL (%) | 0.283 ± 0.279 | 0.012 ± 0.009 | +0.271 ± 0.274 | [+0.169; +0.374] | +0.168 | 94.7% | 30/30 |
| Quadros incompletos (%) | 5.09 ± 6.99 | 0.03 ± 0.01 | +5.07 ± 6.99 | [+2.46; +7.68] | +2.44 | 99.0% | 30/30 |
| Vazao DL (Mbps) | 25.27 ± 0.08 | 25.34 ± 0.00 | -0.07 ± 0.08 | [-0.10; -0.04] | -0.04 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.566 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (28 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.594 ± 0.111 | 2.649 ± 0.394 | +1.055 ± 0.430 | [+0.888; +1.222] | 67.2% |
| Atraso de rede p95 (ms) | 2.267 ± 0.128 | 4.895 ± 0.576 | +2.628 ± 0.572 | [+2.406; +2.850] | 116.4% |
| Atraso de rede p99 (ms) | 3.549 ± 0.266 | 6.996 ± 0.579 | +3.447 ± 0.554 | [+3.232; +3.661] | 97.9% |
| Atraso de rede (media) (ms) | 1.591 ± 0.088 | 2.884 ± 0.391 | +1.293 ± 0.416 | [+1.131; +1.454] | 82.0% |
| Jitter de rede (us) | 351.7 ± 221.9 | 747.4 ± 187.1 | +395.7 ± 304.0 | [+277.8; +513.6] | 162.7% |
| Motion-to-photon p50 (ms) | 18.356 ± 1.981 | 19.287 ± 2.349 | +0.931 ± 3.057 | [-0.254; +2.117] | 6.2% |
| Motion-to-photon p95 (ms) | 18.810 ± 1.972 | 21.971 ± 1.577 | +3.161 ± 2.524 | [+2.183; +4.140] | 18.1% |
| Perda de pacotes DL (%) | 0.012 ± 0.009 | 0.220 ± 0.166 | +0.209 ± 0.162 | [+0.146; +0.272] | 2852.7% |
| Quadros incompletos (%) | 0.03 ± 0.01 | 3.96 ± 4.46 | +3.94 ± 4.46 | [+2.21; +5.67] | 14736.3% |
| Vazao DL (Mbps) | 25.34 ± 0.00 | 25.28 ± 0.04 | -0.06 ± 0.04 | [-0.07; -0.04] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 826 | 826 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 811 | 812 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 815 | 810 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 835 | 838 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 838 | 835 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 821 | 831 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 833 | 833 |
| 8 | B>A | 1201 | 0 | sim | sim | sim | 827 | 822 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 824 | 845 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 850 | 830 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 835 | 831 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 819 | 832 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 825 | 836 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 821 | 829 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 836 | 833 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 832 | 814 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 835 | 831 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 817 | 816 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 821 | 811 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 822 | 818 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 840 | 824 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 841 | 830 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 842 | 831 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 825 | 820 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 841 | 836 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 846 | 833 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 829 | 825 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 826 | 826 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 826 | 814 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 837 | 842 |
