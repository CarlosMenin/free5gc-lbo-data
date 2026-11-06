#!/usr/bin/env python3
"""
Calibracao do instrumento de medida do TG2.

PARA QUE SERVE
    E' a garantia de que os numeros da campanha sao da REDE e nao da
    ferramenta. A pergunta de fundo e' a do orientador: tirando a rede do
    caminho, o que sobra? Sobra o PISO do instrumento -- Python, kernel,
    escalonador, carimbo de tempo. Diferenca entre caminhos menor que o ruido
    desse piso nao pode ser atribuida a rede, e o texto do TG precisa saber
    onde fica essa linha.

A ESCADA DE CONTROLE (cada degrau repoe uma camada)

    C0  SEM REDE      cliente e servidor no MESMO pod, por 127.0.0.1. Nada de
                      fio, de Kubernetes ou de 5G: e' o piso. Medido nas tres
                      maquinas por onde a medida passa:
                        C0-tester  UE/RAN     instancia de calibracao no tester
                        C0-borda   Edge Node  o vr-server real do mec-app
                        C0-nucleo  remoto     o vr-server real do remote-app
    C1  REDE, SEM 5G  do pod do tester direto ao IP do POD do servidor, pela
                      eth0: Calico, switch e roteador, nenhum UPF.
                        C1-borda -> mec-app        C1-nucleo -> remote-app
    C2  5G COMPLETO   o caminho exato da campanha: IP do UE, uesimtun0, gNB,
                      GTP-U, UPF(s), ClusterIP.
                        C2-borda -> mec-app        C2-nucleo -> remote-app

    C1 - C0 = custo da rede do cluster     C2 - C1 = custo do plano de usuario 5G

    Cada corrida PROVA o caminho que tomou: os contadores da uesimtun0 e da
    upfgtp dos dois UPFs tem que ficar parados em C0/C1 e andar em C2 -- e, em
    C2, o PSA-UPF parado na borda e andando no nucleo.

VALIDACOES DE EXATIDAO (entrada conhecida -> saida esperada)

    Piso baixo nao prova que o instrumento mede CERTO. Por isso:

    V1  sleep injetado no servidor: o net_rtt NAO pode se mexer. Prova que
        tempo de servidor nao vaza para "rede". O hold sai no relatorio, mas
        so' como informacao -- ele carrega a janela de pacing e a fase entre
        pose e frame, que nao tem nada a ver com a subtracao que se verifica.
    V2  atraso injetado com tc netem no loopback do tester, so' na porta de
        calibracao: o net_rtt tem que subir exatamente 2x o atraso (ida e
        volta). Prova que o instrumento mede atraso de rede sem distorcer.
    V3  testemunha independente: ping (ICMP, fora do nosso codigo) nos
        caminhos do C1. O net_rtt nao pode ser menor que o ping, e a diferenca
        tem que ser da ordem do piso C0.

REPETICAO
    Cada degrau roda --repeticoes vezes com a ORDEM rotativa, para nenhuma
    deriva cair sempre no mesmo degrau. O desvio entre repeticoes e' o ruido
    contra o qual a diferenca entre caminhos e' comparada no relatorio.

Pre-requisito: cenario B no ar (--deploy, ou 'python3 deploy.py up b'). O
script NAO derruba o cenario e devolve o loopback do tester como encontrou.

    python3 scripts/calibra-instrumento.py --perfil teleoperacao --carregar-assinantes 5
    python3 scripts/calibra-instrumento.py --perfil vr-cloud --repeticoes 5 --duracao 60
"""
import argparse
import datetime
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import textwrap
import time

# Reaproveita o teste do cenario B inteiro -- deploy, placement, sessao PDU,
# rotas, contadores de caminho. A calibracao so' vale se roda no MESMO ambiente
# que a campanha, e o jeito de garantir isso e' chamar as MESMAS funcoes.
AQUI = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "teste_cenario_b", os.path.join(AQUI, "test-cenario-b.py"))
tcb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tcb)

Falha = tcb.Falha
ok, info, aviso, num = tcb.ok, tcb.info, tcb.aviso, tcb.num

PORTA_CAL = 9200            # instancia de calibracao, dentro do pod do tester
METRICAS_CAL = 9201
METRICAS_SRV = 9101         # vr-server real (mec-app e remote-app)

CLI = ("pod", tcb.TESTER_POD, "vr-client")
MEC = ("deploy", "free5gc-mec-app", "vr-server")
REM = ("deploy", "free5gc-remote-app", "vr-server")

# Tolerancias das validacoes de exatidao.
TOL_INCLINACAO = 0.10   # V2 (net_rtt x atraso injetado): inclinacao 1 +- 10%
TOL_VAZAMENTO = 0.05    # V1: o net_rtt nao pode responder ao sono do servidor
                        # -- nem em tendencia (inclinacao) nem em excursao
                        # total, ambas contra o maior sono injetado
R2_MIN = 0.98           # V2: a resposta ao atraso tem que ser linear
LIMIAR_CAMINHO_PCT = 1.0  # C0/C1: tunel e UPFs podem ver no maximo 1% das poses

# qdisc da V2. Handle proprio para nunca confundir com um qdisc que nao e' nosso.
HANDLE_TC = "7a"
_netem_container = None     # != None enquanto houver netem nosso no loopback


# --------------------------------------------------------------------------
# utilitarios
# --------------------------------------------------------------------------
def etapa(rotulo, titulo, porque=""):
    """Mesmo visual do passo() do teste, mas com rotulo livre (C, V1...)."""
    print(f"\n{'=' * 72}\n[{rotulo}] {titulo}\n{'=' * 72}")
    if porque and not tcb.CONCISO:
        for par in porque.strip().split("\n\n"):
            for linha in textwrap.wrap(" ".join(par.split()), 68):
                print(f"  {tcb.CINZA}# {linha}{tcb.RESET}")
            print()


def exec_em(onde, *cmd, timeout=60):
    tipo, nome, container = onde
    alvo = nome if tipo == "pod" else f"deploy/{nome}"
    return tcb.kubectl("exec", alvo, "-c", container, "--", *cmd,
                       check=False, quiet=True, timeout=timeout)


def metricas(onde, porta):
    """/metrics de um vr-server lido de DENTRO do pod, numa chamada so'."""
    r = exec_em(onde, "python3", "-c",
                "import urllib.request as u;"
                f"print(u.urlopen('http://127.0.0.1:{porta}/metrics',timeout=5)"
                ".read().decode())", timeout=40)
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


CONTADORES_SRV = ("frames_sent_total", "frame_packets_total", "frames_late_total",
                  "send_dropped_total", "pose_packets_total",
                  "sessions_expired_total")


def delta_srv(m0, m1):
    if m0 is None or m1 is None:
        return None
    return {k: m1.get(f"vr_server_{k}", 0.0) - m0.get(f"vr_server_{k}", 0.0)
            for k in CONTADORES_SRV}


def pod_ativo(epc_mode):
    """(nome, ip) do pod Running e que NAO esta sendo apagado -- depois de uma
    troca de perfil o pod antigo ainda aparece por alguns segundos."""
    r = tcb.kubectl("get", "pod", "-l", f"epc-mode={epc_mode}", "-o",
                    "jsonpath={range .items[*]}{.metadata.name}{'|'}"
                    "{.metadata.deletionTimestamp}{'|'}{.status.phase}{'|'}"
                    "{.status.podIP}{'\\n'}{end}", quiet=True)
    for linha in r.stdout.splitlines():
        nome, apagando, fase, ip = (linha.split("|") + ["", "", "", ""])[:4]
        if nome and not apagando and fase == "Running" and ip:
            return nome, ip
    raise Falha(f"nenhum pod Running com epc-mode={epc_mode}")


# --------------------------------------------------------------------------
# instancia de calibracao do vr-server (loopback do tester)
# --------------------------------------------------------------------------
_PROCURA_CAL = """
import os, signal, sys
achados = []
for p in os.listdir('/proc'):
    if not p.isdigit():
        continue
    try:
        c = open('/proc/%s/cmdline' % p, 'rb').read()
    except OSError:
        continue
    if b'vr_server.py' in c and b'--port\\x00PORTA' in c:
        achados.append(p)
        if 'matar' in sys.argv[1:]:
            os.kill(int(p), signal.SIGTERM)
print(' '.join(achados))
""".replace("PORTA", str(PORTA_CAL))


def para_servidor_cal():
    # A imagem python:3.12-slim nao tem pkill/ps: a busca e' pelo /proc.
    return exec_em(CLI, "python3", "-c", _PROCURA_CAL, "matar",
                   timeout=30).stdout.split()


def sobe_servidor_cal(perfil, render_ms=0.0, render_sleep=False):
    """Sobe um vr-server em 127.0.0.1 com o MESMO perfil da campanha e devolve
    o log de subida (de onde sai a folga do pacing usada pela V1).

    render_sleep vai por VARIAVEL DE AMBIENTE, e nao por flag, de proposito: um
    ConfigMap vr-app antigo ignora a variavel e sobe normalmente, enquanto uma
    flag desconhecida derrubaria o servidor com erro de argparse. Quem confere
    se a variavel foi obedecida e' a V1, lendo o banner do log."""
    para_servidor_cal()
    p = tcb.PERFIS[perfil]
    linha = (f"VR_RENDER_SLEEP={1 if render_sleep else 0} "
             f"nohup python3 -u /opt/vr/vr_server.py --bind 127.0.0.1 "
             f"--port {PORTA_CAL} --metrics-port {METRICAS_CAL} "
             f"--bitrate-mbps {p['bitrate_mbps']} --fps {p['fps']} "
             f"--mtu {p['mtu']} --render-ms {render_ms} "
             f"--role calibracao --profile {perfil} "
             "</dev/null >/tmp/cal-server.log 2>&1 &")
    r = exec_em(CLI, "sh", "-c", linha, timeout=30)
    if r.returncode != 0:
        raise Falha(f"nao consegui subir o servidor de calibracao: "
                    f"{r.stderr.strip()[:300]}")
    tcb.espera("servidor de calibracao respondendo",
               lambda: (metricas(CLI, METRICAS_CAL) is not None, "subindo"),
               30, intervalo=1)
    return exec_em(CLI, "cat", "/tmp/cal-server.log", timeout=20).stdout


def folga_ms(log, fps):
    """Quanto do periodo sobra DEPOIS do pacing. O render injetado da V1 tem
    que caber nisso, senao o gerador atrasa e a V1 mede o gerador."""
    periodo = 1000.0 / fps
    m = re.search(r"pacing: (\d+) rajadas de \d+ pkt a cada ([\d.]+) ms", log)
    if m:
        return max(0.0, periodo - (int(m.group(1)) - 1) * float(m.group(2)))
    return periodo if "DESLIGADO" in log else periodo * 0.2


# --------------------------------------------------------------------------
# uma medida
# --------------------------------------------------------------------------
def cliente(onde, servidor, bind, rotulo, args, csv=None):
    cmd = ["python3", "/opt/vr/vr_client.py", "--server", servidor,
           "--bind", bind, "--duration", str(args.duracao),
           "--warmup", str(args.warmup),
           "--pose-hz", str(tcb.PERFIS[args.perfil]["pose_hz"]),
           "--label", rotulo]
    if csv:
        cmd += ["--csv", csv]
    r = exec_em(onde, *cmd, timeout=args.duracao + 90)
    try:
        b = r.stdout
        return json.loads(b[b.index("{"):b.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        raise Falha(f"vr_client nao devolveu JSON (rc={r.returncode}): "
                    f"{r.stderr.strip()[-300:]}")


def foto_caminho():
    f = {"ue-tun": tcb.contadores_tun()}
    for papel, (deploy, _) in tcb.UPFS.items():
        try:
            f[papel] = tcb.contadores_gtp(deploy)
        except Falha:
            f[papel] = None
    return f


def delta_caminho(a, b):
    return {k: (tcb.delta(a[k], b[k]) if a.get(k) and b.get(k) else None)
            for k in a}


def confere_caminho(esperado, d, res):
    """O degrau so' vale se o trafego tomou o caminho que o degrau declara."""
    poses = res.get("ul_packets_tx") or 0
    if not poses:
        return ["o cliente nao enviou nenhuma pose"]

    def cont(k, campo):
        return None if not d.get(k) else d[k][campo]

    probs = []
    tun = cont("ue-tun", "tx_pkts")
    iupf, psa = cont("i-upf", "rx_pkts"), cont("psa-upf", "rx_pkts")
    if esperado == "sem-5g":
        for rotulo, v in (("uesimtun0", tun), ("I-UPF", iupf), ("PSA-UPF", psa)):
            if v is not None and v > poses * LIMIAR_CAMINHO_PCT / 100:
                probs.append(f"{rotulo} contou {v} pacotes ({v / poses * 100:.1f}% "
                             "das poses): este degrau devia estar FORA do 5G")
        return probs
    if tun is not None and tun < 0.95 * poses:
        probs.append(f"uesimtun0 viu {tun} de {poses} poses: parte do trafego "
                     "nao entrou no tunel")
    if esperado == "borda":
        if iupf is not None and iupf < 0.9 * poses:
            probs.append(f"I-UPF desencapsulou {iupf} de {poses} poses: o breakout "
                         "local nao aconteceu")
        if psa is not None and psa > 0.02 * poses:
            probs.append(f"PSA-UPF viu {psa} pacotes: trafego de borda subiu ao nucleo")
    elif psa is not None and psa < 0.9 * poses:
        probs.append(f"PSA-UPF viu {psa} de {poses} poses: o trafego remoto nao "
                     "chegou a' ancora central")
    return probs


def saude(res, srv, fps_alvo):
    """As mesmas guardas da campanha: a corrida mediu a rede, nao o testbed?"""
    probs = []
    if not res.get("frames_complete"):
        probs.append("nenhum frame completo voltou")
    sa = res.get("saude") or {}
    if sa.get("rx_timestamp_kernel") is False:
        probs.append("sem carimbo de tempo do kernel: nao e' o instrumento calibrado")
    janela = res.get("ul_window_s") or res.get("duration_s")
    if srv is None:
        probs.append("nao consegui ler o /metrics do servidor")
    else:
        if janela and fps_alvo:
            fps = srv["frames_sent_total"] / janela
            if fps < 0.9 * fps_alvo:
                probs.append(f"servidor emitiu {fps:.0f} de {fps_alvo:.0f} fps")
        if srv["send_dropped_total"]:
            probs.append(f"servidor descartou {srv['send_dropped_total']:.0f} "
                         "pacotes no envio (sndbuf cheio)")
        if srv["sessions_expired_total"]:
            probs.append("a sessao expirou no servidor (o uplink parou)")
    cont = res.get("dl_continuity_pct")
    if cont is not None and cont < tcb.LIMIAR_CONTINUIDADE_PCT:
        probs.append(f"downlink so' existiu em {cont:.0f}% da janela")
    rec = res.get("dl_packets_rx_run") or 0
    drops = sa.get("dl_sock_drops")
    if drops is None:
        drops = sa.get("dl_sock_overflow_pkts")
    for onde, n in (("fila do socket do cliente", drops),
                    ("buffer UDP do netns do cliente", sa.get("udp_rcvbuf_errors"))):
        if n and rec and n / rec * 100 > tcb.LIMIAR_DESCARTE_LOCAL_PCT:
            probs.append(f"{n} descartes na {onde} ({n / rec * 100:.2f}% do downlink)")
    if abs(sa.get("clock_drift_us") or 0) > 1000:
        probs.append(f"o CLOCK_REALTIME andou {sa['clock_drift_us']:.0f} us "
                     "(passo de NTP no meio da corrida)")
    return probs


def extrai(reg):
    r, srv = reg["resumo"], reg["servidor"]
    perda = r.get("dl_packet_loss_pct")
    if srv and srv.get("frame_packets_total"):
        perda = max(0.0, 1 - (r.get("dl_packets_rx_run") or 0)
                    / srv["frame_packets_total"]) * 100
    return {"net_min": r["net_rtt_us"]["min"],
            "net_p50": r["net_rtt_us"]["p50"], "net_p95": r["net_rtt_us"]["p95"],
            "net_p99": r["net_rtt_us"]["p99"], "jitter_net": r.get("jitter_net_us"),
            "m2p_p50": r["m2p_us"]["p50"], "hold_p50": r["hold_us"]["p50"],
            "perda_pct": perda, "mbps": r.get("dl_throughput_mbps")}


def medir(nome, esperado, cli, servidor, bind, srv, porta_srv, fps_alvo,
          args, rotulo, csv, antes=None, depois=None):
    """antes/depois: chamados COLADOS ao cliente, sem as leituras de contador
    no meio -- a V3 usa isso para marcar a janela no relogio do proprio no."""
    m0, c0 = metricas(srv, porta_srv), foto_caminho()
    marca_ini = antes() if antes else None
    t_ini = time.time()
    res = cliente(cli, servidor, bind, rotulo, args, csv)
    t_fim = time.time()
    marca_fim = depois() if depois else None
    m1, c1 = metricas(srv, porta_srv), foto_caminho()
    dsrv, dcam = delta_srv(m0, m1), delta_caminho(c0, c1)
    probs = saude(res, dsrv, fps_alvo) + confere_caminho(esperado, dcam, res)
    reg = {"degrau": nome, "rotulo": rotulo, "esperado": esperado,
           "servidor_alvo": servidor, "bind": bind, "fps_alvo": fps_alvo,
           # janela de relogio da corrida: e' o que permite cruzar esta medida
           # com Prometheus, Loki ou Grafana depois.
           "inicio_epoch": round(t_ini, 3), "fim_epoch": round(t_fim, 3),
           "marcas_no": [marca_ini, marca_fim],
           "resumo": res, "servidor": dsrv, "caminho": dcam,
           "problemas": probs, "valida": not probs}
    reg["metricas"] = e = extrai(reg)
    estado = (f"{tcb.VERDE}ok{tcb.RESET}" if not probs
              else f"{tcb.VERM}INVALIDA{tcb.RESET}")
    print(f"       {rotulo:<22} net p50={num(e['net_p50'])} p99={num(e['net_p99'])} us"
          f"  jitter={num(e['jitter_net'])} us  perda={num(e['perda_pct'], 3)}%"
          f"  {num(e['mbps'], 2)} Mbps  [{estado}]")
    for p in probs:
        print(f"         {tcb.AMAR}- {p}{tcb.RESET}")
    return reg


def csv_remoto(onde, rotulo):
    return (f"/data/calibracao/{rotulo}.csv" if onde[0] == "pod"
            else f"/tmp/{rotulo}.csv")


def copia_csv(onde, remoto, saida, rotulo):
    tipo, nome, container = onde
    try:
        pod = nome if tipo == "pod" else pod_ativo(nome.replace("free5gc-", ""))[0]
    except Falha:
        return
    destino = os.path.join(saida, "csv", f"{rotulo}.csv")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    # Destino relativo, de dentro da pasta: no Windows o kubectl le "C:\..."
    # como <pod>:<caminho> e recusa a copia.
    r = tcb.run(["kubectl", "-n", tcb.NS, "cp", f"{pod}:{remoto}", os.path.basename(destino),
                 "-c", container], check=False, quiet=True, timeout=120,
                cwd=os.path.dirname(destino))
    if r.returncode != 0:
        info(f"csv de {rotulo} nao copiado: {r.stderr.strip()[:120]}")


def mede_ou_registra(nome, *a, **kw):
    try:
        return medir(nome, *a, **kw)
    except Falha as e:
        motivo = str(e).splitlines()[0]
        print(f"       {kw['rotulo']:<22} {tcb.VERM}FALHOU{tcb.RESET}: {motivo}")
        return {"degrau": nome, "rotulo": kw["rotulo"], "valida": False,
                "problemas": [motivo], "erro": str(e)}


# --------------------------------------------------------------------------
# escada de controle
# --------------------------------------------------------------------------
def escada(args, ctx, registros):
    fps_mec, fps_rem = tcb.fps_alvo("free5gc-mec-app"), tcb.fps_alvo("free5gc-remote-app")
    fps_cal = tcb.PERFIS[args.perfil]["fps"]
    loop_cal, loop_srv = f"127.0.0.1:{PORTA_CAL}", f"127.0.0.1:{tcb.VR_PORT}"
    degraus = [
        ("C0-tester", "sem-5g", CLI, loop_cal, "127.0.0.1", CLI, METRICAS_CAL, fps_cal),
        ("C0-borda", "sem-5g", MEC, loop_srv, "127.0.0.1", MEC, METRICAS_SRV, fps_mec),
        ("C0-nucleo", "sem-5g", REM, loop_srv, "127.0.0.1", REM, METRICAS_SRV, fps_rem),
        ("C1-borda", "sem-5g", CLI, f"{ctx['ip_mec']}:{tcb.VR_PORT}",
         ctx["ip_tester"], MEC, METRICAS_SRV, fps_mec),
        ("C1-nucleo", "sem-5g", CLI, f"{ctx['ip_rem']}:{tcb.VR_PORT}",
         ctx["ip_tester"], REM, METRICAS_SRV, fps_rem),
    ]
    if ctx["ue_ip"]:
        degraus += [
            ("C2-borda", "borda", CLI, f"{ctx['mec_cluster_ip']}:{tcb.VR_PORT}",
             ctx["ue_ip"], MEC, METRICAS_SRV, fps_mec),
            ("C2-nucleo", "nucleo", CLI, f"{ctx['remote_cluster_ip']}:{tcb.VR_PORT}",
             ctx["ue_ip"], REM, METRICAS_SRV, fps_rem),
        ]
    etapa("C", f"Escada de controle: {len(degraus)} degraus x {args.repeticoes} "
               f"repeticoes, {args.duracao:g}s cada",
          """C0 tira a rede inteira (loopback no proprio pod), C1 repoe a rede do
    cluster sem nenhum UPF, C2 e' o caminho 5G da campanha. A diferenca entre
    degraus vizinhos da' dono a cada parcela do atraso.

    A ordem ROTACIONA a cada repeticao, e cada corrida confere pelos contadores
    da uesimtun0 e dos UPFs que o trafego tomou o caminho que o degrau declara.
    Corrida que falha numa guarda fica registrada como invalida -- em
    calibracao, uma falha tambem e' resultado.""")
    for rep in range(args.repeticoes):
        k = rep % len(degraus)
        ordem = degraus[k:] + degraus[:k]
        info(f"repeticao {rep + 1}/{args.repeticoes}: "
             + " -> ".join(d[0] for d in ordem))
        for nome, esperado, cli, alvo, bind, srv, porta, fps in ordem:
            rotulo = f"{nome}-r{rep + 1}"
            csv = csv_remoto(cli, rotulo)
            if nome == "C0-tester":
                sobe_servidor_cal(args.perfil, 0)
            try:
                reg = mede_ou_registra(nome, esperado, cli, alvo, bind, srv, porta,
                                       fps, args, rotulo=rotulo, csv=csv)
            finally:
                if nome == "C0-tester":
                    para_servidor_cal()
            reg["repeticao"] = rep + 1
            registros.append(reg)
            copia_csv(cli, csv, args.saida, rotulo)
            time.sleep(args.pausa)


def agrega(valores):
    v = [x for x in valores if x is not None]
    if not v:
        return None
    return {"n": len(v), "mediana": statistics.median(v), "min": min(v),
            "max": max(v), "desvio": statistics.stdev(v) if len(v) > 1 else None}


ORDEM_DEGRAUS = ["C0-tester", "C0-borda", "C0-nucleo", "C1-borda", "C1-nucleo",
                 "C2-borda", "C2-nucleo"]
CHAVES = ("net_min", "net_p50", "net_p95", "net_p99", "jitter_net", "m2p_p50", "hold_p50",
          "perda_pct", "mbps")


def agrega_degraus(registros):
    ag = {}
    for nome in ORDEM_DEGRAUS:
        regs = [r for r in registros if r["degrau"] == nome]
        if not regs:
            continue
        val = [r for r in regs if r["valida"]]
        ag[nome] = {"corridas": len(regs), "validas": len(val)}
        for c in CHAVES:
            ag[nome][c] = agrega([r["metricas"][c] for r in val])
    return ag


# Quantis da t de Student: bicaudal 95% (alfa 5%) e unicaudal 80% (poder 80%).
# Com 3 repeticoes por lado a aproximacao normal (1,96 + 0,84 = 2,8) subestima
# a menor diferenca detectavel em ate' 2x; a tabela corrige isso sem scipy.
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}
_T80 = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896,
        8: 0.889, 9: 0.883, 10: 0.879, 12: 0.873, 15: 0.866, 20: 0.860, 30: 0.854}


def _quantil_t(tabela, gl, normal):
    if gl is None or gl > 30:
        return normal
    # gl arredondado para BAIXO: o lado conservador
    return tabela[max(k for k in tabela if k <= max(1, int(gl)))]


def menor_diferenca_detectavel(s1, n1, s2, n2):
    """MDE de duas amostras independentes com variancias diferentes (Welch).
    Devolve (mde, graus_de_liberdade)."""
    a, b = s1 ** 2 / n1, s2 ** 2 / n2
    den = (a ** 2 / (n1 - 1) if n1 > 1 else 0) + (b ** 2 / (n2 - 1) if n2 > 1 else 0)
    gl = (a + b) ** 2 / den if den else None
    fator = _quantil_t(_T975, gl, 1.960) + _quantil_t(_T80, gl, 0.842)
    return fator * math.sqrt(a + b), gl


def regressao(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - a * mx
    sst = sum((y - my) ** 2 for y in ys)
    ssr = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    return {"inclinacao": a, "intercepto": b, "r2": 1 - ssr / sst if sst else 1.0}


# --------------------------------------------------------------------------
# V1 -- render injetado
# --------------------------------------------------------------------------
def v1_render(args, registros):
    etapa("V1", "Exatidao: tempo de SERVIDOR nao pode vazar para 'rede'",
          """Faz o servidor DORMIR um tempo conhecido antes de mandar o frame
    (VR_RENDER_SLEEP=1) e verifica UMA coisa: o net_rtt nao pode se mexer. O
    cliente calcula net_rtt = m2p - hold; se o sono do servidor aparecer no
    net_rtt, a subtracao esta errada e tempo de processamento esta sendo
    contado como rede -- o erro que invalidaria a campanha inteira. Com a V2
    (atraso de rede tem que APARECER no net_rtt), fecha o par: o instrumento
    responde ao que e' rede e ignora o que nao e'.

    O hold e' impresso, mas NAO entra no criterio. Ele e' dominado pela janela
    de pacing e pela fase entre a cadencia de pose e a de frame, que mudam de
    corrida para corrida em ~1 ms -- ruido maior que os poucos milissegundos
    injetaveis. Exigir dele uma inclinacao 1,00 reprovou duas calibracoes boas
    em 12/09/2026 (1,32 no ar-industrial, com o render queimando CPU, e 0,68 no
    vr-360, ja' com sleep e R2 de 0,79) sem que houvesse nada errado com a
    medida: nas duas o net_rtt ficou parado.

    Os valores de sono saem da folga que o pacing deixa no periodo: acima dela
    o gerador atrasa, e a validacao passaria a medir o gerador.""")
    fps = tcb.PERFIS[args.perfil]["fps"]
    log = sobe_servidor_cal(args.perfil, 0, render_sleep=True)
    if "[sleep]" not in log:
        aviso("o vr-server ignorou VR_RENDER_SLEEP: o ConfigMap vr-app do "
              "cluster e' anterior a esta versao. Aplique "
              "'kubectl apply -f mec/vr-app.yaml' e espere o kubelet "
              "sincronizar (~1 min). A V1 vai rodar com queima de CPU: o "
              "net_rtt continua valendo, o hold impresso nao.",
              escopo="calibracao")
    folga = folga_ms(log, fps)
    renders = args.render_ms or [0.0] + [round(folga * f, 2) for f in (0.2, 0.4, 0.6)]
    info(f"folga do periodo apos o pacing: {folga:.2f} ms -> renders {renders} ms")
    pontos = []
    try:
        for R in renders:
            sobe_servidor_cal(args.perfil, R, render_sleep=True)
            rotulo = f"V1-render-{R:g}ms"
            csv = csv_remoto(CLI, rotulo)
            reg = mede_ou_registra("V1", "sem-5g", CLI, f"127.0.0.1:{PORTA_CAL}",
                                   "127.0.0.1", CLI, METRICAS_CAL, fps, args,
                                   rotulo=rotulo, csv=csv)
            reg["render_ms"] = R
            registros.append(reg)
            pontos.append(reg)
            copia_csv(CLI, csv, args.saida, rotulo)
            time.sleep(args.pausa)
    finally:
        para_servidor_cal()
    val = [p for p in pontos if p["valida"]]
    if len(val) < 3:
        aviso("V1 com menos de 3 pontos validos: nao da' para ajustar a reta",
              escopo="calibracao")
        return {"executada": True, "aprovada": False, "motivo": "pontos insuficientes"}
    xs = [p["render_ms"] * 1000 for p in val]
    nets = [p["metricas"]["net_p50"] for p in val]
    rh = regressao(xs, [p["metricas"]["hold_p50"] for p in val])
    rn = regressao(xs, nets)
    # Duas leituras do MESMO criterio ("o net_rtt nao se mexe"), porque com
    # poucos pontos a reta sozinha e' fragil: a inclinacao diz se ha' tendencia
    # e a excursao diz se a variacao total cabe no ruido. Ambas sao comparadas
    # com o MAIOR sono injetado -- e' contra ele que "nao mexer" significa algo.
    injetado = max(xs) if xs else 0.0
    excursao = max(nets) - min(nets) if nets else 0.0
    pct = (excursao / injetado * 100) if injetado else None
    aprovada = (rn is not None and abs(rn["inclinacao"]) <= TOL_VAZAMENTO
                and (pct is None or pct <= TOL_VAZAMENTO * 100))
    print(f"\n       net_rtt p50 = {rn['inclinacao']:+.3f} x sono + {rn['intercepto']:.0f} us"
          f"   (esperado 0,000)   [CRITERIO]")
    if pct is not None:
        print(f"       excursao do net_rtt p50: {excursao:.0f} us para "
              f"{injetado:.0f} us de sono injetado ({pct:.1f}%; limite "
              f"{TOL_VAZAMENTO * 100:.0f}%)   [CRITERIO]")
    print(f"       hold p50    = {rh['inclinacao']:.3f} x sono + {rh['intercepto']:.0f} us"
          f"   (R2={rh['r2']:.3f})   [informativo: carrega pacing e fase da pose]")
    (ok if aprovada else aviso)(
        "V1 APROVADA: o sono do servidor nao apareceu no net_rtt" if aprovada
        else "V1 REPROVADA: o sono do servidor vazou para o net_rtt")
    return {"executada": True, "aprovada": bool(aprovada), "renders_ms": renders,
            "hold": rh, "net_rtt": rn, "excursao_net_us": excursao,
            "sono_max_us": injetado, "excursao_pct": pct}


# --------------------------------------------------------------------------
# V2 -- atraso de rede injetado com netem
# --------------------------------------------------------------------------
def container_com(ferramenta):
    for c in ("ue", "gnb"):
        r = tcb.kexec(tcb.TESTER_POD, c, "sh", "-c", f"command -v {ferramenta}",
                      check=False, quiet=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return c
    return None


def tc(container, *a, timeout=20):
    return tcb.kexec(tcb.TESTER_POD, container, "tc", *a, check=False,
                     quiet=True, timeout=timeout)


def remove_netem(container):
    global _netem_container
    tc(container, "qdisc", "del", "dev", "lo", "root")
    _netem_container = None


def aplica_netem(container, atraso_ms):
    """prio no loopback com tudo na banda 1 (sem atraso) e um filtro u32 que
    manda SO' a porta de calibracao para a banda 3, onde esta o netem. O
    radio-link simulado entre nr-gnb e nr-ue tambem passa pelo loopback deste
    pod, e nao pode levar atraso nenhum."""
    global _netem_container
    remove_netem(container)
    h = HANDLE_TC
    passos = [
        ["qdisc", "add", "dev", "lo", "root", "handle", f"{h}:", "prio",
         "bands", "3", "priomap"] + ["0"] * 16,
        ["qdisc", "add", "dev", "lo", "parent", f"{h}:3", "handle", f"{h}3:",
         "netem", "delay", f"{atraso_ms}ms", "limit", "100000"],
        ["filter", "add", "dev", "lo", "parent", f"{h}:", "protocol", "ip",
         "prio", "1", "u32", "match", "ip", "dport", str(PORTA_CAL), "0xffff",
         "flowid", f"{h}:3"],
        ["filter", "add", "dev", "lo", "parent", f"{h}:", "protocol", "ip",
         "prio", "2", "u32", "match", "ip", "sport", str(PORTA_CAL), "0xffff",
         "flowid", f"{h}:3"],
    ]
    _netem_container = container
    for p in passos:
        r = tc(container, *p)
        if r.returncode != 0:
            remove_netem(container)
            return (r.stderr or r.stdout).strip()
    return None


def pacotes_netem(container):
    r = tc(container, "-s", "qdisc", "show", "dev", "lo")
    m = re.search(rf"qdisc netem {HANDLE_TC}3:.*?Sent \d+ bytes (\d+) pkt", r.stdout, re.S)
    return int(m.group(1)) if m else None


def v2_netem(args, registros):
    etapa("V2", "Exatidao: atraso de rede CONHECIDO tem que ser medido 1:1",
          """Injeta atraso com tc netem no loopback do tester, filtrado so' pela
    porta de calibracao -- ida (poses) e volta (frames). Um atraso D por sentido
    tem que aparecer como exatamente 2D a mais no net_rtt. A reta
    net_rtt x 2D precisa ter inclinacao 1 e ser linear: e' a prova de que o
    instrumento mede atraso de rede sem ganho, sem saturacao e sem offset
    escondido.

    O contador do netem confirma que os pacotes da calibracao passaram de fato
    pela fila atrasada. O loopback volta ao estado original no fim, mesmo com
    erro ou Ctrl+C.""")
    c = container_com("tc")
    if not c:
        aviso("V2 NAO EXECUTADA: 'tc' nao existe nos containers ue/gnb do tester. "
              "Alternativa manual no brix-porvir-02 (tem sudo): sudo nsenter -t "
              "<pid do nr-ue> -n tc qdisc add dev lo ...", escopo="calibracao")
        return {"executada": False, "motivo": "tc ausente na imagem do tester"}
    atual = tc(c, "qdisc", "show", "dev", "lo").stdout
    if f"qdisc prio {HANDLE_TC}:" in atual:
        info("sobrou qdisc de uma calibracao anterior no loopback; removendo")
        remove_netem(c)
    elif "noqueue" not in atual:
        aviso(f"V2 NAO EXECUTADA: o loopback do tester ja' tem um qdisc que nao e' "
              f"desta calibracao ({atual.strip()[:80]}). Nao vou sobrescrever.",
              escopo="calibracao")
        return {"executada": False, "motivo": "qdisc alheio no loopback"}
    fps = tcb.PERFIS[args.perfil]["fps"]
    atrasos = args.atraso_ms or [0.0, 1.0, 2.0, 5.0]
    pontos = []
    try:
        sobe_servidor_cal(args.perfil, 0)
        for D in atrasos:
            erro = aplica_netem(c, D)
            if erro:
                dica = (" -- carregue o modulo no brix-porvir-02: sudo modprobe sch_netem"
                        if "unknown" in erro.lower() or "not found" in erro.lower() else "")
                aviso(f"V2 NAO EXECUTADA: tc recusou o netem ({erro[:120]}){dica}",
                      escopo="calibracao")
                return {"executada": False, "motivo": f"tc: {erro[:200]}"}
            rotulo = f"V2-netem-{D:g}ms"
            csv = csv_remoto(CLI, rotulo)
            reg = mede_ou_registra("V2", "sem-5g", CLI, f"127.0.0.1:{PORTA_CAL}",
                                   "127.0.0.1", CLI, METRICAS_CAL, fps, args,
                                   rotulo=rotulo, csv=csv)
            reg["atraso_ms"] = D
            reg["netem_pkts"] = pacotes_netem(c)
            remove_netem(c)
            info(f"netem atrasou {reg['netem_pkts']} pacotes da calibracao")
            registros.append(reg)
            pontos.append(reg)
            copia_csv(CLI, csv, args.saida, rotulo)
            time.sleep(args.pausa)
    finally:
        if _netem_container:
            remove_netem(_netem_container)
        para_servidor_cal()
    val = [p for p in pontos if p["valida"] and p.get("netem_pkts")]
    if len(val) < 3:
        aviso("V2 com menos de 3 pontos validos", escopo="calibracao")
        return {"executada": True, "aprovada": False, "motivo": "pontos insuficientes"}
    xs = [2 * p["atraso_ms"] * 1000 for p in val]
    rn = regressao(xs, [p["metricas"]["net_p50"] for p in val])
    aprovada = (rn and abs(rn["inclinacao"] - 1) <= TOL_INCLINACAO
                and rn["r2"] >= R2_MIN)
    print(f"\n       net_rtt p50 = {rn['inclinacao']:.3f} x (2 x atraso) + "
          f"{rn['intercepto']:.0f} us   (esperado 1,000; R2={rn['r2']:.4f})")
    for p in val:
        esperado = 2 * p["atraso_ms"] * 1000 + rn["intercepto"]
        print(f"       atraso {p['atraso_ms']:>4g} ms/sentido: medido "
              f"{p['metricas']['net_p50']:>8.0f} us, reta {esperado:>8.0f} us")
    (ok if aprovada else aviso)(
        "V2 APROVADA: o atraso injetado aparece 1:1 no net_rtt" if aprovada
        else "V2 REPROVADA: o instrumento nao reproduz o atraso injetado")
    return {"executada": True, "aprovada": bool(aprovada), "atrasos_ms": atrasos,
            "net_rtt": rn}


# --------------------------------------------------------------------------
# V3 -- testemunha independente (ping)
# --------------------------------------------------------------------------
def _pct(valores, q):
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def v3_ping(args, ctx, ag, registros):
    etapa("V3", "Testemunha independente: ICMP no MESMO instante e caminho do C1",
          """ping nao e' codigo nosso e responde dentro do kernel do destino, sem
    Python nenhum: e' um limite INFERIOR do net_rtt no mesmo caminho. Ele roda
    AO MESMO TEMPO que um fluxo C1 -- ping ocioso nao serve de comparacao,
    porque brix ocioso e' mais lento que brix sob carga (a CPU dorme entre os
    pacotes e demora a acordar).

    As respostas sao recortadas para a janela pos-warmup do cliente, marcada no
    relogio do proprio no. A comparacao e' de iguais: minimo com minimo (o piso
    do caminho, sem fila) e mediana com mediana. A diferenca esperada e' da
    ordem de um piso C0 -- o que o Python das duas pontas acrescenta ao ICMP.""")
    c = container_com("ping")
    if not c:
        aviso("V3 NAO EXECUTADA: 'ping' nao existe nos containers ue/gnb do tester",
              escopo="calibracao")
        return {"executada": False, "motivo": "ping ausente"}

    def piso(chave):
        vals = [ag[n][chave]["mediana"] for n in ("C0-tester", "C0-borda", "C0-nucleo")
                if ag.get(n) and ag[n].get(chave)]
        return max(vals) if vals else None
    piso_min, piso_p50 = piso("net_min"), piso("net_p50")
    if piso_min is None or piso_p50 is None:
        aviso("V3 NAO EXECUTADA: sem piso C0 valido para comparar", escopo="calibracao")
        return {"executada": False, "motivo": "sem piso C0"}

    def relogio_no():
        r = tcb.kexec(tcb.TESTER_POD, c, "date", "+%s.%N", check=False,
                      quiet=True, timeout=20)
        try:
            return float(r.stdout.strip())
        except ValueError:
            return None

    # Tamanho do ping: o MESMO total de bytes por ida e volta que o
    # instrumento poe no fio (uma pose de 128 B + um pacote de frame de MTU B).
    # Com o ping padrao de 84 B a comparacao misturava atraso de serializacao
    # -- ~10 us por salto store-and-forward para cada 1228 B em 1 GbE -- com
    # overhead do instrumento. Cabecalho IP+ICMP e IP+UDP sao iguais (28 B).
    tamanho_ping = (128 + tcb.PERFIS[args.perfil]["mtu"]) // 2
    info(f"ping com {tamanho_ping} B de carga: mesmos bytes por ida e volta que "
         f"pose + pacote de frame")
    fps = {"borda": tcb.fps_alvo("free5gc-mec-app"),
           "nucleo": tcb.fps_alvo("free5gc-remote-app")}
    alvos = (("borda", ctx["ip_mec"], MEC), ("nucleo", ctx["ip_rem"], REM))
    resultado, coerente = {}, True
    for lado, ip, srv in alvos:
        arquivo, pidf = f"/tmp/v3-ping-{lado}.txt", f"/tmp/v3-ping-{lado}.pid"
        prazo = int(args.duracao + 60)      # teto de seguranca; o normal e' o SIGINT
        tcb.kexec(tcb.TESTER_POD, c, "sh", "-c",
                  f"ping -D -s {tamanho_ping} -i 0.02 -w {prazo} {ip} </dev/null >{arquivo} 2>&1 & "
                  f"echo $! >{pidf}", check=True, quiet=True, timeout=30)
        rotulo = f"V3-C1-{lado}"
        csv = csv_remoto(CLI, rotulo)
        reg = mede_ou_registra("V3", "sem-5g", CLI, f"{ip}:{tcb.VR_PORT}",
                               ctx["ip_tester"], srv, METRICAS_SRV, fps[lado], args,
                               rotulo=rotulo, csv=csv, antes=relogio_no,
                               depois=relogio_no)
        registros.append(reg)
        copia_csv(CLI, csv, args.saida, rotulo)
        # SIGINT faz o iputils fechar na hora e imprimir as estatisticas; a
        # espera so' confere a linha final, sem trazer o arquivo a cada volta.
        tcb.kexec(tcb.TESTER_POD, c, "sh", "-c", f"kill -INT $(cat {pidf}) 2>/dev/null",
                  check=False, quiet=True, timeout=20)
        tcb.espera(f"ping para {ip} encerrar",
                   lambda: tcb.kexec(tcb.TESTER_POD, c, "grep", "-q", "statistics",
                                     arquivo, check=False, quiet=True,
                                     timeout=20).returncode == 0,
                   prazo + 30, intervalo=1)
        texto = tcb.kexec(tcb.TESTER_POD, c, "cat", arquivo, check=False,
                          quiet=True, timeout=30).stdout
        amostras = [(float(m.group(1)), float(m.group(2)) * 1000)
                    for m in re.finditer(r"^\[(\d+\.\d+)\].*time=([\d.]+) ms",
                                         texto, re.M)]
        ini_no, fim_no = (reg.get("marcas_no") or [None, None])
        janela = amostras
        if ini_no and fim_no:
            janela = [a for a in amostras
                      if ini_no + args.warmup + 0.5 <= a[0] <= fim_no - 1.0]
        if len(janela) < 50:
            aviso(f"V3 {lado}: so' {len(janela)} respostas de ping dentro da janela "
                  f"do cliente ({len(amostras)} no total)", escopo="calibracao")
            coerente = False
            continue
        rtts = [a[1] for a in janela]
        p_min, p_p50, p_p95 = min(rtts), statistics.median(rtts), _pct(rtts, 0.95)
        if not reg.get("valida"):
            coerente = False
            resultado[lado] = {"ip": ip, "motivo": "corrida C1 invalida"}
            continue
        n_min, n_p50 = reg["metricas"]["net_min"], reg["metricas"]["net_p50"]
        d_min, d_p50 = n_min - p_min, n_p50 - p_p50
        TOL = 50.0      # resolucao do ping (1 us) + ruido de escalonamento
        ok_min = -TOL <= d_min <= 2 * piso_min + TOL
        ok_p50 = -TOL <= d_p50 <= 2 * piso_p50 + TOL
        coerente = coerente and ok_min and ok_p50
        resultado[lado] = {
            "ip": ip, "respostas_na_janela": len(rtts),
            "ping_us": {"min": p_min, "p50": p_p50, "p95": p_p95},
            "net_rtt_us": {"min": n_min, "p50": n_p50},
            "diferenca_us": {"min": d_min, "p50": d_p50},
            "limite_us": {"min": [-TOL, 2 * piso_min + TOL],
                          "p50": [-TOL, 2 * piso_p50 + TOL]},
            "coerente": ok_min and ok_p50}
        for rot, n, p, d, piso_, okk in (("min", n_min, p_min, d_min, piso_min, ok_min),
                                        ("p50", n_p50, p_p50, d_p50, piso_p50, ok_p50)):
            print(f"       C1-{lado:<7}{rot}: net_rtt={n:>6.0f}  ping={p:>6.0f}  "
                  f"diferenca={d:>+5.0f} us  (aceito -{TOL:.0f}..{2 * piso_ + TOL:.0f})"
                  f"  [{'coerente' if okk else 'INCOERENTE'}]")
        info(f"{len(rtts)} respostas de ping simultaneas ao fluxo; p95 do ping {p_p95:.0f} us")
        time.sleep(args.pausa)
    (ok if coerente else aviso)(
        "V3 COERENTE: instrumento e testemunha independente concordam dentro do piso"
        if coerente else "V3 INCOERENTE: o instrumento discorda da testemunha independente")
    return {"executada": True, "coerente": coerente, "tamanho_ping_b": tamanho_ping,
            "piso_min_us": piso_min,
            "piso_p50_us": piso_p50, "caminhos": resultado}


# --------------------------------------------------------------------------
# relatorio
# --------------------------------------------------------------------------
def relatorio(args, ctx, placement, ag, v1, v2, v3):
    L = []
    L.append(f"CALIBRACAO DO INSTRUMENTO -- perfil {args.perfil}, "
             f"{args.repeticoes} repeticoes de {args.duracao:g}s (warmup {args.warmup:g}s)")
    L.append(f"placement: {json.dumps(placement)}")
    L.append("")
    L.append("1. ESCADA DE CONTROLE  (net_rtt em us; mediana entre repeticoes [min-max])")
    L.append(f"   {'degrau':<11}{'validas':>8}{'net min':>9}  {'net p50':>20}{'desvio':>8}{'net p99':>9}"
             f"{'jitter':>8}{'perda %':>9}{'Mbps':>7}")
    for nome in ORDEM_DEGRAUS:
        a = ag.get(nome)
        if not a:
            continue
        p50 = a["net_p50"]

        def med(k, casas=0):
            return num(a[k]["mediana"], casas) if a.get(k) else "-"
        faixa = (f"{p50['mediana']:.0f} [{p50['min']:.0f}-{p50['max']:.0f}]"
                 if p50 else "-")
        desv = num(p50["desvio"], 0) if p50 and p50["desvio"] is not None else "-"
        L.append(f"   {nome:<11}{a['validas']:>4}/{a['corridas']:<3}{med('net_min'):>9}  {faixa:>20}{desv:>8}"
                 f"{med('net_p99'):>9}{med('jitter_net'):>8}{med('perda_pct', 3):>9}"
                 f"{med('mbps', 2):>7}")

    def m(n):
        return ag[n]["net_p50"]["mediana"] if ag.get(n) and ag[n]["net_p50"] else None
    pisos = {n: m(n) for n in ("C0-tester", "C0-borda", "C0-nucleo") if m(n) is not None}
    piso = max(pisos.values()) if pisos else None
    L.append("")
    L.append("2. DECOMPOSICAO DO net_rtt p50  (us)")
    L.append(f"   piso do instrumento (maior C0): {num(piso, 0)}   por maquina: "
             + ", ".join(f"{k}={v:.0f}" for k, v in pisos.items()))
    L.append(f"   {'caminho':<8}{'C1 rede s/ 5G':>16}{'C2 5G':>10}{'rede - piso':>14}"
             f"{'5G (C2-C1)':>13}")
    for lado in ("borda", "nucleo"):
        c1, c2 = m(f"C1-{lado}"), m(f"C2-{lado}")
        L.append(f"   {lado:<8}{num(c1, 0):>16}{num(c2, 0):>10}"
                 f"{num(None if c1 is None or piso is None else c1 - piso, 0):>14}"
                 f"{num(None if c1 is None or c2 is None else c2 - c1, 0):>13}")

    L.append("")
    L.append("3. RUIDO x EFEITO")
    b, n = ag.get("C2-borda"), ag.get("C2-nucleo")
    efeito = None
    if b and n and b["net_p50"] and n["net_p50"]:
        efeito = n["net_p50"]["mediana"] - b["net_p50"]["mediana"]
        sb, sn = b["net_p50"]["desvio"], n["net_p50"]["desvio"]
        L.append(f"   aplicacao fora (2 UPFs) no net_rtt p50 (C2-nucleo - C2-borda): "
                 f"{efeito:.0f} us")
        L.append("   (nao e' o ganho do LBO: este sai de a-mec x b-mec, em "
                 "campanha-a-vs-b.py)")
        if sb is not None and sn is not None:
            mde, gl = menor_diferenca_detectavel(sb, b["net_p50"]["n"],
                                                 sn, n["net_p50"]["n"])
            L.append(f"   desvio entre repeticoes: borda {sb:.0f} us, nucleo {sn:.0f} us")
            L.append(f"   menor diferenca detectavel (alfa 5%, poder 80%, t de Student, "
                     f"gl de Welch = {num(gl, 1)}): {mde:.0f} us"
                     + (f" -> efeito = {efeito / mde:.1f}x essa diferenca" if mde else ""))
        else:
            L.append("   (desvio indisponivel: rode com --repeticoes >= 2)")
    s0 = ag.get("C0-tester", {}).get("net_p50")
    if s0 and s0["desvio"] is not None:
        L.append(f"   ruido do proprio instrumento (desvio do p50 em C0-tester): {s0['desvio']:.0f} us")

    L.append("")
    L.append("4. VALIDACOES DE EXATIDAO")
    for rot, v, chave in (("V1 sleep no servidor -> net_rtt parado", v1, "aprovada"),
                          ("V2 netem -> net_rtt 1:1", v2, "aprovada"),
                          ("V3 ping simultaneo (testemunha)", v3, "coerente")):
        if not v or not v.get("executada"):
            estado = f"NAO EXECUTADA ({(v or {}).get('motivo', 'pulada')})"
        else:
            estado = "OK" if v.get(chave) else "FALHOU"
        L.append(f"   {rot:<34} {estado}")
    return L


# --------------------------------------------------------------------------
def main():
    global _netem_container
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    listas = lambda s: [float(x) for x in s.split(",") if x.strip()]  # noqa: E731
    ap.add_argument("--perfil", default=tcb.PERFIL_PADRAO, choices=sorted(tcb.PERFIS))
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--duracao", type=float, default=30)
    ap.add_argument("--warmup", type=float, default=5)
    ap.add_argument("--pausa", type=float, default=3,
                    help="segundos entre corridas (a sessao anterior encerra)")
    ap.add_argument("--render-ms", type=listas, default=None,
                    help="renders da V1, ex: 0,1,2,3 (padrao: fracoes da folga)")
    ap.add_argument("--atraso-ms", type=listas, default=None,
                    help="atrasos da V2 por sentido, ex: 0,1,2,5")
    ap.add_argument("--ping-n", type=int, default=500)
    ap.add_argument("--pular-5g", action="store_true", help="sem os degraus C2")
    ap.add_argument("--pular-v1", action="store_true")
    ap.add_argument("--pular-v2", action="store_true")
    ap.add_argument("--pular-v3", action="store_true")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--carregar-assinantes", type=int, default=0, metavar="N")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--porta-mongo", type=int, default=27017)
    ap.add_argument("--namespace", default=tcb.NS)
    ap.add_argument("--saida", default=None)
    ap.add_argument("--conciso", action="store_true")
    args = ap.parse_args()

    tcb.NS, tcb.CONCISO, tcb.PAUSAR = args.namespace, args.conciso, False
    carimbo = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    args.saida = args.saida or os.path.join(tcb.BASE, "calibracao",
                                            f"{carimbo}-{args.perfil}")
    # Namespace com os campos que os passos 01-10 do teste do cenario B leem.
    targs = argparse.Namespace(
        tentativas=1, repeticoes=1, deploy=args.deploy, incluir_descartadas=False,
        sem_derrubar=True, timeout_derrubada=300,
        carregar_assinantes=args.carregar_assinantes, duracao=args.duracao,
        warmup=args.warmup, prova_duracao=10, so_prova=False, perfil=args.perfil,
        listar_perfis=False, saida=args.saida, timeout=args.timeout,
        porta_mongo=args.porta_mongo, namespace=args.namespace,
        pular_validate=False, passo_a_passo=False, conciso=args.conciso)

    t0 = time.time()
    registros, ctx, placement, ag = [], {}, {}, {}
    v1 = v2 = v3 = None
    rc, interrompido, erro = 0, False, None
    try:
        tcb.p01_ferramentas()
        tcb.p02_validate(targs)
        tcb.p03_deploy(targs)
        tcb.p04_pods(targs)
        placement = tcb.p05_placement()
        if not args.pular_5g:
            tcb.p06_assinantes(targs)
            tcb.p07_pfcp(targs)
        tcb.p08_tester(targs)
        ue_ip = None
        if not args.pular_5g:
            ue_ip = tcb.p09_sessao(targs)
            tcb.p10_rotas()
        _, ip_mec = pod_ativo("mec-app")
        _, ip_rem = pod_ativo("remote-app")
        ip_tester = tcb.kubectl("get", "pod", tcb.TESTER_POD, "-o",
                                "jsonpath={.status.podIP}", quiet=True).stdout.strip()
        ctx = {"ip_tester": ip_tester, "ip_mec": ip_mec, "ip_rem": ip_rem,
               "ue_ip": ue_ip, "mec_cluster_ip": tcb.MEC_IP,
               "remote_cluster_ip": tcb.REMOTE_IP}
        info(f"tester eth0={ip_tester}  mec-app pod={ip_mec}  remote-app pod={ip_rem}"
             f"  UE={ue_ip}")
        exec_em(CLI, "mkdir", "-p", "/data/calibracao")
        os.makedirs(args.saida, exist_ok=True)

        escada(args, ctx, registros)
        ag = agrega_degraus(registros)
        v1 = None if args.pular_v1 else v1_render(args, registros)
        v2 = None if args.pular_v2 else v2_netem(args, registros)
        v3 = None if args.pular_v3 else v3_ping(args, ctx, ag, registros)
    except Falha as e:
        erro = str(e)
        print(f"\n{tcb.VERM}FALHOU:{tcb.RESET} {erro}", file=sys.stderr)
        rc = 1
    except KeyboardInterrupt:
        interrompido, rc = True, 130
        print("\ninterrompido", file=sys.stderr)
    finally:
        # O loopback do tester e o servidor de calibracao voltam ao estado
        # original em qualquer saida -- netem esquecido no lo atrasaria a
        # proxima campanha sem ninguem saber.
        try:
            if _netem_container:
                remove_netem(_netem_container)
            para_servidor_cal()
        except Exception as exc:                          # noqa: BLE001
            print(f"  {tcb.AMAR}limpeza falhou: {exc}{tcb.RESET}", file=sys.stderr)

    ag = ag or agrega_degraus(registros)
    linhas = relatorio(args, ctx, placement, ag, v1, v2, v3) if registros else []
    if linhas:
        print(f"\n{'#' * 72}")
        for linha in linhas:
            print(linha)
        print("#" * 72)
    if registros or erro:
        os.makedirs(args.saida, exist_ok=True)
        with open(os.path.join(args.saida, "calibracao.json"), "w", encoding="utf-8") as fh:
            json.dump({"args": vars(args), "contexto": ctx, "placement": placement,
                       "agregados": ag, "v1": v1, "v2": v2, "v3": v3,
                       "registros": registros, "avisos": tcb.avisos, "erro": erro,
                       "segundos": round(time.time() - t0, 1)}, fh, indent=2)
        with open(os.path.join(args.saida, "relatorio.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(linhas) + "\n")
        info(f"resultados em {args.saida}")

    # A linha final diz a verdade, sem arredondar para o lado bom.
    corridas = [r for r in registros if r["degrau"].startswith("C")]
    invalidas = [r["rotulo"] for r in corridas if not r["valida"]]
    falhas = [n for n, v, k in (("V1", v1, "aprovada"), ("V2", v2, "aprovada"),
                                 ("V3", v3, "coerente"))
              if v and v.get("executada") and not v.get(k)]
    ausentes = [n for n, v in (("V1", v1), ("V2", v2), ("V3", v3))
                if not v or not v.get("executada")]
    tempo = f"{time.time() - t0:.0f}s"
    if interrompido:
        print(f"\n{tcb.AMAR}CALIBRACAO INTERROMPIDA{tcb.RESET} -- {len(corridas)} corridas em {tempo}")
    elif erro or not corridas:
        print(f"\n{tcb.VERM}CALIBRACAO NAO CONCLUIDA{tcb.RESET} -- {len(corridas)} corridas em {tempo}")
        rc = rc or 1
    elif invalidas or falhas:
        print(f"\n{tcb.VERM}INSTRUMENTO NAO CALIBRADO{tcb.RESET} -- "
              f"{len(invalidas)} corrida(s) invalida(s), validacoes reprovadas: "
              f"{', '.join(falhas) or 'nenhuma'} ({tempo})")
        rc = 1
    elif ausentes:
        print(f"\n{tcb.AMAR}INSTRUMENTO CALIBRADO PARCIALMENTE{tcb.RESET} -- "
              f"{len(corridas)} corridas validas; nao executadas: {', '.join(ausentes)} ({tempo})")
        rc = 3
    else:
        print(f"\n{tcb.VERDE}INSTRUMENTO CALIBRADO{tcb.RESET} -- {len(corridas)} corridas "
              f"validas, V1, V2 e V3 aprovadas ({tempo})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
