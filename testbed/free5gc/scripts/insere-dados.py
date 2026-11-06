#!/usr/bin/env python3
"""
Cadastra assinantes no MongoDB do free5GC (equivalente ao insere-dados.py do
Open5GS, mas o free5GC nao tem "uma colecao de subscribers": cada UE vira OITO
documentos, um em cada uma das oito colecoes de ALL_COLLS).

Diferenca conceitual para o Open5GS: la cada assinante tem DUAS sessoes (DNN
"default" e DNN "mec") porque o breakout e' escolhido por DNN. No free5GC o
breakout e' decidido pelo ULCL por destino IP -- a regra chega em runtime por
Traffic Influence (mec-af -> NEF -> UDR -> PCF -> SMF) -- entao existe um
unico DNN ("internet").
Nao adicione um DNN "mec" aqui: ele nao esta no smfConfig.yaml e a sessao seria
rejeitada.

Os documentos abaixo NAO foram escritos de memoria -- foram capturados do
MongoDB depois de criar um assinante pela API do webui da v4.2.3, entao o
formato bate exatamente com o que o webconsole grava. Detalhes que sao faceis
de errar escrevendo na mao:
  - a colecao de autenticacao guarda "encPermanentKey"/"encOpcKey" (planos,
    apesar do prefixo "enc"), e NAO o objeto permanentKey/opc que a API recebe;
  - "sequenceNumber" vira um objeto {sqnScheme, sqn}, nao uma string;
  - as chaves de snssai em smfSelection/smPolicy sao o hex "%02x%s" % (sst, sd),
    ou seja sst=1 + sd=010203 -> "01010203";
  - amData e authenticationSubscription levam "tenantId"; as demais nao.

Uso:
    pip install -r scripts/requirements.txt
    kubectl -n free5gc port-forward svc/mongo 27017:27017 &
    python3 scripts/insere-dados.py --qtd 5000

Conferir no webui (NodePort 30500, admin/free5gc) que um assinante aparece
listado antes de confiar numa carga de 5000.
"""
import argparse
import sys

import pymongo

# Colecoes usadas pelo webconsole v4.2.3 (backend/WebUI/api_webui.go).
AUTH_COLL = "subscriptionData.authenticationData.authenticationSubscription"
WEB_AUTH_COLL = "subscriptionData.authenticationData.webAuthenticationSubscription"
AM_COLL = "subscriptionData.provisionedData.amData"
SM_COLL = "subscriptionData.provisionedData.smData"
SMF_SEL_COLL = "subscriptionData.provisionedData.smfSelectionSubscriptionData"
AM_POLICY_COLL = "policyData.ues.amData"
SM_POLICY_COLL = "policyData.ues.smData"
IDENTITY_COLL = "subscriptionData.identityData"

ALL_COLLS = [
    AUTH_COLL, WEB_AUTH_COLL, AM_COLL, SM_COLL,
    SMF_SEL_COLL, AM_POLICY_COLL, SM_POLICY_COLL, IDENTITY_COLL,
]


def snssai_hex(sst, sd):
    """Chave usada nos mapas de smfSelection/smPolicy: sst em hex + sd."""
    return "%02x%s" % (sst, sd)


def escape_dnn(dnn):
    """EscapeDnn() do webconsole: '.' nao pode ser chave de mapa no Mongo."""
    return dnn.replace(".", "_")


def make_docs(ue_id, args):
    """Os 8 documentos de um UE, na forma exata que o webconsole grava."""
    snssai = {"sst": args.sst, "sd": args.sd}
    key = snssai_hex(args.sst, args.sd)
    dnn = escape_dnn(args.dnn)

    auth = {
        "authenticationMethod": "5G_AKA",
        "encPermanentKey": args.key,
        "sequenceNumber": {"sqnScheme": "GENERAL", "sqn": args.sqn},
        "authenticationManagementField": args.amf,
        "encOpcKey": args.opc,
        "ueId": ue_id,
        "tenantId": args.tenant_id,
    }

    # Copia so para o webui conseguir exibir/editar o assinante. Nenhum NF le
    # esta colecao -- se ela faltar, o core funciona mas a tela fica vazia.
    web_auth = {
        "permanentKey": {
            "encryptionKey": 0,
            "encryptionAlgorithm": 0,
            "permanentKeyValue": args.key,
        },
        "sequenceNumber": args.sqn,
        "milenage": {"op": {"opValue": "", "encryptionKey": 0, "encryptionAlgorithm": 0}},
        "opc": {"opcValue": args.opc, "encryptionKey": 0, "encryptionAlgorithm": 0},
        "authenticationManagementField": args.amf,
        "ueId": ue_id,
        "tenantId": args.tenant_id,
        "authenticationMethod": "5G_AKA",
    }

    am_data = {
        "subscribedUeAmbr": {"uplink": args.ue_ambr_ul, "downlink": args.ue_ambr_dl},
        "nssai": {"defaultSingleNssais": [snssai]},
        "ueId": ue_id,
        "servingPlmnId": args.plmn,
        "tenantId": args.tenant_id,
        "gpsis": ["msisdn-"],
    }

    sm_data = {
        "servingPlmnId": args.plmn,
        "singleNssai": snssai,
        "dnnConfigurations": {
            dnn: {
                "pduSessionTypes": {
                    "defaultSessionType": "IPV4",
                    "allowedSessionTypes": ["IPV4"],
                },
                "sscModes": {
                    "defaultSscMode": "SSC_MODE_1",
                    "allowedSscModes": ["SSC_MODE_2", "SSC_MODE_3"],
                },
                "5gQosProfile": {
                    "5qi": 9,
                    "arp": {"preemptCap": "", "preemptVuln": "", "priorityLevel": 8},
                    "priorityLevel": 8,
                },
                "sessionAmbr": {
                    "uplink": args.sess_ambr_ul,
                    "downlink": args.sess_ambr_dl,
                },
            }
        },
        "ueId": ue_id,
    }

    smf_sel = {
        "subscribedSnssaiInfos": {key: {"dnnInfos": [{"dnn": args.dnn}]}},
        "ueId": ue_id,
        "servingPlmnId": args.plmn,
    }

    am_policy = {"subscCats": ["free5gc"], "ueId": ue_id}

    sm_policy = {
        "smPolicySnssaiData": {
            key: {"snssai": snssai, "smPolicyDnnData": {dnn: {"dnn": args.dnn}}}
        },
        "ueId": ue_id,
    }

    identity = {"ueId": ue_id, "gpsi": "msisdn-"}

    return {
        AUTH_COLL: auth,
        WEB_AUTH_COLL: web_auth,
        AM_COLL: am_data,
        SM_COLL: sm_data,
        SMF_SEL_COLL: smf_sel,
        AM_POLICY_COLL: am_policy,
        SM_POLICY_COLL: sm_policy,
        IDENTITY_COLL: identity,
    }


def resolve_tenant_id(db, informado):
    """O tenantId e' gerado pelo webui no primeiro boot; nao e' fixo."""
    if informado:
        return informado
    doc = db["tenantData"].find_one({"tenantName": "admin"})
    if doc is None:
        sys.exit("tenantData vazio: suba o webui uma vez antes (ele cria o tenant "
                 "'admin' no boot) ou passe --tenant-id explicitamente")
    return doc["tenantId"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="mongodb://localhost:27017/",
                    help="URL do MongoDB (default: localhost via port-forward)")
    ap.add_argument("--db", default="free5gc", help="nome do banco (default: free5gc)")
    ap.add_argument("--imsi-base", default="208930000000000",
                    help="IMSI inicial, sem o prefixo 'imsi-' (default: 208930000000000, "
                         "que casa com MCC/MNC 208/93 e com o supi do tester/ueransim.yaml)")
    ap.add_argument("--qtd", type=int, default=5000,
                    help="quantidade de UEs (default: 5000)")
    ap.add_argument("--limpar", action="store_true",
                    help="remove os assinantes existentes antes de inserir")
    ap.add_argument("--plmn", default="20893", help="servingPlmnId (default: 20893)")
    ap.add_argument("--sst", type=int, default=1, help="SST da slice (default: 1)")
    ap.add_argument("--sd", default="010203", help="SD da slice (default: 010203)")
    ap.add_argument("--dnn", default="internet", help="DNN (default: internet)")
    ap.add_argument("--tenant-id", default=None,
                    help="tenantId do webui (default: lido de tenantData)")
    # Credenciais: default igual ao ue.yaml do tester/ueransim.yaml.
    ap.add_argument("--key", default="8baf473f2f8fd09487cccbd7097c6862")
    ap.add_argument("--opc", default="8e27b6af0e692e750f32667a3b14605d")
    ap.add_argument("--amf", default="8000")
    ap.add_argument("--sqn", default="000000000023")
    ap.add_argument("--ue-ambr-ul", default="1 Gbps")
    ap.add_argument("--ue-ambr-dl", default="2 Gbps")
    ap.add_argument("--sess-ambr-ul", default="200 Mbps")
    ap.add_argument("--sess-ambr-dl", default="100 Mbps")
    args = ap.parse_args()

    client = pymongo.MongoClient(args.url)
    db = client[args.db]
    args.tenant_id = resolve_tenant_id(db, args.tenant_id)
    print(f"tenantId: {args.tenant_id}")

    if args.limpar:
        for coll in ALL_COLLS:
            removed = db[coll].delete_many({}).deleted_count
            if removed:
                print(f"removidos {removed} docs de {coll}")

    base = int(args.imsi_base)
    width = len(args.imsi_base)
    lotes = {coll: [] for coll in ALL_COLLS}
    for i in range(args.qtd):
        ue_id = "imsi-" + str(base + i).zfill(width)
        for coll, doc in make_docs(ue_id, args).items():
            lotes[coll].append(doc)

    for coll, docs in lotes.items():
        db[coll].insert_many(docs)

    ultimo = str(base + args.qtd - 1).zfill(width)
    print(f"inseridos {args.qtd} assinantes "
          f"(imsi-{args.imsi_base} .. imsi-{ultimo})")
    print(f"slice sst={args.sst} sd={args.sd}, dnn={args.dnn}, plmn={args.plmn}")
    print(f"{args.qtd * len(ALL_COLLS)} documentos em {len(ALL_COLLS)} colecoes")


if __name__ == "__main__":
    main()
