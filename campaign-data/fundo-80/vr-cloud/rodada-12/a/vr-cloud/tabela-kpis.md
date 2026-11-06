# Cenario A - UPF centralizada (baseline) - perfil `vr-cloud`

**Carga:** 50 Mbps @ 90 fps por sessao (downlink), pose/controle a 250 Hz (uplink), MTU 1200 B.

> VR interativo com render na borda: ~2K por olho a 90 fps (~50 Mbps em HEVC) e pose a 250 Hz, a taxa tipica da IMU de um headset. E' o perfil do TG1 e o caso mais exigente que ainda e' realista.

Campanha de **1 execucao(oes)** independentes. Cada execucao sobe o cenario do zero, mede e derruba os deployments antes da seguinte.

- Duracao por caminho: 60 s (descartados os 5 s iniciais)
- Carga: aplicacao VR (downlink de frames + uplink de pose), identica nos dois caminhos
- Placement: ueransim=brix-porvir-02, upf=petshopboys, mec-app=brix-porvir-05, remote-app=metallica, smf=petshopboys, amf=petshopboys

Valores: media +- desvio-padrao entre as execucoes.

| KPI | MEC via nucleo | Caminho remoto |
|---|---|---|
| Atraso de rede (media) | 1.610 ± 0.000 ms | - |
| Atraso de rede p50 | 1.551 ± 0.000 ms | - |
| Atraso de rede p95 | 2.203 ± 0.000 ms | - |
| Atraso de rede p99 | 3.227 ± 0.000 ms | - |
| Motion-to-photon (media) | 11.576 ± 0.000 ms | - |
| Motion-to-photon p50 | 11.581 ± 0.000 ms | - |
| Motion-to-photon p95 | 13.474 ± 0.000 ms | - |
| Jitter de rede | 200.9 ± 0.0 us | - |
| Jitter motion-to-photon | 1434.6 ± 0.0 us | - |
| Tempo no servidor p50 | 9.906 ± 0.000 ms | - |
| Perda de pacotes DL | 0.084 ± 0.000 % | - |
| Continuidade do DL | 99.99 ± 0.00 % | - |
| Frames incompletos | 0.759 ± 0.000 % | - |
| Vazao DL | 50.07 ± 0.00 Mbps | - |

No cenario A os dois caminhos passam pela mesma UPF central. A comparacao com o cenario B (a-mec x b-mec) sai de `campanha-a-vs-b.py`.

## Prova da ancoragem central

Pacotes recebidos na interface GTP da UPF central durante o trafego de cada caminho. No cenario A nao ha breakout: a UPF central conta os DOIS trafegos, inclusive o do MEC, que sobe ao nucleo e volta para a borda.

| Execucao | UPF central (MEC) | UPF central (remoto) |
|---|---|---|
| 1 | 2501 | 2501 |

As duas colunas andando juntas = todo o trafego ancorado no nucleo. E' a linha de base contra a qual o cenario B e' comparado (a-mec x b-mec: mesmo destino, ancora em outro lugar).

## Como ler os dois blocos de latencia

O **atraso de rede** e' ida do uplink mais volta do downlink: a parcela que o posicionamento do UPF de fato ataca. O **motion-to-photon** inclui, alem disso, o **tempo no servidor** (a espera pelo proximo instante de render mais a janela em que o gerador espalha os pacotes do frame). Vale a identidade `m2p = atraso de rede + tempo no servidor`, e a tabela traz os tres justamente para que ela possa ser conferida. Reportar so' um dos dois engana: o m2p sozinho dilui o efeito do posicionamento do UPF, o atraso de rede sozinho esconde o que o usuario sente.

O tempo no servidor e' igual nos dois caminhos por construcao (mesmo perfil, mesmo codigo, mesma janela de pacing): ele desloca o m2p dos dois lados pelo mesmo tanto e nao cria nem esconde diferenca entre eles.

## O que valida cada medida

Uma corrida so' entra na tabela se ela mediu a REDE, e nao o proprio medidor. As colunas de `resumo-por-execucao.csv` que sustentam isso:

- `srv_frames_late` / `srv_send_dropped`: o gerador nao sustentou a cadencia, ou nao conseguiu entregar os pacotes ao kernel. Perda que nasceu no servidor, nao no caminho.
- `cli_sock_overflow` (SO_RXQ_OVFL): pacotes que CHEGARAM e o kernel do cliente descartou por fila cheia. E' perda do cliente; nao pode ser lida como perda do UPF.
- `cli_udp_rcvbuf_errors`: estouro de buffer UDP no namespace do tester, que o vr-client divide com o nr-gnb e o nr-ue -- aponta perda dentro do proprio UERANSIM.
- `dl_loss_srv_pct`: perda com o denominador vindo do contador do servidor (pacotes de fato entregues ao kernel), e nao do intervalo de sequencia que o cliente observou, que nao enxerga frame perdido inteiro nas bordas.
- `ts_kernel`: 1 quando os carimbos de tempo vieram do kernel (SO_TIMESTAMPNS). Com 0, a latencia reportada carrega junto o tempo que os processos passaram fora da CPU.
- `frames_incompletos_pct`: so' frames COMPLETOS viram amostra de latencia. Se os dois caminhos perdem quantidades muito diferentes, os percentis nao sao comparaveis -- o que perde mais some com as amostras dos instantes ruins e parece melhor do que e'. Execucoes assim saem da tabela.
