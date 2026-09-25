#!/usr/bin/env bash
# tests/eval/lint/13-organize-prompt-contracts.sh — each check fires on a copy of the
# organize skill with ONE thing broken, and the untouched copy passes (positive control).
#   A. SKILL.md 51,201 bytes                         → fail
#   B. lexicon line `O药 | 纳武利尤单抗` / duplicate / padded / empty → fail
#   C. phase1 §3 header example without PAGE_LABEL / with two keys swapped,
#      SOURCE list drifting from the validator             → fail
#   D. acute-findings.md §3 table missing a class / an extra class /
#      a default acuity ≠ the validator's fixed table      → fail
#   E. phase1 §5 example lists a field_class / layout the validator rejects, or a layout line
#      with no parseable value → fail; a strict subset of the validator's values → pass
#   F. a references/*.md or SKILL.md line quoting a stale-source sentence other than
#      source_freshness.STALE_WARNING_TEMPLATE → fail; the template itself → pass; one character
#      changed in the phase2 §6.2 copy, the SKILL.md Step 8 copy deleted, or the
#      patient-profile-schema.md readiness example reverted to the old wording → fail
#   G. phase2 §0 run_mode list without legacy_upgrade, or the retired boolean parameter
#      documented again → fail
#   H. acute-findings.md §4.1 block missing a chronic word / listing an extra class / gone → fail
#   I. phase1 §3 READ_MODE row with a value the validator rejects → fail
#   J. a prompt running `python3 scripts/…`, a binding's own base path, or a charts script as
#      `../cancer-buddy-charts/…` (relative to the caller's cwd) → fail
#   K. phase2 §6.1 untrusted row not stating the scanner's grading → fail
#   L. a recursive rm naming "$src" (SKILL.md) or "<patient_dir>/raw" (a reference) → fail; the Step 17 rm of
#      the archive unpack dir, with prose naming $src and raw/ beside it, passes (positive control)
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LINT="$REPO_ROOT/tests/eval/lint/13-organize-prompt-contracts.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
ok() { pass=$((pass+1)); }
no() { echo "FAIL: $1" >&2; fail=$((fail+1)); }

fresh() {  # fresh copy of the organize skill at $tmp/$1
  rm -rf "$tmp/$1"; cp -R "$REPO_ROOT/skills/cancer-buddy-organize" "$tmp/$1"
}
expect() {  # label, pass|fail, dir, [expected stderr substring]; $REFS overrides repo references/
  local label="$1" want="$2" dir="$3" needle="${4:-}" got out
  out="$(CB_ORG_DIR="$dir" CB_REPO_REFS_DIR="${REFS:-$REPO_ROOT/references}" bash "$LINT" 2>&1)" && got=pass || got=fail
  if [[ "$got" != "$want" ]]; then no "$label: expected $want, got $got"; echo "$out" | tail -5 >&2; return; fi
  if [[ -n "$needle" ]] && ! grep -qF -- "$needle" <<<"$out"; then no "$label: output lacks '$needle'"; echo "$out" | tail -5 >&2; return; fi
  ok
}
edit() {  # file, python expression over `t` producing the new text
  python3 - "$1" "$2" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
new = eval(sys.argv[2], {"t": t})
assert new != t, "mutation did not change the file"
p.write_text(new, encoding="utf-8")
PY
}

fresh base
expect "positive control: untouched skill copy" pass "$tmp/base"

# ---- A. SKILL.md budget
fresh a1
python3 - "$tmp/a1/SKILL.md" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1]); b = p.read_bytes()
p.write_bytes(b + b"x" * (51201 - len(b)))
PY
expect "SKILL.md of 51,201 bytes" fail "$tmp/a1" "SKILL.md is 51201 bytes"
fresh a2
python3 - "$tmp/a2/SKILL.md" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1]); b = p.read_bytes()
p.write_bytes(b + b"x" * (51200 - len(b)))
PY
expect "SKILL.md of exactly 51,200 bytes" pass "$tmp/a2"

# ---- B. lexicon hygiene
LEX=references/lexicons/oncology_drugs.txt
fresh b1; printf 'O药 | 纳武利尤单抗\n' >> "$tmp/b1/$LEX"
expect "mapping line 'O药 | 纳武利尤单抗'" fail "$tmp/b1" "is a mapping, not a single term"
fresh b2; printf 'K药 → 帕博利珠单抗\n' >> "$tmp/b2/$LEX"
expect "arrow mapping line" fail "$tmp/b2" "is a mapping"
fresh b3; head -1 "$tmp/b3/$LEX" >> "$tmp/b3/$LEX"
expect "duplicate lexicon line" fail "$tmp/b3" "duplicate of line 1"
fresh b4; printf ' 示例药 \n' >> "$tmp/b4/$LEX"
expect "padded lexicon line" fail "$tmp/b4" "leading/trailing whitespace"
fresh b5; printf '\n示例药C\n' >> "$tmp/b5/$LEX"
expect "empty lexicon line" fail "$tmp/b5" "empty line"
fresh b6; printf '示例药C\n' >> "$tmp/b6/$LEX"
expect "a new plain term passes" pass "$tmp/b6"

# ---- C. phase1 §3 header keys + SOURCE list
P1=references/organizer-prompt-phase1-ocr.md
fresh c1; edit "$tmp/c1/$P1" 't.replace("PAGE_LABEL: 第2页，共3页\n", "", 1)'
expect "phase1 §3 example without PAGE_LABEL" fail "$tmp/c1" "header example keys"
fresh c2; edit "$tmp/c2/$P1" 't.replace("READ_MODE: model_vision_assist\nADAPTER: temp_raster\n", "ADAPTER: temp_raster\nREAD_MODE: model_vision_assist\n", 1)'
expect "phase1 §3 example with two keys swapped" fail "$tmp/c2" "pinned order"
fresh c3; edit "$tmp/c3/$P1" 't.replace(" `certificate`", "", 1)'
expect "phase1 §3 SOURCE list drifts from the validator" fail "$tmp/c3" "SIDECAR_SOURCE_TYPES"

# ---- D. acute-findings §3 table ↔ schema enum ↔ validator defaults
AF=references/acute-findings.md
fresh d1; edit "$tmp/d1/$AF" '"\n".join(l for l in t.split("\n") if not l.startswith("| `other_source_flagged`"))'
expect "acute table missing a finding_class" fail "$tmp/d1" "≠ schema finding_class enum"
fresh d2; edit "$tmp/d2/$AF" 't.replace("| `perforation_free_air` | emergent | — |", "| `perforation_free_air` | emergent | — |\n| `bogus_class` | urgent | — |", 1)'
expect "acute table with an extra class" fail "$tmp/d2" "≠ schema finding_class enum"
fresh d3; edit "$tmp/d3/$AF" 't.replace("| `obstruction`（肠/胆/尿路/气道梗阻） | urgent |", "| `obstruction`（肠/胆/尿路/气道梗阻） | emergent |", 1)'
expect "acute table default ≠ validator fixed table" fail "$tmp/d3" "obstruction default 'emergent'"

# ---- E. phase1 §5 uncertainty vocabulary ⊆ validator
FC_LIST="# drug_name | ihc_marker | ln_station | date | number | unit | stage | variant | diagnosis_text | regimen_connector | cycle_number | other"
LAYOUT_LIST="# none | strikethrough | overprint | crop | stamp | shadow_stain_fold"
grep -qF -- "$FC_LIST" "$REPO_ROOT/skills/cancer-buddy-organize/$P1" || no "harness: phase1 §5 field_class comment changed — update FC_LIST"
grep -qF -- "$LAYOUT_LIST" "$REPO_ROOT/skills/cancer-buddy-organize/$P1" || no "harness: phase1 §5 layout comment changed — update LAYOUT_LIST"
fresh e1; edit "$tmp/e1/$P1" 't.replace("| cycle_number | other", "| cycle_number | bogus_class | other", 1)'
expect "phase1 §5 field_class the validator rejects" fail "$tmp/e1" "UNCERTAIN_FIELD_CLASSES"
fresh e2; edit "$tmp/e2/$P1" 't.replace("| stamp | shadow_stain_fold", "| stamp | shadow | shadow_stain_fold", 1)'
expect "phase1 §5 layout the validator rejects" fail "$tmp/e2" "UNCERTAIN_LAYOUTS"
fresh e3; edit "$tmp/e3/$P1" 't.replace(" | diagnosis_text | regimen_connector", "", 1).replace(" | shadow_stain_fold", "", 1)'
expect "phase1 §5 listing a strict subset of the validator's values passes" pass "$tmp/e3"
fresh e4; edit "$tmp/e4/$P1" "t.replace('$LAYOUT_LIST', '# 见 §6', 1)"
expect "phase1 §5 layout line without parseable values" fail "$tmp/e4" "UNCERTAIN_LAYOUTS"
fresh e5; edit "$tmp/e5/$P1" "t.replace('$FC_LIST', '# 见下文', 1)"
expect "phase1 §5 field_class line without parseable values" fail "$tmp/e5" "UNCERTAIN_FIELD_CLASSES"

# ---- F. stale-source sentence = source_freshness.STALE_WARNING_TEMPLATE
P2=references/organizer-prompt-phase2-synthesis.md
fresh f1; edit "$tmp/f1/$P2" 't + "\n时效提示写：“档案中最新资料日期为 X，距本次整理 N 天；请确认是否有更新的检查或记录”。\n"'
expect "a prompt teaching another stale-source wording" fail "$tmp/f1" "STALE_WARNING_TEMPLATE"
TPL="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import source_freshness as s; print(s.STALE_WARNING_TEMPLATE.format(latest="X", days="N"))' "$REPO_ROOT/skills/cancer-buddy-organize/scripts")"
TPL_EX="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import source_freshness as s; print(s.STALE_WARNING_TEMPLATE.format(latest="2024-07-05", days=15))' "$REPO_ROOT/skills/cancer-buddy-organize/scripts")"
fresh f2; edit "$tmp/f2/$P2" "t + '\n时效提示原样写：“${TPL}”\n'"
expect "a prompt quoting the canonical template passes" pass "$tmp/f2"
RAW_TPL="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import source_freshness as s; print(s.STALE_WARNING_TEMPLATE)' "$REPO_ROOT/skills/cancer-buddy-organize/scripts")"
fresh f3; edit "$tmp/f3/$P2" "t.replace('${RAW_TPL}', '${RAW_TPL}'.replace('请确认此后', '请确认之后'), 1)"
expect "phase2 §6.2 template copy with one character changed" fail "$tmp/f3" "§6.2 has no \`\`\`text block"
fresh f4; edit "$tmp/f4/SKILL.md" "t.replace('“${RAW_TPL}”', '', 1)"
expect "SKILL.md Step 8 without the template" fail "$tmp/f4" "SKILL.md Step 8 does not quote"
fresh f5; edit "$tmp/f5/SKILL.md" "t + '\n8. 时效：“档案中最新资料日期为 X，距本次整理 N 天；请确认是否有更新的检查或记录”。\n'"
expect "SKILL.md teaching another stale-source wording" fail "$tmp/f5" "SKILL.md:"
fresh f6; mkdir -p "$tmp/refs6"; cp "$REPO_ROOT/references/patient-profile-schema.md" "$tmp/refs6/"
edit "$tmp/refs6/patient-profile-schema.md" "t.replace('${TPL_EX}', '档案中最新资料日期为 2024-07-05，距本次整理 15 天；请确认是否有更新的检查或记录', 1)"
REFS="$tmp/refs6" expect "patient-profile-schema.md readiness example reverted to the old wording" fail "$tmp/f6" "readiness example warnings[0]"
fresh f7; mkdir -p "$tmp/refs7"; cp "$REPO_ROOT/references/patient-profile-schema.md" "$tmp/refs7/"
REFS="$tmp/refs7" expect "an untouched copy of patient-profile-schema.md passes" pass "$tmp/f7"

# ---- G. run_mode vocabulary (D1)
fresh g1; edit "$tmp/g1/$P2" 't.replace("`legacy_upgrade`（§4.0）| ", "", 1)'
expect "phase2 §0 run_mode list without legacy_upgrade" fail "$tmp/g1" "run_mode list lacks ['legacy_upgrade']"
fresh g2; edit "$tmp/g2/$P2" 't.replace("`prior_archive_authorized`（布尔）", "`prior_archive_authorized`（布尔）、`legacy_upgrade`（布尔，§4.0）", 1)'
expect "phase2 re-documenting the retired boolean parameter" fail "$tmp/g2" "retired boolean legacy_upgrade"
fresh g3; edit "$tmp/g3/SKILL.md" 't.replace("`run_mode: \"legacy_upgrade\"`", "`run_mode: \"full\"` + `legacy_upgrade: true`", 1)'
expect "SKILL.md documenting legacy_upgrade: true" fail "$tmp/g3" "SKILL.md:"

# ---- H. acute-findings.md §4.1 pinned words ↔ validator constants
AFM=references/acute-findings.md
fresh h1; edit "$tmp/h1/$AFM" 't.replace("source_wording_chronic: 陈旧 | 慢性 | old | chronic", "source_wording_chronic: 陈旧 | 慢性 | old | chronic | 无显著变化", 1)'
expect "§4.1 teaching an extra chronic word (无显著变化)" fail "$tmp/h1" "§4.1 \`source_wording_chronic:\`"
fresh h2; edit "$tmp/h2/$AFM" 't.replace("chronic_classes: thrombus_embolism | hemorrhage | fracture_cortical_break", "chronic_classes: thrombus_embolism | hemorrhage | fracture_cortical_break | obstruction", 1)'
expect "§4.1 listing an extra class with a chronic adjustment" fail "$tmp/h2" "§4.1 \`chronic_classes:\`"
fresh h3; edit "$tmp/h3/$AFM" 't.replace("### 4.1 调整依据的固定用词", "### 调整依据的固定用词", 1)'
expect "acute-findings.md without its §4.1 block" fail "$tmp/h3" "no \`### 4.1\` section"

# ---- I. phase1 §3 READ_MODE / ADAPTER / MODALITY ↔ validator
P1=references/organizer-prompt-phase1-ocr.md
fresh i1; edit "$tmp/i1/$P1" 't.replace("`stub_unreadable` `prior_archive_digest` |", "`stub_unreadable` `prior_archive_digest` `fast_read` |", 1)'
expect "phase1 §3 READ_MODE row with a value the validator rejects" fail "$tmp/i1" "phase1 §3 READ_MODE values"

# ---- J. script calls resolve against <skill_dir>
fresh j1; edit "$tmp/j1/references/organizer-prompt-phase2-synthesis.md" 't.replace("python3 \"<skill_dir>/scripts/page_completeness.py\"", "python3 scripts/page_completeness.py", 1)'
expect "a worker prompt running scripts/… relative to its cwd" fail "$tmp/j1" "without the <skill_dir>/ prefix"
fresh j2; edit "$tmp/j2/references/runtime-bindings/headless-codex.md" 't.replace("python3 \"<skill_dir>/scripts/render_html_template.py\"", "python3 skills/cancer-buddy-organize/scripts/render_html_template.py", 1)'
expect "a runtime binding using its own base path" fail "$tmp/j2" "without the <skill_dir>/ prefix"

fresh j3; edit "$tmp/j3/SKILL.md" 't.replace("python3 \"<skill_dir>/../cancer-buddy-charts/scripts/render_chart.py\"", "python3 ../cancer-buddy-charts/scripts/render_chart.py", 1)'
expect "the orchestrator's chart call relative to its own cwd" fail "$tmp/j3" "without the <skill_dir>/ prefix"
fresh j4; edit "$tmp/j4/references/case-summary-html-prompt.md" 't.replace("python3 \"<skill_dir>/../cancer-buddy-charts/scripts/render_chart.py\"", "python3 ../cancer-buddy-charts/scripts/render_chart.py", 1)'
expect "the 段D chart call relative to its cwd" fail "$tmp/j4" "without the <skill_dir>/ prefix"

# ---- L. no recursive rm on $src / raw/ / the patient directory
fresh l1; edit "$tmp/l1/SKILL.md" 't.replace("find \"<patient_dir>\" -name .DS_Store -type f -delete\n", "find \"<patient_dir>\" -name .DS_Store -type f -delete; rm -rf \"$src\"   # the unpack dir\n", 1)'
expect "Step 17 removing \$src (the user's folder or the raw/ vault)" fail "$tmp/l1" "recursive rm on \"\$src\""
fresh l2; edit "$tmp/l2/references/relevance-gate.md" 't + "\n```bash\nrm -r -f \"<patient_dir>/raw\"\n```\n"'
expect "a reference removing <patient_dir>/raw" fail "$tmp/l2" "recursive rm on"
fresh l3; edit "$tmp/l3/references/runtime-bindings/claude-code.md" 't + "\n- 清理：`rm -rf ${src}/tmp` 之后继续。\n"'
expect "a binding removing under \${src}" fail "$tmp/l3" "recursive rm on"
fresh l4; edit "$tmp/l4/SKILL.md" 't.replace("rm -rf \"$unpack_dir\"", "rm -f \"$unpack_dir\"", 1)'
expect "a non-recursive rm is out of scope (positive)" pass "$tmp/l4"

# ---- K. untrusted-content severity row = the scanner's grading
fresh k1; edit "$tmp/k1/references/organizer-prompt-phase2-synthesis.md" 't.replace("最高命中为 high → `yellow`，其余 `info`", "`yellow`", 1)'
expect "phase2 §6.1 grading untrusted markers yellow regardless of the scanner" fail "$tmp/k1" "不可信内容标记 row"

echo "organize-contract-lints: pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
