#!/usr/bin/env python3
"""
Sobe o cenario B e mede o Local Breakout. Faz exatamente quatro coisas:

    1. sobe o cenario B, em ordem de dependencia e com folga entre cada NF
    2. carrega os assinantes no MongoDB
    3. sobe o tester (DEPOIS dos assinantes)
    4. mede os KPIs do LBO

Uso:

    python3 scripts/rodar-cenario-b.py

Os parametros ficam nas constantes logo abaixo -- e' so' editar.

Duas ordens aqui nao sao estilo, sao o que faz a coisa funcionar:

  * mongo -> nrf -> resto. O NRF aceita conexao em ~1 s mas so' responde depois
    que o Mongo esta pronto. Um NF que sobe antes disso fica com o NF instance
    ID vazio, continua Running, e o UE falha muito depois com "CONGESTION".

  * assinantes ANTES do tester. Se o tester sobe primeiro, o UE tenta registrar,
    leva 404 do UDR (banco vazio) e o T3511 desiste na 5a tentativa. Depois
    disso ele fica parado para sempre, mesmo com os assinantes ja' carregados.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time

# ---------------------------------------------------------------- parametros
NS = "free5gc"
QTD_UE = 5            # assinantes gravados no Mongo
DELAY = 5             # folga em segundos entre um NF e o proximo
DURACAO = 30          # segundos de trafego por caminho, na medicao
# ClusterIPs do mec-app (sai na borda, via LBO) e do remote-app (sobe ate' o
# nucleo). Sao DINAMICOS: o k8s aloca e o mec-af anuncia o do mec-app ao NEF.
# Resolvidos em passo4_kpis() com 'kubectl get svc'.
MEC = None
REMOTO = None
TIMEOUT = 180         # espera maxima por NF

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTER = "free5gc-ueransim-0"
TUN = "uesimtun0"
IMSI = "imsi-208930000000000"

# (manifesto, deployment, registra_no_nrf)
ORDEM = [
    ("common/mongo.yaml",            "free5gc-mongodb",   False),
    ("common/nrf.yaml",              "free5gc-nrf",       False),
    ("common/udr.yaml",              "free5gc-udr",       True),
    ("common/udm.yaml",              "free5gc-udm",       True),
    ("common/ausf.yaml",             "free5gc-ausf",      True),
    ("common/nssf.yaml",             "free5gc-nssf",      True),
    ("common/pcf.yaml",              "free5gc-pcf",       True),
    ("common/nef.yaml",              "free5gc-nef",       True),
    ("common/amf.yaml",              "free5gc-amf",       True),
    ("common/webui.yaml",            "free5gc-webui",     True),
    ("scenario-b-dupf/i-upf.yaml",   "free5gc-i-upf",     False),
    ("scenario-b-dupf/psa-upf.yaml", "free5gc-psa-upf",   False),
    ("scenario-b-dupf/smf.yaml",     "free5gc-smf",       True),
    ("mec/vr-app.yaml",              None,                False),
    # mec-service.yaml aparece duas vezes de proposito: ele contem DOIS
    # deployments e cada entrada espera um. O remote-app e' o alvo da
    # medicao b-remoto; sem esperar por ele, um pod Unschedulable so'
    # apareceria no fim, como "nenhum frame voltou".
    ("mec/mec-service.yaml",         "free5gc-mec-app",   False),
    ("mec/mec-service.yaml",         "free5gc-remote-app", False),
    # AF do LBO dinamico: anuncia o ClusterIP do mec-app ao NEF.
    ("mec/mec-af.yaml",              "mec-af",            False),
]

V, R, C, Z = "\033[32m", "\033[31m", "\033[90m", "\033[0m"
if not sys.stdout.isatty():
    V = R = C = Z = ""


# ------------------------------------------------------------------ utilidades
def sh(cmd, timeout=120):
    """Roda um comando e devolve (codigo, saida)."""
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def kc(args, timeout=120):
    return sh(f"kubectl -n {NS} {args}", timeout)


def cluster_ip(svc):
    cod, saida = kc(f"get svc {svc} -o jsonpath='{{.spec.clusterIP}}'")
    ip = saida.strip().strip("'")
    if cod != 0 or not ip or ip == "None":
        erro(f"nao achei o ClusterIP do service {svc}: {saida.strip()}")
    return ip


def erro(msg):
    print(f"\n{R}FALHOU:{Z} {msg}")
    sys.exit(1)


def titulo(n, texto):
    print(f"\n{'='*66}\n{n}. {texto}\n{'='*66}")


def esperar(descricao, condicao, timeout=TIMEOUT):
    """Chama condicao() ate' virar True, ou estoura o timeout."""
    inicio = time.time()
    avisou = False
    while time.time() - inicio < timeout:
        if condicao():
            if avisou:
                print()
            return True
        if not avisou:
            print(f"     {C}esperando {descricao}{Z}", end="", flush=True)
            avisou = True
        print(".", end="", flush=True)
        time.sleep(3)
    if avisou:
        print()
    return False


def pronto(deploy):
    cod, _ = kc(f"rollout status deploy/{deploy} --timeout=10s", timeout=40)
    return cod == 0


def registrou(deploy):
    """True se o NF confirmou registro no NRF depois do ultimo erro de registro.

    Todo NF de SBI imprime 'OAuth2 setting receive from NRF' exatamente quando o
    NRF responde. Comparar a POSICAO dessa linha com a do ultimo erro distingue
    'errou e depois conseguiu' de 'so' errou'."""
    cod, saida = kc(f"logs deploy/{deploy} --tail=400")
    if cod != 0:
        return False
    ok = err = -1
    for i, linha in enumerate(saida.splitlines()):
        if "OAuth2 setting receive from NRF" in linha:
            ok = i
        elif "register to NRF Error" in linha:
            err = i
    return ok > err


def contador_gtp(deploy):
    """Pacotes recebidos na interface do gtp5g dentro do pod do UPF."""
    cod, saida = kc(f"exec deploy/{deploy} -- cat /proc/net/dev")
    if cod != 0:
        erro(f"nao consegui ler /proc/net/dev em {deploy}")
    for linha in saida.splitlines():
        m = re.match(r"\s*upfgtp:\s*(\d+)\s+(\d+)", linha)
        if m:
            return int(m.group(2))
    erro(f"interface upfgtp nao existe em {deploy} -- o gtp5g esta carregado "
         f"nesse no? (lsmod | grep gtp5g)")


# ------------------------------------------------- 1. subir o cenario B
def passo1_subir():
    titulo(1, "Subindo o cenario B (ordem de dependencia)")
    os.chdir(BASE)

    print("  removendo o plano de usuario do cenario A, se existir")
    for f in ("scenario-a-cupf/upf.yaml", "scenario-a-cupf/smf.yaml"):
        sh(f"kubectl delete -f {f} --ignore-not-found=true")

    for arquivo, deploy, precisa_nrf in ORDEM:
        print(f"\n  -> {arquivo}")
        cod, saida = sh(f"kubectl apply -f {arquivo}")
        if cod != 0:
            erro(f"kubectl apply -f {arquivo} falhou:\n{saida.strip()}")
        if not deploy:
            continue

        if deploy in ("free5gc-smf", "mec-af"):
            # Config (SMF) e codigo (mec-af) vivem em ConfigMaps. Se so' eles
            # mudaram, o apply NAO recria o pod e o processo segue com a versao
            # antiga -- o LBO "nao ativa" sem nenhum erro. O restart forca a
            # releitura.
            kc(f"rollout restart deploy/{deploy}")

        if not esperar(deploy, lambda d=deploy: pronto(d)):
            kc(f"get pods -o wide")
            erro(f"{deploy} nao ficou pronto em {TIMEOUT}s")
        print(f"     {V}pronto{Z}")

        if precisa_nrf:
            if not esperar(deploy, lambda d=deploy: registrou(d)):
                erro(f"{deploy} nao confirmou registro no NRF.\n"
                     f"  Ele subiu cedo demais e ficou com instance ID vazio.\n"
                     f"  Corrija com: kubectl -n {NS} rollout restart deploy/{deploy}")
            print(f"     {V}registrado no NRF{Z}")

        time.sleep(DELAY)

    print(f"\n  {V}cenario B no ar{Z}")


# ------------------------------------------------- 2. assinantes no Mongo
def passo2_assinantes():
    titulo(2, f"Carregando {QTD_UE} assinantes no MongoDB")
    print("  abrindo port-forward para o mongo")
    pf = subprocess.Popen(f"kubectl -n {NS} port-forward svc/mongo 27017:27017",
                          shell=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
    try:
        time.sleep(5)
        cod, saida = sh(f"{sys.executable} scripts/insere-dados.py "
                        f"--limpar --qtd {QTD_UE}", timeout=300)
        print("  " + saida.strip().replace("\n", "\n  "))
        if cod != 0:
            erro("insere-dados.py falhou (pymongo instalado? "
                 "pip install -r scripts/requirements.txt)")
    finally:
        pf.send_signal(signal.SIGTERM)
        pf.wait(timeout=10)
    print(f"  {V}assinantes carregados{Z}")


# ------------------------------------------------- 3. tester
def passo3_tester():
    titulo(3, "Subindo o tester (agora que o banco tem assinantes)")
    cod, saida = sh("kubectl apply -f tester/ueransim.yaml")
    if cod != 0:
        erro(f"kubectl apply -f tester/ueransim.yaml falhou:\n{saida.strip()}")

    # Se o tester JA' existia (ex.: deploy.py aplicou antes de o banco ter
    # assinantes), o UE pode ter levado 404 do UDR e desistido no T3511 --
    # e nesse estado ele fica parado para sempre, mesmo com os assinantes
    # ja' carregados. Recriar o pod forca um registro do zero agora.
    cod, saida = kc(f"exec {TESTER} -c ue -- ./nr-cli {IMSI} -e status")
    if cod == 0 and "RM-REGISTERED" not in saida:
        print("  UE nao registrado (tester antigo?); recriando o pod")
        kc(f"delete pod {TESTER} --wait=false")
        time.sleep(5)

    def tester_pronto():
        cod, saida = kc(f"get pod {TESTER} -o "
                        "jsonpath='{.status.containerStatuses[*].ready}'")
        return cod == 0 and saida and "false" not in saida

    if not esperar("tester", tester_pronto):
        erro(f"{TESTER} nao ficou pronto. Se o StatefulSet estiver com "
             "replicas: 0, ajuste em tester/ueransim.yaml")
    print(f"  {V}tester no ar{Z}")

    def registrado():
        cod, saida = kc(f"exec {TESTER} -c ue -- ./nr-cli {IMSI} -e status")
        return cod == 0 and "RM-REGISTERED" in saida

    if not esperar("registro do UE", registrado, 120):
        erro("o UE nao registrou.\n"
             "  Olhe o log do UDM/UDR, nao o do UE -- o UE so' mostra "
             "'CONGESTION' para qualquer causa:\n"
             f"    kubectl -n {NS} logs deploy/free5gc-udm --tail=30")
    print(f"  {V}UE registrado{Z}")


# ------------------------------------------------- 4. KPIs do LBO
def medir(destino, rotulo, ue_ip):
    """Gera trafego para um destino e devolve (resumo, delta i-upf, delta psa)."""
    i0 = contador_gtp("free5gc-i-upf")
    p0 = contador_gtp("free5gc-psa-upf")

    cod, saida = kc(
        f"exec {TESTER} -c vr-client -- python3 /opt/vr/vr_client.py "
        f"--server {destino}:9100 --bind {ue_ip} --duration {DURACAO} "
        f"--warmup 3 --label {rotulo}", timeout=DURACAO + 90)
    try:
        resumo = json.loads(saida[saida.index("{"):saida.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        erro(f"o vr_client nao devolveu resultado para {destino}:\n{saida[-400:]}")

    if not resumo["frames_complete"]:
        erro(f"nenhum frame voltou de {destino}. O plano de dados nao esta "
             f"passando -- confira a rota do tunel e o ip_forward no UPF.")

    return (resumo,
            contador_gtp("free5gc-i-upf") - i0,
            contador_gtp("free5gc-psa-upf") - p0)


def passo4_kpis():
    titulo(4, "Medindo os KPIs do Local Breakout")

    # IP do tunel: e' o PSA-UPF quem aloca, entao ter IP ja' prova que o
    # caminho gNB -> I-UPF -> N9 -> PSA-UPF fechou inteiro.
    ue_ip = None
    def tem_ip():
        nonlocal ue_ip
        cod, saida = kc(f"exec {TESTER} -c ue -- ip -4 -o addr show {TUN}")
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", saida) if cod == 0 else None
        ue_ip = m.group(1) if m else None
        return ue_ip is not None

    if not esperar("sessao PDU", tem_ip, 120):
        erro(f"{TUN} nao ganhou IP: a sessao PDU nao fechou")
    print(f"  IP do UE: {ue_ip}")

    global MEC, REMOTO
    MEC, REMOTO = cluster_ip("mec-app"), cluster_ip("remote-app")
    print(f"  ClusterIPs: mec-app={MEC} (anunciado ao NEF pelo mec-af), "
          f"remote-app={REMOTO}")

    # Sem esta rota o trafego sai pela eth0 do pod, chega pela rede do
    # Kubernetes e nao passa por UPF nenhum -- a medicao seria do cluster.
    for destino in (MEC, REMOTO):
        kc(f"exec {TESTER} -c ue -- ip route replace {destino}/32 dev {TUN}")
    print(f"  rotas de {MEC} e {REMOTO} pelo tunel\n")

    print(f"  medindo {DURACAO}s contra a borda ({MEC})...")
    mec, mec_i, mec_p = medir(MEC, "b-mec", ue_ip)
    print(f"  medindo {DURACAO}s contra o remoto ({REMOTO})...")
    rem, rem_i, rem_p = medir(REMOTO, "b-remoto", ue_ip)

    print(f"\n{'='*66}\nRESULTADO\n{'='*66}")
    print("\n  Prova do breakout (pacotes na interface GTP de cada UPF):\n")
    print("    (o I-UPF conta so' o que ele desencapsula localmente: sobe no")
    print("     caminho do MEC e fica em zero no remoto, onde ele so' repassa")
    print("     GTP-U N3 -> N9. Quem decide e' a coluna do PSA-UPF.)\n")
    print(f"    {'trafego':<12}{'I-UPF (borda)':>16}{'PSA-UPF (nucleo)':>20}")
    print(f"    {'mec':<12}{mec_i:>16}{mec_p:>20}")
    print(f"    {'remoto':<12}{rem_i:>16}{rem_p:>20}")

    if rem_p == 0:
        erro("o PSA-UPF nao viu o trafego remoto: o caminho default (N9 ate' o "
             "nucleo) nao esta funcionando")
    vazamento = mec_p / rem_p
    if vazamento < 0.02:
        print(f"\n    {V}LBO CONFIRMADO{Z}: o trafego do MEC nao passa pelo "
              f"PSA-UPF ({mec_p} contra {rem_p} pacotes)")
    else:
        print(f"\n    {R}LBO NAO ATIVO{Z}: o PSA-UPF viu {mec_p} pacotes do "
              f"trafego MEC ({vazamento*100:.1f}% do remoto).\n"
              f"    Confira 'ulcl: true' no smf.yaml, o IMSI em "
              f"ueRoutingInfo.members, e se o mec-af anunciou {MEC} ao NEF "
              f"(kubectl -n {NS} logs deploy/mec-af).")

    print("\n  KPIs:\n")
    print(f"    {'caminho':<12}{'net_rtt p50':>13}{'net_rtt p95':>13}"
          f"{'m2p p50':>11}{'perda %':>10}{'Mbps':>9}")
    for nome, s in (("b-mec", mec), ("b-remoto", rem)):
        print(f"    {nome:<12}{s['net_rtt_us']['p50']:>13.1f}"
              f"{s['net_rtt_us']['p95']:>13.1f}{s['m2p_us']['p50']:>11.1f}"
              f"{s['dl_packet_loss_pct']:>10.2f}{s['dl_throughput_mbps']:>9.2f}")

    a, b = mec["net_rtt_us"]["p50"], rem["net_rtt_us"]["p50"]
    if a and b:
        print(f"\n    ganho do LBO na parcela de rede: {b - a:.0f} us "
              f"({(1 - a / b) * 100:.1f}%)")
    print("\n    net_rtt = ida do uplink + volta do downlink, a parcela que o")
    print("    LBO ataca. m2p inclui a espera pelo proximo frame, que depende")
    print("    da cadencia e nao da rede.\n")


if __name__ == "__main__":
    inicio = time.time()
    passo1_subir()
    passo2_assinantes()
    passo3_tester()
    passo4_kpis()
    print(f"{V}Concluido em {time.time() - inicio:.0f}s{Z}\n")
