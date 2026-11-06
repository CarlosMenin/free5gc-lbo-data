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
| Atraso de rede (media) | 1.499 ± 0.000 ms | 2.655 ± 0.000 ms | 1.156 ± 0.000 ms a mais fora (MEC 43.5% menor) |
| Atraso de rede p50 | 1.500 ± 0.000 ms | 2.623 ± 0.000 ms | 1.124 ± 0.000 ms a mais fora (MEC 42.8% menor) |
| Atraso de rede p95 | 1.937 ± 0.000 ms | 3.916 ± 0.000 ms | 1.979 ± 0.000 ms a mais fora (MEC 50.5% menor) |
| Atraso de rede p99 | 2.814 ± 0.000 ms | 5.544 ± 0.000 ms | 2.731 ± 0.000 ms a mais fora (MEC 49.3% menor) |
| Motion-to-photon (media) | 16.024 ± 0.000 ms | 17.798 ± 0.000 ms | 1.775 ± 0.000 ms a mais fora (MEC 10.0% menor) |
| Motion-to-photon p50 | 15.762 ± 0.000 ms | 18.025 ± 0.000 ms | 2.262 ± 0.000 ms a mais fora (MEC 12.6% menor) |
| Motion-to-photon p95 | 18.112 ± 0.000 ms | 19.656 ± 0.000 ms | 1.544 ± 0.000 ms a mais fora (MEC 7.9% menor) |
| Jitter de rede | 239.8 ± 0.0 us | 799.8 ± 0.0 us | 560.0 ± 0.0 us a mais fora (MEC 70.0% menor) |
| Jitter motion-to-photon | 2148.1 ± 0.0 us | 2219.7 ± 0.0 us | 71.6 ± 0.0 us a mais fora (MEC 3.2% menor) |
| Tempo no servidor p50 | 14.357 ± 0.000 ms | 15.240 ± 0.000 ms | - |
| Perda de pacotes DL | 0.026 ± 0.000 % | 0.124 ± 0.000 % | 0.098 ± 0.000 % a mais fora (MEC 78.8% menor) |
| Continuidade do DL | 99.99 ± 0.00 % | 99.97 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 1.111 ± 0.000 % | 1.083 ± 0.000 % a mais fora (MEC 97.5% menor) |
| Vazao DL | 12.10 ± 0.00 Mbps | 12.08 ± 0.00 Mbps | - |

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
