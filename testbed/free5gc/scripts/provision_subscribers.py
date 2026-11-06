#!/usr/bin/env python3
"""
Provisions subscribers in the MongoDB of free5GC (equivalent to the
subscriber script of an Open5GS testbed, but free5GC has no "collection of subscribers":
each UE becomes EIGHT documents, one in each of the eight collections of
ALL_COLLS).

Conceptual difference from Open5GS: there, each subscriber has TWO sessions
(DNN "default" and DNN "mec") because the breakout is chosen by DNN. In
free5GC the breakout is decided by the ULCL by destination IP -- the rule
arrives at runtime through Traffic Influence (mec-af -> NEF -> UDR -> PCF ->
SMF) -- so there is a single DNN ("internet").
Do not add a "mec" DNN here: it is not in smfConfig.yaml and the session would
be rejected.

The documents below were NOT written from memory -- they were captured from
MongoDB after creating a subscriber through the webui API of v4.2.3, so the
format matches exactly what the webconsole writes. Details that are easy to
get wrong by hand:
  - the authentication collection stores "encPermanentKey"/"encOpcKey" (plain,
    despite the "enc" prefix), and NOT the permanentKey/opc object that the API receives;
  - "sequenceNumber" becomes an object {sqnScheme, sqn}, not a string;
  - the snssai keys in smfSelection/smPolicy are the hex "%02x%s" % (sst, sd),
    that is, sst=1 + sd=010203 -> "01010203";
  - amData and authenticationSubscription carry "tenantId"; the others do not.

Usage:
    pip install -r scripts/requirements.txt
    kubectl -n free5gc port-forward svc/mongo 27017:27017 &
    python3 scripts/provision_subscribers.py --qty 5000

Check in the webui (NodePort 30500, admin/free5gc) that a subscriber is listed
before relying on a load of 5000.
"""
import argparse
import sys

import pymongo

# Collections used by webconsole v4.2.3 (backend/WebUI/api_webui.go).
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
    """Key used in the smfSelection/smPolicy maps: sst in hex + sd."""
    return "%02x%s" % (sst, sd)


def escape_dnn(dnn):
    """EscapeDnn() of the webconsole: '.' cannot be a map key in Mongo."""
    return dnn.replace(".", "_")


def make_docs(ue_id, args):
    """The 8 documents of a UE, in the exact form that the webconsole writes."""
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

    # Copy only so that the webui can show/edit the subscriber. No NF reads
    # this collection -- if it is missing, the core works but the page is empty.
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


def resolve_tenant_id(db, given):
    """The tenantId is generated by the webui at its first boot; it is not fixed."""
    if given:
        return given
    doc = db["tenantData"].find_one({"tenantName": "admin"})
    if doc is None:
        sys.exit("tenantData empty: start the webui once first (it creates the tenant "
                 "'admin' at boot) or pass --tenant-id explicitly")
    return doc["tenantId"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="mongodb://localhost:27017/",
                    help="URL do MongoDB (default: localhost via port-forward)")
    ap.add_argument("--db", default="free5gc", help="database name (default: free5gc)")
    ap.add_argument("--imsi-base", default="208930000000000",
                    help="initial IMSI, without the 'imsi-' prefix (default: 208930000000000, "
                         "which matches MCC/MNC 208/93 and the supi of tester/ueransim.yaml)")
    ap.add_argument("--qty", type=int, default=5000,
                    help="number of UEs (default: 5000)")
    ap.add_argument("--clean", action="store_true",
                    help="removes the existing subscribers before inserting")
    ap.add_argument("--plmn", default="20893", help="servingPlmnId (default: 20893)")
    ap.add_argument("--sst", type=int, default=1, help="SST of the slice (default: 1)")
    ap.add_argument("--sd", default="010203", help="SD of the slice (default: 010203)")
    ap.add_argument("--dnn", default="internet", help="DNN (default: internet)")
    ap.add_argument("--tenant-id", default=None,
                    help="tenantId of the webui (default: read from tenantData)")
    # Credentials: default equal to the ue.yaml of tester/ueransim.yaml.
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

    if args.clean:
        for coll in ALL_COLLS:
            removed = db[coll].delete_many({}).deleted_count
            if removed:
                print(f"removed {removed} docs from {coll}")

    base = int(args.imsi_base)
    width = len(args.imsi_base)
    batches = {coll: [] for coll in ALL_COLLS}
    for i in range(args.qty):
        ue_id = "imsi-" + str(base + i).zfill(width)
        for coll, doc in make_docs(ue_id, args).items():
            batches[coll].append(doc)

    for coll, docs in batches.items():
        db[coll].insert_many(docs)

    last_one = str(base + args.qty - 1).zfill(width)
    print(f"inserted {args.qty} subscribers "
          f"(imsi-{args.imsi_base} .. imsi-{last_one})")
    print(f"slice sst={args.sst} sd={args.sd}, dnn={args.dnn}, plmn={args.plmn}")
    print(f"{args.qty * len(ALL_COLLS)} documents in {len(ALL_COLLS)} collections")


if __name__ == "__main__":
    main()
