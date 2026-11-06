#!/usr/bin/env python3
"""
mec-af -- Application Function (AF) of the testbed: local breakout with a DYNAMIC IP.

It resolves by DNS the MEC services listed in SERVICES and, for each one, keeps
a Traffic Influence subscription at the NEF of free5GC (TS 29.522,
/3gpp-traffic-influence/v1). The core does the rest:

    mec-app.free5gc.svc.cluster.local --DNS--> mec-af --POST/PUT/DELETE--> NEF
        NEF --PUT influenceData--> UDR --notifies per session--> PCF
        PCF --SmPolicyUpdateNotify--> SMF --PFCP Session Modification--> I-UPF
        I-UPF installs the PDR: SDF = ClusterIP of the service, route = DNAI "mec"

The IP of the MEC service becomes RUNTIME data: Kubernetes allocates whatever
it wants, the AF discovers it through CoreDNS and announces it, and the ULCL
branch appears both in PDU sessions already open and in new ones. No literal
ClusterIP in ueRouting.yaml, no SMF restart.

WHY DNS AND NOT THE KUBERNETES API
----------------------------------
The rest of the testbed already addresses itself by name (smfcfg points to the
UPFs at i-upf.free5gc.svc.cluster.local, the NFs find the NRF this way), so the
AF uses the same source of truth: the A record of a Service is exactly its
current ClusterIP. In exchange, this AF needs NO ServiceAccount, Role or
RoleBinding -- it does not talk to the cluster API, so it does not depend on
RBAC permissions that the testbed account may not have.

What is lost: discovering services by label, and reacting at the instant of a
change. Neither matters here. The list of edge services of the experiment is
known (it is in SERVICES) and the ClusterIP only changes when the Service is
recreated, which happens at deployment. With POLL_S seconds of polling, the new
rule arrives well before the campaign starts -- and, what matters here, it
ALSO reaches PDU sessions that are already open.

Two particularities of the free5GC NEF shape the design:

  * it keeps the subscriptions ONLY IN MEMORY, so a restarted NEF loses all of
    them. Since the listing returns the "self" field (with the id), this AF
    ADOPTS at each cycle what already exists under its AF_ID instead of
    recreating it. Without this, a campaign with --repetitions would accumulate
    a new subscription per round;
  * the corresponding record in the UDR gets a new UUID at each POST, so a NEF
    that restarts leaves orphan records there (with the same SDF). Each orphan
    becomes a duplicated PCC rule in every session. Hence the AF sweeps the UDR
    before (re)creating subscriptions and deletes what carries its signature
    (AnyUE + DNN + DNAI + SDF in the format used here). It is the only direct
    contact with the UDR; everything else goes through the NEF, as 3GPP specifies.

Standard library only: runs on python:3.12-slim with no pip and no credentials
mounted in the pod.

Environment variables (all with defaults for the testbed):
    NS          namespace, to build the FQDN           free5gc
    SERVICES    edge services, separated by ,          mec-app
                (a short name becomes <name>.<NS>.svc.cluster.local; an FQDN
                 or a literal IP are also accepted)
    NEF_URL     base of the NEF                        http://nef.free5gc.svc.cluster.local:8000
    UDR_URL     base of the UDR (only to clean orphans) http://udr.free5gc.svc.cluster.local:8000
                (the /nudr-dr/v2 or /v1 prefix is discovered at the first call)
    AF_ID       id of the AF in the NEF URL            af001
    DNN         DNN of the target sessions             internet
    SNSSAIS     list of sst:sd separated by commas     1:010203,1:112233
    UE_CIDR     pool of the UEs ("to" side of the SDF) 60.60.0.0/16
    DNAI        DNAI of the edge domain (smfcfg)       mec
    NOTIFY_URL  destination of the NEF notifications   http://mec-af.free5gc.svc.cluster.local:8080/notify
    POLL_S      DNS polling interval                   10
    HTTP_PORT   port of the notification server        8080
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
    """Short name -> FQDN of the Service. An FQDN or a literal IP pass unchanged."""
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
    """Current ClusterIP of the Service, or None if the name does not resolve.

    A normal Service has an A record with the ClusterIP. Not resolving means,
    in practice, that the Service does not exist (yet) -- which is the signal
    that the corresponding subscription must leave the NEF."""
    try:
        return socket.gethostbyname(fqdn)
    except socket.gaierror:
        return None


def http(method, url, body=None, timeout=15):
    """Returns (status, headers, body) without raising on 4xx/5xx."""
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
    """Client of the Nnef_TrafficInfluence API (TS 29.522 §5.4)."""

    def __init__(self):
        self.url = f"{CFG['nef_url']}/3gpp-traffic-influence/v1/{CFG['af_id']}/subscriptions"

    @staticmethod
    def sub_id(headers, body):
        loc = headers.get("Location")
        if not loc and isinstance(body, dict):
            loc = body.get("self")
        return loc.rstrip("/").rsplit("/", 1)[-1] if loc else None

    def alive(self):
        """ANY HTTP response means the NEF is up -- including 404.

        The AF only exists at the NEF once the FIRST subscription is created
        (PostTrafficInfluenceSubscription calls NewAf if it does not find it);
        until then the GET of the list answers 404 "AF is not found". Requiring
        200 here would wait for a condition that only the POST itself produces -- a deadlock."""
        try:
            http("GET", self.url)
            return True
        except OSError as e:      # connection refused, DNS, timeout
            log(f"NEF does not answer yet: {type(e).__name__}: {e}")
            return False

    def list(self):
        """(status, list). 404 = the AF does not exist yet, which is normal before
        the first POST and is equivalent to an empty list."""
        st, _, body = http("GET", self.url)
        return st, (body if isinstance(body, list) else [])

    def create(self, body):
        return http("POST", self.url, body)

    def update(self, sub_id, body):
        return http("PUT", f"{self.url}/{sub_id}", body)

    def delete(self, sub_id):
        return http("DELETE", f"{self.url}/{sub_id}")


# ------------------------------------------------------------------ UDR (cleanup only)
class Udr:
    """Direct access to the UDR ONLY to delete orphan records left by a
    restarted NEF. It never creates or changes anything here."""

    def __init__(self):
        self.url = None     # resolved at the first call: v2 (current) or v1 (guide)

    def _resolve(self):
        if self.url:
            return True
        for ver in ("v2", "v1"):
            url = f"{CFG['udr_url']}/nudr-dr/{ver}/application-data/influenceData"
            # A 200 is enough: with an empty query the UDR answers 200 with the body
            # "null" (not "[]"), so requiring a list here would only find the
            # right version once data had been written.
            if http("GET", f"{url}?dnns={urllib.parse.quote(CFG['dnn'])}")[0] == 200:
                self.url = url
                log(f"UDR: influenceData at {url}")
                return True
        log("UDR: no version of /nudr-dr answered 200; no sweep this time")
        return False

    def list_ours(self):
        """influenceData records with the signature of this AF: (id, ip, snssai)."""
        if not self._resolve():
            return None
        st, _, body = http("GET", f"{self.url}?dnns={urllib.parse.quote(CFG['dnn'])}")
        if st != 200:
            log(f"UDR GET influenceData -> {st}; no sweep")
            return None
        body = body or []       # body "null" = no record
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


# ------------------------------------------------------------------ rule
def flow_description(ip):
    # Same format as the official guide (free5gc.org/guide/8-traffic-influence):
    # "out" = downlink direction (server -> UE); the UPF applies it in both directions.
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


# ------------------------------------------------------------------ reconciliation
class Reconciler:
    """Keeps (service x S-NSSAI) -> subscription at the NEF with the current ClusterIP."""

    def __init__(self, nef, udr):
        self.nef, self.udr = nef, udr
        self.subs = {}          # (svc, snssai_key) -> {"id": str, "ip": str}
        self.lock = threading.Lock()

    def snapshot(self):
        with self.lock:
            return {f"{k[0]}/{k[1]}": dict(v) for k, v in self.subs.items()}

    # --- adoption: rebuilds the state from the NEF itself ----------
    def adopt(self):
        """Reads the subscriptions that exist under our AF_ID and takes control.

        Makes the restart of mec-af idempotent: if the right subscription is
        already there, nothing is created. The AF_ID is used only by this
        controller, so whatever is under it and does not match a service of
        SERVICES is left over from a previous execution and is removed."""
        st, subs = self.nef.list()
        if st == 404:
            self.subs = {}          # the AF does not exist yet: nothing to adopt
            return True
        if st != 200:
            log(f"NEF GET subscriptions -> {st}; keeping the current state")
            return False
        our_items = {n for n, _ in SERVICES}
        new, junk = {}, []
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
            if not sid or svc not in our_items or ip is None or key in new:
                junk.append(sid)
                continue
            new[key] = {"id": sid, "ip": ip}
        for sid in junk:
            if sid:
                log(f"NEF: deleting subscription {sid} without an owner (left from a previous "
                    f"anterior) -> {self.nef.delete(sid)[0]}")
        if new != self.subs:
            log(f"adopted {len(new)} subscription(s) from the NEF: "
                + (", ".join(f"{k[0]}[{k[1]}]=sub {v['id']}@{v['ip']}"
                             for k, v in sorted(new.items())) or "none"))
        self.subs = new
        return True

    # --- UDR: delete what does not match a live subscription ------
    def sweep_udr(self):
        ours = self.udr.list_ours()
        if ours is None:
            return
        alive_ = {(v["ip"], k[1]) for k, v in self.subs.items()}
        # A live subscription has exactly ONE record; any repeated one
        # (same ip+slice) is an orphan of a previous NEF. We keep only the last
        # one seen, which is the one the current NEF wrote last.
        seen = set()
        for iid, ip, sk in reversed(ours):
            key_name = (ip, sk)
            if key_name in alive_ and key_name not in seen:
                seen.add(key_name)
                continue
            st = self.udr.delete(iid)
            log(f"UDR: deleted influenceData {iid} ({ip} [{sk}]) orphan -> {st}")

    # --- ensure / remove -------------------------------------------
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
                log(f"{svc} [{sk}] PUT sub {cur['id']} -> {st}: {resp}; recreating")
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
            log(f"{svc} [{key[1]}] removed: DELETE sub {cur['id']} -> {st}")

    def tick(self, desired):
        """desired: {short_name: ip}. Called at each DNS poll."""
        with self.lock:
            # Adoption already covers a restarted NEF: the list comes back empty (or 404)
            # and the local state is reset with it, so everything is recreated.
            if not self.adopt():
                return
            lacking = {(s, sk) for s in desired for sk, _ in SNSSAIS} - set(self.subs)
            for svc in {k[0] for k in self.subs} - set(desired):
                self.remove(svc)
            if lacking:
                # Sweep the UDR BEFORE creating: the old record of the same IP
                # would be a duplicated PCC rule in each session. Only when there is
                # something to create, so as not to poll the UDR every 10 s for nothing.
                self.sweep_udr()
            for svc, ip in desired.items():
                self.ensure(svc, ip)

    # There is no shutdown() on purpose -- see the comment in term().


# ------------------------------------------------------------------ HTTP (notifications + state)
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
            # UpPathChange and similar (TS 29.522 EventNotification). We only log them.
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            log(f"NEF notification at {self.path}: {raw.decode(errors='replace')[:500]}")
            self._send(204)

    srv = ThreadingHTTPServer(("0.0.0.0", CFG["http_port"]), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"notification/state HTTP on :{CFG['http_port']} (/notify, /status, /healthz)")


# ------------------------------------------------------------------ main
def main():
    log("mec-af starting with " + json.dumps(CFG))
    if not SNSSAIS:
        sys.exit("SNSSAIS empty")
    if not SERVICES:
        sys.exit("SERVICES empty")
    log("watched services: " + ", ".join(f"{n} -> {f}" for n, f in SERVICES))

    nef, udr = Nef(), Udr()
    rec = Reconciler(nef, udr)
    http_server(rec)

    def term(signum, frame):
        # We do NOT delete the subscriptions on exit, for two reasons:
        #  1. the rollout of the Deployment overlaps the pods -- the new one has already adopted the
        #     subscriptions when the old one receives SIGTERM, and deleting here
        #     would remove exactly what the new one just took over (this happened
        #     once: the new pod recreated everything 20 s later);
        #  2. the AF is only the announcer. The value of the design is that the rule lives in
        #     the core on its own; restarting the announcer must not remove
        #     the LBO from PDU sessions that are running.
        # What is left over is collected by the adoption and by the UDR sweep at the
        # next boot.
        log("SIGTERM: exiting without touching the subscriptions (they survive the AF)")
        os._exit(0)
    signal.signal(signal.SIGTERM, term)
    signal.signal(signal.SIGINT, term)

    while not nef.alive():
        log(f"waiting for the NEF at {nef.url}")
        time.sleep(5)
    log(f"NEF up at {nef.url}")

    previous = None
    while True:
        try:
            desired = {}
            for name_str, fqdn in SERVICES:
                ip = resolve(fqdn)
                if ip:
                    desired[name_str] = ip
            if desired != previous:
                log("DNS: " + (", ".join(f"{n}={ip}" for n, ip in sorted(desired.items()))
                               or "no service resolves"))
                previous = desired
            rec.tick(desired)
        except Exception as e:            # noqa: BLE001 -- control loop
            log(f"error in the loop: {type(e).__name__}: {e}")
        time.sleep(CFG["poll_s"])


if __name__ == "__main__":
    main()
