"""Common statistics: the round is the unit, and the effect is the paired difference A - B.

  RECORDS, D        records of runs.json; D[(profile, level, round, scenario)]
  PROFILES          the three profiles of the detailed study; ALL_PROFILES all six
  LEVELS            background levels (% of the measured capacity; 0 = none)
  NAME, APP         display name and application bitrate (Mbps) of each profile
  EXCLUDED          rounds excluded as a whole, with the reason ("capacity" or "sentinel")
  CAP_MEDIAN        median capacity of the edge-core link over the campaign (Mbps)
  round_kept(r)     the round of r was kept
  ok(r)             r completed, is valid, and its round was kept
  pairs(pf, lv)     valid pairs (round, run A, run B) of a profile at a level
  paired_t(d)       mean, standard deviation, 95% CI (t) and MDE of the differences d
  median_ci(x)      median of x with its 95% CI from order statistics
  sign_test_p(k, n) two-sided sign-test p-value for k wins in n pairs
  kpi(P, k)         medians of A and B, paired difference with CI, reduction (%),
                    wins of B and sign-test p-value, for indicator k over the pairs P
"""
import json
import math
import os
import statistics

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_RUNS = json.load(open(os.path.join(HERE, "runs.json")))
DEADLINE_GRID, DEADLINES, RECORDS = np.array(_RUNS["grid"]), _RUNS["deadlines"], _RUNS["records"]
PROFILES = ["teleoperation", "vr-cloud", "vr-extreme"]                  # the three profiles of the detailed study
ALL_PROFILES = ["teleoperation", "ar-industrial", "vr-360", "cloud-gaming", "vr-cloud", "vr-extreme"]
LEVELS = [0, 50, 80, 95, 99]
NAME = {p: p for p in ALL_PROFILES}
APP = {"teleoperation": 8.0, "ar-industrial": 12.0, "vr-360": 25.0, "cloud-gaming": 30.0, "vr-cloud": 50.0,
       "vr-extreme": 100.2}
D = {(r["profile"], r["level"], r["round"], r["scenario"]): r for r in RECORDS}
# Student t quantiles 0.975 and 0.80 by degrees of freedom (index = df).
T975 = [None, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
        2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]
T80 = [None, 1.376, 1.061, 0.978, 0.941, 0.920, 0.906, 0.896, 0.889, 0.883, 0.879, 0.876, 0.873, 0.870, 0.868,
       0.866, 0.865, 0.863, 0.862, 0.861, 0.860, 0.859, 0.858, 0.858, 0.857, 0.856, 0.856, 0.855, 0.855, 0.854, 0.854]
med = statistics.median


def _ok(r):
    return bool(r and r.get("completed") and r.get("valid"))


# Whole rounds are excluded by two safeguards that the campaign already had, both independent of
# the A x B comparison: (1) capacity of the round, after the re-measurements, below 90% of the
# campaign median (the same fraction that triggers a re-measurement in the campaign script): the
# link carried external traffic and the nominal level does not hold; (2) sentinel: median delay
# without background of a scenario more than 25% away from the median of the other rounds of the
# same profile and scenario (without background, nothing in the experiment explains that).
CAP_FRACTION, SENTINEL_BAND = 0.90, 0.25
_capacity = {}
for _r in RECORDS:
    if _r.get("completed") and _r["level"] and _r.get("bg_capacity_mbps"):
        _capacity[(_r["profile"], _r["round"])] = _r["bg_capacity_mbps"]
CAP_MEDIAN = med(list(_capacity.values())) if _capacity else None   # None: a campaign without background
EXCLUDED = {}
for (_pf, _rd), _c in sorted(_capacity.items()):
    if _c < CAP_FRACTION * CAP_MEDIAN:
        EXCLUDED[(_pf, _rd)] = ("capacity", _c)
for _pf in ALL_PROFILES:
    for _scen in "ab":
        _values = {rd: D[(_pf, 0, rd, _scen)]["mec_net_p50"] / 1000 for rd in range(1, 31)
                   if _ok(D.get((_pf, 0, rd, _scen)))}
        for _rd, _v in _values.items():
            _others = [x for r2, x in _values.items() if r2 != _rd]
            if not _others:                      # a campaign of one round has no reference
                continue
            _ref = med(_others)
            if abs(_v / _ref - 1) > SENTINEL_BAND and (_pf, _rd) not in EXCLUDED:
                EXCLUDED[(_pf, _rd)] = ("sentinel", _scen, _v, _ref)


def round_kept(r):
    return (r["profile"], r["round"]) not in EXCLUDED


def ok(r):
    return _ok(r) and round_kept(r)


def ok_remote(r):
    return bool(r and r.get("completed") and r.get("valid_remote") and round_kept(r))


def pairs(pf, lv):
    return [(rd, D[(pf, lv, rd, "a")], D[(pf, lv, rd, "b")]) for rd in range(1, 31)
            if ok(D.get((pf, lv, rd, "a"))) and ok(D.get((pf, lv, rd, "b")))]


def paired_t(d):
    n = len(d)
    if n < 2:
        return None
    m = sum(d) / n
    sd = statistics.stdev(d)
    se = sd / math.sqrt(n)
    t, t8 = (T975[n - 1], T80[n - 1]) if n <= 31 else (1.96, 0.842)
    return dict(n=n, mean=m, sd=sd, ci=(m - t * se, m + t * se), mde=(t + t8) * se)


def median_ci(x):
    """95% CI of the median from order statistics (binomial, distribution-free)."""
    x = sorted(x)
    n = len(x)
    k = 0
    while sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n <= 0.025:
        k += 1
    if k == 0:                                   # fewer than 6 values: no 95% interval exists
        return med(x), None, None
    return med(x), x[k - 1], x[n - k]


def sign_test_p(k, n):
    m = min(k, n - k)
    return min(1.0, sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n * 2)


def kpi(P, k, div=1.0):
    A = [a["mec_" + k] / div for _, a, b in P]
    B = [b["mec_" + k] / div for _, a, b in P]
    d = [x - y for x, y in zip(A, B)]
    pc = [(1 - y / x) * 100 for x, y in zip(A, B) if x]
    win = sum(1 for v in d if v > 0)
    return dict(n=len(d), A=med(A), B=med(B), d=median_ci(d) if d else None, t=paired_t(d),
                pct=med(pc) if pc else None, win=win, p=sign_test_p(win, len(d)) if d else None, diffs=d)
