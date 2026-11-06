#!/usr/bin/env python3
"""Check that the regenerated outputs match the ones used in the paper.

Run after reproduce.sh (or let reproduce.sh call it). Exit code 0 means every
derived file and every table is identical to the shipped reference.
"""
import filecmp, glob, hashlib, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# SHA-256 of the derived files as shipped (identical to the files used in the paper).
DERIVED = {
    "analysis/dados.json":
        "aea3a5cf49cee10b2d18fccbcb9ad72cbdfac72f6e1e3cfe91cd44dcd4136192",
    "infrastructure-metrics/janelas.csv":
        "3fb8a47fd46be64b701bff7dd85e4bf07e1a86b1739937fe3e297d85d3dfe104",
    "infrastructure-metrics/metricas-por-janela.csv":
        "77d949b5a25264f9c4c04121b41ad7681c08cd8d9d5317443f7411c25af989fc",
    "infrastructure-metrics/infra-pareado.json":
        "2f157556d1c1f5294ee9f793e6d259adc12828b5df078bf097d9bd4a00a414d9",
}

TABLE_PAIRS = [(os.path.join("analysis", "out", "tables"), os.path.join("analysis", "expected", "tables")),
               (os.path.join("infrastructure-metrics", "out"), os.path.join("infrastructure-metrics", "expected"))]


def sha256(path):
    with open(os.path.join(ROOT, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    bad = 0
    for path, ref in DERIVED.items():
        ok = sha256(path) == ref
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
        print(("ok    " if ok else "MISS  ") + os.path.relpath(p, ROOT) + "  (compare visually with analysis/expected/paper-figures/)")
    print("\nall outputs match" if not bad else "\n%d output(s) differ" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
