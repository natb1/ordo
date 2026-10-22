#!/usr/bin/env bash
# Everything that must pass before code here is merged or the Cadence page is
# republished. The Rule is not in the repo: it lives in the page's store, and
# tools/gate.py checks it on every write. These check the code that does that,
# on a frozen copy of the Rule (tools/fixture/rule).
set -u
fail=0
run() { echo "== $*"; "$@" || fail=1; echo; }
cd "$(dirname "$0")/.."
# The rule that decides a meeting from a fixture, a range of dates and a whole day.
run python3 -m unittest -q tools/test_rule.py
# A fixture warps the notifiers on its own dates only, and the day goes back by itself.
run python3 -m unittest -q tools/test_notifiers.py
run python3 -m unittest -q tools/test_ruledir.py
# The gate a write to the store passes: what it lets through, writes and refuses.
run python3 -m unittest -q tools/test_gate.py
# The record gate: what /ordo writes to the record, held once.
run python3 -m unittest -q tools/test_record.py
# The item contract the record gate and an owner outside this repository both check by.
run python3 -m unittest -q tools/test_items.py
# The horizon counts, over the frozen Rule and the frozen record beside it.
run python3 -m unittest -q tools/test_counts.py
run python3 tools/sync_assets.py --check
# Every citation, in the markdown and in the Rule: the frozen copy stands in for the store.
run env ORDO_RULE=tools/fixture/rule python3 tradition/check.py
# Strictly: a key given twice is an error, not a silent last-one-wins.
run python3 tools/ruleyaml.py tradition/sources.yaml
if [ "$fail" -ne 0 ]; then echo "PREFLIGHT FAILED — do not publish"; exit 1; fi
echo "PREFLIGHT OK"
