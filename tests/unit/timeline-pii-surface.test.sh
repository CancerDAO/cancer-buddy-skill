#!/usr/bin/env bash
# tests/unit/timeline-pii-surface.test.sh — organize v3→v4 fix spec B9 (+ the A17 list).
#
# `timeline.md` was on pii_rescan's synthesized-surface list from the first day it
# existed. `timeline.json` was not — and there was never a principle behind the
# difference, only the order in which the two files got written. They are the SAME
# synthesized content: 段 2 builds both from the same masked sidecars, every downstream
# sub-skill reads the JSON in preference to the prose, and export_share.py ships it. So
# a 手机号 that would have been caught the moment it appeared in `timeline.md` sailed
# straight through in `timeline.json` — same run, same sentence, same patient, one file
# extension apart. B9 adds `timeline.json` to SYNTHESIZED_SURFACES.
#
# The wider rule (A17) is that the deterministic shape floor scans what SHIPS. The
# synthesized list therefore gained `extracted_fields.json`, `readiness.json`,
# `.case_summary_data.json` and the structured JSON products, and LOST two 段 1 build
# intermediates — `.rename_plan.json` and `.phase1_sources.json` — which no longer
# exist in the v4 contract. Scanning a file that is never produced generates findings
# nobody can act on, and a gate that cries wolf on phantom paths is a gate people learn
# to pass with `|| true`.
#
# This file asserts the constant AND the behaviour, because either one alone is
# consistent with a broken gate:
#   * the constant alone would pass on a build where the name was added to the list but
#     nothing ever iterates that list (「加了常量但没走到」);
#   * the behaviour alone would pass if the hit arrived by some other route — a
#     directory-wide *.json sweep, say — in which case the list is decorative and the
#     next file dropped from it is still scanned, until the day it is not
#     (「走到了但靠别的路径」).
# So the negative controls below also prove the scan is driven BY THE LIST: the same
# phone number placed in a JSON that is deliberately NOT on either list must go
# unreported, and the same number in a removed A17 intermediate must go unreported too.
#
# The positive arm matters just as much. `timeline.json` legitimately embeds
# de-identified raw filenames like `微信图片_20260220175937.jpg` — a 14-digit timestamp
# that is not PII. If adding the file to the list fail-closed every clean archive on
# that shape, the entry would be reverted within a week and the real leak path would
# reopen. Hence `drop_numeric_id` on clinical-prose surfaces, asserted here.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
RESCAN="$ORG/scripts/pii_rescan.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# Run the gate exactly the way 段 1 / export_share invoke it: one patient_dir argument.
run_rescan() {  # <patient_dir>
  set +e
  out="$(python3 "$RESCAN" "$1" 2>&1)"
  rc=$?
  set +e
}

# Ask the scanner's own API which surfaces it found residue on — this is the binding
# under test (scan_delivered_surfaces iterates DELIVERED_SURFACES + SYNTHESIZED_SURFACES),
# reported as "<file>\t<rule_id>" lines so both halves can be asserted.
scan_api() {  # <patient_dir>
  set +e
  api="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
pr = importlib.import_module("pii_rescan")
surfaces, _deny = pr.scan_delivered_surfaces(pathlib.Path(sys.argv[2]))
for name, findings in sorted(surfaces.items()):
    for _line, rule, _snippet in findings:
        print(f"{name}\t{rule}")
PYEOF
)"
  set +e
}

mk_patient() {  # <dir>
  mkdir -p "$1"
}

# <dir> <description string for events[0]>
timeline_json() {
  python3 - "$1" "$2" <<'PYEOF'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
doc = {
    "patient_code": "PT-0E11",
    "schema_version": "2",
    "events": [
        {
            "date": "2026-03-15",
            "category": "treatment",
            "title": "第 1 周期化疗",
            "description": sys.argv[2],
            "provenance_layer": "source_reported",
            "verification_status": "unverified",
            "source_refs": ["08_治疗/化疗/2026-03-15_第1周期.md"],
        }
    ],
}
(d / "timeline.json").write_text(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PYEOF
}

CN_MOBILE="13812345678"

# ===========================================================================
# A. the CONSTANT — timeline.json is on the synthesized-surface list
# ===========================================================================
echo "=== A. pii_rescan.SYNTHESIZED_SURFACES ==="

set +e
lists="$(python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
pr = importlib.import_module("pii_rescan")
print("SYN", "\x1f".join(pr.SYNTHESIZED_SURFACES))
print("DEL", "\x1f".join(pr.DELIVERED_SURFACES))
PYEOF
)"
set +e
syn="$(printf '%s\n' "$lists" | sed -n 's/^SYN //p' | tr '\037' '\n')"
del="$(printf '%s\n' "$lists" | sed -n 's/^DEL //p' | tr '\037' '\n')"
both="$(printf '%s\n%s\n' "$syn" "$del")"

printf '%s\n' "$syn" | grep -qx 'timeline.json' \
  && ok "SYNTHESIZED_SURFACES contains 'timeline.json' verbatim (B9)" \
  || no "timeline.json is NOT on the synthesized list: $syn"
printf '%s\n' "$syn" | grep -qx 'timeline.md' \
  && ok "…alongside timeline.md — the prose and machine faces of one artifact, scanned alike" \
  || no "timeline.md fell off the list: $syn"

# A17 ADDITIONS. Read off the real constant rather than invented from the spec text:
# the open-field ledger, the run's own state file, the case-summary data blob, and
# every structured JSON product a consumer reads.
for f in extracted_fields.json readiness.json .case_summary_data.json; do
  printf '%s\n' "$syn" | grep -qx -- "$f" \
    && ok "SYNTHESIZED_SURFACES contains '$f' (A17)" || no "'$f' missing from the list: $syn"
done

# The structured products are enumerated by the VALIDATOR (STRUCTURED_FILES), so this
# arm fails the day a new structured output is added and nobody adds it to the PII
# surface — which is exactly how timeline.json came to be missing in the first place.
set +e
uncovered="$(python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
pr = importlib.import_module("pii_rescan")
v = importlib.import_module("validate_structured_outputs")
covered = set(pr.SYNTHESIZED_SURFACES) | set(pr.DELIVERED_SURFACES)
missing = sorted(n for n in v.STRUCTURED_FILES if n not in covered)
print(" ".join(missing))
PYEOF
)"
set +e
[ -z "$(printf '%s' "$uncovered" | tr -d '[:space:]')" ] \
  && ok "every structured product in validator STRUCTURED_FILES is on a scanned surface list" \
  || no "structured products ship unscanned: $uncovered"

# A17 DELETIONS — the other half, and the one a spec reader is most likely to skip.
for f in .rename_plan.json .phase1_sources.json; do
  printf '%s\n' "$both" | grep -qx -- "$f" \
    && no "'$f' is still on a scanned surface list — it no longer exists in the v4 contract" \
    || ok "'$f' is NOT on any scanned surface list (A17 removal)"
done

# ===========================================================================
# B. NEGATIVE — a 中国手机号 inside timeline.json events[].description
# ===========================================================================
echo "=== B. a phone number in a timeline event description ==="

d="$tmp/leak"; mk_patient "$d"
timeline_json "$d" "患者自述联系电话 ${CN_MOBILE}，本周期后回院复查。"

scan_api "$d"
printf '%s\n' "$api" | grep -q '^timeline\.json	' \
  && ok "scan_delivered_surfaces() reports a finding ON timeline.json" \
  || no "the synthesized-surface scan did not reach timeline.json: ${api:-<none>}"
printf '%s\n' "$api" | grep -qx 'timeline.json	phone' \
  && ok "…and the rule that fired is the phone shape (中国手机 1[3-9]\\d{9}), not an incidental match" \
  || no "wrong rule id for a CN mobile: ${api:-<none>}"

run_rescan "$d"
[ "$rc" -eq 1 ] && ok "pii_rescan.py <patient_dir> → exit 1" \
  || no "the CLI passed an archive with a plaintext phone number in timeline.json, rc=$rc"
printf '%s\n' "$out" | grep -q 'RESIDUE (delivered surface)' \
  && ok "…reported through the delivered/synthesized-surface path (not the sidecar path)" \
  || no "the finding did not come from the surface scan: $out"
printf '%s\n' "$out" | grep -q 'timeline.json' \
  && ok "…and the report NAMES timeline.json" || no "the file is not named in the report: $out"
printf '%s\n' "$out" | grep -q "\[phone\]" \
  && ok "…and names the rule that fired" || no "rule id absent from the report: $out"
printf '%s\n' "$out" | grep -q "$CN_MOBILE" \
  && ok "…and quotes the offending token so a human can find the line" || no "token not quoted: $out"
printf '%s\n' "$out" | grep -q 'delivered_surface_findings=1' \
  && ok "…and the machine summary counts exactly one surface finding" || no "bad summary line: $out"

# the same floor catches the 18-digit 身份证 on this surface too — the entry added the
# FILE to the scan, not one regex to the file
d="$tmp/leak_id"; mk_patient "$d"
timeline_json "$d" "入院登记身份证 110101199003072316，随即开始治疗。"
scan_api "$d"
printf '%s\n' "$api" | grep -qx 'timeline.json	id_number' \
  && ok "an 18-digit 身份证 in the same field also fires (id_number)" \
  || no "only the phone shape reaches timeline.json: ${api:-<none>}"

# ===========================================================================
# C. POSITIVE — a clean timeline.json is not flagged
# ===========================================================================
echo "=== C. the same file with no PII shape ==="

d="$tmp/clean"; mk_patient "$d"
timeline_json "$d" "第 1 周期 AC 方案化疗，耐受可，未见 3 级以上不良反应。"
scan_api "$d"
[ -z "$(printf '%s' "$api" | tr -d '[:space:]')" ] \
  && ok "clinical prose with no identifier shape → no finding" \
  || no "a clean timeline.json was flagged: $api"
run_rescan "$d"
[ "$rc" -eq 0 ] && ok "pii_rescan.py <patient_dir> → exit 0" \
  || no "a clean archive was blocked, rc=$rc: $out"
printf '%s\n' "$out" | grep -q 'delivered_surface_findings=0' \
  && ok "…and the summary reports zero surface findings" || no "bad summary line: $out"

# The de-identified raw-filename timestamp: 14 consecutive digits that are NOT PII.
# Without drop_numeric_id on clinical-prose surfaces this fires on essentially every
# real archive, the B9 entry gets reverted, and the actual leak path reopens.
d="$tmp/timestamp"; mk_patient "$d"
timeline_json "$d" "影像来源 微信图片_20260220175937.jpg（患者上传，已去标识）。"
scan_api "$d"
[ -z "$(printf '%s' "$api" | tr -d '[:space:]')" ] \
  && ok "a 14-digit de-identified filename timestamp does NOT fire (loose numeric_id suppressed on prose surfaces)" \
  || no "the gate fail-closes on every archive carrying a de-identified upload name: $api"

# ===========================================================================
# D. the scan is driven BY THE LIST, not by 「every .json in the directory」
# ===========================================================================
echo "=== D. list-driven, not sweep-driven ==="

# A JSON the contract deliberately keeps OFF both lists (intermediate render state).
# If the same phone number were reported here, the lists would be decorative and every
# assertion above would be measuring the wrong mechanism.
set +e
offlist="$(python3 - "$ORG" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
pr = importlib.import_module("pii_rescan")
name = "visit_prep_data.json"
print(int(name not in pr.SYNTHESIZED_SURFACES and name not in pr.DELIVERED_SURFACES))
PYEOF
)"
set +e
[ "$offlist" = "1" ] && ok "visit_prep_data.json is on neither list (a valid off-list control)" \
  || no "the control file is itself listed; pick another"

d="$tmp/offlist"; mk_patient "$d"
printf '{"phone":"%s"}\n' "$CN_MOBILE" > "$d/visit_prep_data.json"
scan_api "$d"
[ -z "$(printf '%s' "$api" | tr -d '[:space:]')" ] \
  && ok "the same phone number in an off-list JSON is NOT reported → discovery is by name, not by sweep" \
  || no "the surface scan swept the directory; the lists are decorative: $api"

# and the A17 removals, behaviourally: a leftover 段 1 intermediate is out of scope for
# THIS gate (export_share refuses leftovers outright — that is where they are caught)
d="$tmp/removed"; mk_patient "$d"
printf '{"phone":"%s"}\n' "$CN_MOBILE" > "$d/.rename_plan.json"
printf '{"phone":"%s"}\n' "$CN_MOBILE" > "$d/.phase1_sources.json"
scan_api "$d"
[ -z "$(printf '%s' "$api" | tr -d '[:space:]')" ] \
  && ok ".rename_plan.json / .phase1_sources.json are not scanned (A17 removal, behaviour matches constant)" \
  || no "a removed intermediate is still scanned: $api"

# both halves in one archive: the listed file fires, the unlisted ones stay silent
d="$tmp/mixed"; mk_patient "$d"
timeline_json "$d" "联系电话 $CN_MOBILE"
printf '{"phone":"%s"}\n' "$CN_MOBILE" > "$d/.rename_plan.json"
printf '{"phone":"%s"}\n' "$CN_MOBILE" > "$d/visit_prep_data.json"
scan_api "$d"
[ "$(printf '%s\n' "$api" | grep -c .)" = "1" ] \
  && ok "3 files carry the same number, exactly 1 finding — the list decides" \
  || no "expected exactly one finding, got: $api"
printf '%s\n' "$api" | grep -qx 'timeline.json	phone' \
  && ok "…and it is timeline.json" || no "the wrong file fired: $api"

# ---------------------------------------------------------------------------
echo
echo "== timeline-pii-surface: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
