#!/usr/bin/env python3
"""
Campanha A x B: a comparacao que o TG1 propoe (Secao 4.4) -- UPF centralizada
(cenario A) contra dUPF com Local Breakout (cenario B), com o MESMO destino na
borda -- com o backhaul livre e congestionado.

COMO FUNCIONA

    A campanha e' feita de RODADAS. Cada rodada roda os dois cenarios em
    sequencia, chamando test-cenario-a.py e test-cenario-b.py exatamente como
    eles sao:

        rodada 1: A -> B      rodada 2: B -> A      rodada 3: A -> B ...

    A ordem alterna para que nenhuma deriva do cluster ao longo da campanha
    caia sempre no mesmo cenario. Cada rodada vira um PAR: as duas medidas
    foram feitas com minutos de distancia, e a diferenca e' calculada dentro do
    par antes de ser agregada.

O QUE E' MEDIDO (--perfil, --com-remoto, --fundo)

    --perfil aceita uma lista. --perfil vr-cloud,vr-extremo,teleoperacao roda
    TODAS as rodadas, em todos os niveis, do vr-cloud; depois todas as do
    vr-extremo; depois as da teleoperacao. Cada perfil grava na sua pasta
    (<saida>/<nivel>/<perfil>/) e ganha a sua comparacao no fim.

    Por padrao so' o que a comparacao usa: a-mec e b-mec. --com-remoto mede
    tambem o b-remoto (uma corrida a mais por execucao do B). O a-remoto nao e'
    medido na campanha: muda o destino sem mudar a ancora e nao entra em
    nenhuma das duas comparacoes. A prova do mecanismo (passo 11 dos testes)
    usa os dois caminhos sempre.

    --fundo escolhe os niveis de congestao, em % da capacidade medida:
        --fundo 0,80,95   o default
        --fundo 0,99      so' sem fundo e 99%
        --fundo 0         a campanha sem congestao

CONGESTAO DO BACKHAUL

    No centralizado o trafego do MEC sai da borda, vai ate' a UPF no nucleo e
    volta: atravessa o enlace nuvem -> borda DUAS vezes. Com LBO ele sai na
    borda e nao atravessa NENHUMA. Para medir o que isso vale, cada cenario
    passa por niveis de trafego de fundo nesse enlace:

        sem-fundo   o enlace so' com o trafego do experimento
        fundo-80    iperf3 UDP da nuvem para a borda a 80% da capacidade
        fundo-95    idem, a 95%

    De onde vem o fundo (--ruido):
        gtp     (padrao desde 26/09/2026, ideia do orientador) trafego de
                ASSINANTE: iperf3 do no da UPF de ancoragem ate' um segundo
                UERANSIM no brix-porvir-03, PELO TUNEL GTP-U
                (congestao/ruido-gtp.yaml, scripts/ruido-gtp.py). No A ele passa
                pela mesma UPF central do experimento; no B, pelo PSA-UPF, direto
                ao gNB de ruido, sem tocar o Edge Node. O UE de ruido e' preparado
                a partir do passo 07 de cada execucao (cadastro no Mongo -- o
                passo 06 apaga os assinantes -- e, se houve deploy, pod recriado
                e sessao nova), em paralelo com os passos 08-11.
        direto  a campanha de 16/09/2026: iperf3 do no da UPF de ancoragem
                (petshopboys) ate' o brix-porvir-04, sem passar por UPF
                (congestao/iperf.yaml).
    A capacidade e' medida com iperf3 TCP no inicio de CADA rodada (no gtp,
    petshopboys -> brix-03 fora do tunel) e vale para A e B daquela rodada.
    Medida abaixo de 90% da mediana das rodadas anteriores (desta pasta, de
    qualquer perfil) e' repetida ate' 2 vezes, e vale a maior; sem rodada
    anterior, sao 2 medidas. Motivo: na campanha de 30/09-04/10, 7 de 90
    rodadas mediram ~700 Mbps num enlace de ~887, e os niveis de 95 e 99%
    viraram 75-79% de verdade. As medidas ficam em capacidade_medidas no
    fundo.json.
    Nada passa de 100%: sobrecarga continua nao e' a congestao de uma rede real.

    O fundo so' fica ligado durante o passo 12 do teste (a medicao). Deploy,
    sessao PDU e prova do mecanismo acontecem sem ele. O piloto
    (piloto-congestao.py, 16/09/2026) mostrou que o fundo e o trafego medido
    dividem a mesma fila, que o gerador nao interfere por CPU e que o PFCP do
    cenario B sobrevive a 95%.

    Dentro da rodada cada cenario sobe UMA vez e passa por todos os niveis, em
    ordem ROTATIVA entre as rodadas, para nenhum nivel ficar sempre logo depois
    do deploy. Depois do ultimo nivel o cenario e' derrubado com a mesma funcao
    que os scripts usam (por nome; o namespace nao e' tocado).

    Uma execucao congestionada so' vale se o fundo foi aplicado de verdade:
    pelo menos 90% do pedido cruzou o enlace, contado nos contadores de UDP do
    receptor (o que o proprio receptor descartou tambem cruzou o enlace). No
    gtp, nos contadores da chain do pod de ruido, e alem disso o GTP-U tem que
    ter vindo SO' da UPF de ancoragem (tcpdump no pod de ruido) e o fundo tem
    que ter ligado dentro do warmup.

O QUE SAI

    Por nivel, em <saida>/<nivel>/<perfil>/ (com --fundo 0, em <saida>/<perfil>/
    como sempre foi). A <saida> padrao e' resultados-a-vs-b-ruido-gtp (--ruido
    gtp) ou resultados-a-vs-b-congestao (--ruido direto):
        a-vs-b.md               tabelas prontas para o texto
        a-vs-b-por-rodada.csv   uma linha por rodada, com os KPIs dos caminhos medidos
        a-vs-b.json             tudo em bruto
        rodada-NN/{a,b}/        a saida completa de cada script, com saida.log
                                (e fundo.json nos niveis com fundo)

    Principal   a-mec x b-mec     o ganho do LBO sobre o centralizado: mesmo UE,
                                  mesmo destino, mesma carga, mesmo fundo; so' a
                                  ancora do plano de usuario muda de lugar.
    Secundaria  b-remoto x b-mec  (so' com --com-remoto) quanto a mais demora se
                                  a aplicacao estiver fora, com as 2 UPFs do B.

    Com mais de um nivel, em <saida>/:
        lbo-sob-congestao-<perfil>.md   O DESTAQUE: o ganho do LBO em cada nivel
                                        e quanto a congestao custa a cada
                                        cenario, pareado dentro da rodada
        lbo-sob-congestao-<perfil>.csv / .json

    Um par so' entra no A x B se as DUAS execucoes passaram nas guardas de
    saude do caminho MEC. As guardas que so' falam do remoto -- as da corrida
    do b-remoto e a de "perda muito diferente entre os caminhos", que compara
    MEC e remoto DENTRO da execucao -- tiram a execucao so' da comparacao
    b-remoto x b-mec. Sob congestao o b-remoto cruza o enlace e perde, o b-mec
    nao; se essa guarda derrubasse o par, derrubaria justamente as rodadas em
    que o LBO mais aparece (30/09-04/10: 0 pares no vr-cloud a 99%).
    figuras-a-vs-b.py funciona em qualquer pasta de nivel.

WINDOWS

    Roda como esta'. Os arquivos saem em UTF-8 e o kubectl cp dos testes usa
    destino relativo (num caminho absoluto, o "C:" vira nome de pod). Prefira
    uma --saida fora do OneDrive: a sincronizacao pode segurar arquivo aberto.

CONFIABILIDADE (o que a campanha de 30/09-04/10 ensinou)

    Depois de cada execucao a campanha confere o instrumento: o CSV por
    quadro tem que ter vindo do tester com uma linha por quadro completo do
    resumo (se nao veio, copia de novo, duas vezes); o buffer de recepcao do
    tester tem que ter os 4 MB minimos; o carimbo de tempo tem que ser do
    kernel. Falhou: a execucao e' guardada em <a|b>.instrumento-<k> e a
    campanha PARA, porque a falha se repetiria em todas as seguintes. Rodar o
    mesmo comando depois de corrigir continua de onde parou.

    Execucao que nao concluiu, ou em que o fundo nao foi aplicado, e' guardada
    em <a|b>.falhou-<k> e refeita uma vez no fim da rodada (--sem-repetir
    desliga). Medida que caiu numa guarda de qualidade NUNCA e' refeita:
    refazer ate' passar escolheria as rodadas boas.

    Cada vez que o comando roda, grava na raiz campanha-<inicio>.json (comando,
    commit do git e o que estava alterado, versoes) e campanha-<inicio>.log
    (tudo o que foi impresso). Enquanto roda, o computador nao dorme.

    Sentinela da linha de base: depois de cada execucao SEM fundo, o p50 do
    caminho MEC e' comparado com a mediana das rodadas anteriores; mais de 25%
    fora acende um alerta na hora (o defeito externo de 14-26/09 so' foi visto
    dias depois). Os relatorios repetem a conferencia no fim.

    Nos relatorios: mediana pareada e "B abaixo" ao lado da media (resistem a
    rodada bimodal), quadros incompletos (a latencia so' conta quadro
    completo), a carga efetiva do enlace no A (o trafego da aplicacao soma ao
    fundo) e a sentinela da linha de base sem fundo.

    Nivel que ja' tem resultado e' pulado: se a campanha for interrompida, rodar
    o mesmo comando de novo continua de onde parou. --rodada-inicial N comeca em
    N e a comparacao continua lendo tudo que esta' na pasta.

Uso:
    python3 scripts/campanha-a-vs-b.py --rodadas 30 --perfil vr-cloud,vr-extremo,teleoperacao --fundo 0,50,80,95,99 --com-remoto --carregar-assinantes 5
    python3 scripts/campanha-a-vs-b.py --rodadas 10 --perfil teleoperacao --carregar-assinantes 5
    python3 scripts/campanha-a-vs-b.py --rodadas 10 --perfil teleoperacao --fundo 0,99 --carregar-assinantes 5
    python3 scripts/campanha-a-vs-b.py --rodadas 10 --perfil teleoperacao --fundo 0 --com-remoto --carregar-assinantes 5
    python3 scripts/campanha-a-vs-b.py --rodadas 10 --perfil teleoperacao --ruido direto --carregar-assinantes 5
    python3 scripts/campanha-a-vs-b.py --so-comparar resultados-a-vs-b-ruido-gtp
    python3 scripts/campanha-a-vs-b.py --so-comparar resultados-a-vs-b-ruido-gtp --perfil teleoperacao
    python3 scripts/campanha-a-vs-b.py --so-comparar resultados-a-vs-b-congestao --perfil teleoperacao
    python3 scripts/campanha-a-vs-b.py --so-comparar resultados-a-vs-b/teleoperacao
"""
import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time

if sys.version_info < (3, 8):
    sys.exit("campanha-a-vs-b.py precisa de Python 3.8 ou mais novo")

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
SCRIPTS = {"a": os.path.join(AQUI, "test-cenario-a.py"),
           "b": os.path.join(AQUI, "test-cenario-b.py")}

# (chave, rotulo, caminho no resumo do vr_client, divisor, unidade, casas, menor_e_melhor)
KPIS = [
    ("net_p50", "Atraso de rede p50", ("net_rtt_us", "p50"), 1000.0, "ms", 3, True),
    ("net_p95", "Atraso de rede p95", ("net_rtt_us", "p95"), 1000.0, "ms", 3, True),
    ("net_p99", "Atraso de rede p99", ("net_rtt_us", "p99"), 1000.0, "ms", 3, True),
    ("net_media", "Atraso de rede (media)", ("net_rtt_us", "mean"), 1000.0, "ms", 3, True),
    ("jitter_net", "Jitter de rede", ("jitter_net_us",), 1.0, "us", 1, True),
    ("m2p_p50", "Motion-to-photon p50", ("m2p_us", "p50"), 1000.0, "ms", 3, True),
    ("m2p_p95", "Motion-to-photon p95", ("m2p_us", "p95"), 1000.0, "ms", 3, True),
    ("perda_pct", "Perda de pacotes DL", ("dl_packet_loss_srv_pct",), 1.0, "%", 3, True),
    # Latencia so' e' calculada sobre quadros COMPLETOS: com muitos incompletos,
    # o atraso do caminho sai otimista. Este KPI diz quanto da amostra sobrou.
    ("incompletos_pct", "Quadros incompletos", ("frames_incomplete_pct",), 1.0, "%", 2, True),
    ("vazao_mbps", "Vazao DL", ("dl_throughput_mbps",), 1.0, "Mbps", 2, None),
]
# Os KPIs do destaque. O p99 vem logo depois do p50 de proposito: no piloto a
# congestao apareceu primeiro na CAUDA, e e' a cauda que a teleoperacao sente.
KPIS_DESTAQUE = ("net_p50", "net_p99", "jitter_net", "perda_pct", "incompletos_pct")

# Quantis da t de Student (bicaudal 95% e unicaudal 80%). Com poucas rodadas a
# aproximacao normal estreitaria o intervalo e prometeria mais do que os dados dao.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
        15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080,
        22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
        29: 2.045, 30: 2.042}
T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896,
       8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876, 12: 0.873, 13: 0.870, 14: 0.868,
       15: 0.866, 16: 0.865, 17: 0.863, 18: 0.862, 19: 0.861, 20: 0.860, 21: 0.859,
       22: 0.858, 23: 0.858, 24: 0.857, 25: 0.856, 26: 0.856, 27: 0.855, 28: 0.855,
       29: 0.854, 30: 0.854}

# --- trafego de fundo (congestao/iperf.yaml) ---------------------------------
NS = "free5gc"
MANIFESTO_FUNDO = os.path.join(BASE, "congestao", "iperf.yaml")
IPERF_SRV = "congestao-iperf-servidor"   # receptor na borda, fora do experimento
IPERF_CLI = "congestao-iperf-cliente"    # gerador no no da UPF de ancoragem
PORTA_IPERF = 5201
# Payload UDP: cabe no MTU 1450 do VXLAN do Calico sem fragmentar. Tambem e' o
# tamanho usado para converter datagramas contados no receptor em Mbps.
DATAGRAMA = 1400
MBPS_POR_FLUXO = 250
# epc-mode da UPF por onde o trafego centralizado entra no nucleo: o gerador
# precisa estar no MESMO no dela para sair pela mesma placa de rede.
ANCORA = {"a": "upf", "b": "psa-upf"}
# Fracao do fundo pedido que precisa ter cruzado o enlace para o nivel valer.
MIN_FUNDO_ENTREGUE = 0.90
# O iperf pede um -t longo e e' desligado quando o passo 12 termina; este teto
# so' existe para ele nao ficar ligado para sempre se o controle se perder.
FUNDO_MAX_S = 1800
# Capacidade medida abaixo desta fracao da mediana das rodadas anteriores e'
# repetida ate' CAPACIDADE_REPETE vezes a mais; vale a maior medida.
CAPACIDADE_MIN_FRAC = 0.90
CAPACIDADE_REPETE = 2
_capacidades = []   # aceitas nesta pasta, todas as rodadas e perfis
# --ruido gtp: o modulo scripts/ruido-gtp.py (carregado no main).
R = None
SAIDA_PADRAO = {"gtp": "resultados-a-vs-b-ruido-gtp", "direto": "resultados-a-vs-b-congestao"}

VERDE, VERM, AMAR, CINZA, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if os.name == "nt":
    os.system("")   # liga as sequencias ANSI (cores) no console do Windows
for _fluxo in (sys.stdout, sys.stderr):
    # Console ou arquivo em cp1252 nao derruba a campanha por causa de um caractere.
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(errors="replace")
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    VERDE = VERM = AMAR = CINZA = RESET = ""


class ErroFundo(Exception):
    """Problema de montagem do fundo: nao e' falha de UMA medida, e sim algo que
    invalidaria todos os niveis seguintes do mesmo jeito. Para a campanha."""


class ErroInstrumento(Exception):
    """O instrumento de medida falhou de um jeito que se repetiria em todas as
    execucoes seguintes (copia do CSV por quadro, buffer do tester, carimbo de
    tempo). Para a campanha na PRIMEIRA vez, e nao dias depois."""


def quantil_t(tabela, gl, normal):
    if gl is None or gl > 30:
        return normal
    return tabela[max(k for k in tabela if k <= max(1, int(gl)))]


def valor(resumo, caminho):
    v = resumo
    for k in caminho:
        if not isinstance(v, dict):
            return None
        v = v.get(k)
    return v if isinstance(v, (int, float)) else None


def media_dp(vs):
    vs = [v for v in vs if v is not None]
    if not vs:
        return None, None
    return sum(vs) / len(vs), (statistics.stdev(vs) if len(vs) > 1 else None)


def pareado(difs):
    """Media das diferencas pareadas, IC 95% e menor diferenca detectavel."""
    n = len(difs)
    if not n:
        return None
    m = sum(difs) / n
    if n < 2:
        return {"n": n, "media": m, "dp": None, "ic": None, "mde": None}
    dp = statistics.stdev(difs)
    ep = dp / math.sqrt(n)
    t975, t80 = quantil_t(T975, n - 1, 1.960), quantil_t(T80, n - 1, 0.842)
    return {"n": n, "media": m, "dp": dp, "ic": (m - t975 * ep, m + t975 * ep),
            "mde": (t975 + t80) * ep}


def fmt(v, casas):
    return "-" if v is None else f"{v:.{casas}f}"


def nome_nivel(nivel):
    return "sem-fundo" if nivel == 0 else f"fundo-{nivel}"


def rotulo_nivel(nivel):
    return "sem fundo" if nivel == 0 else f"{nivel}%"


ORIGEM_FUNDO = {
    "direto": "iperf3 UDP do no da UPF de ancoragem ate' um brix fora do experimento",
    "gtp": ("iperf3 UDP pelo tunel GTP-U, da UPF de ancoragem (A: a UPF central; B: o "
            "PSA-UPF) ate' um segundo UERANSIM num brix fora do experimento"),
    "misto": ("fundo DIRETO e PELO TUNEL GTP-U misturados nesta pasta -- confira os "
              "fundo.json antes de usar estes numeros"),
}


def modo_fundo(fundos):
    """'gtp' ou 'direto' pelo que foi gravado. fundo.json sem 'modo' e' da
    campanha de 16/09/2026, que so' tinha o fundo direto."""
    modos = {f.get("modo", "direto") for f in fundos if f}
    return "gtp" if modos == {"gtp"} else ("direto" if modos <= {"direto"} else "misto")


def raiz_nivel(saida, perfil, nivel, legado):
    """Com --fundo 0 a campanha grava onde sempre gravou. Com niveis, cada um
    ganha <saida>/<nivel>/<perfil>/ -- o nome da pasta final continua sendo o
    perfil, que e' de onde --so-comparar e figuras-a-vs-b.py tiram o perfil."""
    if legado:
        return os.path.join(saida, perfil)
    return os.path.join(saida, nome_nivel(nivel), perfil)


# --------------------------------------------------------------------------
# trafego de fundo
# --------------------------------------------------------------------------
def kubectl(*a, timeout=120):
    try:
        return subprocess.run(["kubectl", "-n", NS, *a], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(a, 124, "", f"timeout ({timeout}s)")


def no_do(seletor):
    r = kubectl("get", "pod", "-l", seletor, "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].spec.nodeName} {.items[0].status.podIP}")
    partes = r.stdout.split()
    return (partes[0], partes[1]) if len(partes) == 2 else (None, None)


def sobe_iperf(timeout):
    print(f"\n  fundo: aplicando {os.path.relpath(MANIFESTO_FUNDO, BASE)}")
    r = kubectl("apply", "-f", MANIFESTO_FUNDO)
    if r.returncode:
        raise ErroFundo(f"kubectl apply do fundo falhou: {r.stderr.strip()[:300]}")
    for dep in (IPERF_SRV, IPERF_CLI):
        r = kubectl("rollout", "status", f"deploy/{dep}", f"--timeout={timeout}s",
                    timeout=timeout + 30)
        if r.returncode:
            raise ErroFundo(f"{dep} nao ficou pronto: {(r.stderr or r.stdout).strip()[:300]}")
    no_srv, ip_srv = no_do(f"app={IPERF_SRV}")
    no_cli, _ = no_do(f"app={IPERF_CLI}")
    if not ip_srv or not no_cli:
        raise ErroFundo("os pods do iperf nao ficaram Running")
    print(f"  fundo: gerador em {no_cli}, receptor em {no_srv} ({ip_srv})")
    return ip_srv


def no_iperf(dep, *cmd, timeout=60):
    return kubectl("exec", f"deploy/{dep}", "-c", "iperf", "--", *cmd, timeout=timeout)


def capacidade(ip_srv, segundos):
    """iperf3 TCP, 4 fluxos, nuvem -> borda. O TCP sobe ate' o enlace mais
    estreito e para: a vazao recebida e' a capacidade util do caminho."""
    for tentativa in (1, 2):
        r = no_iperf(IPERF_CLI, "iperf3", "-c", ip_srv, "-p", str(PORTA_IPERF), "-P", "4",
                     "-t", str(segundos), "-J", timeout=segundos + 60)
        try:
            j = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
        except ValueError:
            j = {"error": (r.stderr or r.stdout or "sem saida").strip()[:300]}
        if "busy" in str(j.get("error", "")) and tentativa == 1:
            time.sleep(10)
            continue
        break
    rec = ((j.get("end") or {}).get("sum_received") or {}).get("bits_per_second")
    if j.get("error") or not rec:
        raise ErroFundo(f"nao consegui medir a capacidade: {j.get('error', 'sem vazao recebida')}")
    return rec / 1e6


def udp_receptor():
    """(datagramas recebidos, datagramas com erro) no netns do receptor. Erro
    inclui o descarte por buffer cheio -- que tambem cruzou o enlace."""
    r = no_iperf(IPERF_SRV, "cat", "/proc/net/snmp")
    linhas = [l.split()[1:] for l in r.stdout.splitlines() if l.startswith("Udp:")]
    if len(linhas) < 2:
        return None
    c = dict(zip(linhas[0], linhas[1]))
    try:
        return int(c["InDatagrams"]), int(c["InErrors"])
    except (KeyError, ValueError):
        return None


def liga_fundo(cen, fundo):
    """Confere o placement NESTE instante (o cenario esta' no ar) e liga o iperf.
    O gerador fora do no da ancora nao disputaria a fila da aplicacao; o
    receptor dentro do experimento pioraria o B por CPU."""
    no_ancora, _ = no_do(f"epc-mode={ANCORA[cen]}")
    no_cli, _ = no_do(f"app={IPERF_CLI}")
    no_srv, _ = no_do(f"app={IPERF_SRV}")
    experimento = {no_do("epc-mode=mec-app")[0], no_do("epc-mode=ueransim")[0]} - {None}
    if not no_ancora or no_cli != no_ancora:
        raise ErroFundo(f"o gerador esta' em {no_cli} e a UPF de ancoragem ({ANCORA[cen]}) "
                        f"em {no_ancora}: ajuste o nodeSelector em congestao/iperf.yaml")
    if no_srv in experimento:
        raise ErroFundo(f"o receptor caiu em {no_srv}, que e' parte do experimento "
                        "(Edge Node ou tester): escolha outro brix em congestao/iperf.yaml")
    fluxos = max(1, math.ceil(fundo["pedido_mbps"] / MBPS_POR_FLUXO))
    cmd = ["kubectl", "-n", NS, "exec", f"deploy/{IPERF_CLI}", "-c", "iperf", "--",
           "iperf3", "-c", fundo["ip_srv"], "-p", str(PORTA_IPERF), "-u",
           "-b", f"{fundo['pedido_mbps'] / fluxos:.1f}M", "-l", str(DATAGRAMA),
           "-P", str(fluxos), "-t", str(FUNDO_MAX_S)]
    u0 = udp_receptor()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"proc": proc, "u0": u0, "t0": time.time(), "no_gerador": no_cli,
            "no_receptor": no_srv, "no_ancora": no_ancora, "fluxos": fluxos}


def desliga_fundo(estado, fundo):
    no_iperf(IPERF_CLI, "pkill", "-f", "iperf3 -c", timeout=30)
    try:
        estado["proc"].wait(timeout=15)
    except subprocess.TimeoutExpired:
        estado["proc"].kill()
    segundos = time.time() - estado["t0"]
    u1 = udp_receptor()
    reg = {"nivel": fundo["nivel"], "capacidade_mbps": fundo["capacidade_mbps"],
           "pedido_mbps": fundo["pedido_mbps"], "fluxos": estado["fluxos"],
           "segundos_ligado": round(segundos, 1), "no_gerador": estado["no_gerador"],
           "no_receptor": estado["no_receptor"], "no_ancora": estado["no_ancora"],
           "ligado": True, "cruzou_mbps": None, "descartes_receptor": None,
           "fracao_entregue": None}
    if estado["u0"] and u1 and segundos > 0:
        recebidos, erros = u1[0] - estado["u0"][0], u1[1] - estado["u0"][1]
        reg["cruzou_mbps"] = (recebidos + erros) * DATAGRAMA * 8 / segundos / 1e6
        reg["descartes_receptor"] = erros
        reg["fracao_entregue"] = reg["cruzou_mbps"] / fundo["pedido_mbps"]
    return reg


# --------------------------------------------------------------------------
# fundo pelo tunel GTP-U (--ruido gtp)
# --------------------------------------------------------------------------
def carrega_ruido():
    spec = importlib.util.spec_from_file_location("ruido_gtp", os.path.join(AQUI, "ruido-gtp.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sobe_ruido(timeout):
    print(f"\n  fundo: aplicando {os.path.relpath(R.MANIFESTO, BASE)} (pelo tunel GTP-U)")
    try:
        R.aplica(timeout)
    except R.ErroRuido as e:
        raise ErroFundo(str(e))
    no_g, _ = R.pod(f"app={R.GERADOR}")
    no_r, _ = R.pod(f"app={R.RUIDO}")
    print(f"  fundo: gerador em {no_g}, UERANSIM de ruido em {no_r} (UE {R.IMSI})")


def capacidade_ruido(segundos):
    """Como capacidade(), ate' o pod de ruido e fora do tunel -- com o IP de
    AGORA, que muda a cada vez que o pod e' recriado."""
    _, ip = R.pod(f"app={R.RUIDO}")
    if not ip:
        raise ErroFundo(f"o pod {R.RUIDO} nao esta Running: sem destino para medir a capacidade "
                        f"(kubectl -n {NS} get pod -l app={R.RUIDO})")
    try:
        return R.capacidade({"ip_ruido": ip}, segundos)
    except R.ErroRuido as e:
        raise ErroFundo(str(e))


def capacidades_gravadas(saida):
    """Capacidades ja' gravadas nos fundo.json desta pasta: a referencia de uma
    campanha retomada nao recomeca do zero."""
    caps = []
    for f in glob.glob(os.path.join(saida, "*", "*", "rodada-*", "*", "fundo.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                c = json.load(fh).get("capacidade_mbps")
        except (OSError, ValueError):
            continue
        if c:
            caps.append(c)
    return caps


def capacidade_da_rodada(saida, perfil, niveis, n):
    """(capacidade, medidas) ja' gravadas nesta rodada por uma execucao valida,
    ou (None, None). Na retomada, o que falta da rodada usa a MESMA capacidade
    -- e portanto o mesmo fundo em Mbps -- que o resto do par."""
    for nv in niveis:
        if not nv:
            continue
        for cen in ("a", "b"):
            f = os.path.join(pasta_rodada(raiz_nivel(saida, perfil, nv, False), n), cen, "fundo.json")
            if not os.path.exists(f):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    fj = json.load(fh)
            except (OSError, ValueError):
                continue
            if fj.get("capacidade_mbps"):
                return fj["capacidade_mbps"], fj.get("capacidade_medidas") or [fj["capacidade_mbps"]]
    return None, None


def mede_capacidade(args, ip_srv):
    """(capacidade da rodada, todas as medidas). Uma medida abaixo de
    CAPACIDADE_MIN_FRAC da mediana das rodadas anteriores e' repetida e vale a
    maior: o fundo e' uma fracao dela, e uma capacidade subestimada vira um
    nivel mais baixo que o nominal sem ninguem ver. Sem referencia ainda (as
    primeiras rodadas), sao sempre 2 medidas."""
    ref = statistics.median(_capacidades) if len(_capacidades) >= 3 else None
    minimo = 1 if ref else 2
    medidas = []
    for i in range(1 + CAPACIDADE_REPETE):
        medidas.append(capacidade_ruido(args.duracao_capacidade) if args.ruido == "gtp"
                       else capacidade(ip_srv, args.duracao_capacidade))
        if len(medidas) >= minimo and (ref is None or max(medidas) >= CAPACIDADE_MIN_FRAC * ref):
            break
        if i < CAPACIDADE_REPETE:
            if ref:
                print(f"    {AMAR}capacidade {medidas[-1]:.0f} Mbps, abaixo de "
                      f"{CAPACIDADE_MIN_FRAC:.0%} da mediana das rodadas anteriores ({ref:.0f}); "
                      f"medindo de novo{RESET}")
            time.sleep(5)
    cap = max(medidas)
    if ref and cap < CAPACIDADE_MIN_FRAC * ref:
        print(f"    {AMAR}aviso{RESET}: a capacidade ficou baixa nas {len(medidas)} medidas "
              f"({', '.join(f'{m:.0f}' for m in medidas)} Mbps); segue com {cap:.0f} -- "
              "pode ser o enlace de verdade")
    _capacidades.append(cap)
    return cap, medidas


# (AMF, SMF, UPF de ancoragem) quando o UE de ruido abriu a sessao atual.
_nucleo_da_sessao = None


class PreparoRuido(threading.Thread):
    """Deixa o UE de ruido pronto para o passo 12, em paralelo com os passos
    08-11 do teste. Comeca no 07 porque o 06 (--carregar-assinantes) apaga todo
    assinante do Mongo, inclusive o do ruido.

    O UE da execucao anterior so' e' reaproveitado se o NUCLEO for o mesmo em
    que ele abriu a sessao (os mesmos pods de AMF, SMF e UPF de ancoragem --
    R.nucleo) e ele ainda estiver registrado e com IP. Qualquer deploy desde
    entao, em qualquer nivel -- inclusive num "sem fundo", que nao prepara o
    ruido --, recria o pod: o gNB ficou com o SCTP de uma AMF que nao existe
    mais, e o UE so' PARECE registrado. A sessao sobrevive ao cadastro apagado
    pelo passo 06, que so' e' consultado no registro e na abertura de sessao."""

    def __init__(self, cen, reiniciar, timeout):
        super().__init__(daemon=True)
        self.cen, self.reiniciar, self.timeout = cen, reiniciar, timeout
        self.est = self.erro = self.fase = self.segundos = None
        self.reiniciou, self.t0 = False, time.time()
        self.start()

    def run(self):
        global _nucleo_da_sessao
        try:
            self.fase = "placement"
            R.placement(self.cen)
            self.fase = "ue"
            R.cadastra()
            atual = R.nucleo(self.cen)
            ip = None
            if not self.reiniciar and atual == _nucleo_da_sessao:
                ip = R.ue_ip()
                if ip and not R.ue_registrado():
                    ip = None
            if not ip:
                _nucleo_da_sessao = None
                ip = R.reinicia_ue(self.timeout)
                _nucleo_da_sessao = atual
                self.reiniciou = True
            self.fase = "placement"
            est = R.placement(self.cen)          # o pod recriado tem outro IP
            est.update(ue_ip=ip, cenario=self.cen)
            self.est = est
        except Exception as e:                      # noqa: BLE001
            self.erro = e
        finally:
            self.segundos = time.time() - self.t0


def liga_ruido(cen, fundo, preparo, espera):
    """Liga o fundo no passo 12. Nao espera o UE de ruido alem do warmup: o
    fundo tem que estar no ar quando a janela medida comecar."""
    t12 = time.time()
    if preparo is None:
        return {"falha": "o UE de ruido nao foi preparado (o passo 07 nao apareceu nesta tentativa)"}
    preparo.join(espera)
    if preparo.is_alive():
        return {"falha": f"o UE de ruido nao ficou pronto a tempo ({time.time() - preparo.t0:.0f}s "
                         "desde o passo 07); o fundo nao foi ligado"}
    if preparo.erro is not None:
        if preparo.fase == "placement":
            raise ErroFundo(str(preparo.erro))
        return {"falha": f"UE de ruido: {preparo.erro}"}
    est = preparo.est
    lig = R.liga(est, fundo["pedido_mbps"], FUNDO_MAX_S)
    atraso = time.time() - t12
    # Prova do caminho DURANTE a medicao: o GTP-U que chega ao pod de ruido tem
    # que vir so' da UPF de ancoragem. No B, vindo do I-UPF, o fundo estaria
    # passando pelo Edge Node e o b-mec pioraria por outro motivo.
    time.sleep(2)
    fontes = R.origem_gtpu()
    ok, texto = R.confere_origem(cen, fontes)
    return {"lig": lig, "est": est, "atraso_s": atraso, "origem_ok": ok, "origem": texto,
            "fontes": fontes, "preparo_s": preparo.segundos, "reiniciou": preparo.reiniciou}


def desliga_ruido(estado, fundo, warmup):
    reg = {"modo": "gtp", "nivel": fundo["nivel"], "capacidade_mbps": fundo["capacidade_mbps"],
           "pedido_mbps": fundo["pedido_mbps"], "ligado": False, "cruzou_mbps": None,
           "fracao_entregue": None, "descartes_receptor": None, "problemas": []}
    if "falha" in estado:
        reg["problemas"].append(estado["falha"])
        return reg
    reg.update(R.desliga(estado["lig"]))
    est = estado["est"]
    reg.update(ligado=True, no_gerador=est["no_gerador"], no_receptor=est["no_ruido"],
               no_ancora=est["no_ancora"], ue_ruido_ip=est["ue_ip"],
               atraso_s=round(estado["atraso_s"], 1),
               preparo_s=round(estado["preparo_s"] or 0, 1), ue_recriado=estado["reiniciou"],
               origem_gtpu=estado["fontes"], origem=estado["origem"])
    if reg["cruzou_mbps"] is not None:
        reg["fracao_entregue"] = reg["cruzou_mbps"] / fundo["pedido_mbps"]
    if not estado["origem_ok"]:
        reg["problemas"].append(estado["origem"])
    if estado["atraso_s"] > warmup:
        reg["problemas"].append(f"o fundo ligou {estado['atraso_s']:.0f}s depois do inicio do "
                                f"passo 12, fora do warmup de {warmup:g}s")
    return reg


# --------------------------------------------------------------------------
# execucao das rodadas
# --------------------------------------------------------------------------
def pasta_rodada(raiz, n):
    return os.path.join(raiz, f"rodada-{n:02d}")


def guarda_do_remoto(msg):
    """Guarda que so' fala do caminho remoto: a de uma corrida do remoto
    ("b-remoto: ...") e a que compara MEC e remoto dentro da execucao. Ela
    tira a execucao da comparacao b-remoto x b-mec, nao do A x B."""
    return msg.startswith(("a-remoto:", "b-remoto:", "perda muito diferente entre os caminhos"))


def carrega(pasta_cenario, perfil, nivel=0):
    """A execucao gravada por um dos scripts, ou None se ela nao concluiu.

    _valida          vale para o A x B: nenhuma guarda de campanha sobre o
                     caminho MEC e, com fundo, o fundo aplicado de verdade
    _valida_remoto   vale tambem para b-remoto x b-mec: nenhuma guarda de
                     campanha, inclusive as do remoto"""
    p = os.path.join(pasta_cenario, perfil, "campanha.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        j = json.load(fh)
    ex = j.get("execucoes") or []
    if not ex:
        return None
    e = ex[0]
    guardas = [m for esc, m in e.get("avisos", []) if esc == "campanha"]
    e["_valida"] = not [m for m in guardas if not guarda_do_remoto(m)]
    e["_valida_remoto"] = not guardas
    e["_carga"] = j.get("carga")
    e["_fundo"] = None
    if nivel:
        # Nivel com fundo sem prova de que o fundo existiu nao e' nivel com fundo.
        f = os.path.join(pasta_cenario, "fundo.json")
        fj = None
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                fj = json.load(fh)
        e["_fundo"] = fj
        if not (fj and fj.get("ligado")
                and (fj.get("fracao_entregue") or 0) >= MIN_FUNDO_ENTREGUE
                and not fj.get("problemas")):
            e["_valida"] = e["_valida_remoto"] = False
    return e


_testes = {}


def teste(cen):
    """O modulo do test-cenario-<cen>.py, carregado uma vez."""
    if cen not in _testes:
        spec = importlib.util.spec_from_file_location(f"teste_cenario_{cen}", SCRIPTS[cen])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _testes[cen] = mod
    return _testes[cen]


def derruba(cen):
    """Derruba o cenario com a funcao do proprio script (por nome, namespace
    intocado) -- a mesma derrubada que a campanha sem fundo sempre usou."""
    teste(cen).derrubar(argparse.Namespace(timeout_derrubada=300))


def roda_cenario(cen, pasta, args, perfil, deploy=True, sem_derrubar=False, fundo=None):
    # O remoto so' no B (--com-remoto): o a-remoto nao entra em comparacao nenhuma.
    caminhos = "todos" if args.com_remoto and cen == "b" else "mec"
    cmd = [sys.executable, "-u", SCRIPTS[cen], "--repeticoes", "1",
           "--perfil", perfil, "--saida", pasta,
           "--duracao", str(args.duracao), "--warmup", str(args.warmup),
           "--prova-duracao", str(args.prova_duracao),
           "--tentativas", str(args.tentativas), "--timeout", str(args.timeout),
           "--caminhos", caminhos]
    if deploy:
        cmd.append("--deploy")
    if sem_derrubar:
        cmd.append("--sem-derrubar")
    if args.carregar_assinantes:
        cmd += ["--carregar-assinantes", str(args.carregar_assinantes)]
    if args.conciso:
        cmd.append("--conciso")
    os.makedirs(pasta, exist_ok=True)
    ultima = ""
    # UTF-8 no filho e na leitura: no Windows o padrao e' cp1252 nos dois lados.
    env = dict(os.environ, NO_COLOR="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    estado, registros = None, []
    gtp = bool(fundo) and args.ruido == "gtp"
    preparo, deployou = None, False

    def desliga(est):
        return desliga_ruido(est, fundo, args.warmup) if gtp else desliga_fundo(est, fundo)

    with open(os.path.join(pasta, "saida.log"), "w", encoding="utf-8") as log:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", cwd=BASE, env=env)
        try:
            for linha in p.stdout:
                log.write(linha)
                if re.match(r"^\[\d\d\]|^  (OK|AVISO) |FALHOU|^CENARIO ", linha):
                    print(f"    {cen.upper()} {linha.rstrip()}")
                if linha.strip():
                    ultima = linha.strip()
                if gtp and re.search(r"cenario [AB] aplicado", linha):
                    deployou = True
                passo = re.match(r"^\[(\d\d)\]", linha)
                if fundo and passo:
                    n = passo.group(1)
                    if gtp and n == "01":
                        deployou = False            # nova tentativa
                    if gtp and n == "07":
                        # Depois do 06, que apaga os assinantes; em paralelo
                        # com os passos 08-11.
                        if preparo is not None and preparo.is_alive():
                            preparo.join()
                        preparo = PreparoRuido(cen, deployou, args.timeout)
                    # O fundo acompanha o passo 12 (a medicao). Qualquer outro
                    # cabecalho desliga -- inclusive o [01] de uma nova tentativa.
                    if n == "12" and estado is None:
                        if gtp:
                            estado = liga_ruido(cen, fundo, preparo, max(1.0, args.warmup - 1))
                        else:
                            estado = liga_fundo(cen, fundo)
                        if "falha" in estado:
                            print(f"    {VERM}{cen.upper()} fundo NAO ligado: {estado['falha']}{RESET}")
                        else:
                            print(f"    {CINZA}{cen.upper()} fundo ligado: {fundo['pedido_mbps']:.0f} "
                                  f"Mbps ({fundo['nivel']}% de {fundo['capacidade_mbps']:.0f})"
                                  + (f"; {estado['origem']}" if gtp else "") + RESET)
                    elif n != "12" and estado is not None:
                        registros.append(desliga(estado))
                        estado = None
            rc = p.wait()
        except BaseException:
            p.terminate()
            raise
        finally:
            if estado is not None:
                registros.append(desliga(estado))
            if fundo:
                # Vale o ULTIMO trecho de fundo: e' o da tentativa que gravou o resultado.
                reg = dict(registros[-1]) if registros else {
                    "nivel": fundo["nivel"], "capacidade_mbps": fundo["capacidade_mbps"],
                    "pedido_mbps": fundo["pedido_mbps"], "ligado": False}
                reg["vezes_ligado"] = len(registros)
                if fundo.get("capacidade_medidas"):
                    reg["capacidade_medidas"] = [round(m, 1) for m in fundo["capacidade_medidas"]]
                with open(os.path.join(pasta, "fundo.json"), "w", encoding="utf-8") as fh:
                    json.dump(reg, fh, indent=2)
                if reg.get("fracao_entregue") is not None:
                    cor = VERDE if reg["fracao_entregue"] >= MIN_FUNDO_ENTREGUE else VERM
                    print(f"    {cor}{cen.upper()} fundo desligado: cruzaram "
                          f"{reg['cruzou_mbps']:.0f} de {reg['pedido_mbps']:.0f} Mbps "
                          f"em {reg['segundos_ligado']:.0f}s{RESET}")
                if reg.get("problemas"):
                    print(f"    {VERM}{cen.upper()} nivel invalido pelo fundo: "
                          f"{'; '.join(reg['problemas'])}{RESET}")
    return rc, ultima


# --------------------------------------------------------------------------
# conferencia do instrumento e repeticao de falha de infraestrutura
# --------------------------------------------------------------------------
def descarta(pasta, motivo):
    """Tira uma execucao do caminho sem apagar nada: <pasta>.<motivo>-<k>. A
    comparacao so' le as pastas a/ e b/, e a retomada mede de novo."""
    k = 1
    while os.path.exists(f"{pasta}.{motivo}-{k}"):
        k += 1
    destino = f"{pasta}.{motivo}-{k}"
    for _ in range(5):
        try:
            os.rename(pasta, destino)
            return destino
        except PermissionError:
            # Windows: OneDrive ou antivirus segurando um arquivo por instantes.
            time.sleep(3)
    os.rename(pasta, destino)
    return destino


def falha_de_infra(pasta, perfil, nivel):
    """Motivo para repetir a execucao, ou None.

    So' falha de INFRAESTRUTURA: a execucao nao concluiu (deploy, PFCP, sessao
    PDU) ou o fundo nao foi aplicado (UE de ruido sem trafego, GTP-U pelo
    caminho errado, fundo ligado tarde). Execucao que MEDIU e caiu numa guarda
    de qualidade -- perda, pose, fundo que cruzou menos de 90% porque o enlace
    estava saturado -- fica como esta': repetir ate' passar escolheria as
    rodadas boas e enviesaria a comparacao."""
    if carrega(pasta, perfil) is None:
        return "a execucao nao concluiu"
    if nivel:
        fj = None
        f = os.path.join(pasta, "fundo.json")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                fj = json.load(fh)
        if not fj or not fj.get("ligado"):
            return "o fundo nao ligou" + (f" ({'; '.join(fj['problemas'])})"
                                          if fj and fj.get("problemas") else "")
        if fj.get("problemas"):
            return "o fundo nao foi aplicado direito (" + "; ".join(fj["problemas"]) + ")"
    return None


def csv_que_nao_bate(pasta, perfil, e):
    """Caminhos cujo CSV por quadro falta ou nao e' DESTA execucao: o
    vr_client grava uma linha por quadro completo, entao as linhas tem que
    ser exatamente o frames_complete do resumo. Um CSV velho que sobrou no
    /data do tester tambem cai aqui."""
    ruins = []
    for nome, resumo in sorted((e.get("campanha") or {}).items()):
        n = None
        for csvf in sorted(glob.glob(os.path.join(pasta, perfil, "run-*", nome + ".csv"))):
            with open(csvf, encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in fh) - 1
        if n is None or n != resumo.get("frames_complete"):
            ruins.append(nome)
    return ruins


def copia_csv(cen, pasta, perfil):
    """Copia de novo o /data do tester, que continua no ar (--sem-derrubar).
    Destino relativo pelo mesmo motivo do teste: o "C:" do Windows."""
    runs = sorted(glob.glob(os.path.join(pasta, perfil, "run-*")))
    destino = runs[-1] if runs else os.path.join(pasta, perfil, "run-01")
    os.makedirs(destino, exist_ok=True)
    try:
        r = subprocess.run(["kubectl", "-n", NS, "cp", f"{teste(cen).TESTER_POD}:/data", ".",
                            "-c", "vr-client"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180, cwd=destino)
    except subprocess.TimeoutExpired:
        return "timeout (180s)"
    return (r.stderr or r.stdout).strip()[:200] if r.returncode else ""


def confere_instrumento(cen, pasta, perfil, pode_copiar):
    """Problemas SISTEMATICOS do instrumento numa execucao que concluiu ([] se
    nenhum). Na campanha de 30/09-04/10 o kubectl cp falhou nas 898
    execucoes e ninguem viu, porque era um aviso entre dezenas."""
    e = carrega(pasta, perfil)
    if e is None:
        return []
    t = teste(cen)
    problemas = []
    for nome, resumo in sorted((e.get("campanha") or {}).items()):
        saude = resumo.get("saude") or {}
        buf = saude.get("sock_rcvbuf_bytes")
        if buf is not None and buf < t.RMEM_MIN:
            problemas.append(
                f"{nome}: o vr_client ficou com {buf // 1024} kB de buffer de recepcao "
                f"(minimo {t.RMEM_MIN // 1024} kB). O net.core.rmem_max do no do tester "
                "voltou ao padrao (reboot?). No no: sudo sysctl -w "
                "net.core.rmem_max=16777216 net.core.wmem_max=16777216")
        if saude.get("rx_timestamp_kernel") is False:
            problemas.append(f"{nome}: sem carimbo de tempo do kernel no vr_client; a latencia "
                             "passa a incluir o tempo que o cliente ficou fora da CPU")
    ruins, erro = csv_que_nao_bate(pasta, perfil, e), ""
    for tentativa in range(1, 3 if pode_copiar else 1):
        if not ruins:
            break
        print(f"    {AMAR}{cen.upper()} CSV por quadro faltando ou de outra execucao "
              f"({', '.join(ruins)}); copiando de novo do tester (tentativa {tentativa}){RESET}")
        erro = copia_csv(cen, pasta, perfil)
        ruins = csv_que_nao_bate(pasta, perfil, e)
    if ruins:
        problemas.append(f"o CSV por quadro de {', '.join(ruins)} nao veio do tester"
                         + (f" (kubectl cp: {erro})" if erro else "")
                         + ". Sem ele nao ha' curva de cauda quadro a quadro.")
    return problemas


def roda_conferido(cen, pasta, args, perfil, nv, repetir, **kw):
    """Roda uma execucao e confere. Devolve (rc, ultima, motivo): motivo e' a
    falha de infraestrutura que pede repeticao (None se nao ha'). Problema do
    instrumento descarta a execucao e para a campanha (ErroInstrumento)."""
    if os.path.isdir(pasta):
        # Tentativa anterior (falha de infraestrutura, ou --refazer): nada de
        # misturar arquivos de duas execucoes na mesma pasta.
        velha = falha_de_infra(pasta, perfil, nv)
        destino = descarta(pasta, "falhou" if velha else "refeita")
        print(f"    {CINZA}{cen.upper()} {nome_nivel(nv)}: tentativa anterior guardada em "
              f"{os.path.basename(destino)}{' (' + velha + ')' if velha else ''}{RESET}")
    t0 = time.time()
    rc, ultima = roda_cenario(cen, pasta, args, perfil, **kw)
    cor = VERDE if rc == 0 else VERM
    print(f"    {cor}{cen.upper()} {nome_nivel(nv)} terminou (rc={rc}) em "
          f"{time.time() - t0:.0f}s{RESET}: {ultima}")
    motivo = falha_de_infra(pasta, perfil, nv)
    if motivo is None:
        problemas = confere_instrumento(cen, pasta, perfil, pode_copiar=kw.get("sem_derrubar", False))
        if problemas:
            destino = descarta(pasta, "instrumento")
            raise ErroInstrumento(f"{cen.upper()} {nome_nivel(nv)} em {pasta}:\n  - "
                                  + "\n  - ".join(problemas)
                                  + f"\n  A execucao foi guardada em {os.path.basename(destino)} "
                                  "e sera' medida de novo: corrija e rode o mesmo comando.")
        # pasta = <raiz do nivel>/rodada-NN/<cen>
        m = re.match(r"rodada-(\d+)$", os.path.basename(os.path.dirname(pasta)))
        if nv == 0 and m:
            alerta_linha_de_base(os.path.dirname(os.path.dirname(pasta)), perfil,
                                 int(m.group(1)), cen)
        return rc, ultima, None
    if repetir:
        destino = descarta(pasta, "falhou")
        print(f"    {AMAR}{cen.upper()} {nome_nivel(nv)}: {motivo}; guardada em "
              f"{os.path.basename(destino)} e repetida no fim da rodada{RESET}")
        return rc, ultima, motivo
    print(f"    {VERM}{cen.upper()} {nome_nivel(nv)}: {motivo} de novo; fica para a "
          f"proxima vez que o comando rodar{RESET}")
    return rc, ultima, None


def alerta_linha_de_base(raiz, perfil, n, cen, faixa=0.25):
    """Sentinela AO VIVO: o p50 sem fundo desta rodada contra a mediana das
    rodadas anteriores do mesmo cenario. O defeito de 14-26/09 (a-mec 5 a 20x
    mais lento, causa externa) so' foi visto depois; aqui aparece na hora."""
    cam = f"{cen}-mec"
    vs = {}
    for d in glob.glob(os.path.join(raiz, "rodada-*")):
        m = re.match(r"rodada-(\d+)$", os.path.basename(d))
        e = carrega(os.path.join(d, cen), perfil) if m else None
        v = valor(camp(e, cam), ("net_rtt_us", "p50")) if e and e["_valida"] else None
        if v is not None:
            vs[int(m.group(1))] = v / 1000
    atual = vs.pop(n, None)
    if atual is None or len(vs) < 3:
        return
    ref = statistics.median(vs.values())
    if abs(atual / ref - 1) > faixa:
        print(f"    {VERM}SENTINELA: {cam} sem fundo nesta rodada = {atual:.3f} ms, contra "
              f"{ref:.3f} ms de mediana nas rodadas anteriores ({atual / ref - 1:+.0%}). Sem fundo "
              "isto nao e' efeito do LBO: olhe o testbed (o defeito de 14-26/09 comecou "
              f"assim). A campanha continua.{RESET}")


def prepara_fundo(args, niveis, legado, perfis):
    """Imprime o que vai ser medido e sobe o gerador do fundo, UMA vez para
    todos os perfis. Devolve o IP do receptor do fundo direto (None no gtp)."""
    print(f"\n  perfis, nesta ordem: {', '.join(perfis)} ({args.rodadas} rodadas cada)")
    print(f"  caminhos medidos: {'a-mec, b-mec e b-remoto' if args.com_remoto else 'a-mec e b-mec'}"
          + ("" if legado else "   niveis: " + ", ".join(rotulo_nivel(nv) for nv in niveis)
             + "   fundo: " + ("pelo tunel GTP-U" if args.ruido == "gtp" else "direto")))
    if max(niveis) >= 95:
        print(f"  {AMAR}aviso{RESET}: no cenario A o trafego da propria aplicacao soma ao fundo "
              f"no enlace; a {max(niveis)}%, nos perfis pesados, a carga passa da capacidade e a "
              "fila fica cheia o tempo todo (perda alta e poucos quadros completos no A).")
    if legado:
        return None
    if args.ruido == "gtp":
        sobe_ruido(args.timeout)
        return None
    return sobe_iperf(args.timeout)


def rodadas(args, saida, niveis, legado, perfil, ip_srv):
    for n in range(args.rodada_inicial, args.rodadas + 1):
        ordem = ("a", "b") if n % 2 else ("b", "a")
        k = (n - 1) % len(niveis)
        ordem_niveis = niveis[k:] + niveis[:k]
        print(f"\n{'#' * 72}\n# {perfil} -- RODADA {n} de {args.rodadas}: "
              f"{ordem[0].upper()} -> {ordem[1].upper()}"
              + ("" if legado else "   niveis: " + " -> ".join(nome_nivel(x) for x in ordem_niveis))
              + f"\n{'#' * 72}")
        cap, medidas = None, None
        for cen in ordem:
            def pasta(nv):
                return os.path.join(pasta_rodada(raiz_nivel(saida, perfil, nv, legado), n), cen)
            # Pendente: nunca medido, ou medido com falha de infraestrutura (nao
            # concluiu, fundo nao aplicado) -- inclusive de uma vez anterior em
            # que o comando rodou. A tentativa velha e' guardada, nao apagada.
            pendentes = [nv for nv in ordem_niveis
                         if args.refazer or falha_de_infra(pasta(nv), perfil, nv) is not None]
            if not pendentes:
                print(f"    {cen.upper()} ja' medido nesta rodada; pulando")
                continue
            if legado:
                # A campanha de sempre: sobe do zero, mede, derruba (por isso
                # o CSV nao pode ser copiado de novo depois).
                _, _, motivo = roda_conferido(cen, pasta(0), args, perfil, 0, args.repetir_falhas)
                if motivo:
                    roda_conferido(cen, pasta(0), args, perfil, 0, False)
                continue
            if cap is None and any(pendentes):
                cap, medidas = capacidade_da_rodada(saida, perfil, niveis, n)
                if cap:
                    print(f"    capacidade desta rodada, ja' gravada: {cap:.0f} Mbps (retomada)")
                else:
                    cap, medidas = mede_capacidade(args, ip_srv)
                    print(f"    capacidade util nuvem -> borda nesta rodada: {cap:.0f} Mbps"
                          + (f" (medidas: {', '.join(f'{m:.0f}' for m in medidas)})"
                             if len(medidas) > 1 else ""))
            precisa_deploy, no_ar = True, False
            # Falha de infraestrutura e' repetida UMA vez, no fim da rodada,
            # depois dos outros niveis (a ordem rotativa fica como planejada).
            fila, repetidos = list(pendentes), set()
            try:
                while fila:
                    nv = fila.pop(0)
                    fundo = None if nv == 0 else {
                        "nivel": nv, "capacidade_mbps": cap, "capacidade_medidas": medidas,
                        "pedido_mbps": cap * nv / 100, "ip_srv": ip_srv}
                    print(f"\n    {cen.upper()} -- {nome_nivel(nv)}"
                          + (" (deploy)" if precisa_deploy else " (mesmo deploy)")
                          + (" (repeticao)" if nv in repetidos else ""))
                    repetir = args.repetir_falhas and nv not in repetidos
                    no_ar = True
                    rc, ultima, motivo = roda_conferido(
                        cen, pasta(nv), args, perfil, nv, repetir,
                        deploy=precisa_deploy, sem_derrubar=True, fundo=fundo)
                    # Execucao que falhou pode ter deixado o cenario quebrado: o
                    # nivel seguinte sobe do zero em vez de herdar o estado.
                    precisa_deploy = rc != 0
                    if motivo:
                        repetidos.add(nv)
                        fila.append(nv)
            finally:
                if no_ar:
                    derruba(cen)


# --------------------------------------------------------------------------
# comparacao de um nivel
# --------------------------------------------------------------------------
def compara(raiz, perfil, nivel=0):
    nums = sorted(int(m.group(1)) for d in os.listdir(raiz)
                  if (m := re.match(r"rodada-(\d+)$", d)))
    linhas = []
    for n in nums:
        pr = pasta_rodada(raiz, n)
        a = carrega(os.path.join(pr, "a"), perfil, nivel)
        b = carrega(os.path.join(pr, "b"), perfil, nivel)
        linhas.append({"rodada": n, "ordem": "A>B" if n % 2 else "B>A", "a": a, "b": b,
                       "par_valido": bool(a and b and a["_valida"] and b["_valida"])})
    if not linhas:
        return None

    principal, secundaria = [], []
    for chave, rot, cam, div, un, casas, menor in KPIS:
        pares = [r for r in linhas if r["par_valido"]]
        av = [valor(camp(r["a"], "a-mec"), cam) for r in pares]
        bv = [valor(camp(r["b"], "b-mec"), cam) for r in pares]
        difs = [(x - y) / div for x, y in zip(av, bv) if x is not None and y is not None]
        pcts = [(1 - y / x) * 100 for x, y in zip(av, bv) if x and y is not None]
        ma, da = media_dp([x / div for x in av if x is not None])
        mb, db = media_dp([y / div for y in bv if y is not None])
        principal.append({"kpi": chave, "rotulo": rot, "unidade": un, "casas": casas,
                          "a": (ma, da), "b": (mb, db), "dif": pareado(difs),
                          "pct": (sum(pcts) / len(pcts)) if pcts and menor else None,
                          # A mediana resiste a rodada bimodal (a 95% uma fila
                          # que satura numas rodadas e noutras nao).
                          "mediana": statistics.median(difs) if difs else None,
                          "b_melhor": sum(1 for d in difs if d > 0) if menor else None})

        bs = [r for r in linhas if r["b"] and r["b"]["_valida_remoto"]]
        mec = [valor(camp(r["b"], "b-mec"), cam) for r in bs]
        rem = [valor(camp(r["b"], "b-remoto"), cam) for r in bs]
        difs2 = [(y - x) / div for x, y in zip(mec, rem) if x is not None and y is not None]
        pcts2 = [(y / x - 1) * 100 for x, y in zip(mec, rem) if x and y is not None]
        mm, dm = media_dp([x / div for x in mec if x is not None])
        mr, dr = media_dp([y / div for y in rem if y is not None])
        secundaria.append({"kpi": chave, "rotulo": rot, "unidade": un, "casas": casas,
                           "mec": (mm, dm), "remoto": (mr, dr), "dif": pareado(difs2),
                           "pct": (sum(pcts2) / len(pcts2)) if pcts2 and menor else None})
    return {"linhas": linhas, "principal": principal, "secundaria": secundaria}


def tem_remoto(res):
    """So' existe comparacao secundaria se o b-remoto foi medido."""
    return any(camp(r["b"], "b-remoto") for r in res["linhas"])


def n_secundaria(res):
    return sum(1 for r in res["linhas"]
               if r["b"] and r["b"]["_valida_remoto"] and camp(r["b"], "b-remoto"))


SEM_SECUNDARIA = ("Nenhuma execucao do B passou na guarda de perda entre caminhos neste "
                  "nivel. Sob congestao o b-remoto cruza o enlace e perde, o b-mec nao; com "
                  "perdas tao diferentes so' os quadros completos viram amostra, e a "
                  "comparacao entre os dois deixa de valer. O A x B acima nao e' afetado.")


def camp(e, caminho):
    return (e or {}).get("campanha", {}).get(caminho, {})


def cel_k(md, casas):
    m, d = md
    return "-" if m is None else (f"{m:.{casas}f}" if d is None else f"{m:.{casas}f} ± {d:.{casas}f}")


def cel_dif(k):
    d = k["dif"]
    if not d:
        return "-", "-"
    c = k["casas"]
    base = f"{d['media']:+.{c}f}" + ("" if d["dp"] is None else f" ± {d['dp']:.{c}f}")
    ic = "-" if not d["ic"] else f"[{d['ic'][0]:+.{c}f}; {d['ic'][1]:+.{c}f}]"
    return base, ic


def cel_med(k):
    return "-" if k.get("mediana") is None else f"{k['mediana']:+.{k['casas']}f}"


def cel_abaixo(k):
    return "-" if not k["dif"] or k["b_melhor"] is None else f"{k['b_melhor']}/{k['dif']['n']}"


ROTULO_DESCARTE = {"falhou": "falha de infraestrutura", "instrumento": "falha do instrumento",
                   "refeita": "--refazer"}


def descartadas(raiz):
    """Execucoes tiradas do caminho por esta campanha, por motivo."""
    c = {}
    for d in glob.glob(os.path.join(raiz, "rodada-*", "*.*-*")):
        m = re.match(r"[ab]\.(\w+)-\d+$", os.path.basename(d))
        if m and os.path.isdir(d):
            c[m.group(1)] = c.get(m.group(1), 0) + 1
    return c


def linha_de_base(res, faixa=0.25):
    """Rodadas em que o p50 sem fundo fugiu mais de `faixa` da mediana do
    proprio cenario. E' a sentinela de um defeito externo como o de 14-26/09,
    quando o a-mec ficou 5 a 20x mais lento sem nada nosso ter mudado."""
    out = []
    for cen, cam in (("a", "a-mec"), ("b", "b-mec")):
        vs = [(r["rodada"], valor(camp(r[cen], cam), ("net_rtt_us", "p50")))
              for r in res["linhas"] if r[cen] and r[cen]["_valida"]]
        vs = [(n, v / 1000) for n, v in vs if v is not None]
        if len(vs) < 3:
            continue
        m = statistics.median(v for _, v in vs)
        fora = [(n, v) for n, v in vs if abs(v / m - 1) > faixa]
        out.append((cam, m, fora))
    return out


def prova(e, upf):
    try:
        return e["prova"]["mec"]["delta"][upf]["rx_pkts"]
    except (KeyError, TypeError):
        return None


def fundo_cruzou(e):
    f = (e or {}).get("_fundo") or {}
    return f.get("cruzou_mbps")


def args_legado(args, nivel):
    return nivel == 0 and getattr(args, "_legado", True)


def escreve(raiz, perfil, res, args, nivel=0):
    linhas = res["linhas"]
    n_pares = sum(1 for r in linhas if r["par_valido"])
    carga = next((r[c]["_carga"] for r in linhas for c in ("a", "b") if r[c] and r[c].get("_carga")), None)
    caps = [e["_fundo"]["capacidade_mbps"] for r in linhas for e in (r["a"], r["b"])
            if e and e.get("_fundo") and e["_fundo"].get("capacidade_mbps")]

    so_remoto = sum(1 for r in linhas for e in (r["a"], r["b"])
                    if e and e["_valida"] and not e["_valida_remoto"])
    with open(os.path.join(raiz, "a-vs-b.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Campanha A x B - perfil `{perfil}`"
                 + ("" if not nivel else f" - backhaul com fundo a {nivel}%") + "\n\n")
        if carga:
            fh.write(f"**Carga:** {carga['bitrate_mbps']} Mbps @ {carga['fps']} fps (downlink), "
                     f"pose a {carga['pose_hz']} Hz (uplink), MTU {carga['mtu']} B.\n\n")
        if nivel:
            modo = modo_fundo([e["_fundo"] for r in linhas for e in (r["a"], r["b"])
                               if e and e.get("_fundo")])
            fh.write(f"**Fundo no backhaul:** {ORIGEM_FUNDO[modo]}, a {nivel}% da capacidade "
                     "medida no inicio de cada rodada"
                     + (f" (media {sum(caps) / len(caps):.0f} Mbps)" if caps else "")
                     + ". Ligado so' durante a medicao; execucao em que menos de "
                     f"{MIN_FUNDO_ENTREGUE * 100:.0f}% do fundo cruzou o enlace nao vale.\n\n")
            if carga and caps:
                ef = nivel + carga["bitrate_mbps"] / (sum(caps) / len(caps)) * 100
                fh.write(f"**Carga efetiva no A:** no centralizado o downlink da propria aplicacao "
                         f"({carga['bitrate_mbps']} Mbps) desce pelo mesmo enlace que o fundo, "
                         f"entao a carga do enlace durante a medicao do a-mec e' ~{ef:.1f}% da "
                         "capacidade"
                         + (". **Acima de 100%: no A isto e' sobrecarga, nao so' congestao** -- a "
                            "fila fica cheia o tempo todo, o atraso trava no teto do buffer e o "
                            "excesso vira perda." if ef >= 100 else ".")
                         + " No B o b-mec nao cruza o enlace.\n\n")
        deploy = ("Cada cenario sobe do zero e e' derrubado no fim." if args_legado(args, nivel)
                  else "Cada cenario sobe uma vez por rodada e passa por todos os niveis de "
                       "fundo, em ordem rotativa entre as rodadas.")
        fh.write(f"{len(linhas)} rodada(s), ordem alternada (A->B, B->A, ...). {deploy} "
                 f"**Pares validos: {n_pares} de {len(linhas)}** -- um par so' entra se as duas "
                 "execucoes passaram nas guardas de saude do caminho MEC."
                 + (f" {so_remoto} execucao(oes) dispararam so' guardas do caminho remoto: valem "
                    "para o A x B e ficam fora da comparacao b-remoto x b-mec." if so_remoto else "")
                 + "\n\n")
        desc = descartadas(raiz)
        if desc:
            fh.write("**Execucoes refeitas:** "
                     + ", ".join(f"{n} por {ROTULO_DESCARTE.get(m, m)}" for m, n in sorted(desc.items()))
                     + " (pastas `rodada-NN/<a|b>.<motivo>-<k>`, guardadas para diagnostico). "
                     "So' se refaz o que nao mediu; medida que caiu numa guarda de qualidade "
                     "nunca e' refeita.\n\n")
        if not nivel:
            base = linha_de_base(res)
            if base:
                fh.write("**Linha de base (sentinela):** p50 sem fundo, mediana entre rodadas -- "
                         + "; ".join(f"{cam} {m:.3f} ms" + (
                             f", FORA de +-25% nas rodadas {', '.join(f'{n} ({v:.3f})' for n, v in fora)}"
                             if fora else ", todas as rodadas dentro de +-25%")
                                     for cam, m, fora in base)
                         + ". Rodada fora da faixa sem fundo aponta defeito no testbed (como o "
                         "de 14-26/09), nao efeito do LBO: investigar antes de usar.\n\n")

        fh.write("## LBO contra o centralizado (a-mec x b-mec)\n\n")
        fh.write("Mesmo UE, mesmo destino (mec-app na borda), mesma carga: so' a ancora "
                 "do plano de usuario muda. Diferenca = A - B, calculada dentro de cada "
                 "rodada; **positiva = o LBO e' mais rapido**. Valores: media ± "
                 "desvio-padrao entre rodadas.\n\n")
        fh.write("| KPI | A: UPF centralizada | B: dUPF com LBO | A - B (pareado) | IC 95% | "
                 "A - B (mediana) | LBO menor | B abaixo |\n")
        fh.write("|---|---|---|---|---|---|---|---|\n")
        for k in res["principal"]:
            dif, ic = cel_dif(k)
            pct = "-" if k["pct"] is None else f"{k['pct']:.1f}%"
            fh.write(f"| {k['rotulo']} ({k['unidade']}) | {cel_k(k['a'], k['casas'])} | "
                     f"{cel_k(k['b'], k['casas'])} | {dif} | {ic} | {cel_med(k)} | {pct} | "
                     f"{cel_abaixo(k)} |\n")
        p50 = next(k for k in res["principal"] if k["kpi"] == "net_p50")["dif"]
        if p50 and p50["mde"] is not None:
            fh.write(f"\nMenor diferenca detectavel no atraso de rede p50 com {p50['n']} par(es) "
                     f"(alfa 5%, poder 80%): **{p50['mde']:.3f} ms**. Diferencas menores que "
                     "isso nao podem ser afirmadas com esta campanha.\n\n")

        if tem_remoto(res) and not n_secundaria(res):
            fh.write("## Aplicacao fora no cenario B (b-remoto x b-mec)\n\n" + SEM_SECUNDARIA + "\n\n")
        elif tem_remoto(res):
            fh.write("## Aplicacao fora no cenario B (b-remoto x b-mec)\n\n")
            fh.write("Quanto a mais demora quando a aplicacao esta no nucleo, atravessando as "
                     "2 UPFs do cenario B. Diferenca = remoto - MEC, dentro de cada execucao do B "
                     f"({n_secundaria(res)} execucao(oes) sem nenhuma guarda, nem as do remoto).\n\n")
            fh.write("| KPI | B: MEC (LBO) | B: remoto (2 UPFs) | remoto - MEC | IC 95% | a mais fora |\n")
            fh.write("|---|---|---|---|---|---|\n")
            for k in res["secundaria"]:
                dif, ic = cel_dif(k)
                pct = "-" if k["pct"] is None else f"{k['pct']:.1f}%"
                fh.write(f"| {k['rotulo']} ({k['unidade']}) | {cel_k(k['mec'], k['casas'])} | "
                         f"{cel_k(k['remoto'], k['casas'])} | {dif} | {ic} | {pct} |\n")

        fh.write("\n## Prova do mecanismo em cada rodada\n\n")
        fh.write("Pacotes que a UPF de ancoragem viu sob trafego MEC. No A a UPF central "
                 "tem que contar o trafego (trombone); no B o PSA-UPF tem que ficar em zero "
                 "(breakout na borda).\n\n")
        extra = " A: fundo cruzou (Mbps) | B: fundo cruzou (Mbps) |" if nivel else ""
        fh.write("| Rodada | Ordem | A: UPF central sob MEC | B: PSA-UPF sob MEC | A valida | B valida | Par |"
                 + extra + "\n")
        fh.write("|---|---|---|---|---|---|---|" + ("---|---|" if nivel else "") + "\n")
        for r in linhas:
            fh.write(f"| {r['rodada']} | {r['ordem']} | {prova(r['a'], 'upf') if r['a'] else 'falhou'} | "
                     f"{prova(r['b'], 'psa-upf') if r['b'] else 'falhou'} | "
                     f"{'-' if not r['a'] else ('sim' if r['a']['_valida'] else 'nao')} | "
                     f"{'-' if not r['b'] else ('sim' if r['b']['_valida'] else 'nao')} | "
                     f"{'sim' if r['par_valido'] else 'nao'} |"
                     + (f" {fmt(fundo_cruzou(r['a']), 0)} | {fmt(fundo_cruzou(r['b']), 0)} |"
                        if nivel else "") + "\n")

    # So' os caminhos que foram medidos: desde 10/2026 a campanha nao mede o a-remoto.
    caminhos = tuple((cen, cam) for cen, cam in (("a", "a-mec"), ("a", "a-remoto"),
                                                 ("b", "b-mec"), ("b", "b-remoto"))
                     if cam.endswith("mec") or any(camp(r[cen], cam) for r in linhas))
    with open(os.path.join(raiz, "a-vs-b-por-rodada.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rodada", "ordem", "a_valida", "b_valida", "par_valido",
                    "a_upf_rx_sob_mec", "b_psa_rx_sob_mec"]
                   + [f"{cam}_{k[0]}" for _, cam in caminhos for k in KPIS]
                   + ["nivel_fundo_pct", "a_fundo_cruzou_mbps", "b_fundo_cruzou_mbps"])
        for r in linhas:
            row = [r["rodada"], r["ordem"],
                   "" if not r["a"] else int(r["a"]["_valida"]),
                   "" if not r["b"] else int(r["b"]["_valida"]), int(r["par_valido"]),
                   prova(r["a"], "upf") if r["a"] else "", prova(r["b"], "psa-upf") if r["b"] else ""]
            for cen, cam in caminhos:
                resumo = (r[cen] or {}).get("campanha", {}).get(cam, {})
                row += ["" if valor(resumo, k[2]) is None else valor(resumo, k[2]) for k in KPIS]
            row += [nivel, "" if fundo_cruzou(r["a"]) is None else round(fundo_cruzou(r["a"]), 1),
                    "" if fundo_cruzou(r["b"]) is None else round(fundo_cruzou(r["b"]), 1)]
            w.writerow(row)

    with open(os.path.join(raiz, "a-vs-b.json"), "w", encoding="utf-8") as fh:
        json.dump({"perfil": perfil, "nivel_fundo_pct": nivel, "rodadas": len(linhas),
                   "pares_validos": n_pares,
                   "principal": res["principal"], "secundaria": res["secundaria"],
                   "por_rodada": [{"rodada": r["rodada"], "ordem": r["ordem"],
                                   "a_valida": bool(r["a"] and r["a"]["_valida"]),
                                   "b_valida": bool(r["b"] and r["b"]["_valida"]),
                                   "b_valida_remoto": bool(r["b"] and r["b"]["_valida_remoto"]),
                                   "par_valido": r["par_valido"],
                                   "a_fundo": (r["a"] or {}).get("_fundo"),
                                   "b_fundo": (r["b"] or {}).get("_fundo")} for r in linhas]},
                  fh, indent=2)
    return n_pares


def imprime(res, n_pares):
    print(f"\n{'=' * 72}\nLBO contra o centralizado (a-mec x b-mec) -- {n_pares} par(es) valido(s)\n{'=' * 72}")
    print(f"  {'KPI':<26}{'A: centralizado':>18}{'B: LBO':>18}{'A - B':>14}{'IC 95%':>22}")
    for k in res["principal"]:
        dif, ic = cel_dif(k)
        print(f"  {k['rotulo'] + ' (' + k['unidade'] + ')':<26}{fmt(k['a'][0], k['casas']):>18}"
              f"{fmt(k['b'][0], k['casas']):>18}{dif.split(' ')[0]:>14}{ic:>22}")
    if not tem_remoto(res):
        return
    print(f"\n{'=' * 72}\nAplicacao fora no cenario B (b-remoto x b-mec)\n{'=' * 72}")
    if not n_secundaria(res):
        print("  " + SEM_SECUNDARIA)
        return
    print(f"  {'KPI':<26}{'B: MEC':>18}{'B: remoto':>18}{'remoto - MEC':>14}{'IC 95%':>22}")
    for k in res["secundaria"]:
        dif, ic = cel_dif(k)
        print(f"  {k['rotulo'] + ' (' + k['unidade'] + ')':<26}{fmt(k['mec'][0], k['casas']):>18}"
              f"{fmt(k['remoto'][0], k['casas']):>18}{dif.split(' ')[0]:>14}{ic:>22}")


# --------------------------------------------------------------------------
# o destaque: LBO sob congestao, atravessando os niveis
# --------------------------------------------------------------------------
def kpi_def(chave):
    return next(k for k in KPIS if k[0] == chave)


def compara_niveis(por_nivel, niveis):
    """Junta os niveis rodada a rodada.

    ganho      A - B em cada nivel (o mesmo numero do a-vs-b.md daquele nivel,
               mais em quantas rodadas o B ficou abaixo)
    custo      quanto cada cenario piorou do sem-fundo para o nivel, DENTRO da
               mesma rodada e do mesmo deploy
    poupado    (piora do A) - (piora do B) na mesma rodada: o quanto da
               congestao o centralizado absorve e o LBO nao. E' a estatistica
               que responde "o LBO isola a aplicacao do backhaul?"."""
    ganho, custo = [], []
    for nv in niveis:
        res = por_nivel.get(nv)
        if not res:
            continue
        for k in res["principal"]:
            if k["kpi"] in KPIS_DESTAQUE:
                ganho.append({"nivel": nv, **k})
    base = por_nivel.get(0)
    if base:
        por_rodada0 = {r["rodada"]: r for r in base["linhas"]}
        for nv in niveis:
            if nv == 0 or nv not in por_nivel:
                continue
            for chave in KPIS_DESTAQUE:
                _, rot, cam, div, un, casas, _ = kpi_def(chave)
                piora = {"a": [], "b": []}
                poupado = []
                for r in por_nivel[nv]["linhas"]:
                    r0 = por_rodada0.get(r["rodada"])
                    if not r0:
                        continue
                    d = {}
                    for cen, caminho in (("a", "a-mec"), ("b", "b-mec")):
                        e, e0 = r[cen], r0[cen]
                        if e and e0 and e["_valida"] and e0["_valida"]:
                            x, x0 = valor(camp(e, caminho), cam), valor(camp(e0, caminho), cam)
                            if x is not None and x0 is not None:
                                d[cen] = (x - x0) / div
                                piora[cen].append(d[cen])
                    if "a" in d and "b" in d:
                        poupado.append(d["a"] - d["b"])
                custo.append({"nivel": nv, "kpi": chave, "rotulo": rot, "unidade": un,
                              "casas": casas, "piora_a": pareado(piora["a"]),
                              "piora_b": pareado(piora["b"]), "poupado": pareado(poupado)})
    return {"ganho": ganho, "custo": custo}


def cel_p(d, casas, com_ic=False):
    if not d:
        return "-"
    s = f"{d['media']:+.{casas}f}" + ("" if d["dp"] is None else f" ± {d['dp']:.{casas}f}")
    if com_ic and d["ic"]:
        s += f" [{d['ic'][0]:+.{casas}f}; {d['ic'][1]:+.{casas}f}]"
    return s


def escreve_destaque(saida, perfil, por_nivel, niveis, dest):
    nome = f"lbo-sob-congestao-{perfil}"
    todas = [r for nv in niveis if por_nivel.get(nv) for r in por_nivel[nv]["linhas"]]
    carga = next((e["_carga"] for r in todas for e in (r["a"], r["b"]) if e and e.get("_carga")), None)
    fundos = [e["_fundo"] for r in todas for e in (r["a"], r["b"]) if e and e.get("_fundo")]
    caps = [f["capacidade_mbps"] for f in fundos if f.get("capacidade_mbps")]
    rodadas_n = sorted({r["rodada"] for r in todas})
    modo = modo_fundo(fundos)

    with open(os.path.join(saida, nome + ".md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Local Breakout sob congestao do backhaul - perfil `{perfil}`\n\n")
        fh.write("**A pergunta.** No cenario centralizado (A), o trafego da aplicacao MEC sai "
                 "da borda, vai ate' a UPF no nucleo e volta: atravessa o enlace nuvem -> borda "
                 "**duas vezes**. Com Local Breakout (B), ele sai na propria borda e nao "
                 "atravessa **nenhuma**. O que acontece com cada um quando esse enlace "
                 "congestiona?\n\n")
        fh.write(f"**Como foi medido.** {len(rodadas_n)} rodada(s), ordem A/B alternada. Em cada "
                 "rodada os dois cenarios passam pelos mesmos niveis de trafego de fundo: "
                 + ORIGEM_FUNDO[modo] + ", a "
                 + " e ".join(", ".join(f"{nv}%" for nv in niveis if nv).rsplit(", ", 1))
                 + " da capacidade medida no inicio da rodada"
                 + (f" (media {sum(caps) / len(caps):.0f} Mbps)" if caps else "") + ". "
                 "Diferencas calculadas dentro da rodada antes de agregar.")
        if carga:
            fh.write(f" Carga da aplicacao: {carga['bitrate_mbps']} Mbps @ {carga['fps']} fps "
                     f"no downlink, pose a {carga['pose_hz']} Hz.")
        fh.write("\n\n")

        fh.write("## 1. O ganho do LBO em cada nivel de congestao (a-mec x b-mec)\n\n")
        fh.write("A - B pareado dentro da rodada: **positivo = o LBO e' mais rapido**. "
                 "\"B abaixo\" conta em quantas rodadas o B ficou abaixo do A. Valores: media ± "
                 "desvio-padrao entre rodadas.\n\n")
        fh.write("| Backhaul | KPI | A: centralizada | B: LBO | A - B (pareado) | IC 95% | "
                 "A - B (mediana) | LBO menor | B abaixo |\n")
        fh.write("|---|---|---|---|---|---|---|---|---|\n")
        for nv in niveis:
            linhas_nv = [g for g in dest["ganho"] if g["nivel"] == nv]
            for i, g in enumerate(linhas_nv):
                dif, ic = cel_dif(g)
                pct = "-" if g["pct"] is None else f"{g['pct']:.1f}%"
                ab = "-" if not g["dif"] or g["b_melhor"] is None else f"{g['b_melhor']}/{g['dif']['n']}"
                fh.write(f"| {'**' + rotulo_nivel(nv) + '**' if i == 0 else ''} | "
                         f"{g['rotulo']} ({g['unidade']}) | {cel_k(g['a'], g['casas'])} | "
                         f"{cel_k(g['b'], g['casas'])} | {dif} | {ic} | {cel_med(g)} | {pct} | {ab} |\n")

        if dest["custo"]:
            fh.write("\n## 2. Quanto a congestao custa a cada cenario\n\n")
            fh.write("Diferenca contra o nivel sem fundo, dentro da MESMA rodada e do MESMO "
                     "deploy (media ± desvio-padrao). A ultima coluna e' o que o LBO poupa: "
                     "quanto o centralizado piora **a mais** que o LBO, com IC 95%. Se o "
                     "intervalo nao cruza o zero, a diferenca e' afirmavel com esta campanha.\n\n")
            fh.write("| Backhaul | KPI | A piora | B piora | A piora a mais que B [IC 95%] |\n")
            fh.write("|---|---|---|---|---|\n")
            for nv in niveis:
                linhas_nv = [c for c in dest["custo"] if c["nivel"] == nv]
                for i, c in enumerate(linhas_nv):
                    fh.write(f"| {'**' + rotulo_nivel(nv) + '**' if i == 0 else ''} | "
                             f"{c['rotulo']} ({c['unidade']}) | {cel_p(c['piora_a'], c['casas'])} | "
                             f"{cel_p(c['piora_b'], c['casas'])} | "
                             f"{cel_p(c['poupado'], c['casas'], com_ic=True)} |\n")

        fh.write("\n## 3. Validade por nivel\n\n")
        fh.write("| Backhaul | Rodadas | Pares validos | Fundo pedido (Mbps) | Fundo que cruzou o enlace (Mbps) |\n")
        fh.write("|---|---|---|---|---|\n")
        for nv in niveis:
            res = por_nivel.get(nv)
            if not res:
                continue
            fs = [e["_fundo"] for r in res["linhas"] for e in (r["a"], r["b"]) if e and e.get("_fundo")]
            ped = media_dp([f.get("pedido_mbps") for f in fs])
            cru = media_dp([f.get("cruzou_mbps") for f in fs])
            fh.write(f"| {rotulo_nivel(nv)} | {len(res['linhas'])} | "
                     f"{sum(1 for r in res['linhas'] if r['par_valido'])} | "
                     f"{cel_k(ped, 0) if nv else '-'} | {cel_k(cru, 0) if nv else '-'} |\n")
        fh.write("\nTabelas completas (todos os KPIs e prova do mecanismo por rodada) em `" + "`, `".join(f"{nome_nivel(nv)}/{perfil}/a-vs-b.md" for nv in niveis)
                 + "`.\n\n")

        fh.write("## Limitacoes a declarar\n\n")
        fh.write("- O fundo e' UDP com taxa fixa. Trafego real e' majoritariamente TCP/QUIC, que "
                 "recua sob perda; os niveis ficam abaixo de 100% para nao transformar congestao "
                 "em sobrecarga continua.\n")
        fh.write("- O transporte do testbed nao tem QoS: numa operadora, trafego de baixa latencia "
                 "e plano de controle iriam em filas prioritarias, o que reduziria o dano ao "
                 "centralizado.\n")
        fh.write("- O backhaul do testbed tem ~20 us de propagacao; num nucleo regional a "
                 "distancia soma alguns ms que aqui nao aparecem e que tambem pesam contra o "
                 "centralizado.\n")
        if modo == "gtp":
            fh.write("- O fundo e' trafego de assinante e passa pela UPF de ancoragem. No A ela e' "
                     "a MESMA UPF central do experimento, entao a piora do A soma congestao do "
                     "backhaul e carga na UPF compartilhada -- como num nucleo real. O UE de "
                     "ruido e' de outra fatia (1/112233), sem LBO, numa segunda celula.\n")
            fh.write("- O UERANSIM nao absorve a taxa do fundo (50-100 Mbps por sessao): o "
                     "excedente e' descartado no pod de ruido DEPOIS de cruzar o enlace. O "
                     "enlace ve a carga inteira; o UE de ruido recebe uma fracao dela.\n")
        else:
            fh.write("- O fundo nao passa pelas UPFs: mede a congestao do transporte, nao a carga de "
                     "outros usuarios sobre o plano de usuario.\n")
        fh.write("- O enlace e' da rede da universidade; trafego de terceiros entra como ruido, "
                 "que o pareamento por rodada e a ordem alternada ajudam a cancelar.\n")

    with open(os.path.join(saida, nome + ".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rodada", "nivel_fundo_pct", "a_valida", "b_valida", "par_valido",
                    "capacidade_mbps", "a_fundo_cruzou_mbps", "b_fundo_cruzou_mbps"]
                   + [f"{cam}_{k}" for cam in ("a-mec", "b-mec") for k in KPIS_DESTAQUE])
        for nv in niveis:
            for r in (por_nivel.get(nv) or {}).get("linhas", []):
                fa, fb = (r["a"] or {}).get("_fundo") or {}, (r["b"] or {}).get("_fundo") or {}
                row = [r["rodada"], nv, "" if not r["a"] else int(r["a"]["_valida"]),
                       "" if not r["b"] else int(r["b"]["_valida"]), int(r["par_valido"]),
                       fa.get("capacidade_mbps") or fb.get("capacidade_mbps") or "",
                       fa.get("cruzou_mbps") or "", fb.get("cruzou_mbps") or ""]
                for cen, cam in (("a", "a-mec"), ("b", "b-mec")):
                    for chave in KPIS_DESTAQUE:
                        v = valor(camp(r[cen], cam), kpi_def(chave)[2])
                        row.append("" if v is None else v)
                w.writerow(row)

    with open(os.path.join(saida, nome + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"perfil": perfil, "niveis_fundo_pct": niveis, "rodadas": rodadas_n,
                   "ganho": dest["ganho"], "custo": dest["custo"]}, fh, indent=2)
    return nome


def imprime_destaque(niveis, dest):
    print(f"\n{'=' * 72}\nLOCAL BREAKOUT SOB CONGESTAO DO BACKHAUL (a-mec x b-mec)\n{'=' * 72}")
    print(f"  {'backhaul':<10}{'KPI':<24}{'A: central':>12}{'B: LBO':>12}{'A - B':>10}"
          f"{'IC 95%':>22}{'B abaixo':>10}")
    for nv in niveis:
        for i, g in enumerate(x for x in dest["ganho"] if x["nivel"] == nv):
            dif, ic = cel_dif(g)
            ab = "-" if not g["dif"] or g["b_melhor"] is None else f"{g['b_melhor']}/{g['dif']['n']}"
            print(f"  {rotulo_nivel(nv) if i == 0 else '':<10}{g['rotulo'] + ' (' + g['unidade'] + ')':<24}"
                  f"{fmt(g['a'][0], g['casas']):>12}{fmt(g['b'][0], g['casas']):>12}"
                  f"{dif.split(' ')[0]:>10}{ic:>22}{ab:>10}")
    if dest["custo"]:
        print("\n  quanto a congestao custa (contra o sem fundo, na mesma rodada)")
        print(f"  {'backhaul':<10}{'KPI':<24}{'A piora':>12}{'B piora':>12}"
              f"   A piora a mais que B [IC 95%]")
        for c in dest["custo"]:
            pa, pb = c["piora_a"], c["piora_b"]
            print(f"  {rotulo_nivel(c['nivel']):<10}{c['rotulo'] + ' (' + c['unidade'] + ')':<24}"
                  f"{fmt(pa['media'] if pa else None, c['casas']):>12}"
                  f"{fmt(pb['media'] if pb else None, c['casas']):>12}"
                  f"   {cel_p(c['poupado'], c['casas'], com_ic=True)}")


# --------------------------------------------------------------------------
def niveis_em(pasta):
    """Niveis gravados numa raiz de campanha com fundo (sem-fundo, fundo-80...)."""
    achados = []
    for d in os.listdir(pasta):
        if d == "sem-fundo":
            achados.append(0)
        elif (m := re.match(r"fundo-(\d+)$", d)):
            achados.append(int(m.group(1)))
    return sorted(achados)


# --------------------------------------------------------------------------
# registro da campanha (reprodutibilidade)
# --------------------------------------------------------------------------
class Tee:
    """Copia tudo o que a campanha imprime para um arquivo, sem as cores."""

    def __init__(self, fluxo, fh):
        self.fluxo, self.fh = fluxo, fh

    def write(self, s):
        self.fluxo.write(s)
        if not self.fh.closed:
            self.fh.write(re.sub(r"\x1b\[[0-9;]*m", "", s))
        return len(s)

    def flush(self):
        self.fluxo.flush()
        if not self.fh.closed:
            self.fh.flush()

    def __getattr__(self, nome):
        return getattr(self.fluxo, nome)


def saida_de(cmd, cwd=None, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def versao_git():
    commit = saida_de(["git", "rev-parse", "HEAD"], cwd=BASE)
    if not commit:
        return None
    alterados = saida_de(["git", "status", "--porcelain", "--", "."], cwd=BASE) or ""
    return {"commit": commit, "alterados": [l[3:] for l in alterados.splitlines()][:50]}


def versao_kubectl():
    try:
        j = json.loads(saida_de(["kubectl", "version", "-o", "json"]) or "")
    except ValueError:
        return None
    return {k: (j.get(k) or {}).get("gitVersion") for k in ("clientVersion", "serverVersion")}


def abre_registro(saida, args, perfis, niveis):
    """campanha-<inicio>.json e campanha-<inicio>.log na raiz da campanha. Cada
    vez que o comando roda (retomadas inclusive) gera um par novo."""
    base = os.path.join(saida, f"campanha-{time.strftime('%Y%m%d-%H%M%S')}")
    reg = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "fim": None,
           "comando": [os.path.basename(sys.argv[0])] + sys.argv[1:],
           "args": {k: v for k, v in vars(args).items() if not k.startswith("_")},
           "perfis": perfis, "niveis_fundo_pct": niveis,
           "python": sys.version.split()[0], "plataforma": platform.platform(),
           "git": versao_git(), "kubectl": versao_kubectl(), "resultado": None}
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2)
    log = open(base + ".log", "w", encoding="utf-8", buffering=1)
    sys.stdout, sys.stderr = Tee(sys.stdout, log), Tee(sys.stderr, log)
    print(f"  registro deste comando: {os.path.basename(base)}.json e .log")
    return base, reg, log


def fecha_registro(base, reg, log, resultado):
    reg.update(fim=time.strftime("%Y-%m-%dT%H:%M:%S%z"), resultado=resultado)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2)
    for nome in ("stdout", "stderr"):
        fluxo = getattr(sys, nome)
        fluxo.flush()
        if isinstance(fluxo, Tee):
            setattr(sys, nome, fluxo.fluxo)
    log.close()


def mantem_acordado():
    """Campanha de dias sem ninguem olhando: o computador nao pode dormir no
    meio. Vale so' enquanto este processo existir."""
    if os.name == "nt":
        try:
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except (AttributeError, OSError):
            pass
    elif shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def relatorio(args, saida, perfil, niveis, legado, t0):
    """Compara e grava os relatorios de UM perfil. Devolve o codigo de saida."""
    por_nivel, pares, totais = {}, {}, {}
    for nv in niveis:
        raiz = raiz_nivel(saida, perfil, nv, legado)
        res = compara(raiz, perfil, nv) if os.path.isdir(raiz) else None
        if not res:
            continue
        por_nivel[nv] = res
        pares[nv] = escreve(raiz, perfil, res, args, nv)
        totais[nv] = len(res["linhas"])
    if not por_nivel:
        print(f"\n{VERM}CAMPANHA A x B NAO CONCLUIDA{RESET} ({perfil}) -- nenhuma rodada em {saida}")
        return 1

    if legado:
        imprime(por_nivel[0], pares[0])
        print(f"\n  Arquivos em {raiz_nivel(saida, perfil, 0, True)}: a-vs-b.md, "
              "a-vs-b-por-rodada.csv, a-vs-b.json")
    else:
        dest = compara_niveis(por_nivel, niveis)
        nome = escreve_destaque(saida, perfil, por_nivel, niveis, dest)
        imprime_destaque(niveis, dest)
        print(f"\n  Destaque em {saida}: {nome}.md, .csv, .json")
        print("  Tabelas completas por nivel: "
              + ", ".join(f"{nome_nivel(nv)}/{perfil}/a-vs-b.md" for nv in por_nivel))

    tempo = f"{time.time() - t0:.0f}s"
    if legado:
        n_pares, total = pares[0], totais[0]
        if n_pares == 0:
            print(f"\n{VERM}CAMPANHA A x B SEM PAR VALIDO{RESET} ({perfil}) -- {total} rodada(s), "
                  f"nenhuma com A e B validos ({tempo})")
            return 1
        if n_pares < total:
            print(f"\n{AMAR}CAMPANHA A x B COM FALHAS{RESET} ({perfil}) -- {n_pares} de {total} "
                  f"rodada(s) com par valido ({tempo})")
            return 1
        print(f"\n{VERDE}CAMPANHA A x B CONCLUIDA{RESET} ({perfil}) -- {n_pares} par(es) valido(s) ({tempo})")
        return 0
    resumo = ", ".join(f"{rotulo_nivel(nv)} {pares[nv]}/{totais[nv]}" for nv in por_nivel)
    if not any(pares.values()):
        print(f"\n{VERM}CAMPANHA A x B SEM PAR VALIDO{RESET} ({perfil}) -- pares validos: {resumo} ({tempo})")
        return 1
    faltando = [nv for nv in niveis if nv not in por_nivel]
    if any(pares[nv] < totais[nv] for nv in por_nivel) or faltando:
        print(f"\n{AMAR}CAMPANHA A x B COM FALHAS{RESET} ({perfil}) -- pares validos: {resumo}"
              + (f"; sem resultado: {', '.join(rotulo_nivel(nv) for nv in faltando)}" if faltando else "")
              + f" ({tempo})")
        return 1
    print(f"\n{VERDE}CAMPANHA A x B CONCLUIDA{RESET} ({perfil}) -- pares validos: {resumo} ({tempo})")
    return 0


def main():
    global R
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rodadas", type=int, default=5, metavar="N",
                    help="quantas rodadas A+B por perfil (default: 5)")
    ap.add_argument("--perfil", default=None, metavar="PERFIS",
                    help="perfil de carga, o mesmo nome aceito pelos dois scripts, ou uma lista "
                         "separada por virgula, rodada um perfil inteiro de cada vez, na ordem "
                         "dada (ex.: vr-cloud,vr-extremo,teleoperacao). Default: vr-cloud; com "
                         "--so-comparar, todos os perfis da pasta")
    ap.add_argument("--fundo", default="0,80,95", metavar="PCTS",
                    help="niveis de trafego de fundo no backhaul, em %% da capacidade medida, "
                         "de 0 a 99 (default: 0,80,95). Ex.: --fundo 0,99 so' sem fundo e 99%%; "
                         "--fundo 0 e' a campanha sem congestao")
    ap.add_argument("--ruido", choices=("gtp", "direto"), default="gtp",
                    help="de onde vem o fundo: gtp (padrao) pelo tunel GTP-U ate' o UERANSIM "
                         "de ruido no brix-porvir-03 (congestao/ruido-gtp.yaml); direto: "
                         "iperf3 ate' o brix-porvir-04 sem passar por UPF (campanha de 16/09)")
    ap.add_argument("--com-remoto", action="store_true",
                    help="mede tambem o b-remoto (default: so' a-mec e b-mec). O a-remoto nao "
                         "e' medido pela campanha")
    ap.add_argument("--duracao", type=float, default=60)
    ap.add_argument("--warmup", type=float, default=5)
    ap.add_argument("--prova-duracao", type=float, default=10)
    ap.add_argument("--duracao-capacidade", type=int, default=10, metavar="S",
                    help="segundos do iperf3 TCP que mede a capacidade a cada rodada")
    ap.add_argument("--carregar-assinantes", type=int, default=0, metavar="N")
    ap.add_argument("--tentativas", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--conciso", action="store_true")
    ap.add_argument("--rodada-inicial", type=int, default=1, metavar="N",
                    help="comeca na rodada N em vez da 1, em todos os perfis (default: 1); as "
                         "rodadas anteriores nao sao tocadas, mas continuam entrando na comparacao")
    ap.add_argument("--refazer", action="store_true",
                    help="mede de novo mesmo o que ja' tem resultado")
    ap.add_argument("--sem-repetir", dest="repetir_falhas", action="store_false",
                    help="nao refaz a execucao que nao concluiu ou em que o fundo nao foi "
                         "aplicado (default: refaz uma vez, no fim da rodada)")
    ap.add_argument("--saida", default=None,
                    help="raiz (default: resultados-a-vs-b-ruido-gtp com --ruido gtp, "
                         "resultados-a-vs-b-congestao com --ruido direto, "
                         "resultados-a-vs-b com --fundo 0)")
    ap.add_argument("--so-comparar", metavar="PASTA",
                    help="nao roda nada: so' compara o que ja' esta' gravado. Com fundo, a "
                         "raiz (ex.: resultados-a-vs-b-congestao); sem fundo, a pasta do perfil "
                         "(ex.: resultados-a-vs-b/teleoperacao)")
    args = ap.parse_args()

    try:
        niveis = sorted({int(x) for x in args.fundo.split(",") if x.strip()})
    except ValueError:
        ap.error("--fundo aceita inteiros separados por virgula, ex.: 0,80,95")
    if not niveis or min(niveis) < 0 or max(niveis) >= 100:
        ap.error("--fundo: cada nivel em [0, 100) -- nada acima da capacidade")
    pedidos = list(dict.fromkeys(p.strip() for p in (args.perfil or "").split(",") if p.strip()))

    t0 = time.time()
    registro, parada = None, None
    if args.so_comparar:
        pasta = os.path.abspath(args.so_comparar)
        if not os.path.isdir(pasta):
            ap.error(f"nao existe: {pasta}")
        achados = niveis_em(pasta)
        if achados:
            niveis, legado, saida = achados, False, pasta
            sub = os.path.join(pasta, nome_nivel(niveis[0]))
            encontrados = sorted(d for d in os.listdir(sub) if os.path.isdir(os.path.join(sub, d)))
            faltam = [p for p in pedidos if p not in encontrados]
            if faltam:
                ap.error(f"sem resultado de {', '.join(faltam)} em {pasta} "
                         f"(encontrados: {', '.join(encontrados)})")
            perfis = pedidos or encontrados
            if not perfis:
                ap.error(f"nenhum perfil em {sub}")
        else:
            niveis, legado = [0], True
            perfis = [os.path.basename(pasta)]
            saida = os.path.dirname(pasta)
    else:
        if args.rodadas < 1:
            ap.error("--rodadas precisa ser >= 1")
        if args.rodada_inicial < 1:
            ap.error("--rodada-inicial precisa ser >= 1")
        if args.rodada_inicial > args.rodadas:
            ap.error(f"--rodada-inicial {args.rodada_inicial} e' maior que --rodadas "
                     f"{args.rodadas}: nao ha' rodada para medir")
        perfis = pedidos or ["vr-cloud"]
        # Nome errado tem que parar AGORA, e nao horas depois, quando a campanha
        # chegar no perfil.
        conhecidos = getattr(teste("a"), "PERFIS", {})
        errados = [p for p in perfis if p not in conhecidos]
        if errados:
            ap.error(f"perfil desconhecido: {', '.join(errados)} "
                     f"(existentes: {', '.join(sorted(conhecidos))})")
        legado = niveis == [0]
        if not legado and 0 not in niveis:
            ap.error("--fundo precisa incluir 0: sem o nivel sem fundo nao ha' contra o que "
                     "medir quanto a congestao custa a cada cenario")
        saida = args.saida or os.path.join(
            BASE, "resultados-a-vs-b" if legado else SAIDA_PADRAO[args.ruido])
        if not legado and args.ruido == "gtp":
            R = carrega_ruido()
        existentes = [] if legado or not os.path.isdir(saida) else niveis_em(saida)
        if existentes and existentes != niveis:
            # Misturar niveis de campanhas diferentes quebra o pareamento: o
            # "sem fundo" ja' gravado foi medido em OUTRO deploy, outro dia, e a
            # retomada o pularia. Campanha com outros niveis vai para outra pasta.
            if args.saida:
                ap.error(f"{saida} ja' tem uma campanha com os niveis "
                         f"{', '.join(rotulo_nivel(x) for x in existentes)}. Os niveis pedidos "
                         "sao outros: use outra --saida para nao misturar deploys diferentes")
            saida = f"{saida}-{'-'.join(str(x) for x in niveis)}"
            print(f"{AMAR}a pasta padrao ja' tem outra campanha "
                  f"({', '.join(rotulo_nivel(x) for x in existentes)}); esta vai para "
                  f"{os.path.relpath(saida, BASE)}{RESET}")
        for perfil in perfis:
            for nv in niveis:
                os.makedirs(raiz_nivel(saida, perfil, nv, legado), exist_ok=True)
        registro = abre_registro(saida, args, perfis, niveis)
        mantem_acordado()
        livre = shutil.disk_usage(saida).free
        if livre < 2 << 30:
            print(f"  {AMAR}aviso{RESET}: so' {livre / 2 ** 30:.1f} GB livres em {saida}; uma "
                  "campanha completa com CSV por quadro ocupa algumas centenas de MB")
        if not (registro[1].get("kubectl") or {}).get("serverVersion"):
            print(f"  {AMAR}aviso{RESET}: o kubectl nao respondeu com a versao do cluster em 20 s. "
                  "Se o cluster estiver fora do alcance, o primeiro deploy vai falhar.")
        _capacidades.extend(capacidades_gravadas(saida))
        try:
            ip_srv = prepara_fundo(args, niveis, legado, perfis)
            for i, perfil in enumerate(perfis, 1):
                if len(perfis) > 1:
                    print(f"\n{'=' * 72}\n= PERFIL {i} de {len(perfis)}: {perfil}\n{'=' * 72}")
                rodadas(args, saida, niveis, legado, perfil, ip_srv)
        except KeyboardInterrupt:
            parada = "interrompida"
            print(f"\n{AMAR}interrompido{RESET}: rode o mesmo comando para continuar de onde parou",
                  file=sys.stderr)
        except ErroFundo as e:
            parada = "fundo"
            print(f"\n{VERM}CAMPANHA PARADA: problema no trafego de fundo{RESET}\n  {e}",
                  file=sys.stderr)
        except ErroInstrumento as e:
            parada = "instrumento"
            print(f"\n{VERM}CAMPANHA PARADA: problema no instrumento de medida{RESET}\n  {e}",
                  file=sys.stderr)

    args._legado = legado
    codigos = {}
    for perfil in perfis:
        if len(perfis) > 1:
            print(f"\n{'#' * 72}\n# RESULTADO: {perfil}\n{'#' * 72}")
        codigos[perfil] = relatorio(args, saida, perfil, niveis, legado, t0)
    codigo = max([*codigos.values(), 1 if parada else 0])
    if registro:
        fecha_registro(*registro, {"parada": parada, "codigo_por_perfil": codigos,
                                   "codigo": codigo})
    return codigo


if __name__ == "__main__":
    sys.exit(main())
