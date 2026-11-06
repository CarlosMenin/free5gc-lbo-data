# Campanha A x B - perfil `teleoperacao` - backhaul com fundo a 99%

**Carga:** 8 Mbps @ 60 fps (downlink), pose a 500 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 99% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (8 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~99.9% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.589 ± 0.218 | 1.446 ± 0.018 | +1.143 ± 0.219 | [+1.061; +1.225] | +1.159 | 43.8% | 30/30 |
| Atraso de rede p95 (ms) | 5.205 ± 0.443 | 1.843 ± 0.021 | +3.362 ± 0.447 | [+3.195; +3.529] | +3.372 | 64.3% | 30/30 |
| Atraso de rede p99 (ms) | 6.188 ± 0.328 | 2.736 ± 0.110 | +3.452 ± 0.354 | [+3.320; +3.584] | +3.441 | 55.7% | 30/30 |
| Atraso de rede (media) (ms) | 2.836 ± 0.221 | 1.406 ± 0.016 | +1.430 ± 0.222 | [+1.347; +1.513] | +1.389 | 50.1% | 30/30 |
| Jitter de rede (us) | 443.8 ± 145.1 | 267.6 ± 111.6 | +176.3 ± 150.9 | [+119.9; +232.6] | +149.4 | 36.2% | 29/30 |
| Motion-to-photon p50 (ms) | 15.338 ± 0.215 | 14.098 ± 0.070 | +1.241 ± 0.223 | [+1.158; +1.324] | +1.199 | 8.1% | 30/30 |
| Motion-to-photon p95 (ms) | 17.945 ± 0.437 | 15.187 ± 0.047 | +2.758 ± 0.448 | [+2.590; +2.925] | +2.721 | 15.3% | 30/30 |
| Perda de pacotes DL (%) | 0.173 ± 0.044 | 0.012 ± 0.010 | +0.161 ± 0.044 | [+0.145; +0.178] | +0.159 | 92.8% | 30/30 |
| Quadros incompletos (%) | 1.41 ± 0.41 | 0.02 ± 0.01 | +1.38 ± 0.41 | [+1.23; +1.54] | +1.39 | 98.3% | 30/30 |
| Vazao DL (Mbps) | 8.05 ± 0.00 | 8.06 ± 0.00 | -0.01 ± 0.00 | [-0.01; -0.01] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.116 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.446 ± 0.018 | 2.719 ± 0.250 | +1.272 ± 0.254 | [+1.178; +1.367] | 88.1% |
| Atraso de rede p95 (ms) | 1.843 ± 0.021 | 4.305 ± 0.323 | +2.462 ± 0.328 | [+2.340; +2.585] | 133.7% |
| Atraso de rede p99 (ms) | 2.736 ± 0.110 | 5.395 ± 0.384 | +2.659 ± 0.386 | [+2.514; +2.803] | 97.4% |
| Atraso de rede (media) (ms) | 1.406 ± 0.016 | 2.839 ± 0.242 | +1.432 ± 0.245 | [+1.341; +1.524] | 101.9% |
| Jitter de rede (us) | 267.6 ± 111.6 | 469.4 ± 143.0 | +201.8 ± 163.0 | [+141.0; +262.7] | 93.7% |
| Motion-to-photon p50 (ms) | 14.098 ± 0.070 | 15.393 ± 0.240 | +1.295 ± 0.256 | [+1.199; +1.390] | 9.2% |
| Motion-to-photon p95 (ms) | 15.187 ± 0.047 | 17.189 ± 0.329 | +2.002 ± 0.345 | [+1.873; +2.130] | 13.2% |
| Perda de pacotes DL (%) | 0.012 ± 0.010 | 0.180 ± 0.120 | +0.169 ± 0.122 | [+0.123; +0.214] | 1896.8% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 1.54 ± 1.28 | +1.52 ± 1.28 | [+1.04; +2.00] | 4782.5% |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.05 ± 0.01 | -0.01 ± 0.01 | [-0.02; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 5001 | 0 | sim | sim | sim | 881 | 880 |
| 2 | B>A | 5000 | 0 | sim | sim | sim | 873 | 867 |
| 3 | A>B | 5001 | 0 | sim | sim | sim | 881 | 877 |
| 4 | B>A | 4999 | 0 | sim | sim | sim | 874 | 875 |
| 5 | A>B | 5001 | 0 | sim | sim | sim | 877 | 881 |
| 6 | B>A | 5001 | 0 | sim | sim | sim | 867 | 881 |
| 7 | A>B | 5001 | 0 | sim | sim | sim | 876 | 875 |
| 8 | B>A | 5000 | 0 | sim | sim | sim | 865 | 865 |
| 9 | A>B | 5001 | 0 | sim | sim | sim | 868 | 863 |
| 10 | B>A | 5000 | 0 | sim | sim | sim | 878 | 880 |
| 11 | A>B | 5001 | 0 | sim | sim | sim | 879 | 880 |
| 12 | B>A | 5000 | 0 | sim | sim | sim | 874 | 877 |
| 13 | A>B | 5000 | 0 | sim | sim | sim | 865 | 876 |
| 14 | B>A | 5001 | 0 | sim | sim | sim | 873 | 873 |
| 15 | A>B | 5001 | 0 | sim | sim | sim | 870 | 872 |
| 16 | B>A | 5001 | 0 | sim | sim | sim | 875 | 878 |
| 17 | A>B | 5001 | 0 | sim | sim | sim | 871 | 874 |
| 18 | B>A | 5001 | 0 | sim | sim | sim | 875 | 874 |
| 19 | A>B | 5001 | 0 | sim | sim | sim | 874 | 862 |
| 20 | B>A | 5001 | 0 | sim | sim | sim | 878 | 873 |
| 21 | A>B | 4998 | 0 | sim | sim | sim | 869 | 877 |
| 22 | B>A | 5000 | 0 | sim | sim | sim | 873 | 868 |
| 23 | A>B | 5001 | 0 | sim | sim | sim | 868 | 870 |
| 24 | B>A | 5001 | 0 | sim | sim | sim | 879 | 875 |
| 25 | A>B | 5001 | 0 | sim | sim | sim | 861 | 865 |
| 26 | B>A | 5000 | 0 | sim | sim | sim | 870 | 869 |
| 27 | A>B | 5001 | 0 | sim | sim | sim | 875 | 870 |
| 28 | B>A | 5001 | 0 | sim | sim | sim | 876 | 871 |
| 29 | A>B | 5001 | 0 | sim | sim | sim | 867 | 853 |
| 30 | B>A | 5001 | 0 | sim | sim | sim | 877 | 874 |
