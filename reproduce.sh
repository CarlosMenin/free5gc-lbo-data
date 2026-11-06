#!/usr/bin/env bash
# Rebuild every derived file, table and figure from the raw data, then check
# them against the reference outputs. Takes about 30 s on a laptop.
set -euo pipefail
cd "$(dirname "$0")"

echo "== campaign: parse the raw runs into analysis/dados.json"
(cd analysis && python3 load_campaign.py)
echo "== tables (analysis/out/tables) and figures (analysis/out/...)"
(cd analysis && python3 tables.py && python3 paper_figures.py && python3 thesis_figures.py)
echo "== infrastructure metrics: windows, per-window means, paired statistics, figure and table"
(cd infrastructure-metrics && python3 build_windows.py && python3 summarize_windows.py \
   && python3 infra_stats.py > out-infra_stats.txt && python3 resources_figure.py)
echo "== verify against the reference outputs"
python3 verify.py
