# Campanha A x B - perfil `cloud-gaming` - backhaul com fundo a 80%

**Carga:** 30 Mbps @ 60 fps (downlink), pose a 120 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 80% da capacidade medida no inicio de cada rodada (media 837 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (30 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~83.6% da capacidade. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 2.732 ± 0.855 | 1.479 ± 0.084 | +1.254 ± 0.861 | [+0.932; +1.575] | +0.993 | 42.1% | 30/30 |
| Atraso de rede p95 (ms) | 4.036 ± 1.022 | 2.063 ± 0.133 | +1.973 ± 1.012 | [+1.595; +2.351] | +1.622 | 46.0% | 30/30 |
| Atraso de rede p99 (ms) | 5.156 ± 0.838 | 3.273 ± 0.327 | +1.883 ± 0.804 | [+1.583; +2.183] | +1.780 | 35.3% | 30/30 |
| Atraso de rede (media) (ms) | 2.808 ± 0.834 | 1.475 ± 0.075 | +1.333 ± 0.837 | [+1.021; +1.646] | +1.081 | 44.0% | 30/30 |
| Jitter de rede (us) | 549.8 ± 217.9 | 278.1 ± 66.6 | +271.7 ± 232.5 | [+184.9; +358.6] | +227.9 | 41.1% | 27/30 |
| Motion-to-photon p50 (ms) | 19.279 ± 2.597 | 17.098 ± 2.303 | +2.181 ± 3.563 | [+0.850; +3.511] | +2.536 | 9.6% | 24/30 |
| Motion-to-photon p95 (ms) | 20.678 ± 2.838 | 18.306 ± 2.487 | +2.372 ± 3.584 | [+1.033; +3.710] | +2.130 | 10.0% | 24/30 |
| Perda de pacotes DL (%) | 0.240 ± 0.349 | 0.010 ± 0.009 | +0.230 ± 0.350 | [+0.099; +0.360] | +0.081 | 88.7% | 30/30 |
| Quadros incompletos (%) | 5.04 ± 9.17 | 0.02 ± 0.01 | +5.02 ± 9.17 | [+1.59; +8.44] | +1.10 | 98.5% | 30/30 |
| Vazao DL (Mbps) | 30.45 ± 0.11 | 30.52 ± 0.01 | -0.07 ± 0.11 | [-0.11; -0.03] | -0.03 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.456 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as 2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B (30 execucao(oes) sem nenhuma guarda, nem as do remoto).

| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |
|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 1.479 ± 0.084 | 2.297 ± 0.413 | +0.818 ± 0.431 | [+0.657; +0.979] | 56.0% |
| Atraso de rede p95 (ms) | 2.063 ± 0.133 | 4.524 ± 0.492 | +2.461 ± 0.511 | [+2.270; +2.652] | 120.2% |
| Atraso de rede p99 (ms) | 3.273 ± 0.327 | 6.717 ± 0.536 | +3.443 ± 0.606 | [+3.217; +3.670] | 107.0% |
| Atraso de rede (media) (ms) | 1.475 ± 0.075 | 2.516 ± 0.374 | +1.042 ± 0.391 | [+0.896; +1.188] | 71.2% |
| Jitter de rede (us) | 278.1 ± 66.6 | 876.0 ± 320.5 | +598.0 ± 337.6 | [+471.9; +724.0] | 236.7% |
| Motion-to-photon p50 (ms) | 17.098 ± 2.303 | 19.348 ± 2.364 | +2.250 ± 2.596 | [+1.280; +3.219] | 14.3% |
| Motion-to-photon p95 (ms) | 18.306 ± 2.487 | 21.783 ± 1.531 | +3.477 ± 2.796 | [+2.433; +4.521] | 20.9% |
| Perda de pacotes DL (%) | 0.010 ± 0.009 | 0.215 ± 0.205 | +0.204 ± 0.202 | [+0.129; +0.280] | 3919.1% |
| Quadros incompletos (%) | 0.02 ± 0.01 | 4.47 ± 4.90 | +4.45 ± 4.89 | [+2.63; +6.28] | 20067.7% |
| Vazao DL (Mbps) | 30.52 ± 0.01 | 30.46 ± 0.06 | -0.06 ± 0.06 | [-0.09; -0.04] | - |

## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 1201 | 0 | sim | sim | sim | 479 | 479 |
| 2 | B>A | 1201 | 0 | sim | sim | sim | 617 | 617 |
| 3 | A>B | 1201 | 0 | sim | sim | sim | 603 | 604 |
| 4 | B>A | 1201 | 0 | sim | sim | sim | 694 | 703 |
| 5 | A>B | 1201 | 0 | sim | sim | sim | 622 | 624 |
| 6 | B>A | 1201 | 0 | sim | sim | sim | 706 | 698 |
| 7 | A>B | 1201 | 0 | sim | sim | sim | 712 | 705 |
| 8 | B>A | 1201 | 0 | sim | sim | sim | 692 | 687 |
| 9 | A>B | 1201 | 0 | sim | sim | sim | 694 | 702 |
| 10 | B>A | 1201 | 0 | sim | sim | sim | 689 | 692 |
| 11 | A>B | 1201 | 0 | sim | sim | sim | 649 | 651 |
| 12 | B>A | 1201 | 0 | sim | sim | sim | 676 | 691 |
| 13 | A>B | 1201 | 0 | sim | sim | sim | 395 | 397 |
| 14 | B>A | 1201 | 0 | sim | sim | sim | 618 | 618 |
| 15 | A>B | 1201 | 0 | sim | sim | sim | 703 | 697 |
| 16 | B>A | 1201 | 0 | sim | sim | sim | 699 | 697 |
| 17 | A>B | 1201 | 0 | sim | sim | sim | 665 | 659 |
| 18 | B>A | 1201 | 0 | sim | sim | sim | 681 | 687 |
| 19 | A>B | 1201 | 0 | sim | sim | sim | 704 | 705 |
| 20 | B>A | 1201 | 0 | sim | sim | sim | 625 | 625 |
| 21 | A>B | 1201 | 0 | sim | sim | sim | 700 | 713 |
| 22 | B>A | 1201 | 0 | sim | sim | sim | 680 | 678 |
| 23 | A>B | 1201 | 0 | sim | sim | sim | 710 | 710 |
| 24 | B>A | 1201 | 0 | sim | sim | sim | 705 | 707 |
| 25 | A>B | 1201 | 0 | sim | sim | sim | 705 | 704 |
| 26 | B>A | 1201 | 0 | sim | sim | sim | 710 | 712 |
| 27 | A>B | 1201 | 0 | sim | sim | sim | 708 | 707 |
| 28 | B>A | 1201 | 0 | sim | sim | sim | 636 | 635 |
| 29 | A>B | 1201 | 0 | sim | sim | sim | 706 | 707 |
| 30 | B>A | 1201 | 0 | sim | sim | sim | 704 | 706 |
