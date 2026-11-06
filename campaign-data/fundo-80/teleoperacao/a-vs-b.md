# Campanha A x B - perfil `teleoperacao` - backhaul com fundo a 80%

**Carga:** 8 Mbps @ 60 fps (downlink), pose a 500 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 80% da capacidade medida no inicio de cada rodada (media 888 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (8 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~80.9% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.169 ± 0.133 | 1.447 ± 0.017 | +0.722 ± 0.133 | [+0.672; +0.772] | +0.696 | 33.1% | 30/30 |
| Atraso de rede p95 (ms) | 2.777 ± 0.181 | 1.851 ± 0.028 | +0.926 ± 0.191 | [+0.855; +0.998] | +0.879 | 33.1% | 30/30 |
| Atraso de rede p99 (ms) | 3.915 ± 0.225 | 2.742 ± 0.166 | +1.173 ± 0.266 | [+1.074; +1.273] | +1.094 | 29.8% | 30/30 |
| Atraso de rede (media) (ms) | 2.169 ± 0.126 | 1.408 ± 0.018 | +0.762 ± 0.131 | [+0.713; +0.810] | +0.731 | 34.9% | 30/30 |
| Jitter de rede (us) | 360.1 ± 120.8 | 273.8 ± 108.7 | +86.3 ± 176.1 | [+20.5; +152.1] | +68.5 | 16.2% | 25/30 |
| Motion-to-photon p50 (ms) | 14.816 ± 0.140 | 14.098 ± 0.062 | +0.718 ± 0.163 | [+0.657; +0.779] | +0.654 | 4.8% | 30/30 |
| Motion-to-photon p95 (ms) | 15.976 ± 0.180 | 15.182 ± 0.046 | +0.794 ± 0.200 | [+0.720; +0.869] | +0.741 | 5.0% | 30/30 |
| Perda de pacotes DL (%) | 0.066 ± 0.021 | 0.009 ± 0.009 | +0.057 ± 0.020 | [+0.050; +0.065] | +0.057 | 86.9% | 30/30 |
| Quadros incompletos (%) | 0.37 ± 0.12 | 0.02 ± 0.01 | +0.35 ± 0.12 | [+0.31; +0.40] | +0.35 | 94.7% | 30/30 |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.06 ± 0.00 | -0.00 ± 0.00 | [-0.01; -0.00] | -0.01 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.071 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.447 ± 0.017 | 2.361 ± 0.100 | +0.914 ± 0.100 | [+0.877; +0.951] | 63.2% |
| Atraso de rede p95 (ms) | 1.851 ± 0.028 | 3.208 ± 0.148 | +1.357 ± 0.156 | [+1.299; +1.415] | 73.4% |
| Atraso de rede p99 (ms) | 2.742 ± 0.166 | 4.725 ± 0.168 | +1.983 ± 0.236 | [+1.895; +2.071] | 72.9% |
| Atraso de rede (media) (ms) | 1.408 ± 0.018 | 2.391 ± 0.104 | +0.983 ± 0.106 | [+0.943; +1.023] | 69.9% |
| Jitter de rede (us) | 273.8 ± 108.7 | 432.9 ± 125.0 | +159.2 ± 142.4 | [+106.0; +212.4] | 69.7% |
| Motion-to-photon p50 (ms) | 14.098 ± 0.062 | 14.994 ± 0.098 | +0.896 ± 0.118 | [+0.852; +0.940] | 6.4% |
| Motion-to-photon p95 (ms) | 15.182 ± 0.046 | 16.312 ± 0.162 | +1.130 ± 0.170 | [+1.067; +1.193] | 7.4% |
| Perda de pacotes DL (%) | 0.009 ± 0.009 | 0.056 ± 0.017 | +0.047 ± 0.021 | [+0.039; +0.055] | 647.9% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 0.34 ± 0.08 | +0.32 ± 0.09 | [+0.29; +0.35] | 1101.5% |
| Vazao DL (Mbps) | 8.06 ± 0.00 | 8.06 ± 0.00 | -0.00 ± 0.00 | [-0.01; -0.00] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 5001 | 0 | sim | sim | sim | 703 | 706 |
| 2 | B>A | 5001 | 0 | sim | sim | sim | 711 | 707 |
| 3 | A>B | 5001 | 0 | sim | sim | sim | 701 | 709 |
| 4 | B>A | 5001 | 0 | sim | sim | sim | 707 | 707 |
| 5 | A>B | 5001 | 0 | sim | sim | sim | 707 | 708 |
| 6 | B>A | 5001 | 0 | sim | sim | sim | 707 | 700 |
| 7 | A>B | 5001 | 0 | sim | sim | sim | 694 | 708 |
| 8 | B>A | 5000 | 0 | sim | sim | sim | 698 | 701 |
| 9 | A>B | 5001 | 0 | sim | sim | sim | 706 | 704 |
| 10 | B>A | 5001 | 0 | sim | sim | sim | 707 | 698 |
| 11 | A>B | 5001 | 0 | sim | sim | sim | 702 | 708 |
| 12 | B>A | 5001 | 0 | sim | sim | sim | 705 | 706 |
| 13 | A>B | 5001 | 0 | sim | sim | sim | 703 | 708 |
| 14 | B>A | 5000 | 0 | sim | sim | sim | 699 | 701 |
| 15 | A>B | 5001 | 0 | sim | sim | sim | 695 | 694 |
| 16 | B>A | 5001 | 0 | sim | sim | sim | 699 | 706 |
| 17 | A>B | 5001 | 0 | sim | sim | sim | 702 | 699 |
| 18 | B>A | 5001 | 0 | sim | sim | sim | 695 | 701 |
| 19 | A>B | 5001 | 0 | sim | sim | sim | 704 | 703 |
| 20 | B>A | 5001 | 0 | sim | sim | sim | 708 | 705 |
| 21 | A>B | 5001 | 0 | sim | sim | sim | 704 | 708 |
| 22 | B>A | 5000 | 0 | sim | sim | sim | 699 | 706 |
| 23 | A>B | 5001 | 0 | sim | sim | sim | 705 | 703 |
| 24 | B>A | 5001 | 0 | sim | sim | sim | 700 | 706 |
| 25 | A>B | 5001 | 0 | sim | sim | sim | 699 | 698 |
| 26 | B>A | 5001 | 0 | sim | sim | sim | 707 | 705 |
| 27 | A>B | 4999 | 0 | sim | sim | sim | 710 | 708 |
| 28 | B>A | 5000 | 0 | sim | sim | sim | 700 | 705 |
| 29 | A>B | 5001 | 0 | sim | sim | sim | 703 | 703 |
| 30 | B>A | 5001 | 0 | sim | sim | sim | 697 | 707 |
