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
| Atraso de rede (media) | 0.676 ± 0.000 ms | 5.158 ± 0.000 ms | 4.481 ± 0.000 ms a mais fora (MEC 86.9% menor) |
| Atraso de rede p50 | 0.589 ± 0.000 ms | 4.667 ± 0.000 ms | 4.078 ± 0.000 ms a mais fora (MEC 87.4% menor) |
| Atraso de rede p95 | 0.993 ± 0.000 ms | 8.079 ± 0.000 ms | 7.086 ± 0.000 ms a mais fora (MEC 87.7% menor) |
| Atraso de rede p99 | 2.774 ± 0.000 ms | 11.115 ± 0.000 ms | 8.341 ± 0.000 ms a mais fora (MEC 75.0% menor) |
| Motion-to-photon (media) | 11.075 ± 0.000 ms | 15.744 ± 0.000 ms | 4.668 ± 0.000 ms a mais fora (MEC 29.7% menor) |
| Motion-to-photon p50 | 11.024 ± 0.000 ms | 15.524 ± 0.000 ms | 4.500 ± 0.000 ms a mais fora (MEC 29.0% menor) |
| Motion-to-photon p95 | 12.912 ± 0.000 ms | 19.582 ± 0.000 ms | 6.670 ± 0.000 ms a mais fora (MEC 34.1% menor) |
| Jitter de rede | 128.8 ± 0.0 us | 984.5 ± 0.0 us | 855.7 ± 0.0 us a mais fora (MEC 86.9% menor) |
| Jitter motion-to-photon | 1460.4 ± 0.0 us | 1870.1 ± 0.0 us | 409.7 ± 0.0 us a mais fora (MEC 21.9% menor) |
| Tempo no servidor p50 | 10.472 ± 0.000 ms | 10.412 ± 0.000 ms | - |
| Perda de pacotes DL | 0.889 ± 0.000 % | 1.663 ± 0.000 % | 0.774 ± 0.000 % a mais fora (MEC 46.5% menor) |
| Continuidade do DL | 99.97 ± 0.00 % | 99.98 ± 0.00 % | - |
| Frames incompletos | 29.278 ± 0.000 % | 71.111 ± 0.000 % | 41.833 ± 0.000 % a mais fora (MEC 58.8% menor) |
| Vazao DL | 99.23 ± 0.00 Mbps | 98.55 ± 0.00 Mbps | - |

A coluna *Aplicacao fora* compara dois destinos DENTRO do cenario B (b-remoto x b-mec). O ganho do LBO sobre o centralizado e' a-mec x b-mec e sai de `campanha-a-vs-b.py`.

## Prova do Local Breakout

Pacotes recebidos na interface GTP de cada UPF durante o trafego de cada caminho. O que prova o breakout e' o CONTRASTE na coluna do PSA-UPF, nao a latencia menor.

| Execucao | I-UPF (MEC) | PSA-UPF (MEC) | I-UPF (remoto) | PSA-UPF (remoto) |
|---|---|---|---|---|
| 1 | 2501 | 0 | 0 | 2500 |

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
