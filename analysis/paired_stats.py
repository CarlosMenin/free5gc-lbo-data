"""Common statistics: the round is the unit, the effect is the paired difference A - B.

Names (kept from the original code, in Portuguese):
  R, D           records of dados.json; D[(profile, level, round, scenario)]
  PERFIS         the three profiles of the detailed study; PERFIS_TODOS all six
  NIVEIS         background levels (% of the measured capacity; 0 = none)
  NOME, APP      English name and application bitrate (Mbps) of each profile
  EXCL           rounds excluded as a whole, with the reason ("cap" or "sent")
  CAP_MED        median capacity of the edge-core link over the campaign (Mbps)
  mantida(r)     the round of r was kept
  ok(r)          r completed, is valid, and its round was kept
  pares(pf, nv)  valid pairs (round, run A, run B) of a profile at a level
  pareado(d)     mean, standard deviation, 95% CI (t) and MDE of differences d
  ic_mediana(x)  median of x with its 95% CI from order statistics
  sinal_p(k, n)  two-sided sign test p-value for k wins in n pairs
  kpi(P, k)      medians of A and B, paired difference with CI, reduction (%),
                 wins of B and sign-test p-value, for indicator k over pairs P
"""
import json, math, os, statistics
import numpy as np
AQUI = os.path.dirname(os.path.abspath(__file__))
_D = json.load(open(os.path.join(AQUI, "dados.json")))
GRADE, PRAZOS, R = np.array(_D["grade"]), _D["prazos"], _D["regs"]
PERFIS = ["teleoperacao", "vr-cloud", "vr-extremo"]                       # the three profiles of the detailed study
PERFIS_TODOS = ["teleoperacao", "ar-industrial", "vr-360", "cloud-gaming", "vr-cloud", "vr-extremo"]
NIVEIS = [0, 50, 80, 95, 99]
NOME = {"teleoperacao": "teleoperation", "ar-industrial": "ar-industrial", "vr-360": "vr-360",
        "cloud-gaming": "cloud-gaming", "vr-cloud": "vr-cloud", "vr-extremo": "vr-extreme"}
APP = {"teleoperacao": 8.0, "ar-industrial": 12.0, "vr-360": 25.0, "cloud-gaming": 30.0, "vr-cloud": 50.0,
       "vr-extremo": 100.2}
D = {(r["perfil"], r["nivel"], r["rodada"], r["cen"]): r for r in R}
T975 = [None, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
        2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]
T80 = [None, 1.376, 1.061, 0.978, 0.941, 0.920, 0.906, 0.896, 0.889, 0.883, 0.879, 0.876, 0.873, 0.870, 0.868,
       0.866, 0.865, 0.863, 0.862, 0.861, 0.860, 0.859, 0.858, 0.858, 0.857, 0.856, 0.856, 0.855, 0.855, 0.854, 0.854]
med = statistics.median

def _ok(r): return bool(r and r.get("concluiu") and r.get("valida"))

# Whole rounds are excluded by two safeguards that the campaign already had, both independent of
# the A x B comparison: (1) capacity of the round, after the re-measurements, below 90% of the
# campaign median (the same fraction that triggers a re-measurement in campanha-a-vs-b.py): the
# link carried external traffic and the nominal level does not hold; (2) sentinel: median delay
# without background of a scenario more than 25% away from the median of the other rounds of the
# same profile and scenario (without background, nothing in the experiment explains that).
CAP_FRAC, SENT_FAIXA = 0.90, 0.25
_cap = {}
for _r in R:
    if _r.get("concluiu") and _r["nivel"] and _r.get("f_capacidade_mbps"):
        _cap[(_r["perfil"], _r["rodada"])] = _r["f_capacidade_mbps"]
CAP_MED = med(list(_cap.values()))
EXCL = {}
for (_pf, _rd), _c in sorted(_cap.items()):
    if _c < CAP_FRAC * CAP_MED:
        EXCL[(_pf, _rd)] = ("cap", _c)
for _pf in PERFIS_TODOS:
    for _cen in "ab":
        _vs = {rd: D[(_pf, 0, rd, _cen)]["mec_net_p50"] / 1000 for rd in range(1, 31) if _ok(D.get((_pf, 0, rd, _cen)))}
        for _rd, _v in _vs.items():
            _ref = med([x for r2, x in _vs.items() if r2 != _rd])
            if abs(_v / _ref - 1) > SENT_FAIXA and (_pf, _rd) not in EXCL:
                EXCL[(_pf, _rd)] = ("sent", _cen, _v, _ref)

def mantida(r): return (r["perfil"], r["rodada"]) not in EXCL
def ok(r): return _ok(r) and mantida(r)
def ok_rem(r): return bool(r and r.get("concluiu") and r.get("valida_remoto") and mantida(r))

def pares(pf, nv):
    return [(rd, D[(pf, nv, rd, "a")], D[(pf, nv, rd, "b")]) for rd in range(1, 31)
            if ok(D.get((pf, nv, rd, "a"))) and ok(D.get((pf, nv, rd, "b")))]

def pareado(d):
    n = len(d)
    if n < 2: return None
    m = sum(d) / n; dp = statistics.stdev(d); ep = dp / math.sqrt(n)
    t, t8 = (T975[n - 1], T80[n - 1]) if n <= 31 else (1.96, 0.842)
    return dict(n=n, media=m, dp=dp, ic=(m - t * ep, m + t * ep), mde=(t + t8) * ep)

def ic_mediana(x):
    """95% CI of the median from order statistics (binomial, distribution-free)."""
    x = sorted(x); n = len(x); k = 0
    while sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n <= 0.025: k += 1
    return med(x), x[k - 1], x[n - k]

def sinal_p(k, n):
    m = min(k, n - k)
    return min(1.0, sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n * 2)

def kpi(P, k, div=1.0):
    A = [a["mec_" + k] / div for _, a, b in P]; B = [b["mec_" + k] / div for _, a, b in P]
    d = [x - y for x, y in zip(A, B)]
    pc = [(1 - y / x) * 100 for x, y in zip(A, B) if x]
    win = sum(1 for v in d if v > 0)
    return dict(n=len(d), A=med(A), B=med(B), d=ic_mediana(d) if d else None, t=pareado(d),
                pct=med(pc) if pc else None, win=win, p=sinal_p(win, len(d)) if d else None, difs=d)
