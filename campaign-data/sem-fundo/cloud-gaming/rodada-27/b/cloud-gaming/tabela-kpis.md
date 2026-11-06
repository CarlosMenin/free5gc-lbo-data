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
| Atraso de rede (media) | 1.511 ± 0.000 ms | 2.122 ± 0.000 ms | 0.611 ± 0.000 ms a mais fora (MEC 28.8% menor) |
| Atraso de rede p50 | 1.480 ± 0.000 ms | 1.873 ± 0.000 ms | 0.392 ± 0.000 ms a mais fora (MEC 21.0% menor) |
| Atraso de rede p95 | 2.284 ± 0.000 ms | 4.241 ± 0.000 ms | 1.957 ± 0.000 ms a mais fora (MEC 46.2% menor) |
| Atraso de rede p99 | 3.745 ± 0.000 ms | 6.606 ± 0.000 ms | 2.861 ± 0.000 ms a mais fora (MEC 43.3% menor) |
| Motion-to-photon (media) | 19.965 ± 0.000 ms | 21.485 ± 0.000 ms | 1.520 ± 0.000 ms a mais fora (MEC 7.1% menor) |
| Motion-to-photon p50 | 19.679 ± 0.000 ms | 21.328 ± 0.000 ms | 1.649 ± 0.000 ms a mais fora (MEC 7.7% menor) |
| Motion-to-photon p95 | 20.779 ± 0.000 ms | 22.652 ± 0.000 ms | 1.873 ± 0.000 ms a mais fora (MEC 8.3% menor) |
| Jitter de rede | 576.5 ± 0.0 us | 768.7 ± 0.0 us | 192.2 ± 0.0 us a mais fora (MEC 25.0% menor) |
| Jitter motion-to-photon | 354.2 ± 0.0 us | 516.1 ± 0.0 us | 161.9 ± 0.0 us a mais fora (MEC 31.4% menor) |
| Tempo no servidor p50 | 18.322 ± 0.000 ms | 19.537 ± 0.000 ms | - |
| Perda de pacotes DL | 0.025 ± 0.000 % | 0.009 ± 0.000 % | -0.016 ± 0.000 % a mais fora (MEC -176.4% menor) |
| Continuidade do DL | 99.97 ± 0.00 % | 99.98 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.028 ± 0.000 % | 0.000 ± 0.000 % a mais fora (MEC 0.0% menor) |
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
