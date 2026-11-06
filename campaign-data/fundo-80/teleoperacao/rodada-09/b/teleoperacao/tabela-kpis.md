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
| Atraso de rede (media) | 1.395 ± 0.000 ms | 2.270 ± 0.000 ms | 0.875 ± 0.000 ms a mais fora (MEC 38.5% menor) |
| Atraso de rede p50 | 1.437 ± 0.000 ms | 2.238 ± 0.000 ms | 0.801 ± 0.000 ms a mais fora (MEC 35.8% menor) |
| Atraso de rede p95 | 1.869 ± 0.000 ms | 3.030 ± 0.000 ms | 1.161 ± 0.000 ms a mais fora (MEC 38.3% menor) |
| Atraso de rede p99 | 2.591 ± 0.000 ms | 4.580 ± 0.000 ms | 1.988 ± 0.000 ms a mais fora (MEC 43.4% menor) |
| Motion-to-photon (media) | 14.077 ± 0.000 ms | 14.905 ± 0.000 ms | 0.829 ± 0.000 ms a mais fora (MEC 5.6% menor) |
| Motion-to-photon p50 | 14.036 ± 0.000 ms | 14.865 ± 0.000 ms | 0.830 ± 0.000 ms a mais fora (MEC 5.6% menor) |
| Motion-to-photon p95 | 15.157 ± 0.000 ms | 16.033 ± 0.000 ms | 0.876 ± 0.000 ms a mais fora (MEC 5.5% menor) |
| Jitter de rede | 195.6 ± 0.0 us | 240.1 ± 0.0 us | 44.5 ± 0.0 us a mais fora (MEC 18.5% menor) |
| Jitter motion-to-photon | 888.5 ± 0.0 us | 1028.0 ± 0.0 us | 139.5 ± 0.0 us a mais fora (MEC 13.6% menor) |
| Tempo no servidor p50 | 12.662 ± 0.000 ms | 12.589 ± 0.000 ms | - |
| Perda de pacotes DL | 0.010 ± 0.000 % | 0.054 ± 0.000 % | 0.044 ± 0.000 % a mais fora (MEC 81.5% menor) |
| Continuidade do DL | 99.98 ± 0.00 % | 99.94 ± 0.00 % | - |
| Frames incompletos | 0.028 ± 0.000 % | 0.306 ± 0.000 % | 0.278 ± 0.000 % a mais fora (MEC 90.8% menor) |
| Vazao DL | 8.06 ± 0.00 Mbps | 8.06 ± 0.00 Mbps | - |

A coluna *Aplicacao fora* compara dois destinos DENTRO do cenario B (b-remoto x b-mec). O ganho do LBO sobre o centralizado e' a-mec x b-mec e sai de `campanha-a-vs-b.py`.

## Prova do Local Breakout

Pacotes recebidos na interface GTP de cada UPF durante o trafego de cada caminho. O que prova o breakout e' o CONTRASTE na coluna do PSA-UPF, nao a latencia menor.

| Execucao | I-UPF (MEC) | PSA-UPF (MEC) | I-UPF (remoto) | PSA-UPF (remoto) |
|---|---|---|---|---|
| 1 | 5001 | 0 | 0 | 5000 |

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
