#!/usr/bin/env python3
"""
vr-client -- lado UE da aplicacao VR (roda DENTRO do pod do tester UERANSIM,
ligado ao IP do tunel da sessao PDU).

Envia o fluxo de pose/controle (uplink leve e frequente) e consome o fluxo de
frames (downlink pesado), medindo por frame:

    m2p_us  motion-to-photon: da amostra de pose ate o frame completo chegar
    hold_us tempo que a pose passou DENTRO do servidor: espera pelo proximo
            instante de render (cadencia + pacing) + o render em si (render_us)
    net_us  m2p - hold: a parcela que depende de ONDE o UPF esta

Tudo com o relogio do proprio cliente (ida e volta), entao nao ha necessidade
de sincronizar relogios entre o UE e a borda.

CARIMBO DO KERNEL. A chegada de cada pacote e' datada pelo KERNEL
(SO_TIMESTAMPNS), nao pelo Python. Sem isso, o tempo que este processo passa
esperando CPU entra no m2p e, como nao esta no hold, sai reportado como
"atraso de rede" -- um erro que CRESCE com a carga, justo onde a medida
precisa valer. Ver vrclock.py. O preco e' que o relogio das medidas passa a
ser o CLOCK_REALTIME; clock_drift_us no resumo denuncia um ajuste de NTP no
meio da corrida.

ONDE A PERDA ACONTECEU. dl_sock_overflow_pkts vem do SO_RXQ_OVFL: sao os
pacotes que chegaram e o KERNEL DESCARTOU porque a fila deste socket estava
cheia -- ou seja, perda DESTE cliente, nao do caminho do UPF. Se ele nao for
zero, o ponto nao mede rede, mede Python. udp_rcvbuf_errors faz o mesmo para
o namespace de rede inteiro, que no pod do tester inclui os sockets do nr-gnb
e do nr-ue: estouro la' e' perda dentro do UERANSIM.

JANELA. Latencia, perda e vazao sao TODAS calculadas na mesma janela
pos-warmup. Misturar (perda na corrida inteira, latencia so' depois do
warmup) contaminava a perda com a subida da sessao PDU.

Saida: CSV por frame (para os graficos) + resumo JSON no stdout (para o script
de campanha agregar).

    python3 vr_client.py --server mec-app:9100 --bind 60.60.0.1 \
        --duration 60 --csv /tmp/vr-mec.csv --label cenario-b-mec
"""
import argparse
import json
import os
import random
import socket
import struct
import sys
import threading
import time

import vrclock

POSE_MAGIC = b"VRP0"
FRAME_MAGIC = b"VRF0"
POSE_HDR = struct.Struct("!4sIQQI")
FRAME_HDR = struct.Struct("!4sIQHHQQIII")
FLAG_BYE = 1


def pct(values, q):
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


class Janela:
    """Contadores de um trecho da corrida. Existem dois: 'corrida' (tudo) e
    'medida' (pos-warmup). O resumo reporta o segundo, porque e' o mesmo
    recorte de onde saem os percentis de latencia."""

    __slots__ = ("rx_packets", "rx_bytes", "first_seq", "last_seq",
                 "t_first_ns", "t_last_ns", "ovfl_inicio", "ovfl_fim")

    def __init__(self):
        self.rx_packets = 0
        self.rx_bytes = 0
        self.first_seq = None
        self.last_seq = 0
        self.t_first_ns = None
        self.t_last_ns = None
        self.ovfl_inicio = None
        self.ovfl_fim = None

    def conta(self, fseq, nbytes, t_ns, ovfl):
        self.rx_packets += 1
        self.rx_bytes += nbytes
        if self.first_seq is None:
            self.first_seq = fseq
            self.t_first_ns = t_ns
            self.ovfl_inicio = ovfl
        self.last_seq = max(self.last_seq, fseq)
        self.t_last_ns = t_ns
        if ovfl is not None:
            self.ovfl_fim = ovfl

    @property
    def span_s(self):
        if self.t_first_ns is None or self.t_last_ns is None:
            return 0.0
        return (self.t_last_ns - self.t_first_ns) / 1e9

    @property
    def frames_esperados(self):
        return 0 if self.first_seq is None else self.last_seq - self.first_seq + 1

    @property
    def overflow(self):
        if self.ovfl_inicio is None or self.ovfl_fim is None:
            return None
        return max(0, self.ovfl_fim - self.ovfl_inicio)


class Client:
    def __init__(self, args):
        self.args = args
        self.sid = args.session or random.getrandbits(31)
        self.running = True
        self.samples = []            # dicts, um por frame completo
        self.frames = {}             # frame_seq -> estado parcial
        self.lock = threading.Lock()
        self.corrida = Janela()
        self.medida = Janela()
        self.tx_packets = 0
        self.tx_bytes = 0
        self.frames_partial = 0
        self.pkt_cnt = 0
        self.t0_ns = None            # chegada do primeiro pacote de downlink
        self.t_medida_ns = None      # inicio da janela pos-warmup
        self.seq_corte = -1          # maior frame_seq visto ANTES do corte
        self.na_janela = False
        self.tx_span = 0.0           # tempo em que o uplink de fato correu

        if args.pose_hz <= 0:
            sys.exit("--pose-hz precisa ser maior que zero")
        host, _, port = args.server.rpartition(":")
        # Resolve UMA vez: sendto() com nome faria uma consulta DNS por pacote.
        # O nome vem do CoreDNS do cluster, entao o IP e' o mesmo ClusterIP que
        # o mec-af anunciou ao NEF -- nenhum literal em lugar nenhum.
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror as e:
            sys.exit(f"nao resolvi '{host}': {e}")
        self.dst = (ip, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rcvbuf, _ = vrclock.buffers(self.sock, 8 << 20)
        self.ts_kernel, self.tem_ovfl = vrclock.habilitar(self.sock)
        self.sock.bind((args.bind, args.lport))
        # Timeout pelo kernel, e nao por sock.settimeout(): o modo 'timeout' do
        # CPython acrescenta um poll() por pacote no laco mais quente do
        # cliente, exatamente o que nao pode custar caro sob carga alta.
        vrclock.rcvtimeo(self.sock, 0.2)
        self.ancbuf = vrclock.ancbufsize()
        self.rxbuf = bytearray(2048)

    # ------------------------------------------------------------------ TX
    def tx_loop(self):
        a = self.args
        period = 1.0 / a.pose_hz
        pad = bytes(max(0, a.pose_bytes - POSE_HDR.size))
        seq = 0
        next_t = inicio = time.perf_counter()
        end = next_t + a.duration
        while self.running and time.perf_counter() < end:
            next_t += period
            seq += 1
            pkt = POSE_HDR.pack(POSE_MAGIC, self.sid, seq,
                                vrclock.now_ns(), 0) + pad
            try:
                self.sock.sendto(pkt, self.dst)
                self.tx_packets += 1
                self.tx_bytes += len(pkt)
            except OSError as exc:
                print(f"erro de envio: {exc}", file=sys.stderr)
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.perf_counter()
        self.tx_span = time.perf_counter() - inicio
        # Encerra a sessao no servidor para ele parar de enviar frames.
        try:
            self.sock.sendto(POSE_HDR.pack(POSE_MAGIC, self.sid, seq + 1,
                                           vrclock.now_ns(), FLAG_BYE),
                             self.dst)
        except OSError:
            pass
        self.running = False

    # ------------------------------------------------------------------ RX
    def rx_loop(self):
        recv_into = self.sock.recvmsg_into
        vista = [memoryview(self.rxbuf)]
        buf = self.rxbuf
        warmup_ns = int(self.args.warmup * 1e9)
        while self.running:
            try:
                n, ancdata, _, _ = recv_into(vista, self.ancbuf)
            except (BlockingIOError, socket.timeout):
                continue
            except OSError:
                return
            if n < FRAME_HDR.size:
                continue
            (magic, sid, fseq, idx, cnt, pose_seq, t_pose_ns,
             hold_us, render_us, ai_us) = FRAME_HDR.unpack_from(buf)
            if magic != FRAME_MAGIC or sid != self.sid:
                continue
            if cnt < 1:
                continue

            k_ns, ovfl = vrclock.ler_anc(ancdata) if ancdata else (None, None)
            now_ns = k_ns if k_ns is not None else vrclock.now_ns()
            if self.t0_ns is None:
                self.t0_ns = now_ns
                self.t_medida_ns = now_ns + warmup_ns
            self.pkt_cnt = cnt
            self.corrida.conta(fseq, n, now_ns, ovfl)
            # A janela de medida comeca no primeiro frame INTEIRAMENTE dentro
            # dela, e nao no primeiro pacote depois do corte. Um frame partido
            # pelo corte teria parte dos pacotes contada fora e todos os seus
            # esperados contados dentro, e a diferenca sairia como perda: num
            # teste de 4 s com 44 pacotes por frame isso ja' inventava 0,08% de
            # perda que nao existia.
            if not self.na_janela:
                if now_ns < self.t_medida_ns:
                    self.seq_corte = max(self.seq_corte, fseq)
                elif fseq > self.seq_corte:
                    self.na_janela = True
            if self.na_janela:
                self.medida.conta(fseq, n, now_ns, ovfl)

            st = self.frames.get(fseq)
            if st is None:
                # st[0] e' a MASCARA de bits dos idx ja' vistos, nao uma
                # contagem: com contagem, um pacote DUPLICADO fecharia um frame
                # a que ainda falta pedaco, e o m2p daquele frame sairia medido
                # no instante errado (cedo demais).
                st = self.frames[fseq] = [0, cnt, t_pose_ns, hold_us,
                                          render_us, ai_us, pose_seq]
            if idx < st[1]:
                st[0] |= 1 << idx
            if st[0] == (1 << st[1]) - 1:
                del self.frames[fseq]
                # hold do pacote QUE FECHOU o frame -- e' a chegada dele que
                # define o m2p, entao e' o tempo-no-servidor dele que precisa
                # sair da conta do net_us. Com o pacing ligado os pacotes de um
                # frame saem em instantes diferentes, e este e' o unico hold
                # que casa com o instante medido.
                st[3] = hold_us
                self.record(fseq, now_ns, st)
            # Frames antigos que nunca completaram viram perda.
            if len(self.frames) > 64:
                for old in sorted(self.frames)[:-32]:
                    self.frames.pop(old, None)
                    self.frames_partial += 1

    def record(self, fseq, now_ns, st):
        _, cnt, t_pose_ns, hold_us, render_us, ai_us, pose_seq = st
        m2p_us = (now_ns - t_pose_ns) / 1000.0
        # hold ja inclui o render (medido no instante do envio).
        net_us = m2p_us - hold_us
        t_rel = (now_ns - self.t0_ns) / 1e9
        with self.lock:
            self.samples.append({
                "t_s": round(t_rel, 6),
                "frame_seq": fseq,
                "pose_seq": pose_seq,
                "m2p_us": round(m2p_us, 1),
                "net_us": round(net_us, 1),
                "hold_us": hold_us,
                "render_us": render_us,
                "ai_us": ai_us,
                "pkts": cnt,
            })

    # -------------------------------------------------------------- resumo
    def summary(self, wall_s, saude):
        a = self.args
        # Mesmo recorte dos contadores de perda/vazao: a janela comeca no
        # primeiro frame inteiro pos-warmup. Filtrar a latencia por tempo e os
        # contadores por frame deixaria o frame da borda dentro de um e fora do
        # outro -- pouco, mas e' a diferenca entre duas contas que o texto
        # apresenta como sendo do mesmo recorte.
        corte = self.medida.first_seq
        with self.lock:
            kept = ([] if corte is None
                    else [s for s in self.samples if s["frame_seq"] >= corte])
        m2p = sorted(s["m2p_us"] for s in kept)
        net = sorted(s["net_us"] for s in kept)
        hold = sorted(float(s["hold_us"]) for s in kept)

        # Jitter no estilo RFC 3550, sobre a serie temporal (nao ordenada).
        # Calculado nas duas metricas: o de m2p inclui a cadencia de render
        # (varia com o fps), o de net_rtt e' o que a rede de fato causou.
        def rfc3550(key):
            j, prev = 0.0, None
            for smp in kept:
                if prev is not None:
                    j += (abs(smp[key] - prev) - j) / 16.0
                prev = smp[key]
            return round(j, 1)

        # Perda e vazao na MESMA janela dos percentis de latencia. Ambas ainda
        # sao ESTIMATIVAS do lado do cliente: frames perdidos inteiros nas
        # bordas da janela encolhem o denominador, entao esta perda e' um piso.
        # A conta exata sai no script de campanha, com o frame_packets_total
        # que o servidor diz ter entregue ao kernel.
        w = self.medida
        frames_expected = w.frames_esperados
        pkts_expected = frames_expected * (self.pkt_cnt or 1)
        loss = 0.0
        if pkts_expected:
            loss = max(0.0, 1 - w.rx_packets / pkts_expected) * 100

        # Vazao sobre a janela PEDIDA (o tempo em que a sessao esteve viva e o
        # downlink devia estar chegando), e nao sobre o intervalo em que ele de
        # fato chegou.
        #
        # Dividir pelo intervalo observado esconde a falha mais grave que este
        # teste pode ter: um fluxo que MORRE no meio da corrida sai com vazao
        # nominal e perda zero, porque o denominador encolhe junto com o
        # numerador. Foi exatamente o que aconteceu na primeira corrida no brix
        # -- o downlink do caminho remoto parou aos 33 s e o resumo dizia
        # "6,34 Mbps, perda 0,000%".
        #
        # dl_continuity_pct e' o outro lado da mesma conta: quanto da janela
        # pedida teve trafego. Menos de 100% e' fluxo interrompido, nao perda
        # de pacote -- sao coisas diferentes e precisam de numeros diferentes.
        janela_nominal = max(0.0, (self.tx_span or wall_s) - a.warmup)
        dl_eff = max(1e-9, janela_nominal or w.span_s or wall_s)
        ul_eff = max(1e-9, self.tx_span or wall_s)
        completos = len(self.samples)
        total_frames = completos + self.frames_partial
        return {
            "label": a.label,
            "server": a.server,
            "bind": a.bind,
            "duration_s": round(wall_s, 3),
            "ul_window_s": round(self.tx_span, 3),
            "warmup_s": a.warmup,
            "pose_hz": a.pose_hz,
            # Totais da CORRIDA INTEIRA (inclusive o warmup).
            "frames_complete": completos,
            "frames_partial": self.frames_partial,
            # Total da corrida, para casar com o frame_packets_total do
            # servidor: e' desse par que sai a perda EXATA (a do cliente
            # sozinho e' um piso, porque nao ve frame perdido inteiro).
            "dl_packets_rx_run": self.corrida.rx_packets,
            "frames_incomplete_pct": (
                round(self.frames_partial / total_frames * 100, 3)
                if total_frames else 0.0),
            # KPIs -- todos da JANELA DE MEDIDA, o mesmo recorte dos percentis.
            "frames_in_stats": len(kept),
            "dl_packet_loss_pct": round(loss, 4),
            "dl_throughput_mbps": round(w.rx_bytes * 8 / dl_eff / 1e6, 3),
            # Fracao da janela pedida em que houve downlink. < 100% = o fluxo
            # foi interrompido; a perda de pacote nao enxerga isso, porque um
            # servidor que PARA de emitir nao deixa buraco de sequencia.
            "dl_continuity_pct": round(min(100.0, w.span_s / dl_eff * 100), 2),
            "ul_packets_tx": self.tx_packets,
            "ul_pose_hz_real": round(self.tx_packets / ul_eff, 1),
            "ul_throughput_mbps": round(self.tx_bytes * 8 / ul_eff / 1e6, 3),
            # Os contadores de onde os KPIs de perda/vazao saem. Ficam num
            # bloco proprio para nao ficar ambiguo o que e' janela e o que e'
            # corrida inteira -- misturar os dois no mesmo nivel foi o que
            # antes deixava "frames_expected" e "frames_complete" com recortes
            # diferentes lado a lado.
            "janela": {
                "inicio_s": a.warmup,
                "nominal_s": round(janela_nominal, 3),
                "span_s": round(w.span_s, 3),
                "frames_esperados": frames_expected,
                "dl_packets_rx": w.rx_packets,
                "dl_packets_esperados": pkts_expected,
            },
            "m2p_us": {
                "min": pct(m2p, 0), "p50": pct(m2p, 0.50), "p95": pct(m2p, 0.95),
                "p99": pct(m2p, 0.99), "max": pct(m2p, 1.0),
                "mean": round(sum(m2p) / len(m2p), 1) if m2p else None,
            },
            "net_rtt_us": {
                "min": pct(net, 0), "p50": pct(net, 0.50), "p95": pct(net, 0.95),
                "p99": pct(net, 0.99), "max": pct(net, 1.0),
                "mean": round(sum(net) / len(net), 1) if net else None,
            },
            # hold = tempo DENTRO do servidor (espera pelo proximo instante
            # de render + janela de pacing + render). Vai reportado porque e' a
            # unica forma de o leitor conferir a decomposicao m2p = net + hold
            # -- e de enxergar quanto do m2p e' escolha do gerador (o pacing) em
            # vez de propriedade do caminho.
            "hold_us": {
                "min": pct(hold, 0), "p50": pct(hold, 0.50),
                "p95": pct(hold, 0.95), "max": pct(hold, 1.0),
                "mean": round(sum(hold) / len(hold), 1) if hold else None,
            },
            "jitter_us": rfc3550("m2p_us"),
            "jitter_net_us": rfc3550("net_us"),
            # ------------------------------------------------ saude da medida
            # Tudo abaixo responde "esta corrida vale?". Nenhum deles descreve
            # a rede: descrevem se o MEDIDOR aguentou medir.
            "saude": saude,
        }

    def saude(self, snmp0, ctx0, drift0, drops0):
        """Evidencia de que a corrida mediu a rede e nao o proprio cliente."""
        snmp1 = vrclock.udp_erros()
        ctx1 = vrclock.ctxt_switches()
        rt1, mono1 = vrclock.clock_drift_us()
        rt0, mono0 = drift0
        drops1 = vrclock.udp_drops(self.lport_real)

        def d(k):
            if not snmp0 or not snmp1 or k not in snmp0 or k not in snmp1:
                return None
            return snmp1[k] - snmp0[k]

        return {
            "rx_timestamp_kernel": self.ts_kernel,
            "sock_rcvbuf_bytes": self.rcvbuf,
            # Pacotes que chegaram e o kernel jogou fora por fila cheia DESTE
            # socket: perda do cliente, nao do caminho do UPF. A fonte confiavel
            # e' o /proc (dl_sock_drops); o cmsg do SO_RXQ_OVFL fica como
            # confirmacao, porque nem sempre vem.
            "dl_sock_drops": (None if drops0 is None or drops1 is None
                              else drops1 - drops0),
            "dl_sock_overflow_pkts": self.medida.overflow if self.tem_ovfl else None,
            "dl_sock_overflow_run": self.corrida.overflow if self.tem_ovfl else None,
            # Do netns inteiro -- no pod do tester, inclui nr-gnb e nr-ue.
            "udp_rcvbuf_errors": d("RcvbufErrors"),
            "udp_in_errors": d("InErrors"),
            # Vezes que o escalonador tirou este processo da CPU sem ele pedir.
            "ctxt_switches_involuntary": (
                None if ctx0 is None or ctx1 is None else ctx1 - ctx0),
            # Quanto o CLOCK_REALTIME andou alem do monotonico durante a
            # corrida. Alguns ms = houve ajuste de NTP e as amostras de m2p
            # daquele trecho estao deslocadas.
            "clock_drift_us": round(((rt1 - rt0) - (mono1 - mono0)) / 1000.0, 1),
        }

    def flush_parciais(self):
        """Frames que ficaram incompletos ate' o fim da corrida NUNCA passaram
        pela poda dos 64 e, sem isto, sumiam da contabilidade: o resumo dizia
        'frames_partial: 0' num teste que perdeu pacote do inicio ao fim."""
        self.frames_partial += len(self.frames)
        self.frames.clear()

    def write_csv(self, path):
        with self.lock:
            rows = list(self.samples)
        cols = ["t_s", "frame_seq", "pose_seq", "m2p_us", "net_us", "hold_us",
                "render_us", "ai_us", "pkts"]
        with open(path, "w") as fh:
            fh.write("label," + ",".join(cols) + "\n")
            for r in rows:
                fh.write(self.args.label + "," +
                         ",".join(str(r[c]) for c in cols) + "\n")

    def run(self):
        a = self.args
        print(f"vr-client sid={self.sid} {a.bind}:{a.lport} -> {a.server} "
              f"pose={a.pose_hz} Hz por {a.duration}s "
              f"rcvbuf={self.rcvbuf // 1024} kB "
              f"carimbo_kernel={'sim' if self.ts_kernel else 'NAO'}",
              file=sys.stderr)
        if self.rcvbuf < 4 << 20:
            print("AVISO: o kernel cortou o rcvbuf pedido (8 MB) para "
                  f"{self.rcvbuf // 1024} kB. Levante net.core.rmem_max NO NO "
                  "-- e' sysctl global, nao existe por namespace de rede, e de "
                  "dentro do pod nao da'.", file=sys.stderr)
        self.lport_real = self.sock.getsockname()[1]
        snmp0 = vrclock.udp_erros()
        ctx0 = vrclock.ctxt_switches()
        drift0 = vrclock.clock_drift_us()
        drops0 = vrclock.udp_drops(self.lport_real)

        rx = threading.Thread(target=self.rx_loop, daemon=True)
        rx.start()
        t0 = time.perf_counter()
        try:
            self.tx_loop()
        except KeyboardInterrupt:
            self.running = False
        time.sleep(0.5)             # drena os ultimos frames em voo
        self.running = False
        rx.join(timeout=1.0)
        wall = time.perf_counter() - t0
        self.flush_parciais()

        if a.csv:
            self.write_csv(a.csv)
            print(f"csv: {a.csv}", file=sys.stderr)
        s = self.summary(wall, self.saude(snmp0, ctx0, drift0, drops0))
        out = json.dumps(s, indent=2)
        if a.json:
            with open(a.json, "w") as fh:
                fh.write(out + "\n")
        print(out)
        if not s["frames_complete"]:
            print("NENHUM frame completo recebido -- confira a rota do tunel "
                  "e se o servidor esta alcancavel pelo IP do UE.",
                  file=sys.stderr)
            return 1
        ov = s["saude"]["dl_sock_drops"] or s["saude"]["dl_sock_overflow_pkts"]
        if ov:
            print(f"AVISO: o kernel descartou {ov} pacotes por fila cheia DESTE "
                  "socket. A perda desta corrida e' do cliente, nao do caminho "
                  "do UPF -- o ponto nao mede a rede.", file=sys.stderr)
        return 0


def envd(name, default, cast=str):
    v = os.environ.get(name)
    return cast(v) if v not in (None, "") else default


def parse_args(argv):
    p = argparse.ArgumentParser(description="Cliente VR (lado UE)")
    p.add_argument("--server", default=envd("VR_SERVER", "mec-app:9100"),
                   help="host:porta do vr-server (nome do Service mec-app ou "
                        "remote-app, ou IP); resolvido uma vez no inicio")
    p.add_argument("--bind", default=envd("VR_BIND", "0.0.0.0"),
                   help="IP do UE (interface do tunel), para o trafego sair pela sessao PDU")
    p.add_argument("--lport", type=int, default=envd("VR_LPORT", 0, int))
    p.add_argument("--duration", type=float, default=envd("VR_DURATION", 60.0, float))
    p.add_argument("--warmup", type=float, default=envd("VR_WARMUP", 5.0, float),
                   help="segundos iniciais descartados do resumo (de TODAS as "
                        "metricas: latencia, perda e vazao)")
    p.add_argument("--pose-hz", type=float, default=envd("VR_POSE_HZ", 250.0, float))
    p.add_argument("--pose-bytes", type=int, default=envd("VR_POSE_BYTES", 128, int))
    p.add_argument("--session", type=int, default=envd("VR_SESSION", 0, int))
    p.add_argument("--csv", default=envd("VR_CSV", ""))
    p.add_argument("--json", default=envd("VR_JSON", ""))
    p.add_argument("--label", default=envd("VR_LABEL", "run"))
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(Client(parse_args(sys.argv[1:])).run())
