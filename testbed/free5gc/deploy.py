#!/usr/bin/env python3
"""
Sobe/derruba o testbed free5gc v4.2.3 em um dos dois cenarios do TG2.

    python3 deploy.py up a       # cenario A: UPF centralizado (baseline)
    python3 deploy.py up b       # cenario B: dUPF na borda com ULCL/LBO
    python3 deploy.py down       # remove tudo do namespace
    python3 deploy.py status     # visao rapida do estado

POR QUE A ORDEM IMPORTA (aprendido na marra em 24/08/2026)
----------------------------------------------------------
Aplicar os NFs todos de uma vez e dormir N segundos NAO funciona, e falha de um
jeito que so' aparece muito depois:

  1. o NRF sobe e aceita conexao em ~1 s, mas so' responde de fato depois que o
     MongoDB esta pronto -- ele grava o perfil do NF no banco;
  2. os outros NFs sobem junto, chamam o NRF e levam 'context deadline
     exceeded' (nao 'connection refused' -- o socket abre);
  3. o NF que perde essa corrida fica com o NF instance ID VAZIO;
  4. o registro do UE falha muito mais tarde, num lugar que nao tem relacao
     obvia com isso:
        AUSF sem ID -> UDM: "Mandatory IE [ausfInstanceId] is missing"
        AMF  sem ID -> UDM: "Mandatory IE [AmfInstanceId] is missing"
     e o UE ve so' "Initial Registration failed [CONGESTION]".

Por isso cada NF e' aplicado na ordem de dependencia e so' se passa para o
proximo depois que ele CONFIRMA registro no NRF -- o marcador universal e' a
linha "OAuth2 setting receive from NRF:", que todo NF imprime exatamente quando
o NRF responde. Se o registro nao fechar, o NF e' reiniciado uma vez antes de
desistir, que e' a correcao manual para esse estado.
"""
import argparse
import re
import subprocess
import sys
import time

NS = "free5gc"

# Ordem de dependencia do plano de controle. Nao reordene sem motivo:
#   mongo  <- NRF (grava perfis) e webui (assinantes)
#   NRF    <- todos os demais
#   UDR    <- UDM;  UDM <- AUSF/AMF/SMF;  NSSF/PCF <- AMF/SMF
#   NEF    depois de UDR e PCF (consome os dois); so' o mec-af depende dele
#   AMF    por ultimo entre os NFs de sinalizacao (consome quase todos)
CADEIA_COMUM = [
    ("common/mongo.yaml", "free5gc-mongodb"),
    ("common/nrf.yaml", "free5gc-nrf"),
    ("common/udr.yaml", "free5gc-udr"),
    ("common/udm.yaml", "free5gc-udm"),
    ("common/ausf.yaml", "free5gc-ausf"),
    ("common/nssf.yaml", "free5gc-nssf"),
    ("common/pcf.yaml", "free5gc-pcf"),
    ("common/nef.yaml", "free5gc-nef"),
    ("common/amf.yaml", "free5gc-amf"),
    ("common/webui.yaml", "free5gc-webui"),
]

# UPFs primeiro, SMF depois: quem abre a associacao PFCP e' o SMF, entao ele
# encontra os UPFs ja' de pe' em vez de depender do retransmit.
SCENARIOS = {
    "a": [("scenario-a-cupf/upf.yaml", "free5gc-upf"),
          ("scenario-a-cupf/smf.yaml", "free5gc-smf")],
    "b": [("scenario-b-dupf/i-upf.yaml", "free5gc-i-upf"),
          ("scenario-b-dupf/psa-upf.yaml", "free5gc-psa-upf"),
          ("scenario-b-dupf/smf.yaml", "free5gc-smf")],
}

# mec-service.yaml aparece duas vezes de proposito: ele contem DOIS
# deployments (mec-app e remote-app) e sobe() so espera um por entrada.
# O apply repetido e' idempotente. O remote-app e' o alvo da medicao
# b-remoto; sem esperar por ele, um pod Unschedulable so' apareceria
# no fim da campanha.
#
# mec-af depois do mec-service: ele vigia os Services com a label
# tg2.mec/lbo=true e anuncia o ClusterIP ao NEF (LBO dinamico). Antes do
# tester so' por clareza -- a regra vale tambem para sessoes ja' abertas.
EXTRAS = [("mec/vr-app.yaml", None),
          ("mec/mec-service.yaml", "free5gc-mec-app"),
          ("mec/mec-service.yaml", "free5gc-remote-app"),
          ("mec/mec-af.yaml", "mec-af"),
          ("tester/ueransim.yaml", None)]

# NFs que falam SBI e portanto registram no NRF. O UPF nao entra: ele nao e' um
# NF de SBI, fala so' PFCP com o SMF.
REGISTRAM_NO_NRF = {
    "free5gc-udr", "free5gc-udm", "free5gc-ausf", "free5gc-nssf",
    "free5gc-pcf", "free5gc-nef", "free5gc-amf", "free5gc-smf", "free5gc-webui",
}

MARCADOR_OK = "OAuth2 setting receive from NRF"
MARCADOR_ERRO = "register to NRF Error"
NRF_PRONTO = "SBI server started"

VERDE, VERM, AMAR, CINZA, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if not sys.stdout.isatty():
    VERDE = VERM = AMAR = CINZA = RESET = ""


def run(cmd, check=True, quiet=False, timeout=180):
    if not quiet:
        print(f"  {CINZA}$ {cmd}{RESET}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.stdout.strip() and not quiet:
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0 and check and not quiet:
        print(f"    {VERM}ERRO:{RESET} {r.stderr.strip()}", file=sys.stderr)
    return r


def limpa_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def espera_rollout(deploy, timeout):
    r = run(f"kubectl -n {NS} rollout status deploy/{deploy} --timeout={timeout}s",
            check=False, quiet=True, timeout=timeout + 30)
    return r.returncode == 0


def registrou_no_nrf(deploy):
    """True se o NF confirmou registro DEPOIS do ultimo erro de registro.

    A ordem importa: um NF que errou, tentou de novo e conseguiu esta' bom; um
    que so' errou, nao. Comparar presenca/ausencia dos dois marcadores nao
    distingue os dois casos."""
    r = run(f"kubectl -n {NS} logs deploy/{deploy} --tail=400",
            check=False, quiet=True, timeout=60)
    if r.returncode != 0:
        return None
    ult_ok = ult_erro = -1
    for i, linha in enumerate(limpa_ansi(r.stdout).splitlines()):
        if MARCADOR_OK in linha:
            ult_ok = i
        elif MARCADOR_ERRO in linha:
            ult_erro = i
    return ult_ok > ult_erro


def espera_registro(deploy, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if registrou_no_nrf(deploy):
            return True
        time.sleep(3)
    return False


def sobe(manifesto, deploy, args):
    print(f"\n==> {manifesto}")
    run(f"kubectl apply -f {manifesto}")
    if not deploy:
        return

    if deploy in ("free5gc-smf", "mec-af"):
        # Config (SMF) e codigo (mec-af) vivem em ConfigMaps. Se so' eles
        # mudaram, o apply NAO recria o pod e o processo segue com a versao
        # antiga -- o LBO "nao ativa" sem nenhum erro. O restart forca a
        # releitura; quando o template do pod tambem mudou, vira um rollout so'.
        run(f"kubectl -n {NS} rollout restart deploy/{deploy}",
            check=False, quiet=True)

    if not espera_rollout(deploy, args.timeout):
        print(f"    {VERM}{deploy} nao ficou pronto em {args.timeout}s{RESET}")
        run(f"kubectl -n {NS} get pods -l app={deploy} -o wide", check=False)
        sys.exit(1)
    print(f"    {VERDE}pronto{RESET}")

    if deploy == "free5gc-nrf":
        # O NRF nao registra em si mesmo: o gate dele e' o proprio SBI de pe'.
        # Ele aceita conexao antes de conseguir gravar no Mongo, entao a folga
        # abaixo e' o que evita a corrida que quebra todo o resto.
        for _ in range(args.timeout // 2):
            r = run(f"kubectl -n {NS} logs deploy/{deploy} --tail=50",
                    check=False, quiet=True, timeout=60)
            if NRF_PRONTO in limpa_ansi(r.stdout):
                break
            time.sleep(2)
        print(f"    {VERDE}SBI do NRF no ar{RESET}; folga de {args.espera}s antes dos demais")
        time.sleep(args.espera)
        return

    if deploy in REGISTRAM_NO_NRF:
        if espera_registro(deploy, args.timeout):
            print(f"    {VERDE}registrado no NRF{RESET}")
        else:
            # Estado conhecido: o NF perdeu a corrida e ficou com instance ID
            # vazio. Reiniciar e' a correcao -- ele refaz o registro do zero.
            print(f"    {AMAR}nao confirmou registro no NRF; reiniciando "
                  f"{deploy} (instance ID vazio){RESET}")
            run(f"kubectl -n {NS} rollout restart deploy/{deploy}", check=False)
            espera_rollout(deploy, args.timeout)
            if espera_registro(deploy, args.timeout):
                print(f"    {VERDE}registrado no NRF apos restart{RESET}")
            else:
                print(f"    {VERM}{deploy} segue sem registrar no NRF. "
                      f"Nao adianta seguir: o registro do UE vai falhar com "
                      f"MANDATORY_IE_MISSING la' na frente.{RESET}")
                sys.exit(1)

    time.sleep(args.espera)


def up(args):
    outro = "b" if args.scenario == "a" else "a"

    print(f"==> Removendo plano de usuario do cenario {outro.upper()} (se existir)")
    for manifesto, _ in SCENARIOS[outro]:
        run(f"kubectl delete -f {manifesto} --ignore-not-found=true",
            check=False, quiet=True)

    print(f"\n{'='*70}\nPlano de controle, em ordem de dependencia\n{'='*70}")
    for manifesto, deploy in CADEIA_COMUM:
        sobe(manifesto, deploy, args)

    print(f"\n{'='*70}\nPlano de usuario - cenario {args.scenario.upper()}\n{'='*70}")
    for manifesto, deploy in SCENARIOS[args.scenario]:
        sobe(manifesto, deploy, args)

    print(f"\n{'='*70}\nServicos MEC/remoto e tester\n{'='*70}")
    for manifesto, deploy in EXTRAS:
        sobe(manifesto, deploy, args)

    print(f"\n{VERDE}==> Pronto.{RESET} Verifique com: python3 deploy.py status")


def down():
    print("==> Removendo tudo do namespace")
    todos = EXTRAS + SCENARIOS["a"] + SCENARIOS["b"] + CADEIA_COMUM
    for manifesto, _ in todos:
        run(f"kubectl delete -f {manifesto} --ignore-not-found=true",
            check=False, quiet=True)


def status():
    run(f"kubectl -n {NS} get pods -o wide")
    print()
    run(f"kubectl -n {NS} get svc")
    print()
    print("==> NFs que NAO confirmaram registro no NRF (ID vazio, quebra o UE):")
    ruins = [d for d in sorted(REGISTRAM_NO_NRF) if registrou_no_nrf(d) is False]
    print("    " + (", ".join(ruins) if ruins else f"{VERDE}nenhum{RESET}"))
    print()
    print("==> Associacoes PFCP vistas pelo SMF (esperado: 1 UPF no A, 2 no B)")
    # Filtro em Python, e nao com grep/tail: o cmd.exe do Windows nao tem nenhum dos dois.
    r = run(f"kubectl -n {NS} logs deploy/free5gc-smf --tail=200", check=False, quiet=True)
    linhas = [l for l in limpa_ansi(r.stdout).splitlines()
              if re.search(r"pfcp|association", l, re.I)]
    print("    " + ("\n    ".join(linhas[-20:]) if linhas else "(nada nas ultimas 200 linhas)"))
    print()
    print("==> LBO dinamico: Services com tg2.mec/lbo=true e o que o mec-af anunciou ao NEF")
    run(f"kubectl -n {NS} get svc -l tg2.mec/lbo=true", check=False)
    run(f"kubectl -n {NS} logs deploy/mec-af --tail=8", check=False)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["up", "down", "status"])
    ap.add_argument("scenario", nargs="?", choices=["a", "b"],
                    help="obrigatorio para 'up'")
    ap.add_argument("--espera", type=int, default=10,
                    help="folga em segundos entre um NF e o proximo (default: 10)")
    ap.add_argument("--timeout", type=int, default=180,
                    help="timeout por NF, em segundos (default: 180)")
    args = ap.parse_args()

    if args.action == "up":
        if not args.scenario:
            ap.error("'up' exige o cenario: a (cUPF) ou b (dUPF/ULCL)")
        up(args)
    elif args.action == "down":
        down()
    else:
        status()


if __name__ == "__main__":
    main()
