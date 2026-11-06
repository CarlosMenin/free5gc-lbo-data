#!/usr/bin/env python3
"""
mec-af -- Application Function (AF) do TG2: Local Breakout com IP DINAMICO.

Resolve por DNS os servicos MEC listados em SERVICES e, para cada um, mantem
uma assinatura de Traffic Influence no NEF do free5gc (TS 29.522,
/3gpp-traffic-influence/v1). O nucleo faz o resto:

    mec-app.free5gc.svc.cluster.local --DNS--> mec-af --POST/PUT/DELETE--> NEF
        NEF --PUT influenceData--> UDR --notifica por sessao--> PCF
        PCF --SmPolicyUpdateNotify--> SMF --PFCP Session Modification--> I-UPF
        I-UPF instala o PDR: SDF = ClusterIP do servico, rota = DNAI "mec"

O IP do servico MEC vira um dado de RUNTIME: o k8s aloca o que quiser, o AF
descobre pelo CoreDNS e anuncia, e o branch ULCL aparece tanto nas sessoes PDU
ja' abertas quanto nas novas. Nada de ClusterIP literal no ueRouting.yaml,
nada de reiniciar o SMF.

POR QUE DNS E NAO A API DO KUBERNETES
-------------------------------------
Todo o resto do testbed ja' se enderecca por nome (o smfcfg aponta os UPFs em
i-upf.free5gc.svc.cluster.local, os NFs acham o NRF assim), entao o AF usa a
mesma fonte de verdade: o A record de um Service e' exatamente o ClusterIP que
ele tem agora. Em troca, este AF NAO precisa de ServiceAccount, Role nem
RoleBinding -- ele nao fala com a API do cluster, e portanto nao depende de
permissao de RBAC que a conta do testbed pode nao ter.

O que se perde: descobrir servicos por label, e reagir no instante da mudanca.
Nenhum dos dois importa aqui. A lista de servicos de borda do experimento e'
conhecida (esta' em SERVICES) e o ClusterIP so' muda quando o Service e'
recriado, o que acontece no deploy. Com POLL_S segundos de sondagem a regra
nova chega bem antes de a campanha comecar -- e, o que interessa para o TG2,
chega TAMBEM em sessoes PDU que ja' estao abertas.

Duas particularidades do NEF do free5gc moldam o desenho:

  * ele guarda as assinaturas SO' EM MEMORIA, entao um NEF reiniciado perde
    todas. Como a listagem devolve o campo "self" (com o id), este AF ADOTA
    a cada ciclo o que ja' existe sob o seu AF_ID em vez de recriar. Sem isso
    a campanha com --repeticoes acumularia uma assinatura nova por rodada;
  * o registro correspondente no UDR ganha um UUID novo a cada POST, entao um
    NEF que reinicia deixa registros orfaos la' (com o mesmo SDF). Cada orfao
    vira uma PCC rule duplicada em toda sessao. Por isso o AF varre o UDR
    antes de (re)criar assinaturas e apaga o que tem a assinatura dele
    (AnyUE + DNN + DNAI + SDF no formato daqui). E' o unico contato direto
    com o UDR; todo o resto passa pelo NEF, como manda a 3GPP.

So' biblioteca padrao: roda em python:3.12-slim sem pip e sem credencial
nenhuma montada no pod.

Variaveis de ambiente (todas com default para o testbed):
    NS          namespace, para montar o FQDN         free5gc
    SERVICES    servicos de borda, separados por ,    mec-app
                (nome curto vira <nome>.<NS>.svc.cluster.local; um FQDN
                 ou um IP literal tambem sao aceitos)
    NEF_URL     base do NEF                           http://nef.free5gc.svc.cluster.local:8000
    UDR_URL     base do UDR (so' para limpar orfaos)  http://udr.free5gc.svc.cluster.local:8000
                (o prefixo /nudr-dr/v2 ou /v1 e' descoberto na primeira chamada)
    AF_ID       id do AF na URL do NEF                af001
    DNN         DNN das sessoes alvo                  internet
    SNSSAIS     lista sst:sd separada por virgula     1:010203,1:112233
    UE_CIDR     pool dos UEs (lado "to" do SDF)       60.60.0.0/16
    DNAI        DNAI do dominio de borda (smfcfg)     mec
    NOTIFY_URL  destino das notificacoes do NEF       http://mec-af.free5gc.svc.cluster.local:8080/notify
    POLL_S      intervalo de sondagem do DNS          10
    HTTP_PORT   porta do servidor de notificacao      8080
"""
import json
import os
import re
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def env(name, default):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


CFG = {
    "ns": env("NS", "free5gc"),
    "services": env("SERVICES", "mec-app"),
    "nef_url": env("NEF_URL", "http://nef.free5gc.svc.cluster.local:8000").rstrip("/"),
    "udr_url": env("UDR_URL", "http://udr.free5gc.svc.cluster.local:8000").rstrip("/"),
    "af_id": env("AF_ID", "af001"),
    "dnn": env("DNN", "internet"),
    "snssais": env("SNSSAIS", "1:010203,1:112233"),
    "ue_cidr": env("UE_CIDR", "60.60.0.0/16"),
    "dnai": env("DNAI", "mec"),
    "notify_url": env("NOTIFY_URL", "http://mec-af.free5gc.svc.cluster.local:8080/notify"),
    "poll_s": int(env("POLL_S", "10")),
    "http_port": int(env("HTTP_PORT", "8080")),
}


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def parse_snssais(spec):
    out = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        sst, _, sd = item.partition(":")
        s = {"sst": int(sst)}
        if sd:
            s["sd"] = sd
        out.append((item, s))
    return out


def parse_services(spec):
    """Nome curto -> FQDN do Service. FQDN e IP literal passam intactos."""
    out = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        fqdn = item if ("." in item) else f"{item}.{CFG['ns']}.svc.cluster.local"
        out.append((item.split(".")[0], fqdn))
    return out


SNSSAIS = parse_snssais(CFG["snssais"])
SERVICES = parse_services(CFG["services"])


def snssai_key(s):
    s = s or {}
    return f"{s.get('sst')}:{s.get('sd', '')}".rstrip(":")


def resolve(fqdn):
    """ClusterIP atual do Service, ou None se o nome nao resolve.

    Um Service normal tem um A record com o ClusterIP. Nao resolver significa,
    na pratica, que o Service nao existe (ainda) -- o que e' o sinal de que a
    assinatura correspondente deve sair do NEF."""
    try:
        return socket.gethostbyname(fqdn)
    except socket.gaierror:
        return None


def http(method, url, body=None, timeout=15):
    """Devolve (status, headers, corpo) sem lancar em 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                parsed = json.loads(raw) if raw else None
            except ValueError:
                parsed = raw.decode(errors="replace")
            return r.status, dict(r.headers), parsed
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


# ------------------------------------------------------------------ NEF
class Nef:
    """Cliente da API Nnef_TrafficInfluence (TS 29.522 §5.4)."""

    def __init__(self):
        self.url = f"{CFG['nef_url']}/3gpp-traffic-influence/v1/{CFG['af_id']}/subscriptions"

    @staticmethod
    def sub_id(headers, body):
        loc = headers.get("Location")
        if not loc and isinstance(body, dict):
            loc = body.get("self")
        return loc.rstrip("/").rsplit("/", 1)[-1] if loc else None

    def alive(self):
        """QUALQUER resposta HTTP significa NEF no ar -- inclusive 404.

        O AF so' passa a existir no NEF quando a PRIMEIRA assinatura e' criada
        (PostTrafficInfluenceSubscription faz NewAf se nao achar); ate' la' o
        GET da lista responde 404 "AF is not found". Exigir 200 aqui era
        esperar por uma condicao que so' o proprio POST produz -- deadlock."""
        try:
            http("GET", self.url)
            return True
        except OSError as e:      # conexao recusada, DNS, timeout
            log(f"NEF ainda nao responde: {type(e).__name__}: {e}")
            return False

    def list(self):
        """(status, lista). 404 = o AF ainda nao existe, o que e' normal antes
        do primeiro POST e equivale a uma lista vazia."""
        st, _, body = http("GET", self.url)
        return st, (body if isinstance(body, list) else [])

    def create(self, body):
        return http("POST", self.url, body)

    def update(self, sub_id, body):
        return http("PUT", f"{self.url}/{sub_id}", body)

    def delete(self, sub_id):
        return http("DELETE", f"{self.url}/{sub_id}")


# ------------------------------------------------------------------ UDR (so' limpeza)
class Udr:
    """Acesso direto ao UDR APENAS para apagar registros orfaos deixados por
    um NEF reiniciado. Nunca cria nem altera nada aqui."""

    def __init__(self):
        self.url = None     # resolvido na primeira chamada: v2 (atual) ou v1 (guia)

    def _resolve(self):
        if self.url:
            return True
        for ver in ("v2", "v1"):
            url = f"{CFG['udr_url']}/nudr-dr/{ver}/application-data/influenceData"
            # Basta o 200: com a consulta vazia o UDR responde 200 com corpo
            # "null" (nao "[]"), entao exigir uma lista aqui so' encontraria a
            # versao certa quando ja' houvesse dado gravado.
            if http("GET", f"{url}?dnns={urllib.parse.quote(CFG['dnn'])}")[0] == 200:
                self.url = url
                log(f"UDR: influenceData em {url}")
                return True
        log("UDR: nenhuma versao de /nudr-dr respondeu 200; sem varredura desta vez")
        return False

    def list_ours(self):
        """Registros de influenceData com a assinatura deste AF: (id, ip, snssai)."""
        if not self._resolve():
            return None
        st, _, body = http("GET", f"{self.url}?dnns={urllib.parse.quote(CFG['dnn'])}")
        if st != 200:
            log(f"UDR GET influenceData -> {st}; sem varredura")
            return None
        body = body or []       # corpo "null" = nenhum registro
        ours = []
        for it in body:
            if not isinstance(it, dict) or it.get("interGroupId") != "AnyUE":
                continue
            if it.get("dnn") != CFG["dnn"]:
                continue
            routes = it.get("trafficRoutes") or []
            if not routes or routes[0].get("dnai") != CFG["dnai"]:
                continue
            ip = None
            for tf in it.get("trafficFilters") or []:
                for fd in tf.get("flowDescriptions") or []:
                    m = FLOW_RE.match(fd)
                    if m:
                        ip = m.group(1)
            res = it.get("resUri") or ""
            iid = res.rstrip("/").rsplit("/", 1)[-1] if res else None
            if ip and iid:
                ours.append((iid, ip, snssai_key(it.get("snssai"))))
        return ours

    def delete(self, iid):
        return http("DELETE", f"{self.url}/{iid}")[0]


# ------------------------------------------------------------------ regra
def flow_description(ip):
    # Mesmo formato do guia oficial (free5gc.org/guide/8-traffic-influence):
    # "out" = sentido downlink (servidor -> UE); o UPF aplica nos dois sentidos.
    return f"permit out ip from {ip}/32 to {CFG['ue_cidr']}"


FLOW_RE = re.compile(
    r"^permit out ip from (\d+\.\d+\.\d+\.\d+)/32 to " + re.escape(CFG["ue_cidr"]) + r"$")


def subscription_body(svc, ip, snssai):
    return {
        "afServiceId": svc,
        "dnn": CFG["dnn"],
        "snssai": snssai,
        "anyUeInd": True,
        "notificationDestination": CFG["notify_url"],
        "trafficFilters": [{"flowId": 1, "flowDescriptions": [flow_description(ip)]}],
        "trafficRoutes": [{"dnai": CFG["dnai"]}],
    }


# ------------------------------------------------------------------ reconciliacao
class Reconciler:
    """Mantem (servico x S-NSSAI) -> assinatura no NEF com o ClusterIP atual."""

    def __init__(self, nef, udr):
        self.nef, self.udr = nef, udr
        self.subs = {}          # (svc, snssai_key) -> {"id": str, "ip": str}
        self.lock = threading.Lock()

    def snapshot(self):
        with self.lock:
            return {f"{k[0]}/{k[1]}": dict(v) for k, v in self.subs.items()}

    # --- adocao: reconstroi o estado a partir do proprio NEF ----------
    def adopt(self):
        """Le as assinaturas que existem sob o nosso AF_ID e assume o controle.

        Torna o restart do mec-af idempotente: se a assinatura certa ja' esta'
        la', nada e' criado. O AF_ID e' de uso exclusivo deste controlador,
        entao o que estiver sob ele e nao corresponder a um servico de
        SERVICES e' resto de execucao anterior e sai."""
        st, subs = self.nef.list()
        if st == 404:
            self.subs = {}          # AF ainda nao existe: nada a adotar
            return True
        if st != 200:
            log(f"NEF GET subscriptions -> {st}; mantendo o estado atual")
            return False
        nossos = {n for n, _ in SERVICES}
        novo, lixo = {}, []
        for s in subs:
            sid = self.nef.sub_id({}, s)
            svc = s.get("afServiceId")
            ip = None
            for tf in s.get("trafficFilters") or []:
                for fd in tf.get("flowDescriptions") or []:
                    m = FLOW_RE.match(fd)
                    if m:
                        ip = m.group(1)
            key = (svc, snssai_key(s.get("snssai")))
            if not sid or svc not in nossos or ip is None or key in novo:
                lixo.append(sid)
                continue
            novo[key] = {"id": sid, "ip": ip}
        for sid in lixo:
            if sid:
                log(f"NEF: apagando assinatura {sid} sem dono (resto de execucao "
                    f"anterior) -> {self.nef.delete(sid)[0]}")
        if novo != self.subs:
            log(f"adotadas {len(novo)} assinatura(s) do NEF: "
                + (", ".join(f"{k[0]}[{k[1]}]=sub {v['id']}@{v['ip']}"
                             for k, v in sorted(novo.items())) or "nenhuma"))
        self.subs = novo
        return True

    # --- UDR: apagar o que nao corresponde a uma assinatura viva ------
    def sweep_udr(self):
        ours = self.udr.list_ours()
        if ours is None:
            return
        vivas = {(v["ip"], k[1]) for k, v in self.subs.items()}
        # Uma assinatura viva tem exatamente UM registro; qualquer repetido
        # (mesmo ip+slice) e' orfao de um NEF anterior. Mantemos so' o ultimo
        # visto, que e' o que o NEF atual escreveu por ultimo.
        vistos = set()
        for iid, ip, sk in reversed(ours):
            chave = (ip, sk)
            if chave in vivas and chave not in vistos:
                vistos.add(chave)
                continue
            st = self.udr.delete(iid)
            log(f"UDR: apagado influenceData {iid} ({ip} [{sk}]) orfao -> {st}")

    # --- garantir / remover -------------------------------------------
    def ensure(self, svc, ip):
        for sk, snssai in SNSSAIS:
            key = (svc, sk)
            cur = self.subs.get(key)
            if cur and cur["ip"] == ip:
                continue
            body = subscription_body(svc, ip, snssai)
            if cur:
                st, _, resp = self.nef.update(cur["id"], body)
                if st in (200, 204):
                    log(f"{svc} [{sk}] {cur['ip']} -> {ip}: PUT ok (sub {cur['id']})")
                    cur["ip"] = ip
                    continue
                log(f"{svc} [{sk}] PUT sub {cur['id']} -> {st}: {resp}; recriando")
                self.subs.pop(key, None)
            st, hdr, resp = self.nef.create(body)
            sid = self.nef.sub_id(hdr, resp) if st == 201 else None
            if sid:
                self.subs[key] = {"id": sid, "ip": ip}
                log(f"{svc} [{sk}] -> {ip}: POST ok (sub {sid}); "
                    f"SDF='{flow_description(ip)}' dnai={CFG['dnai']}")
            else:
                log(f"{svc} [{sk}] POST -> {st}: {resp}")

    def remove(self, svc):
        for key in [k for k in self.subs if k[0] == svc]:
            cur = self.subs.pop(key)
            st, _, _ = self.nef.delete(cur["id"])
            log(f"{svc} [{key[1]}] removido: DELETE sub {cur['id']} -> {st}")

    def tick(self, desired):
        """desired: {nome_curto: ip}. Chamado a cada sondagem do DNS."""
        with self.lock:
            # A adocao ja' cobre o NEF reiniciado: a lista volta vazia (ou 404)
            # e o estado local zera junto, entao tudo e' recriado.
            if not self.adopt():
                return
            faltando = {(s, sk) for s in desired for sk, _ in SNSSAIS} - set(self.subs)
            for svc in {k[0] for k in self.subs} - set(desired):
                self.remove(svc)
            if faltando:
                # Varre o UDR ANTES de criar: o registro velho do mesmo IP
                # seria uma PCC rule duplicada em cada sessao. So' quando ha'
                # algo a criar, para nao sondar o UDR a cada 10s a toa.
                self.sweep_udr()
            for svc, ip in desired.items():
                self.ensure(svc, ip)

    # Nao existe shutdown() de proposito -- veja o comentario em term().


# ------------------------------------------------------------------ HTTP (notificacoes + estado)
def http_server(rec):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/healthz"):
                self._send(200, b"ok", "text/plain")
            elif self.path.startswith("/status"):
                self._send(200, json.dumps(
                    {"config": CFG, "subscriptions": rec.snapshot()}, indent=2).encode())
            else:
                self._send(404)

        def do_POST(self):
            # UpPathChange e afins (TS 29.522 EventNotification). So' registramos.
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            log(f"notificacao do NEF em {self.path}: {raw.decode(errors='replace')[:500]}")
            self._send(204)

    srv = ThreadingHTTPServer(("0.0.0.0", CFG["http_port"]), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"HTTP de notificacao/estado em :{CFG['http_port']} (/notify, /status, /healthz)")


# ------------------------------------------------------------------ main
def main():
    log("mec-af iniciando com " + json.dumps(CFG))
    if not SNSSAIS:
        sys.exit("SNSSAIS vazio")
    if not SERVICES:
        sys.exit("SERVICES vazio")
    log("servicos vigiados: " + ", ".join(f"{n} -> {f}" for n, f in SERVICES))

    nef, udr = Nef(), Udr()
    rec = Reconciler(nef, udr)
    http_server(rec)

    def term(signum, frame):
        # NAO apagamos as assinaturas ao sair, por dois motivos:
        #  1. o rollout do Deployment sobrepoe os pods -- o novo ja' adotou as
        #     assinaturas quando o antigo recebe o SIGTERM, e apagar aqui
        #     derrubaria justo o que o novo acabou de assumir (foi o que
        #     aconteceu em 03/09: o novo pod recriou tudo 20s depois);
        #  2. o AF e' so' o anunciante. O valor do desenho e' a regra viver no
        #     nucleo por conta propria; reiniciar o anunciante nao pode tirar
        #     o LBO de sessoes PDU que estao no ar.
        # O que sobra e' recolhido pela adocao e pela varredura do UDR no
        # proximo boot.
        log("SIGTERM: saindo sem mexer nas assinaturas (elas sobrevivem ao AF)")
        os._exit(0)
    signal.signal(signal.SIGTERM, term)
    signal.signal(signal.SIGINT, term)

    while not nef.alive():
        log(f"aguardando o NEF em {nef.url}")
        time.sleep(5)
    log(f"NEF no ar em {nef.url}")

    anterior = None
    while True:
        try:
            desired = {}
            for nome, fqdn in SERVICES:
                ip = resolve(fqdn)
                if ip:
                    desired[nome] = ip
            if desired != anterior:
                log("DNS: " + (", ".join(f"{n}={ip}" for n, ip in sorted(desired.items()))
                               or "nenhum servico resolve"))
                anterior = desired
            rec.tick(desired)
        except Exception as e:            # noqa: BLE001 -- loop de controle
            log(f"erro no loop: {type(e).__name__}: {e}")
        time.sleep(CFG["poll_s"])


if __name__ == "__main__":
    main()
