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
| Atraso de rede (media) | 1.480 ± 0.000 ms | 2.342 ± 0.000 ms | 0.862 ± 0.000 ms a mais fora (MEC 36.8% menor) |
| Atraso de rede p50 | 1.455 ± 0.000 ms | 2.139 ± 0.000 ms | 0.684 ± 0.000 ms a mais fora (MEC 32.0% menor) |
| Atraso de rede p95 | 2.126 ± 0.000 ms | 4.223 ± 0.000 ms | 2.097 ± 0.000 ms a mais fora (MEC 49.7% menor) |
| Atraso de rede p99 | 3.167 ± 0.000 ms | 6.320 ± 0.000 ms | 3.153 ± 0.000 ms a mais fora (MEC 49.9% menor) |
| Motion-to-photon (media) | 21.618 ± 0.000 ms | 19.259 ± 0.000 ms | -2.359 ± 0.000 ms a mais fora (MEC -12.2% menor) |
| Motion-to-photon p50 | 21.609 ± 0.000 ms | 19.100 ± 0.000 ms | -2.509 ± 0.000 ms a mais fora (MEC -13.1% menor) |
| Motion-to-photon p95 | 22.008 ± 0.000 ms | 20.445 ± 0.000 ms | -1.563 ± 0.000 ms a mais fora (MEC -7.6% menor) |
| Jitter de rede | 332.5 ± 0.0 us | 984.2 ± 0.0 us | 651.7 ± 0.0 us a mais fora (MEC 66.2% menor) |
| Jitter motion-to-photon | 292.6 ± 0.0 us | 714.5 ± 0.0 us | 421.9 ± 0.0 us a mais fora (MEC 59.0% menor) |
| Tempo no servidor p50 | 20.188 ± 0.000 ms | 16.990 ± 0.000 ms | - |
| Perda de pacotes DL | 0.012 ± 0.000 % | 0.006 ± 0.000 % | -0.006 ± 0.000 % a mais fora (MEC -110.5% menor) |
| Continuidade do DL | 99.98 ± 0.00 % | 99.96 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.056 ± 0.000 % | 0.028 ± 0.000 % a mais fora (MEC 50.0% menor) |
| Vazao DL | 25.34 ± 0.00 Mbps | 25.34 ± 0.00 Mbps | - |

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
