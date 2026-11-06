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
| Atraso de rede (media) | 0.673 ± 0.000 ms | 2.471 ± 0.000 ms | 1.798 ± 0.000 ms a mais fora (MEC 72.8% menor) |
| Atraso de rede p50 | 0.579 ± 0.000 ms | 1.830 ± 0.000 ms | 1.252 ± 0.000 ms a mais fora (MEC 68.4% menor) |
| Atraso de rede p95 | 1.082 ± 0.000 ms | 5.602 ± 0.000 ms | 4.520 ± 0.000 ms a mais fora (MEC 80.7% menor) |
| Atraso de rede p99 | 2.665 ± 0.000 ms | 7.777 ± 0.000 ms | 5.113 ± 0.000 ms a mais fora (MEC 65.7% menor) |
| Motion-to-photon (media) | 11.018 ± 0.000 ms | 12.943 ± 0.000 ms | 1.925 ± 0.000 ms a mais fora (MEC 14.9% menor) |
| Motion-to-photon p50 | 10.952 ± 0.000 ms | 12.636 ± 0.000 ms | 1.684 ± 0.000 ms a mais fora (MEC 13.3% menor) |
| Motion-to-photon p95 | 12.790 ± 0.000 ms | 16.951 ± 0.000 ms | 4.161 ± 0.000 ms a mais fora (MEC 24.5% menor) |
| Jitter de rede | 338.2 ± 0.0 us | 2746.4 ± 0.0 us | 2408.2 ± 0.0 us a mais fora (MEC 87.7% menor) |
| Jitter motion-to-photon | 1675.0 ± 0.0 us | 2772.4 ± 0.0 us | 1097.4 ± 0.0 us a mais fora (MEC 39.6% menor) |
| Tempo no servidor p50 | 10.412 ± 0.000 ms | 10.252 ± 0.000 ms | - |
| Perda de pacotes DL | 0.895 ± 0.000 % | 0.899 ± 0.000 % | 0.003 ± 0.000 % a mais fora (MEC 0.4% menor) |
| Continuidade do DL | 99.96 ± 0.00 % | 99.96 ± 0.00 % | - |
| Frames incompletos | 30.259 ± 0.000 % | 25.037 ± 0.000 % | -5.222 ± 0.000 % a mais fora (MEC -20.9% menor) |
| Vazao DL | 99.22 ± 0.00 Mbps | 99.22 ± 0.00 Mbps | - |

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
