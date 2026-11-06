#!/usr/bin/env python3
"""
vr-client -- UE side of the VR application (runs INSIDE the UERANSIM tester pod,
bound to the IP of the tunnel of the PDU session).

It sends the pose/control flow (light, frequent uplink) and consumes the flow of
frames (heavy downlink), measuring per frame:

    m2p_us  motion-to-photon: from the pose sample until the complete frame arrives
    hold_us time the pose spent INSIDE the server: wait for the next render
            instant (cadence + pacing) + the render itself (render_us)
    net_us  m2p - hold: the part that depends on WHERE the UPF is

Everything uses the client's own clock (round trip), so there is no need to
synchronize clocks between the UE and the edge.

KERNEL TIMESTAMP. The arrival of each packet is timestamped by the KERNEL
(SO_TIMESTAMPNS), not by Python. Without it, the time this process spends
waiting for the CPU enters m2p and, since it is not in hold, is reported as
"network delay" -- an error that GROWS with the load, exactly where the
measurement must hold. See vrclock.py. The price is that the clock of the
measurements becomes CLOCK_REALTIME; clock_drift_us in the summary reveals an
NTP adjustment in the middle of the run.

WHERE THE LOSS HAPPENED. dl_sock_overflow_pkts comes from SO_RXQ_OVFL: the
packets that arrived and the KERNEL DROPPED because the queue of this socket
was full -- that is, loss of THIS client, not of the UPF path. If it is not
zero, the point does not measure the network, it measures Python.
udp_rcvbuf_errors does the same for the whole network namespace, which in the
tester pod includes the sockets of nr-gnb and nr-ue: an overflow there is loss
inside UERANSIM.

WINDOW. Latency, loss and throughput are ALL computed in the same
post-warm-up window. Mixing them (loss over the whole run, latency only after
the warm-up) contaminated the loss with the setup of the PDU session.

Output: CSV per frame (for the plots) + JSON summary on stdout (for the
campaign script to aggregate).

    python3 vr_client.py --server mec-app:9100 --bind 60.60.0.1 \
        --duration 60 --csv /tmp/vr-mec.csv --label scenario-b-mec
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


class Window:
    """Counters of a stretch of the run. There are two: the whole run and the
    measurement window (after the warm-up). The summary reports the second,
    because it is the same window from which the latency percentiles come."""

    __slots__ = ("rx_packets", "rx_bytes", "first_seq", "last_seq",
                 "t_first_ns", "t_last_ns", "ovfl_start", "ovfl_end")

    def __init__(self):
        self.rx_packets = 0
        self.rx_bytes = 0
        self.first_seq = None
        self.last_seq = 0
        self.t_first_ns = None
        self.t_last_ns = None
        self.ovfl_start = None
        self.ovfl_end = None

    def tally(self, fseq, nbytes, t_ns, ovfl):
        self.rx_packets += 1
        self.rx_bytes += nbytes
        if self.first_seq is None:
            self.first_seq = fseq
            self.t_first_ns = t_ns
            self.ovfl_start = ovfl
        self.last_seq = max(self.last_seq, fseq)
        self.t_last_ns = t_ns
        if ovfl is not None:
            self.ovfl_end = ovfl

    @property
    def span_s(self):
        if self.t_first_ns is None or self.t_last_ns is None:
            return 0.0
        return (self.t_last_ns - self.t_first_ns) / 1e9

    @property
    def frames_expected_n(self):
        return 0 if self.first_seq is None else self.last_seq - self.first_seq + 1

    @property
    def overflow(self):
        if self.ovfl_start is None or self.ovfl_end is None:
            return None
        return max(0, self.ovfl_end - self.ovfl_start)


class Client:
    def __init__(self, args):
        self.args = args
        self.sid = args.session or random.getrandbits(31)
        self.running = True
        self.samples = []            # dicts, one per complete frame
        self.frames = {}             # frame_seq -> partial state
        self.lock = threading.Lock()
        self.measurement = Window()
        self.measured = Window()
        self.tx_packets = 0
        self.tx_bytes = 0
        self.frames_partial = 0
        self.pkt_cnt = 0
        self.t0_ns = None            # arrival of the first downlink packet
        self.t_measured_ns = None      # start of the post-warm-up window
        self.seq_cutoff = -1          # largest frame_seq seen BEFORE the cutoff
        self.in_window = False
        self.tx_span = 0.0           # time during which the uplink actually ran

        if args.pose_hz <= 0:
            sys.exit("--pose-hz must be greater than zero")
        host, _, port = args.server.rpartition(":")
        # Resolve ONCE: sendto() with a name would make one DNS query per packet.
        # The name comes from the CoreDNS of the cluster, so the IP is the same ClusterIP that
        # mec-af announced to the NEF -- no literal anywhere.
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror as e:
            sys.exit(f"could not resolve '{host}': {e}")
        self.dst = (ip, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rcvbuf, _ = vrclock.buffers(self.sock, 8 << 20)
        self.ts_kernel, self.has_ovfl = vrclock.enable(self.sock)
        self.sock.bind((args.bind, args.lport))
        # Timeout by the kernel, not by sock.settimeout(): the 'timeout' mode of
        # CPython adds one poll() per packet in the hottest loop of the
        # client, exactly what cannot be expensive under high load.
        vrclock.rcvtimeo(self.sock, 0.2)
        self.ancbuf = vrclock.ancbufsize()
        self.rxbuf = bytearray(2048)

    # ------------------------------------------------------------------ TX
    def tx_loop(self):
        a = self.args
        period = 1.0 / a.pose_hz
        pad = bytes(max(0, a.pose_bytes - POSE_HDR.size))
        seq = 0
        next_t = begin = time.perf_counter()
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
                print(f"send error: {exc}", file=sys.stderr)
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.perf_counter()
        self.tx_span = time.perf_counter() - begin
        # Ends the session at the server so that it stops sending frames.
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
        seen_ = [memoryview(self.rxbuf)]
        buf = self.rxbuf
        warmup_ns = int(self.args.warmup * 1e9)
        while self.running:
            try:
                n, ancdata, _, _ = recv_into(seen_, self.ancbuf)
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

            k_ns, ovfl = vrclock.read_anc(ancdata) if ancdata else (None, None)
            now_ns = k_ns if k_ns is not None else vrclock.now_ns()
            if self.t0_ns is None:
                self.t0_ns = now_ns
                self.t_measured_ns = now_ns + warmup_ns
            self.pkt_cnt = cnt
            self.measurement.tally(fseq, n, now_ns, ovfl)
            # The measurement window starts at the first frame ENTIRELY inside
            # it, not at the first packet after the cutoff. A frame split
            # by the cutoff would have some packets counted outside and all of its
            # expected packets counted inside, and the difference would show up as loss: in a
            # 4 s test with 44 packets per frame this already invented 0.08% of
            # loss that did not exist.
            if not self.in_window:
                if now_ns < self.t_measured_ns:
                    self.seq_cutoff = max(self.seq_cutoff, fseq)
                elif fseq > self.seq_cutoff:
                    self.in_window = True
            if self.in_window:
                self.measured.tally(fseq, n, now_ns, ovfl)

            st = self.frames.get(fseq)
            if st is None:
                # st[0] is the BIT MASK of the idx already seen, not a
                # count: with a count, a DUPLICATED packet would close a frame
                # that still lacks a piece, and the m2p of that frame would be measured
                # at the wrong instant (too early).
                st = self.frames[fseq] = [0, cnt, t_pose_ns, hold_us,
                                          render_us, ai_us, pose_seq]
            if idx < st[1]:
                st[0] |= 1 << idx
            if st[0] == (1 << st[1]) - 1:
                del self.frames[fseq]
                # hold of the packet THAT CLOSED the frame -- its arrival
                # defines the m2p, so its time in the server is the one that must
                # leave the net_us. With pacing on, the packets of a
                # frame leave at different instants, and this is the only hold
                # that matches the measured instant.
                st[3] = hold_us
                self.record(fseq, now_ns, st)
            # Old frames that never completed count as loss.
            if len(self.frames) > 64:
                for old in sorted(self.frames)[:-32]:
                    self.frames.pop(old, None)
                    self.frames_partial += 1

    def record(self, fseq, now_ns, st):
        _, cnt, t_pose_ns, hold_us, render_us, ai_us, pose_seq = st
        m2p_us = (now_ns - t_pose_ns) / 1000.0
        # hold already includes the render (measured at the instant of sending).
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

    # -------------------------------------------------------------- summary
    def summary(self, wall_s, health):
        a = self.args
        # Same window as the loss/throughput counters: the window starts at the
        # first whole frame after the warm-up. Filtering the latency by time and the
        # counters by frame would leave the edge frame inside one and outside the
        # other -- little, but it is the difference between two figures that the text
        # presents as coming from the same window.
        cutoff = self.measured.first_seq
        with self.lock:
            kept = ([] if cutoff is None
                    else [s for s in self.samples if s["frame_seq"] >= cutoff])
        m2p = sorted(s["m2p_us"] for s in kept)
        net = sorted(s["net_us"] for s in kept)
        hold = sorted(float(s["hold_us"]) for s in kept)

        # Jitter in the RFC 3550 style, over the time series (not sorted).
        # Computed for both metrics: the one of m2p includes the render cadence
        # (varies with the fps), the one of net_rtt is what the network actually caused.
        def rfc3550(key):
            j, prev = 0.0, None
            for smp in kept:
                if prev is not None:
                    j += (abs(smp[key] - prev) - j) / 16.0
                prev = smp[key]
            return round(j, 1)

        # Loss and throughput in the SAME window as the latency percentiles. Both are still
        # ESTIMATES from the client side: whole frames lost at the edges
        # of the window shrink the denominator, so this loss is a floor.
        # The exact figure comes from the campaign script, with the frame_packets_total
        # that the server says it handed to the kernel.
        w = self.measured
        frames_expected = w.frames_expected_n
        pkts_expected = frames_expected * (self.pkt_cnt or 1)
        loss = 0.0
        if pkts_expected:
            loss = max(0.0, 1 - w.rx_packets / pkts_expected) * 100

        # Throughput over the REQUESTED window (the time in which the session was alive and the
        # downlink should be arriving), not over the interval in which it
        # actually arrived.
        # 
        # Dividing by the observed interval hides the most serious failure this
        # test can have: a flow that DIES in the middle of the run shows nominal
        # throughput and zero loss, because the denominator shrinks with the
        # numerator. This is exactly what happened in the first run on the edge machine
        # -- the downlink of the remote path stopped at 33 s and the summary said
        # "6.34 Mbps, loss 0.000%".
        # 
        # dl_continuity_pct is the other side of the same figure: how much of the
        # requested window had traffic. Less than 100% is an interrupted flow, not packet
        # loss -- they are different things and need different numbers.
        nominal_window = max(0.0, (self.tx_span or wall_s) - a.warmup)
        dl_eff = max(1e-9, nominal_window or w.span_s or wall_s)
        ul_eff = max(1e-9, self.tx_span or wall_s)
        complete = len(self.samples)
        total_frames = complete + self.frames_partial
        return {
            "label": a.label,
            "server": a.server,
            "bind": a.bind,
            "duration_s": round(wall_s, 3),
            "ul_window_s": round(self.tx_span, 3),
            "warmup_s": a.warmup,
            "pose_hz": a.pose_hz,
            # Totals of the WHOLE RUN (including the warm-up).
            "frames_complete": complete,
            "frames_partial": self.frames_partial,
            # Total of the run, to match the frame_packets_total of the
            # server: the EXACT loss comes from this pair (the one of the client
            # alone is a floor, because it does not see a frame lost entirely).
            "dl_packets_rx_run": self.measurement.rx_packets,
            "frames_incomplete_pct": (
                round(self.frames_partial / total_frames * 100, 3)
                if total_frames else 0.0),
            # KPIs -- all from the MEASUREMENT WINDOW, the same window as the percentiles.
            "frames_in_stats": len(kept),
            "dl_packet_loss_pct": round(loss, 4),
            "dl_throughput_mbps": round(w.rx_bytes * 8 / dl_eff / 1e6, 3),
            # Fraction of the requested window with downlink. < 100% = the flow
            # was interrupted; packet loss does not see this, because a
            # server that STOPS emitting leaves no gap in the sequence.
            "dl_continuity_pct": round(min(100.0, w.span_s / dl_eff * 100), 2),
            "ul_packets_tx": self.tx_packets,
            "ul_pose_hz_real": round(self.tx_packets / ul_eff, 1),
            "ul_throughput_mbps": round(self.tx_bytes * 8 / ul_eff / 1e6, 3),
            # The counters from which the loss/throughput KPIs come. They are in a
            # block of their own so that it is not ambiguous what is window and what is
            # whole run -- mixing both at the same level is what
            # used to leave "frames_expected" and "frames_complete" with different
            # windows side by side.
            "window": {
                "start_s": a.warmup,
                "nominal_s": round(nominal_window, 3),
                "span_s": round(w.span_s, 3),
                "frames_expected": frames_expected,
                "dl_packets_rx": w.rx_packets,
                "dl_packets_expected": pkts_expected,
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
            # hold = time INSIDE the server (wait for the next render
            # instant + pacing window + render). It is reported because it is the
            # only way for the reader to check the decomposition m2p = net + hold
            # -- and to see how much of the m2p is a choice of the generator (the pacing) rather
            # than a property of the path.
            "hold_us": {
                "min": pct(hold, 0), "p50": pct(hold, 0.50),
                "p95": pct(hold, 0.95), "max": pct(hold, 1.0),
                "mean": round(sum(hold) / len(hold), 1) if hold else None,
            },
            "jitter_us": rfc3550("m2p_us"),
            "jitter_net_us": rfc3550("net_us"),
            # ------------------------------------------------ health of the measurement
            # Everything below answers "does this run hold?". None of it describes
            # the network: it describes whether the MEASURING TOOL kept up.
            "health": health,
        }

    def health(self, snmp0, ctx0, drift0, drops0):
        """Evidence that the run measured the network and not the client itself."""
        snmp1 = vrclock.udp_errors()
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
            # Packets that arrived and the kernel discarded due to a full queue of THIS
            # socket: loss of the client, not of the UPF path. The reliable source
            # is /proc (dl_sock_drops); the SO_RXQ_OVFL cmsg stays as a
            # confirmation, because it does not always come.
            "dl_sock_drops": (None if drops0 is None or drops1 is None
                              else drops1 - drops0),
            "dl_sock_overflow_pkts": self.measured.overflow if self.has_ovfl else None,
            "dl_sock_overflow_run": self.measurement.overflow if self.has_ovfl else None,
            # Of the whole netns -- in the tester pod, it includes nr-gnb and nr-ue.
            "udp_rcvbuf_errors": d("RcvbufErrors"),
            "udp_in_errors": d("InErrors"),
            # Times the scheduler took this process off the CPU without it asking.
            "ctxt_switches_involuntary": (
                None if ctx0 is None or ctx1 is None else ctx1 - ctx0),
            # How much CLOCK_REALTIME moved beyond the monotonic clock during the
            # run. A few ms = there was an NTP adjustment and the m2p samples
            # of that stretch are shifted.
            "clock_drift_us": round(((rt1 - rt0) - (mono1 - mono0)) / 1000.0, 1),
        }

    def flush_partials(self):
        """Frames that remained incomplete until the end of the run NEVER went
        through the pruning of the 64 and, without this, vanished from the accounting: the summary said
        'frames_partial: 0' in a test that lost packets from beginning to end."""
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
              f"pose={a.pose_hz} Hz for {a.duration}s "
              f"rcvbuf={self.rcvbuf // 1024} kB "
              f"kernel_timestamp={'yes' if self.ts_kernel else 'NO'}",
              file=sys.stderr)
        if self.rcvbuf < 4 << 20:
            print("WARNING: the kernel capped the requested rcvbuf (8 MB) to "
                  f"{self.rcvbuf // 1024} kB. Raise net.core.rmem_max ON THE NODE "
                  "-- it is a global sysctl, it does not exist per network namespace, and it cannot be "
                  "done from inside the pod.", file=sys.stderr)
        self.lport_real = self.sock.getsockname()[1]
        snmp0 = vrclock.udp_errors()
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
        time.sleep(0.5)             # drains the last frames in flight
        self.running = False
        rx.join(timeout=1.0)
        wall = time.perf_counter() - t0
        self.flush_partials()

        if a.csv:
            self.write_csv(a.csv)
            print(f"csv: {a.csv}", file=sys.stderr)
        s = self.summary(wall, self.health(snmp0, ctx0, drift0, drops0))
        out = json.dumps(s, indent=2)
        if a.json:
            with open(a.json, "w") as fh:
                fh.write(out + "\n")
        print(out)
        if not s["frames_complete"]:
            print("NO complete frame received -- check the route of the tunnel "
                  "and whether the server is reachable through the IP of the UE.",
                  file=sys.stderr)
            return 1
        ov = s["health"]["dl_sock_drops"] or s["health"]["dl_sock_overflow_pkts"]
        if ov:
            print(f"WARNING: the kernel dropped {ov} packets due to a full queue of THIS "
                  "socket. The loss of this run belongs to the client, not to the path "
                  "of the UPF -- the point does not measure the network.", file=sys.stderr)
        return 0


def envd(name, default, cast=str):
    v = os.environ.get(name)
    return cast(v) if v not in (None, "") else default


def parse_args(argv):
    p = argparse.ArgumentParser(description="VR client (UE side)")
    p.add_argument("--server", default=envd("VR_SERVER", "mec-app:9100"),
                   help="host:port of the vr-server (name of the Service mec-app or "
                        "remote-app, or an IP); resolved once at the start")
    p.add_argument("--bind", default=envd("VR_BIND", "0.0.0.0"),
                   help="IP of the UE (tunnel interface), so that the traffic leaves through the PDU session")
    p.add_argument("--lport", type=int, default=envd("VR_LPORT", 0, int))
    p.add_argument("--duration", type=float, default=envd("VR_DURATION", 60.0, float))
    p.add_argument("--warmup", type=float, default=envd("VR_WARMUP", 5.0, float),
                   help="initial seconds dropped from the summary (from ALL "
                        "metrics: latency, loss and throughput)")
    p.add_argument("--pose-hz", type=float, default=envd("VR_POSE_HZ", 250.0, float))
    p.add_argument("--pose-bytes", type=int, default=envd("VR_POSE_BYTES", 128, int))
    p.add_argument("--session", type=int, default=envd("VR_SESSION", 0, int))
    p.add_argument("--csv", default=envd("VR_CSV", ""))
    p.add_argument("--json", default=envd("VR_JSON", ""))
    p.add_argument("--label", default=envd("VR_LABEL", "run"))
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(Client(parse_args(sys.argv[1:])).run())
