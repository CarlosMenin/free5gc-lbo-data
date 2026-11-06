#!/usr/bin/env python3
"""
Piloto de congestao do enlace nuvem -> borda.

PARA QUE SERVE
    Antes de gastar uma campanha A x B sob congestao, quatro coisas precisam
    ser verdade -- e nenhuma delas se sabe sem medir:

    1. A CAPACIDADE do caminho petshopboys -> brix. Sem ela nao da' para dizer
       "enlace a 90%", e os niveis de carga viram numeros soltos.
    2. O FUNDO DISPUTA A MESMA FILA que a aplicacao. O switch enfileira por
       porta de saida: o fundo vai para a porta do brix-04 e a aplicacao sai
       pelas portas do brix-01 e do brix-02. Se o gargalo for so' a porta do
       brix-04, a congestao nunca chega na medida e a campanha concluiria "o
       LBO nao ajuda" por erro de montagem.
    3. O GERADOR NAO INTERFERE POR CPU. Ele roda no mesmo no da UPF central,
       que so' o cenario A usa.
    4. No cenario B, o PLANO DE CONTROLE QUE CRUZA O ENLACE sobrevive. O PFCP
       entre o SMF (nucleo) e o I-UPF (borda) desce o mesmo fio; no A o SMF e
       a UPF estao no mesmo no. Se o heartbeat se perder, o B cairia por um
       motivo que uma operadora nao permitiria (la' o controle tem prioridade).

ROTEIRO
    passos 01-10  os MESMOS do teste do cenario escolhido (--cenario a|b),
                  importados do test-cenario-X.py -- o piloto mede o ambiente
                  exato da campanha
    P1  pods do iperf (congestao/iperf.yaml) e placement: gerador no no da UPF
        de ancoragem, receptor num brix fora do experimento
    P2  capacidade: iperf3 TCP, 4 fluxos, nuvem -> borda
    P3  degraus, cada um medindo o caminho MEC com o mesmo vr_client da campanha
          base           sem fundo
          controle-cpu   fundo no LOOPBACK do gerador: gasta a CPU, nao a rede
          fundo-50%...   UDP nuvem -> borda, fracao da capacidade medida
          base-final     sem fundo de novo, para medir a deriva do proprio piloto

    Nenhum degrau passa de 100% da capacidade. Sobrecarga continua nao e' a
    congestao tipica de uma rede real (operadora nao opera enlace saturado) e
    derrubaria o plano de controle por excesso, nao por arquitetura.

LEITURA
    cenario a  o a-mec PIORA com o fundo e NAO piora no controle-cpu:
               a fila e' compartilhada e a campanha faz sentido.
    cenario b  o b-mec NAO muda, e o PFCP com o I-UPF continua vivo.

DE ONDE VEM O FUNDO (--ruido)
    gtp     (padrao desde 26/09/2026, ideia do orientador) o fundo e' trafego de
            ASSINANTE: iperf3 do no da UPF de ancoragem ate' um segundo UERANSIM
            no brix-porvir-03, PELO TUNEL GTP-U (congestao/ruido-gtp.yaml e
            scripts/ruido-gtp.py). No A ele passa pela mesma UPF central do
            experimento; no B, pelo PSA-UPF, direto para o gNB de ruido, sem
            tocar o Edge Node. P1 vira: sobe o UE de ruido e PROVA o caminho
            (origem do GTP-U, eth0 do I-UPF parada). A capacidade e' medida
            petshopboys -> brix-03, fora do tunel, pelo mesmo fio.
    direto  o piloto de 16/09/2026: iperf3 do no da UPF de ancoragem ate' o
            brix-porvir-04, sem passar por UPF (congestao/iperf.yaml).

    O controle de CPU e' o mesmo nos dois: a carga do fundo no loopback do
    gerador. No gtp ele NAO cobre o trabalho da UPF central encapsulando o
    fundo -- isso e' parte do tratamento no A (e' o que um nucleo compartilhado
    faz com os usuarios dele), e o veredito diz isso.

    python3 scripts/piloto-congestao.py --cenario a --deploy --perfil teleoperacao --carregar-assinantes 5
    python3 scripts/piloto-congestao.py --cenario b --deploy --perfil teleoperacao --carregar-assinantes 5
    python3 scripts/piloto-congestao.py --cenario a --ruido direto ...     # o piloto de 16/09
"""
import argparse
import datetime
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import textwrap
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
MANIFESTO = os.path.join(os.path.dirname(AQUI), "congestao", "iperf.yaml")

SRV = "congestao-iperf-servidor"     # receptor na borda (brix-porvir-04)
CLI = "congestao-iperf-cliente"      # gerador na nuvem (no da UPF de ancoragem)
PORTA_REDE = 5201
PORTA_LOOPBACK = 5202                # servidor do controle de CPU, no proprio gerador
MEC_DEPLOY = "free5gc-mec-app"

# epc-mode da UPF por onde o trafego centralizado entra no nucleo. E' no no
# dela que o gerador tem que estar para sair pela mesma placa de rede.
ANCORA = {"a": "upf", "b": "psa-upf"}

# Payload UDP do fundo: cabe no MTU 1450 do VXLAN do Calico sem fragmentar.
DATAGRAMA = 1400
# iperf3 -P: cada fluxo fica bem abaixo do que uma thread gera, para o fundo
# pedido ser o fundo enviado.
MBPS_POR_FLUXO = 250
# O fundo liga antes do vr_client e tem que cobrir a corrida inteira: rampa +
# warmup + duracao + a partida e a drenagem do cliente.
RAMPA_S = 2
FOLGA_S = 12

t = None                 # modulo test-cenario-a.py ou test-cenario-b.py
_fundo = None            # Popen do iperf de fundo em andamento
R = None                 # modulo ruido-gtp.py (--ruido gtp)


def carrega_ruido():
    spec = importlib.util.spec_from_file_location("ruido_gtp", os.path.join(AQUI, "ruido-gtp.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def carrega_teste(cenario):
    """Importa o teste do cenario inteiro -- deploy, placement, sessao PDU,
    rotas e contadores. O piloto so' vale se mede o MESMO ambiente que a
    campanha, e o jeito de garantir isso e' chamar as MESMAS funcoes."""
    caminho = os.path.join(AQUI, f"test-cenario-{cenario}.py")
    spec = importlib.util.spec_from_file_location(f"teste_cenario_{cenario}", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def etapa(rotulo, titulo, porque=""):
    """Mesmo visual do passo() do teste, mas com rotulo livre (P1, P2...)."""
    print(f"\n{'=' * 72}\n[{rotulo}] {titulo}\n{'=' * 72}")
    if porque and not t.CONCISO:
        for par in porque.strip().split("\n\n"):
            for linha in textwrap.wrap(" ".join(par.split()), 68):
                print(f"  {t.CINZA}# {linha}{t.RESET}")
            print()


def no_iperf(deploy, *cmd, timeout=60):
    return t.kubectl("exec", f"deploy/{deploy}", "-c", "iperf", "--", *cmd,
                     check=False, quiet=True, timeout=timeout)


def pod_de(app):
    """(no, ip) do pod ativo de um deployment do iperf."""
    r = t.kubectl("get", "pod", "-l", f"app={app}", "--field-selector=status.phase=Running",
                  "-o", "jsonpath={.items[0].spec.nodeName} {.items[0].status.podIP}",
                  check=False, quiet=True)
    partes = r.stdout.split()
    return (partes[0], partes[1]) if len(partes) == 2 else (None, None)


def json_iperf(texto):
    try:
        return json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
    except ValueError:
        return {"error": (texto or "sem saida").strip()[:300]}


def udp_erros(deploy):
    """RcvbufErrors do UDP no netns do receptor. Separa 'o fundo se perdeu no
    caminho' de 'o fundo chegou e o proprio receptor nao deu conta'."""
    r = no_iperf(deploy, "cat", "/proc/net/snmp")
    linhas = [l.split()[1:] for l in r.stdout.splitlines() if l.startswith("Udp:")]
    if len(linhas) < 2:
        return None
    campos = dict(zip(linhas[0], linhas[1]))
    try:
        return int(campos.get("RcvbufErrors", 0))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# P1 pods do iperf
# --------------------------------------------------------------------------
def p1_iperf(args, placement):
    etapa("P1", "Gerador e receptor do trafego de fundo",
          """Aplica congestao/iperf.yaml e confere onde cada pod caiu.

    O gerador precisa estar no no da UPF de ancoragem: e' la' que o trafego
    centralizado entra no fio que desce para a borda. O receptor precisa estar
    num brix do mesmo segmento do tester, mas FORA do Edge Node e do proprio
    tester -- receber quase 1 Gbps custa CPU, e o b-mec pioraria por
    processador, nao por congestao.""")
    t.kubectl("apply", "-f", MANIFESTO)
    for dep in (SRV, CLI):
        t.kubectl("rollout", "status", f"deploy/{dep}", f"--timeout={args.timeout}s",
                  timeout=args.timeout + 30)
    no_srv, ip_srv = pod_de(SRV)
    no_cli, _ = pod_de(CLI)
    ancora = placement.get(ANCORA[args.cenario])
    borda, tester = placement.get("mec-app"), placement.get("ueransim")
    print(f"       gerador   {no_cli}   (UPF de ancoragem em {ancora})")
    print(f"       receptor  {no_srv}   ({ip_srv}; Edge Node {borda}, tester {tester})")
    if not ip_srv or not no_cli:
        raise t.Falha("os pods do iperf nao ficaram Running")
    if no_cli != ancora:
        raise t.Falha(f"o gerador esta em {no_cli} e a UPF de ancoragem em {ancora}. "
                      "Fora do no da UPF o fundo sai por outra placa e pode nao "
                      "disputar fila nenhuma com a aplicacao -- ajuste o nodeSelector "
                      "de congestao-iperf-cliente em congestao/iperf.yaml")
    if no_srv in (borda, tester):
        raise t.Falha(f"o receptor caiu em {no_srv}, que e' parte do experimento "
                      "(Edge Node ou tester). Escolha outro brix em congestao/iperf.yaml")
    if t._mesmo_segmento(no_srv, tester) is False:
        raise t.Falha(f"o receptor ({no_srv}) nao esta no segmento dos brix: o fundo "
                      "nao desceria o mesmo enlace nuvem -> borda que o teste")
    r = no_iperf(CLI, "iperf3", "--version")
    info(f"iperf3: {(r.stdout.splitlines() or ['?'])[0]}")
    ok("gerador no no da UPF de ancoragem, receptor na borda fora do experimento")
    return ip_srv


# --------------------------------------------------------------------------
# P2 capacidade
# --------------------------------------------------------------------------
def p2_capacidade(args, ip_srv):
    etapa("P2", "Capacidade do caminho nuvem -> borda",
          """iperf3 TCP com 4 fluxos, do gerador ao receptor. O TCP sobe ate' o
    enlace mais estreito do caminho e para ali: o que ele entrega e' a
    capacidade util desse caminho, ja' descontados os cabecalhos.

    Os degraus de fundo sao fracoes deste numero. Sem ele, 'fundo de 900 Mbps'
    tanto pode ser 45% de um enlace de 2 Gbps quanto sobrecarga de um de 800.""")
    for tentativa in (1, 2):
        r = no_iperf(CLI, "iperf3", "-c", ip_srv, "-p", str(PORTA_REDE), "-P", "4",
                     "-t", str(args.duracao_capacidade), "-J",
                     timeout=args.duracao_capacidade + 60)
        j = json_iperf(r.stdout)
        if "busy" in str(j.get("error", "")) and tentativa == 1:
            info("servidor iperf3 ocupado com um teste anterior; tentando de novo em 10s")
            time.sleep(10)
            continue
        break
    if j.get("error"):
        raise t.Falha(f"iperf3 TCP falhou: {j['error']}")
    fim = j.get("end", {})
    rec = (fim.get("sum_received") or {}).get("bits_per_second")
    if not rec:
        raise t.Falha("iperf3 TCP nao devolveu a vazao recebida")
    retx = (fim.get("sum_sent") or {}).get("retransmits")
    cap = rec / 1e6
    ok(f"capacidade util nuvem -> borda: {cap:.0f} Mbps"
       + (f"  ({retx} retransmissoes TCP)" if retx is not None else ""))
    return cap


# --------------------------------------------------------------------------
# P1/P2 do fundo pelo tunel GTP-U (--ruido gtp)
# --------------------------------------------------------------------------
def p1_ruido(args):
    etapa("P1", "UE de ruido no brix-porvir-03 e o CAMINHO do fundo",
          """Aplica congestao/ruido-gtp.yaml, cadastra o UE de ruido (fatia 112233,
    AMBR alta), recria o pod e espera a sessao PDU. O gerador precisa estar no
    no da UPF de ancoragem; o UERANSIM de ruido, num brix do segmento do tester
    e fora do experimento.

    Depois, a PROVA DO CAMINHO, com o experimento parado: alguns segundos de
    fundo a 50 Mbps. O GTP-U que chega ao pod de ruido tem que vir SO' do pod
    da UPF de ancoragem, a upfgtp dela tem que contar o fundo, e no cenario B a
    eth0 do I-UPF tem que ficar parada -- o fundo desce do nucleo sem tocar o
    Edge Node. Se passasse pelo I-UPF, o B pioraria por CPU e placa da borda,
    nao por congestao do backhaul.""")
    try:
        est = R.prepara(args.cenario, args.timeout, log=info)
        problemas, det = R.prova_caminho(est, log=info)
    except R.ErroRuido as e:
        raise t.Falha(f"ruido: {e}")
    if problemas:
        raise t.Falha("o fundo nao esta' no caminho certo:\n       " + "\n       ".join(problemas))
    if det.get("qos_gtp5g") == "1":
        info("gtp5g com QoS ligado no no da ancora: a AMBR do UE de ruido vale como teto "
             f"(cadastrada em {R.AMBR})")
    ok("fundo pelo tunel GTP-U, saindo so' da UPF de ancoragem")
    return est, det


def p2_capacidade_gtp(args, est):
    etapa("P2", "Capacidade do caminho nuvem -> borda",
          f"""iperf3 TCP com 4 fluxos, do gerador ({est['no_gerador']}) ao pod de ruido
    ({est['no_ruido']}), FORA do tunel: o mesmo fio que o GTP-U do fundo
    percorre. O TCP sobe ate' o enlace mais estreito e para ali.

    Os degraus de fundo sao fracoes deste numero, contadas em pacotes do mesmo
    tamanho no fio que os do fundo direto (ver scripts/ruido-gtp.py).""")
    try:
        cap = R.capacidade(est, args.duracao_capacidade)
    except R.ErroRuido as e:
        raise t.Falha(str(e))
    ok(f"capacidade util nuvem -> borda: {cap:.0f} Mbps")
    return cap


# --------------------------------------------------------------------------
# P3 degraus
# --------------------------------------------------------------------------
def liga_fundo(destino, porta, mbps, segundos):
    global _fundo
    fluxos = max(1, math.ceil(mbps / MBPS_POR_FLUXO))
    cmd = ["kubectl", "-n", t.NS, "exec", f"deploy/{CLI}", "-c", "iperf", "--",
           "iperf3", "-c", destino, "-p", str(porta), "-u",
           "-b", f"{mbps / fluxos:.1f}M", "-l", str(DATAGRAMA), "-P", str(fluxos),
           "-t", str(math.ceil(segundos)), "-J"]
    _fundo = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True)
    return _fundo


def desliga_fundo(proc, segundos):
    """Espera o iperf terminar sozinho e devolve o que ele de fato entregou."""
    global _fundo
    try:
        saida, _ = proc.communicate(timeout=segundos + 60)
    except subprocess.TimeoutExpired:
        proc.kill()
        mata_fundo()
        saida = ""
    _fundo = None
    j = json_iperf(saida)
    if j.get("error"):
        return {"erro": j["error"]}
    fim = j.get("end", {})
    s = fim.get("sum") or {}
    env = (fim.get("sum_sent") or s).get("bits_per_second")
    rec = (fim.get("sum_received") or {}).get("bits_per_second")
    perda = s.get("lost_percent")
    if rec is None and env is not None and perda is not None:
        rec = env * (1 - perda / 100)
    return {"enviado_mbps": env / 1e6 if env else None,
            "recebido_mbps": rec / 1e6 if rec else None, "perda_pct": perda}


def mata_fundo():
    if R is not None:
        R.mata()
        return
    no_iperf(CLI, "pkill", "-f", "iperf3 -c", timeout=30)


def liga_degrau(args, alvo, onde, mbps, segundos):
    """Liga o fundo de um degrau. alvo: o IP do receptor (--ruido direto) ou
    o estado do ruido (--ruido gtp). Devolve (Popen, estado do ruido ou None)."""
    global _fundo
    if args.ruido == "gtp":
        if onde == "rede":
            lig = R.liga(alvo, mbps, segundos)
            _fundo = lig["proc"]
            return lig["proc"], lig
        _fundo = R.liga_loopback(mbps, segundos)
        return _fundo, None
    destino, porta = ((alvo, PORTA_REDE) if onde == "rede" else ("127.0.0.1", PORTA_LOOPBACK))
    return liga_fundo(destino, porta, mbps, segundos), None


def desliga_degrau(proc, lig, segundos):
    global _fundo
    if lig is None:
        return desliga_fundo(proc, segundos)
    _fundo = None
    f = R.desliga(lig, esperar_s=segundos)
    # Mesmas chaves do fundo direto para a tabela e o veredito: "recebido" e' o
    # que CRUZOU o enlace (contado no pod de ruido antes do descarte), no padrao
    # de 1400 B; a perda e' a do caminho gerador -> brix-03.
    f["recebido_mbps"] = f["cruzou_mbps"]
    f["perda_pct"] = f["perda_caminho_pct"]
    if not f["cruzou_mbps"] and f.get("erro_iperf"):
        f["erro"] = f["erro_iperf"]
    return f


def saude_instrumento(resumo, srv, fps_alvo):
    """So' as guardas que dizem respeito ao INSTRUMENTO. Perda, continuidade e
    poses que nao chegaram sao efeito do caminho -- sob congestao, isso e'
    resultado, e fica na tabela, nao aqui."""
    probs = []
    if not resumo.get("frames_complete"):
        probs.append("nenhum frame completo voltou")
    sa = resumo.get("saude") or {}
    if sa.get("rx_timestamp_kernel") is False:
        probs.append("sem carimbo de tempo do kernel")
    janela = resumo.get("ul_window_s") or resumo.get("duration_s")
    if srv.get("frames_sent_total") is None:
        probs.append("nao consegui ler o /metrics do mec-app")
    elif (janela and fps_alvo and not srv.get("sessions_expired_total")
          and srv["frames_sent_total"] / janela < 0.9 * fps_alvo):
        probs.append(f"o servidor emitiu {srv['frames_sent_total'] / janela:.0f} "
                     f"de {fps_alvo:.0f} fps")
    if srv.get("send_dropped_total"):
        probs.append(f"o servidor descartou {srv['send_dropped_total']:.0f} pacotes no envio")
    rec = resumo.get("dl_packets_rx_run") or 0
    drops = sa.get("dl_sock_drops")
    if drops is None:
        drops = sa.get("dl_sock_overflow_pkts")
    for onde, n in (("fila do socket do cliente", drops),
                    ("buffer UDP do netns do cliente", sa.get("udp_rcvbuf_errors"))):
        if n and rec and n / rec * 100 > t.LIMIAR_DESCARTE_LOCAL_PCT:
            probs.append(f"{n} descartes na {onde}")
    if abs(sa.get("clock_drift_us") or 0) > 1000:
        probs.append(f"o CLOCK_REALTIME andou {sa['clock_drift_us']:.0f} us")
    return probs


def extrai(resumo, srv):
    perda = resumo.get("dl_packet_loss_pct")
    if srv.get("frame_packets_total"):
        perda = max(0.0, 1 - (resumo.get("dl_packets_rx_run") or 0)
                    / srv["frame_packets_total"]) * 100
    env, rec = resumo.get("ul_packets_tx"), srv.get("pose_packets_total")
    return {"net_p50": resumo["net_rtt_us"]["p50"], "net_p95": resumo["net_rtt_us"]["p95"],
            "net_p99": resumo["net_rtt_us"]["p99"], "jitter_net": resumo.get("jitter_net_us"),
            "m2p_p50": resumo["m2p_us"]["p50"], "perda_dl_pct": perda,
            "entrega_ul_pct": (rec / env * 100) if env and rec is not None else None,
            "continuidade_pct": resumo.get("dl_continuity_pct"),
            "sessoes_expiradas": srv.get("sessions_expired_total")}


def pfcp_vivo(deploy):
    """Como o _pfcp_vivo do teste, mas mais rigoroso: la' basta a palavra
    'heartbeat' aparecer, e no passo 7 isso e' suficiente porque nada esta'
    sendo estressado. Aqui o fundo pode justamente derrubar o heartbeat, e uma
    linha de 'heartbeat timeout' nao pode contar como associacao viva.

    Lido DEPOIS do degrau, com janela de 45 s: cobre a corrida inteira."""
    r = t.kubectl("logs", f"deploy/{deploy}", "--since=45s", check=False,
                  quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    linhas = [l for l in r.stdout.splitlines() if re.search(r"heartbeat", l, re.I)]
    if any(re.search(r"timeout|fail|lost|expire|no response|not respond", l, re.I)
           for l in linhas):
        return False
    return bool(linhas)


def plano_controle():
    """PFCP de cada UPF e registro do UE, lidos depois de cada degrau."""
    return {"pfcp": {k: pfcp_vivo(d) for k, (d, _) in t.UPFS.items()},
            "ue_registrado": t._ue_registrado()}


def p3_degraus(args, ue_ip, alvo, cap):
    etapa("P3", f"Degraus de fundo: caminho MEC, {args.duracao:g}s cada",
          """Cada degrau liga o fundo, mede o caminho MEC com o mesmo vr_client da
    campanha, desliga o fundo e confere o plano de controle.

    base e base-final medem o caminho sem fundo no comeco e no fim: a
    diferenca entre os dois e' a deriva do proprio piloto, e e' contra ela (e
    contra um piso fixo) que o efeito do fundo e' julgado.

    controle-cpu manda o fundo MAIS PESADO para o loopback do gerador: a CPU do
    no da UPF trabalha igual, mas nada sai para a rede. Se o caminho MEC piorar
    aqui, o que o piloto mede e' processador, nao congestao.""")
    global _fundo
    fps = t.fps_alvo(MEC_DEPLOY)
    pose_hz = t.PERFIS[args.perfil]["pose_hz"]
    maior = max(args.fracoes) * cap
    degraus = ([("base", None, 0.0), ("controle-cpu", "loopback", maior)]
               + [(f"fundo-{f * 100:g}%", "rede", f * cap) for f in args.fracoes]
               + [("base-final", None, 0.0)])
    info("ordem: " + " -> ".join(d[0] for d in degraus))
    segundos_fundo = RAMPA_S + args.warmup + args.duracao + FOLGA_S
    registros = []
    for rotulo, onde, mbps in degraus:
        reg = {"rotulo": rotulo, "onde": onde, "fundo_pedido_mbps": mbps or None,
               "fracao": (mbps / cap) if onde == "rede" else None}
        m0 = t.metricas_servidor(MEC_DEPLOY)
        g0 = {k: t.contadores_gtp(d) for k, (d, _) in t.UPFS.items()}
        u0 = udp_erros(SRV) if onde == "rede" and args.ruido == "direto" else None
        proc = lig = None
        try:
            if onde:
                proc, lig = liga_degrau(args, alvo, onde, mbps, segundos_fundo)
                time.sleep(RAMPA_S)
            resumo = t.vr_client(t.MEC_IP, ue_ip, args.duracao, f"piloto-{rotulo}",
                                 warmup=args.warmup, pose_hz=pose_hz)
        except t.Falha as e:
            reg["erro"] = str(e).splitlines()[0]
            resumo = None
        except BaseException:
            # Ctrl+C: nao espera o iperf terminar sozinho; a limpeza do main
            # mata o que sobrar dentro do pod.
            if proc is not None:
                proc.kill()
            raise
        # Contadores do servidor LOGO depois da corrida, antes de esperar o
        # fundo acabar: o vr-server segue emitindo frames ate' a sessao expirar,
        # e esses pacotes entrariam no denominador da perda como se tivessem
        # se perdido no caminho.
        m1 = t.metricas_servidor(MEC_DEPLOY)
        g1 = {k: t.contadores_gtp(d) for k, (d, _) in t.UPFS.items()}
        reg["fundo"] = desliga_degrau(proc, lig, segundos_fundo) if proc else None
        if u0 is not None and reg["fundo"] is not None:
            u1 = udp_erros(SRV)
            reg["fundo"]["descartes_receptor"] = None if u1 is None else u1 - u0
        reg["gtp"] = {k: t.delta(g0[k], g1[k]) for k in g0}
        reg["plano_controle"] = cp = plano_controle()
        if resumo is not None:
            srv = {k: t._d(m0, m1, f"vr_server_{k}") for k in (
                "frames_sent_total", "frame_packets_total", "send_dropped_total",
                "pose_packets_total", "sessions_expired_total")}
            reg["resumo"], reg["servidor"] = resumo, srv
            reg["metricas"] = extrai(resumo, srv)
            reg["instrumento"] = saude_instrumento(resumo, srv, fps)
        imprime_degrau(reg)
        registros.append(reg)
        if cp["ue_registrado"] is False:
            t.aviso("o UE perdeu o registro: os degraus seguintes nao teriam o que "
                    "medir. Parando aqui.")
            break
        time.sleep(args.pausa)
    return registros


def imprime_degrau(reg):
    f = reg.get("fundo") or {}
    fundo = "sem fundo"
    if reg["onde"]:
        fundo = (f"fundo {reg['fundo_pedido_mbps']:.0f} Mbps "
                 f"({'loopback' if reg['onde'] == 'loopback' else 'rede'})")
        if f.get("erro"):
            fundo += f" ERRO: {f['erro'][:60]}"
        elif f.get("recebido_mbps") is not None:
            fundo += f", chegou {f['recebido_mbps']:.0f}"
    cp = reg["plano_controle"]
    pfcp = " ".join(f"{k}={'ok' if v else ('CAIU' if v is False else '?')}"
                    for k, v in cp["pfcp"].items())
    ue = "ok" if cp["ue_registrado"] else ("PERDIDO" if cp["ue_registrado"] is False else "?")
    print(f"       {reg['rotulo']:<14} {fundo}")
    if reg.get("erro"):
        print(f"         {t.VERM}medida falhou:{t.RESET} {reg['erro']}")
    elif reg.get("metricas"):
        m = reg["metricas"]
        estado = "ok" if not reg["instrumento"] else "INSTRUMENTO: " + "; ".join(reg["instrumento"])
        print(f"         net p50={t.num(m['net_p50'], 0)} p99={t.num(m['net_p99'], 0)} us"
              f"  jitter={t.num(m['jitter_net'], 0)} us  perda DL={t.num(m['perda_dl_pct'], 3)}%"
              f"  poses entregues={t.num(m['entrega_ul_pct'], 1)}%  [{estado}]")
    print(f"         PFCP {pfcp}  UE {ue}")


# --------------------------------------------------------------------------
# veredito
# --------------------------------------------------------------------------
def veredito(args, cap, registros):
    validos = {r["rotulo"]: r for r in registros
               if r.get("metricas") and not r.get("instrumento")}
    b0, b1 = validos.get("base"), validos.get("base-final")
    L = [f"capacidade util nuvem -> borda: {cap:.0f} Mbps" if cap else "capacidade: nao medida"]
    if not (b0 and b1):
        return L + ["sem base valida no comeco E no fim: nao da' para julgar efeito"], "INCONCLUSIVO"
    base = {k: (b0["metricas"][k] + b1["metricas"][k]) / 2 for k in ("net_p50", "net_p99")}
    # Cada percentil e' julgado contra a deriva DELE MESMO. A primeira versao
    # tirava o limite do p99 da deriva do p50 (x2), e no piloto do cenario B de
    # 16/09/2026 isso deu 200 us contra um p99 que variou 259 us so' entre as
    # duas bases -- um falso "b-mec afetado" num degrau que estava no ruido.
    deriva = {k: abs(b1["metricas"][k] - b0["metricas"][k]) for k in ("net_p50", "net_p99")}
    limiar = {"net_p50": max(3 * deriva["net_p50"], args.limiar_us),
              "net_p99": max(3 * deriva["net_p99"], 2 * args.limiar_us)}
    perda_base = max(b0["metricas"]["perda_dl_pct"] or 0, b1["metricas"]["perda_dl_pct"] or 0)
    L.append(f"base net p50={base['net_p50']:.0f} us, p99={base['net_p99']:.0f} us; deriva "
             f"entre base e base-final: p50 {deriva['net_p50']:.0f} us, p99 {deriva['net_p99']:.0f} us")
    L.append(f"efeito so' conta acima de {limiar['net_p50']:.0f} us no p50, "
             f"{limiar['net_p99']:.0f} us no p99 (3x a deriva de cada um; pisos "
             f"{args.limiar_us:.0f} e {2 * args.limiar_us:.0f}) ou +0,5 pp de perda")

    def sentiu(r):
        m = r["metricas"]
        return (m["net_p50"] - base["net_p50"] > limiar["net_p50"]
                or m["net_p99"] - base["net_p99"] > limiar["net_p99"]
                or (m["perda_dl_pct"] or 0) - perda_base > 0.5)

    L.append("")
    L.append(f"   {'degrau':<14}{'fundo':>9}{'chegou':>9}{'d p50':>9}{'d p99':>9}"
             f"{'perda DL':>10}  plano de controle")
    for r in registros:
        f = r.get("fundo") or {}
        pedido = f"{r['fundo_pedido_mbps']:.0f}" if r["fundo_pedido_mbps"] else "-"
        chegou = f"{f['recebido_mbps']:.0f}" if f.get("recebido_mbps") else "-"
        cp = r["plano_controle"]
        caiu = [k for k, v in cp["pfcp"].items() if v is False]
        cps = ("UE PERDIDO" if cp["ue_registrado"] is False
               else f"PFCP caiu: {', '.join(caiu)}" if caiu else "ok")
        if r["rotulo"] in validos:
            m = r["metricas"]
            L.append(f"   {r['rotulo']:<14}{pedido:>9}{chegou:>9}"
                     f"{m['net_p50'] - base['net_p50']:>+9.0f}{m['net_p99'] - base['net_p99']:>+9.0f}"
                     f"{m['perda_dl_pct'] or 0:>9.3f}%  {cps}")
        else:
            motivo = r.get("erro") or "; ".join(r.get("instrumento") or []) or "sem medida"
            L.append(f"   {r['rotulo']:<14}{pedido:>9}{chegou:>9}   invalido: {motivo[:50]}  {cps}")

    notas = []
    for r in registros:
        f = r.get("fundo") or {}
        if (r["onde"] == "rede" and f.get("modo") == "gtp" and f.get("recebido_mbps") is not None
                and f["recebido_mbps"] < 0.9 * r["fundo_pedido_mbps"]):
            notas.append(f"{r['rotulo']}: cruzaram {f['recebido_mbps']:.0f} dos "
                         f"{r['fundo_pedido_mbps']:.0f} Mbps pedidos (o gerador enviou "
                         f"{f['enviado_mbps'] or 0:.0f}; perda no caminho "
                         f"{f['perda_caminho_pct'] or 0:.1f}%). Com o enlace cheio, parte do "
                         "fundo cai na fila -- o degrau vale menos que o rotulo")
        elif r["onde"] and f.get("recebido_mbps") and f["recebido_mbps"] < 0.9 * r["fundo_pedido_mbps"]:
            desc = f.get("descartes_receptor")
            notas.append(f"{r['rotulo']}: chegaram {f['recebido_mbps']:.0f} dos "
                         f"{r['fundo_pedido_mbps']:.0f} Mbps pedidos"
                         + (f"; o proprio receptor descartou {desc} datagramas, e essa "
                            "parte cruzou o enlace antes de sumir" if desc else
                            "; o receptor nao descartou nada, entao o que faltou se "
                            "perdeu no caminho ou nem saiu do gerador"))
    controle_cp = all(r["plano_controle"]["ue_registrado"] is not False
                      and all(v is not False for v in r["plano_controle"]["pfcp"].values())
                      for r in registros)
    cpu = validos.get("controle-cpu")
    fundos = [r for r in registros if r["onde"] == "rede" and r["rotulo"] in validos]
    sentidos = [r for r in fundos if sentiu(r)]
    alvo = "a-mec" if args.cenario == "a" else "b-mec"

    L.append("")
    if cpu is None:
        L.append("controle de CPU sem medida valida: nao da' para separar CPU de congestao")
        curto = "INCONCLUSIVO (sem controle de CPU)"
    elif sentiu(cpu):
        L.append(f"GERADOR INTERFERE: o {alvo} piorou com o fundo no LOOPBACK, sem nada na "
                 "rede. O efeito dos outros degraus nao separa CPU de congestao.")
        curto = "GERADOR INTERFERE"
    elif args.cenario == "a":
        if sentidos:
            primeiro = min(sentidos, key=lambda r: r["fracao"])
            L.append(f"FILA COMPARTILHADA: o a-mec piora a partir de {primeiro['fracao'] * 100:g}% "
                     "da capacidade, e o controle de CPU nao mexeu. A campanha sob "
                     "congestao faz sentido com este enlace.")
            curto = "FILA COMPARTILHADA"
        else:
            L.append("FILA NAO COMPARTILHADA: nem no maior degrau o a-mec saiu do ruido. O "
                     "gargalo provavelmente e' so' a porta do receptor -- este desenho nao "
                     "congestiona a medida. Plano B: gargalo emulado com tc.")
            curto = "FILA NAO COMPARTILHADA"
    else:
        if sentidos:
            L.append(f"ATENCAO: o b-mec sentiu o fundo ({', '.join(r['rotulo'] for r in sentidos)}), "
                     "e com LBO ele nao cruza o enlace. Algo do caminho de borda divide "
                     "fila ou CPU com o fundo -- investigar antes da campanha.")
            curto = "B-MEC AFETADO"
        else:
            L.append("B-MEC IMUNE AO FUNDO, como a arquitetura preve.")
            curto = "B-MEC IMUNE"
    if not controle_cp:
        L.append("PLANO DE CONTROLE FALHOU sob fundo (tabela acima). Na campanha, essas "
                 "rodadas cairiam por controle sem prioridade, nao pelo plano de usuario.")
        curto += " / PLANO DE CONTROLE FALHOU"
    if args.ruido == "gtp":
        L.append("")
        L.append("fundo pelo tunel GTP-U (--ruido gtp): o controle de CPU cobre o gerador. O "
                 "trabalho da UPF de ancoragem encapsulando o fundo faz parte do tratamento no "
                 "A -- a UPF central e' a mesma do experimento, como num nucleo compartilhado.")
    if notas:
        L.append("")
        L.extend(["nota: " + n for n in notas])
    return L, curto


# --------------------------------------------------------------------------
def info(msg):
    t.info(msg)


def ok(msg):
    t.ok(msg)


def main():
    global t, R
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    fracoes = lambda s: [float(x) for x in s.split(",") if x.strip()]  # noqa: E731
    ap.add_argument("--cenario", required=True, choices=("a", "b"))
    ap.add_argument("--perfil", default="teleoperacao")
    ap.add_argument("--duracao", type=float, default=30, help="segundos por degrau")
    ap.add_argument("--warmup", type=float, default=5)
    ap.add_argument("--pausa", type=float, default=5, help="segundos entre degraus")
    ap.add_argument("--fracoes", type=fracoes, default=[0.5, 0.8, 0.9, 0.95],
                    help="fundo como fracao da capacidade medida (max 1.0)")
    ap.add_argument("--duracao-capacidade", type=int, default=10)
    ap.add_argument("--limiar-us", type=float, default=100,
                    help="piso do efeito no net_rtt p50 (no p99 o piso e' o dobro); o "
                         "limiar de cada percentil e' o maior entre o piso e 3x a "
                         "deriva DELE entre as duas bases")
    ap.add_argument("--ruido", choices=("gtp", "direto"), default="gtp",
                    help="gtp (padrao): fundo pelo tunel GTP-U ate' o UERANSIM de ruido no "
                         "brix-porvir-03 (congestao/ruido-gtp.yaml); direto: iperf3 ate' o "
                         "brix-porvir-04 sem passar por UPF, o piloto de 16/09/2026")
    ap.add_argument("--manter-iperf", action="store_true",
                    help="nao remove os pods do iperf (ou do ruido) no fim")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--carregar-assinantes", type=int, default=0, metavar="N")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--porta-mongo", type=int, default=27017)
    ap.add_argument("--namespace", default="free5gc")
    ap.add_argument("--saida", default=None)
    ap.add_argument("--conciso", action="store_true")
    args = ap.parse_args()

    if not args.fracoes or max(args.fracoes) > 1.0 or min(args.fracoes) <= 0:
        ap.error("--fracoes precisa estar em (0, 1]: nada acima da capacidade")
    t = carrega_teste(args.cenario)
    if args.ruido == "gtp":
        R = carrega_ruido()
    if args.perfil not in t.PERFIS:
        ap.error(f"perfil desconhecido: {args.perfil} (opcoes: {', '.join(sorted(t.PERFIS))})")
    t.NS, t.CONCISO, t.PAUSAR = args.namespace, args.conciso, False
    carimbo = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    args.saida = args.saida or os.path.join(
        t.BASE, "congestao", "resultados", f"{carimbo}-cenario-{args.cenario}-{args.perfil}"
        + ("-gtp" if args.ruido == "gtp" else ""))
    # Namespace com os campos que os passos 01-10 do teste do cenario leem.
    targs = argparse.Namespace(
        tentativas=1, repeticoes=1, deploy=args.deploy, incluir_descartadas=False,
        sem_derrubar=True, timeout_derrubada=300,
        carregar_assinantes=args.carregar_assinantes, duracao=args.duracao,
        warmup=args.warmup, prova_duracao=10, so_prova=False, perfil=args.perfil,
        listar_perfis=False, saida=args.saida, timeout=args.timeout,
        porta_mongo=args.porta_mongo, namespace=args.namespace,
        pular_validate=False, passo_a_passo=False, conciso=args.conciso)

    t0 = time.time()
    placement, cap, registros, prova = {}, None, [], None
    rc, interrompido, erro, aplicou = 0, False, None, False
    try:
        t.p01_ferramentas()
        t.p02_validate(targs)
        t.p03_deploy(targs)
        t.p04_pods(targs)
        placement = t.p05_placement()
        t.p06_assinantes(targs)
        t.p07_pfcp(targs)
        t.p08_tester(targs)
        ue_ip = t.p09_sessao(targs)
        t.p10_rotas()
        aplicou = True
        if args.ruido == "gtp":
            est, prova = p1_ruido(args)
            cap = p2_capacidade_gtp(args, est)
            registros = p3_degraus(args, ue_ip, est, cap)
        else:
            ip_srv = p1_iperf(args, placement)
            cap = p2_capacidade(args, ip_srv)
            registros = p3_degraus(args, ue_ip, ip_srv, cap)
    except t.Falha as e:
        erro = str(e)
        print(f"\n{t.VERM}FALHOU:{t.RESET} {erro}", file=sys.stderr)
        rc = 1
    except KeyboardInterrupt:
        interrompido, rc = True, 130
        print("\ninterrompido", file=sys.stderr)
    finally:
        # Fundo esquecido ligado congestionaria a proxima campanha sem ninguem
        # saber -- e a rede dos outros.
        try:
            if _fundo is not None and _fundo.poll() is None:
                _fundo.kill()
            if aplicou:
                mata_fundo()
                if not args.manter_iperf:
                    if R is not None:
                        R.desce()
                    else:
                        t.kubectl("delete", "-f", MANIFESTO, "--wait=false",
                                  check=False, quiet=True, timeout=60)
        except Exception as exc:                          # noqa: BLE001
            print(f"  {t.AMAR}limpeza falhou: {exc}{t.RESET}", file=sys.stderr)

    linhas, curto = (veredito(args, cap, registros) if registros
                     else ([], "SEM DEGRAUS"))
    if linhas:
        print(f"\n{'#' * 72}\nPILOTO DE CONGESTAO -- cenario {args.cenario.upper()}, "
              f"perfil {args.perfil}, {args.duracao:g}s por degrau, fundo "
              + ("pelo tunel GTP-U" if args.ruido == "gtp" else "direto"))
        print(f"placement: {json.dumps(placement)}")
        for linha in linhas:
            print(linha)
        print("#" * 72)
    if registros or erro:
        os.makedirs(args.saida, exist_ok=True)
        with open(os.path.join(args.saida, "piloto.json"), "w") as fh:
            json.dump({"args": vars(args), "placement": placement, "capacidade_mbps": cap,
                       "ruido": args.ruido, "prova_caminho_ruido": prova,
                       "registros": registros, "veredito": curto, "avisos": t.avisos,
                       "erro": erro, "segundos": round(time.time() - t0, 1)}, fh, indent=2)
        with open(os.path.join(args.saida, "relatorio.txt"), "w") as fh:
            fh.write("\n".join(linhas) + "\n")
        info(f"resultados em {args.saida}")

    tempo = f"{time.time() - t0:.0f}s"
    if interrompido:
        print(f"\n{t.AMAR}PILOTO INTERROMPIDO{t.RESET} -- {len(registros)} degrau(s) em {tempo}")
    elif erro or not registros:
        print(f"\n{t.VERM}PILOTO NAO CONCLUIDO{t.RESET} -- {len(registros)} degrau(s) em {tempo}")
        rc = rc or 1
    elif curto.startswith(("INCONCLUSIVO", "GERADOR", "FILA NAO", "B-MEC AFETADO")) \
            or "FALHOU" in curto:
        print(f"\n{t.AMAR}PILOTO CONCLUIDO: {curto}{t.RESET} ({tempo})")
        rc = 3
    else:
        print(f"\n{t.VERDE}PILOTO CONCLUIDO: {curto}{t.RESET} ({tempo})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
