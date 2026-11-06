#!/usr/bin/env python3
"""
vrclock -- KERNEL timestamps for vr_server and vr_client.

Why this exists: the latency measured here is in milliseconds, and a
timestamp taken in Python (after recvfrom returns) also carries the time the
process spent off the CPU. On a small machine that runs the whole core, both
UPFs, UERANSIM and the two generators, that time is NOT negligible -- and it
grows with the load, exactly where the measurement must be reliable. The
result would be a "network latency" that worsens when the CPU is busy, and
the analysis would blame the UPF for a delay caused by the scheduler.

SO_TIMESTAMPNS solves it: the kernel stamps the packet on reception and
delivers the stamp as ancillary data of recvmsg. What happens between the
stamp and Python no longer counts.

Consequence: the clock becomes CLOCK_REALTIME (the one the kernel uses for
software timestamps), no longer perf_counter. Since both ends of each
measurement are IN THE SAME process, no synchronization between machines is
involved -- but an NTP step in the middle of a run would corrupt the samples.
That is why clock_drift_us() exists: the run reports how much CLOCK_REALTIME
moved beyond the monotonic clock, and a step shows up there.

Without support (macOS, old kernel, exotic architecture) everything degrades
to a Python timestamp -- the constants below are those of
asm-generic/socket.h, valid on x86_64/arm64, and enable() only turns on what
the kernel accepts.
"""
import socket
import struct
import time

# asm-generic/socket.h -- x86_64, arm64, riscv. On mips/parisc/sparc/alpha the
# numbers differ; hence getattr() first and setsockopt inside try.
SO_TIMESTAMPNS = getattr(socket, "SO_TIMESTAMPNS", 35)
SCM_TIMESTAMPNS = SO_TIMESTAMPNS
SO_RXQ_OVFL = getattr(socket, "SO_RXQ_OVFL", 40)
SCM_RXQ_OVFL = SO_RXQ_OVFL

CLOCK_REALTIME = getattr(time, "CLOCK_REALTIME", 0)


def now_ns():
    """Clock of the MEASUREMENTS -- the same one the kernel uses for SO_TIMESTAMPNS."""
    return time.clock_gettime_ns(CLOCK_REALTIME)


def clock_drift_us():
    """(realtime_ns, monotonic_ns) to measure, between two points of a run, how
    much CLOCK_REALTIME moved beyond the monotonic clock. Zero = no NTP
    adjustment in between; a few milliseconds = the samples of that run are
    contaminated and the point does not hold."""
    return now_ns(), time.monotonic_ns()


def enable(sock, rxq_ovfl=True):
    """Turns on the kernel timestamp (and, optionally, the receive queue
    overflow counter) on the socket. Returns (has_timestamp, has_ovfl)."""
    ts = ovfl = False
    try:
        sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
        ts = True
    except OSError:
        pass
    if rxq_ovfl:
        try:
            sock.setsockopt(socket.SOL_SOCKET, SO_RXQ_OVFL, 1)
            ovfl = True
        except OSError:
            pass
    return ts, ovfl


def ancbufsize():
    """Room for the two cmsg (16 B timespec + 4 B u32)."""
    try:
        return socket.CMSG_SPACE(16) + socket.CMSG_SPACE(4)
    except AttributeError:
        return 128


def read_anc(ancdata):
    """Extracts (t_kernel_ns, overflow_counter) from the ancillary data of recvmsg.
    Returns None in each field that did not come."""
    t_ns = ovfl = None
    for level, kind_, datum in ancdata:
        if level != socket.SOL_SOCKET:
            continue
        if kind_ == SCM_TIMESTAMPNS:
            # struct timespec: 2 words of native size (16 B on 64 bits,
            # 8 B on 32 bits). The size of the data tells which one it is.
            if len(datum) >= 16:
                s, ns = struct.unpack_from("@qq", datum)
            elif len(datum) >= 8:
                s, ns = struct.unpack_from("@ii", datum)
            else:
                continue
            t_ns = s * 1_000_000_000 + ns
        elif kind_ == SCM_RXQ_OVFL and len(datum) >= 4:
            ovfl = struct.unpack_from("@I", datum)[0]
    return t_ns, ovfl


def rcvtimeo(sock, seconds):
    """Receive timeout BY THE KERNEL, instead of sock.settimeout().

    settimeout() puts the socket in the 'timeout' mode of CPython, which then
    calls poll() before each recvmsg -- one extra syscall per packet, exactly in
    the hottest loop. With SO_RCVTIMEO the socket stays blocking for CPython
    and the kernel returns EAGAIN by itself when the deadline expires, which
    arrives here as BlockingIOError."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                        struct.pack("@qq", int(seconds),
                                    int((seconds % 1) * 1e6)))
        return True
    except OSError:
        sock.settimeout(seconds)
        return False


def buffers(sock, requested):
    """Requests SO_RCVBUF/SO_SNDBUF and returns what the kernel ACTUALLY granted.

    The kernel caps the request at net.core.rmem_max / wmem_max (208 KB by
    default) without warning: asking for 8 MB and getting 416 KB is silent.
    Since these two sysctls are GLOBAL (not per network namespace), the node
    has to raise them -- it cannot be done from inside the pod. Returning the
    effective value lets the run summary show the cap instead of hiding it."""
    for opt in (socket.SO_RCVBUF, socket.SO_SNDBUF):
        try:
            sock.setsockopt(socket.SOL_SOCKET, opt, requested)
        except OSError:
            pass
    return (sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF))


def udp_errors():
    """UDP RcvbufErrors/InErrors from /proc/net/snmp -- of the whole NETWORK
    NAMESPACE, not only of this socket. In the tester pod this includes the
    sockets of nr-gnb and nr-ue, which share the netns: if the overflow is
    there, the loss happened in UERANSIM and not on the UPF path."""
    try:
        with open("/proc/net/snmp") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return {}
    head_line = None
    for line in lines:
        if line.startswith("Udp:"):
            fields = line.split()[1:]
            if head_line is None:
                head_line = fields
            else:
                return {k: int(v) for k, v in zip(head_line, fields)}
    return {}


def udp_drops(port_num):
    """Drops due to a full queue of THIS socket, read from the last column of
    /proc/net/udp (the one the kernel calls 'drops').

    It exists because the SO_RXQ_OVFL cmsg did not appear in the first run on
    the small machine, even with the option accepted by the kernel -- and a
    counter that "sometimes comes" cannot decide whether a measurement holds.
    Here the source is the socket itself in /proc, always available, and the
    port is the one bind() picked (sock.getsockname()[1]).

    Returns None if the line is not found; the caller takes the delta between
    two readings."""
    tgt = f":{port_num:04X}"
    try:
        with open("/proc/net/udp") as fh:
            next(fh, None)          # header
            for line in fh:
                fields = line.split()
                if len(fields) >= 13 and fields[1].endswith(tgt):
                    return int(fields[-1])
    except (OSError, ValueError):
        pass
    return None


def ctxt_switches():
    """INVOLUNTARY context switches of the process: how many times the
    scheduler took it off the CPU without it asking. If this number explodes
    during the run, the machine was contended and the measured latency
    includes CPU time."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("nonvoluntary_ctxt_switches:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None
