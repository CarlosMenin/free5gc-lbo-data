# Cenario B - dUPF com ULCL / Local Breakout - perfil `cloud-gaming`

**Carga:** 30 Mbps @ 60 fps por sessao (downlink), pose/controle a 120 Hz (uplink), MTU 1200 B.

> Jogo renderizado na borda, 1080p60 em HEVC de qualidade alta (~30 Mbps). Controle a 120 Hz (gamepad/mouse). Malha fechada, mas tolerante a ~50 ms de m2p.

Campanha de **1 execucao(oes)** independentes. Cada execucao sobe o cenario do zero, mede e derruba os deployments antes da seguinte.

- Duracao por caminho: 60 s (descartados os 5 s iniciais)
- Carga: aplicacao VR (downlink de frames + uplink de pose), identica nos dois caminhos
- Placement: ueransim=brix-porvir-02, i-upf=brix-porvir-05, mec-app=brix-porvir-05, psa-upf=petshopboys, remote-app=metallica, smf=petshopboys, amf=petshopboys

Valores: media +- desvio-padrao entre as execucoes.

| KPI | MEC / LBO | Caminho remoto | Aplicacao fora (2 UPFs) |
|---|---|---|---|
| Atraso de rede (media) | 1.657 ± 0.000 ms | 2.120 ± 0.000 ms | 0.463 ± 0.000 ms a mais fora (MEC 21.8% menor) |
| Atraso de rede p50 | 1.678 ± 0.000 ms | 1.861 ± 0.000 ms | 0.182 ± 0.000 ms a mais fora (MEC 9.8% menor) |
| Atraso de rede p95 | 2.257 ± 0.000 ms | 4.083 ± 0.000 ms | 1.826 ± 0.000 ms a mais fora (MEC 44.7% menor) |
| Atraso de rede p99 | 3.630 ± 0.000 ms | 6.100 ± 0.000 ms | 2.470 ± 0.000 ms a mais fora (MEC 40.5% menor) |
| Motion-to-photon (media) | 19.775 ± 0.000 ms | 18.987 ± 0.000 ms | -0.788 ± 0.000 ms a mais fora (MEC -4.2% menor) |
| Motion-to-photon p50 | 19.754 ± 0.000 ms | 18.765 ± 0.000 ms | -0.989 ± 0.000 ms a mais fora (MEC -5.3% menor) |
| Motion-to-photon p95 | 20.126 ± 0.000 ms | 20.459 ± 0.000 ms | 0.333 ± 0.000 ms a mais fora (MEC 1.6% menor) |
| Jitter de rede | 233.9 ± 0.0 us | 629.3 ± 0.0 us | 395.4 ± 0.0 us a mais fora (MEC 62.8% menor) |
| Jitter motion-to-photon | 182.9 ± 0.0 us | 489.8 ± 0.0 us | 306.9 ± 0.0 us a mais fora (MEC 62.7% menor) |
| Tempo no servidor p50 | 18.088 ± 0.000 ms | 16.964 ± 0.000 ms | - |
| Perda de pacotes DL | 0.006 ± 0.000 % | 0.036 ± 0.000 % | 0.030 ± 0.000 % a mais fora (MEC 82.6% menor) |
| Continuidade do DL | 99.99 ± 0.00 % | 99.94 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.556 ± 0.000 % | 0.528 ± 0.000 % a mais fora (MEC 95.0% menor) |
| Vazao DL | 30.53 ± 0.00 Mbps | 30.51 ± 0.00 Mbps | - |

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
