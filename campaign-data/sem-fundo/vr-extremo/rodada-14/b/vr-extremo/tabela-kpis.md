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
| Atraso de rede (media) | 0.673 ± 0.000 ms | 2.504 ± 0.000 ms | 1.831 ± 0.000 ms a mais fora (MEC 73.1% menor) |
| Atraso de rede p50 | 0.583 ± 0.000 ms | 1.836 ± 0.000 ms | 1.253 ± 0.000 ms a mais fora (MEC 68.3% menor) |
| Atraso de rede p95 | 1.056 ± 0.000 ms | 5.608 ± 0.000 ms | 4.552 ± 0.000 ms a mais fora (MEC 81.2% menor) |
| Atraso de rede p99 | 2.566 ± 0.000 ms | 8.201 ± 0.000 ms | 5.634 ± 0.000 ms a mais fora (MEC 68.7% menor) |
| Motion-to-photon (media) | 10.876 ± 0.000 ms | 13.016 ± 0.000 ms | 2.139 ± 0.000 ms a mais fora (MEC 16.4% menor) |
| Motion-to-photon p50 | 10.798 ± 0.000 ms | 12.686 ± 0.000 ms | 1.889 ± 0.000 ms a mais fora (MEC 14.9% menor) |
| Motion-to-photon p95 | 12.594 ± 0.000 ms | 17.142 ± 0.000 ms | 4.549 ± 0.000 ms a mais fora (MEC 26.5% menor) |
| Jitter de rede | 311.6 ± 0.0 us | 2648.8 ± 0.0 us | 2337.2 ± 0.0 us a mais fora (MEC 88.2% menor) |
| Jitter motion-to-photon | 2215.2 ± 0.0 us | 3035.7 ± 0.0 us | 820.5 ± 0.0 us a mais fora (MEC 27.0% menor) |
| Tempo no servidor p50 | 10.229 ± 0.000 ms | 10.294 ± 0.000 ms | - |
| Perda de pacotes DL | 0.894 ± 0.000 % | 0.932 ± 0.000 % | 0.037 ± 0.000 % a mais fora (MEC 4.0% menor) |
| Continuidade do DL | 99.98 ± 0.00 % | 99.96 ± 0.00 % | - |
| Frames incompletos | 29.556 ± 0.000 % | 26.222 ± 0.000 % | -3.334 ± 0.000 % a mais fora (MEC -12.7% menor) |
| Vazao DL | 99.25 ± 0.00 Mbps | 99.19 ± 0.00 Mbps | - |

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
