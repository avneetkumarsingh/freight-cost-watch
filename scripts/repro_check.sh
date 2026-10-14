#!/usr/bin/env bash
# Three untouched runs in fresh processes; outputs must be byte-identical.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p outputs/repro
for i in 1 2 3; do
  python3 run.py > /dev/null
  cp outputs/output.csv "outputs/repro/run$i.csv"
done
sha256sum outputs/repro/run*.csv | tee outputs/repro/checksums.txt
if diff -q outputs/repro/run1.csv outputs/repro/run2.csv && diff -q outputs/repro/run2.csv outputs/repro/run3.csv; then
  echo "REPRODUCIBLE: 3 runs identical (flags, numbers, cited notes, and reason text)" | tee -a outputs/repro/checksums.txt
else
  echo "MISMATCH between runs" ; exit 1
fi
