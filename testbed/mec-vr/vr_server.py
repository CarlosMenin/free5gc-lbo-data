#!/usr/bin/env python3
"""
vr-server -- MEC virtual reality application (server / edge side).

Generates the "VR-inspired bidirectional traffic profile" load of the initial
design: a heavy DOWNLINK flow (rendered media) closed in a loop with a light,
frequent UPLINK flow (pose/control of the headset).

    UE  --- POSE  (128 B @ 250 Hz, uplink)  --->  vr-server (MEC)
    UE  <-- FRAME (~12 kB @ 60 fps, downlink) --  vr-server (MEC)

Each FRAME carries back the timestamp of the LAST pose received, so the client
measures motion-to-photon with its own clock -- with no need to synchronize the
UE and the edge (there is no reliable NTP between the nodes of the testbed).

The server also reports, in each frame, how long the pose stayed inside it
(hold_us: wait for the next render instant + the render itself, whose cost is
given separately in render_us). With it, the client separates two metrics that
are often confused:

    motion-to-photon = network(UL) + hold + network(DL)
    network rtt      = motion-to-photon - hold

The first is the KPI of the application; the second is the one that changes
when the UPF moves from the core to the edge. Measuring both is what allows
saying *how much* of the QoE gain came from the local breakout.

TWO THINGS THAT CHANGED SO THAT THE LOAD COULD SCALE (read before comparing
with old results):

1. The frame leaves PACED within the period, in small bursts, and no longer as
   a single burst of all its packets. A frame of 50 Mbps at 60 fps is 87
   packets (~104 kB) that, in a burst, leave at the speed of the veth -- a few
   Gbps instantaneously. No queue of the path (receive queue of the client,
   sockets of nr-gnb/nr-ue) absorbs that, and what overflows becomes "loss"
   that is really a burst. Paced, the same frame needs a queue ~10x smaller.
   This is what unlocks higher loads. Cost: the hold of the last packet now
   includes the pacing window, so the m2p rises -- EQUALLY ON BOTH PATHS, and
   net_rtt (which subtracts the hold) does not change. Turn it off with
   --no-spread to reproduce the old behavior.

2. The reception timestamp of the pose comes from the KERNEL (SO_TIMESTAMPNS),
   no longer from Python. Without it, the time THIS process spends off the CPU
   entered the hold wrongly and leaked into the net_rtt of the client as if it
   were network -- an error that grows with the load, exactly where the
   measurement matters. See vrclock.py.

Prometheus metrics at /metrics (port 9101 by default). They include the pacing
error of the generator itself, the packets that the generator could NOT hand to
the socket and the effective size of the buffers -- if any of them moves, the
bottleneck is the server and not the network, and the measurement of that point
must be discarded.

Typical use (inside the MEC pod):
    python3 vr_server.py --bitrate-mbps 50 --fps 90

All parameters accept an environment variable (VR_BITRATE_MBPS, VR_FPS, ...),
to switch profiles with 'kubectl set env' without rebuilding anything.
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
    """Simple counters -- the Prometheus text format is trivial enough not to
    justify an external dependency in the image."""

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
        self.ts_kernel, _ = vrclock.enable(self.sock, rxq_ovfl=False)
        self.sock.bind((args.bind, args.port))
        vrclock.rcvtimeo(self.sock, 0.2)
        self.ancbuf = vrclock.ancbufsize()
        self.rxbuf = bytearray(2048)
        self.metrics.set("sock_rcvbuf_bytes", self.rcvbuf)
        self.metrics.set("sock_sndbuf_bytes", self.sndbuf)
        self.metrics.set("kernel_rx_timestamp", 1 if self.ts_kernel else 0)

        self.payload_size = args.mtu - FRAME_HDR.size
        if self.payload_size < 1:
            sys.exit(f"--mtu {args.mtu} smaller than the header ({FRAME_HDR.size} B)")
        if args.fps <= 0:
            sys.exit("--fps must be greater than zero")
        if args.bitrate_mbps <= 0:
            sys.exit("--bitrate-mbps must be greater than zero")
        frame_bytes = args.bitrate_mbps * 1e6 / 8.0 / args.fps
        self.pkt_cnt = max(1, math.ceil(frame_bytes / args.mtu))
        if self.pkt_cnt > 0xFFFF:
            sys.exit("frame too large: more than 65535 packets per frame")

        # Pacing: splits the frame into bursts of 'chunk' packets, one every
        # 'gap' seconds, covering pace_duty of the period. The chunk is NOT 1 on
        # purpose: with 174 packets in a period of 16.7 ms the interval between
        # packets would drop to 77 us, below what Linux time.sleep()
        # delivers, and the generator would overrun the period by overshoot --
        # trading the burst problem for a cadence problem. With chunks, the number
        # of waits is limited and each one stays above the floor of sleep.
        period = 1.0 / args.fps
        self.budget = period * args.pace_duty
        gap_min = max(1e-4, args.pace_min_gap_ms / 1000.0)
        slots = max(1, int(self.budget / gap_min))
        self.chunk = max(1, math.ceil(self.pkt_cnt / slots))
        self.n_chunks = math.ceil(self.pkt_cnt / self.chunk)
        self.gap = self.budget / self.n_chunks if self.n_chunks else 0.0
        pace = args.spread and self.n_chunks > 1
        self.metrics.set("pace_chunk_packets", self.chunk if pace else 0)
        # Goes to /metrics because it enters the m2p (inside the hold): the campaign
        # script records the value with the result, otherwise the inflation of the m2p
        # is left unexplained in the report.
        self.metrics.set("pace_window_seconds",
                         round(self.gap * (self.n_chunks - 1), 6) if pace else 0.0)

        # Single reused buffer: avoids allocating ~70 kB per frame.
        self.buf = bytearray(args.mtu)
        self.view = memoryview(self.buf)
        # Non-zero payload pattern (compressors/offloads do not like zeros).
        for i in range(FRAME_HDR.size, args.mtu):
            self.buf[i] = i & 0xFF

    # ------------------------------------------------------------------ RX
    def rx_loop(self):
        recv_into = self.sock.recvmsg_into
        seen_ = [memoryview(self.rxbuf)]
        while self.running:
            try:
                n, ancdata, _, addr = recv_into(seen_, self.ancbuf)
            except (BlockingIOError, socket.timeout):
                continue        # SO_RCVTIMEO expired: just re-read self.running
            except OSError:
                if self.running:
                    continue
                return
            if n < POSE_HDR.size:
                continue
            magic, sid, seq, t_ns, flags = POSE_HDR.unpack_from(self.rxbuf)
            if magic != POSE_MAGIC:
                continue

            # KERNEL timestamp: whatever this process takes between the arrival of the
            # packet and this line must not enter the hold, otherwise it leaves the m2p and
            # appears as if it were network in the net_rtt of the client.
            k_ns, _ = vrclock.read_anc(ancdata) if ancdata else (None, None)
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
                # SNAPSHOT of the state of each session, taken UNDER THE LOCK. Reading
                # s.seq/s.t_pose_ns/s.recv_ns inside send_frame would race
                # with rx_loop: hold_us would come from one pose and
                # t_pose_ns from another, and the net_us of the client (m2p - hold)
                # would be off by up to one pose interval -- the same order of
                # magnitude as the net_rtt to be measured.
                active = [(s, s.seq, s.t_pose_ns, s.recv_ns)
                          for s in self.sessions.values()]

            render_us = self.render(len(active)) if active else 0

            # With N sessions the pacing budget is split among them: there is
            # a single period and all of them must fit inside it.
            slice_ = self.budget / max(1, len(active))
            for s, seq, t_pose_ns, recv_ns in active:
                self.send_frame(s, seq, t_pose_ns, recv_ns, render_us, slice_)

            now = time.perf_counter()
            drift = next_t - now
            self.metrics.set("pacing_error_seconds", round(-drift, 6))
            if drift > 0:
                time.sleep(drift)
            else:
                self.metrics.add("frames_late_total")
                if drift < -5 * period:
                    # Large delay: re-anchors the clock instead of trying
                    # to recover frames that no longer make sense.
                    self.metrics.add("frames_reanchored_total")
                    next_t = now

    def send_frame(self, s, seq, t_pose_ns, recv_ns, render_us, budget):
        """seq/t_pose_ns/recv_ns come from the snapshot of tx_loop -- the three must
        describe THE SAME pose, otherwise the net_us of the client is wrong."""
        s.frame_seq += 1
        pace = self.args.spread and self.n_chunks > 1
        gap = budget / self.n_chunks if pace else 0.0
        t_ref = time.perf_counter()
        sent = 0
        for idx in range(self.pkt_cnt):
            if pace and idx % self.chunk == 0 and idx:
                tgt = t_ref + (idx // self.chunk) * gap
                wait_for = tgt - time.perf_counter()
                if wait_for > 0:
                    # ABSOLUTE deadline from t_ref: the overshoot of sleep
                    # does not accumulate along the frame, it only shortens the next
                    # wait.
                    time.sleep(wait_for)
            # hold recomputed FOR EACH packet: the packets of the same frame leave
            # at different instants and the client closes the m2p at the arrival of the
            # LAST one. With each packet carrying the time IT spent in here,
            # the client matches the m2p with the right hold; a single hold per
            # frame would put the server's own pacing inside the net_us, as
            # if it were network.
            hold_us = max(0, (vrclock.now_ns() - recv_ns) // 1000)
            FRAME_HDR.pack_into(
                self.buf, 0, FRAME_MAGIC, s.sid, s.frame_seq, idx,
                self.pkt_cnt, seq, t_pose_ns, int(hold_us),
                int(render_us), int(self.ai_us),
            )
            try:
                # MSG_DONTWAIT without changing the mode of the socket (rx_loop shares the
                # same socket and remains blocking). With a blocking socket a
                # full sndbuf would STOP the generator until it drained, and the symptom
                # would show up as a late frame, without saying that the origin was
                # here. This way the overflow becomes a counter -- and a packet that this
                # process never handed to the kernel cannot be counted as
                # network loss.
                self.sock.sendto(self.view, MSG_DONTWAIT, s.addr)
            except BlockingIOError:
                self.metrics.add("send_dropped_total", self.pkt_cnt - idx)
                break
            except OSError:
                self.metrics.add("send_errors_total")
                self.metrics.add("send_dropped_total", self.pkt_cnt - idx)
                break
            sent += 1
        self.metrics.add("frames_sent_total")
        self.metrics.add("frame_packets_total", sent)
        self.metrics.add("frame_bytes_total", sent * self.args.mtu)
        if sent < self.pkt_cnt:
            self.metrics.add("frames_truncated_total")

    def render(self, n_sessions):
        """Simulates the cost of rendering the frame. With --render-ms 0 it spends
        nothing; with a value > 0 it burns CPU on purpose, so that the edge node
        has a computational load comparable to that of a real render.

        --render-sleep replaces the burning by a sleep. It is the mode of the
        CALIBRATION (V1), not of the campaign. Burning CPU, this process holds
        the interpreter and the rx_loop thread falls behind: at the frame
        instant the server still has an older pose than the one that already
        arrived, and the hold -- measured against the ARRIVAL of that pose --
        grows MORE than the injected render. Measured on the ar-industrial
        profile: the hold rose 1.32 x the render instead of 1.00, and V1 failed
        because of it. Sleep frees the interpreter, rx_loop keeps up and the hold
        rises 1:1 -- which is the property that V1 wants to verify.

        Whoever wants CPU load at the edge keeps the burning (the default): sleep
        does not occupy any core."""
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
        """Hook for the AI-on-RAN application on the Jetson: fires inferences at
        a fixed rate and measures the response time. It is the "AI-on-RAN request
        rate" that the initial design lists as a load dimension. Off by default."""
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
              f"= {mbps:.1f} Mbps per session (target {a.bitrate_mbps} Mbps)",
              flush=True)
        if a.spread and self.n_chunks > 1:
            print(f"  pacing: {self.n_chunks} bursts of {self.chunk} pkt every "
                  f"{self.gap * 1e3:.2f} ms ({self.budget * 1e3:.1f} ms of "
                  f"{1e3 / a.fps:.1f} ms)", flush=True)
        else:
            print("  pacing: OFF -- the whole frame leaves in a single burst "
                  f"({self.pkt_cnt * a.mtu / 1e3:.1f} kB)", flush=True)
        print(f"  buffers: rcvbuf={self.rcvbuf // 1024} kB "
              f"sndbuf={self.sndbuf // 1024} kB "
              f"kernel_timestamp={'yes' if self.ts_kernel else 'NO'}", flush=True)
        if self.sndbuf < 4 << 20:
            print("  WARNING: the kernel capped the requested sndbuf (8 MB). Raise "
                  "net.core.wmem_max/rmem_max ON THE NODE -- they are global sysctls, not "
                  "per namespace, and it cannot be done from inside the pod.", flush=True)
        if not self.ts_kernel:
            print("  WARNING: no SO_TIMESTAMPNS. The hold is timestamped in "
                  "Python and includes the time this process spends off the CPU.",
                  flush=True)
        print(f"  render={a.render_ms} ms/frame/session "
              f"[{'sleep' if a.render_sleep else 'CPU burn'}] "
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
        description="Server of the MEC VR application (heavy downlink + closed loop)")
    p.add_argument("--bind", default=envd("VR_BIND", "0.0.0.0"))
    p.add_argument("--port", type=int, default=envd("VR_PORT", 9100, int))
    p.add_argument("--metrics-port", type=int,
                   default=envd("VR_METRICS_PORT", 9101, int))
    p.add_argument("--bitrate-mbps", type=float,
                   default=envd("VR_BITRATE_MBPS", 50.0, float),
                   help="downlink rate PER SESSION (default 50)")
    p.add_argument("--fps", type=int, default=envd("VR_FPS", 90, int))
    p.add_argument("--mtu", type=int, default=envd("VR_MTU", 1200, int),
                   help="UDP payload bytes per packet (default 1200, "
                        "below the MTU of the GTP-U tunnel)")
    p.add_argument("--render-ms", type=float,
                   default=envd("VR_RENDER_MS", 0.0, float),
                   help="CPU burned per frame/session, simulating the render")
    p.add_argument("--render-sleep", action=argparse.BooleanOptionalAction,
                   default=envd("VR_RENDER_SLEEP", "0") not in ("0", "false", ""),
                   help="injects --render-ms as a SLEEP instead of burning "
                        "CPU. It is the mode of the CALIBRATION (V1): sleeping, the "
                        "interpreter is free, rx_loop keeps up and the "
                        "hold rises 1:1 with the injected render. The campaign uses the "
                        "burning (default), which is what loads the edge node")
    p.add_argument("--spread", action=argparse.BooleanOptionalAction,
                   default=envd("VR_SPREAD", "1") not in ("0", "false", ""),
                   help="ON by default: spreads the packets of the frame over "
                        "the period, in bursts of --pace-chunk packets, "
                        "instead of sending the whole frame at once. "
                        "--no-spread returns to the old behavior (and again "
                        "loses frames at high load)")
    p.add_argument("--pace-duty", type=float,
                   default=envd("VR_PACE_DUTY", 0.8, float),
                   help="fraction of the frame period used to spread the "
                        "packets (default 0.8; the rest is slack so that the "
                        "generator itself does not overrun the cadence)")
    p.add_argument("--pace-min-gap-ms", type=float,
                   default=envd("VR_PACE_MIN_GAP_MS", 1.0, float),
                   help="minimum interval between bursts. Below it, Linux "
                        "time.sleep() errs by more than the requested "
                        "interval; the burst size is derived from this floor")
    p.add_argument("--session-timeout", type=float,
                   default=envd("VR_SESSION_TIMEOUT", 2.0, float))
    p.add_argument("--role", default=envd("VR_ROLE", "mec"),
                   help="label of the metrics: mec (edge) or remote (core)")
    p.add_argument("--profile", default=envd("VR_PROFILE", "heavy"))
    p.add_argument("--ai-url", default=envd("VR_AI_URL", ""),
                   help="endpoint of the AI-on-RAN application (Jetson); empty turns it off")
    p.add_argument("--ai-rate", type=float, default=envd("VR_AI_RATE", 10.0, float))
    p.add_argument("--ai-bytes", type=int, default=envd("VR_AI_BYTES", 4096, int))
    p.add_argument("--ai-timeout", type=float, default=envd("VR_AI_TIMEOUT", 2.0, float))
    return p.parse_args(argv)


if __name__ == "__main__":
    Server(parse_args(sys.argv[1:])).run()
