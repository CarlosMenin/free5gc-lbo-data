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
| Atraso de rede (media) | 1.444 ± 0.000 ms | 3.616 ± 0.000 ms | 2.171 ± 0.000 ms a mais fora (MEC 60.1% menor) |
| Atraso de rede p50 | 1.453 ± 0.000 ms | 3.612 ± 0.000 ms | 2.158 ± 0.000 ms a mais fora (MEC 59.8% menor) |
| Atraso de rede p95 | 1.997 ± 0.000 ms | 5.502 ± 0.000 ms | 3.505 ± 0.000 ms a mais fora (MEC 63.7% menor) |
| Atraso de rede p99 | 3.047 ± 0.000 ms | 7.447 ± 0.000 ms | 4.400 ± 0.000 ms a mais fora (MEC 59.1% menor) |
| Motion-to-photon (media) | 16.355 ± 0.000 ms | 19.398 ± 0.000 ms | 3.042 ± 0.000 ms a mais fora (MEC 15.7% menor) |
| Motion-to-photon p50 | 16.321 ± 0.000 ms | 19.430 ± 0.000 ms | 3.109 ± 0.000 ms a mais fora (MEC 16.0% menor) |
| Motion-to-photon p95 | 16.739 ± 0.000 ms | 20.905 ± 0.000 ms | 4.166 ± 0.000 ms a mais fora (MEC 19.9% menor) |
| Jitter de rede | 156.0 ± 0.0 us | 1037.8 ± 0.0 us | 881.8 ± 0.0 us a mais fora (MEC 85.0% menor) |
| Jitter motion-to-photon | 128.4 ± 0.0 us | 1261.3 ± 0.0 us | 1132.9 ± 0.0 us a mais fora (MEC 89.8% menor) |
| Tempo no servidor p50 | 14.899 ± 0.000 ms | 15.817 ± 0.000 ms | - |
| Perda de pacotes DL | 0.000 ± 0.000 % | 0.954 ± 0.000 % | 0.954 ± 0.000 % a mais fora (MEC 100.0% menor) |
| Continuidade do DL | 99.99 ± 0.00 % | 99.96 ± 0.00 % | - |
| Frames incompletos | 0.000 ± 0.000 % | 23.167 ± 0.000 % | 23.167 ± 0.000 % a mais fora (MEC 100.0% menor) |
| Vazao DL | 25.34 ± 0.00 Mbps | 25.08 ± 0.00 Mbps | - |

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
