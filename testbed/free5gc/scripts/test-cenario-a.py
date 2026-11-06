#!/usr/bin/env python3
"""
Teste fim-a-fim do CENARIO A (UPF centralizada -- o baseline do TG1) no free5gc v4.2.3.
E' o test-cenario-b.py adaptado ao cenario A: mesmos parametros, perfis,
campanha, guardas de saude e formato de relatorio, para os resultados dos dois
cenarios serem comparaveis (a-mec x b-mec: mesmo destino, ancora em outro lugar).

Roda a cadeia inteira, na ordem em que cada passo depende do anterior, e para
no primeiro que falhar -- porque seguir adiante so' produz sintoma derivado:

    1. ferramentas e conexao com o cluster
    2. validate.py (consistencia estatica dos manifestos)
    3. deploy do cenario A                        (opcional, --deploy)
    4. pods prontos
    5. placement: onde cada peca caiu de fato
    6. carga de assinantes no Mongo               (opcional, --carregar-assinantes)
    7. associacao PFCP com a UPF central
    8. tester UERANSIM no ar (replicas vem do manifesto)
    9. sessao PDU com IP no pool da UPF central
   10. rota dos destinos por dentro do tunel do UE
   11. PROVA DA ANCORAGEM CENTRAL: a UPF central conta o trafego MEC e o remoto
   12. campanha de medicao VR (a-mec x a-remoto)
   13. coleta dos resultados
   14. derrubada dos deployments/statefulset      (quando este script subiu)

O passo 11 e' o que define o cenario: no cenario A nao ha breakout, entao a UPF
central tem que contar os DOIS trafegos -- o do mec-app inclusive, que sai da
borda, sobe o backhaul ate' o nucleo e volta (o "trombone" que o cenario B elimina).

COMO A MEDIDA SE DEFENDE (passo 12)

    Ordem alternada.   A cada execucao os dois caminhos trocam de lugar na
                       fila. Medir sempre o MEC primeiro faria qualquer deriva
                       ao longo da execucao virar diferenca entre caminhos.

    Ganho pareado.     A diferenca e' calculada DENTRO de cada execucao e so'
                       depois agregada. O que varia entre execucoes (deploy
                       novo, cluster em outro estado) e' comum as duas corridas
                       e se cancela, em vez de engordar a barra de erro.

    Guardas de saude.  Uma corrida so' entra na tabela se mediu a REDE: o
                       gerador sustentou a cadencia (frames_late), conseguiu
                       entregar os pacotes ao kernel (send_dropped), o kernel
                       do cliente nao descartou nada por fila cheia
                       (SO_RXQ_OVFL), o relogio nao levou passo de NTP, e os
                       DOIS caminhos perderam quantidades parecidas -- so'
                       frame completo vira amostra de latencia, entao perdas
                       muito diferentes tornam os percentis incomparaveis.

    Perda exata.       O denominador vem do contador do servidor (pacotes de
                       fato entregues ao kernel), nao do intervalo de sequencia
                       que o cliente conseguiu observar.

CAMPANHA DE 10 EXECUCOES (o que gera a tabela do TG):

    python3 scripts/test-cenario-a.py --repeticoes 10 --carregar-assinantes 5

Cada execucao sobe o cenario do zero, mede, coleta e DERRUBA os deployments e
o StatefulSet antes da seguinte -- e' o que torna as 10 repeticoes independentes
em vez de 10 medidas do mesmo core quente. O namespace nunca e' tocado: ele ja'
existe, nao pertence ao experimento e a remocao e' sempre por NOME de recurso,
nunca 'delete -f' nem '--all'.

Ao final sai a tabela agregada (media +- desvio-padrao entre execucoes) e, em
resultados-a/:

    tabela-kpis.md            tabela pronta para colar no texto
    resumo-por-execucao.csv   uma linha por (execucao, caminho) -- para boxplot
    kpis-agregados.csv        a mesma tabela em CSV
    campanha.json             tudo em bruto, inclusive execucoes descartadas
    run-01/ ... run-10/       CSV por frame e JSON de resumo de cada execucao

Uso tipico (testbed ja' no ar, uma execucao, sem derrubar nada):

    python3 scripts/test-cenario-a.py

Uma execucao do zero, subindo o cenario e populando o Mongo:

    python3 scripts/test-cenario-a.py --deploy --carregar-assinantes 5

So' derrubamos o que nos mesmos subimos: sem --deploy e sem --repeticoes>1 o
script nao apaga nada, para nao levar junto um testbed que ja' estava de pe'.

So' a prova da ancoragem central, sem campanha de medicao (rapido, ~1 min):

    python3 scripts/test-cenario-a.py --so-prova

Acompanhando passo a passo (para em cada etapa esperando enter):

    python3 scripts/test-cenario-a.py -p

Rode de dentro de implementacoes/free5gc/ ou de qualquer lugar: os caminhos
sao resolvidos a partir da localizacao deste arquivo.
"""
import argparse
import ipaddress
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import traceback
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NS = "free5gc"
# ClusterIPs DINAMICOS (o k8s aloca; o mec-af anuncia o do mec-app ao NEF).
# Resolvidos em p10_rotas() com 'kubectl get svc'.
MEC_IP = None
REMOTE_IP = None
VR_PORT = 9100
TESTER_STS = "free5gc-ueransim"
TESTER_POD = "free5gc-ueransim-0"
TUN = "uesimtun0"
GTP_IF = "upfgtp"          # interface criada pelo gtp5g dentro do pod do UPF
UE_POOL_PREFIX = "60.60."          # pool da UPF central (60.60.0.0/17 na slice 010203)
IMSI_PRINCIPAL = "imsi-208930000000000"   # casa com o supi do tester/ueransim.yaml

# Deployments que o cenario A exige no ar. Nomes conferidos com os manifestos.
DEPLOYS = [
    "free5gc-mongodb", "free5gc-nrf", "free5gc-amf", "free5gc-ausf",
    "free5gc-nssf", "free5gc-pcf", "free5gc-nef", "free5gc-udm", "free5gc-udr",
    "free5gc-smf",
    "free5gc-webui",   # o passo 6 depende dele: o tenantId nasce no boot do webui
    "free5gc-upf", "free5gc-mec-app", "free5gc-remote-app",
    "mec-af",          # no ar como no cenario B, para o ambiente ser o mesmo
]

# Deployments exclusivos do cenario B. Se estiverem no ar junto com o A, o SMF
# fica com UPFs orfaos associados e a prova do passo 11 mede a topologia errada.
DEPLOYS_CENARIO_B = ["free5gc-i-upf", "free5gc-psa-upf"]

# NFs de SBI, que registram no NRF. O UPF nao entra: fala so' PFCP com o SMF.
# Um NF que sobe antes do NRF conseguir gravar no Mongo fica com o NF instance
# ID VAZIO -- e o sintoma so' aparece la' no registro do UE, como
# "Mandatory IE [ausfInstanceId/AmfInstanceId] is missing" no UDM e
# "Initial Registration failed [CONGESTION]" no UE.
NFS_SBI = [
    "free5gc-udr", "free5gc-udm", "free5gc-ausf", "free5gc-nssf",
    "free5gc-pcf", "free5gc-nef", "free5gc-amf", "free5gc-smf",
    # o webconsole tambem registra no NRF (como AF) e imprime o mesmo marcador
    "free5gc-webui",
]
MARCADOR_OK = "OAuth2 setting receive from NRF"
MARCADOR_ERRO = "register to NRF Error"

# --------------------------------------------------------------------------
# PERFIS DE CARGA
# --------------------------------------------------------------------------
# Cada perfil e' um caso de uso, nao um numero solto. Os valores sao a ORDEM DE
# GRANDEZA que a composicao do caso pede (resolucao x fps x eficiencia do
# codec) -- estao aqui com a conta a vista para que o texto do TG possa
# justifica-los, e nao para serem citados como medida de um produto real.
#
# bitrate_mbps  downlink POR SESSAO (o fluxo de midia renderizada)
# fps           cadencia de quadro do servidor
# pose_hz       uplink de pose/controle -- a malha fechada do caso de uso
# mtu           payload UDP por pacote; 1200 fica abaixo do MTU do tunel GTP-U
#
# Trocar de perfil NAO exige editar manifesto: o passo 3 aplica os valores nos
# dois deployments (mec-app e remote-app) e confere que os dois calcularam a
# mesma carga. Rodar varios de uma vez:
#     --perfil vr-cloud,cloud-gaming,teleoperacao --repeticoes 10
PERFIS = {
    "vr-360": {
        "bitrate_mbps": 25, "fps": 60, "pose_hz": 120, "mtu": 1200,
        "descricao": "Video 360 estereoscopico 4K a 60 fps (~25 Mbps em HEVC). "
                     "Pose so' para orientar a projecao, entao 120 Hz basta. "
                     "E' o piso do que se chama de VR: sem render remoto.",
    },
    "cloud-gaming": {
        "bitrate_mbps": 30, "fps": 60, "pose_hz": 120, "mtu": 1200,
        "descricao": "Jogo renderizado na borda, 1080p60 em HEVC de qualidade "
                     "alta (~30 Mbps). Controle a 120 Hz (gamepad/mouse). "
                     "Malha fechada, mas tolerante a ~50 ms de m2p.",
    },
    "vr-cloud": {
        "bitrate_mbps": 50, "fps": 90, "pose_hz": 250, "mtu": 1200,
        "descricao": "VR interativo com render na borda: ~2K por olho a 90 fps "
                     "(~50 Mbps em HEVC) e pose a 250 Hz, a taxa tipica da IMU "
                     "de um headset. E' o perfil do TG1 e o caso mais exigente "
                     "que ainda e' realista.",
    },
    "vr-extremo": {
        "bitrate_mbps": 100, "fps": 90, "pose_hz": 250, "mtu": 1200,
        "descricao": "VR de alta fidelidade (~4K por olho). Serve para achar o "
                     "TETO do testbed: se a carga nao trafega, o relatorio diz "
                     "onde ela parou, e esse tambem e' um resultado.",
    },
    "ar-industrial": {
        "bitrate_mbps": 12, "fps": 60, "pose_hz": 200, "mtu": 1200,
        "descricao": "AR assistida: video 1080p com overlay de anotacao "
                     "(~12 Mbps). Downlink leve, mas a pose precisa ser rapida "
                     "para o overlay nao descolar do objeto real.",
    },
    "teleoperacao": {
        "bitrate_mbps": 8, "fps": 60, "pose_hz": 500, "mtu": 1200,
        "descricao": "Teleoperacao/telemedicina: video de apoio 720p60 "
                     "(~8 Mbps) com a MALHA DE CONTROLE a 500 Hz. Inverte o "
                     "perfil dos outros -- pouco downlink, uplink muito "
                     "frequente -- e e' o caso em que a latencia da rede pesa "
                     "mais do que a vazao.",
    },
}
PERFIL_PADRAO = "vr-cloud"

# Deployments que rodam o vr-server e precisam receber o perfil.
APPS_VR = ("free5gc-mec-app", "free5gc-remote-app")

# nodeID que a UPF anuncia no PFCP -- tem que casar com scenario-a-cupf/smf.yaml.
UPFS = {
    "upf": ("free5gc-upf", "upf.free5gc.svc.cluster.local"),
}

VERDE, VERM, AMAR, CINZA, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    VERDE = VERM = AMAR = CINZA = RESET = ""

avisos = []
PAUSAR = False
CONCISO = False


# --------------------------------------------------------------------------
# infra
# --------------------------------------------------------------------------
class Falha(Exception):
    """Erro que interrompe o teste. A mensagem ja' vem pronta para o usuario."""


class FalhaDefinitiva(Falha):
    """Falha que REPETIR nao resolve -- erro de uso, pre-requisito ausente,
    configuracao errada. A campanha tem retentativa porque o testbed falha por
    motivo transitorio (a corrida NF x NRF, o SMF que ainda nao respondia); mas
    insistir num cenario que nem foi aplicado so' imprime o mesmo erro duas
    vezes e sugere, mentindo, que havia algo a refazer."""


def passo(n, titulo, porque=""):
    """Cabecalho da etapa. 'porque' explica, em tempo de execucao, o que este
    passo faz e por que ele existe -- para acompanhar sem ter que ler o codigo."""
    print(f"\n{'='*72}\n[{n:02d}] {titulo}\n{'='*72}")
    if porque and not CONCISO:
        for paragrafo in porque.strip().split("\n\n"):
            for linha in textwrap.wrap(" ".join(paragrafo.split()), 68):
                print(f"  {CINZA}# {linha}{RESET}")
            print()


def ok(msg):
    print(f"  {VERDE}OK{RESET}   {msg}")


def info(msg):
    print(f"  {CINZA}..{RESET}   {msg}")


def aviso(msg, escopo="geral"):
    """escopo='campanha' marca os avisos que invalidam a COMPARACAO entre os
    dois caminhos. Aviso de placement, por exemplo, e' relevante mas nao torna
    as duas corridas incomparaveis entre si."""
    avisos.append((escopo, msg))
    print(f"  {AMAR}AVISO{RESET} {msg}")


def pausa(proximo=""):
    """Modo passo-a-passo: para depois de cada etapa para dar tempo de ler."""
    global PAUSAR
    if not PAUSAR:
        return
    if not sys.stdin.isatty():
        return
    alvo = f" -> {proximo}" if proximo else ""
    try:
        r = input(f"\n  {CINZA}[enter] continua{alvo}   "
                  f"(c = segue sem pausar, q = aborta){RESET} ").strip().lower()
    except EOFError:
        return
    if r == "q":
        raise KeyboardInterrupt
    if r == "c":
        PAUSAR = False


def run(cmd, check=True, timeout=120, quiet=False, cwd=None):
    if not quiet:
        print(f"  {CINZA}$ {' '.join(cmd) if isinstance(cmd, list) else cmd}{RESET}")
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                       text=True, timeout=timeout, cwd=cwd)
    if check and r.returncode != 0:
        raise Falha(f"comando falhou ({r.returncode}): "
                    f"{' '.join(cmd) if isinstance(cmd, list) else cmd}\n"
                    f"       {r.stderr.strip() or r.stdout.strip()}")
    return r


def kubectl(*args, **kw):
    return run(["kubectl", "-n", NS, *args], **kw)


def kexec(pod, container, *cmd, **kw):
    return kubectl("exec", pod, "-c", container, "--", *cmd, **kw)


def _cluster_ip(svc):
    r = kubectl("get", "svc", svc, "-o", "jsonpath={.spec.clusterIP}", quiet=True)
    ip = r.stdout.strip()
    if not ip or ip == "None":
        raise Falha(f"service {svc} sem ClusterIP")
    return ip


def espera(descricao, cond, timeout, intervalo=3):
    """Chama cond() ate' virar verdadeiro. cond pode devolver (ok, detalhe)."""
    t0 = time.time()
    ultimo = ""
    while time.time() - t0 < timeout:
        r = cond()
        val, detalhe = r if isinstance(r, tuple) else (r, "")
        if val:
            return detalhe
        if detalhe and detalhe != ultimo:
            info(f"{descricao}: {detalhe}")
            ultimo = detalhe
        time.sleep(intervalo)
    raise Falha(f"timeout ({timeout}s) esperando: {descricao}"
                + (f"\n       ultimo estado: {ultimo}" if ultimo else ""))


# --------------------------------------------------------------------------
# 01 ferramentas
# --------------------------------------------------------------------------
def p01_ferramentas():
    passo(1, "Ferramentas e conexao com o cluster",
          """Confere o kubectl, qual contexto esta ativo e quais nos existem. E' a
    primeira coisa porque, com o contexto errado, todo o resto mede o cluster
    errado sem dar nenhum sinal disso.""")
    if not shutil.which("kubectl"):
        raise Falha("kubectl nao encontrado no PATH")
    r = run(["kubectl", "config", "current-context"], check=False, quiet=True)
    if r.returncode != 0:
        raise Falha("kubectl sem contexto ativo (kubectl config current-context falhou)")
    ok(f"contexto: {r.stdout.strip()}")

    r = run(["kubectl", "get", "nodes", "-o",
             "jsonpath={range .items[*]}{.metadata.name}{'\\t'}"
             "{.status.conditions[?(@.type=='Ready')].status}{'\\n'}{end}"], quiet=True)
    nos = [l.split("\t") for l in r.stdout.strip().splitlines() if l.strip()]
    for nome, pronto in nos:
        estado = f"{VERDE}Ready{RESET}" if pronto == "True" else f"{VERM}NotReady{RESET}"
        print(f"       no {nome:<20} {estado}")
    ok(f"{len(nos)} no(s) no cluster")


# --------------------------------------------------------------------------
# 02 validate
# --------------------------------------------------------------------------
def p02_validate(args):
    passo(2, "Consistencia estatica dos manifestos (validate.py)",
          """Parseia os YAML embutidos nos ConfigMaps e checa as regras que o free5gc so'
    aplica no boot: versao de cada config, endpoint 0.0.0.0 em campo que vira
    F-TEID, nome de UPF que precisa casar entre o smfcfg e o ueRouting.

    Vale rodar antes de aplicar porque essa classe de erro nao aparece como
    erro: o NF sobe normalmente e a sessao PDU simplesmente nunca fecha.""")
    if args.pular_validate:
        info("pulado (--pular-validate)")
        return
    r = subprocess.run([sys.executable, "scripts/validate.py"], cwd=BASE,
                       capture_output=True, text=True)
    saida = (r.stdout + r.stderr).strip()
    print("       " + saida.replace("\n", "\n       "))
    if "ModuleNotFoundError" in saida:
        raise Falha("falta dependencia para rodar o validate.py:\n"
                    "       pip install -r scripts/requirements.txt\n"
                    "       (ou pule esta etapa com --pular-validate)")
    if r.returncode != 0:
        raise Falha("validate.py reprovou os manifestos; corrija antes de aplicar")
    ok("manifestos consistentes")


# --------------------------------------------------------------------------
# 03 deploy
# --------------------------------------------------------------------------
def p03_deploy(args):
    passo(3, f"Deploy do cenario A + perfil de carga '{args.perfil}'",
          """Chama o deploy.py up a, que remove o plano de usuario do cenario B (senao
    sobram I-UPF e PSA-UPF associados ao SMF e a prova do passo 11 mede a
    topologia errada), aplica o plano de controle comum, a UPF central, os
    servicos MEC/remoto e o tester, e reinicia o SMF para ele reler os ConfigMaps.

    Depois APLICA O PERFIL DE CARGA nos dois vr-server. Isso vem aqui, e nao no
    manifesto, por duas razoes: o manifesto teria que ser editado a cada
    cenario (e commitado errado junto), e numa campanha com --repeticoes o
    deploy reaplica o YAML a cada execucao -- um 'kubectl set env' feito antes
    seria desfeito no meio da campanha, sem aviso, e metade das repeticoes
    mediria outra carga.""")
    if args.deploy:
        r = subprocess.run([sys.executable, "deploy.py", "up", "a"], cwd=BASE, text=True)
        if r.returncode != 0:
            raise Falha("deploy.py up a falhou")
        ok("cenario A aplicado")
    else:
        info("deploy pulado (use --deploy para subir o cenario antes do teste)")
        # Sem --deploy o cenario tem que JA' estar no ar. Se nao estiver, o
        # 'kubectl set env' logo abaixo falha com um "deployments.apps
        # <nome> not found" que nao diz o que fazer -- e numa campanha com
        # --repeticoes isso ainda vira "tentativa 1 de 2 falhou" e um deploy
        # do zero que tambem nao existe. Melhor parar aqui dizendo o motivo.
        faltando = sorted(set(APPS_VR) - _deploys_existentes())
        if faltando:
            raise FalhaDefinitiva(
                "o cenario nao esta no ar: faltam " + ", ".join(faltando) + ".\n"
                "       Suba antes de testar, de um dos dois jeitos:\n"
                "         python3 scripts/test-cenario-a.py --deploy ...\n"
                "         python3 deploy.py up a")
    _aplicar_perfil(args)


def _carga_esperada(perf):
    """O que o vr_server VAI calcular para este perfil: ele fecha o frame em
    pacotes inteiros de MTU, entao a taxa efetiva quase nunca e' o alvo redondo
    (8 Mbps a 60 fps viram 14 pacotes = 8.1 Mbps). Comparar o log com o ALVO
    faria toda corrida parecer divergente; comparar com este valor detecta o
    que importa -- o perfil que nao pegou."""
    frame_bytes = perf["bitrate_mbps"] * 1e6 / 8.0 / perf["fps"]
    pkts = max(1, math.ceil(frame_bytes / perf["mtu"]))
    return pkts, pkts * perf["mtu"] * 8 * perf["fps"] / 1e6


def _pod_ativo(deploy):
    """Nome do pod que esta' DE FATO servindo: Running e sem deletionTimestamp,
    o mais recente se houver mais de um.

    'kubectl logs deploy/X' escolhe um pod qualquer entre os que existem, e
    durante um rollout o velho ainda esta' la' em Terminating. Foi assim que
    uma troca de perfil passou despercebida: o rollout tinha terminado, o pod
    novo ja' servia 8 Mbps, e a leitura pegou o pod velho ainda com 50 Mbps --
    o script seguiu achando que o perfil nao tinha sido aplicado."""
    r = kubectl("get", "pods", "-l", f"app={deploy}", "-o", "json",
                check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    try:
        pods = json.loads(r.stdout).get("items", [])
    except json.JSONDecodeError:
        return None
    vivos = [p for p in pods
             if not p["metadata"].get("deletionTimestamp")
             and p["status"].get("phase") == "Running"]
    if not vivos:
        return None
    vivos.sort(key=lambda p: p["metadata"].get("creationTimestamp", ""))
    return vivos[-1]["metadata"]["name"]


def _perfil_do_log(deploy):
    """Le, do log do vr-server que esta' servindo, a carga que ELE calculou.

    Conferir a variavel de ambiente do Deployment nao bastaria: ela diz o que
    foi pedido, nao o que esta' rodando."""
    pod = _pod_ativo(deploy)
    if not pod:
        return None
    r = kubectl("logs", pod, "-c", "vr-server", "--tail=40",
                check=False, quiet=True, timeout=60)
    m = re.search(r"downlink:\s*(\d+) pkt/frame x (\d+) B x (\d+) fps\s*=\s*([\d.]+) Mbps",
                  r.stdout)
    if not m:
        return None
    return {"pod": pod, "pkts": int(m.group(1)), "mtu": int(m.group(2)),
            "fps": int(m.group(3)), "mbps": float(m.group(4))}


def _aplicar_perfil(args):
    """Poe o perfil nos dois vr-server e so' segue quando OS DOIS confirmarem.

    A comparacao MEC x remoto so' vale se a carga for identica nos dois lados;
    um rollout que pegou num e nao no outro produz uma tabela que parece boa e
    esta' errada."""
    perf = PERFIS[args.perfil]
    info(f"{args.perfil}: {perf['bitrate_mbps']} Mbps @ {perf['fps']} fps, "
         f"pose {perf['pose_hz']} Hz, MTU {perf['mtu']} B")
    for linha in textwrap.wrap(perf["descricao"], 68):
        print(f"       {CINZA}{linha}{RESET}")

    pkts_alvo, mbps_alvo = _carga_esperada(perf)
    info(f"o vr_server deve fechar isso em {pkts_alvo} pacotes por frame "
         f"= {mbps_alvo:.1f} Mbps efetivos")

    def _no_perfil(v):
        """Compara com a carga que o servidor DEVE calcular, nao com o alvo."""
        return bool(v) and (v["pkts"], v["mtu"], v["fps"]) == (
            pkts_alvo, perf["mtu"], perf["fps"])

    for deploy in APPS_VR:
        if _no_perfil(_perfil_do_log(deploy)):
            info(f"{deploy} ja' esta' no perfil")
            continue
        kubectl("set", "env", f"deploy/{deploy}", "-c", "vr-server",
                f"VR_BITRATE_MBPS={perf['bitrate_mbps']}",
                f"VR_FPS={perf['fps']}", f"VR_MTU={perf['mtu']}",
                f"VR_PROFILE={args.perfil}", quiet=True)
        run(["kubectl", "-n", NS, "rollout", "status", f"deploy/{deploy}",
             "--timeout=180s"], check=False, quiet=True, timeout=200)

    # espera() devolve o DETALHE da condicao (a string de progresso), nao o
    # valor -- por isso o resultado sai por este dict, e nao pelo retorno.
    vistos = {}

    # Espera os DOIS chegarem na carga certa. A condicao e' o perfil aplicado,
    # e nao "o log respondeu": durante o rollout o pod velho ainda serve, e
    # aceitar a primeira leitura que voltasse mediria o perfil anterior.
    def cond():
        lidos, pendentes = {}, []
        for deploy in APPS_VR:
            v = _perfil_do_log(deploy)
            if not v:
                pendentes.append(f"{deploy}: sem pod ativo reportando carga")
            elif not _no_perfil(v):
                pendentes.append(f"{deploy}: ainda em {v['mbps']:.1f} Mbps @ "
                                 f"{v['fps']} fps ({v['pod']})")
            else:
                lidos[deploy] = v
        if pendentes:
            return False, "; ".join(pendentes)
        vistos.update(lidos)
        return True, ""

    try:
        espera("os dois vr-server no perfil novo", cond, 240)
    except Falha as e:
        raise Falha(
            f"o perfil '{args.perfil}' nao chegou nos dois vr-server.\n"
            f"       {e}\n"
            "       Sem os dois na MESMA carga a comparacao MEC x remoto nao "
            "mede o UPF, mede a diferenca de carga.") from None

    for deploy, v in vistos.items():
        print(f"       {deploy:<22} {v['pkts']} pkt/frame x {v['mtu']} B x "
              f"{v['fps']} fps = {v['mbps']:.1f} Mbps  ({v['pod']})")
    ok(f"perfil '{args.perfil}' ativo e identico nos dois caminhos "
       f"({mbps_alvo:.1f} Mbps efetivos)")


# --------------------------------------------------------------------------
# 04 pods prontos
# --------------------------------------------------------------------------
def _pods_pendentes():
    r = kubectl("get", "pods", "-o", "json", check=False, quiet=True)
    if r.returncode != 0:
        return None, f"namespace {NS} inacessivel"
    pods = json.loads(r.stdout)["items"]
    ruins = []
    for p in pods:
        nome = p["metadata"]["name"]
        fase = p["status"]["phase"]
        if fase == "Succeeded":
            continue
        pronto = all(c.get("ready") for c in p["status"].get("containerStatuses", [])) \
            and p["status"].get("containerStatuses")
        if fase != "Running" or not pronto:
            motivo = fase
            for c in p["status"].get("conditions", []):
                if c["type"] == "PodScheduled" and c["status"] != "True":
                    motivo = f"{fase}/{c.get('reason')}: {c.get('message', '')[:90]}"
            for c in p["status"].get("containerStatuses", []):
                w = c.get("state", {}).get("waiting")
                if w:
                    motivo = f"{fase}/{w.get('reason')}"
            ruins.append((nome, motivo))
    return pods, ruins


def _registrou_no_nrf(deploy):
    """True se o NF confirmou registro no NRF DEPOIS do ultimo erro de registro,
    False se o ultimo marcador foi de erro, e None quando NAO DA' PARA SABER.

    O terceiro caso e' o que faltava. Os marcadores saem no boot do NF; num pod
    que ja' esta' no ar ha' bastante tempo eles saem da janela do 'logs --tail'
    -- e o SMF, que loga um par de linhas de charging por sessao, enterra o
    proprio boot em minutos. Antes, nenhum marcador dava ult_ok == ult_erro ==
    -1, e '-1 > -1' e' False: "nao observei" era reportado como "nao registrou",
    e o teste abortava contra um cenario perfeitamente saudavel (foi o que
    aconteceu ao rodar sem --deploy contra um SMF de 11 min de vida, que estava
    servindo sessoes PDU normalmente).

    Nao vale trocar por uma consulta ao NRF: a NFDiscovery pede token OAuth2
    quando o core esta' com oauth ligado, e um teste que precisa de credencial
    para dizer se o cluster esta' de pe' troca um falso negativo por outro."""
    r = kubectl("logs", f"deploy/{deploy}", "--tail=3000", check=False, quiet=True)
    if r.returncode != 0:
        return None
    limpo = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    ult_ok = ult_erro = -1
    for i, linha in enumerate(limpo.splitlines()):
        if MARCADOR_OK in linha:
            ult_ok = i
        elif MARCADOR_ERRO in linha:
            ult_erro = i
    if ult_ok == -1 and ult_erro == -1:
        return None
    return ult_ok > ult_erro


def _deploys_existentes():
    r = kubectl("get", "deploy", "-o",
                "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
                check=False, quiet=True)
    return set(r.stdout.split())


def p04_pods(args):
    passo(4, "Pods do plano de controle e de usuario prontos",
          """Confere que os deployments do cenario A existem, que nao sobrou nada do
    cenario B, e que nenhum pod ficou pendente.

    Pod parado em Pending quase sempre e' nodeSelector que nenhum no satisfaz --
    lembrando que o seletor e' um AND, entao hostname + nodetype que nao casam
    entre si dao zero nos. Quando acontece, o motivo exato do scheduler e'
    impresso aqui.

    Confere tambem se todo NF de SBI fechou registro no NRF. NF que subiu antes
    do NRF conseguir gravar no Mongo fica com instance ID vazio, continua
    Running e so' quebra no registro do UE -- e la' o sintoma nao tem relacao
    obvia com a causa.""")

    existentes = _deploys_existentes()
    faltando = [d for d in DEPLOYS if d not in existentes]
    if faltando:
        raise Falha(
            "deployments do cenario A ausentes no namespace: "
            + ", ".join(faltando) + "\n"
            "       Suba o cenario antes: python3 deploy.py up a  "
            "(ou rode este teste com --deploy)")
    residuo = [d for d in DEPLOYS_CENARIO_B if d in existentes]
    if residuo:
        raise Falha(
            f"{', '.join(residuo)} (UPFs do cenario B) ainda no ar junto com o A.\n"
            "       O SMF fica com UPF orfao associado e a prova do passo 11 mede a\n"
            "       topologia errada. Rode: python3 deploy.py up a")
    ok(f"{len(DEPLOYS)} deployments do cenario A presentes, nenhum residuo do B")

    def cond():
        pods, ruins = _pods_pendentes()
        if pods is None:
            return False, ruins
        # o tester tem ciclo proprio (pode estar reiniciando); passo 8 cuida dele
        ruins = [x for x in ruins if not x[0].startswith(TESTER_STS)]
        if not ruins:
            return True, ""
        return False, "; ".join(f"{n} [{m}]" for n, m in ruins[:4])

    try:
        espera("pods prontos", cond, args.timeout)
    except Falha:
        _pods_pendentes_relatorio()
        raise
    ok("todos os pods prontos")

    estado = {d: _registrou_no_nrf(d) for d in NFS_SBI}
    perdidos = [d for d, v in estado.items() if v is False]
    mudos = [d for d, v in estado.items() if v is None]
    if mudos and not perdidos:
        # Inconclusivo NAO e' falha: o marcador so' saiu da janela do log. Quem
        # decide de verdade e' o passo 9 -- sem registro no NRF a sessao PDU nao
        # fecha, e ali o erro aparece com a causa junto.
        info("sem marcador de registro no log de " + ", ".join(mudos)
             + " (pod no ar ha' tempo demais); o passo 9 e' quem confirma")
    if perdidos:
        raise Falha(
            "estes NFs nao confirmaram registro no NRF: " + ", ".join(perdidos) + "\n"
            "       Eles subiram antes de o NRF conseguir gravar no MongoDB e\n"
            "       ficaram com o NF instance ID VAZIO. Seguir daqui nao adianta:\n"
            "       o registro do UE falha no passo 9 com 'CONGESTION', e a causa\n"
            "       real aparece so' no log do UDM, como\n"
            "       'Mandatory IE [ausfInstanceId/AmfInstanceId] is missing'.\n"
            "       Correcao: kubectl -n " + NS + " rollout restart deploy/"
            + perdidos[0] + "\n"
            "       (ou suba tudo de novo com deploy.py, que agora respeita a\n"
            "       ordem de dependencia e confirma o registro de cada NF)")
    ok(f"{len(NFS_SBI)} NFs com registro confirmado no NRF")


def _pods_pendentes_relatorio():
    pods, ruins = _pods_pendentes()
    if pods is None:
        return
    for nome, motivo in ruins or []:
        print(f"       {VERM}{nome}{RESET}: {motivo}")
        if "Unschedulable" in motivo or "FailedScheduling" in motivo:
            print(f"       {AMAR}-> nenhum no satisfaz o nodeSelector desse pod. "
                  f"Ajuste o hostname no manifesto ou rotule o no.{RESET}")


# --------------------------------------------------------------------------
# 05 placement
# --------------------------------------------------------------------------
def _no_do(label):
    r = kubectl("get", "pod", "-l", f"epc-mode={label}", "-o",
                "jsonpath={.items[0].spec.nodeName}", check=False, quiet=True)
    return r.stdout.strip() or "?"


# Bits comparados para decidir se dois nos estao no MESMO segmento de rede.
#
# Verificado no cluster: os brix (borda) estao todos em <edge-subnet> --
# brix-porvir-01 e' <campus-ip>, o -02 e' .<host>, o -03 e' .<host> -- com
# rota DIRETA entre si em enp3s0, 1 hop, sem passar pelo gateway. O nucleo
# (petshopboys .<host>, metallica .<host>) esta em <core-subnet>, atras de outro
# gateway, a 2 hops. Comparar os 22 primeiros bits separa exatamente esses dois
# grupos, e e' isso que "sair da borda" quer dizer aqui: cruzar o roteador.
#
# Se o testbed mudar de faixa de IP, este e' o unico numero a ajustar.
PREFIXO_SEGMENTO = 22


def _ip_do_no(no):
    if no in (None, "?", ""):
        return None
    r = kubectl("get", "node", no, "-o",
                "jsonpath={.status.addresses[?(@.type=='InternalIP')].address}",
                check=False, quiet=True)
    return r.stdout.strip() or None


def _mesmo_segmento(a, b):
    """True/False se os nos a e b estao (ou nao) no mesmo segmento L2.

    Devolve None quando nao deu para descobrir o IP de algum dos dois -- ai a
    checagem e' PULADA, em vez de virar um aviso falso. Placement e' decisao
    manual: um aviso errado aqui custa mais caro que a checagem ausente."""
    ia, ib = _ip_do_no(a), _ip_do_no(b)
    if not ia or not ib:
        return None
    rede = ipaddress.ip_network(f"{ia}/{PREFIXO_SEGMENTO}", strict=False)
    return ipaddress.ip_address(ib) in rede


def _gtp5g_carregado(deploy):
    """Modulos de kernel NAO sao namespaced: o /proc/modules visto de dentro de
    qualquer container e' o do HOST. Da' para conferir o gtp5g do no sem SSH e
    sem pod privilegiado extra -- basta ler de dentro do proprio UPF."""
    r = kubectl("exec", f"deploy/{deploy}", "--", "grep", "gtp5g", "/proc/modules",
                check=False, quiet=True, timeout=60)
    linha = next((l for l in r.stdout.splitlines() if l.startswith("gtp5g")), "")
    return bool(linha), linha


def p05_placement():
    passo(5, "Placement real das pecas + gtp5g no no da UPF central",
          """Mostra em que no cada peca caiu de fato e confere o gtp5g.

    O criterio e' a Figura 3 do TG1 no cenario A: a UPF centralizada fica DENTRO
    do Server Node, junto do plano de controle, do outro lado do backhaul em
    relacao a RAN. O tester e o mec-app ficam na borda, exatamente onde estao no
    cenario B -- e' isso que faz o a-mec ter o MESMO destino que o b-mec.

    O gtp5g e' modulo de KERNEL: a exigencia e' por NO, nao por pod, e sem ele o
    pod da UPF sobe normalmente enquanto o plano de dados nunca passa a existir.

    Os avisos de placement nao derrubam o teste: dizem se o numero de latencia
    vale alguma coisa na comparacao com o cenario B.""")
    antes_de_checar = len(avisos)
    n = {k: _no_do(k) for k in
         ("ueransim", "upf", "mec-app", "remote-app", "smf", "amf")}
    for papel, no in n.items():
        print(f"       {papel:<12} {no}")

    nucleo = ("smf", "amf", "upf")
    if len({n[p] for p in nucleo if n[p] != "?"}) > 1:
        aviso("as pecas do Server Node estao em nos DIFERENTES ("
              + ", ".join(f"{p}={n[p]}" for p in nucleo) + "). Na Figura 3 o "
              "plano de controle e a UPF centralizada dividem a MESMA caixa.")
    if _mesmo_segmento(n["upf"], n["ueransim"]) is True:
        aviso(f"a UPF central ({n['upf']}) esta no segmento da BORDA, junto do "
              f"tester ({n['ueransim']}): nao ha backhaul entre a RAN e a ancora, "
              "e o cenario A deixa de ser o baseline centralizado.")
    if _mesmo_segmento(n["upf"], n["mec-app"]) is True:
        aviso(f"mec-app ({n['mec-app']}) no mesmo segmento da UPF central: o "
              "trafego MEC nao faz o trombone borda -> nucleo -> borda, e a "
              "comparacao a-mec x b-mec perde o sentido.")
    elif _mesmo_segmento(n["ueransim"], n["mec-app"]) is False:
        aviso(f"mec-app ({n['mec-app']}) fora do segmento da borda: nao e' o "
              "mesmo destino do b-mec.")
    if _mesmo_segmento(n["ueransim"], n["remote-app"]) is True:
        aviso(f"remote-app ({n['remote-app']}) no segmento da borda: o trafego "
              "remoto nao atravessa o backhaul.")
    if n["remote-app"] != "?" and n["remote-app"] == n["upf"]:
        aviso(f"remote-app no proprio no da UPF central ({n['upf']}): o caminho "
              "remoto economiza o hop N6 que ele paga no cenario B, e o a-remoto "
              "deixa de ser comparavel ao b-remoto.")
    if len(avisos) == antes_de_checar:
        ok(f"placement fiel a Figura 3 do TG1 (cenario A): UPF central em "
           f"{n['upf']}, MEC na borda em {n['mec-app']}, tester em {n['ueransim']}")

    for papel, (deploy, _) in UPFS.items():
        carregado, linha = _gtp5g_carregado(deploy)
        if not carregado:
            raise Falha(
                f"gtp5g NAO esta carregado no no da UPF central ({n[papel]}).\n"
                "       O pod da UPF sobe assim mesmo e o plano de dados nunca "
                "existe -- a falha e' muda.\n"
                f"       No no {n[papel]}:\n"
                "         git clone https://github.com/free5gc/gtp5g.git\n"
                "         cd gtp5g && make && sudo make install && sudo modprobe gtp5g\n"
                "       Use uma versao do gtp5g que compile no kernel do no "
                "(kernel 6.8 exige gtp5g recente)")
        info(f"{papel} @ {n[papel]}: {linha.split()[0]} carregado "
             f"({'OE' if '(OE)' in linha else 'in-tree'})")
    ok("gtp5g presente no no da UPF central")
    return n

# --------------------------------------------------------------------------
# 06 assinantes
# --------------------------------------------------------------------------
def p06_assinantes(args):
    passo(6, "Assinantes no MongoDB",
          """Grava os assinantes. No free5gc cada UE vira oito documentos espalhados por
    oito colecoes (autenticacao, dados provisionados, politica) -- nao existe uma
    colecao unica de subscribers como no Open5GS.

    Se o registro do UE falhar la' no passo 9, este e' o primeiro suspeito.""")
    if not args.carregar_assinantes:
        info("pulado (use --carregar-assinantes N para popular o Mongo). "
             "Se o registro do UE falhar no passo 9, suspeite disto primeiro.")
        return
    try:
        import pymongo  # noqa: F401
    except ImportError:
        raise Falha("pymongo nao instalado -- necessario para carregar assinantes.\n"
                    "       pip install -r scripts/requirements.txt")

    porta = args.porta_mongo
    info(f"abrindo port-forward svc/mongo {porta}:27017")
    pf = subprocess.Popen(["kubectl", "-n", NS, "port-forward", "svc/mongo",
                           f"{porta}:27017"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        if pf.poll() is not None:
            raise Falha(f"port-forward morreu -- a porta local {porta} ja' esta em uso?")
        r = subprocess.run(
            [sys.executable, "scripts/insere-dados.py", "--limpar",
             "--qtd", str(args.carregar_assinantes),
             "--url", f"mongodb://localhost:{porta}/"],
            cwd=BASE, capture_output=True, text=True)
        print("       " + (r.stdout or r.stderr).strip().replace("\n", "\n       "))
        if r.returncode != 0:
            raise Falha("insere-dados.py falhou")
    finally:
        pf.send_signal(signal.SIGTERM)
        pf.wait(timeout=10)
    ok(f"{args.carregar_assinantes} assinante(s) carregado(s)")


# --------------------------------------------------------------------------
# 07 PFCP
# --------------------------------------------------------------------------
def _pfcp_vivo(deploy):
    """True se o UPF trocou heartbeat PFCP com o SMF nos ultimos segundos.

    A associacao PFCP e' um ESTADO, nao um evento de boot -- e era isso que a
    checagem anterior errava. Ela procurava o nodeID do UPF no log do SMF, mas
    esse registro sai uma vez, no boot, e o SMF loga um par de linhas de
    charging por sessao: depois de alguns minutos de trafego o kubelet ja'
    rotacionou o arquivo e o boot sumiu de vez (medido: 48 mil linhas de log,
    ZERO mencoes a PFCP). Nenhum --tail recupera o que nao esta' mais la', e o
    teste abortava com "timeout esperando associacao PFCP" contra um core que
    estava servindo trafego naquele instante.

    O heartbeat, ao contrario, se repete a cada poucos segundos enquanto a
    associacao existir -- e' a prova de que ela esta' viva AGORA."""
    r = kubectl("logs", f"deploy/{deploy}", "--since=40s", check=False,
                quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    return bool(re.search(r"heartbeat", r.stdout, re.I))


def p07_pfcp(args):
    passo(7, "Associacao PFCP: o SMF precisa enxergar a UPF central",
          """Espera o SMF fechar associacao PFCP com a UPF centralizada.

    A prova e' o HEARTBEAT PFCP que a UPF troca com o SMF: se ele esta'
    acontecendo agora, a associacao esta' de pe' agora. O marcador de boot nao
    serve -- ele sai uma vez e o log rotaciona.

    Se o SMF subiu com o config do cenario B, ele procura o I-UPF e o PSA-UPF,
    nao acha nenhum, e este passo expira.""")
    deploy = UPFS["upf"][0]

    def cond():
        if _pfcp_vivo(deploy):
            return True, ""
        return False, "heartbeat PFCP ainda nao visto"

    espera("associacao PFCP", cond, args.timeout)
    ok("UPF central associada ao SMF (heartbeat PFCP ativo)")

# --------------------------------------------------------------------------
# 08 tester
# --------------------------------------------------------------------------
def _ue_registrado():
    """True/False conforme o rm-state do UE; None se nem der para perguntar."""
    r = kexec(TESTER_POD, "ue", "./nr-cli", IMSI_PRINCIPAL, "-e", "status",
              check=False, quiet=True, timeout=30)
    if r.returncode != 0:
        return None
    return "RM-REGISTERED" in r.stdout


def p08_tester(args):
    passo(8, "Tester UERANSIM (gNB + UE)",
          """Confere que o tester esta no ar e que o gNB fechou NG Setup com a AMF.

    O numero de UEs vem do MANIFESTO, nao de scale em tempo de execucao:
    'replicas' no StatefulSet e' quantos pods sobem e NUM_UE no container 'ue' e'
    quantos IMSIs cada pod registra. Para mudar, edite tester/ueransim.yaml e
    aplique de novo.

    Se o UE nao estiver registrado, o pod e' recriado aqui. Motivo: o tester sobe
    junto com o deploy, antes de o Mongo ter assinantes; ele leva 404 do UDR e o
    T3511 desiste na 5a tentativa. Passado isso o UE fica parado para sempre,
    mesmo com os assinantes ja' carregados -- e o log so' mostra CONGESTION.""")
    r = kubectl("get", "statefulset", TESTER_STS, "-o",
                "jsonpath={.spec.replicas}{'\\t'}{.status.readyReplicas}",
                check=False, quiet=True)
    if r.returncode != 0:
        raise Falha(f"StatefulSet {TESTER_STS} nao existe no namespace {NS}")
    campos = (r.stdout + "\t").split("\t")
    desejadas = int(campos[0] or 0)
    if desejadas == 0:
        raise Falha(
            f"o StatefulSet {TESTER_STS} esta com replicas: 0.\n"
            "       O numero de UEs e' definido no manifesto, nao por scale:\n"
            "         1) edite 'replicas' em tester/ueransim.yaml (e NUM_UE no\n"
            "            container 'ue', se quiser mais de um IMSI por pod);\n"
            "         2) kubectl apply -f tester/ueransim.yaml\n"
            "       No cenario A nao ha lista de ULCL: basta os IMSIs estarem\n"
            "       cadastrados no Mongo (--carregar-assinantes N).")
    info(f"replicas definidas no manifesto: {desejadas} "
         f"(as medicoes usam o pod {TESTER_POD})")

    # O tester sobe junto com o deploy, ANTES de o Mongo ter assinantes. Ele
    # tenta registrar, leva 404 do UDR, e o T3511 desiste na 5a tentativa
    # (~45 s) -- depois disso o UE fica parado em ATTEMPTING-REGISTRATION para
    # sempre, mesmo que os assinantes entrem logo em seguida. Recriar o pod e' o
    # que forca uma tentativa nova agora que o passo 6 ja' populou o banco.
    if _ue_registrado() is False:
        info("UE nao esta registrado (provavelmente desistiu antes de os "
             "assinantes existirem); recriando o pod para tentar de novo")
        kubectl("delete", "pod", TESTER_POD, "--wait=false", check=False)
        time.sleep(5)

    def cond():
        r = kubectl("get", "pod", TESTER_POD, "-o", "json", check=False, quiet=True)
        if r.returncode != 0:
            return False, "pod ainda nao criado"
        p = json.loads(r.stdout)
        cs = p["status"].get("containerStatuses", [])
        if cs and all(c.get("ready") for c in cs):
            return True, ""
        naopronto = [c["name"] for c in cs if not c.get("ready")] or ["(criando)"]
        return False, f"containers nao prontos: {naopronto}"

    espera("tester pronto", cond, args.timeout)
    ok(f"{TESTER_POD} no ar (no {_no_do('ueransim')})")

    r = kubectl("logs", TESTER_POD, "-c", "gnb", "--tail=40", check=False, quiet=True)
    if "NG Setup procedure is successful" in r.stdout:
        ok("NG Setup com a AMF concluido")
    else:
        aviso("nao encontrei 'NG Setup procedure is successful' no log do gNB; "
              "o registro pode falhar no passo seguinte")

    _checa_sysctl_rede()


# Piso de buffer de socket para a carga VR nao perder frame por fila cheia.
# 4 MB cobre com folga um frame inteiro em rajada mais o que chega enquanto o
# Python processa o anterior.
RMEM_MIN = 4 << 20


def _checa_sysctl_rede():
    """Quanto de SO_RCVBUF o kernel DE FATO concede a um socket UDP, nos TRES
    nos por onde a carga VR passa: o do tester (cliente), o do mec-app e o do
    remote-app. Com as pontas espalhadas por maquinas diferentes, medir so' o
    tester esconderia metade do problema.

    A pergunta e' sobre net.core.rmem_max/wmem_max, mas ela NAO pode ser feita
    lendo /proc/sys/net/core dentro do pod: como esses sysctl sao globais (nao
    existem por namespace de rede), o runtime de container simplesmente NAO
    expoe o diretorio -- 'cat' devolve "No such file or directory". Ironicamente
    e' a propria ausencia que confirma que sao do no.

    Entao a medida e' o efeito, e nao a causa: abre um socket, pede 8 MB, e ve
    o que voltou. O kernel concede min(pedido, rmem_max) e DOBRA o valor, sem
    avisar de corte nenhum -- pedir 8 MB e receber 416 KB e' silencioso, e sob
    carga alta a fila estoura, o kernel descarta, e a perda aparece no relatorio
    como se fosse do caminho do UPF."""
    # SONDA -- roda dentro do pod e reporta o que o kernel do NO concedeu.
    SONDA = ("import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);"
             "s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,8<<20);"
             "s.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,8<<20);"
             "print(s.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF),"
             "s.getsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF))")

    # Os TRES pontos onde a carga VR entra e sai do kernel. Medir so' o tester
    # deixaria de fora justamente o lado que estoura primeiro: o remote-app
    # esta no nucleo, onde nao ha sudo para levantar o sysctl.
    pontos = [
        ("tester (vr_client)", lambda: kexec(TESTER_POD, "vr-client", "python3",
                                             "-c", SONDA, check=False,
                                             quiet=True, timeout=30)),
    ]
    for papel, deploy in (("mec-app (vr_server)", "free5gc-mec-app"),
                          ("remote-app (vr_server)", "free5gc-remote-app")):
        pontos.append((papel, lambda d=deploy: kubectl(
            "exec", f"deploy/{d}", "-c", "vr-server", "--", "python3", "-c",
            SONDA, check=False, quiet=True, timeout=30)))

    curtos = []
    for descricao, sonda in pontos:
        r = sonda()
        try:
            rcv, snd = (int(x) for x in r.stdout.split())
        except ValueError:
            aviso(f"nao consegui medir o SO_RCVBUF efetivo em {descricao}; nao "
                  "da' para saber se o no vai cortar os buffers da carga VR.")
            continue
        no = _no_do({"tester (vr_client)": "ueransim",
                     "mec-app (vr_server)": "mec-app",
                     "remote-app (vr_server)": "remote-app"}[descricao])
        menor = min(rcv, snd)
        info(f"{descricao:<22} @ {no:<16} rcvbuf={rcv // 1024} kB "
             f"sndbuf={snd // 1024} kB (pedidos 8192 kB)")
        if menor < RMEM_MIN:
            curtos.append((descricao, no, menor))

    if not curtos:
        ok("buffers de socket dimensionados para a carga VR nos tres pontos")
        return

    # A assimetria e' pior que o valor absoluto: se um lado tem buffer e o outro
    # nao, a perda fica desigual entre os caminhos e a guarda do passo 12 barra
    # a execucao -- o que parece resultado do cenario e' o sysctl.
    detalhe = "\n".join(f"         {d} @ {no}: {v // 1024} kB"
                        for d, no, v in curtos)
    aviso(f"buffer de socket abaixo do minimo ({RMEM_MIN // 1024} kB) em "
          f"{len(curtos)} de {len(pontos)} pontos:\n{detalhe}\n"
          "       O que estourar a fila vira 'perda' no relatorio sem ser perda "
          "do UPF -- e se sobrar so' de um lado, a comparacao entre os caminhos\n"
          "       cai por diferenca de perda, nao por diferenca de caminho. "
          "Rode NO NO (sao sysctl globais; o container nem os enxerga):\n"
          "         sudo sysctl -w net.core.rmem_max=16777216 "
          "net.core.wmem_max=16777216\n"
          "       Para nao perder no reboot, grave em "
          "/etc/sysctl.d/99-tg2-vr.conf. Nos nos do nucleo (petshopboys, "
          "metallica), onde\n       nao ha sudo, o jeito e' baixar o perfil "
          "de carga ate' os dois lados perderem igual.")


# --------------------------------------------------------------------------
# 09 sessao PDU
# --------------------------------------------------------------------------
def p09_sessao(args):
    passo(9, "Sessao PDU: interface de tunel com IP do pool da UPF central",
          """Espera a interface de tunel do UE ganhar IP.

    No cenario A o IP e' alocado pela unica UPF, entao um endereco em 60.60.x.x
    ja' e' prova de que o caminho gNB -> N3 -> UPF central fechou inteiro.""")

    def cond():
        r = kexec(TESTER_POD, "ue", "ip", "-4", "-o", "addr", "show", TUN,
                  check=False, quiet=True, timeout=30)
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
        if m:
            return True, m.group(1)
        return False, f"{TUN} ainda sem IP"

    ue_ip = espera("sessao PDU", cond, args.timeout)
    if not ue_ip.startswith(UE_POOL_PREFIX):
        aviso(f"IP do UE {ue_ip} fora do pool esperado {UE_POOL_PREFIX}0.0/16 -- "
              "confira os pools da UPF em scenario-a-cupf/smf.yaml")
    ok(f"{TUN} = {ue_ip}")
    return ue_ip

# --------------------------------------------------------------------------
# 10 rotas
# --------------------------------------------------------------------------
def p10_rotas():
    passo(10, "Rota dos destinos por DENTRO do tunel do UE",
          """Manda os dois destinos pela interface do tunel.

    Sem isso o trafego sai pela eth0 do pod, chega ao destino pela rede do
    Kubernetes e nao passa por UPF nenhum -- o teste mediria a rede do cluster e
    devolveria numeros excelentes e sem nenhum significado.""")
    global MEC_IP, REMOTE_IP
    MEC_IP, REMOTE_IP = _cluster_ip("mec-app"), _cluster_ip("remote-app")
    info(f"ClusterIPs: mec-app={MEC_IP} (dinamico; anunciado ao NEF pelo mec-af), "
         f"remote-app={REMOTE_IP}")

    # Sem isto o trafego sai pela eth0 do pod, chega no destino pela rede do
    # Kubernetes e NAO PASSA POR UPF NENHUM -- o teste mediria a rede do cluster.
    # 'replace' em vez de 'add' para o script ser re-executavel.
    for dest in (MEC_IP, REMOTE_IP):
        kexec(TESTER_POD, "ue", "ip", "route", "replace", f"{dest}/32",
              "dev", TUN, timeout=30)
    r = kexec(TESTER_POD, "ue", "ip", "route", "show", quiet=True, timeout=30)
    for linha in r.stdout.splitlines():
        if MEC_IP in linha or REMOTE_IP in linha:
            print(f"       {linha.strip()}")
    if TUN not in r.stdout:
        raise Falha(f"rotas nao apontam para {TUN}")
    ok("mec-app e remote-app roteados pelo tunel")


# --------------------------------------------------------------------------
# contadores GTP
# --------------------------------------------------------------------------
def contadores_gtp(deploy):
    """RX/TX (bytes, pacotes) da interface do gtp5g dentro do pod do UPF."""
    r = kubectl("exec", f"deploy/{deploy}", "--", "cat", "/proc/net/dev",
                check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        raise Falha(f"nao consegui ler /proc/net/dev em {deploy}: {r.stderr.strip()}")
    ifaces = {}
    for linha in r.stdout.splitlines():
        m = re.match(r"\s*([^:]+):\s*(.*)$", linha)
        if not m:
            continue
        campos = m.group(2).split()
        if len(campos) >= 10:
            ifaces[m.group(1).strip()] = {
                "rx_bytes": int(campos[0]), "rx_pkts": int(campos[1]),
                "tx_bytes": int(campos[8]), "tx_pkts": int(campos[9]),
            }
    if GTP_IF not in ifaces:
        raise Falha(f"interface '{GTP_IF}' nao existe em {deploy}. "
                    f"Interfaces vistas: {sorted(ifaces)}.\n"
                    "       Sem ela o gtp5g nao criou o plano de dados "
                    "(modulo carregado no no? 'lsmod | grep gtp5g')")
    return ifaces[GTP_IF]


def contadores_tun():
    """RX/TX da uesimtun0, a interface de tunel do UE dentro do pod do tester.

    Fecha um ponto cego do diagnostico: se a upfgtp da UPF central nao contar o
    trafego, o contador da UPF sozinho nao distingue "o UE parou de emitir" de
    "o UE emitiu e o pacote sumiu antes da UPF". O tx daqui e' o que o UE de
    fato colocou no tunel."""
    r = kexec(TESTER_POD, "ue", "cat", "/proc/net/dev", check=False, quiet=True,
              timeout=30)
    for linha in r.stdout.splitlines():
        m = re.match(r"\s*" + TUN + r":\s*(.*)$", linha)
        if m:
            c = m.group(1).split()
            if len(c) >= 10:
                return {"rx_bytes": int(c[0]), "rx_pkts": int(c[1]),
                        "tx_bytes": int(c[8]), "tx_pkts": int(c[9])}
    return None


def delta(antes, depois):
    return {k: depois[k] - antes[k] for k in antes}


def vr_client(alvo_ip, ue_ip, duracao, label, warmup, csv=None, jsonf=None,
              timeout_extra=60, pose_hz=None):
    cmd = ["python3", "/opt/vr/vr_client.py",
           "--server", f"{alvo_ip}:{VR_PORT}", "--bind", ue_ip,
           "--duration", str(duracao), "--warmup", str(warmup), "--label", label]
    # A pose faz parte do PERFIL (a malha de controle do caso de uso), entao
    # vem por argumento e nao do VR_POSE_HZ do container -- senao trocar de
    # cenario mudaria a midia e deixaria o uplink no valor de outro caso.
    if pose_hz:
        cmd += ["--pose-hz", str(pose_hz)]
    if csv:
        cmd += ["--csv", csv]
    if jsonf:
        cmd += ["--json", jsonf]
    r = kexec(TESTER_POD, "vr-client", *cmd, check=False,
              timeout=duracao + timeout_extra)
    try:
        bruto = r.stdout
        resumo = json.loads(bruto[bruto.index("{"):bruto.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        raise Falha(f"vr_client nao devolveu JSON (rc={r.returncode}).\n"
                    f"       stdout: {r.stdout.strip()[:400]}\n"
                    f"       stderr: {r.stderr.strip()[:400]}")
    return resumo


def metricas_servidor(deploy):
    """Le o /metrics do vr-server DE UMA VEZ e soma as series de cada metrica.

    Um unico 'kubectl exec' por leitura: com uma chamada por metrica, as duas
    leituras (antes e depois da corrida) esticariam a janela dos contadores
    para muito alem da corrida, e as taxas derivadas deles sairiam diluidas."""
    r = kubectl("exec", f"deploy/{deploy}", "-c", "vr-server", "--", "python3", "-c",
                "import urllib.request as u;"
                "print(u.urlopen('http://127.0.0.1:9101/metrics').read().decode())",
                check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    vals = {}
    for linha in r.stdout.splitlines():
        if linha.startswith("#") or not linha.strip():
            continue
        nome = linha.split("{", 1)[0].split(None, 1)[0]
        try:
            vals[nome] = vals.get(nome, 0.0) + float(linha.rsplit(None, 1)[1])
        except (IndexError, ValueError):
            pass
    return vals


def _d(antes, depois, nome):
    """Delta de um contador entre duas leituras; None se faltou alguma."""
    if not antes or not depois or nome not in antes or nome not in depois:
        return None
    return depois[nome] - antes[nome]


def fps_alvo(deploy):
    """VR_FPS declarado no deployment; 90 e' o default do vr_server."""
    r = kubectl("get", "deploy", deploy, "-o",
                "jsonpath={.spec.template.spec.containers[?(@.name=='vr-server')]"
                ".env[?(@.name=='VR_FPS')].value}", check=False, quiet=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 90.0




# --------------------------------------------------------------------------
# 11 prova da ancoragem central
# --------------------------------------------------------------------------
def p11_prova_ancora(ue_ip, args):
    passo(11, "PROVA DA ANCORAGEM CENTRAL (o teste que define o cenario A)",
          """Gera trafego para o mec-app e depois para o remote-app, lendo o
    contador da interface GTP da UPF central antes e depois de cada corrida.

    E' o espelho da prova do cenario B. La', o PSA-UPF tinha que ficar PARADO
    sob trafego MEC. Aqui NAO existe breakout: a UPF central tem que contar os
    DOIS trafegos -- sob trafego para o mec-app ela sobe tanto quanto sob
    trafego para o remote-app. O pacote do MEC atravessa o backhaul ate' o
    nucleo e volta para a borda. Esse trombone e' exatamente o que o cenario B
    elimina.

    Se a UPF central ficar parada sob trafego MEC, algum caminho alternativo
    existe -- e so' poderia ser plano de usuario do cenario B ainda no ar.""")

    resultados = {}
    for nome, alvo in (("mec", MEC_IP), ("remoto", REMOTE_IP)):
        antes = {k: contadores_gtp(d) for k, (d, _) in UPFS.items()}
        info(f"gerando {args.prova_duracao}s de trafego para {alvo} ({nome})")
        resumo = vr_client(alvo, ue_ip, args.prova_duracao, f"prova-{nome}",
                           warmup=1, pose_hz=PERFIS[args.perfil]["pose_hz"])
        depois = {k: contadores_gtp(d) for k, (d, _) in UPFS.items()}
        d = {k: delta(antes[k], depois[k]) for k in antes}
        resultados[nome] = {"delta": d, "frames": resumo["frames_complete"],
                            "poses": resumo.get("ul_packets_tx")}

        if not resumo["frames_complete"]:
            raise Falha(
                f"nenhum frame completo voltou de {alvo}. O plano de dados nao "
                "esta passando.\n"
                "       Suspeitos, nesta ordem: (a) rota do tunel (passo 10); "
                "(b) ip_forward=0 na UPF;\n"
                "       (c) gtp5g ausente no no; (d) o pod alvo nao esta pronto;\n"
                "       (e) a regra de Traffic Influence do mec-af mexeu na sessao -- "
                f"kubectl -n {NS} logs deploy/free5gc-smf | grep -i influence")

        u = d["upf"]
        print(f"       {nome:<7} upf       rx={u['rx_pkts']:>8} pkts / "
              f"{u['rx_bytes']/1e6:>8.2f} MB   "
              f"tx={u['tx_pkts']:>8} pkts / {u['tx_bytes']/1e6:>8.2f} MB")
        print()

    for nome, rotulo in (("mec", "trafego MEC"), ("remoto", "trafego remoto")):
        rx = resultados[nome]["delta"]["upf"]["rx_pkts"]
        poses = resultados[nome]["poses"]
        if rx == 0:
            raise Falha(
                f"a UPF central ficou PARADA sob {rotulo}: o trafego nao passou por ela.\n"
                "       No cenario A so' existe esse caminho. Suspeitos: sobrou "
                "free5gc-i-upf ou free5gc-psa-upf do cenario B,\n"
                "       ou o SMF subiu com o config do B (o passo 07 devia ter pego).")
        if poses and rx < 0.9 * poses:
            raise Falha(
                f"a UPF central viu {rx} pacotes sob {rotulo}, contra {poses} poses "
                f"enviadas ({rx / poses * 100:.0f}%).\n"
                "       Parte do uplink passou por outro caminho ou se perdeu antes "
                "da ancora.")

    upf_mec = resultados["mec"]["delta"]["upf"]["rx_pkts"]
    upf_rem = resultados["remoto"]["delta"]["upf"]["rx_pkts"]
    ok(f"ANCORAGEM CENTRAL CONFIRMADA: a UPF central viu {upf_mec} pkts sob "
       f"trafego MEC e {upf_rem} sob trafego remoto -- o trafego de borda sobe "
       "ao nucleo")
    return resultados

# --------------------------------------------------------------------------
# 12 campanha
# --------------------------------------------------------------------------
# Caminhos medidos. A ORDEM em que sao medidos alterna a cada execucao (ver
# p12_campanha): rodar sempre mec-antes-de-remoto faria qualquer deriva ao
# longo da execucao (cache quente, termica, um pod vizinho acordando) cair
# sempre no mesmo lado, e ela apareceria na tabela como diferenca entre os caminhos.
CAMINHOS = (("a-mec", "mec", "free5gc-mec-app"),
            ("a-remoto", "remoto", "free5gc-remote-app"))

# Diferenca de perda entre os dois caminhos, em pontos percentuais, acima da
# qual a COMPARACAO de latencia deixa de valer. O motivo e' vies de
# sobrevivencia: so' frames COMPLETOS geram amostra de latencia, entao o
# caminho que perde mais tem suas amostras filtradas justamente nos instantes
# de fila cheia -- e sai com latencia artificialmente melhor. Comparar 0,1% com
# 4% de perda nao e' comparar dois caminhos, e' comparar duas amostras
# diferentes.
LIMIAR_DIF_PERDA_PP = 1.0

# Fracao da janela pedida que precisa ter tido downlink. Abaixo disso o fluxo
# foi interrompido, e nem a perda nem a vazao denunciam isso sozinhas.
LIMIAR_CONTINUIDADE_PCT = 95.0

# Acima desta fracao de frames atrasados o relatorio comenta que o pacing esta'
# apertado. NAO invalida a corrida: veja o comentario em _avaliar_corrida.
LIMIAR_FRAMES_LATE_PCT = 1.0

# Descarte por fila cheia (socket do cliente ou netns do tester) que a corrida
# tolera antes de deixar de valer, em % do downlink recebido. Abaixo disso a
# perda e' residual e nao move os percentis; acima, a medida passa a descrever
# o medidor.
LIMIAR_DESCARTE_LOCAL_PCT = 0.5


def p12_campanha(ue_ip, args, idx=1):
    passo(12, f"Campanha de medicao VR ({args.duracao}s por caminho)",
          """Roda a carga VR de verdade contra os dois destinos, com o mesmo perfil.

    Reporta o net_rtt (ida do uplink + volta do downlink -- a parcela que o
    posicionamento do UPF ataca) separado do m2p (motion-to-photon, o que o usuario sente e
    que inclui a espera pelo proximo frame). Reportar so' um dos dois engana:
    o m2p sozinho dilui o efeito, o net_rtt sozinho esconde a experiencia.

    A ordem dos dois caminhos ALTERNA a cada execucao, para que nenhuma deriva
    ao longo da execucao caia sempre no mesmo lado.

    Depois de medir, confere se a corrida MEDIU A REDE: se o gerador sustentou
    a cadencia, se ele conseguiu entregar todos os pacotes ao kernel, se o
    kernel do cliente nao descartou nada por fila cheia e se os dois caminhos
    perderam quantidades parecidas. Falhou qualquer um: o ponto e' sobre o
    testbed, nao sobre o UPF.""")
    if args.so_prova:
        info("pulado (--so-prova)")
        return {}

    # --caminhos mec: a campanha A x B compara so' o caminho MEC dos dois
    # cenarios, e o remoto custaria uma corrida inteira por execucao sem entrar
    # na conta. A guarda de perda entre caminhos (_avaliar_par) sai sozinha.
    medir = [c for c in CAMINHOS
             if getattr(args, "caminhos", "todos") == "todos" or c[1] == "mec"]
    ordem = medir if idx % 2 else list(reversed(medir))
    info("ordem desta execucao: " + " -> ".join(n for n, _, _ in ordem))
    ips = {"mec": MEC_IP, "remoto": REMOTE_IP}   # resolvidos no passo 10

    campanha = {}
    for pos, (nome, chave, deploy) in enumerate(ordem, 1):
        alvo = ips[chave]
        m0 = metricas_servidor(deploy)
        # Contadores GTP da UPF central tambem na campanha, e nao so' na prova
        # do passo 11: se o uplink morrer no meio da corrida, estes deltas
        # separam "o UE parou de emitir" de "a UPF parou de receber" de "a UPF
        # recebeu e nao entregou ao servidor".
        g0 = {k: contadores_gtp(d) for k, (d, _) in UPFS.items()}
        g0["ue-tun"] = contadores_tun()
        info(f"{nome}: {args.duracao}s contra {alvo}")
        resumo = vr_client(alvo, ue_ip, args.duracao, nome, warmup=args.warmup,
                           csv=f"/data/{nome}.csv", jsonf=f"/data/{nome}.json",
                           pose_hz=PERFIS[args.perfil]["pose_hz"])
        m1 = metricas_servidor(deploy)
        g1 = {k: contadores_gtp(d) for k, (d, _) in UPFS.items()}
        g1["ue-tun"] = contadores_tun()
        resumo["_gtp"] = {k: delta(g0[k], g1[k])
                          for k in g0 if g0[k] and g1.get(k)}

        resumo["_ordem"] = pos
        resumo["_srv"] = srv = {
            k: _d(m0, m1, f"vr_server_{k}") for k in (
                "frames_sent_total", "frame_packets_total", "frames_late_total",
                "frames_truncated_total", "send_dropped_total",
                # As duas que faltavam quando o downlink do caminho remoto
                # morreu na metade da primeira corrida no brix. O servidor so'
                # emite frame enquanto a sessao existe, e a sessao morre depois
                # de --session-timeout sem pose: comparar as poses que o cliente
                # ENVIOU com as que o servidor RECEBEU diz, em um numero, se o
                # que quebrou foi o uplink.
                "pose_packets_total", "sessions_expired_total")
        }
        srv["pace_window_seconds"] = (m1 or {}).get("vr_server_pace_window_seconds")
        srv["sndbuf_bytes"] = (m1 or {}).get("vr_server_sock_sndbuf_bytes")

        # fps que o servidor REALMENTE emitiu. O frames_late sozinho nao basta:
        # um servidor pode emitir MENOS frames do que devia e ainda se declarar
        # pontual, e ai' a latencia medida e' de outra carga, nao da configurada.
        # O divisor e' a janela do uplink (quando a sessao existiu no servidor),
        # e nao o relogio de parede do cliente, que inclui a drenagem final.
        janela = resumo.get("ul_window_s") or resumo["duration_s"]
        resumo["_fps_servidor"] = (
            None if srv["frames_sent_total"] is None or not janela
            else srv["frames_sent_total"] / janela)
        # Perda EXATA: denominador = pacotes que o servidor entregou ao kernel.
        # A do cliente e' um piso, porque um frame perdido inteiro nao entra no
        # intervalo de sequencia que ele consegue observar.
        pk = srv["frame_packets_total"]
        resumo["dl_packet_loss_srv_pct"] = (
            None if not pk else
            round(max(0.0, 1 - resumo["dl_packets_rx_run"] / pk) * 100, 4))
        campanha[nome] = resumo
        _avaliar_corrida(nome, deploy, resumo, srv, args)

    _avaliar_par(campanha)
    return campanha


def _avaliar_corrida(nome, deploy, resumo, srv, args):
    """Guardas de UMA corrida. Cada uma responde 'esta medida e' da rede?'."""
    net, m2p = resumo["net_rtt_us"], resumo["m2p_us"]
    saude = resumo.get("saude", {})
    perda = resumo.get("dl_packet_loss_srv_pct")
    if perda is None:
        perda = resumo["dl_packet_loss_pct"]
    print(f"       net_rtt p50={num(net['p50'])} us  p95={num(net['p95'])} us"
          f" | m2p p50={num(m2p['p50'])} us"
          f" | hold p50={num(resumo.get('hold_us', {}).get('p50'))} us"
          f" | perda={num(perda, 3)}%"
          f" | dl={num(resumo['dl_throughput_mbps'], 2)} Mbps"
          f" | continuidade={num(resumo.get('dl_continuity_pct'), 1)}%")

    # Ordem dos pontos ao longo do caminho, para a linha ser lida da esquerda
    # (UE) para a direita (nucleo).
    gtp = resumo.get("_gtp") or {}
    if gtp:
        print("       caminho " + "   ".join(
            f"{k}: rx={gtp[k]['rx_pkts']} tx={gtp[k]['tx_pkts']}"
            for k in ("ue-tun", "upf") if k in gtp))

    # As poses que SAIRAM do cliente contra as que CHEGARAM ao servidor. E' a
    # medida direta do uplink, e a unica que separa "o gerador parou" de "o
    # caminho parou" -- a perda do downlink nao enxerga isso.
    env, rec = resumo.get("ul_packets_tx"), srv.get("pose_packets_total")
    if env and rec is not None and rec < 0.95 * env:
        aviso(f"{nome}: o servidor recebeu {rec:.0f} das {env} poses enviadas "
              f"({rec / env * 100:.0f}%). O UPLINK deste caminho nao entregou; "
              "compare os contadores GTP acima para achar em que salto parou.",
              escopo="campanha")

    alvo_fps = fps_alvo(deploy)
    real = resumo.get("_fps_servidor")
    if real is not None and real < 0.9 * alvo_fps:
        aviso(f"{nome}: o servidor emitiu {real:.0f} fps contra os "
              f"{alvo_fps:.0f} configurados. A carga que trafegou nao e' a "
              "que voce pediu, entao a latencia desta corrida nao e' "
              "comparavel com a do outro caminho.", escopo="campanha")

    # Continuidade: a guarda que faltava. Um servidor que PARA de emitir nao
    # deixa buraco de sequencia, entao a perda de pacote continua zero e a
    # corrida passa despercebida por todas as outras guardas.
    cont = resumo.get("dl_continuity_pct")
    if cont is not None and cont < LIMIAR_CONTINUIDADE_PCT:
        j = resumo.get("janela", {})
        aviso(f"{nome}: o downlink so' existiu em {cont:.0f}% da janela "
              f"({j.get('span_s')}s de {j.get('nominal_s')}s pedidos) -- o fluxo "
              "foi INTERROMPIDO no meio, nao e' perda de pacote. Veja "
              "sessions_expired e pose_packets abaixo para saber se o que caiu "
              "foi o uplink.", escopo="campanha")

    # Sessao expirada = o servidor ficou --session-timeout sem receber pose.
    if srv.get("sessions_expired_total"):
        env = resumo.get("ul_packets_tx")
        rec = srv.get("pose_packets_total")
        detalhe = ""
        if env and rec is not None:
            detalhe = (f" O cliente enviou {env} poses e o servidor recebeu "
                       f"{rec:.0f} ({rec / env * 100:.0f}%).")
        aviso(f"{nome}: a sessao expirou {srv['sessions_expired_total']:.0f} vez(es) "
              "no servidor -- ele ficou sem receber pose por mais que o "
              f"--session-timeout e parou de emitir frames.{detalhe} O problema "
              "esta' no UPLINK do caminho, nao no gerador.", escopo="campanha")

    if srv["frames_late_total"] is None:
        aviso(f"{nome}: nao consegui ler /metrics do {deploy}. Sem isso a "
              "regra de descarte nao se aplica -- nao da' para saber se o "
              "gargalo foi o gerador Python ou o caminho de rede.",
              escopo="campanha")
    elif srv["frames_late_total"]:
        # frames_late conta os ciclos em que o tx_loop estourou o periodo. Com
        # o pacing ocupando 80% do periodo isso acontece com facilidade -- e
        # NAO quer dizer que a carga deixou de trafegar: o relogio do gerador e'
        # absoluto, entao um ciclo que atrasa e' compensado pelo seguinte e a
        # taxa media se mantem.
        #
        # Medido a 50 Mbps/90 fps: 371 frames tarde em 5400 (6,9%) numa corrida
        # que entregou 90,0 fps, 50,10 Mbps, 100% de continuidade e 0,010% de
        # perda. Invalidar isso era jogar fora uma medida boa.
        #
        # Quem responde "a carga configurada trafegou?" sao o fps entregue, a
        # continuidade e a perda -- todos guardas proprias acima. Aqui fica so'
        # o registro, porque o atraso do gerador entra no hold (e sai do
        # net_rtt na subtracao) e e' identico nos dois caminhos.
        enviados = srv.get("frames_sent_total") or 0
        frac = srv["frames_late_total"] / enviados * 100 if enviados else 100.0
        msg = (f"{nome}: {srv['frames_late_total']:.0f} frames atrasados em "
               f"{enviados:.0f} ({frac:.2f}%)")
        if frac > LIMIAR_FRAMES_LATE_PCT:
            info(msg + " -- o pacing esta' apertado neste perfil. Nao invalida "
                 "a corrida (quem decide isso e' o fps entregue, a continuidade "
                 "e a perda); para folgar, baixe VR_PACE_DUTY.")
        else:
            info(msg + " -- dentro do ruido de escalonamento do no.")

    # Pacotes que o SERVIDOR nunca entregou ao kernel: nao sao perda de rede, e
    # sem esta guarda entrariam na conta como se fossem.
    if srv.get("send_dropped_total"):
        aviso(f"{nome}: o vr-server nao conseguiu enfileirar "
              f"{srv['send_dropped_total']:.0f} pacotes (sndbuf cheio). A perda "
              "desta corrida nasceu no gerador, nao no caminho do UPF.",
              escopo="campanha")

    # Descartes de fila cheia, do socket do cliente e do netns do tester. Os
    # dois entram como FRACAO dos pacotes recebidos, e nao como "qualquer valor
    # acima de zero invalida": a 50 Mbps sao ~313 mil pacotes por corrida, e
    # 94 descartes (0,03%) nao movem percentil nenhum -- descartar a execucao
    # por causa deles jogava fora uma medida boa. O que de fato compromete a
    # comparacao e' perda MATERIAL, e mais ainda perda material DESIGUAL entre
    # os caminhos, que tem guarda propria em _avaliar_par.
    recebidos = resumo.get("dl_packets_rx_run") or 0

    def _fracao(n):
        return (n / recebidos * 100) if recebidos else 100.0

    ovfl = saude.get("dl_sock_drops")
    if ovfl is None:
        ovfl = saude.get("dl_sock_overflow_pkts")
    if ovfl:
        f = _fracao(ovfl)
        msg = (f"{nome}: o kernel do cliente descartou {ovfl} pacotes por fila "
               f"cheia do socket ({f:.3f}% do downlink)")
        if f > LIMIAR_DESCARTE_LOCAL_PCT:
            aviso(msg + ". O gargalo e' o vr_client, nao a rede. Levante "
                  "net.core.rmem_max no no ou baixe a carga.", escopo="campanha")
        else:
            info(msg + " -- residual; nao invalida a corrida.")
    if saude.get("udp_rcvbuf_errors"):
        n = saude["udp_rcvbuf_errors"]
        f = _fracao(n)
        msg = (f"{nome}: {n} estouros de buffer UDP no namespace do tester "
               f"({f:.3f}% do downlink); como o vr-client divide o netns com o "
               "nr-gnb e o nr-ue, e' perda DENTRO do UERANSIM")
        if f > LIMIAR_DESCARTE_LOCAL_PCT:
            aviso(msg + ". Nessa magnitude ela distorce os percentis: baixe a "
                  "carga ou levante net.core.rmem_max no no.", escopo="campanha")
        else:
            info(msg + " -- residual; nao invalida a corrida.")

    hz = resumo.get("ul_pose_hz_real")
    if hz is not None and hz < 0.9 * resumo["pose_hz"]:
        aviso(f"{nome}: o uplink de pose correu a {hz:.0f} Hz contra os "
              f"{resumo['pose_hz']:.0f} pedidos -- o cliente nao sustentou o "
              "proprio envio, e o m2p sai inflado por pose velha.",
              escopo="campanha")

    if abs(saude.get("clock_drift_us") or 0) > 1000:
        aviso(f"{nome}: o CLOCK_REALTIME andou {saude['clock_drift_us']:.0f} us "
              "alem do monotonico durante a corrida (ajuste de NTP). As "
              "amostras de latencia estao deslocadas.", escopo="campanha")

    if saude.get("rx_timestamp_kernel") is False:
        aviso(f"{nome}: sem carimbo de tempo do kernel no cliente. A latencia "
              "reportada inclui o tempo que o vr_client passou fora da CPU.")


def _avaliar_par(campanha):
    """A guarda que so' faz sentido com os DOIS caminhos na mao."""
    a, b = campanha.get("a-mec"), campanha.get("a-remoto")
    if not a or not b:
        return
    pa = a.get("dl_packet_loss_srv_pct")
    pb = b.get("dl_packet_loss_srv_pct")
    if pa is None or pb is None:
        pa, pb = a["dl_packet_loss_pct"], b["dl_packet_loss_pct"]
    if abs(pa - pb) > LIMIAR_DIF_PERDA_PP:
        aviso(f"perda muito diferente entre os caminhos ({pa:.2f}% no MEC contra "
              f"{pb:.2f}% no remoto). So' frames COMPLETOS viram amostra de "
              "latencia, entao o caminho que perde mais some justamente com as "
              "amostras dos instantes de fila cheia e sai parecendo melhor do "
              "que e'. A comparacao desta execucao nao vale.", escopo="campanha")


# --------------------------------------------------------------------------
# 13 coleta
# --------------------------------------------------------------------------
def p13_coleta(args, campanha=None):
    passo(13, "Coleta dos resultados",
          """Traz os CSV (uma linha por frame) e os JSON de resumo de dentro do pod para
    a maquina local, que e' o insumo dos graficos de distribuicao.

    Junto vai um resumo-completo.json com o que o cliente NAO sabe: os deltas
    dos contadores do servidor e a ordem em que os dois caminhos correram. O
    JSON que o proprio cliente escreve dentro do pod e' gravado antes disso
    existir, entao sozinho ele nao explica um descarte.""")
    if args.so_prova:
        info("pulado (--so-prova)")
        return
    os.makedirs(args.saida, exist_ok=True)
    # Destino RELATIVO, de dentro da pasta: no Windows o kubectl le
    # "C:\Users\..." como <pod>:<caminho> e recusa a copia ("one of src or
    # dest must be a local file specification").
    r = run(["kubectl", "-n", NS, "cp", f"{TESTER_POD}:/data", ".",
             "-c", "vr-client"], check=False, timeout=180, cwd=args.saida)
    if r.returncode != 0:
        aviso(f"kubectl cp falhou: {r.stderr.strip()[:200]}")
        return
    if campanha:
        with open(os.path.join(args.saida, "resumo-completo.json"), "w", encoding="utf-8") as fh:
            json.dump(campanha, fh, indent=2)
    arquivos = sorted(os.listdir(args.saida))
    ok(f"{len(arquivos)} arquivo(s) em {args.saida}: {', '.join(arquivos)}")


# --------------------------------------------------------------------------
# 14 derrubada
# --------------------------------------------------------------------------
def _pods_do_cenario():
    """Pods criados pelos nossos Deployments/StatefulSet (prefixo free5gc-)."""
    r = kubectl("get", "pods", "-o",
                "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
                check=False, quiet=True)
    return [p for p in r.stdout.split() if p.startswith("free5gc-")]


def derrubar(args):
    """Apaga Deployments e StatefulSet do cenario. O NAMESPACE NAO E' TOCADO.

    A remocao e' por NOME -- nunca 'kubectl delete -f arquivo' e nunca '--all'.
    Assim nao ha como levar junto um objeto que nao seja nosso: o namespace
    free5gc ja' existe no cluster, nao pertence a este experimento e nao pode
    ser recriado (a conta do testbed nem tem permissao para isso).

    Services, ConfigMaps e o PVC do Mongo ficam de pe' de proposito: nao
    influenciam a medicao, e preservar o PVC mantem os assinantes carregados
    entre uma execucao e a seguinte."""
    passo(14, "Derrubando o cenario (deployments e statefulset)",
          """Cada repeticao da campanha precisa comecar do zero. Sem derrubar, a
    execucao seguinte mediria um core que ja' esta' de pe' ha' muito tempo, com
    caches quentes e sessoes antigas -- e as repeticoes deixariam de ser
    independentes entre si.

    So' Deployments e o StatefulSet saem, e sempre por nome. Services,
    ConfigMaps e o PVC do Mongo continuam; o namespace nunca e' tocado.""")
    alvos = DEPLOYS + DEPLOYS_CENARIO_B
    kubectl("delete", "deploy", *alvos, "--ignore-not-found=true",
            "--wait=false", check=False, quiet=True)
    kubectl("delete", "statefulset", TESTER_STS, "--ignore-not-found=true",
            "--wait=false", check=False, quiet=True)

    def cond():
        restantes = _pods_do_cenario()
        if not restantes:
            return True, ""
        return False, f"{len(restantes)} pod(s) ainda terminando"

    try:
        espera("pods encerrarem", cond, args.timeout_derrubada, intervalo=5)
        ok("deployments e statefulset removidos; namespace preservado")
    except Falha:
        aviso("nem todos os pods terminaram a tempo; a proxima execucao pode "
              "comecar com residuo da anterior")


# --------------------------------------------------------------------------
# relatorio de UMA execucao
# --------------------------------------------------------------------------
def num(v, casas=1):
    """Arredonda para a tabela. Sem isto um p95 tipo 20402.41999999998 estoura
    a largura da coluna e gruda no numero seguinte."""
    return "-" if v is None else f"{v:.{casas}f}"


def resumo_execucao(res):
    """Resumo compacto de uma execucao -- numa campanha de 10 o relatorio
    completo por execucao inundaria o terminal."""
    prova = res["prova"]
    upf_mec = prova["mec"]["delta"]["upf"]["rx_pkts"]
    upf_rem = prova["remoto"]["delta"]["upf"]["rx_pkts"]
    print(f"\n  Prova da ancoragem central: UPF viu {upf_mec} pkts sob trafego MEC "
          f"e {upf_rem} sob trafego remoto")

    c = res["campanha"]
    if not c:
        return
    print(f"    {'caminho':<12}{'net p50':>11}{'net p95':>11}{'m2p p50':>11}"
          f"{'hold p50':>11}{'loss %':>9}{'cont %':>8}{'Mbps':>8}{'fps':>6}{'drops':>7}")
    for nome in ("a-mec", "a-remoto"):
        s = c.get(nome)
        if not s:
            continue
        perda = s.get("dl_packet_loss_srv_pct")
        if perda is None:
            perda = s["dl_packet_loss_pct"]
        sa = s.get("saude", {})
        ovfl = sa.get("dl_sock_drops")
        if ovfl is None:
            ovfl = sa.get("dl_sock_overflow_pkts")
        print(f"    {nome:<12}{num(s['net_rtt_us']['p50']):>11}"
              f"{num(s['net_rtt_us']['p95']):>11}{num(s['m2p_us']['p50']):>11}"
              f"{num(s.get('hold_us', {}).get('p50')):>11}"
              f"{num(perda, 2):>9}"
              f"{num(s.get('dl_continuity_pct'), 1):>8}"
              f"{num(s['dl_throughput_mbps'], 2):>8}"
              f"{num(s.get('_fps_servidor'), 0):>6}"
              f"{('-' if ovfl is None else ovfl):>7}")
    mec = c.get("a-mec", {}).get("net_rtt_us", {}).get("p50")
    rem = c.get("a-remoto", {}).get("net_rtt_us", {}).get("p50")


# --------------------------------------------------------------------------
# agregacao da campanha
# --------------------------------------------------------------------------
# (rotulo, caminho dentro do resumo do vr_client, divisor, unidade, casas,
#  menor_e_melhor). menor_e_melhor=None marca a linha como informativa: nao faz
# sentido falar em "ganho" de vazao, que por construcao e' igual nos dois lados.
KPIS = [
    ("Atraso de rede (media)",   ("net_rtt_us", "mean"), 1000.0, "ms", 3, True),
    ("Atraso de rede p50",       ("net_rtt_us", "p50"),  1000.0, "ms", 3, True),
    ("Atraso de rede p95",       ("net_rtt_us", "p95"),  1000.0, "ms", 3, True),
    ("Atraso de rede p99",       ("net_rtt_us", "p99"),  1000.0, "ms", 3, True),
    ("Motion-to-photon (media)", ("m2p_us", "mean"),     1000.0, "ms", 3, True),
    ("Motion-to-photon p50",     ("m2p_us", "p50"),      1000.0, "ms", 3, True),
    ("Motion-to-photon p95",     ("m2p_us", "p95"),      1000.0, "ms", 3, True),
    ("Jitter de rede",           ("jitter_net_us",),        1.0, "us", 1, True),
    ("Jitter motion-to-photon",  ("jitter_us",),            1.0, "us", 1, True),
    # Tempo DENTRO do servidor. Nao e' KPI de rede: entra na tabela para o
    # leitor conferir que m2p = net + hold e enxergar quanto do m2p e' a janela
    # de pacing do gerador (identica nos dois lados) e nao o caminho.
    ("Tempo no servidor p50",    ("hold_us", "p50"),     1000.0, "ms", 3, None),
    ("Perda de pacotes DL",      ("dl_packet_loss_srv_pct",), 1.0, "%",  3, True),
    ("Continuidade do DL",       ("dl_continuity_pct",),      1.0, "%",  2, None),
    ("Frames incompletos",       ("frames_incomplete_pct",),  1.0, "%",  3, True),
    ("Vazao DL",                 ("dl_throughput_mbps",),   1.0, "Mbps", 2, None),
]


def _valor(resumo, caminho):
    v = resumo
    for chave in caminho:
        if not isinstance(v, dict):
            return None
        v = v.get(chave)
    return v if isinstance(v, (int, float)) else None


def _media_dp(valores):
    """Media e desvio-padrao amostral. Com uma execucao so' o dp e' 0 -- o que
    e' honesto: nao ha dispersao medida, nao ha dispersao a reportar."""
    vs = [v for v in valores if v is not None]
    if not vs:
        return None, None
    media = sum(vs) / len(vs)
    if len(vs) < 2:
        return media, 0.0
    var = sum((v - media) ** 2 for v in vs) / (len(vs) - 1)
    return media, var ** 0.5


def linhas_kpi(execucoes):
    """Uma linha por KPI: (rotulo, (mec, dp), (remoto, dp), ganho, unidade, casas).

    O ganho e' PAREADO: a diferenca e' calculada DENTRO de cada execucao e so'
    depois agregada (media +- desvio das diferencas). As duas corridas de uma
    execucao veem o mesmo cluster, no mesmo estado, com minutos de distancia --
    entao a variacao que existe ENTRE execucoes (deploy novo, pods em outro
    lugar da fila do escalonador) e' comum as duas e se cancela na subtracao.
    Subtrair medias de execucoes diferentes jogaria essa variacao inteira dentro
    da barra de erro do ganho, e um efeito real de centenas de microssegundos
    poderia sumir dentro dela."""
    linhas = []
    for rotulo, caminho, div, unidade, casas, menor_melhor in KPIS:
        cel = {}
        for lado in ("a-mec", "a-remoto"):
            vs = [_valor(e["campanha"].get(lado, {}), caminho) for e in execucoes]
            m, dp = _media_dp(vs)
            cel[lado] = (None if m is None else m / div,
                         None if dp is None else dp / div)
        ganho = None
        if menor_melhor:
            difs, pcts = [], []
            for e in execucoes:
                mec = _valor(e["campanha"].get("a-mec", {}), caminho)
                rem = _valor(e["campanha"].get("a-remoto", {}), caminho)
                if mec is None or not rem:
                    continue
                difs.append((rem - mec) / div)
                pcts.append((1 - mec / rem) * 100)
            if difs:
                md, dpd = _media_dp(difs)
                ganho = (md, dpd, sum(pcts) / len(pcts), len(difs))
        linhas.append((rotulo, cel["a-mec"], cel["a-remoto"], ganho, unidade, casas))
    return linhas


def tabela_kpis(execucoes):
    print(f"\n  KPIs de {len(execucoes)} execucao(oes) agregada(s) "
          f"-- media +- desvio-padrao ENTRE execucoes:\n")
    print(f"    {'KPI':<26}{'MEC via nucleo':>21}{'Caminho remoto':>21}")
    print(f"    {'-' * 26}{'-' * 21}{'-' * 21}")
    for rotulo, (m, mdp), (r, rdp), ganho, un, c in linhas_kpi(execucoes):
        cm = "-" if m is None else f"{m:.{c}f}+-{mdp:.{c}f} {un}"
        cr = "-" if r is None else f"{r:.{c}f}+-{rdp:.{c}f} {un}"
        print(f"    {rotulo:<26}{cm:>21}{cr:>21}")
    print(f"\n    {CINZA}No cenario A os dois caminhos passam pela mesma UPF central. "
          f"A comparacao com o cenario B sai de campanha-a-vs-b.py.{RESET}")


COLUNAS_EXEC = [
    "cenario", "execucao", "caminho", "ordem_na_execucao",
    "net_mean_us", "net_p50_us", "net_p95_us",
    "net_p99_us", "net_min_us", "net_max_us", "m2p_mean_us", "m2p_p50_us",
    "m2p_p95_us", "m2p_p99_us", "hold_p50_us", "jitter_net_us", "jitter_m2p_us",
    "dl_loss_pct", "dl_loss_srv_pct", "dl_continuidade_pct",
    "frames_incompletos_pct", "dl_mbps",
    "fps_servidor", "frames_completos", "frames_em_estatistica",
    # Saude da medida: sem estas colunas nao da' para defender, depois, que a
    # linha mediu a rede e nao o proprio medidor.
    "srv_frames_late", "srv_send_dropped", "srv_sessions_expired",
    "srv_pose_packets", "cli_sock_drops", "cli_sock_overflow",
    "cli_udp_rcvbuf_errors", "cli_ctxt_switches", "clock_drift_us",
    "ts_kernel", "pace_window_ms", "ul_pose_hz_real",
    "upf_rx_pkts", "avisos_campanha", "valida",
]
LADOS = (("a-mec", "mec"), ("a-remoto", "remoto"))


def _linha_exec(res, lado, lado_prova, valida):
    s = res["campanha"].get(lado, {})
    d = res["prova"][lado_prova]["delta"]
    n_av = len([1 for e, _ in res["avisos"] if e == "campanha"])
    srv = s.get("_srv") or {}
    pw = srv.get("pace_window_seconds")
    return [
        res.get("perfil", ""), res["execucao"], lado, s.get("_ordem"),
        _valor(s, ("net_rtt_us", "mean")), _valor(s, ("net_rtt_us", "p50")),
        _valor(s, ("net_rtt_us", "p95")), _valor(s, ("net_rtt_us", "p99")),
        _valor(s, ("net_rtt_us", "min")), _valor(s, ("net_rtt_us", "max")),
        _valor(s, ("m2p_us", "mean")), _valor(s, ("m2p_us", "p50")),
        _valor(s, ("m2p_us", "p95")), _valor(s, ("m2p_us", "p99")),
        _valor(s, ("hold_us", "p50")),
        _valor(s, ("jitter_net_us",)), _valor(s, ("jitter_us",)),
        _valor(s, ("dl_packet_loss_pct",)), _valor(s, ("dl_packet_loss_srv_pct",)),
        _valor(s, ("dl_continuity_pct",)),
        _valor(s, ("frames_incomplete_pct",)), _valor(s, ("dl_throughput_mbps",)),
        _valor(s, ("_fps_servidor",)), _valor(s, ("frames_complete",)),
        _valor(s, ("frames_in_stats",)),
        srv.get("frames_late_total"), srv.get("send_dropped_total"),
        srv.get("sessions_expired_total"), srv.get("pose_packets_total"),
        _valor(s, ("saude", "dl_sock_drops")),
        _valor(s, ("saude", "dl_sock_overflow_pkts")),
        _valor(s, ("saude", "udp_rcvbuf_errors")),
        _valor(s, ("saude", "ctxt_switches_involuntary")),
        _valor(s, ("saude", "clock_drift_us")),
        1 if s.get("saude", {}).get("rx_timestamp_kernel") else 0,
        None if pw is None else round(pw * 1000, 3),
        _valor(s, ("ul_pose_hz_real",)),
        d["upf"]["rx_pkts"], n_av,
        1 if valida else 0,
    ]


def escrever_por_execucao(caminho, execucoes, validas):
    """Uma linha por (execucao, caminho), com TODAS as execucoes -- inclusive as
    descartadas, marcadas com valida=0.

    E' o arquivo de dados brutos: filtrar aqui esconderia do proprio autor o que
    foi deixado de fora. Quem decide se usa so' as validas e' a analise, e para
    isso basta a coluna 'valida'."""
    ids_validas = {id(e) for e in validas}
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(",".join(COLUNAS_EXEC) + "\n")
        for res in execucoes:
            for lado, lado_prova in LADOS:
                if lado not in res["campanha"]:
                    continue
                vals = _linha_exec(res, lado, lado_prova, id(res) in ids_validas)
                fh.write(",".join("" if v is None else str(v) for v in vals) + "\n")


def escrever_agregado(caminho, execucoes):
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("kpi,unidade,mec_media,mec_desvio,remoto_media,remoto_desvio,"
                 "ganho_pareado_media,ganho_pareado_desvio,ganho_pct,"
                 "n_execucoes\n")
        for rotulo, (m, mdp), (r, rdp), ganho, un, _ in linhas_kpi(execucoes):
            g_abs = "" if ganho is None else f"{ganho[0]:.6f}"
            g_dp = "" if ganho is None else f"{ganho[1]:.6f}"
            g_pct = "" if ganho is None else f"{ganho[2]:.3f}"
            fh.write(f'"{rotulo}",{un},'
                     f'{"" if m is None else f"{m:.6f}"},'
                     f'{"" if mdp is None else f"{mdp:.6f}"},'
                     f'{"" if r is None else f"{r:.6f}"},'
                     f'{"" if rdp is None else f"{rdp:.6f}"},'
                     f'{g_abs},{g_dp},{g_pct},{len(execucoes)}\n')


def escrever_markdown(caminho, execucoes, descartadas, args):
    n = len(execucoes)
    placement = execucoes[0].get("placement", {})
    with open(caminho, "w", encoding="utf-8") as fh:
        perfil = getattr(args, "perfil", PERFIL_PADRAO)
        pf = PERFIS.get(perfil, {})
        fh.write(f"# Cenario A - UPF centralizada (baseline) - perfil `{perfil}`\n\n")
        if pf:
            fh.write(f"**Carga:** {pf['bitrate_mbps']} Mbps @ {pf['fps']} fps "
                     f"por sessao (downlink), pose/controle a {pf['pose_hz']} Hz "
                     f"(uplink), MTU {pf['mtu']} B.\n\n")
            fh.write(f"> {pf['descricao']}\n\n")
        fh.write(f"Campanha de **{n} execucao(oes)** independentes. Cada execucao "
                 "sobe o cenario do zero, mede e derruba os deployments antes da "
                 "seguinte.\n\n")
        fh.write(f"- Duracao por caminho: {args.duracao:g} s "
                 f"(descartados os {args.warmup:g} s iniciais)\n")
        fh.write("- Carga: aplicacao VR (downlink de frames + uplink de pose), "
                 "identica nos dois caminhos\n")
        if placement:
            fh.write("- Placement: "
                     + ", ".join(f"{k}={v}" for k, v in placement.items()) + "\n")
        if descartadas:
            fh.write(f"- **{descartadas} execucao(oes) descartada(s)** por aviso de "
                     "campanha (as duas corridas nao foram equivalentes)\n")
        fh.write("\nValores: media +- desvio-padrao entre as execucoes.\n\n")

        fh.write("| KPI | MEC via nucleo | Caminho remoto |\n")
        fh.write("|---|---|---|\n")
        for rotulo, (m, mdp), (r, rdp), ganho, un, c in linhas_kpi(execucoes):
            cm = "-" if m is None else f"{m:.{c}f} ± {mdp:.{c}f} {un}"
            cr = "-" if r is None else f"{r:.{c}f} ± {rdp:.{c}f} {un}"
            fh.write(f"| {rotulo} | {cm} | {cr} |\n")
        fh.write("\nNo cenario A os dois caminhos passam pela mesma UPF central. "
                 "A comparacao com o cenario B (a-mec x b-mec) sai de "
                 "`campanha-a-vs-b.py`.\n")

        fh.write("\n## Prova da ancoragem central\n\n")
        fh.write("Pacotes recebidos na interface GTP da UPF central durante o "
                 "trafego de cada caminho. No cenario A nao ha breakout: a UPF "
                 "central conta os DOIS trafegos, inclusive o do MEC, que sobe ao "
                 "nucleo e volta para a borda.\n\n")
        fh.write("| Execucao | UPF central (MEC) | UPF central (remoto) |\n"
                 "|---|---|---|\n")
        for res in execucoes:
            d = res["prova"]
            fh.write(f"| {res['execucao']} "
                     f"| {d['mec']['delta']['upf']['rx_pkts']} "
                     f"| {d['remoto']['delta']['upf']['rx_pkts']} |\n")
        fh.write("\nAs duas colunas andando juntas = todo o trafego ancorado no "
                 "nucleo. E' a linha de base contra a qual o cenario B e' "
                 "comparado (a-mec x b-mec: mesmo destino, ancora em outro "
                 "lugar).\n\n")
        fh.write("## Como ler os dois blocos de latencia\n\n")
        fh.write("O **atraso de rede** e' ida do uplink mais volta do downlink: "
                 "a parcela que o posicionamento do UPF de fato ataca. O "
                 "**motion-to-photon** inclui, alem disso, o **tempo no "
                 "servidor** (a espera pelo proximo instante de render mais a "
                 "janela em que o gerador espalha os pacotes do frame). Vale a "
                 "identidade `m2p = atraso de rede + tempo no servidor`, e a "
                 "tabela traz os tres justamente para que ela possa ser "
                 "conferida. Reportar so' um dos dois engana: o m2p sozinho "
                 "dilui o efeito do posicionamento do UPF, o atraso de rede sozinho esconde "
                 "o que o usuario sente.\n\n")
        fh.write("O tempo no servidor e' igual nos dois caminhos por construcao "
                 "(mesmo perfil, mesmo codigo, mesma janela de pacing): ele "
                 "desloca o m2p dos dois lados pelo mesmo tanto e nao cria nem "
                 "esconde diferenca entre eles.\n\n")

        fh.write("## O que valida cada medida\n\n")
        fh.write("Uma corrida so' entra na tabela se ela mediu a REDE, e nao o "
                 "proprio medidor. As colunas de `resumo-por-execucao.csv` que "
                 "sustentam isso:\n\n")
        fh.write("- `srv_frames_late` / `srv_send_dropped`: o gerador nao "
                 "sustentou a cadencia, ou nao conseguiu entregar os pacotes ao "
                 "kernel. Perda que nasceu no servidor, nao no caminho.\n")
        fh.write("- `cli_sock_overflow` (SO_RXQ_OVFL): pacotes que CHEGARAM e o "
                 "kernel do cliente descartou por fila cheia. E' perda do "
                 "cliente; nao pode ser lida como perda do UPF.\n")
        fh.write("- `cli_udp_rcvbuf_errors`: estouro de buffer UDP no namespace "
                 "do tester, que o vr-client divide com o nr-gnb e o nr-ue -- "
                 "aponta perda dentro do proprio UERANSIM.\n")
        fh.write("- `dl_loss_srv_pct`: perda com o denominador vindo do "
                 "contador do servidor (pacotes de fato entregues ao kernel), e "
                 "nao do intervalo de sequencia que o cliente observou, que "
                 "nao enxerga frame perdido inteiro nas bordas.\n")
        fh.write("- `ts_kernel`: 1 quando os carimbos de tempo vieram do kernel "
                 "(SO_TIMESTAMPNS). Com 0, a latencia reportada carrega junto o "
                 "tempo que os processos passaram fora da CPU.\n")
        fh.write("- `frames_incompletos_pct`: so' frames COMPLETOS viram amostra "
                 "de latencia. Se os dois caminhos perdem quantidades muito "
                 "diferentes, os percentis nao sao comparaveis -- o que perde "
                 "mais some com as amostras dos instantes ruins e parece melhor "
                 "do que e'. Execucoes assim saem da tabela.\n")


def relatorio_campanha(execucoes, falhas, args):
    perfil = getattr(args, "perfil", PERFIL_PADRAO)
    pf = PERFIS.get(perfil, {})
    passo(99, f"RESUMO DA CAMPANHA - perfil '{perfil}' "
              f"({pf.get('bitrate_mbps', '?')} Mbps @ {pf.get('fps', '?')} fps, "
              f"pose {pf.get('pose_hz', '?')} Hz)")

    validas = [e for e in execucoes
               if not [1 for esc, _ in e["avisos"] if esc == "campanha"]]
    ids_validas = {id(e) for e in validas}
    com_aviso = len(execucoes) - len(validas)
    # O CSV bruto leva SEMPRE todas as execucoes. O que a flag muda e' apenas
    # quais entram na media da tabela.
    tudo = getattr(args, "incluir_descartadas", False)
    usar = execucoes if tudo else validas
    fora = len(execucoes) - len(usar)

    extra = " (agregadas assim mesmo: --incluir-descartadas)" if tudo and com_aviso else ""
    print(f"  {len(execucoes)} execucao(oes) concluida(s), "
          f"{len(falhas)} falha(s), {com_aviso} com aviso de campanha{extra}\n")

    print(f"    {'exec':<6}{'net p50 mec':>13}{'net p50 remoto':>16}"
          f"{'UPF sob MEC':>13}{'status':>16}")
    for e in execucoes:
        c = e["campanha"]
        mec = c.get("a-mec", {}).get("net_rtt_us", {}).get("p50")
        rem = c.get("a-remoto", {}).get("net_rtt_us", {}).get("p50")
        psa = e["prova"]["mec"]["delta"]["upf"]["rx_pkts"]
        st = ("ok" if id(e) in ids_validas
              else ("aviso (usada)" if tudo else "descartada"))
        print(f"    {e['execucao']:<6}{num(mec):>13}{num(rem):>16}"
              f"{psa:>13}{st:>16}")
    for i, msg in falhas:
        print(f"    {i:<6}{VERM}falhou{RESET}: {msg.splitlines()[0][:60]}")

    # Os dados BRUTOS saem sempre, e antes de qualquer desistencia. Na primeira
    # campanha no brix as duas corridas foram descartadas e este bloco ficava
    # depois do 'return' -- os deltas do servidor, a saude e o CSV por execucao
    # foram embora justamente na hora em que eram a unica forma de descobrir
    # POR QUE tinham sido descartadas.
    os.makedirs(args.saida, exist_ok=True)
    p_exec = os.path.join(args.saida, "resumo-por-execucao.csv")
    p_json = os.path.join(args.saida, "campanha.json")
    escrever_por_execucao(p_exec, execucoes, validas)
    with open(p_json, "w", encoding="utf-8") as fh:
        json.dump({"perfil": getattr(args, "perfil", None),
                   "carga": PERFIS.get(getattr(args, "perfil", ""), {}),
                   "execucoes": execucoes, "falhas": falhas,
                   "duracao_s": args.duracao, "warmup_s": args.warmup,
                   "repeticoes": args.repeticoes}, fh, indent=2)

    if not usar:
        print(f"\n  {AMAR}Nenhuma execucao valida para agregar.{RESET} Todas "
              "tiveram aviso de campanha, ou seja, as duas corridas nao foram "
              "equivalentes entre si.")
        print(f"  Os dados brutos ficaram em {args.saida}: "
              f"{os.path.basename(p_exec)} e {os.path.basename(p_json)} -- as "
              "colunas de saude dizem o que invalidou cada uma.")
        return

    # Com --so-prova nao ha campanha VR: sobra a prova do passo 11, que ja' foi
    # impressa acima. Montar uma tabela de KPIs so' de tracos nao ajuda ninguem.
    if not any(e["campanha"] for e in usar):
        print(f"\n  {CINZA}--so-prova: sem campanha VR, nao ha KPIs a agregar. "
              f"Dados brutos em {p_json}{RESET}")
        return

    tabela_kpis(usar)

    p_agr = os.path.join(args.saida, "kpis-agregados.csv")
    p_md = os.path.join(args.saida, "tabela-kpis.md")
    escrever_agregado(p_agr, usar)
    escrever_markdown(p_md, usar, fora, args)

    print(f"\n  Arquivos em {args.saida}:")
    for p in (p_md, p_exec, p_agr, p_json):
        print(f"    {os.path.basename(p)}")
    print(f"\n  A tabela pronta para o texto esta' em "
          f"{os.path.basename(p_md)}; os dados por execucao, em "
          f"{os.path.basename(p_exec)}.")

    if fora:
        aviso(f"{fora} execucao(oes) ficaram de fora da agregacao. Elas "
              "estao no campanha.json, mas nao entram na tabela: nelas o "
              "gerador nao sustentou a carga configurada, entao os dois "
              "caminhos nao carregaram o mesmo trafego.")


def _ganho_medio(validas):
    """Ganho pareado medio de net_rtt p50, em us, entre as execucoes validas."""
    difs = []
    for e in validas:
        mec = _valor(e["campanha"].get("a-mec", {}), ("net_rtt_us", "p50"))
        rem = _valor(e["campanha"].get("a-remoto", {}), ("net_rtt_us", "p50"))
        if mec is not None and rem:
            difs.append((rem - mec, (1 - mec / rem) * 100))
    if not difs:
        return None
    return (sum(d for d, _ in difs) / len(difs),
            sum(p for _, p in difs) / len(difs), len(difs))


def _tabela_cenarios(resumo, raiz):
    """Fecha a varredura mostrando os cenarios lado a lado.

    Lista, perfil a perfil, quantas execucoes concluiram. A comparacao com o
    cenario B sai de campanha-a-vs-b.py. O numero por cenario ja' esta' na pasta de cada um; aqui
    eles aparecem juntos."""
    print(f"\n{'=' * 72}\nCENARIOS MEDIDOS\n{'=' * 72}\n")
    print(f"  {'cenario':<16}{'carga':>16}{'exec':>6}{'falhas':>8}")
    print(f"  {'-' * 16}{'-' * 16}{'-' * 6}{'-' * 8}")
    linhas = []
    for perfil, n_exec, n_falhas, ganho in resumo:
        p = PERFIS[perfil]
        carga = f"{p['bitrate_mbps']} Mbps/{p['fps']}fps"
        if ganho is None:
            cel = "-"
            linhas.append((perfil, carga, n_exec, n_falhas, "", "", ""))
        else:
            us, pct, n = ganho
            cel = f"{us / 1000:.3f} ms ({pct:.1f}%)"
            linhas.append((perfil, carga, n_exec, n_falhas,
                           f"{us / 1000:.4f}", f"{pct:.2f}", n))
        print(f"  {perfil:<16}{carga:>16}{n_exec:>6}{n_falhas:>8}")
    print(f"\n  {CINZA}A comparacao com o cenario B sai de campanha-a-vs-b.py.{RESET}")

    os.makedirs(raiz, exist_ok=True)
    caminho = os.path.join(raiz, "cenarios.csv")
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("cenario,bitrate_mbps,fps,pose_hz,execucoes,falhas,"
                 "ganho_net_p50_ms,ganho_pct,execucoes_validas\n")
        for perfil, carga, n_exec, n_falhas, g_ms, g_pct, n_val in linhas:
            p = PERFIS[perfil]
            fh.write(f"{perfil},{p['bitrate_mbps']},{p['fps']},{p['pose_hz']},"
                     f"{n_exec},{n_falhas},{g_ms},{g_pct},{n_val}\n")
    print(f"\n  Comparativo entre cenarios: {caminho}")
    for perfil, *_ in resumo:
        print(f"    {os.path.join(raiz, perfil)}/")


# --------------------------------------------------------------------------
# uma execucao completa
# --------------------------------------------------------------------------
def executar_uma_vez(args, idx, saida_run, deve_subir):
    """Executa o experimento inteiro uma vez e devolve o registro da execucao."""
    global avisos
    avisos = []

    args_run = argparse.Namespace(**vars(args))
    args_run.saida = saida_run
    args_run.deploy = deve_subir

    p03_deploy(args_run)
    pausa("04 pods prontos")
    p04_pods(args_run)
    pausa("05 placement + gtp5g")
    placement = p05_placement()
    pausa("06 assinantes no Mongo")
    p06_assinantes(args_run)
    pausa("07 associacao PFCP")
    p07_pfcp(args_run)
    pausa("08 tester UERANSIM")
    p08_tester(args_run)
    pausa("09 sessao PDU")
    ue_ip = p09_sessao(args_run)
    pausa("10 rota do tunel")
    p10_rotas()
    pausa("11 PROVA DA ANCORAGEM CENTRAL")
    prova = p11_prova_ancora(ue_ip, args_run)
    pausa("12 campanha VR")
    campanha = p12_campanha(ue_ip, args_run, idx)
    pausa("13 coleta dos resultados")
    p13_coleta(args_run, campanha)

    return {"execucao": idx, "prova": prova, "campanha": campanha,
            "placement": placement, "avisos": list(avisos),
            "saida": saida_run}


# --------------------------------------------------------------------------
def main():
    global NS, PAUSAR, CONCISO
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tentativas", type=int, default=2, metavar="N",
                    help="quantas vezes tentar cada execucao antes de conta-la "
                         "como falha. Cada tentativa refaz o cenario do zero, "
                         "entao serve para falha transitoria do testbed (corrida "
                         "NF x NRF, SMF que ainda nao respondia). Use 1 para "
                         "nao repetir (default: 2)")
    ap.add_argument("--repeticoes", type=int, default=1, metavar="N",
                    help="quantas vezes repetir o experimento inteiro. Com N>1 "
                         "cada repeticao sobe o cenario do zero, mede e derruba "
                         "os deployments antes da seguinte (default: 1)")
    ap.add_argument("--deploy", action="store_true",
                    help="roda 'deploy.py up a' antes do teste (implicito quando "
                         "--repeticoes > 1)")
    ap.add_argument("--incluir-descartadas", action="store_true",
                    help="agrega TODAS as execucoes na tabela, inclusive as que "
                         "tiveram aviso de campanha (por padrao elas ficam so' "
                         "no CSV bruto e no campanha.json)")
    ap.add_argument("--sem-derrubar", action="store_true",
                    help="nao apaga os deployments ao fim de cada execucao "
                         "(util para inspecionar o cenario depois)")
    ap.add_argument("--timeout-derrubada", type=int, default=300,
                    help="espera maxima (s) pelos pods terminarem (default: 300)")
    ap.add_argument("--carregar-assinantes", type=int, default=0, metavar="N",
                    help="popula o Mongo com N assinantes (via port-forward)")
    ap.add_argument("--duracao", type=float, default=60,
                    help="segundos por corrida da campanha VR (default: 60)")
    ap.add_argument("--warmup", type=float, default=5,
                    help="segundos descartados do inicio de cada corrida (default: 5)")
    ap.add_argument("--prova-duracao", type=float, default=10,
                    help="segundos de trafego por caminho na prova da ancoragem central (default: 10)")
    ap.add_argument("--caminhos", choices=("todos", "mec"), default="todos",
                    help="caminhos medidos na campanha do passo 12: 'todos' (MEC e remoto, "
                         "default) ou so' 'mec'. A prova do passo 11 usa os dois sempre")
    ap.add_argument("--so-prova", action="store_true",
                    help="para depois da prova da ancoragem central, sem campanha de medicao")
    ap.add_argument("--perfil", default=PERFIL_PADRAO, metavar="NOME[,NOME...]",
                    help="perfil(is) de carga a medir. Varios separados por "
                         "virgula rodam campanhas independentes, uma apos a "
                         "outra, cada uma na sua pasta. Disponiveis: "
                         + ", ".join(PERFIS) + f" (default: {PERFIL_PADRAO})")
    ap.add_argument("--listar-perfis", action="store_true",
                    help="mostra os perfis disponiveis com a carga de cada um e sai")
    ap.add_argument("--saida", default=os.path.join(BASE, "resultados-a"),
                    help="diretorio RAIZ dos resultados; cada perfil ganha uma "
                         "subpasta com o proprio nome, entao campanhas de "
                         "cenarios diferentes nao se sobrescrevem")
    ap.add_argument("--timeout", type=int, default=300,
                    help="timeout (s) de cada espera (default: 300)")
    ap.add_argument("--porta-mongo", type=int, default=27017)
    ap.add_argument("--namespace", default=NS)
    ap.add_argument("--pular-validate", action="store_true")
    ap.add_argument("--passo-a-passo", "-p", action="store_true",
                    help="pausa depois de cada passo e espera enter")
    ap.add_argument("--conciso", action="store_true",
                    help="omite os comentarios explicativos de cada passo")
    args = ap.parse_args()
    NS = args.namespace
    PAUSAR = args.passo_a_passo
    CONCISO = args.conciso

    if args.listar_perfis:
        print("\nPerfis de carga disponiveis:\n")
        for nome, p in PERFIS.items():
            marca = "  (default)" if nome == PERFIL_PADRAO else ""
            print(f"  {nome}{marca}")
            print(f"    {p['bitrate_mbps']} Mbps @ {p['fps']} fps  |  "
                  f"pose {p['pose_hz']} Hz  |  MTU {p['mtu']} B")
            for linha in textwrap.wrap(p["descricao"], 68):
                print(f"      {linha}")
            print()
        return 0

    if args.repeticoes < 1:
        ap.error("--repeticoes precisa ser >= 1")
    if args.tentativas < 1:
        ap.error("--tentativas precisa ser >= 1")
    perfis = [x.strip() for x in args.perfil.split(",") if x.strip()]
    desconhecidos = [x for x in perfis if x not in PERFIS]
    if desconhecidos:
        ap.error("perfil desconhecido: " + ", ".join(desconhecidos)
                 + "\nDisponiveis: " + ", ".join(PERFIS)
                 + "\nUse --listar-perfis para ver a carga de cada um.")

    # Campanha com repeticoes SEMPRE sobe o cenario. E so' derrubamos o que
    # nos mesmos subimos: rodar contra um testbed que ja' estava de pe' nao
    # pode apagar os deployments de quem estava usando.
    subir = args.deploy or args.repeticoes > 1
    derrubar_ao_fim = subir and not args.sem_derrubar

    t0 = time.time()
    try:
        p01_ferramentas()
        pausa("02 validate.py")
        p02_validate(args)
    except Falha as e:
        print(f"\n{VERM}FALHOU{RESET}: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompido", file=sys.stderr)
        return 130

    if len(perfis) > 1:
        print(f"\n{'#' * 72}\n# {len(perfis)} CENARIOS: " + ", ".join(perfis)
              + f"\n# {args.repeticoes} execucao(oes) cada, "
              f"{args.duracao:g}s por caminho\n{'#' * 72}")

    # Uma campanha COMPLETA por perfil, cada uma na sua pasta. Rodar em serie e
    # nao intercalado e' de proposito: intercalar cenarios faria a diferenca
    # entre eles carregar tambem a deriva do cluster ao longo das horas.
    resultado_geral = 0
    resumo_cenarios = []
    # inicializado aqui tambem, e nao so' dentro do laco de perfis:
    # o resumo final le esta variavel depois do laco.
    interrompido = False
    for perfil in perfis:
        args_p = argparse.Namespace(**vars(args))
        args_p.perfil = perfil
        # A pasta leva o NOME DO CENARIO: campanhas de perfis diferentes
        # convivem sem que uma apague a outra, e o nome do diretorio ja' diz
        # que carga produziu aqueles numeros.
        args_p.saida = os.path.join(args.saida, perfil)

        if len(perfis) > 1:
            print(f"\n{'#' * 72}\n# CENARIO: {perfil}\n"
                  f"# {PERFIS[perfil]['bitrate_mbps']} Mbps @ "
                  f"{PERFIS[perfil]['fps']} fps, pose "
                  f"{PERFIS[perfil]['pose_hz']} Hz -> {args_p.saida}\n"
                  f"{'#' * 72}")
        elif args.repeticoes > 1:
            print(f"\n{'#' * 72}\n# CAMPANHA '{perfil}': {args.repeticoes} "
                  f"execucoes de {args.duracao:g}s por caminho\n"
                  f"# cada execucao: deploy -> medicao -> coleta -> derrubada\n"
                  f"# resultados em {args_p.saida}\n{'#' * 72}")

        execucoes, falhas = [], []
        interrompido = False
        seguidas = 0    # falhas consecutivas; 3 delas = problema sistemico
        for i in range(1, args.repeticoes + 1):
            if args.repeticoes > 1:
                print(f"\n{'#' * 72}\n# [{perfil}] EXECUCAO {i} de {args.repeticoes}"
                      f"{'  (' + str(len(falhas)) + ' falha(s) ate agora)' if falhas else ''}"
                      f"\n{'#' * 72}")
            saida_run = os.path.join(args_p.saida, f"run-{i:02d}")
            res, erro = None, None
            # Uma execucao pode falhar por motivo transitorio do proprio
            # testbed -- a corrida NF x NRF, um SMF que ainda nao respondia
            # quando o UE pediu a sessao PDU. Numa campanha longa, contar isso
            # como falha definitiva desperdicaria os ~19 min de deploy que
            # acabaram de ser gastos. Cada tentativa refaz o cenario do zero
            # (a derrubada roda no finally), entao a repeticao nao herda o
            # estado que quebrou.
            definitiva = False
            for tent in range(1, args.tentativas + 1):
                t_run = time.time()
                try:
                    res = executar_uma_vez(args_p, i, saida_run, subir)
                    res["segundos"] = round(time.time() - t_run, 1)
                    res["perfil"] = perfil
                    res["tentativas"] = tent
                    erro = None
                except FalhaDefinitiva as e:
                    erro, definitiva = str(e), True
                except Falha as e:
                    erro = str(e)
                except Exception as e:                    # noqa: BLE001
                    # Erro NAO previsto (bug do script, kubectl que sumiu no
                    # meio, JSON malformado). Vai com traceback para o registro.
                    erro = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                except KeyboardInterrupt:
                    print("\ninterrompido", file=sys.stderr)
                    interrompido = True
                finally:
                    if derrubar_ao_fim:
                        try:
                            derrubar(args_p)
                        except Exception as exc:          # noqa: BLE001
                            print(f"  {AMAR}derrubada falhou: {exc}{RESET}",
                                  file=sys.stderr)
                if interrompido or erro is None or definitiva:
                    break
                if tent < args.tentativas:
                    print(f"\n{AMAR}[{perfil}] execucao {i}: tentativa {tent} de "
                          f"{args.tentativas} falhou{RESET} ({erro.splitlines()[0]})"
                          f"\n  refazendo o cenario do zero...", file=sys.stderr)
            if interrompido:
                break

            if res is not None and erro is None:
                execucoes.append(res)
                seguidas = 0
                resumo_execucao(res)
                extra = (f" (na tentativa {res['tentativas']})"
                         if res.get("tentativas", 1) > 1 else "")
                print(f"\n  {VERDE}execucao {i} concluida{RESET}{extra} em "
                      f"{res['segundos']:.0f}s -> {saida_run}")
            else:
                # 'tent', e nao args.tentativas: uma FalhaDefinitiva sai na
                # primeira, e dizer "apos 2 tentativas" seria falso.
                print(f"\n{VERM}[{perfil}] EXECUCAO {i} FALHOU{RESET} apos "
                      f"{tent} tentativa(s): {erro}", file=sys.stderr)
                falhas.append((i, erro))
                seguidas += 1
            # Numa campanha longa e desacompanhada, tres falhas seguidas nao
            # sao azar: e' algo sistemico (gtp5g fora, no sem CPU, banco
            # vazio). Insistir so' queima mais uma hora de deploy para colher o
            # mesmo erro.
            if seguidas >= 3 and args.repeticoes > 3:
                print(f"\n{VERM}3 execucoes seguidas falharam em '{perfil}' -- "
                      f"abortando este cenario.{RESET}", file=sys.stderr)
                break

        if not execucoes:
            print(f"\n{VERM}[{perfil}] nenhuma execucao concluiu.{RESET}",
                  file=sys.stderr)
            resumo_cenarios.append((perfil, 0, len(falhas), None))
            resultado_geral = 1
        else:
            relatorio_campanha(execucoes, falhas, args_p)
            validas = [e for e in execucoes
                       if not [1 for esc, _ in e["avisos"] if esc == "campanha"]]
            resumo_cenarios.append((perfil, len(execucoes), len(falhas),
                                    _ganho_medio(validas)))
            if falhas:
                resultado_geral = 1
        if interrompido:
            resultado_geral = 130
            break

    if len(perfis) > 1:
        _tabela_cenarios(resumo_cenarios, args.saida)

    # A linha final tem que dizer a VERDADE. Ela ja' saiu verde com zero
    # execucoes concluidas -- o codigo de saida estava certo (1), mas quem le
    # o terminal ve "VALIDADO" e acredita. Numa campanha longa e desacompanhada
    # e' a diferenca entre repetir o teste e escrever o TG em cima de nada.
    concluidas = sum(c for _, c, _, _ in resumo_cenarios)
    total_falhas = sum(f for _, _, f, _ in resumo_cenarios)
    tempo = f"{time.time() - t0:.0f}s"
    if interrompido:
        print(f"\n{AMAR}CENARIO A INTERROMPIDO{RESET} -- {concluidas} execucao(oes) "
              f"concluida(s) em {tempo}")
    elif concluidas == 0:
        print(f"\n{VERM}CENARIO A NAO VALIDADO{RESET} -- nenhuma execucao concluiu "
              f"({total_falhas} falha(s)) em {tempo}")
    elif total_falhas:
        print(f"\n{AMAR}CENARIO A VALIDADO COM FALHAS{RESET} -- {concluidas} "
              f"execucao(oes) concluida(s), {total_falhas} falha(s), "
              f"{len(perfis)} cenario(s) em {tempo}")
    else:
        print(f"\n{VERDE}CENARIO A VALIDADO{RESET} -- {concluidas} execucao(oes) "
              f"em {len(perfis)} cenario(s), {tempo}")
    return resultado_geral


if __name__ == "__main__":
    sys.exit(main())
