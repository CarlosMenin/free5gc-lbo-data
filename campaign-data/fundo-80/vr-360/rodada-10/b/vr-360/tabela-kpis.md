# Cenario B - dUPF com ULCL / Local Breakout - perfil `vr-360`

**Carga:** 25 Mbps @ 60 fps por sessao (downlink), pose/controle a 120 Hz (uplink), MTU 1200 B.

> Video 360 estereoscopico 4K a 60 fps (~25 Mbps em HEVC). Pose so' para orientar a projecao, entao 120 Hz basta. E' o piso do que se chama de VR: sem render remoto.

Campanha de **1 execucao(oes)** independentes. Cada execucao sobe o cenario do zero, mede e derruba os deployments antes da seguinte.

- Duracao por caminho: 60 s (descartados os 5 s iniciais)
- Carga: aplicacao VR (downlink de frames + uplink de pose), identica nos dois caminhos
- Placement: ueransim=brix-porvir-02, i-upf=brix-porvir-05, mec-app=brix-porvir-05, psa-upf=petshopboys, remote-app=metallica, smf=petshopboys, amf=petshopboys

Valores: media +- desvio-padrao entre as execucoes.

| KPI | MEC / LBO | Caminho remoto | Aplicacao fora (2 UPFs) |
|---|---|---|---|
| Atraso de rede (media) | 1.639 ± 0.000 ms | 2.281 ± 0.000 ms | 0.642 ± 0.000 ms a mais fora (MEC 28.1% menor) |
| Atraso de rede p50 | 1.648 ± 0.000 ms | 2.140 ± 0.000 ms | 0.492 ± 0.000 ms a mais fora (MEC 23.0% menor) |
| Atraso de rede p95 | 2.310 ± 0.000 ms | 3.855 ± 0.000 ms | 1.545 ± 0.000 ms a mais fora (MEC 40.1% menor) |
| Atraso de rede p99 | 3.312 ± 0.000 ms | 6.194 ± 0.000 ms | 2.883 ± 0.000 ms a mais fora (MEC 46.5% menor) |
| Motion-to-photon (media) | 17.289 ± 0.000 ms | 15.863 ± 0.000 ms | -1.426 ± 0.000 ms a mais fora (MEC -9.0% menor) |
| Motion-to-photon p50 | 17.277 ± 0.000 ms | 15.353 ± 0.000 ms | -1.925 ± 0.000 ms a mais fora (MEC -12.5% menor) |
| Motion-to-photon p95 | 17.712 ± 0.000 ms | 20.254 ± 0.000 ms | 2.542 ± 0.000 ms a mais fora (MEC 12.6% menor) |
| Jitter de rede | 328.7 ± 0.0 us | 877.4 ± 0.0 us | 548.7 ± 0.0 us a mais fora (MEC 62.5% menor) |
| Jitter motion-to-photon | 340.0 ± 0.0 us | 1617.0 ± 0.0 us | 1277.0 ± 0.0 us a mais fora (MEC 79.0% menor) |
| Tempo no servidor p50 | 15.641 ± 0.000 ms | 13.270 ± 0.000 ms | - |
| Perda de pacotes DL | 0.020 ± 0.000 % | 0.092 ± 0.000 % | 0.073 ± 0.000 % a mais fora (MEC 78.7% menor) |
| Continuidade do DL | 99.98 ± 0.00 % | 99.95 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.944 ± 0.000 % | 0.916 ± 0.000 % a mais fora (MEC 97.0% menor) |
| Vazao DL | 25.34 ± 0.00 Mbps | 25.31 ± 0.00 Mbps | - |

A coluna *Aplicacao fora* compara dois destinos DENTRO do cenario B (b-remoto x b-mec). O ganho do LBO sobre o centralizado e' a-mec x b-mec e sai de `campanha-a-vs-b.py`.

## Prova do Local Breakout

Pacotes recebidos na interface GTP de cada UPF durante o trafego de cada caminho. O que prova o breakout e' o CONTRASTE na coluna do PSA-UPF, nao a latencia menor.

| Execucao | I-UPF (MEC) | PSA-UPF (MEC) | I-UPF (remoto) | PSA-UPF (remoto) |
|---|---|---|---|---|
| 1 | 1201 | 0 | 0 | 1201 |

PSA-UPF em zero na coluna MEC = o trafego de borda nunca subiu para o nucleo.

## Como ler os dois blocos de latencia

O **atraso de rede** e' ida do uplink mais volta do downlink: a parcela que o posicionamento do UPF de fato ataca. O **motion-to-photon** inclui, alem disso, o **tempo no servidor** (a espera pelo proximo instante de render mais a janela em que o gerador espalha os pacotes do frame). Vale a identidade `m2p = atraso de rede + tempo no servidor`, e a tabela traz os tres justamente para que ela possa ser conferida. Reportar so' um dos dois engana: o m2p sozinho dilui o efeito do breakout, o atraso de rede sozinho esconde o que o usuario sente.

O tempo no servidor e' igual nos dois caminhos por construcao (mesmo perfil, mesmo codigo, mesma janela de pacing): ele desloca o m2p dos dois lados pelo mesmo tanto e nao cria nem esconde diferenca entre eles.

## O que valida cada medida

Uma corrida so' entra na tabela se ela mediu a REDE, e nao o proprio medidor. As colunas de `resumo-por-execucao.csv` que sustentam isso:

- `srv_frames_late` / `srv_send_dropped`: o gerador nao sustentou a cadencia, ou nao conseguiu entregar os pacotes ao kernel. Perda que nasceu no servidor, nao no caminho.
- `cli_sock_overflow` (SO_RXQ_OVFL): pacotes que CHEGARAM e o kernel do cliente descartou por fila cheia. E' perda do cliente; nao pode ser lida como perda do UPF.
- `cli_udp_rcvbuf_errors`: estouro de buffer UDP no namespace do tester, que o vr-client divide com o nr-gnb e o nr-ue -- aponta perda dentro do proprio UERANSIM.
- `dl_loss_srv_pct`: perda com o denominador vindo do contador do servidor (pacotes de fato entregues ao kernel), e nao do intervalo de sequencia que o cliente observou, que nao enxerga frame perdido inteiro nas bordas.
- `ts_kernel`: 1 quando os carimbos de tempo vieram do kernel (SO_TIMESTAMPNS). Com 0, a latencia reportada carrega junto o tempo que os processos passaram fora da CPU.
- `frames_incompletos_pct`: so' frames COMPLETOS viram amostra de latencia. Se os dois caminhos perdem quantidades muito diferentes, os percentis nao sao comparaveis -- o que perde mais some com as amostras dos instantes ruins e parece melhor do que e'. Execucoes assim saem da tabela.
