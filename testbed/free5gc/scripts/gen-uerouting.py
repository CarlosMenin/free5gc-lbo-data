#!/usr/bin/env python3
"""
Gera o ConfigMap ue-routing-info do cenario B para N UEs.

O ULCL do free5gc so se aplica a UEs listados explicitamente em
ueRoutingInfo.<grupo>.members. Escalar o numero de UEs no experimento
(uma das variaveis de carga do TG1) exige regerar essa lista.

O DESTINO do Local Breakout nao entra aqui: ele chega em runtime por Traffic
Influence (mec-af -> NEF -> UDR -> PCF -> SMF), com o ClusterIP que o k8s
alocou ao servico MEC. Use --dest so' para gerar o fallback estatico
(specificPath) ao depurar sem o NEF.

Uso:
    python3 scripts/gen-uerouting.py -n 50 > scenario-b-dupf/ue-routing.yaml
    kubectl apply -f scenario-b-dupf/ue-routing.yaml
    kubectl -n free5gc rollout restart deployment/free5gc-smf
"""
import argparse

TEMPLATE = """apiVersion: v1
kind: ConfigMap
metadata:
  name: ue-routing-info
  namespace: free5gc
data:
  ueRouting.yaml: |
    info:
      version: 1.0.7
      description: Roteamento de UE - LBO via ULCL ({n} UEs)

    ueRoutingInfo:
      UE1:
        members:
{members}
        topology:
          - A: gNB1
            B: I-UPF
          - A: I-UPF
            B: PSA-UPF
{specific}"""

SPECIFIC = """        # Fallback ESTATICO (--dest). O caminho normal e' o Traffic Influence
        # via mec-af; com o NEF no ar esta regra e' redundante.
        specificPath:
          - dest: {dest}
            path: [I-UPF]
"""


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-n", "--num-ue", type=int, default=5,
                   help="quantidade de UEs no grupo ULCL (default: 5)")
    p.add_argument("--imsi-base", default="208930000000000",
                   help="IMSI inicial (default: 208930000000000)")
    p.add_argument("--dest", default=None,
                   help="fallback estatico: destino do LBO em CIDR (ClusterIP atual "
                        "do mec-app + /32). Omitido por padrao: a regra vem do mec-af")
    args = p.parse_args()

    base = int(args.imsi_base)
    width = len(args.imsi_base)
    members = "\n".join(
        f"          - imsi-{str(base + i).zfill(width)}" for i in range(args.num_ue)
    )
    specific = SPECIFIC.format(dest=args.dest) if args.dest else ""
    print(TEMPLATE.format(n=args.num_ue, members=members, specific=specific), end="")


if __name__ == "__main__":
    main()
