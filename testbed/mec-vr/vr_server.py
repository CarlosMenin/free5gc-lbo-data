#!/usr/bin/env python3
"""
vr-server -- aplicacao MEC de realidade virtual (lado servidor / borda).

Gera a carga "VR-inspired bidirectional traffic profile" do TG1: fluxo de
DOWNLINK pesado (midia renderizada) fechado em loop com um fluxo de UPLINK
leve e frequente (pose/controle do headset).

    UE  --- POSE  (128 B @ 250 Hz, uplink)  --->  vr-server (MEC)
    UE  <-- FRAME (~12 kB @ 60 fps, downlink) --  vr-server (MEC)

Cada FRAME carrega de volta o timestamp da ULTIMA pose recebida, entao o
cliente mede motion-to-photon com o proprio relogio -- sem precisar
sincronizar UE e borda (nao ha NTP confiavel entre os nos do testbed).

O servidor tambem informa, em cada frame, quanto tempo a pose passou dentro
dele (hold_us: espera pelo proximo instante de render + o render em si, cujo
custo vai separado em render_us). Com isso o cliente separa duas metricas que
costumam ser confundidas:

    motion-to-photon = rede(UL) + hold + rede(DL)
    rtt de rede      = motion-to-photon - hold

A primeira e' a KPI da aplicacao; a segunda e' a que muda quando o UPF sai do
nucleo para a borda. Medir as duas e' o que permite dizer *quanto* do ganho de
QoE veio do Local Breakout.

DUAS COISAS QUE MUDARAM PARA A CARGA ESCALAR (leia antes de comparar com
resultados antigos):

1. O frame sai PACEADO dentro do periodo, em rajadas pequenas, e nao mais como
   uma rajada unica de todos os pacotes. Um frame de 50 Mbps a 60 fps sao 87
   pacotes (~104 kB) que, em rajada, saem na velocidade do veth -- alguns Gbps
   instantaneos. Nenhuma fila do caminho (fila de recepcao do cliente, sockets
   do nr-gnb/nr-ue) absorve isso, e o que estoura vira "perda" que na verdade
   e' burst. Paceado, o mesmo frame pede uma fila ~10x menor. Isto e' o que
   destrava cargas maiores. Custo: o hold do ultimo pacote passa a incluir a
   janela de pacing, entao o m2p sobe -- IGUAL NOS DOIS CAMINHOS, e o net_rtt
   (que desconta o hold) nao muda. Desligue com --no-spread para reproduzir o
   comportamento antigo.

2. O carimbo de recepcao da pose vem do KERNEL (SO_TIMESTAMPNS), nao mais do
   Python. Sem isso o tempo que ESTE processo passa fora da CPU entrava no
   hold errado e vazava para o net_rtt do cliente como se fosse rede -- um
   erro que cresce com a carga, justamente onde a medida importa. Ver
   vrclock.py.

Metricas Prometheus em /metrics (porta 9101 por padrao). Inclui o erro de
pacing do proprio gerador, os pacotes que o gerador NAO conseguiu entregar ao
socket e o tamanho efetivo dos buffers -- se qualquer um deles se mexer, o
gargalo e' o servidor e nao a rede, e a medida daquele ponto deve ser
descartada.

Uso tipico (dentro do pod MEC):
    python3 vr_server.py --bitrate-mbps 50 --fps 90

Todos os parametros aceitam variavel de ambiente (VR_BITRATE_MBPS, VR_FPS,
...), para trocar de perfil com 'kubectl set env' sem reconstruir nada.
"""
import argparse
import math
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import vrclock

POSE_MAGIC = b"VRP0"
FRAME_MAGIC = b"VRF0"

# magic, session, seq, t_client_ns, flags
POSE_HDR = struct.Struct("!4sIQQI")
# magic, session, frame_seq, pkt_idx, pkt_cnt, pose_seq, t_pose_ns,
# hold_us, render_us, ai_us
FRAME_HDR = struct.Struct("!4sIQHHQQIII")

FLAG_BYE = 1
MSG_DONTWAIT = getattr(socket, "MSG_DONTWAIT", 0x40)


class Metrics:
    """Contadores simples -- o formato texto do Prometheus e' trivial o
    bastante para nao valer uma dependencia externa na imagem."""

    def __init__(self):
        self.lock = threading.Lock()
        self.c = {
            "pose_packets_total": 0,
            "pose_bytes_total": 0,
            "pose_lost_total": 0,
            "pose_reordered_total": 0,
            "frames_sent_total": 0,
            "frame_packets_total": 0,
            "frame_bytes_total": 0,
            "frames_late_total": 0,
            "frames_truncated_total": 0,
            "frames_reanchored_total": 0,
            "send_dropped_total": 0,
            "send_errors_total": 0,
            "sessions_started_total": 0,
            "sessions_expired_total": 0,
            "ai_requests_total": 0,
            "ai_failures_total": 0,
        }
        self.g = {
            "sessions_active": 0,
            "pacing_error_seconds": 0.0,
            "render_seconds": 0.0,
            "ai_response_seconds": 0.0,
            "sock_rcvbuf_bytes": 0,
            "sock_sndbuf_bytes": 0,
            "kernel_rx_timestamp": 0,
            "pace_chunk_packets": 0,
            "pace_window_seconds": 0.0,
        }

    def add(self, key, value=1):
        with self.lock:
            self.c[key] += value

    def set(self, key, value):
        with self.lock:
            self.g[key] = value

    def render(self, labels):
        lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lbl = "{" + lbl + "}" if lbl else ""
        out = []
        with self.lock:
            for k, v in self.c.items():
                out.append(f"# TYPE vr_server_{k} counter")
                out.append(f"vr_server_{k}{lbl} {v}")
            for k, v in self.g.items():
                out.append(f"# TYPE vr_server_{k} gauge")
                out.append(f"vr_server_{k}{lbl} {v}")
        return "\n".join(out) + "\n"


class Session:
    __slots__ = ("sid", "addr", "seq", "t_pose_ns", "recv_ns", "frame_seq",
                 "started_ns")

    def __init__(self, sid, addr, now_ns):
        self.sid = sid
        self.addr = addr
        self.seq = 0
        self.t_pose_ns = 0
        self.recv_ns = now_ns
        self.frame_seq = 0
        self.started_ns = now_ns


class Server:
    def __init__(self, args):
        self.args = args
        self.metrics = Metrics()
        self.sessions = {}          # addr -> Session
        self.lock = threading.Lock()
        self.running = True
        self.ai_us = 0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rcvbuf, self.sndbuf = vrclock.buffers(self.sock, 8 << 20)
        self.ts_kernel, _ = vrclock.habilitar(self.sock, rxq_ovfl=False)
        self.sock.bind((args.bind, args.port))
        vrclock.rcvtimeo(self.sock, 0.2)
        self.ancbuf = vrclock.ancbufsize()
        self.rxbuf = bytearray(2048)
        self.metrics.set("sock_rcvbuf_bytes", self.rcvbuf)
        self.metrics.set("sock_sndbuf_bytes", self.sndbuf)
        self.metrics.set("kernel_rx_timestamp", 1 if self.ts_kernel else 0)

        self.payload_size = args.mtu - FRAME_HDR.size
        if self.payload_size < 1:
            sys.exit(f"--mtu {args.mtu} menor que o cabecalho ({FRAME_HDR.size} B)")
        if args.fps <= 0:
            sys.exit("--fps precisa ser maior que zero")
        if args.bitrate_mbps <= 0:
            sys.exit("--bitrate-mbps precisa ser maior que zero")
        frame_bytes = args.bitrate_mbps * 1e6 / 8.0 / args.fps
        self.pkt_cnt = max(1, math.ceil(frame_bytes / args.mtu))
        if self.pkt_cnt > 0xFFFF:
            sys.exit("frame grande demais: mais de 65535 pacotes por frame")

        # Pacing: divide o frame em rajadas de 'chunk' pacotes, uma a cada
        # 'gap' segundos, cobrindo pace_duty do periodo. O chunk NAO e' 1 de
        # proposito: com 174 pacotes num periodo de 16,7 ms o intervalo entre
        # pacotes cairia para 77 us, abaixo do que o time.sleep() do Linux
        # entrega, e o gerador passaria a estourar o periodo por overshoot --
        # trocando o problema de rajada por um de cadencia. Com chunk, o numero
        # de esperas e' limitado e cada uma fica acima do piso do sleep.
        period = 1.0 / args.fps
        self.budget = period * args.pace_duty
        gap_min = max(1e-4, args.pace_min_gap_ms / 1000.0)
        slots = max(1, int(self.budget / gap_min))
        self.chunk = max(1, math.ceil(self.pkt_cnt / slots))
        self.n_chunks = math.ceil(self.pkt_cnt / self.chunk)
        self.gap = self.budget / self.n_chunks if self.n_chunks else 0.0
        pacear = args.spread and self.n_chunks > 1
        self.metrics.set("pace_chunk_packets", self.chunk if pacear else 0)
        # Vai para o /metrics porque entra no m2p (dentro do hold): o script de
        # campanha registra o valor junto do resultado, senao a inflacao do m2p
        # fica sem explicacao no relatorio.
        self.metrics.set("pace_window_seconds",
                         round(self.gap * (self.n_chunks - 1), 6) if pacear else 0.0)

        # Buffer unico reaproveitado: evita alocar ~70 kB por frame.
        self.buf = bytearray(args.mtu)
        self.view = memoryview(self.buf)
        # Padrao de payload nao-nulo (compressores/offloads nao amam zeros).
        for i in range(FRAME_HDR.size, args.mtu):
            self.buf[i] = i & 0xFF

    # ------------------------------------------------------------------ RX
    def rx_loop(self):
        recv_into = self.sock.recvmsg_into
        vista = [memoryview(self.rxbuf)]
        while self.running:
            try:
                n, ancdata, _, addr = recv_into(vista, self.ancbuf)
            except (BlockingIOError, socket.timeout):
                continue        # SO_RCVTIMEO estourou: so' releia self.running
            except OSError:
                if self.running:
                    continue
                return
            if n < POSE_HDR.size:
                continue
            magic, sid, seq, t_ns, flags = POSE_HDR.unpack_from(self.rxbuf)
            if magic != POSE_MAGIC:
                continue

            # Carimbo DO KERNEL: o que este processo demorar entre a chegada do
            # pacote e esta linha nao pode entrar no hold, senao sai do m2p e
            # aparece como se fosse rede no net_rtt do cliente.
            k_ns, _ = vrclock.ler_anc(ancdata) if ancdata else (None, None)
            now_ns = k_ns if k_ns is not None else vrclock.now_ns()
            self.metrics.add("pose_packets_total")
            self.metrics.add("pose_bytes_total", n)

            with self.lock:
                s = self.sessions.get(addr)
                if s is None or s.sid != sid:
                    s = Session(sid, addr, now_ns)
                    self.sessions[addr] = s
                    self.metrics.add("sessions_started_total")
                    self.metrics.set("sessions_active", len(self.sessions))
                if flags & FLAG_BYE:
                    self.sessions.pop(addr, None)
                    self.metrics.set("sessions_active", len(self.sessions))
                    continue
                if seq > s.seq + 1 and s.seq:
                    self.metrics.add("pose_lost_total", seq - s.seq - 1)
                elif seq <= s.seq and s.seq:
                    self.metrics.add("pose_reordered_total")
                if seq >= s.seq:
                    s.seq = seq
                    s.t_pose_ns = t_ns
                    s.recv_ns = now_ns

    # ------------------------------------------------------------------ TX
    def tx_loop(self):
        a = self.args
        period = 1.0 / a.fps
        timeout_ns = int(a.session_timeout * 1e9)
        next_t = time.perf_counter()
        while self.running:
            next_t += period
            now_ns = vrclock.now_ns()

            with self.lock:
                dead = [k for k, s in self.sessions.items()
                        if now_ns - s.recv_ns > timeout_ns]
                for k in dead:
                    self.sessions.pop(k, None)
                if dead:
                    self.metrics.add("sessions_expired_total", len(dead))
                    self.metrics.set("sessions_active", len(self.sessions))
                # SNAPSHOT do estado de cada sessao, tirado SOB O LOCK. Ler
                # s.seq/s.t_pose_ns/s.recv_ns dentro do send_frame seria uma
                # corrida com o rx_loop: o hold_us sairia de uma pose e o
                # t_pose_ns de outra, e o net_us do cliente (m2p - hold)
                # erraria por ate' um intervalo de pose -- mesma ordem de
                # grandeza do net_rtt que se quer medir.
                active = [(s, s.seq, s.t_pose_ns, s.recv_ns)
                          for s in self.sessions.values()]

            render_us = self.render(len(active)) if active else 0

            # Com N sessoes o orcamento de pacing e' dividido entre elas: o
            # periodo e' um so' e todas precisam caber dentro dele.
            fatia = self.budget / max(1, len(active))
            for s, seq, t_pose_ns, recv_ns in active:
                self.send_frame(s, seq, t_pose_ns, recv_ns, render_us, fatia)

            now = time.perf_counter()
            drift = next_t - now
            self.metrics.set("pacing_error_seconds", round(-drift, 6))
            if drift > 0:
                time.sleep(drift)
            else:
                self.metrics.add("frames_late_total")
                if drift < -5 * period:
                    # Atraso grande: reancora o relogio em vez de tentar
                    # recuperar frames que ja perderam o sentido.
                    self.metrics.add("frames_reanchored_total")
                    next_t = now

    def send_frame(self, s, seq, t_pose_ns, recv_ns, render_us, budget):
        """seq/t_pose_ns/recv_ns vem do snapshot do tx_loop -- os tres precisam
        descrever A MESMA pose, senao o net_us do cliente sai errado."""
        s.frame_seq += 1
        pacear = self.args.spread and self.n_chunks > 1
        gap = budget / self.n_chunks if pacear else 0.0
        t_ref = time.perf_counter()
        enviados = 0
        for idx in range(self.pkt_cnt):
            if pacear and idx % self.chunk == 0 and idx:
                alvo = t_ref + (idx // self.chunk) * gap
                espera = alvo - time.perf_counter()
                if espera > 0:
                    # Prazo ABSOLUTO a partir de t_ref: o overshoot do sleep
                    # nao se acumula ao longo do frame, so' encurta a proxima
                    # espera.
                    time.sleep(espera)
            # hold recalculado A CADA pacote: os pacotes de um mesmo frame saem
            # em instantes diferentes e o cliente fecha o m2p na chegada do
            # ULTIMO. Cada pacote carregando o tempo que ELE passou aqui
            # dentro, o cliente casa o m2p com o hold certo; um hold unico por
            # frame jogaria o pacing do proprio servidor dentro do net_us, como
            # se fosse rede.
            hold_us = max(0, (vrclock.now_ns() - recv_ns) // 1000)
            FRAME_HDR.pack_into(
                self.buf, 0, FRAME_MAGIC, s.sid, s.frame_seq, idx,
                self.pkt_cnt, seq, t_pose_ns, int(hold_us),
                int(render_us), int(self.ai_us),
            )
            try:
                # MSG_DONTWAIT sem trocar o modo do socket (o rx_loop divide o
                # mesmo socket e continua bloqueante). Com socket bloqueante um
                # sndbuf cheio PARARIA o gerador ate' drenar, e o sintoma
                # apareceria como frame atrasado, sem dizer que a origem foi
                # aqui. Assim o estouro vira contador -- e um pacote que este
                # processo nunca entregou ao kernel nao pode ser contado como
                # perda da rede.
                self.sock.sendto(self.view, MSG_DONTWAIT, s.addr)
            except BlockingIOError:
                self.metrics.add("send_dropped_total", self.pkt_cnt - idx)
                break
            except OSError:
                self.metrics.add("send_errors_total")
                self.metrics.add("send_dropped_total", self.pkt_cnt - idx)
                break
            enviados += 1
        self.metrics.add("frames_sent_total")
        self.metrics.add("frame_packets_total", enviados)
        self.metrics.add("frame_bytes_total", enviados * self.args.mtu)
        if enviados < self.pkt_cnt:
            self.metrics.add("frames_truncated_total")

    def render(self, n_sessions):
        """Simula o custo de renderizar o frame. Com --render-ms 0 nao gasta
        nada; com valor > 0 queima CPU de proposito, para que o no de borda
        tenha carga computacional comparavel a de um render real.

        --render-sleep troca a queima por sleep. E' o modo da CALIBRACAO (V1),
        nao o da campanha. Queimando CPU, este processo segura o interpretador
        e a thread do rx_loop fica para tras: no instante do frame o servidor
        ainda tem na mao uma pose mais velha do que a que ja' chegou, e o
        hold -- que e' medido contra a CHEGADA dessa pose -- cresce MAIS do que
        o render injetado. Medido no perfil ar-industrial (12/09/2026): o hold
        subiu 1,32 x o render em vez de 1,00, e a V1 reprovou por isso. O
        sleep libera o interpretador, o rx_loop acompanha e o hold sobe 1:1 --
        que e' a propriedade que a V1 quer verificar.

        Quem quer carga de CPU na borda continua com a queima (o default): o
        sleep nao ocupa nucleo nenhum."""
        ms = self.args.render_ms
        if ms <= 0:
            self.metrics.set("render_seconds", 0.0)
            return 0
        budget = ms * n_sessions / 1000.0
        t0 = time.perf_counter()
        if self.args.render_sleep:
            time.sleep(budget)
        else:
            deadline = t0 + budget
            x = 0.0
            while time.perf_counter() < deadline:
                for _ in range(200):
                    x += 1.000001
        spent = time.perf_counter() - t0
        self.metrics.set("render_seconds", round(spent, 6))
        return spent * 1e6 / max(1, n_sessions)

    # ------------------------------------------------------------- AI hook
    def ai_loop(self):
        """Gancho para a aplicacao AI-on-RAN do Jetson: dispara inferencias a
        uma taxa fixa e mede o tempo de resposta. E' o "AI-on-RAN request
        rate" que o TG1 lista como dimensao de carga. Desligado por padrao."""
        import urllib.request

        a = self.args
        period = 1.0 / a.ai_rate
        payload = os.urandom(a.ai_bytes)
        next_t = time.perf_counter()
        while self.running:
            next_t += period
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(
                    a.ai_url, data=payload,
                    headers={"Content-Type": "application/octet-stream"})
                with urllib.request.urlopen(req, timeout=a.ai_timeout) as r:
                    r.read()
                dt = time.perf_counter() - t0
                self.ai_us = int(dt * 1e6)
                self.metrics.set("ai_response_seconds", round(dt, 6))
                self.metrics.add("ai_requests_total")
            except Exception:
                self.metrics.add("ai_requests_total")
                self.metrics.add("ai_failures_total")
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.perf_counter()

    # ------------------------------------------------------------- metrics
    def serve_metrics(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/metrics"):
                    body = server.metrics.render({
                        "role": server.args.role,
                        "profile": server.args.profile,
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.startswith("/healthz"):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok\n")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *_):
                pass

        ThreadingHTTPServer((self.args.bind, self.args.metrics_port),
                            Handler).serve_forever()

    def run(self):
        a = self.args
        mbps = self.pkt_cnt * a.mtu * 8 * a.fps / 1e6
        print(f"vr-server role={a.role} profile={a.profile} "
              f"udp={a.bind}:{a.port} metrics={a.metrics_port}", flush=True)
        print(f"  downlink: {self.pkt_cnt} pkt/frame x {a.mtu} B x {a.fps} fps "
              f"= {mbps:.1f} Mbps por sessao (alvo {a.bitrate_mbps} Mbps)",
              flush=True)
        if a.spread and self.n_chunks > 1:
            print(f"  pacing: {self.n_chunks} rajadas de {self.chunk} pkt a cada "
                  f"{self.gap * 1e3:.2f} ms ({self.budget * 1e3:.1f} ms de "
                  f"{1e3 / a.fps:.1f} ms)", flush=True)
        else:
            print("  pacing: DESLIGADO -- o frame inteiro sai em rajada unica "
                  f"({self.pkt_cnt * a.mtu / 1e3:.1f} kB)", flush=True)
        print(f"  buffers: rcvbuf={self.rcvbuf // 1024} kB "
              f"sndbuf={self.sndbuf // 1024} kB "
              f"carimbo_kernel={'sim' if self.ts_kernel else 'NAO'}", flush=True)
        if self.sndbuf < 4 << 20:
            print("  AVISO: o kernel cortou o sndbuf pedido (8 MB). Levante "
                  "net.core.wmem_max/rmem_max NO NO -- sao sysctl globais, nao "
                  "por namespace, e de dentro do pod nao da'.", flush=True)
        if not self.ts_kernel:
            print("  AVISO: sem SO_TIMESTAMPNS. O hold vai carimbado em "
                  "Python e leva junto o tempo fora da CPU deste processo.",
                  flush=True)
        print(f"  render={a.render_ms} ms/frame/sessao "
              f"[{'sleep' if a.render_sleep else 'queima de CPU'}] "
              f"ai={'on' if a.ai_url else 'off'}", flush=True)

        threading.Thread(target=self.serve_metrics, daemon=True).start()
        threading.Thread(target=self.rx_loop, daemon=True).start()
        if a.ai_url:
            threading.Thread(target=self.ai_loop, daemon=True).start()
        try:
            self.tx_loop()
        except KeyboardInterrupt:
            self.running = False


def envd(name, default, cast=str):
    v = os.environ.get(name)
    return cast(v) if v not in (None, "") else default


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Servidor da aplicacao VR do MEC (downlink pesado + loop fechado)")
    p.add_argument("--bind", default=envd("VR_BIND", "0.0.0.0"))
    p.add_argument("--port", type=int, default=envd("VR_PORT", 9100, int))
    p.add_argument("--metrics-port", type=int,
                   default=envd("VR_METRICS_PORT", 9101, int))
    p.add_argument("--bitrate-mbps", type=float,
                   default=envd("VR_BITRATE_MBPS", 50.0, float),
                   help="taxa de downlink POR SESSAO (default 50)")
    p.add_argument("--fps", type=int, default=envd("VR_FPS", 90, int))
    p.add_argument("--mtu", type=int, default=envd("VR_MTU", 1200, int),
                   help="bytes de payload UDP por pacote (default 1200, "
                        "abaixo do MTU do tunel GTP-U)")
    p.add_argument("--render-ms", type=float,
                   default=envd("VR_RENDER_MS", 0.0, float),
                   help="CPU queimada por frame/sessao, simulando o render")
    p.add_argument("--render-sleep", action=argparse.BooleanOptionalAction,
                   default=envd("VR_RENDER_SLEEP", "0") not in ("0", "false", ""),
                   help="injeta o --render-ms como SLEEP em vez de queima de "
                        "CPU. E' o modo da CALIBRACAO (V1): dormindo, o "
                        "interpretador fica livre, o rx_loop acompanha e o "
                        "hold sobe 1:1 com o render injetado. A campanha usa a "
                        "queima (default), que e' o que carrega o no de borda")
    p.add_argument("--spread", action=argparse.BooleanOptionalAction,
                   default=envd("VR_SPREAD", "1") not in ("0", "false", ""),
                   help="LIGADO por padrao: espalha os pacotes do frame ao "
                        "longo do periodo, em rajadas de --pace-chunk pacotes, "
                        "em vez de mandar o frame inteiro de uma vez. "
                        "--no-spread volta ao comportamento antigo (e volta a "
                        "perder frame em carga alta)")
    p.add_argument("--pace-duty", type=float,
                   default=envd("VR_PACE_DUTY", 0.8, float),
                   help="fracao do periodo do frame usada para espalhar os "
                        "pacotes (default 0.8; o resto e' folga para o proprio "
                        "gerador nao estourar a cadencia)")
    p.add_argument("--pace-min-gap-ms", type=float,
                   default=envd("VR_PACE_MIN_GAP_MS", 1.0, float),
                   help="intervalo minimo entre rajadas. Abaixo disso o "
                        "time.sleep() do Linux erra mais do que o intervalo "
                        "pedido; o tamanho da rajada e' derivado deste piso")
    p.add_argument("--session-timeout", type=float,
                   default=envd("VR_SESSION_TIMEOUT", 2.0, float))
    p.add_argument("--role", default=envd("VR_ROLE", "mec"),
                   help="rotulo das metricas: mec (borda) ou remote (nucleo)")
    p.add_argument("--profile", default=envd("VR_PROFILE", "heavy"))
    p.add_argument("--ai-url", default=envd("VR_AI_URL", ""),
                   help="endpoint da aplicacao AI-on-RAN (Jetson); vazio desliga")
    p.add_argument("--ai-rate", type=float, default=envd("VR_AI_RATE", 10.0, float))
    p.add_argument("--ai-bytes", type=int, default=envd("VR_AI_BYTES", 4096, int))
    p.add_argument("--ai-timeout", type=float, default=envd("VR_AI_TIMEOUT", 2.0, float))
    return p.parse_args(argv)


if __name__ == "__main__":
    Server(parse_args(sys.argv[1:])).run()
