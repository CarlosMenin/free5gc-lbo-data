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
| Atraso de rede (media) | 1.510 ± 0.000 ms | 4.156 ± 0.000 ms | 2.646 ± 0.000 ms a mais fora (MEC 63.7% menor) |
| Atraso de rede p50 | 1.466 ± 0.000 ms | 4.013 ± 0.000 ms | 2.548 ± 0.000 ms a mais fora (MEC 63.5% menor) |
| Atraso de rede p95 | 2.345 ± 0.000 ms | 6.106 ± 0.000 ms | 3.761 ± 0.000 ms a mais fora (MEC 61.6% menor) |
| Atraso de rede p99 | 3.804 ± 0.000 ms | 8.885 ± 0.000 ms | 5.081 ± 0.000 ms a mais fora (MEC 57.2% menor) |
| Motion-to-photon (media) | 19.400 ± 0.000 ms | 22.073 ± 0.000 ms | 2.673 ± 0.000 ms a mais fora (MEC 12.1% menor) |
| Motion-to-photon p50 | 19.348 ± 0.000 ms | 24.323 ± 0.000 ms | 4.975 ± 0.000 ms a mais fora (MEC 20.5% menor) |
| Motion-to-photon p95 | 19.814 ± 0.000 ms | 25.268 ± 0.000 ms | 5.453 ± 0.000 ms a mais fora (MEC 21.6% menor) |
| Jitter de rede | 242.2 ± 0.0 us | 856.0 ± 0.0 us | 613.8 ± 0.0 us a mais fora (MEC 71.7% menor) |
| Jitter motion-to-photon | 116.8 ± 0.0 us | 3803.1 ± 0.0 us | 3686.3 ± 0.0 us a mais fora (MEC 96.9% menor) |
| Tempo no servidor p50 | 17.913 ± 0.000 ms | 20.007 ± 0.000 ms | - |
| Perda de pacotes DL | 0.025 ± 0.000 % | 0.880 ± 0.000 % | 0.856 ± 0.000 % a mais fora (MEC 97.2% menor) |
| Continuidade do DL | 99.97 ± 0.00 % | 99.97 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 22.994 ± 0.000 % | 22.966 ± 0.000 % a mais fora (MEC 99.9% menor) |
| Vazao DL | 25.34 ± 0.00 Mbps | 25.12 ± 0.00 Mbps | - |

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
