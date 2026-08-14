#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/cancer-buddy-organize"
PLAN="$SKILL/scripts/plan_phase4.py"
BUILD_PROFILE="$SKILL/scripts/build_profile.py"
DAG="$SKILL/references/runtime-bindings/phase4-dag.json"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 "$PLAN" --validate-only >/dev/null

# Static contract: corrected bucket routing and no patient_summary/profile overlap.
python3 - "$DAG" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
t = {x["id"]: x for x in d["tasks"]}
assert t["molecular"]["sidecar_buckets"] == ["06_"]
assert t["treatment"]["sidecar_buckets"] == ["03_", "08_", "09_"]
assert t["comorbidities"]["sidecar_buckets"] == ["02_", "03_"]
assert t["patient_summary"]["outputs"] == ["patient_summary.json"]
assert t["profile"]["kind"] == "deterministic" and t["profile"]["outputs"] == ["profile.json"]
assert t["case_summary_data"]["outputs"] == [".case_summary_data.json"]
assert t["case_summary_html"]["kind"] == "deterministic"
assert t["case_summary_html"]["outputs"] == ["病情简要总结.html"]
assert t["finalize_log"]["outputs"] == ["update_log.json"]
for task_id in ("labs", "comorbidities", "missing_items", "molecular", "treatment",
                "patient_summary", "timeline", "readiness_review", "case_summary_data"):
    assert t[task_id]["schemas"], task_id
flat = [p for c in t["finalize_log"]["commands"] for p in c]
assert "--finalize-log" in flat and any(p.endswith("build_inventory_index.py") for p in flat)
PY

# The validator must reject both output-owner conflicts and dependency cycles.
python3 - "$DAG" "$TMP/bad-dag.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
t = {x["id"]: x for x in d["tasks"]}
t["patient_summary"]["outputs"].append("profile.json")
t["labs"].pop("schemas")
t["inventory"]["depends_on"] = ["finalize_log"]
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
if python3 "$PLAN" --dag "$TMP/bad-dag.json" --validate-only >"$TMP/bad.out" 2>&1; then
  echo "invalid DAG was accepted" >&2
  exit 1
fi
grep -q 'output owner conflict' "$TMP/bad.out"
grep -q 'dependency cycle detected' "$TMP/bad.out"
grep -q 'labs: schemas must be exactly' "$TMP/bad.out"

# File-state scheduling: inventory -> all Wave A -> bounded Wave B -> deterministic tail.
P="$TMP/PT-AB12"
mkdir -p "$P"
run_id="RUN-20260814T010203Z-ABCDEF"
cat > "$P/.organize_run.json" <<JSON
{"schema":"organize_run_v1","patient_code":"PT-AB12","run_id":"$run_id","status":"active","started_at":"2026-08-14T01:02:03Z"}
JSON
plan() { python3 "$PLAN" "$P" --run-id "$run_id" "$@"; }
plan > "$TMP/inventory-ready.json"
python3 - "$TMP/inventory-ready.json" <<'PY'
import json, sys
assert [t["id"] for t in json.load(open(sys.argv[1]))["ready"]] == ["inventory"]
PY
printf '{}\n' > "$P/source_inventory.json"
printf '# INDEX\n' > "$P/INDEX.md"

plan --available-slots 2 > "$TMP/a-short.json"
python3 - "$TMP/a-short.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding="utf-8"))
assert x["ready_wave"] == "A" and x["ready"] == []
assert x["needs_slots"] == 3
PY

plan --available-slots 3 > "$TMP/a.json"
python3 - "$TMP/a.json" <<'PY'
import json, sys
from pathlib import Path
x = json.load(open(sys.argv[1], encoding="utf-8"))
assert x["ready_wave"] == "A"
assert [t["id"] for t in x["ready"]] == ["labs", "comorbidities", "missing_items"]
assert x["dispatch_policy"] == "all_before_wait"
assert all(
    Path(t["python_executable"]).resolve() == Path(sys.executable).resolve()
    for t in x["ready"]
)
PY

for f in labs.json comorbidities.json missing_items.json; do printf '{}\n' > "$P/$f"; done
plan --available-slots 2 > "$TMP/b.json"
python3 - "$TMP/b.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding="utf-8"))
assert x["ready_wave"] == "B"
assert [t["id"] for t in x["ready"]] == ["molecular", "treatment"]
assert x["dispatch_policy"] == "up_to_available_slots_then_wait"
PY

for f in molecular.json treatment_lines.json patient_summary.json timeline.json timeline.md case_text.md; do
  printf '{}\n' > "$P/$f"
done
plan --available-slots 3 > "$TMP/profile-ready.json"
python3 - "$TMP/profile-ready.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1], encoding="utf-8"))
assert [t["id"] for t in x["ready"]] == ["profile"]
PY

printf '{}\n' > "$P/profile.json"
plan > "$TMP/agents-ready.json"
python3 - "$TMP/agents-ready.json" <<'PY'
import json, sys
assert [t["id"] for t in json.load(open(sys.argv[1]))["ready"]] == ["agents_md"]
PY
printf '# AGENTS\n' > "$P/AGENTS.md"
plan > "$TMP/review-ready.json"
python3 - "$TMP/review-ready.json" <<'PY'
import json, sys
assert [t["id"] for t in json.load(open(sys.argv[1]))["ready"]] == ["readiness_review"]
PY
printf '{}\n' > "$P/readiness.json"
printf '# Review\n' > "$P/review_summary.md"
plan > "$TMP/data-ready.json"
python3 - "$TMP/data-ready.json" <<'PY'
import json, sys
assert [t["id"] for t in json.load(open(sys.argv[1]))["ready"]] == ["case_summary_data"]
PY
printf '{}\n' > "$P/.case_summary_data.json"
plan > "$TMP/html-ready.json"
python3 - "$TMP/html-ready.json" <<'PY'
import json, sys
assert [t["id"] for t in json.load(open(sys.argv[1]))["ready"]] == ["case_summary_html"]
PY
printf '<html></html>\n' > "$P/病情简要总结.html"
plan > "$TMP/pii-blocked.json"
python3 - "$TMP/pii-blocked.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))
assert x["ready"] == []
assert x["blocked_on_required_files"]["finalize_log"] == [".semantic_pii_review.phase1.json"]
PY
printf '{}\n' > "$P/.semantic_pii_review.phase1.json"
plan > "$TMP/finalize-ready.json"
python3 - "$TMP/finalize-ready.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))
assert [t["id"] for t in x["ready"]] == ["finalize_log"]
commands = x["ready"][0]["commands"]
assert "--finalize-log" in commands[1]
assert commands[1][-2:] == ["--run-id", "RUN-20260814T010203Z-ABCDEF"]
PY
printf '{"schema":"update_log_v1","runs":[{"run_id":"RUN-20000101T000000Z-000000"}]}\n' > "$P/update_log.json"
plan > "$TMP/wrong-run-log.json"
python3 - "$TMP/wrong-run-log.json" <<'PY'
import json, sys
assert [t["id"] for t in json.load(open(sys.argv[1]))["ready"]] == ["finalize_log"]
PY
cat > "$P/update_log.json" <<JSON
{"schema":"update_log_v1","runs":[{"run_id":"$run_id"}]}
JSON
plan > "$TMP/done.json"
python3 - "$TMP/done.json" <<'PY'
import json, sys
x = json.load(open(sys.argv[1]))
assert x["complete"] is True and x["pending"] == []
PY

# Deterministic profile projection: fixed timestamp, copied facts, stable bytes.
PF="$TMP/profile-fixture/PT-CD34"
mkdir -p "$PF"
cat > "$PF/patient_summary.json" <<'JSON'
{
  "patient_code": "PT-CD34",
  "schema_version": "2.1",
  "generated_at": "2026-08-14T01:02:03Z",
  "alias": "case-demo",
  "demographics": {
    "height_cm": 170,
    "height_cm_as_of": "2026-08-01",
    "weight_kg": 68,
    "weight_kg_as_of": "2026-08-01",
    "provenance_layer": "source_reported",
    "verification_status": "unverified",
    "source_refs": ["01_身份与基础信息/a.md"]
  },
  "diagnosis": {
    "primary": "来源原文诊断",
    "histology": null,
    "stage": "来源原文分期",
    "metastasis_sites": [],
    "provenance_layer": "source_reported",
    "verification_status": "unverified",
    "source_refs": ["04_诊断与分期/a.md"]
  },
  "current_status": {
    "regimen": "来源原文方案",
    "response": null,
    "ecog": null,
    "as_of": "2026-08-02",
    "provenance_layer": "source_reported",
    "verification_status": "unverified",
    "source_refs": ["08_治疗/b.md", "04_诊断与分期/a.md"]
  }
}
JSON
cp "$PF/patient_summary.json" "$TMP/patient-summary.before"
python3 "$BUILD_PROFILE" "$PF" --locale en >/dev/null
cp "$PF/profile.json" "$TMP/profile.first"
python3 "$BUILD_PROFILE" "$PF" --locale en >/dev/null
cmp "$TMP/profile.first" "$PF/profile.json"
cmp "$TMP/patient-summary.before" "$PF/patient_summary.json"
bash "$ROOT/scripts/validate-profile-schema.sh" "$PF" >/dev/null
python3 - "$PF/profile.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding="utf-8"))
assert p["schema"] == "cancer_buddy_profile_v3"
assert p["patient_code"] == "PT-CD34" and p["locale"] == "en"
assert p["generated_at"] == "2026-08-14T01:02:03Z"
assert p["summary"]["primary"] == "来源原文诊断"
assert p["summary"]["stage"] == "来源原文分期"
assert p["summary"]["current_regimen"] == "来源原文方案"
assert p["anthropometrics"]["bmi"] is None
assert p["source_refs"] == [
    "04_诊断与分期/a.md", "08_治疗/b.md", "01_身份与基础信息/a.md"
]
PY

echo "organize-phase4-dag: OK"
