# Campanha A x B - perfil `vr-cloud` - backhaul com fundo a 99%

**Carga:** 50 Mbps @ 90 fps (downlink), pose a 250 Hz (uplink), MTU 1200 B.

**Fundo no backhaul:** iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento, a 99% da capacidade medida no inicio de cada rodada (media 890 Mbps). Ligado so' durante a medicao; execucao em que menos de 90% do fundo cruzou o enlace nao vale.

**Carga efetiva no A:** no centralizado o downlink da propria aplicacao (50 Mbps) desce pelo mesmo enlace que o fundo, entao a carga do enlace durante a medicao do a-mec e' ~104.6% da capacidade. **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a fila fica cheia o tempo todo, o atraso trava no teto do buffer e o excesso vira perda. No B o b-mec nao cruza o enlace.

30 rodada(s), ordem alternada (A->B, B->A, ...). Cada cenario sobe uma vez por rodada e passa por todos os niveis de fundo, em ordem rotativa entre as rodadas. **Pares validos: 30 de 30** -- um par so' entra se as duas execucoes passaram nas guardas de saude do caminho MEC. 30 execucao(oes) dispararam so' guardas do caminho remoto: valem para o A x B e ficam fora da comparacao b-remoto x b-mec.

## LBO contra o centralizado (a-mec x b-mec)

Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora do plano de usuario muda. Diferenca = A - B, calculada dentro de cada rodada; **positiva = o LBO e' mais rapido**. Valores: media ± desvio-padrao entre rodadas.

| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | A - B (mediana) | LBO menor | B abaixo |
|---|---|---|---|---|---|---|---|
| Atraso de rede p50 (ms) | 5.713 ± 0.498 | 0.952 ± 0.017 | +4.761 ± 0.497 | [+4.575; +4.947] | +4.624 | 83.2% | 30/30 |
| Atraso de rede p95 (ms) | 6.460 ± 0.624 | 1.464 ± 0.040 | +4.996 ± 0.629 | [+4.761; +5.231] | +4.840 | 77.1% | 30/30 |
| Atraso de rede p99 (ms) | 7.651 ± 1.941 | 2.170 ± 0.125 | +5.481 ± 1.943 | [+4.756; +6.206] | +4.955 | 70.7% | 30/30 |
| Atraso de rede (media) (ms) | 5.689 ± 0.512 | 0.969 ± 0.017 | +4.721 ± 0.513 | [+4.529; +4.912] | +4.515 | 82.8% | 30/30 |
| Jitter de rede (us) | 305.1 ± 64.8 | 239.3 ± 81.3 | +65.8 ± 110.7 | [+24.5; +107.2] | +84.3 | 17.2% | 21/30 |
| Motion-to-photon p50 (ms) | 15.666 ± 0.524 | 10.971 ± 0.045 | +4.696 ± 0.524 | [+4.500; +4.891] | +4.610 | 29.9% | 30/30 |
| Motion-to-photon p95 (ms) | 17.775 ± 0.529 | 12.817 ± 0.063 | +4.959 ± 0.534 | [+4.759; +5.158] | +4.797 | 27.8% | 30/30 |
| Perda de pacotes DL (%) | 1.811 ± 0.153 | 0.008 ± 0.007 | +1.803 ± 0.153 | [+1.746; +1.860] | +1.757 | 99.6% | 30/30 |
| Quadros incompletos (%) | 54.82 ± 2.90 | 0.01 ± 0.01 | +54.81 ± 2.90 | [+53.72; +55.89] | +54.44 | 100.0% | 30/30 |
| Vazao DL (Mbps) | 49.20 ± 0.08 | 50.11 ± 0.01 | -0.91 ± 0.08 | [-0.94; -0.88] | -0.89 | - | - |

Menor diferenca detectavel no atraso de rede p50 com 30 par(es) (alfa 5%, poder 80%): **0.263 ms**. Diferencas menores que isso nao podem ser afirmadas com esta campanha.

## Aplicacao fora no cenario B (b-remoto x b-mec)

Nenhuma execucao do B passou na guarda de perda entre caminhos neste nivel. Sob congestao o b-remoto cruza o enlace e perde, o b-mec nao; com perdas tao diferentes so' os quadros completos viram amostra, e a comparacao entre os dois deixa de valer. O A x B acima nao e' afetado.


## Prova do mecanismo em cada rodada

Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero (breakout na borda).

| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par | A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |
|---|---|---|---|---|---|---|---|---|
| 1 | A>B | 2501 | 0 | sim | sim | sim | 852 | 863 |
| 2 | B>A | 2501 | 0 | sim | sim | sim | 851 | 862 |
| 3 | A>B | 2501 | 0 | sim | sim | sim | 852 | 864 |
| 4 | B>A | 2501 | 0 | sim | sim | sim | 848 | 863 |
| 5 | A>B | 2501 | 0 | sim | sim | sim | 851 | 866 |
| 6 | B>A | 2501 | 0 | sim | sim | sim | 855 | 862 |
| 7 | A>B | 2501 | 0 | sim | sim | sim | 852 | 861 |
| 8 | B>A | 2501 | 0 | sim | sim | sim | 854 | 865 |
| 9 | A>B | 2501 | 0 | sim | sim | sim | 854 | 865 |
| 10 | B>A | 2501 | 0 | sim | sim | sim | 853 | 862 |
| 11 | A>B | 2501 | 0 | sim | sim | sim | 851 | 863 |
| 12 | B>A | 2501 | 0 | sim | sim | sim | 848 | 867 |
| 13 | A>B | 2501 | 0 | sim | sim | sim | 854 | 868 |
| 14 | B>A | 2501 | 0 | sim | sim | sim | 854 | 864 |
| 15 | A>B | 2501 | 0 | sim | sim | sim | 853 | 868 |
| 16 | B>A | 2501 | 0 | sim | sim | sim | 855 | 864 |
| 17 | A>B | 2501 | 0 | sim | sim | sim | 854 | 866 |
| 18 | B>A | 2501 | 0 | sim | sim | sim | 850 | 864 |
| 19 | A>B | 2501 | 0 | sim | sim | sim | 853 | 860 |
| 20 | B>A | 2501 | 0 | sim | sim | sim | 854 | 860 |
| 21 | A>B | 2501 | 0 | sim | sim | sim | 851 | 863 |
| 22 | B>A | 2501 | 0 | sim | sim | sim | 854 | 868 |
| 23 | A>B | 2501 | 0 | sim | sim | sim | 857 | 867 |
| 24 | B>A | 2501 | 0 | sim | sim | sim | 854 | 869 |
| 25 | A>B | 2501 | 0 | sim | sim | sim | 856 | 868 |
| 26 | B>A | 2501 | 0 | sim | sim | sim | 853 | 865 |
| 27 | A>B | 2501 | 0 | sim | sim | sim | 855 | 864 |
| 28 | B>A | 2501 | 0 | sim | sim | sim | 850 | 866 |
| 29 | A>B | 2501 | 0 | sim | sim | sim | 864 | 864 |
| 30 | B>A | 2501 | 0 | sim | sim | sim | 854 | 869 |
