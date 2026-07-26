#!/usr/bin/env bash
# Unit tests for cancer-buddy-charts layer-1 primitives (chart_core.py).
#
# These cover the three parsers whose failure modes are silent and clinical:
#   - parse_reference_range: must refuse ambiguity (sex-split ranges) rather than
#     pick a side; picking would require deciding which range applies, which is a
#     clinical judgement this codebase does not make.
#   - range_status: classifies in/out/unknown WITHOUT grading severity.
#   - censoring: '<5.0' is a bound, not a measurement of 5.0. Treating it as a
#     value is false precision — the quiet cousin of fabrication.
# Deterministic, stdlib only, no LLM.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/skills/cancer-buddy-charts/scripts"

python3 - "$SCRIPTS" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from chart_core import parse_reference_range as P, range_status as S, censoring as C

fail = 0
def eq(got, want, label):
    global fail
    if got != want:
        print(f"FAIL: {label}: got {got!r}, want {want!r}", file=sys.stderr)
        fail += 1

# ── parse_reference_range ────────────────────────────────────────────────────
for raw, want in [
    # two-sided, every separator seen in real CN/EN reports
    ("0-37", (0.0, 37.0)), ("3.50-5.50", (3.5, 5.5)), ("3.5～5.5", (3.5, 5.5)),
    ("3.5~5.5", (3.5, 5.5)), ("11–15", (11.0, 15.0)), ("0 至 5", (0.0, 5.0)),
    ("5.1-19.0 umol/L", (5.1, 19.0)),          # trailing unit stripped
    ("55-40", (40.0, 55.0)),                    # reversed bounds normalised
    # one-sided
    ("<5.0", (None, 5.0)), ("＜5.0", (None, 5.0)), ("≤37", (None, 37.0)),
    ("小于 40", (None, 40.0)), ("不高于 19.0", (None, 19.0)),
    (">10", (10.0, None)), ("≥130", (130.0, None)),
    # MUST refuse: more than one range encoded → picking one needs a clinical call
    ("男:125-350 女:100-300", None),
    ("13.0-17.5(男) 11.5-15.0(女)", None),
    # MUST refuse: not a numeric range
    ("阴性", None), ("Negative", None), ("", None), (None, None), ("  ", None),
    ("abc", None), ("-", None),
]:
    eq(P(raw), want, f"parse_reference_range({raw!r})")

# ── range_status: classification only, never severity ────────────────────────
for v, ref, want in [
    (12, (0, 37), "in"), (40, (0, 37), "out"), (37, (0, 37), "in"),
    (4.9, (None, 5.0), "in"), (5.1, (None, 5.0), "out"),
    (200, (130, None), "in"), (100, (130, None), "out"),
    ("阳性", (0, 37), "unknown"),     # non-numeric result
    (12, None, "unknown"),            # no parseable range
]:
    eq(S(v, ref), want, f"range_status({v!r}, {ref!r})")

# ── censoring ────────────────────────────────────────────────────────────────
for raw, want in [
    ("<5.0", "left"), ("＜5", "left"), ("≤3", "left"),
    (">1000", "right"), ("≥50", "right"),
    ("5.0", None), (5.0, None), (None, None),
]:
    eq(C(raw), want, f"censoring({raw!r})")

print("charts-primitives: OK" if not fail else f"charts-primitives: {fail} failure(s)")
sys.exit(1 if fail else 0)
PY
