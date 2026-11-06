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
| Atraso de rede (media) | 1.690 ± 0.000 ms | 2.384 ± 0.000 ms | 0.694 ± 0.000 ms a mais fora (MEC 29.1% menor) |
| Atraso de rede p50 | 1.712 ± 0.000 ms | 2.128 ± 0.000 ms | 0.415 ± 0.000 ms a mais fora (MEC 19.5% menor) |
| Atraso de rede p95 | 2.457 ± 0.000 ms | 4.651 ± 0.000 ms | 2.194 ± 0.000 ms a mais fora (MEC 47.2% menor) |
| Atraso de rede p99 | 3.701 ± 0.000 ms | 6.766 ± 0.000 ms | 3.065 ± 0.000 ms a mais fora (MEC 45.3% menor) |
| Motion-to-photon (media) | 18.654 ± 0.000 ms | 20.934 ± 0.000 ms | 2.280 ± 0.000 ms a mais fora (MEC 10.9% menor) |
| Motion-to-photon p50 | 18.570 ± 0.000 ms | 20.781 ± 0.000 ms | 2.210 ± 0.000 ms a mais fora (MEC 10.6% menor) |
| Motion-to-photon p95 | 19.055 ± 0.000 ms | 22.201 ± 0.000 ms | 3.146 ± 0.000 ms a mais fora (MEC 14.2% menor) |
| Jitter de rede | 372.6 ± 0.0 us | 704.2 ± 0.0 us | 331.6 ± 0.0 us a mais fora (MEC 47.1% menor) |
| Jitter motion-to-photon | 280.9 ± 0.0 us | 435.5 ± 0.0 us | 154.6 ± 0.0 us a mais fora (MEC 35.5% menor) |
| Tempo no servidor p50 | 16.881 ± 0.000 ms | 18.727 ± 0.000 ms | - |
| Perda de pacotes DL | 0.004 ± 0.000 % | 0.030 ± 0.000 % | 0.027 ± 0.000 % a mais fora (MEC 87.8% menor) |
| Continuidade do DL | 99.96 ± 0.00 % | 99.97 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.083 ± 0.000 % | 0.055 ± 0.000 % a mais fora (MEC 66.3% menor) |
| Vazao DL | 30.52 ± 0.00 Mbps | 30.52 ± 0.00 Mbps | - |

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
