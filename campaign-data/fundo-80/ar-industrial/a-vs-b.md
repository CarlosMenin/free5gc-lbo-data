# Campanha A x B - perfil `ar-industrial` - backhaul com fundo a 80%

**Carga:** 12 Mbps @ 60 fps (downlink), pose a 200 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 80% da capacidade medida no inicio de cada rodada (media 887 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (12 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~81.4% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.177 ± 0.190 | 1.496 ± 0.025 | +0.680 ± 0.194 | [+0.608; +0.753] | +0.715 | 30.7% | 30/30 |
| Atraso de rede p95 (ms) | 2.998 ± 0.240 | 1.940 ± 0.036 | +1.058 ± 0.248 | [+0.966; +1.151] | +1.065 | 34.9% | 30/30 |
| Atraso de rede p99 (ms) | 4.872 ± 0.353 | 2.875 ± 0.182 | +1.996 ± 0.391 | [+1.850; +2.142] | +1.962 | 40.7% | 30/30 |
| Atraso de rede (media) (ms) | 2.228 ± 0.177 | 1.489 ± 0.021 | +0.739 ± 0.181 | [+0.671; +0.806] | +0.772 | 32.7% | 30/30 |
| Jitter de rede (us) | 403.7 ± 114.3 | 259.8 ± 63.1 | +143.9 ± 112.4 | [+101.9; +185.9] | +153.8 | 31.9% | 27/30 |
| Motion-to-photon p50 (ms) | 17.168 ± 0.487 | 16.298 ± 0.412 | +0.870 ± 0.707 | [+0.606; +1.134] | +0.750 | 5.0% | 27/30 |
| Motion-to-photon p95 (ms) | 19.182 ± 0.407 | 18.554 ± 0.374 | +0.628 ± 0.439 | [+0.464; +0.791] | +0.561 | 3.2% | 27/30 |
| Perda de pacotes DL (%) | 0.064 ± 0.016 | 0.010 ± 0.009 | +0.054 ± 0.019 | [+0.047; +0.061] | +0.052 | 83.3% | 30/30 |
| Quadros incompletos (%) | 0.53 ± 0.11 | 0.02 ± 0.01 | +0.51 ± 0.11 | [+0.47; +0.55] | +0.47 | 96.4% | 30/30 |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.09 ± 0.00 | -0.01 ± 0.00 | [-0.01; -0.01] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.103 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.496 ± 0.025 | 2.285 ± 0.137 | +0.789 ± 0.140 | [+0.736; +0.841] | 52.8% |
| Atraso de rede p95 (ms) | 1.940 ± 0.036 | 3.504 ± 0.190 | +1.564 ± 0.191 | [+1.493; +1.635] | 80.7% |
| Atraso de rede p99 (ms) | 2.875 ± 0.182 | 5.184 ± 0.250 | +2.308 ± 0.303 | [+2.195; +2.421] | 81.0% |
| Atraso de rede (media) (ms) | 1.489 ± 0.021 | 2.379 ± 0.136 | +0.890 ± 0.138 | [+0.838; +0.942] | 59.8% |
| Jitter de rede (us) | 259.8 ± 63.1 | 468.7 ± 126.3 | +208.9 ± 149.2 | [+153.2; +264.6] | 92.4% |
| Motion-to-photon p50 (ms) | 16.298 ± 0.412 | 16.871 ± 0.452 | +0.574 ± 0.501 | [+0.387; +0.761] | 3.6% |
| Motion-to-photon p95 (ms) | 18.554 ± 0.374 | 19.324 ± 0.364 | +0.770 ± 0.513 | [+0.579; +0.962] | 4.2% |
| Perda de pacotes DL (%) | 0.010 ± 0.009 | 0.061 ± 0.018 | +0.051 ± 0.017 | [+0.045; +0.057] | 482.9% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.54 ± 0.14 | +0.52 ± 0.15 | [+0.47; +0.58] | 1804.5% |
| Vazao DL (Mbps) | 12.09 ± 0.00 | 12.09 ± 0.00 | -0.01 ± 0.00 | [-0.01; -0.01] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2001 | 0 | sim | sim | sim | 711 | 711 |
| 2 | B>A | 2001 | 0 | sim | sim | sim | 697 | 700 |
| 3 | A>B | 2001 | 0 | sim | sim | sim | 710 | 700 |
| 4 | B>A | 2001 | 0 | sim | sim | sim | 706 | 706 |
| 5 | A>B | 2001 | 0 | sim | sim | sim | 709 | 710 |
| 6 | B>A | 2001 | 0 | sim | sim | sim | 698 | 707 |
| 7 | A>B | 2001 | 0 | sim | sim | sim | 700 | 697 |
| 8 | B>A | 2001 | 0 | sim | sim | sim | 709 | 703 |
| 9 | A>B | 2001 | 0 | sim | sim | sim | 702 | 705 |
| 10 | B>A | 2001 | 0 | sim | sim | sim | 701 | 702 |
| 11 | A>B | 2001 | 0 | sim | sim | sim | 710 | 706 |
| 12 | B>A | 2001 | 0 | sim | sim | sim | 704 | 702 |
| 13 | A>B | 2001 | 0 | sim | sim | sim | 711 | 711 |
| 14 | B>A | 2001 | 0 | sim | sim | sim | 704 | 705 |
| 15 | A>B | 2001 | 0 | sim | sim | sim | 709 | 709 |
| 16 | B>A | 2001 | 0 | sim | sim | sim | 710 | 707 |
| 17 | A>B | 2001 | 0 | sim | sim | sim | 707 | 702 |
| 18 | B>A | 2001 | 0 | sim | sim | sim | 713 | 707 |
| 19 | A>B | 2001 | 0 | sim | sim | sim | 678 | 683 |
| 20 | B>A | 2001 | 0 | sim | sim | sim | 701 | 703 |
| 21 | A>B | 2001 | 0 | sim | sim | sim | 701 | 706 |
| 22 | B>A | 2001 | 0 | sim | sim | sim | 706 | 704 |
| 23 | A>B | 2001 | 0 | sim | sim | sim | 721 | 712 |
| 24 | B>A | 2001 | 0 | sim | sim | sim | 708 | 708 |
| 25 | A>B | 2001 | 0 | sim | sim | sim | 707 | 705 |
| 26 | B>A | 2001 | 0 | sim | sim | sim | 702 | 702 |
| 27 | A>B | 2001 | 0 | sim | sim | sim | 695 | 695 |
| 28 | B>A | 2001 | 0 | sim | sim | sim | 701 | 696 |
| 29 | A>B | 2001 | 0 | sim | sim | sim | 708 | 708 |
| 30 | B>A | 2001 | 0 | sim | sim | sim | 699 | 701 |
