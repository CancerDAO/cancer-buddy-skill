#!/usr/bin/env bash
# Two gate false positives from a real run (all values synthetic here):
# 1. pii_rescan name_in_filename: a CJK term glued to a Latin lab name ("…Lab病理实验室-NGS…")
#    is not a personal name; a name that starts the basename / follows a digit or separator
#    still fires. (A name glued to another CJK word is left to the identity-denylist arm.)
# 2. validate_structured_outputs._yaml_value: second_read_align.py writes readings with
#    json.dumps, so a two-line engine reading carries an escaped newline; the parser must
#    unescape it or the gate rejects the script's own `## 不确定字段` entry.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import sys
repo = sys.argv[1]
sys.path.insert(0, repo + "/skills/cancer-buddy-organize/scripts")
import pii_rescan as pr
import validate_structured_outputs as vso

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


pat = pr._FILENAME_PII[0][0]
for path in ["raw/ingest/20300101-示例城Examplab病理实验室-NGS报告.pdf",
             "raw/ingest/20300101-示例国Genolab实验室-HLA分型报告.pdf"]:
    check(f"CJK term after a Latin lab name does not fire: {path}", not pat.search(path))
for path in ["raw/张测试-OncoFusion报告.pdf", "raw/20300101-张测试-Onco.pdf", "raw/x_李测试-NGS.pdf"]:
    check(f"name-shaped basename token still fires: {path}", bool(pat.search(path)))

block = ('- id: U-001\n  line: 45\n  field_class: number\n  readings:\n'
         '    - {channel: llm_vision, text: "4.3", confidence: null}\n'
         '    - {channel: "deterministic_ocr:apple_vision", text: "4\\n8.3", confidence: 1.0}\n')
ents = vso.parse_uncertain_entries(block)
check("escaped newline in a reading is unescaped", ents and ents[0]["readings"][1]["text"] == "4\n8.3", repr(ents))
check("plain quoted reading unchanged", ents and ents[0]["readings"][0]["text"] == "4.3", repr(ents))
check("single-quoted scalar keeps its content", vso._yaml_value("'a\\nb'") == "a\\nb")
check("unbalanced JSON escape falls back to the stripped text", vso._yaml_value('"a\\x"') == "a\\x")

print(f"gate-false-positive-regressions: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
