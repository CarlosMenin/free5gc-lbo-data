#!/usr/bin/env python3
"""
Generates the ue-routing-info ConfigMap of Scenario B for N UEs.

The ULCL of free5GC applies only to the UEs listed explicitly in
ueRoutingInfo.<group>.members. Scaling the number of UEs in the experiment
requires regenerating this list.

The DESTINATION of the local breakout is not set here: it arrives at runtime
through Traffic Influence (mec-af -> NEF -> UDR -> PCF -> SMF), with the
ClusterIP that Kubernetes allocated to the MEC service. Use --dest only to
generate the static fallback (specificPath) when debugging without the NEF.

Usage:
    python3 scripts/gen_uerouting.py -n 50 > scenario-b-dupf/ue-routing.yaml
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
      description: UE routing - LBO via ULCL ({n} UEs)

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

SPECIFIC = """        # STATIC fallback (--dest). The normal path is Traffic Influence
        # through mec-af; with the NEF running, this rule is redundant.
        specificPath:
          - dest: {dest}
            path: [I-UPF]
"""


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-n", "--num-ue", type=int, default=5,
                   help="number of UEs in the ULCL group (default: 5)")
    p.add_argument("--imsi-base", default="208930000000000",
                   help="initial IMSI (default: 208930000000000)")
    p.add_argument("--dest", default=None,
                   help="static fallback: LBO destination in CIDR (current ClusterIP "
                        "of mec-app + /32). Omitted by default: the rule comes from mec-af")
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
