# Cenario B - dUPF com ULCL / Local Breakout - perfil `teleoperacao`

**Carga:** 8 Mbps @ 60 fps por sessao (downlink), pose/controle a 500 Hz (uplink), MTU 1200 B.

> Teleoperacao/telemedicina: video de apoio 720p60 (~8 Mbps) com a MALHA DE CONTROLE a 500 Hz. Inverte o perfil dos outros -- pouco downlink, uplink muito frequente -- e e' o caso em que a latencia da rede pesa mais do que a vazao.

Campanha de **1 execucao(oes)** independentes. Cada execucao sobe o cenario do zero, mede e derruba os deployments antes da seguinte.

- Duracao por caminho: 60 s (descartados os 5 s iniciais)
- Carga: aplicacao VR (downlink de frames + uplink de pose), identica nos dois caminhos
- Placement: ueransim=brix-porvir-02, i-upf=brix-porvir-05, mec-app=brix-porvir-05, psa-upf=petshopboys, remote-app=metallica, smf=petshopboys, amf=petshopboys

Valores: media +- desvio-padrao entre as execucoes.

| KPI | MEC / LBO | Caminho remoto | Aplicacao fora (2 UPFs) |
|---|---|---|---|
| Atraso de rede (media) | 1.403 ± 0.000 ms | 2.138 ± 0.000 ms | 0.735 ± 0.000 ms a mais fora (MEC 34.4% menor) |
| Atraso de rede p50 | 1.441 ± 0.000 ms | 2.119 ± 0.000 ms | 0.679 ± 0.000 ms a mais fora (MEC 32.0% menor) |
| Atraso de rede p95 | 1.883 ± 0.000 ms | 2.923 ± 0.000 ms | 1.040 ± 0.000 ms a mais fora (MEC 35.6% menor) |
| Atraso de rede p99 | 2.746 ± 0.000 ms | 4.450 ± 0.000 ms | 1.705 ± 0.000 ms a mais fora (MEC 38.3% menor) |
| Motion-to-photon (media) | 14.088 ± 0.000 ms | 14.819 ± 0.000 ms | 0.731 ± 0.000 ms a mais fora (MEC 4.9% menor) |
| Motion-to-photon p50 | 14.105 ± 0.000 ms | 14.769 ± 0.000 ms | 0.664 ± 0.000 ms a mais fora (MEC 4.5% menor) |
| Motion-to-photon p95 | 15.169 ± 0.000 ms | 16.023 ± 0.000 ms | 0.854 ± 0.000 ms a mais fora (MEC 5.3% menor) |
| Jitter de rede | 290.0 ± 0.0 us | 384.6 ± 0.0 us | 94.6 ± 0.0 us a mais fora (MEC 24.6% menor) |
| Jitter motion-to-photon | 1177.7 ± 0.0 us | 893.3 ± 0.0 us | -284.4 ± 0.0 us a mais fora (MEC -31.8% menor) |
| Tempo no servidor p50 | 12.673 ± 0.000 ms | 12.611 ± 0.000 ms | - |
| Perda de pacotes DL | 0.002 ± 0.000 % | 0.046 ± 0.000 % | 0.044 ± 0.000 % a mais fora (MEC 95.6% menor) |
| Continuidade do DL | 99.99 ± 0.00 % | 99.99 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.250 ± 0.000 % | 0.222 ± 0.000 % a mais fora (MEC 88.8% menor) |
| Vazao DL | 8.06 ± 0.00 Mbps | 8.06 ± 0.00 Mbps | - |

A coluna *Aplicacao fora* compara dois destinos DENTRO do cenario B (b-remoto x b-mec). O ganho do LBO sobre o centralizado e' a-mec x b-mec e sai de `campanha-a-vs-b.py`.

## Prova do Local Breakout

Pacotes recebidos na interface GTP de cada UPF durante o trafego de cada caminho. O que prova o breakout e' o CONTRASTE na coluna do PSA-UPF, nao a latencia menor.

| Execucao | I-UPF (MEC) | PSA-UPF (MEC) | I-UPF (remoto) | PSA-UPF (remoto) |
|---|---|---|---|---|
| 1 | 5001 | 0 | 0 | 4997 |

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
