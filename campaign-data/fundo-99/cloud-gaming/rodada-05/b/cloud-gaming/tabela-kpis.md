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
| Atraso de rede (media) | 1.504 ± 0.000 ms | 3.112 ± 0.000 ms | 1.608 ± 0.000 ms a mais fora (MEC 51.7% menor) |
| Atraso de rede p50 | 1.510 ± 0.000 ms | 3.088 ± 0.000 ms | 1.578 ± 0.000 ms a mais fora (MEC 51.1% menor) |
| Atraso de rede p95 | 2.219 ± 0.000 ms | 4.572 ± 0.000 ms | 2.353 ± 0.000 ms a mais fora (MEC 51.5% menor) |
| Atraso de rede p99 | 3.724 ± 0.000 ms | 6.809 ± 0.000 ms | 3.085 ± 0.000 ms a mais fora (MEC 45.3% menor) |
| Motion-to-photon (media) | 18.888 ± 0.000 ms | 17.773 ± 0.000 ms | -1.115 ± 0.000 ms a mais fora (MEC -6.3% menor) |
| Motion-to-photon p50 | 18.845 ± 0.000 ms | 17.564 ± 0.000 ms | -1.281 ± 0.000 ms a mais fora (MEC -7.3% menor) |
| Motion-to-photon p95 | 19.246 ± 0.000 ms | 20.330 ± 0.000 ms | 1.083 ± 0.000 ms a mais fora (MEC 5.3% menor) |
| Jitter de rede | 278.6 ± 0.0 us | 1132.9 ± 0.0 us | 854.3 ± 0.0 us a mais fora (MEC 75.4% menor) |
| Jitter motion-to-photon | 312.1 ± 0.0 us | 1487.1 ± 0.0 us | 1175.0 ± 0.0 us a mais fora (MEC 79.0% menor) |
| Tempo no servidor p50 | 17.366 ± 0.000 ms | 14.451 ± 0.000 ms | - |
| Perda de pacotes DL | 0.004 ± 0.000 % | 0.702 ± 0.000 % | 0.699 ± 0.000 % a mais fora (MEC 99.5% menor) |
| Continuidade do DL | 99.99 ± 0.00 % | 99.99 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 19.778 ± 0.000 % | 19.750 ± 0.000 % a mais fora (MEC 99.9% menor) |
| Vazao DL | 30.53 ± 0.00 Mbps | 30.31 ± 0.00 Mbps | - |

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
