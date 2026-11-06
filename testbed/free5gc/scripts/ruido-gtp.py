#!/usr/bin/env python3
"""
Trafego de fundo PELO PLANO DE USUARIO: iperf3 descendo pelo tunel GTP-U ate'
um segundo UERANSIM no brix-porvir-03 (congestao/ruido-gtp.yaml).

    ruido-gerador (petshopboys) --N6--> UPF de ancoragem --GTP-U--> gNB de ruido (brix-03)
                                        A: upf  |  B: psa-upf

E' a biblioteca do piloto-congestao.py e da campanha-a-vs-b.py (--ruido gtp) e
a ferramenta para montar e conferir o ruido na mao. O cenario (A ou B) precisa
estar no ar: o UE de ruido registra na AMF dele.

    python3 scripts/ruido-gtp.py sobe --cenario b     # aplica, cadastra o UE, abre a sessao
    python3 scripts/ruido-gtp.py prova --cenario b    # 6 s a 50 Mbps: por onde o fundo passou
    python3 scripts/ruido-gtp.py capacidade           # iperf3 TCP petshopboys -> brix-03
    python3 scripts/ruido-gtp.py liga --mbps 300 --segundos 20
    python3 scripts/ruido-gtp.py status
    python3 scripts/ruido-gtp.py desce

UNIDADE DOS NUMEROS
    O datagrama do fundo tem 1356 B para que o pacote GTP-U no fio tenha o
    MESMO tamanho (1428 B de IP) que o datagrama de 1400 B do fundo direto
    (congestao/iperf.yaml). Os Mbps de "pedido" e "cruzou" sao contados nesse
    padrao -- pacotes x 1400 B -- e portanto sao a mesma coisa que eram na
    campanha de 16/09/2026: mesmo nivel = mesmo pacote e mesma taxa de pacotes
    no enlace. O iperf recebe a taxa ajustada (taxa_iperf). "gtpu_ip_mbps" e' o
    que de fato passou, em bytes de IP do pacote GTP-U.

O QUE CONTA COMO "CRUZOU O ENLACE"
    Os contadores da chain RUIDO-GTPU no netns do pod de ruido: todo GTP-U que
    chega ao pod passa por ela ANTES do nr-gnb, inclusive o que ela descarta.
    O UERANSIM nao aguenta a taxa do fundo (ver o manifesto) e so' recebe um
    fio; o resto ja' cruzou o enlace quando cai. O iperf3 do lado do UE ve
    perda enorme, e isso e' esperado.
"""
import argparse
import importlib.util
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import time

import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
MANIFESTO = os.path.join(BASE, "congestao", "ruido-gtp.yaml")

NS = "free5gc"
GERADOR = "ruido-gerador"       # fonte do fundo, no no da UPF de ancoragem
RUIDO = "ruido-ueransim"        # gNB + UE de ruido + iperf, no brix-porvir-03
PORTA = 5201                    # servidor do fundo no gerador (e da capacidade no ruido)
PORTA_LOOPBACK = 5202           # controle de CPU do piloto, no loopback do gerador
TUN = "uesimtun0"
CHAIN = "RUIDO-GTPU"

DATAGRAMA = 1356                # payload UDP: 1428 B de IP no pacote GTP-U
DATAGRAMA_EQUIV = 1400          # o do fundo direto -- a unidade dos Mbps
# iperf3 -P: cada fluxo bem abaixo do que uma thread gera (igual ao fundo direto).
MBPS_POR_FLUXO = 250
# AMBR do UE de ruido. A padrao do insere-dados.py (100 Mbps de sessao no
# downlink) viraria teto do fundo se o QoS do gtp5g estiver ligado no no.
AMBR = "5 Gbps"
PORTA_MONGO = 27018             # != 27017, que o passo 6 dos testes usa

# epc-mode dos pods que interessam, por cenario.
ANCORA = {"a": "upf", "b": "psa-upf"}           # UPF de onde o fundo sai
BORDA = {"a": None, "b": "i-upf"}                # dUPF que o fundo NAO pode tocar
DEPLOY_UPF = {"upf": "free5gc-upf", "psa-upf": "free5gc-psa-upf", "i-upf": "free5gc-i-upf"}
PREFIXO_SEGMENTO = 22           # o mesmo criterio de segmento dos testes


class ErroRuido(Exception):
    pass


# --------------------------------------------------------------------------
# o UE de ruido, lido do PROPRIO manifesto (uma fonte so' para IMSI, chaves
# e fatia -- cadastrar diferente do que o UERANSIM usa seria falha muda)
# --------------------------------------------------------------------------
def _ue_do_manifesto():
    for d in yaml.safe_load_all(open(MANIFESTO, encoding="utf-8")):
        if d and d.get("kind") == "ConfigMap":
            raw = (d.get("data") or {}).get("ue.yaml")
            if raw:
                # BaseLoader: tudo string, senao 'sd: 0x112233' vira inteiro.
                ue = yaml.load(raw, Loader=yaml.BaseLoader)
                s = ue["sessions"][0]["slice"]
                sd = s["sd"].lower()
                return {"supi": ue["supi"], "key": ue["key"], "opc": ue["op"],
                        "amf": ue["amf"], "sst": int(s["sst"], 0),
                        "sd": f"{int(sd, 16):06x}" if sd.startswith("0x") else sd.zfill(6),
                        "dnn": ue["sessions"][0]["apn"]}
    raise ErroRuido(f"ue.yaml nao encontrado em {MANIFESTO}")


UE = _ue_do_manifesto()
IMSI = UE["supi"]


# --------------------------------------------------------------------------
# kubectl
# --------------------------------------------------------------------------
def kubectl(*a, timeout=120):
    try:
        # utf-8 explicito: no Windows o padrao e' cp1252, e a saida do kubectl e' utf-8.
        return subprocess.run(["kubectl", "-n", NS, *a], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(a, 124, "", f"timeout ({timeout}s)")


def em(deploy, container, *cmd, timeout=60):
    args = ["exec", f"deploy/{deploy}"] + (["-c", container] if container else []) + ["--", *cmd]
    return kubectl(*args, timeout=timeout)


def pod(seletor):
    """(no, ip) do primeiro pod Running com o seletor; (None, None) se nao houver."""
    r = kubectl("get", "pod", "-l", seletor, "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].spec.nodeName} {.items[0].status.podIP}")
    partes = r.stdout.split()
    return (partes[0], partes[1]) if len(partes) == 2 else (None, None)


def _ip_do_no(no):
    if not no:
        return None
    r = kubectl("get", "node", no, "-o",
                "jsonpath={.status.addresses[?(@.type=='InternalIP')].address}")
    return r.stdout.strip() or None


def mesmo_segmento(a, b):
    ia, ib = _ip_do_no(a), _ip_do_no(b)
    if not ia or not ib:
        return None
    return ipaddress.ip_address(ib) in ipaddress.ip_network(f"{ia}/{PREFIXO_SEGMENTO}",
                                                            strict=False)


def json_de(texto):
    try:
        return json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
    except ValueError:
        return {"error": (texto or "sem saida").strip()[:300]}


# --------------------------------------------------------------------------
# montagem
# --------------------------------------------------------------------------
def aplica(timeout=300):
    r = kubectl("apply", "-f", MANIFESTO)
    if r.returncode:
        raise ErroRuido(f"kubectl apply do ruido falhou: {r.stderr.strip()[:300]}")
    for dep in (GERADOR, RUIDO):
        r = kubectl("rollout", "status", f"deploy/{dep}", f"--timeout={timeout}s",
                    timeout=timeout + 30)
        if r.returncode:
            raise ErroRuido(f"{dep} nao ficou pronto: {(r.stderr or r.stdout).strip()[:300]}")


def desce():
    kubectl("delete", "-f", MANIFESTO, "--ignore-not-found=true", "--wait=false", timeout=60)


def placement(cenario):
    """Onde cada peca esta AGORA. Levanta ErroRuido se o desenho nao vale:
    o gerador fora do no da ancora nao sai pela placa da UPF, e o ruido dentro
    do experimento pioraria a medida por CPU."""
    no_ger, ip_ger = pod(f"app={GERADOR}")
    no_rui, ip_rui = pod(f"app={RUIDO}")
    no_anc, _ = pod(f"epc-mode={ANCORA[cenario]}")
    experimento = {p: pod(f"epc-mode={p}")[0] for p in ("ueransim", "mec-app", "i-upf")}
    if not ip_ger or not ip_rui:
        raise ErroRuido("os pods do ruido nao estao Running (aplique congestao/ruido-gtp.yaml)")
    if not no_anc:
        raise ErroRuido(f"a UPF de ancoragem do cenario {cenario.upper()} "
                        f"(epc-mode={ANCORA[cenario]}) nao esta no ar")
    if no_ger != no_anc:
        raise ErroRuido(f"o gerador esta' em {no_ger} e a UPF de ancoragem em {no_anc}: "
                        "ajuste o nodeSelector de ruido-gerador em congestao/ruido-gtp.yaml")
    dentro = [p for p, no in experimento.items() if no and no == no_rui]
    if dentro:
        raise ErroRuido(f"o UERANSIM de ruido caiu em {no_rui}, que hospeda "
                        f"{', '.join(dentro)} do experimento: escolha outro brix em "
                        "congestao/ruido-gtp.yaml")
    if experimento["ueransim"] and mesmo_segmento(no_rui, experimento["ueransim"]) is False:
        raise ErroRuido(f"o UERANSIM de ruido ({no_rui}) nao esta no segmento dos brix: o "
                        "fundo nao desceria o mesmo enlace nuvem -> borda que o teste")
    return {"no_gerador": no_ger, "ip_gerador": ip_ger, "no_ruido": no_rui,
            "ip_ruido": ip_rui, "no_ancora": no_anc}


def cadastra(porta=PORTA_MONGO):
    """Grava o UE de ruido no Mongo, SUBSTITUINDO o que houver com o mesmo
    IMSI. O passo 6 dos testes roda insere-dados.py --limpar, que apaga todo
    assinante -- por isso isto roda depois dele, a cada preparo."""
    try:
        import pymongo
    except ImportError:
        raise ErroRuido("pymongo nao instalado: pip install -r scripts/requirements.txt")
    spec = importlib.util.spec_from_file_location("insere_dados",
                                                  os.path.join(AQUI, "insere-dados.py"))
    ins = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ins)
    pf = subprocess.Popen(["kubectl", "-n", NS, "port-forward", "svc/mongo", f"{porta}:27017"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(4)
        if pf.poll() is not None:
            raise ErroRuido(f"port-forward do mongo morreu (porta local {porta} em uso?)")
        db = pymongo.MongoClient(f"mongodb://localhost:{porta}/",
                                 serverSelectionTimeoutMS=15000)["free5gc"]
        try:
            tenant = ins.resolve_tenant_id(db, None)
        except SystemExit as e:
            raise ErroRuido(str(e))
        a = argparse.Namespace(sst=UE["sst"], sd=UE["sd"], dnn=UE["dnn"], plmn="20893",
                               key=UE["key"], opc=UE["opc"], amf=UE["amf"],
                               sqn="000000000023", tenant_id=tenant,
                               ue_ambr_ul=AMBR, ue_ambr_dl=AMBR,
                               sess_ambr_ul=AMBR, sess_ambr_dl=AMBR)
        for coll, doc in ins.make_docs(IMSI, a).items():
            db[coll].delete_many({"ueId": IMSI})
            db[coll].insert_one(doc)
    finally:
        pf.terminate()
        try:
            pf.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pf.kill()


def ue_ip():
    r = em(RUIDO, "ue", "ip", "-4", "-o", "addr", "show", TUN, timeout=30)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
    return m.group(1) if m else None


def ue_registrado():
    r = em(RUIDO, "ue", "./nr-cli", IMSI, "-e", "status", timeout=30)
    if r.returncode:
        return None
    return "RM-REGISTERED" in r.stdout


def nucleo(cenario):
    """Os pods que guardam a sessao do UE de ruido: AMF, SMF e a UPF de
    ancoragem. Pod recriado ganha nome novo, entao esta tupla muda a cada
    deploy do cenario. E' o que diz se a sessao do UE ainda existe do lado do
    nucleo -- o UERANSIM nao sabe: depois que o nucleo cai ele continua
    RM-REGISTERED e com IP na uesimtun0 (campanha de 26/09/2026: o fundo do B
    foi ligado num UE aberto no nucleo do A e nao passou pacote nenhum)."""
    nomes = []
    for papel in ("amf", "smf", ANCORA[cenario]):
        r = kubectl("get", "pod", "-l", f"epc-mode={papel}",
                    "--field-selector=status.phase=Running",
                    "-o", "jsonpath={.items[*].metadata.name}")
        nomes.append(" ".join(sorted(r.stdout.split())) or None)
    return tuple(nomes)


def reinicia_ue(timeout=180):
    """Recria o pod de ruido e espera a sessao PDU. Sempre recria: depois de um
    deploy o gNB velho ficou com o SCTP de uma AMF que nao existe mais, e um
    UE que so' PARECE registrado seria pior do que nenhum."""
    kubectl("rollout", "restart", f"deploy/{RUIDO}")
    r = kubectl("rollout", "status", f"deploy/{RUIDO}", f"--timeout={timeout}s",
                timeout=timeout + 30)
    if r.returncode:
        raise ErroRuido(f"{RUIDO} nao voltou: {(r.stderr or r.stdout).strip()[:300]}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        ip = ue_ip()
        if ip:
            return ip
        time.sleep(3)
    log = kubectl("logs", f"deploy/{RUIDO}", "-c", "ue", "--tail=15").stdout.strip()
    raise ErroRuido(f"UE de ruido sem sessao PDU em {timeout}s ({TUN} sem IP). "
                    f"Ultimas linhas do nr-ue:\n{log}")


def prepara(cenario, timeout=300, porta_mongo=PORTA_MONGO, log=print):
    """Tudo o que precisa acontecer DEPOIS do deploy e ANTES de ligar o fundo."""
    aplica(timeout)
    est = placement(cenario)
    log(f"  ruido: gerador em {est['no_gerador']} (ancora {ANCORA[cenario]} em "
        f"{est['no_ancora']}), UERANSIM de ruido em {est['no_ruido']}")
    cadastra(porta_mongo)
    ue = reinicia_ue(timeout)
    # De novo: o pod recriado tem OUTRO IP, e a capacidade mede ate' ele. Com
    # o placement de antes do restart o iperf da capacidade ficava pendurado
    # num IP que nao existe mais (piloto do B de 26/09/2026).
    est = placement(cenario)
    est.update(ue_ip=ue, cenario=cenario)
    log(f"  ruido: UE {IMSI} com sessao PDU, {TUN} = {est['ue_ip']}")
    return est


def estado_atual(cenario):
    """O estado de um ruido JA' preparado (para a linha de comando)."""
    est = placement(cenario)
    est["ue_ip"] = ue_ip()
    est["cenario"] = cenario
    if not est["ue_ip"]:
        raise ErroRuido(f"UE de ruido sem sessao ({TUN} sem IP): rode 'sobe' antes")
    return est


# --------------------------------------------------------------------------
# contadores
# --------------------------------------------------------------------------
def contadores_if(deploy, container, iface):
    """rx/tx (bytes, pacotes) de uma interface, lidos do /proc/net/dev do pod."""
    r = em(deploy, container, "cat", "/proc/net/dev")
    for linha in r.stdout.splitlines():
        m = re.match(r"\s*([^:]+):\s*(.*)$", linha)
        if m and m.group(1).strip() == iface:
            c = m.group(2).split()
            return {"rx_bytes": int(c[0]), "rx_pkts": int(c[1]),
                    "tx_bytes": int(c[8]), "tx_pkts": int(c[9])}
    return None


def contadores_gtpu():
    """Contadores da chain RUIDO-GTPU, na ordem das regras do manifesto:
    pequenos (passam), entregues ao UERANSIM (limite), descartados."""
    r = em(RUIDO, "iperf", "iptables", "-nvx", "-L", CHAIN)
    regras = []
    for linha in r.stdout.splitlines():
        c = linha.split()
        if len(c) >= 3 and c[0].isdigit() and c[1].isdigit():
            regras.append((int(c[0]), int(c[1])))
    if len(regras) != 3:
        return None
    (pp, pb), (ep, eb), (dp, db) = regras
    return {"pequenos_pkts": pp, "grandes_pkts": ep + dp, "grandes_bytes": eb + db,
            "entregues_pkts": ep, "descartados_pkts": dp}


def delta(a, b):
    if a is None or b is None:
        return None
    return {k: b[k] - a[k] for k in a}


def qos_gtp5g(cenario):
    """/proc/gtp5g/qos do no da ancora (modulo de kernel: e' do HOST). '1' =
    o gtp5g aplica a AMBR -- por isso o UE de ruido tem AMBR alta."""
    r = em(DEPLOY_UPF[ANCORA[cenario]], None, "cat", "/proc/gtp5g/qos", timeout=30)
    return r.stdout.strip() or None


def origem_gtpu(segundos=4):
    """{ip: pacotes} de ORIGEM do GTP-U grande que chega ao pod de ruido. E' a
    prova do caminho: tem que ser SO' o pod da UPF de ancoragem."""
    r = em(RUIDO, "iperf", "timeout", str(segundos), "tcpdump", "-n", "-l", "-i", "eth0",
           "-c", "30", "udp dst port 2152 and greater 1000", timeout=segundos + 30)
    fontes = {}
    # Origem por IP, sem supor a porta de origem que o gtp5g usa.
    for m in re.finditer(r"IP (\d+\.\d+\.\d+\.\d+)\.\d+ > \d+\.\d+\.\d+\.\d+\.2152\b",
                         r.stdout):
        fontes[m.group(1)] = fontes.get(m.group(1), 0) + 1
    return fontes


def ips_da_upf(papel):
    """IPs com que o GTP-U de uma UPF pode chegar ao gNB: o do pod E o
    ClusterIP do Service (mesmo nome do epc-mode). O N3 e' enderecado ao
    ClusterIP (endpoints do smfcfg); o kube-proxy faz DNAT do uplink para o
    pod, e o downlink da UPF para o gNB -- mesmas portas, 2152 <-> 2152 -- cai
    no conntrack como RESPOSTA desse fluxo e sai com a origem trocada de volta
    para o ClusterIP. Visto no piloto do B de 26/09/2026: o fundo chegou de
    10.108.124.178, o ClusterIP do psa-upf, e nao do pod."""
    _, ip_pod = pod(f"epc-mode={papel}")
    r = kubectl("get", "svc", papel, "-o", "jsonpath={.spec.clusterIP}")
    return {ip for ip in (ip_pod, r.stdout.strip()) if ip}


def confere_origem(cenario, fontes):
    """(ok, texto). ok None = nada chegou para julgar."""
    anc = ips_da_upf(ANCORA[cenario])
    borda = ips_da_upf(BORDA[cenario]) if BORDA[cenario] else set()
    if not fontes:
        return None, "nenhum GTP-U do fundo capturado no pod de ruido"
    nomes = {**{ip: BORDA[cenario] for ip in borda}, **{ip: ANCORA[cenario] for ip in anc}}
    desc = ", ".join(f"{nomes.get(ip, ip)} via {ip} ({n})" for ip, n in sorted(fontes.items()))
    if anc and set(fontes) <= anc:
        return True, f"GTP-U do fundo veio so' da {ANCORA[cenario]}: {desc}"
    return False, (f"GTP-U do fundo veio de {desc}; esperado so' da {ANCORA[cenario]} "
                   f"({', '.join(sorted(anc)) or '?'})"
                   + (" -- o fundo esta' passando pelo Edge Node" if set(fontes) & borda else ""))


# --------------------------------------------------------------------------
# fundo
# --------------------------------------------------------------------------
def taxa_iperf(pedido_mbps):
    """Taxa de payload para o iperf com datagrama de 1356 B que poe no fio a
    MESMA taxa de pacotes do pedido em datagramas de 1400 B."""
    return pedido_mbps * DATAGRAMA / DATAGRAMA_EQUIV


def capacidade(est, segundos=10):
    """iperf3 TCP, 4 fluxos, do gerador ao pod de ruido, FORA do tunel: o
    mesmo fio petshopboys -> brix-03 que o GTP-U do fundo percorre."""
    for tentativa in (1, 2):
        r = em(GERADOR, "iperf", "iperf3", "-c", est["ip_ruido"], "-p", str(PORTA),
               "-P", "4", "-t", str(segundos), "-J", timeout=segundos + 60)
        j = json_de(r.stdout) if r.stdout.strip() else {
            "error": f"kubectl exec rc={r.returncode}: {(r.stderr or 'sem saida').strip()[:300]}"}
        if "busy" in str(j.get("error", "")) and tentativa == 1:
            time.sleep(10)
            continue
        break
    rec = ((j.get("end") or {}).get("sum_received") or {}).get("bits_per_second")
    if j.get("error") or not rec:
        raise ErroRuido(f"nao consegui medir a capacidade ate' {est['ip_ruido']}: "
                        f"{j.get('error', 'sem vazao recebida')}")
    return rec / 1e6


def mata():
    """Para o fundo pelos dois lados. O cliente (no UE) avisa o servidor e
    sai; matar tambem o servidor no gerador garante que nada segue enviando se
    o controle se perdeu -- o laco do manifesto o sobe de novo em 1 s."""
    em(RUIDO, "iperf", "pkill", "-f", "^iperf3 -c", timeout=30)
    em(GERADOR, "iperf", "pkill", "-f", f"^iperf3 -s -p {PORTA}$", timeout=30)
    em(GERADOR, "iperf", "pkill", "-f", "^iperf3 -c", timeout=30)   # controle de CPU
    time.sleep(2)


def liga(est, pedido_mbps, segundos):
    """Liga o fundo (UDP, gerador -> UE, pelo tunel). pedido em Mbps no
    padrao de 1400 B (ver o cabecalho). Devolve o estado para desliga()."""
    taxa = taxa_iperf(pedido_mbps)
    fluxos = max(1, math.ceil(taxa / MBPS_POR_FLUXO))
    cmd = ["kubectl", "-n", NS, "exec", f"deploy/{RUIDO}", "-c", "iperf", "--",
           "iperf3", "-c", est["ip_gerador"], "-p", str(PORTA), "-B", est["ue_ip"],
           "-R", "-u", "-b", f"{taxa / fluxos:.1f}M", "-l", str(DATAGRAMA),
           "-P", str(fluxos), "-t", str(math.ceil(segundos)), "-J"]
    antes = {"gtpu": contadores_gtpu(), "gerador": contadores_if(GERADOR, "iperf", "eth0")}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    return {"proc": proc, "antes": antes, "t0": time.time(), "pedido_mbps": pedido_mbps,
            "taxa_iperf_mbps": taxa, "fluxos": fluxos}


def desliga(lig, esperar_s=None):
    """Desliga e devolve o que o fundo fez. esperar_s: espera o iperf terminar
    sozinho (piloto); None: para agora (campanha, no fim da medicao)."""
    proc = lig["proc"]
    saida = ""
    if esperar_s is not None:
        try:
            saida, _ = proc.communicate(timeout=esperar_s + 60)
        except subprocess.TimeoutExpired:
            proc.kill()
    t_fim = time.time()
    mata()
    if esperar_s is None:
        try:
            saida, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    seg = t_fim - lig["t0"]
    g = delta(lig["antes"]["gtpu"], contadores_gtpu())
    e = delta(lig["antes"]["gerador"], contadores_if(GERADOR, "iperf", "eth0"))
    reg = {"modo": "gtp", "pedido_mbps": lig["pedido_mbps"],
           "taxa_iperf_mbps": round(lig["taxa_iperf_mbps"], 1), "datagrama": DATAGRAMA,
           "fluxos": lig["fluxos"], "segundos_ligado": round(seg, 1),
           "enviado_mbps": None, "cruzou_mbps": None, "gtpu_ip_mbps": None, "gtpu_pkts": None,
           "perda_caminho_pct": None, "entregues_ue_pkts": None, "descartados_no_ruido_pkts": None}
    mbps = lambda pkts: pkts * DATAGRAMA_EQUIV * 8 / seg / 1e6   # noqa: E731
    if e and seg > 0:
        reg["enviado_mbps"] = mbps(e["tx_pkts"])
    if g and seg > 0:
        reg["cruzou_mbps"] = mbps(g["grandes_pkts"])
        reg["gtpu_pkts"] = g["grandes_pkts"]
        reg["gtpu_ip_mbps"] = g["grandes_bytes"] * 8 / seg / 1e6
        reg["entregues_ue_pkts"] = g["entregues_pkts"]
        reg["descartados_no_ruido_pkts"] = g["descartados_pkts"]
        if e and e["tx_pkts"]:
            reg["perda_caminho_pct"] = max(0.0, 1 - g["grandes_pkts"] / e["tx_pkts"]) * 100
    j = json_de(saida) if saida else {}
    if j.get("error"):
        reg["erro_iperf"] = j["error"]
    elif not saida and esperar_s is not None:
        reg["erro_iperf"] = "iperf sem saida (timeout)"
    return reg


def liga_loopback(pedido_mbps, segundos):
    """Controle de CPU do piloto: a MESMA carga de fundo, do gerador para o
    proprio loopback. O gerador trabalha igual e nada sai para a rede."""
    taxa = taxa_iperf(pedido_mbps)
    fluxos = max(1, math.ceil(taxa / MBPS_POR_FLUXO))
    cmd = ["kubectl", "-n", NS, "exec", f"deploy/{GERADOR}", "-c", "iperf", "--",
           "iperf3", "-c", "127.0.0.1", "-p", str(PORTA_LOOPBACK), "-u",
           "-b", f"{taxa / fluxos:.1f}M", "-l", str(DATAGRAMA), "-P", str(fluxos),
           "-t", str(math.ceil(segundos)), "-J"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")


def prova_caminho(est, mbps=50, segundos=6, log=print):
    """Fundo curto SEM trafego do experimento, para ver por onde ele passa:
      - a origem do GTP-U que chega ao pod de ruido (tcpdump): so' a ancora;
      - no B, a eth0 do I-UPF parada: o fundo nao toca o Edge Node;
      - a upfgtp da ancora contando o que desceu (a UPF encapsulou o fundo).
    Devolve (problemas, detalhes)."""
    cen = est["cenario"]
    anc = DEPLOY_UPF[ANCORA[cen]]
    borda = DEPLOY_UPF[BORDA[cen]] if BORDA[cen] else None
    a0 = contadores_if(anc, None, "upfgtp")
    b0 = contadores_if(borda, None, "eth0") if borda else None
    lig = liga(est, mbps, segundos)
    time.sleep(2)
    fontes = origem_gtpu()
    reg = desliga(lig, esperar_s=segundos)
    da = delta(a0, contadores_if(anc, None, "upfgtp"))
    db = delta(b0, contadores_if(borda, None, "eth0")) if borda else None
    ok, texto = confere_origem(cen, fontes)
    problemas = [] if ok else [texto]
    det = {"fontes": fontes, "origem": texto, "ruido": reg, "ancora_upfgtp": da,
           "borda_eth0": db, "qos_gtp5g": qos_gtp5g(cen)}
    gtpu_bytes = (reg["gtpu_ip_mbps"] or 0) * 1e6 / 8 * reg["segundos_ligado"]
    if not reg["gtpu_pkts"]:
        problemas.append("nenhum pacote do fundo chegou ao pod de ruido"
                         + (f" (iperf: {reg['erro_iperf']})" if reg.get("erro_iperf") else ""))
    elif da is None or da["tx_pkts"] < 0.5 * reg["gtpu_pkts"]:
        problemas.append(f"a upfgtp da {ANCORA[cen]} nao contou o fundo: ele nao saiu pela "
                         "UPF de ancoragem")
    if db is not None and gtpu_bytes and db["rx_bytes"] > 0.1 * gtpu_bytes:
        problemas.append(f"a eth0 do {BORDA[cen]} recebeu {db['rx_bytes'] / 1e6:.1f} MB durante "
                         f"a prova ({gtpu_bytes / 1e6:.1f} MB de fundo): o fundo passa pelo "
                         "Edge Node")
    log(f"  ruido: {texto}")
    log(f"  ruido: {mbps:g} Mbps pedidos, cruzaram {reg['cruzou_mbps'] or 0:.1f}; "
        f"upfgtp da {ANCORA[cen]} TX +{(da or {}).get('tx_pkts', '?')} pkts"
        + (f"; eth0 do {BORDA[cen]} RX +{db['rx_bytes'] / 1e3:.0f} kB" if db else "")
        + f"; /proc/gtp5g/qos = {det['qos_gtp5g']}")
    return problemas, det


# --------------------------------------------------------------------------
# linha de comando
# --------------------------------------------------------------------------
def status():
    for app in (GERADOR, RUIDO):
        no, ip = pod(f"app={app}")
        print(f"  {app:<16} {no or '-'} {ip or '(nao esta Running)'}")
    if pod(f"app={RUIDO}")[1]:
        print(f"  UE {IMSI}: {TUN} = {ue_ip() or '(sem IP)'}; registrado: {ue_registrado()}")
        g = contadores_gtpu()
        if g:
            print(f"  chain {CHAIN}: {g['grandes_pkts']} pacotes de fundo, "
                  f"{g['entregues_pkts']} entregues ao UERANSIM, "
                  f"{g['descartados_pkts']} descartados, {g['pequenos_pkts']} pequenos")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=("sobe", "prova", "capacidade", "liga", "status", "desce"))
    ap.add_argument("--cenario", choices=("a", "b"),
                    help="o cenario no ar (sobe, prova, liga; default: o que tiver UPF no ar)")
    ap.add_argument("--mbps", type=float, default=50,
                    help="liga/prova: fundo em Mbps no padrao de 1400 B (default: 50)")
    ap.add_argument("--segundos", type=float, default=20)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--porta-mongo", type=int, default=PORTA_MONGO)
    args = ap.parse_args()

    cen = args.cenario
    if args.acao in ("sobe", "prova", "liga") and not cen:
        cen = "b" if pod("epc-mode=psa-upf")[0] else ("a" if pod("epc-mode=upf")[0] else None)
        if not cen:
            ap.error("nenhum cenario no ar (nem upf nem psa-upf): suba um com deploy.py")
        print(f"  cenario no ar: {cen.upper()}")
    try:
        if args.acao == "sobe":
            prepara(cen, args.timeout, args.porta_mongo)
        elif args.acao == "prova":
            problemas, _ = prova_caminho(estado_atual(cen), args.mbps)
            for p in problemas:
                print(f"  PROBLEMA: {p}")
            print("  caminho do fundo OK" if not problemas else "  caminho do fundo ERRADO")
            return 1 if problemas else 0
        elif args.acao == "capacidade":
            est = placement(cen or ("b" if pod("epc-mode=psa-upf")[0] else "a"))
            print(f"  capacidade util {est['no_gerador']} -> {est['no_ruido']}: "
                  f"{capacidade(est):.0f} Mbps")
        elif args.acao == "liga":
            lig = liga(estado_atual(cen), args.mbps, args.segundos)
            print(f"  fundo ligado: {args.mbps:g} Mbps por {args.segundos:g}s "
                  f"({lig['fluxos']} fluxo(s), iperf a {lig['taxa_iperf_mbps']:.1f} Mbps)")
            try:
                reg = desliga(lig, esperar_s=args.segundos)
            except KeyboardInterrupt:
                reg = desliga(lig)
            print(json.dumps(reg, indent=2))
        elif args.acao == "status":
            status()
        else:
            mata()
            desce()
            print("  ruido removido")
    except ErroRuido as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
