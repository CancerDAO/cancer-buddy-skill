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
#   M. phase2 §7 段D stale notice with one character changed, or its ```text block removed → fail
#   N. case-summary-html-prompt.md lead reverted to 「资料中有报告原文写到…」, the translated item form or the caveat
#      prefix dropped / reworded, or phase2 §7 quoting another lead → fail; the prompt back to the quotation-slot
#      caveat wording, listing fewer presented-as-original phrases than ACUTE_CAVEAT_ORIGINAL_CLAIMS or not asking for one
#      caveat item per finding, the validator copy drifted back to a substring count or to a quotation-slot reading or
#      no longer rejecting a claim next to the prefix, the translated caveat form without the prefix right before
#      <verbatim_text>, profile-card.md without the translation label (or calling every finding
#      报告原文), acute-findings.md §2.4 without Step 11, or SKILL.md Step 12 / phase2 §9 / §10 not routing an
#      「ERROR: .case_summary_data.json」 line to the 段D re-render, or §9 letting Phase 2 leave the missing-stale-notice
#      line too → fail
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
fresh c2; edit "$tmp/c2/$P1" 't.replace("READ_MODE: model_vision_primary\nADAPTER: temp_raster\n", "ADAPTER: temp_raster\nREAD_MODE: model_vision_primary\n", 1)'
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

# ---- M. the pinned 段D stale notice
fresh m1; edit "$tmp/m1/references/organizer-prompt-phase2-synthesis.md" 't.replace("登记时现有的病情简要总结.html 还没有写入它们", "登记时现有的病情简要总结.html 尚未写入它们", 1)'
expect "phase2 §7 stale notice reworded by one word" fail "$tmp/m1" "CASE_SUMMARY_STALE_NOTICE"
fresh m2; edit "$tmp/m2/references/organizer-prompt-phase2-synthesis.md" 't.replace("  ```text\n  本次登记了需要尽快告知治疗团队的发现", "  本次登记了需要尽快告知治疗团队的发现", 1)'
expect "phase2 §7 stale notice outside a text block" fail "$tmp/m2" "CASE_SUMMARY_STALE_NOTICE"

# ---- N. the 段D lead and the translation labels
CSP=references/case-summary-html-prompt.md
fresh n1; edit "$tmp/n1/$CSP" 't.replace("“资料中有报告写到需要尽快告知治疗团队的发现：<label>", "“资料中有报告原文写到需要尽快告知治疗团队的发现：<label>", 1)'
expect "case-summary prompt lead reverted to 报告原文写到" fail "$tmp/n1" "ACUTE_SUMMARY_LEAD"
fresh n2; edit "$tmp/n2/$CSP" 't.replace("“<label>（<日期>，中文转述）”", "“<label>（<日期>，转述）”", 1)'
expect "case-summary prompt translated item form reworded" fail "$tmp/n2" "translated item form"
fresh n3; edit "$tmp/n3/$CSP" 't.replace("中文转述，非报告原句：", "中文转述：", 2)'
expect "case-summary prompt caveat prefix reworded" fail "$tmp/n3" "ACUTE_CAVEAT_TRANSLATION_PREFIX"
fresh n4; edit "$tmp/n4/$CSP" 't.replace("  - 有 emergent/urgent 发现时", "  - 另有 emergent/urgent 发现时", 1)'
expect "case-summary prompt reworded outside the pinned strings (positive)" pass "$tmp/n4"
fresh n5; edit "$tmp/n5/references/organizer-prompt-phase2-synthesis.md" 't.replace("首句不以“资料中有报告写到需要尽快告知治疗团队的发现：”开头", "首句不以“资料中有报告原文写到需要尽快告知治疗团队的发现：”开头", 1)'
expect "phase2 §7 quoting another lead than the validator's" fail "$tmp/n5" "§7 段D 过期提示"
# N (rule): the prompt states the validator's quotation-slot rule, and its caveat forms behave as it says
fresh n6; edit "$tmp/n6/$CSP" 't.replace("按条核对：一条 caveat 只要含有某条转述发现的 `verbatim_text`（嵌在别的发现更长的原句里的不算），这一条就必须写有", "核对：转述发现的 `verbatim_text` 出现在引文位置（冒号或开引号之后，其后紧接“（”“；”“——”“。”或该条结尾；按占满这个位置的最长一条发现原句计）时，它前面必须紧挨着", 1)'
expect "case-summary prompt back to the quotation-slot caveat wording" fail "$tmp/n6" "ACUTE_CAVEAT_ITEM_RULE"
fresh n7
python3 - "$tmp/n7/scripts/validate_structured_outputs.py" <<'PY2'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
head = 'def translated_caveat_problems(acute_doc, render_data) -> list[tuple[str, dict]]:\n'
assert head in t
# the validator drifts back to the substring count the prompt no longer describes
t = t.replace(head, head + """    fs = (acute_doc or {}).get("findings") or []
    cs = [_norm_text(c["caveat_text"]) for c in (render_data or {}).get("caveats") or []]
    pre = _norm_text(ACUTE_CAVEAT_TRANSLATION_PREFIX)
    return [("caveats quote " + str(f.get("finding_id")), f) for f in fs if f.get("verbatim_is_translation") is True
            and any(c.count(_norm_text(f["verbatim_text"])) > c.count(pre + _norm_text(f["verbatim_text"])) for c in cs)]
""", 1)
p.write_text(t, encoding="utf-8")
PY2
expect "validator's caveat check drifted back to a substring count" fail "$tmp/n7" "inside another finding's 报告原文 quote"
fresh n16
python3 - "$tmp/n16/scripts/validate_structured_outputs.py" <<'PY2'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
head = 'def translated_caveat_problems(acute_doc, render_data) -> list[tuple[str, dict]]:\n'
assert head in t
# the validator drifts back to a quotation-slot reading: only a translated quote right after a colon that is not the
# prefix's own is caught — 「报告原文写明<转述>」 walks past it, and a colon inside another finding's original trips it
t = t.replace(head, head + """    import re as _re
    fs = (acute_doc or {}).get("findings") or []
    cs = [_norm_text(c["caveat_text"]) for c in (render_data or {}).get("caveats") or []]
    pre = _norm_text(ACUTE_CAVEAT_TRANSLATION_PREFIX)
    return [("caveats quote " + str(f.get("finding_id")), f) for f in fs if f.get("verbatim_is_translation") is True
            and any(_re.search("(?<!" + _re.escape(pre[:-1]) + "):" + _re.escape(_norm_text(f["verbatim_text"])), c)
                    for c in cs)]
""", 1)
p.write_text(t, encoding="utf-8")
PY2
expect "validator's caveat check drifted back to a quotation-slot reading" fail "$tmp/n16" "presents the translated finding as the report's own words"
fresh n17; edit "$tmp/n17/scripts/validate_structured_outputs.py" 't.replace("            found = claims_in(t)\n", "            found = []\n", 1)'
expect "validator no longer rejects a presented-as-original phrase next to the prefix" fail "$tmp/n17" "presents the translated finding as the report's own words"
fresh n18; edit "$tmp/n18/$CSP" 't.replace("“报告原文”“原文写”“报告写道”“报告写明”“报告原句”", "“报告原文”“原文写”“报告写明”“报告原句”", 1)'
expect "case-summary prompt listing fewer presented-as-original phrases than the validator" fail "$tmp/n18" "ACUTE_CAVEAT_ITEM_RULE"
fresh n19; edit "$tmp/n19/$CSP" 't.replace("**一条发现单独一条 caveat**", "按发现逐条", 1)'
expect "case-summary prompt without one caveat item per finding" fail "$tmp/n19" "one caveat item per finding"
fresh n8; edit "$tmp/n8/$CSP" 't.replace("“报告（外文）中文转述，非报告原句：<verbatim_text>", "“报告（外文）中文转述：<verbatim_text>，非报告原句", 1)'
expect "case-summary prompt translated caveat form without the prefix before the quote" fail "$tmp/n8" "中文转述，非报告原句：<verbatim_text>"
# N (surfaces): Profile Card labels a translation; a .case_summary_data.json ERROR routes to Step 12
fresh n9; edit "$tmp/n9/references/profile-card.md" 't.replace("- 报告写明的急性/附带发现", "- 报告原文写明的急性/附带发现", 1)'
expect "profile-card.md back to 「报告原文写明的急性/附带发现」" fail "$tmp/n9" "profile-card.md still presents"
fresh n10; edit "$tmp/n10/references/profile-card.md" 't.replace("标“中文转述，非报告原句”，不称“报告原文”", "照常显示", 1)'
expect "profile-card.md acute bullet without the translation label" fail "$tmp/n10" "does not label a verbatim_is_translation"
fresh n11; edit "$tmp/n11/references/acute-findings.md" 't.replace("（Step 7.5、Step 11 Profile Card、§11、段D）", "（Step 7.5、§11、段D）", 1)'
expect "acute-findings.md §2.4 surfaces without Step 11" fail "$tmp/n11" "does not list Step 11"
fresh n12; edit "$tmp/n12/SKILL.md" 't.replace("or its §9 run reported an `ERROR: .case_summary_data.json` line), and whenever any validator run reports such a line", "), and whenever any validator run reports a 段D error", 1)'
expect "SKILL.md Step 12 without the .case_summary_data.json ERROR trigger" fail "$tmp/n12" "SKILL.md Step 12 does not make"
fresh n13; edit "$tmp/n13/references/organizer-prompt-phase2-synthesis.md" 't.replace("以及以 `ERROR: .case_summary_data.json` 开头的行", "以及上一次 段D 渲染的错误", 1)'
expect "phase2 §9 not naming the .case_summary_data.json lines it may leave" fail "$tmp/n13" "§9 does not name"
fresh n15; edit "$tmp/n15/references/organizer-prompt-phase2-synthesis.md" 't.replace("；只有写着 “the pinned stale notice … is missing from …” 的那一行例外：它说的是你 §7 的过期提示没写全，补上后重跑", "", 1)'
expect "phase2 §9 leaving every .case_summary_data.json ERROR, the missing stale notice included" fail "$tmp/n15" "Phase 2's own §7 notice"
fresh n14; edit "$tmp/n14/references/organizer-prompt-phase2-synthesis.md" 't.replace("§9 的校验输出里有以 `ERROR: .case_summary_data.json` 开头的行时也为 true", "§9 报了 段D 错误时也为 true", 1)'
expect "phase2 §10 case_summary_rerender_required not covering the ERROR line" fail "$tmp/n14" "§10 case_summary_rerender_required"

# ---- O. read channel (ORG-P0-01/02)
fresh o1; edit "$tmp/o1/$P1" 't.replace("python3 \"<skill_dir>/scripts/second_read_align.py\" --apply", "python3 \"<skill_dir>/scripts/run_ocr_engine.py\" read", 1)'
expect "phase1 no longer running the second read through second_read_align.py" fail "$tmp/o1" "second_read_align.py"
fresh o2; edit "$tmp/o2/$P1" 't.replace("不插 token、不建条目、不出 flag", "按 flag 处理", 1)'
expect "phase1 §5.1 without the no-signal rule" fail "$tmp/o2" "no-signal rule"
fresh o3; edit "$tmp/o3/$P1" 't.replace("写正文之前不运行任何 OCR", "写正文时可参考 OCR", 1)'
expect "phase1 §4 D without the anti-anchoring rule" fail "$tmp/o3" "anti-anchoring"
fresh o4; edit "$tmp/o4/references/schemas/source_inventory.schema.json" 't.replace("\"model_vision_primary\", ", "", 1)'
expect "schema read_mode enum drifting from SIDECAR_READ_MODES" fail "$tmp/o4" "read_mode enum"
fresh o5; edit "$tmp/o5/$P1" 't.replace(" `model_vision_primary`（像素页", " （像素页", 1)'
expect "phase1 §3 READ_MODE row without model_vision_primary" fail "$tmp/o5" "phase1 §3 READ_MODE values"

# ---- P. orchestration discipline (X-P0-05 / X-P1-01 / X-P1-03)
fresh p1; edit "$tmp/p1/references/organizer-prompt-phase2-synthesis.md" 't.replace("`<skill_dir>` 在运行期只读", "`<skill_dir>` 可写", 1)'
expect "phase2 prompt without the read-only skill-dir rule" fail "$tmp/p1" "organizer-prompt-phase2-synthesis.md does not tell"
fresh p2; edit "$tmp/p2/references/pii-rescan-prompt.md" 't.replace("`<skill_dir>` 在运行期只读", "`<skill_dir>` 可写", 1)'
expect "pii-rescan prompt without the read-only skill-dir rule" fail "$tmp/p2" "pii-rescan-prompt.md does not tell"
fresh p3; edit "$tmp/p3/SKILL.md" 't.replace("--can-stop", "--final", 1)'
expect "SKILL.md without --can-stop" fail "$tmp/p3" "turn-discipline invariant"
fresh p4; edit "$tmp/p4/references/runtime-bindings/grok-build.md" 't.replace("## 4. 确认门", "## 4. 用户确认", 1)'
expect "grok binding missing a _template section" fail "$tmp/p4" "grok-build.md lacks the _template.md section"
fresh p5; rm "$tmp/p5/references/runtime-bindings/grok-build.md"
expect "grok binding removed" fail "$tmp/p5" "grok-build.md is missing"
fresh p6; edit "$tmp/p6/references/runtime-bindings/grok-build.md" 't.replace("回合结束就等于进程退出", "回合结束后会被唤醒", 1)'
expect "grok binding without the no-wake-up rule" fail "$tmp/p6" "回合结束就等于进程退出"

# ---- lint 07 (I-07): a pixel page's model transcription is never the only reading
LINT07="$REPO_ROOT/tests/eval/lint/07-clinical-governance.sh"
g07() {  # label, pass|fail, mutation (python over t) of the phase1 prompt in a copy of skills/
  local label="$1" want="$2" expr="$3" got
  rm -rf "$tmp/s07"; cp -R "$REPO_ROOT/skills" "$tmp/s07"
  [[ -n "$expr" ]] && edit "$tmp/s07/cancer-buddy-organize/$P1" "$expr"
  CB_SKILLS_DIR="$tmp/s07" bash "$LINT07" >/dev/null 2>&1 && got=pass || got=fail
  [[ "$got" == "$want" ]] && ok || no "$label: expected $want, got $got"
}
g07 "lint 07 on an untouched copy" pass ""
g07 "phase1 without 「模型转写不是唯一读数」" fail 't.replace("模型转写不是唯一读数", "模型转写即唯一读数", 1)'
g07 "phase1 without the second_read_align.py call" fail 't.replace("second_read_align.py", "an_engine.py")'

echo "organize-contract-lints: pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
