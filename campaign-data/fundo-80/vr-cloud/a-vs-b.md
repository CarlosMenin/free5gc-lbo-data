# Campanha A x B - perfil `vr-cloud` - backhaul com fundo a 80%

**Carga:** 50 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 80% da capacidade medida no inicio de cada rodada (media 890 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (50 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~85.6% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.693 ± 0.174 | 0.948 ± 0.014 | +0.745 ± 0.176 | [+0.679; +0.811] | +0.729 | 43.4% | 30/30 |
| Atraso de rede p95 (ms) | 2.383 ± 0.223 | 1.462 ± 0.036 | +0.921 ± 0.217 | [+0.839; +1.002] | +0.860 | 38.2% | 30/30 |
| Atraso de rede p99 (ms) | 4.134 ± 2.969 | 2.184 ± 0.085 | +1.950 ± 2.989 | [+0.834; +3.066] | +1.274 | 40.0% | 30/30 |
| Atraso de rede (media) (ms) | 1.752 ± 0.180 | 0.966 ± 0.013 | +0.786 ± 0.180 | [+0.719; +0.853] | +0.744 | 44.3% | 30/30 |
| Jitter de rede (us) | 280.8 ± 95.4 | 202.7 ± 47.3 | +78.1 ± 112.2 | [+36.2; +120.0] | +66.9 | 18.6% | 22/30 |
| Motion-to-photon p50 (ms) | 11.638 ± 0.163 | 10.977 ± 0.037 | +0.661 ± 0.178 | [+0.595; +0.728] | +0.610 | 5.7% | 30/30 |
| Motion-to-photon p95 (ms) | 13.528 ± 0.159 | 12.831 ± 0.054 | +0.697 ± 0.182 | [+0.629; +0.765] | +0.677 | 5.1% | 30/30 |
| Perda de pacotes DL (%) | 0.073 ± 0.021 | 0.010 ± 0.006 | +0.063 ± 0.019 | [+0.056; +0.070] | +0.062 | 86.6% | 30/30 |
| Quadros incompletos (%) | 0.58 ± 0.15 | 0.02 ± 0.00 | +0.56 ± 0.15 | [+0.50; +0.61] | +0.54 | 96.9% | 30/30 |
| Vazao DL (Mbps) | 50.07 ± 0.01 | 50.10 ± 0.01 | -0.03 ± 0.01 | [-0.04; -0.03] | -0.03 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.093 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 0.948 ± 0.014 | 1.626 ± 0.182 | +0.678 ± 0.181 | [+0.611; +0.746] | 71.6% |
| Atraso de rede p95 (ms) | 1.462 ± 0.036 | 3.672 ± 0.194 | +2.211 ± 0.199 | [+2.136; +2.285] | 151.4% |
| Atraso de rede p99 (ms) | 2.184 ± 0.085 | 5.526 ± 0.287 | +3.342 ± 0.301 | [+3.230; +3.455] | 153.4% |
| Atraso de rede (media) (ms) | 0.966 ± 0.013 | 1.860 ± 0.165 | +0.895 ± 0.164 | [+0.833; +0.956] | 92.7% |
| Jitter de rede (us) | 202.7 ± 47.3 | 548.9 ± 186.5 | +346.2 ± 198.8 | [+272.0; +420.4] | 187.1% |
| Motion-to-photon p50 (ms) | 10.977 ± 0.037 | 11.789 ± 0.166 | +0.812 ± 0.172 | [+0.748; +0.877] | 7.4% |
| Motion-to-photon p95 (ms) | 12.831 ± 0.054 | 14.462 ± 0.258 | +1.631 ± 0.264 | [+1.532; +1.729] | 12.7% |
| Perda de pacotes DL (%) | 0.010 ± 0.006 | 0.083 ± 0.041 | +0.074 ± 0.041 | [+0.059; +0.089] | 1055.0% |
| Quadros incompletos (%) | 0.02 ± 0.00 | 0.71 ± 0.40 | +0.70 ± 0.39 | [+0.55; +0.84] | 3778.6% |
| Vazao DL (Mbps) | 50.10 ± 0.01 | 50.06 ± 0.02 | -0.04 ± 0.02 | [-0.05; -0.03] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 705 | 708 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 704 | 706 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 706 | 708 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 696 | 705 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 705 | 707 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 701 | 706 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 697 | 708 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 695 | 705 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 707 | 700 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 709 | 707 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 700 | 704 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 695 | 704 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 699 | 704 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 704 | 703 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 699 | 712 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 709 | 705 |
| 17 | A>B | 2501 | 0 | sim | sim | sim | 703 | 708 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 699 | 702 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 705 | 698 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 702 | 708 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 709 | 702 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 707 | 709 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 705 | 705 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 706 | 711 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 696 | 702 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 699 | 707 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 704 | 707 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 708 | 700 |
| 29 | A>B | 2501 | 0 | sim | sim | sim | 705 | 705 |
| 30 | B>A | 2501 | 0 | sim | sim | sim | 702 | 710 |
