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
| Atraso de rede (media) | 1.406 ± 0.000 ms | 2.193 ± 0.000 ms | 0.787 ± 0.000 ms a mais fora (MEC 35.9% menor) |
| Atraso de rede p50 | 1.417 ± 0.000 ms | 1.935 ± 0.000 ms | 0.518 ± 0.000 ms a mais fora (MEC 26.8% menor) |
| Atraso de rede p95 | 1.926 ± 0.000 ms | 4.433 ± 0.000 ms | 2.507 ± 0.000 ms a mais fora (MEC 56.6% menor) |
| Atraso de rede p99 | 3.125 ± 0.000 ms | 6.352 ± 0.000 ms | 3.227 ± 0.000 ms a mais fora (MEC 50.8% menor) |
| Motion-to-photon (media) | 16.293 ± 0.000 ms | 21.342 ± 0.000 ms | 5.049 ± 0.000 ms a mais fora (MEC 23.7% menor) |
| Motion-to-photon p50 | 16.264 ± 0.000 ms | 21.198 ± 0.000 ms | 4.934 ± 0.000 ms a mais fora (MEC 23.3% menor) |
| Motion-to-photon p95 | 16.617 ± 0.000 ms | 22.509 ± 0.000 ms | 5.892 ± 0.000 ms a mais fora (MEC 26.2% menor) |
| Jitter de rede | 232.4 ± 0.0 us | 582.5 ± 0.0 us | 350.1 ± 0.0 us a mais fora (MEC 60.1% menor) |
| Jitter motion-to-photon | 226.3 ± 0.0 us | 506.1 ± 0.0 us | 279.8 ± 0.0 us a mais fora (MEC 55.3% menor) |
| Tempo no servidor p50 | 14.886 ± 0.000 ms | 19.306 ± 0.000 ms | - |
| Perda de pacotes DL | 0.017 ± 0.000 % | 0.033 ± 0.000 % | 0.016 ± 0.000 % a mais fora (MEC 48.3% menor) |
| Continuidade do DL | 99.95 ± 0.00 % | 99.94 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.139 ± 0.000 % | 0.111 ± 0.000 % a mais fora (MEC 79.9% menor) |
| Vazao DL | 30.51 ± 0.00 Mbps | 30.51 ± 0.00 Mbps | - |

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
