# Cenario B - dUPF com ULCL / Local Breakout - perfil `ar-industrial`

**Carga:** 12 Mbps @ 60 fps por sessao (downlink), pose/controle a 200 Hz (uplink), MTU 1200 B.

> AR assistida: video 1080p com overlay de anotacao (~12 Mbps). Downlink leve, mas a pose precisa ser rapida para o overlay nao descolar do objeto real.

Campanha de **1 execucao(oes)** independentes. Cada execucao sobe o cenario do zero, mede e derruba os deployments antes da seguinte.

- Duracao por caminho: 60 s (descartados os 5 s iniciais)
- Carga: aplicacao VR (downlink de frames + uplink de pose), identica nos dois caminhos
- Placement: ueransim=brix-porvir-02, i-upf=brix-porvir-05, mec-app=brix-porvir-05, psa-upf=petshopboys, remote-app=metallica, smf=petshopboys, amf=petshopboys

Valores: media +- desvio-padrao entre as execucoes.

| KPI | MEC / LBO | Caminho remoto | Aplicacao fora (2 UPFs) |
|---|---|---|---|
| Atraso de rede (media) | 1.518 ± 0.000 ms | 2.089 ± 0.000 ms | 0.571 ± 0.000 ms a mais fora (MEC 27.3% menor) |
| Atraso de rede p50 | 1.556 ± 0.000 ms | 2.015 ± 0.000 ms | 0.460 ± 0.000 ms a mais fora (MEC 22.8% menor) |
| Atraso de rede p95 | 1.924 ± 0.000 ms | 3.128 ± 0.000 ms | 1.204 ± 0.000 ms a mais fora (MEC 38.5% menor) |
| Atraso de rede p99 | 2.732 ± 0.000 ms | 4.542 ± 0.000 ms | 1.810 ± 0.000 ms a mais fora (MEC 39.9% menor) |
| Motion-to-photon (media) | 15.813 ± 0.000 ms | 16.469 ± 0.000 ms | 0.656 ± 0.000 ms a mais fora (MEC 4.0% menor) |
| Motion-to-photon p50 | 15.768 ± 0.000 ms | 16.276 ± 0.000 ms | 0.508 ± 0.000 ms a mais fora (MEC 3.1% menor) |
| Motion-to-photon p95 | 17.633 ± 0.000 ms | 19.294 ± 0.000 ms | 1.661 ± 0.000 ms a mais fora (MEC 8.6% menor) |
| Jitter de rede | 318.5 ± 0.0 us | 596.2 ± 0.0 us | 277.7 ± 0.0 us a mais fora (MEC 46.6% menor) |
| Jitter motion-to-photon | 2157.0 ± 0.0 us | 2531.5 ± 0.0 us | 374.5 ± 0.0 us a mais fora (MEC 14.8% menor) |
| Tempo no servidor p50 | 14.257 ± 0.000 ms | 14.213 ± 0.000 ms | - |
| Perda de pacotes DL | 0.018 ± 0.000 % | 0.001 ± 0.000 % | -0.017 ± 0.000 % a mais fora (MEC -1323.1% menor) |
| Continuidade do DL | 99.98 ± 0.00 % | 99.96 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.028 ± 0.000 % | 0.000 ± 0.000 % a mais fora (MEC 0.0% menor) |
| Vazao DL | 12.09 ± 0.00 Mbps | 12.09 ± 0.00 Mbps | - |

A coluna *Aplicacao fora* compara dois destinos DENTRO do cenario B (b-remoto x b-mec). O ganho do LBO sobre o centralizado e' a-mec x b-mec e sai de `campanha-a-vs-b.py`.

## Prova do Local Breakout

Pacotes recebidos na interface GTP de cada UPF durante o trafego de cada caminho. O que prova o breakout e' o CONTRASTE na coluna do PSA-UPF, nao a latencia menor.

| Execucao | I-UPF (MEC) | PSA-UPF (MEC) | I-UPF (remoto) | PSA-UPF (remoto) |
|---|---|---|---|---|
| 1 | 2001 | 0 | 0 | 2001 |

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
