#!/usr/bin/env python3
"""
Gera o manifesto do mec-af (AF de Traffic Influence) com o codigo embutido.

O fonte vive so aqui (implementacoes/mec-af/mec_af.py); o YAML em
free5gc/mec/mec-af.yaml e' DERIVADO -- mesma convencao do vr-app. Depois de
mexer no .py, rode:

    python3 gen-manifest.py
    kubectl apply -f ../free5gc/mec/mec-af.yaml
    kubectl -n free5gc rollout restart deploy/mec-af
"""
import argparse
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = "mec_af.py"
OUT = "../free5gc/mec/mec-af.yaml"

TEMPLATE = """# GERADO por implementacoes/mec-af/gen-manifest.py -- NAO EDITAR A MAO.
# Fonte: implementacoes/mec-af/{source}
# checksum do fonte: {digest}
#
# mec-af: o Application Function (AF) do testbed. Resolve por DNS os servicos
# listados em SERVICES e mantem, para cada um, uma assinatura de Traffic
# Influence no NEF -- e' assim que o ClusterIP (dinamico) do servico MEC
# chega ao I-UPF como regra de Local Breakout, sem literal no ueRouting.yaml.
#
#   mec-app.<ns>.svc.cluster.local --DNS--> mec-af --Nnef_TrafficInfluence-->
#           NEF --> UDR --> PCF --> SMF (DNAI=mec) --PFCP--> I-UPF
#
# Sem ServiceAccount/Role/RoleBinding de proposito: o AF nao fala com a API do
# Kubernetes, so' com o CoreDNS -- a mesma fonte de verdade que o smfcfg ja'
# usa para achar os UPFs. Assim ele nao depende de permissao de RBAC.
#
# Depende de: nef (common/nef.yaml) e do DNAI "mec" declarado no I-UPF
# (scenario-b-dupf/smf.yaml). Estado em http://mec-af:8080/status.
apiVersion: v1
kind: ConfigMap
metadata:
  name: mec-af
  namespace: {ns}
  labels:
    app: mec-af
data:
  {source}: |
{code}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mec-af
  namespace: {ns}
  labels:
    app: mec-af
spec:
  replicas: 1
  # Recreate, nao RollingUpdate: o mec-af e' um controlador singleton e dois
  # deles no ar ao mesmo tempo disputam as mesmas assinaturas no NEF.
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: mec-af
  template:
    metadata:
      labels:
        app: mec-af
    spec:
      # MEC DOMAIN do EDGE NODE 1 (brix-porvir-01), junto do mec-app.
      #
      # O AF nao e' um NF do 5GC: ele e' a funcao de aplicacao do dominio MEC, e
      # e' por isso que fala com o core pelo NEF (Nnef_TrafficInfluence) e nao
      # direto com o PCF -- modelo de AF de terceiro, fora do dominio confiavel
      # do operador. Na Figura 3 do TG1 ele cai dentro da caixa "MEC Domain" do
      # Edge Node, e nao dentro do "Server Node (5G Core)"; deixa-lo no core
      # apagava essa fronteira.
      #
      # Nao mexe no plano de dados nem no que e' medido: o AF resolve DNS e faz
      # algumas chamadas HTTP na subida, depois so' mantem a assinatura viva. O
      # pedido de Traffic Influence atravessa o backhaul ate' o NEF, como manda
      # a arquitetura -- se essa chamada falhar, o sintoma aparece no passo 11
      # do teste como "LBO NAO ESTA ATIVO".
      #
      # nodetype: os brix sao 'computer', nao 'server' -- por isso o seletor sai.
      nodeSelector:
        kubernetes.io/arch: amd64
        kubernetes.io/hostname: brix-porvir-01
        #nodetype: server
      volumes:
        - name: code
          configMap:
            name: mec-af
      containers:
        - name: mec-af
          image: python:3.12-slim
          command: ["python3", "-u", "/opt/af/{source}"]
          env:
            - name: NS
              value: "{ns}"
            # Servicos de borda anunciados ao NEF. Nome curto vira
            # <nome>.<ns>.svc.cluster.local. O remote-app fica de FORA: ele e'
            # o contraponto da medicao e tem que continuar subindo ao PSA-UPF.
            - name: SERVICES
              value: "mec-app"
            - name: NEF_URL
              value: "http://nef.{ns}.svc.cluster.local:8000"
            # So' para apagar registros orfaos deixados por um NEF reiniciado.
            - name: UDR_URL
              value: "http://udr.{ns}.svc.cluster.local:8000"
            - name: AF_ID
              value: "af001"
            - name: DNN
              value: "internet"
            # As duas slices do smf.yaml do cenario B; o UE do tester usa 010203.
            - name: SNSSAIS
              value: "1:010203,1:112233"
            # Uniao dos pools do PSA-UPF (60.60.0.0/17 + 60.60.128.0/17).
            - name: UE_CIDR
              value: "60.60.0.0/16"
            # Tem que ser o mesmo dnaiList do I-UPF em scenario-b-dupf/smf.yaml.
            - name: DNAI
              value: "mec"
            - name: NOTIFY_URL
              value: "http://mec-af.{ns}.svc.cluster.local:8080/notify"
            # Sondagem do DNS. O ClusterIP so' muda quando o Service e'
            # recriado, entao 10s chega com folga antes de a campanha comecar.
            - name: POLL_S
              value: "10"
          ports:
            - name: http-8080
              protocol: TCP
              containerPort: 8080
          volumeMounts:
            - name: code
              mountPath: /opt/af
              readOnly: true
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: mec-af
  namespace: {ns}
  labels:
    app: mec-af
spec:
  selector:
    app: mec-af
  ports:
    - name: http-8080
      protocol: TCP
      port: 8080
      targetPort: 8080
"""


def build(ns):
    body = open(os.path.join(HERE, SOURCE)).read()
    digest = hashlib.sha256(body.encode()).hexdigest()[:16]
    code = "\n".join(("    " + l) if l.strip() else ""
                     for l in body.rstrip("\n").split("\n"))
    return TEMPLATE.format(ns=ns, source=SOURCE, digest=digest, code=code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace", default="free5gc")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    path = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
    with open(path, "w") as fh:
        fh.write(build(args.namespace))
    print(f"escrito {os.path.normpath(path)} (namespace {args.namespace})")


if __name__ == "__main__":
    main()
