#!/usr/bin/env python3
"""
Gera o ConfigMap 'vr-app' com os scripts da aplicacao VR para um namespace.

Os fontes vivem so aqui (implementacoes/mec-vr/); os YAML em
<core>/mec/vr-app.yaml sao DERIVADOS -- editar o YAML na mao e' garantia de
divergencia entre os dois testbeds. Depois de mexer nos .py, rode:

    python3 gen-configmap.py --all

Uso avulso:
    python3 gen-configmap.py --namespace free5gc --out ../free5gc/mec/vr-app.yaml
"""
import argparse
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = ["vrclock.py", "vr_server.py", "vr_client.py"]
TARGETS = [("free5gc", "../free5gc/mec/vr-app.yaml"),
           ("cemenin", "../open5gs/mec/vr-app.yaml")]

HEADER = """# GERADO por implementacoes/mec-vr/gen-configmap.py -- NAO EDITAR A MAO.
# Fonte: implementacoes/mec-vr/{sources}
# checksum dos fontes: {digest}
#
# Scripts da aplicacao VR (carga "VR-inspired" do TG1) montados em /opt/vr:
#   vr_server.py  roda no mec-app (borda) e no remote-app (nucleo)
#   vr_client.py  roda no pod do tester UERANSIM, pelo IP do tunel do UE
#   vrclock.py    modulo comum aos dois: carimbo de tempo do kernel
#
# O 'import vrclock' funciona porque os tres caem no MESMO diretorio (/opt/vr)
# e o Python poe o diretorio do script no sys.path.
#
# Sao montados como ConfigMap de proposito: nao exige registry nem build de
# imagem, e trocar o codigo e' 'kubectl apply' + restart do pod.
apiVersion: v1
kind: ConfigMap
metadata:
  name: vr-app
  namespace: {ns}
  labels:
    app: vr-app
data:
"""


def build(ns):
    blobs = []
    digest = hashlib.sha256()
    for name in SOURCES:
        body = open(os.path.join(HERE, name)).read()
        digest.update(body.encode())
        indented = "\n".join(("    " + l) if l.strip() else ""
                             for l in body.rstrip("\n").split("\n"))
        blobs.append(f"  {name}: |\n{indented}\n")
    head = HEADER.format(ns=ns, sources=" ".join(SOURCES),
                         digest=digest.hexdigest()[:16])
    return head + "".join(blobs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace")
    ap.add_argument("--out")
    ap.add_argument("--all", action="store_true",
                    help="regenera os dois testbeds (free5gc e open5gs)")
    args = ap.parse_args()

    jobs = TARGETS if args.all else [(args.namespace, args.out)]
    if not args.all and not (args.namespace and args.out):
        ap.error("use --all ou (--namespace e --out)")

    for ns, out in jobs:
        path = out if os.path.isabs(out) else os.path.join(HERE, out)
        with open(path, "w") as fh:
            fh.write(build(ns))
        print(f"escrito {os.path.normpath(path)} (namespace {ns})")


if __name__ == "__main__":
    main()
