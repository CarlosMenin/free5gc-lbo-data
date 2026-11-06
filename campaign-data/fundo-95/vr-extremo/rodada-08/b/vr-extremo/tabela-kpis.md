# Cenario B - dUPF com ULCL / Local Breakout - perfil `vr-extremo`

**Carga:** 100 Mbps @ 90 fps por sessao (downlink), pose/controle a 250 Hz (uplink), MTU 1200 B.

> VR de alta fidelidade (~4K por olho). Serve para achar o TETO do testbed: se a carga nao trafega, o relatorio diz onde ela parou, e esse tambem e' um resultado.

Campanha de **1 execucao(oes)** independentes. Cada execucao sobe o cenario do zero, mede e derruba os deployments antes da seguinte.

- Duracao por caminho: 60 s (descartados os 5 s iniciais)
- Carga: aplicacao VR (downlink de frames + uplink de pose), identica nos dois caminhos
- Placement: ueransim=brix-porvir-02, i-upf=brix-porvir-05, mec-app=brix-porvir-05, psa-upf=petshopboys, remote-app=metallica, smf=petshopboys, amf=petshopboys

Valores: media +- desvio-padrao entre as execucoes.

| KPI | MEC / LBO | Caminho remoto | Aplicacao fora (2 UPFs) |
|---|---|---|---|
| Atraso de rede (media) | 0.662 ± 0.000 ms | 8.885 ± 0.000 ms | 8.223 ± 0.000 ms a mais fora (MEC 92.5% menor) |
| Atraso de rede p50 | 0.575 ± 0.000 ms | 8.454 ± 0.000 ms | 7.879 ± 0.000 ms a mais fora (MEC 93.2% menor) |
| Atraso de rede p95 | 1.005 ± 0.000 ms | 12.514 ± 0.000 ms | 11.509 ± 0.000 ms a mais fora (MEC 92.0% menor) |
| Atraso de rede p99 | 2.471 ± 0.000 ms | 16.538 ± 0.000 ms | 14.067 ± 0.000 ms a mais fora (MEC 85.1% menor) |
| Motion-to-photon (media) | 11.001 ± 0.000 ms | 19.399 ± 0.000 ms | 8.398 ± 0.000 ms a mais fora (MEC 43.3% menor) |
| Motion-to-photon p50 | 11.113 ± 0.000 ms | 19.055 ± 0.000 ms | 7.942 ± 0.000 ms a mais fora (MEC 41.7% menor) |
| Motion-to-photon p95 | 12.910 ± 0.000 ms | 24.060 ± 0.000 ms | 11.150 ± 0.000 ms a mais fora (MEC 46.3% menor) |
| Jitter de rede | 196.9 ± 0.0 us | 1470.5 ± 0.0 us | 1273.6 ± 0.0 us a mais fora (MEC 86.6% menor) |
| Jitter motion-to-photon | 1072.9 ± 0.0 us | 2403.8 ± 0.0 us | 1330.9 ± 0.0 us a mais fora (MEC 55.4% menor) |
| Tempo no servidor p50 | 10.485 ± 0.000 ms | 10.339 ± 0.000 ms | - |
| Perda de pacotes DL | 0.880 ± 0.000 % | 1.659 ± 0.000 % | 0.779 ± 0.000 % a mais fora (MEC 47.0% menor) |
| Continuidade do DL | 99.99 ± 0.00 % | 99.98 ± 0.00 % | - |
| Frames incompletos | 29.722 ± 0.000 % | 70.481 ± 0.000 % | 40.759 ± 0.000 % a mais fora (MEC 57.8% menor) |
| Vazao DL | 99.26 ± 0.00 Mbps | 98.60 ± 0.00 Mbps | - |

A coluna *Aplicacao fora* compara dois destinos DENTRO do cenario B (b-remoto x b-mec). O ganho do LBO sobre o centralizado e' a-mec x b-mec e sai de `campanha-a-vs-b.py`.

## Prova do Local Breakout

Pacotes recebidos na interface GTP de cada UPF durante o trafego de cada caminho. O que prova o breakout e' o CONTRASTE na coluna do PSA-UPF, nao a latencia menor.

| Execucao | I-UPF (MEC) | PSA-UPF (MEC) | I-UPF (remoto) | PSA-UPF (remoto) |
|---|---|---|---|---|
| 1 | 2501 | 0 | 0 | 2501 |

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
