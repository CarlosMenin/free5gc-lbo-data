#!/usr/bin/env python3
"""
Valida os manifestos ANTES de aplicar no cluster.

Checa as regras que o free5gc v4.2.3 aplica em tempo de execucao (extraidas
dos structs govalidator em smf/pkg/factory/config.go e
go-upf/pkg/factory/config.go) mais a consistencia entre arquivos.

Pega a classe de erro que custa mais caro: config sintaticamente valido que o
NF rejeita no boot, ou nome de UPF que nao casa entre smfcfg e ueRouting --
esses falham silenciosamente, sem sessao PDU, e sao chatos de rastrear no log.

Uso:
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
    """Retorna {'<configmap>/<chave>': config_parseado} dos YAML embutidos."""
    out = {}
    for d in load_docs(path):
        if d.get("kind") == "ConfigMap":
            for key, raw in (d.get("data") or {}).items():
                if key.endswith((".yaml", ".yml")):
                    out[f"{d['metadata']['name']}/{key}"] = yaml.safe_load(raw)
    return out


def configmaps_texto(path):
    """Como configmaps(), mas com todo escalar como STRING (BaseLoader). Para
    comparar fatias: o safe_load le 'sd: 010203' como octal (4227) e
    'sd: 112233' como decimal, e o hex do S-NSSAI se perde."""
    out = {}
    for d in load_docs(path):
        if d.get("kind") == "ConfigMap":
            for key, raw in (d.get("data") or {}).items():
                if key.endswith((".yaml", ".yml")):
                    out[f"{d['metadata']['name']}/{key}"] = yaml.load(raw, Loader=yaml.BaseLoader)
    return out


def fatia(sst, sd):
    """S-NSSAI normalizado: (1, '010203'). Aceita '0x112233' (UERANSIM),
    '112233' (smfcfg) e '010203'."""
    sst, sd = str(sst).strip().lower(), str(sd or "").strip().lower()
    sst = int(sst, 16) if sst.startswith("0x") else int(sst)
    sd = f"{int(sd, 16):06x}" if sd.startswith("0x") else sd.zfill(6)
    return sst, sd


def check_smf(path, conf, errors):
    c = conf["configuration"]
    version = str(conf["info"]["version"])
    if version not in SMF_VERSIONS:
        errors.append(f"{path}: smf info.version={version}, esperado {SMF_VERSIONS}")

    for name, node in c["userplaneInformation"]["upNodes"].items():
        if node["type"] not in ("AN", "UPF"):
            errors.append(f"{path}: upNode {name} type='{node['type']}' (use AN ou UPF)")
        for iface in node.get("interfaces", []):
            if iface["interfaceType"] not in ("N3", "N9"):
                errors.append(f"{path}: {name} interfaceType invalido")
            for endpoint in iface["endpoints"]:
                if endpoint == "0.0.0.0":
                    errors.append(
                        f"{path}: {name} tem endpoint 0.0.0.0; este endereco vai "
                        "no F-TEID entregue ao gNB e precisa ser roteavel"
                    )

    metrics = c.get("metrics")
    if metrics:
        if "scheme" not in metrics:
            errors.append(f"{path}: metrics exige 'scheme'")
        if (metrics.get("port") == c["sbi"]["port"]
                and metrics.get("bindingIPv4") == c["sbi"]["bindingIPv4"]):
            errors.append(f"{path}: metrics e sbi no mesmo IP:porta; o SMF recusa subir")


def check_upf(path, conf, errors, warnings):
    version = str(conf["version"])
    if version not in UPF_VERSIONS:
        errors.append(f"{path}: upf version={version}, esperado {UPF_VERSIONS}")
    if conf["pfcp"]["addr"] == "0.0.0.0":
        errors.append(f"{path}: pfcp.addr nao pode ser 0.0.0.0")
    if conf["gtpu"]["forwarder"] != "gtp5g":
        errors.append(f"{path}: gtpu.forwarder deve ser gtp5g")
    for iface in conf["gtpu"]["ifList"]:
        if iface["type"] not in ("N3", "N9"):
            errors.append(f"{path}: gtpu.ifList type invalido")
    if len(conf["gtpu"]["ifList"]) > 1:
        warnings.append(
            f"{path}: gtpu.ifList tem {len(conf['gtpu']['ifList'])} entradas, mas o "
            "go-upf so usa a primeira (driver.go faz break); prefira 0.0.0.0"
        )


def check_scenario_b(errors):
    maps = configmaps("scenario-b-dupf/smf.yaml")
    smf = next(v for k, v in maps.items() if "smfConfig" in k)["configuration"]
    routing = next(v for k, v in maps.items() if "ueRouting" in k)

    if not smf.get("ulcl"):
        errors.append("cenario B: 'ulcl: true' ausente; o ueRouting seria ignorado por inteiro")

    nodes = set(smf["userplaneInformation"]["upNodes"])
    for group, info in routing["ueRoutingInfo"].items():
        for link in info["topology"]:
            for side in (link["A"], link["B"]):
                if side not in nodes:
                    errors.append(
                        f"ueRouting[{group}]: no '{side}' nao existe em upNodes {sorted(nodes)}"
                    )
        for spec in info.get("specificPath", []):
            try:
                ipaddress.ip_network(spec["dest"], strict=False)
            except ValueError as exc:
                errors.append(f"ueRouting[{group}]: dest '{spec['dest']}' invalido ({exc})")
            for hop in spec["path"]:
                if hop not in nodes:
                    errors.append(f"ueRouting[{group}]: path '{hop}' nao existe em upNodes")

    # LBO dinamico: o destino nao fica mais no ueRouting -- chega por Traffic
    # Influence. O que precisa bater: todo nome em SERVICES existe como Service
    # (o mec-af o resolve por DNS), nenhum deles fixa ClusterIP, e algum UPF
    # declara o DNAI anunciado.
    servicos = {
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
            f"mec-af anuncia DNAI '{af_env.get('DNAI')}' mas nenhum UPF do smf.yaml o declara "
            f"em dnaiList ({sorted(dnais)}); o SMF nao teria para onde desviar"
        )
    anunciados = [s.strip() for s in (af_env.get("SERVICES") or "").split(",") if s.strip()]
    if not anunciados:
        errors.append("mec-af sem SERVICES: nenhum servico seria anunciado ao NEF")
    for nome in anunciados:
        curto = nome.split(".")[0]
        if curto not in servicos:
            errors.append(
                f"mec-af anuncia '{nome}' mas nao existe Service '{curto}' em "
                f"mec-service.yaml ({sorted(servicos)}); o DNS nao resolveria"
            )
        elif "clusterIP" in servicos[curto]["spec"]:
            errors.append(
                f"{curto}: clusterIP fixo no manifesto; o LBO dinamico nao precisa dele "
                "e ele colide se o cluster ja' alocou esse IP"
            )
    if "remote-app" in [n.split(".")[0] for n in anunciados]:
        errors.append("mec-af anuncia o remote-app; ele e' o contraponto da medicao e "
                      "precisa continuar subindo ate' o PSA-UPF")
    # Cada fatia anunciada precisa de um UPF com o DNAI NELA. Sem isso o SMF nao
    # acha caminho para a PCC rule e o ApplyPccRules das sessoes daquela fatia
    # falha -- e o gen-manifest.py do mec-af ainda traz a 112233 (a do ruido).
    smf_txt = next(v for k, v in configmaps_texto("scenario-b-dupf/smf.yaml").items()
                   if "smfConfig" in k)["configuration"]
    for item in (af_env.get("SNSSAIS") or "").split(","):
        sst, _, sd = item.strip().partition(":")
        if not sst:
            continue
        alvo = fatia(sst, sd)
        com_dnai = [
            nome for nome, n in smf_txt["userplaneInformation"]["upNodes"].items()
            if n["type"] == "UPF"
            for s in n.get("sNssaiUpfInfos", [])
            if fatia(s["sNssai"]["sst"], s["sNssai"].get("sd")) == alvo
            for d in s.get("dnnUpfInfoList", [])
            if af_env.get("DNAI") in d.get("dnaiList", [])
        ]
        if not com_dnai:
            errors.append(
                f"mec-af anuncia a fatia {alvo[0]}:{alvo[1]}, mas nenhum UPF do smf.yaml do B "
                f"tem o DNAI '{af_env.get('DNAI')}' nela; a PCC rule de breakout nao teria "
                "caminho (o gen-manifest.py do mec-af ainda traz a 112233?)")

    check_ruido(smf_txt, routing, errors)

    # nodeID declarado no SMF x nodeID que o proprio UPF anuncia via PFCP
    declared = {
        n["nodeID"] for n in smf["userplaneInformation"]["upNodes"].values()
        if n["type"] == "UPF"
    }
    for path in ("scenario-b-dupf/i-upf.yaml", "scenario-b-dupf/psa-upf.yaml"):
        for key, conf in configmaps(path).items():
            if "upfConfig" in key:
                if conf["pfcp"]["nodeID"] not in declared:
                    errors.append(
                        f"{path}: nodeID '{conf['pfcp']['nodeID']}' nao consta no SMF "
                        f"{sorted(declared)}; a associacao PFCP nunca fecha"
                    )


def check_ruido(smf, routing, errors):
    """UE de trafego de fundo (congestao/ruido-gtp.yaml): no cenario B ele tem
    que ancorar no PSA-UPF SEM passar pelo I-UPF. Quem decide e' a fatia dele
    -- o SMF pula UPF que nao atende a fatia -- mais um link gNB -> PSA-UPF que
    venha DEPOIS do gNB -> I-UPF (senao a fatia do experimento tambem pularia o
    I-UPF). Tudo isso falha calado: o ruido passaria pela borda."""
    try:
        maps = configmaps_texto("congestao/ruido-gtp.yaml")
    except FileNotFoundError:
        return
    ue = next((v for k, v in maps.items() if k.endswith("/ue.yaml")), None)
    if not ue:
        return
    supi = ue["supi"]
    alvo = fatia(ue["sessions"][0]["slice"]["sst"], ue["sessions"][0]["slice"]["sd"])
    nodes = smf["userplaneInformation"]["upNodes"]

    def atende(nome):
        return any(fatia(s["sNssai"]["sst"], s["sNssai"].get("sd")) == alvo
                   for s in nodes.get(nome, {}).get("sNssaiUpfInfos", []))

    if atende("I-UPF"):
        errors.append(f"ruido: o I-UPF atende a fatia {alvo[0]}:{alvo[1]} do UE de ruido; o "
                      "fundo passaria pelo Edge Node em vez de descer direto do PSA-UPF")
    if not atende("PSA-UPF"):
        errors.append(f"ruido: o PSA-UPF nao atende a fatia {alvo[0]}:{alvo[1]}; a sessao do "
                      "UE de ruido nao teria ancora no cenario B")
    if not any(i["interfaceType"] == "N3" for i in nodes.get("PSA-UPF", {}).get("interfaces", [])):
        errors.append("ruido: o PSA-UPF sem interface N3; o SMF nao tem F-TEID para "
                      "entregar ao gNB de ruido e a sessao nao fecha")
    links = [(l["A"], l["B"]) for l in smf["userplaneInformation"]["links"]]
    idx = {}
    for i, par in enumerate(links):
        idx.setdefault(par, i)          # o que vale e' a PRIMEIRA ocorrencia
    direto, borda = idx.get(("gNB1", "PSA-UPF")), idx.get(("gNB1", "I-UPF"))
    if direto is None:
        errors.append("ruido: falta o link gNB1 -> PSA-UPF; sem ele o UE de ruido "
                      "nao tem caminho no cenario B")
    elif borda is not None and direto < borda:
        errors.append("ruido: o link gNB1 -> PSA-UPF vem ANTES do gNB1 -> I-UPF; o SMF "
                      "percorre na ordem da lista e a fatia do experimento perderia o I-UPF")
    for grupo, info in routing["ueRoutingInfo"].items():
        if supi in (info.get("members") or []):
            errors.append(f"ruido: {supi} esta no grupo ULCL {grupo}; ele nao deve "
                          "receber o tratamento do experimento")


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
                    errors.append(f"{path}: udr info.version deve ser {UDR_VERSIONS} na v4.2.3")
                elif "webuiConfig" in key and str(conf["info"]["version"]) not in WEBUI_VERSIONS:
                    errors.append(f"{path}: webui info.version deve ser {WEBUI_VERSIONS} na v4.2.3")
        except (yaml.YAMLError, KeyError, TypeError) as exc:
            errors.append(f"{path}: falha ao interpretar ({exc})")

    check_scenario_b(errors)

    for w in warnings:
        print(f"AVISO: {w}")
    for e in errors:
        print(f"ERRO : {e}")

    if errors:
        print(f"\n{len(errors)} problema(s) encontrado(s).")
        return 1
    print("\nManifestos consistentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
