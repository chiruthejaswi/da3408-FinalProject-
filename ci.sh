#!/usr/bin/env bash
# Local CI driven by DVC: a change to code/params/data re-runs only the affected stages.
set -euo pipefail
echo "== 1/4 lint";         ruff check . --select E,F --line-length 130
echo "== 2/4 dvc repro";    dvc repro
echo "== 3/4 dvc dag";      dvc dag | tee docs/dvc_dag.txt
echo "== 4/4 tests+report"; python make_test_report.py
echo "CI OK  commit=$(git rev-parse --short HEAD 2>/dev/null || echo n/a)"
