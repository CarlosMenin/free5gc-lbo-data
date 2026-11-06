#!/usr/bin/env python3
"""Check that the regenerated outputs match the ones used in the paper.

Run after reproduce.sh (or let reproduce.sh call it). Exit code 0 means every
derived file and every table is identical to the shipped reference.
"""
import filecmp, glob, hashlib, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# SHA-256 of the derived files as shipped (the tables built from them are identical
# to the ones used in the paper).
DERIVED = {
    "analysis/runs.json": "c9d83069b00904ca7c810c96077f334580966783e070d2742c39a1f2419a85a0",
    "infrastructure-metrics/windows.csv": "4ca7b4b03da992f531758e8c38d1a4b2cfe863eaf1feef853252671509d6aa25",
    "infrastructure-metrics/metrics-per-window.csv": "603f33ee9274db68f949b1ec0c56bbfa9ff5db0370b7d0e3a02aa42c65e1577f",
    "infrastructure-metrics/infra-paired.json": "6a96ac5eb566480104d65ee3027b3383aa53f36dab2be34ca7044207511a97ef",
}

TABLE_PAIRS = [(os.path.join("analysis", "out", "tables"), os.path.join("analysis", "expected", "tables")),
               (os.path.join("infrastructure-metrics", "out"), os.path.join("infrastructure-metrics", "expected"))]


def sha256(path):
    with open(os.path.join(ROOT, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    bad = 0
    for path, ref in DERIVED.items():
        ok = os.path.exists(os.path.join(ROOT, path)) and sha256(path) == ref
        bad += not ok
        print(("ok    " if ok else "DIFF  ") + path)
    for out, exp in TABLE_PAIRS:
        for ref in sorted(glob.glob(os.path.join(ROOT, exp, "*.tex"))):
            new = os.path.join(ROOT, out, os.path.basename(ref))
            ok = os.path.exists(new) and filecmp.cmp(ref, new, shallow=False)
            bad += not ok
            print(("ok    " if ok else "DIFF  ") + os.path.relpath(new, ROOT))
    for fig in ("results-load-levels.pdf", "results-offered-load.pdf"):
        p = os.path.join(ROOT, "analysis", "out", "paper-figures", fig)
        ok = os.path.exists(p)
        bad += not ok
        print(("ok    " if ok else "MISS  ") + os.path.relpath(p, ROOT)
              + "  (compare visually with analysis/expected/paper-figures/)")
    print("\nall outputs match" if not bad else "\n%d output(s) differ" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
