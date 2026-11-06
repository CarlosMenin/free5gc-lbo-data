#!/usr/bin/env python3
"""
Validates the manifests BEFORE applying them to the cluster.

Checks the rules that free5GC v4.2.3 applies at runtime (taken from the
govalidator structs in smf/pkg/factory/config.go and
go-upf/pkg/factory/config.go) plus the consistency between files.

It catches the most expensive class of error: a syntactically valid config
that the NF rejects at boot, or a UPF name that does not match between smfcfg
and ueRouting -- these fail silently, with no PDU session, and are tedious to
trace in the logs.

Usage:
    python3 scripts/validate.py
"""
import glob
import ipaddress
import sys

import yaml

SMF_VERSIONS = {"1.0.7"}
SMF_UEROUTING_VERSIONS = {"1.0.7"}
UPF_VERSIONS = {"1.0.3"}
UDR_VERSIONS = {"1.1.0"}
WEBUI_VERSIONS = {"1.0.3"}


def load_docs(path):
    return [d for d in yaml.safe_load_all(open(path)) if d]


def configmaps(path):
    """Returns {'<configmap>/<key>': parsed_config} of the embedded YAML."""
    out = {}
    for d in load_docs(path):
        if d.get("kind") == "ConfigMap":
            for key, raw in (d.get("data") or {}).items():
                if key.endswith((".yaml", ".yml")):
                    out[f"{d['metadata']['name']}/{key}"] = yaml.safe_load(raw)
    return out


def configmaps_text(path):
    """Like configmaps(), but with every scalar as a STRING (BaseLoader). To
    compare slices: safe_load reads 'sd: 010203' as octal (4227) and
    'sd: 112233' as decimal, and the hex of the S-NSSAI is lost."""
    out = {}
    for d in load_docs(path):
        if d.get("kind") == "ConfigMap":
            for key, raw in (d.get("data") or {}).items():
                if key.endswith((".yaml", ".yml")):
                    out[f"{d['metadata']['name']}/{key}"] = yaml.load(raw, Loader=yaml.BaseLoader)
    return out


def slice_(sst, sd):
    """Normalized S-NSSAI: (1, '010203'). Accepts '0x112233' (UERANSIM),
    '112233' (smfcfg) and '010203'."""
    sst, sd = str(sst).strip().lower(), str(sd or "").strip().lower()
    sst = int(sst, 16) if sst.startswith("0x") else int(sst)
    sd = f"{int(sd, 16):06x}" if sd.startswith("0x") else sd.zfill(6)
    return sst, sd


def check_smf(path, conf, errors):
    c = conf["configuration"]
    version = str(conf["info"]["version"])
    if version not in SMF_VERSIONS:
        errors.append(f"{path}: smf info.version={version}, expected {SMF_VERSIONS}")

    for name, node in c["userplaneInformation"]["upNodes"].items():
        if node["type"] not in ("AN", "UPF"):
            errors.append(f"{path}: upNode {name} type='{node['type']}' (use AN or UPF)")
        for iface in node.get("interfaces", []):
            if iface["interfaceType"] not in ("N3", "N9"):
                errors.append(f"{path}: {name} interfaceType invalid")
            for endpoint in iface["endpoints"]:
                if endpoint == "0.0.0.0":
                    errors.append(
                        f"{path}: {name} has endpoint 0.0.0.0; this address goes "
                        "into the F-TEID given to the gNB and must be routable"
                    )

    metrics = c.get("metrics")
    if metrics:
        if "scheme" not in metrics:
            errors.append(f"{path}: metrics requires 'scheme'")
        if (metrics.get("port") == c["sbi"]["port"]
                and metrics.get("bindingIPv4") == c["sbi"]["bindingIPv4"]):
            errors.append(f"{path}: metrics and sbi on the same IP:port; the SMF refuses to start")


def check_upf(path, conf, errors, warnings):
    version = str(conf["version"])
    if version not in UPF_VERSIONS:
        errors.append(f"{path}: upf version={version}, expected {UPF_VERSIONS}")
    if conf["pfcp"]["addr"] == "0.0.0.0":
        errors.append(f"{path}: pfcp.addr cannot be 0.0.0.0")
    if conf["gtpu"]["forwarder"] != "gtp5g":
        errors.append(f"{path}: gtpu.forwarder must be gtp5g")
    for iface in conf["gtpu"]["ifList"]:
        if iface["type"] not in ("N3", "N9"):
            errors.append(f"{path}: gtpu.ifList type invalid")
    if len(conf["gtpu"]["ifList"]) > 1:
        warnings.append(
            f"{path}: gtpu.ifList has {len(conf['gtpu']['ifList'])} entries, but "
            "go-upf only uses the first one (driver.go breaks); prefer 0.0.0.0"
        )


def check_scenario_b(errors):
    maps = configmaps("scenario-b-dupf/smf.yaml")
    smf = next(v for k, v in maps.items() if "smfConfig" in k)["configuration"]
    routing = next(v for k, v in maps.items() if "ueRouting" in k)

    if not smf.get("ulcl"):
        errors.append("scenario B: 'ulcl: true' missing; ueRouting would be ignored entirely")

    nodes = set(smf["userplaneInformation"]["upNodes"])
    for group, info in routing["ueRoutingInfo"].items():
        for link in info["topology"]:
            for side in (link["A"], link["B"]):
                if side not in nodes:
                    errors.append(
                        f"ueRouting[{group}]: node '{side}' does not exist in upNodes {sorted(nodes)}"
                    )
        for spec in info.get("specificPath", []):
            try:
                ipaddress.ip_network(spec["dest"], strict=False)
            except ValueError as exc:
                errors.append(f"ueRouting[{group}]: dest '{spec['dest']}' invalid ({exc})")
            for hop in spec["path"]:
                if hop not in nodes:
                    errors.append(f"ueRouting[{group}]: path '{hop}' does not exist in upNodes")

    # Dynamic LBO: the destination is no longer in ueRouting -- it arrives through Traffic
    # Influence. What must match: every name in SERVICES exists as a Service
    # (mec-af resolves it by DNS), none of them fixes a ClusterIP, and some UPF
    # declares the announced DNAI.
    services = {
        d["metadata"]["name"]: d
        for d in load_docs("mec/mec-service.yaml") if d.get("kind") == "Service"
    }
    af = next(
        d for d in load_docs("mec/mec-af.yaml")
        if d.get("kind") == "Deployment" and d["metadata"]["name"] == "mec-af"
    )
    af_env = {e["name"]: e.get("value")
              for e in af["spec"]["template"]["spec"]["containers"][0]["env"]}
    dnais = {
        dnai
        for n in smf["userplaneInformation"]["upNodes"].values() if n["type"] == "UPF"
        for s in n.get("sNssaiUpfInfos", [])
        for d in s.get("dnnUpfInfoList", [])
        for dnai in d.get("dnaiList", [])
    }
    if af_env.get("DNAI") not in dnais:
        errors.append(
            f"mec-af announces DNAI '{af_env.get('DNAI')}' but no UPF of smf.yaml declares it "
            f"in dnaiList ({sorted(dnais)}); the SMF would have nowhere to divert to"
        )
    announced = [s.strip() for s in (af_env.get("SERVICES") or "").split(",") if s.strip()]
    if not announced:
        errors.append("mec-af without SERVICES: no service would be announced to the NEF")
    for name_str in announced:
        short = name_str.split(".")[0]
        if short not in services:
            errors.append(
                f"mec-af announces '{name_str}' but there is no Service '{short}' in "
                f"mec-service.yaml ({sorted(services)}); DNS would not resolve it"
            )
        elif "clusterIP" in services[short]["spec"]:
            errors.append(
                f"{short}: fixed clusterIP in the manifest; the dynamic LBO does not need it "
                "and it collides if the cluster already allocated that IP"
            )
    if "remote-app" in [n.split(".")[0] for n in announced]:
        errors.append("mec-af announces remote-app; it is the counterpoint of the measurement and "
                      "must keep going up to the PSA-UPF")
    # Each announced slice needs a UPF with the DNAI IN IT. Without it, the SMF finds
    # no path for the PCC rule and ApplyPccRules of the sessions of that slice
    # fails -- and the gen_manifest.py of mec-af still carries 112233 (the background one).
    smf_txt = next(v for k, v in configmaps_text("scenario-b-dupf/smf.yaml").items()
                   if "smfConfig" in k)["configuration"]
    for item in (af_env.get("SNSSAIS") or "").split(","):
        sst, _, sd = item.strip().partition(":")
        if not sst:
            continue
        tgt = slice_(sst, sd)
        with_dnai = [
            name_str for name_str, n in smf_txt["userplaneInformation"]["upNodes"].items()
            if n["type"] == "UPF"
            for s in n.get("sNssaiUpfInfos", [])
            if slice_(s["sNssai"]["sst"], s["sNssai"].get("sd")) == tgt
            for d in s.get("dnnUpfInfoList", [])
            if af_env.get("DNAI") in d.get("dnaiList", [])
        ]
        if not with_dnai:
            errors.append(
                f"mec-af announces slice {tgt[0]}:{tgt[1]}, but no UPF of the smf.yaml of B "
                f"has DNAI '{af_env.get('DNAI')}' in it; the breakout PCC rule would have no "
                "path (does the gen_manifest.py of mec-af still carry 112233?)")

    check_background(smf_txt, routing, errors)

    # nodeID declared in the SMF x nodeID that the UPF itself announces through PFCP
    declared = {
        n["nodeID"] for n in smf["userplaneInformation"]["upNodes"].values()
        if n["type"] == "UPF"
    }
    for path in ("scenario-b-dupf/i-upf.yaml", "scenario-b-dupf/psa-upf.yaml"):
        for key, conf in configmaps(path).items():
            if "upfConfig" in key:
                if conf["pfcp"]["nodeID"] not in declared:
                    errors.append(
                        f"{path}: nodeID '{conf['pfcp']['nodeID']}' is not in the SMF "
                        f"{sorted(declared)}; the PFCP association never completes"
                    )


def check_background(smf, routing, errors):
    """UE of the background traffic (background/background-gtp.yaml): in Scenario B
    it must be anchored at the PSA-UPF WITHOUT going through the I-UPF. What
    decides is its slice -- the SMF skips a UPF that does not serve the slice --
    plus a gNB -> PSA-UPF link that comes AFTER gNB -> I-UPF (otherwise the
    slice of the experiment would also skip the I-UPF). All of this fails
    silently: the background would go through the edge."""
    try:
        maps = configmaps_text("background/background-gtp.yaml")
    except FileNotFoundError:
        return
    ue = next((v for k, v in maps.items() if k.endswith("/ue.yaml")), None)
    if not ue:
        return
    supi = ue["supi"]
    tgt = slice_(ue["sessions"][0]["slice"]["sst"], ue["sessions"][0]["slice"]["sd"])
    nodes = smf["userplaneInformation"]["upNodes"]

    def serves(name_str):
        return any(slice_(s["sNssai"]["sst"], s["sNssai"].get("sd")) == tgt
                   for s in nodes.get(name_str, {}).get("sNssaiUpfInfos", []))

    if serves("I-UPF"):
        errors.append(f"background: the I-UPF serves slice {tgt[0]}:{tgt[1]} of the background UE; the "
                      "background would go through the Edge Node instead of descending directly from the PSA-UPF")
    if not serves("PSA-UPF"):
        errors.append(f"background: the PSA-UPF does not serve slice {tgt[0]}:{tgt[1]}; the session of the "
                      "background UE would have no anchor in Scenario B")
    if not any(i["interfaceType"] == "N3" for i in nodes.get("PSA-UPF", {}).get("interfaces", [])):
        errors.append("background: the PSA-UPF has no N3 interface; the SMF has no F-TEID to "
                      "give to the background gNB and the session does not complete")
    links = [(l["A"], l["B"]) for l in smf["userplaneInformation"]["links"]]
    idx = {}
    for i, pair in enumerate(links):
        idx.setdefault(pair, i)          # what counts is the FIRST occurrence
    direct, edge = idx.get(("gNB1", "PSA-UPF")), idx.get(("gNB1", "I-UPF"))
    if direct is None:
        errors.append("background: link gNB1 -> PSA-UPF is missing; without it the background UE "
                      "has no path in Scenario B")
    elif edge is not None and direct < edge:
        errors.append("background: link gNB1 -> PSA-UPF comes BEFORE gNB1 -> I-UPF; the SMF "
                      "walks the list in order and the slice of the experiment would lose the I-UPF")
    for grp, info in routing["ueRoutingInfo"].items():
        if supi in (info.get("members") or []):
            errors.append(f"background: {supi} is in ULCL group {grp}; it must not "
                          "receive the treatment of the experiment")


def main():
    errors, warnings = [], []

    for path in sorted(glob.glob("**/*.yaml", recursive=True)):
        try:
            for key, conf in configmaps(path).items():
                if "smfConfig" in key:
                    check_smf(path, conf, errors)
                elif "upfConfig" in key:
                    check_upf(path, conf, errors, warnings)
                elif "udrConfig" in key and str(conf["info"]["version"]) not in UDR_VERSIONS:
                    errors.append(f"{path}: udr info.version must be {UDR_VERSIONS} in v4.2.3")
                elif "webuiConfig" in key and str(conf["info"]["version"]) not in WEBUI_VERSIONS:
                    errors.append(f"{path}: webui info.version must be {WEBUI_VERSIONS} in v4.2.3")
        except (yaml.YAMLError, KeyError, TypeError) as exc:
            errors.append(f"{path}: failed to parse ({exc})")

    check_scenario_b(errors)

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR  : {e}")

    if errors:
        print(f"\n{len(errors)} problem(s) found.")
        return 1
    print("\nManifests consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
