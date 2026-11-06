#!/usr/bin/env python3
"""
vrclock -- carimbo de tempo DO KERNEL para o vr_server e o vr_client.

Por que isto existe: a latencia que o TG mede e' de milissegundos, e um
timestamp tirado em Python (depois que o recvfrom volta) carrega junto o
tempo que o processo passou fora da CPU. Num brix que roda o core inteiro,
os dois UPFs, o UERANSIM e mais os dois geradores, esse tempo NAO e'
desprezivel -- e cresce junto com a carga, exatamente onde a medida precisa
ser confiavel. O resultado seria uma "latencia de rede" que piora quando a
CPU aperta, e o texto atribuiria ao UPF um atraso que foi do escalonador.

SO_TIMESTAMPNS resolve: o kernel carimba o pacote na recepcao e entrega o
carimbo como dado auxiliar do recvmsg. O que sobra entre o carimbo e o
Python deixa de contar.

Consequencia: o relogio passa a ser CLOCK_REALTIME (e' o que o kernel usa em
timestamp de software), e nao mais o perf_counter. Como as duas pontas de
cada medida estao NO MESMO processo, nao ha sincronizacao entre maquinas
envolvida -- mas um passo de NTP no meio da corrida corromperia as amostras.
Por isso clock_drift_us() existe: a corrida reporta o quanto o CLOCK_REALTIME
andou alem do monotonico, e um passo aparece la'.

Sem suporte (macOS, kernel antigo, arquitetura exotica) tudo degrada para o
carimbo em Python -- as constantes abaixo sao as do asm-generic/socket.h,
validas em x86_64/arm64, e habilitar() so' liga o que o kernel aceitar.
"""
import socket
import struct
import time

# asm-generic/socket.h -- x86_64, arm64, riscv. Em mips/parisc/sparc/alpha os
# numeros sao outros; por isso getattr() primeiro e setsockopt dentro de try.
SO_TIMESTAMPNS = getattr(socket, "SO_TIMESTAMPNS", 35)
SCM_TIMESTAMPNS = SO_TIMESTAMPNS
SO_RXQ_OVFL = getattr(socket, "SO_RXQ_OVFL", 40)
SCM_RXQ_OVFL = SO_RXQ_OVFL

CLOCK_REALTIME = getattr(time, "CLOCK_REALTIME", 0)


def now_ns():
    """Relogio das MEDIDAS -- o mesmo que o kernel usa no SO_TIMESTAMPNS."""
    return time.clock_gettime_ns(CLOCK_REALTIME)


def clock_drift_us():
    """(realtime_ns, monotonic_ns) para medir, entre dois pontos da corrida, o
    quanto o CLOCK_REALTIME andou a mais que o monotonico. Zero = nenhum ajuste
    de NTP no meio; alguns milissegundos = as amostras daquela corrida estao
    contaminadas e o ponto nao vale."""
    return now_ns(), time.monotonic_ns()


def habilitar(sock, rxq_ovfl=True):
    """Liga o carimbo do kernel (e, opcionalmente, o contador de estouro da
    fila de recepcao) no socket. Devolve (tem_timestamp, tem_ovfl)."""
    ts = ovfl = False
    try:
        sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
        ts = True
    except OSError:
        pass
    if rxq_ovfl:
        try:
            sock.setsockopt(socket.SOL_SOCKET, SO_RXQ_OVFL, 1)
            ovfl = True
        except OSError:
            pass
    return ts, ovfl


def ancbufsize():
    """Espaco para os dois cmsg (timespec de 16 B + u32 de 4 B)."""
    try:
        return socket.CMSG_SPACE(16) + socket.CMSG_SPACE(4)
    except AttributeError:
        return 128


def ler_anc(ancdata):
    """Extrai (t_kernel_ns, contador_de_estouro) do dado auxiliar do recvmsg.
    Devolve None em cada campo que nao veio."""
    t_ns = ovfl = None
    for nivel, tipo, dado in ancdata:
        if nivel != socket.SOL_SOCKET:
            continue
        if tipo == SCM_TIMESTAMPNS:
            # struct timespec: 2 palavras do tamanho nativo (16 B em 64 bits,
            # 8 B em 32 bits). O tamanho do dado e' quem diz qual e'.
            if len(dado) >= 16:
                s, ns = struct.unpack_from("@qq", dado)
            elif len(dado) >= 8:
                s, ns = struct.unpack_from("@ii", dado)
            else:
                continue
            t_ns = s * 1_000_000_000 + ns
        elif tipo == SCM_RXQ_OVFL and len(dado) >= 4:
            ovfl = struct.unpack_from("@I", dado)[0]
    return t_ns, ovfl


def rcvtimeo(sock, segundos):
    """Timeout de recepcao PELO KERNEL, em vez de sock.settimeout().

    settimeout() poe o socket no modo 'timeout' do CPython, que passa a chamar
    poll() antes de cada recvmsg -- uma syscall extra por pacote, justamente no
    laco mais quente. Com SO_RCVTIMEO o socket continua bloqueante para o
    CPython e o kernel devolve EAGAIN sozinho quando o prazo estoura, o que
    chega aqui como BlockingIOError."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                        struct.pack("@qq", int(segundos),
                                    int((segundos % 1) * 1e6)))
        return True
    except OSError:
        sock.settimeout(segundos)
        return False


def buffers(sock, pedido):
    """Pede SO_RCVBUF/SO_SNDBUF e devolve o que o kernel DE FATO concedeu.

    O kernel corta o pedido em net.core.rmem_max / wmem_max (208 KB por padrao)
    e nao avisa: pedir 8 MB e receber 416 KB e' silencioso. Como esses dois
    sysctl sao GLOBAIS (nao sao por namespace de rede), quem tem que levanta-los
    e' o no -- de dentro do pod nao da'. Devolver o valor efetivo e' o que
    permite ao resumo da corrida mostrar o corte em vez de esconde-lo."""
    for opt in (socket.SO_RCVBUF, socket.SO_SNDBUF):
        try:
            sock.setsockopt(socket.SOL_SOCKET, opt, pedido)
        except OSError:
            pass
    return (sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF))


def udp_erros():
    """RcvbufErrors/InErrors de UDP do /proc/net/snmp -- do NAMESPACE DE REDE
    inteiro, nao so' deste socket. No pod do tester isso inclui os sockets do
    nr-gnb e do nr-ue, que dividem o netns: se o estouro estiver la', a perda
    aconteceu no UERANSIM e nao no caminho do UPF."""
    try:
        with open("/proc/net/snmp") as fh:
            linhas = fh.read().splitlines()
    except OSError:
        return {}
    cabec = None
    for linha in linhas:
        if linha.startswith("Udp:"):
            campos = linha.split()[1:]
            if cabec is None:
                cabec = campos
            else:
                return {k: int(v) for k, v in zip(cabec, campos)}
    return {}


def udp_drops(porta):
    """Descartes por fila cheia DESTE socket, lidos da ultima coluna de
    /proc/net/udp (a que o kernel chama 'drops').

    Existe porque o cmsg do SO_RXQ_OVFL nao apareceu na primeira corrida no
    brix, mesmo com a opcao aceita pelo kernel -- e um contador que "as vezes
    vem" nao serve para decidir se uma medida vale. Aqui a fonte e' o proprio
    socket no /proc, sempre disponivel, e a porta e' a que o bind() sorteou
    (sock.getsockname()[1]).

    Devolve None se a linha nao for encontrada; o chamador tira o delta entre
    duas leituras."""
    alvo = f":{porta:04X}"
    try:
        with open("/proc/net/udp") as fh:
            next(fh, None)          # cabecalho
            for linha in fh:
                campos = linha.split()
                if len(campos) >= 13 and campos[1].endswith(alvo):
                    return int(campos[-1])
    except (OSError, ValueError):
        pass
    return None


def ctxt_switches():
    """Trocas de contexto INVOLUNTARIAS do processo: quantas vezes o
    escalonador o tirou da CPU sem ele pedir. Se este numero explodir durante
    a corrida, a maquina estava disputada e a latencia medida tem CPU dentro."""
    try:
        with open("/proc/self/status") as fh:
            for linha in fh:
                if linha.startswith("nonvoluntary_ctxt_switches:"):
                    return int(linha.split()[1])
    except OSError:
        pass
    return None
