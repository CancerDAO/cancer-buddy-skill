#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$ROOT/skills/cancer-buddy-organize"
RUN="$ORG/scripts/run_context.py"
PII="$ORG/scripts/semantic_pii_gate.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
patient="$tmp/PT-A1B2C3"
mkdir -p "$patient/ocr"

cat > "$patient/ocr/SRC-DEMO.md" <<'EOF'
SOURCE: SRC-DEMO | confidence=high | report_type=病理报告
READ_MODE: model_vision_assist
FILE_ID: FILE-DEMO

患者张三，联系人张三。
检查日期：2026-08-01
来源机构：示例医院
EOF

start_json="$(python3 "$RUN" start "$patient")"
run_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<<"$start_json")"
[[ "$run_id" == RUN-* ]]
resume_json="$(python3 "$RUN" start "$patient")"
python3 -c 'import json,sys; assert json.load(sys.stdin)["resumed"] is True' <<<"$resume_json"
if python3 "$RUN" start "$patient" --run-id RUN-20000101T000000Z-ABCDEF >/dev/null; then
  echo "FAIL: mismatched active run accepted" >&2; exit 1
fi

before_json="$(python3 "$PII" scope "$patient" --run-id "$run_id" --stage phase1 --pass before)"
before_scope="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["scope_path"])' <<<"$before_json")"
before_report="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["report_path"])' <<<"$before_json")"
python3 - "$before_scope" "$before_report" "$run_id" <<'PY'
import json, pathlib, sys
scope = json.loads(pathlib.Path(sys.argv[1]).read_text())
report = {
  "schema": "semantic_pii_report_v1",
  "run_id": sys.argv[3],
  "stage": "phase1",
  "scope_sha256": scope["scope_sha256"],
  "scanned": [row["path"] for row in scope["files"]],
  "findings": [
    {"surface":"ocr/SRC-DEMO.md","line":5,"occurrence":1,"exact_text":"张三","category":"患者姓名"},
    {"surface":"ocr/SRC-DEMO.md","line":5,"occurrence":2,"exact_text":"张三","category":"联系人姓名"},
  ],
  "clean": False,
}
pathlib.Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
PY

python3 "$PII" validate-report "$patient" --run-id "$run_id" --scope "$before_scope" --report "$before_report" >/dev/null
apply_json="$(python3 "$PII" apply "$patient" --run-id "$run_id" --scope "$before_scope" --report "$before_report")"
corrections="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["receipt_path"])' <<<"$apply_json")"
grep -q '患者\[PII_MASKED\]，联系人\[PII_MASKED\]' "$patient/ocr/SRC-DEMO.md"
grep -q '检查日期：2026-08-01' "$patient/ocr/SRC-DEMO.md"
grep -q '来源机构：示例医院' "$patient/ocr/SRC-DEMO.md"

after_json="$(python3 "$PII" scope "$patient" --run-id "$run_id" --stage phase1 --pass after)"
after_scope="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["scope_path"])' <<<"$after_json")"
after_report="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["report_path"])' <<<"$after_json")"
python3 - "$after_scope" "$after_report" "$run_id" <<'PY'
import json, pathlib, sys
scope = json.loads(pathlib.Path(sys.argv[1]).read_text())
report = {
  "schema": "semantic_pii_report_v1", "run_id": sys.argv[3], "stage": "phase1",
  "scope_sha256": scope["scope_sha256"], "scanned": [x["path"] for x in scope["files"]],
  "findings": [], "clean": True,
}
pathlib.Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
PY
python3 "$PII" record-clean "$patient" --run-id "$run_id" --scope "$after_scope" --report "$after_report" --corrections "$corrections" >/dev/null
python3 "$PII" check "$patient" --stage phase1 >/dev/null

# A clean final receipt must cover the exact current deliverable set, not just
# rehash the files that happened to exist when the scope was frozen.
mkdir -p "$patient/01_身份与基础信息"
cp "$patient/ocr/SRC-DEMO.md" "$patient/01_身份与基础信息/a.md"
printf '{"schema":"high_risk_review_v2","sources":{}}\n' > "$patient/high_risk_review.json"
final_before="$(python3 "$PII" scope "$patient" --run-id "$run_id" --stage final --pass before)"
final_scope="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["scope_path"])' <<<"$final_before")"
final_report="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["report_path"])' <<<"$final_before")"
python3 - "$final_scope" <<'PY'
import json, pathlib, sys
scope = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert "high_risk_review.json" in [row["path"] for row in scope["files"]]
PY
python3 - "$final_scope" "$final_report" "$run_id" <<'PY'
import json, pathlib, sys
scope = json.loads(pathlib.Path(sys.argv[1]).read_text())
pathlib.Path(sys.argv[2]).write_text(json.dumps({
  "schema":"semantic_pii_report_v1", "run_id":sys.argv[3], "stage":"final",
  "scope_sha256":scope["scope_sha256"], "scanned":[x["path"] for x in scope["files"]],
  "findings":[], "clean":True,
}, ensure_ascii=False)+"\n")
PY
python3 "$PII" record-clean "$patient" --run-id "$run_id" --scope "$final_scope" --report "$final_report" >/dev/null
printf '# late deliverable\n' > "$patient/review_summary.md"
if python3 "$PII" check "$patient" --stage final >/dev/null; then
  echo "FAIL: final receipt ignored newly added deliverable" >&2; exit 1
fi
rm "$patient/review_summary.md"
python3 "$PII" check "$patient" --stage final >/dev/null

python3 "$RUN" complete "$patient" --run-id "$run_id" >/dev/null
if python3 "$RUN" start "$patient" >/dev/null; then
  echo "FAIL: completed run restarted without --new" >&2; exit 1
fi
if python3 "$RUN" start "$patient" --new --run-id "$run_id" >/dev/null; then
  echo "FAIL: --new reused completed run_id" >&2; exit 1
fi
next="$(python3 "$RUN" start "$patient" --new)"
next_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' <<<"$next")"
[[ "$next_id" != "$run_id" ]]

echo "PASS: simple pinned run + semantic PII scan/mask/rescan"
