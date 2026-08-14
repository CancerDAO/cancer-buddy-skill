#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/cancer-buddy-organize"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PATIENT="$WORK/PT-LIFECYCLE"

mkdir -p "$PATIENT/raw/input" "$PATIENT/ocr"
: > "$PATIENT/raw/input/full.heic"
: > "$PATIENT/raw/input/partial.pdf"
: > "$PATIENT/raw/input/blocked.bin"

python3 - "$PATIENT" <<'PY'
import json
import pathlib
import sys

patient = pathlib.Path(sys.argv[1])
run_id = "RUN-20260814T000000Z-A1B2C3"
(patient / ".organize_run.json").write_text(json.dumps({
    "schema": "organize_run_v1", "patient_code": patient.name,
    "run_id": run_id, "status": "active", "started_at": "2026-08-14T00:00:00Z"
}, indent=2) + "\n", encoding="utf-8")
manifest = {
    "schema": "phase0_manifest_v1",
    "total": 3,
    "blocked": 1,
    "sources": [
        {
            "file_id": "FILE-FULL-1",
            "source_id": "SRC-FULL0000001",
            "raw_path": "raw/input/full.heic",
            "status": "ok",
            "raster_paths": [".staging/rasters/SRC-FULL0000001/page1.jpg"],
        },
        {
            "file_id": "FILE-PART-1",
            "source_id": "SRC-PART0000001",
            "raw_path": "raw/input/partial.pdf",
            "status": "ok",
            "raster_paths": [".staging/rasters/SRC-PART0000001/page1.png"],
        },
        {
            "source_id": "SRC-BLOCK000001",
            "raw_path": "raw/input/blocked.bin",
            "status": "blocked_unsupported",
            "raster_paths": [],
        },
    ],
}
(patient / "phase0_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

# This is written while both sidecars are still under ocr/. The first record is
# keyed by file_id; the second exercises the lite source_id fallback. Paths are
# audit attributes and intentionally remain unchanged after filing.
review = {
    "schema": "high_risk_review_v2",
    "sources": {
        "FILE-FULL-1": {
            "file_id": "FILE-FULL-1",
            "source_id": "SRC-FULL0000001",
            "sidecar_path": "ocr/SRC-FULL0000001.md",
            "status": "passed_independent_reread",
            "values": {"67.61": "verified_by_second_read"},
        },
        "SRC-PART0000001": {
            "file_id": "FILE-PART-1",
            "source_id": "SRC-PART0000001",
            "sidecar_path": "ocr/SRC-PART0000001.md",
            "status": "needs_human_review",
            "values": {"5.2": "verified_by_second_read"},
        },
    },
}
(patient / "high_risk_review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
PY

cat > "$PATIENT/ocr/SRC-FULL0000001.md" <<'EOF'
source_id: SRC-FULL0000001
read_mode: model_vision

| 项目 | 结果 | 复核状态 |
|---|---:|---|
| synthetic_marker | 67.61 U/mL | needs_human_review |
EOF
cat > "$PATIENT/ocr/SRC-PART0000001.md" <<'EOF'
source_id: SRC-PART0000001
read_mode: model_vision

synthetic value: 5.2
EOF

FULL_REL="07_检验/血常规/2026-01-01_血常规_合成机构_来源SRC-FULL0000001.md"
PART_REL="03_病程与叙事文书/门诊病历/2026-01-02_门诊记录_合成机构_来源SRC-PART0000001.md"
mkdir -p "$PATIENT/$(dirname "$FULL_REL")" "$PATIENT/$(dirname "$PART_REL")"
mv "$PATIENT/ocr/SRC-FULL0000001.md" "$PATIENT/$FULL_REL"
mv "$PATIENT/ocr/SRC-PART0000001.md" "$PATIENT/$PART_REL"
rmdir "$PATIENT/ocr"

python3 "$SKILL/scripts/build_inventory_index.py" "$PATIENT" --run-mode full >/dev/null
test ! -e "$PATIENT/update_log.json"
python3 "$SKILL/scripts/validate_structured_outputs.py" "$PATIENT" >/dev/null

python3 - "$PATIENT" "$SKILL" "$FULL_REL" "$PART_REL" <<'PY'
import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(sys.argv[2]) / "scripts"))
from high_risk_review import inventory_review_status

patient = pathlib.Path(sys.argv[1])
skill = pathlib.Path(sys.argv[2])
full_rel, part_rel = sys.argv[3], sys.argv[4]
inventory = json.loads((patient / "source_inventory.json").read_text(encoding="utf-8"))
review = json.loads((patient / "high_risk_review.json").read_text(encoding="utf-8"))
assert (patient / "INDEX.md").read_text(encoding="utf-8").splitlines()[0] == (
    "# patient_code: PT-LIFECYCLE"
)
inventory_schema = json.loads(
    (skill / "references/schemas/source_inventory.schema.json").read_text(encoding="utf-8")
)
review_schema = json.loads(
    (skill / "references/schemas/high_risk_review.schema.json").read_text(encoding="utf-8")
)
assert inventory_review_status({"status": "not_applicable"}) == "not_applicable"
assert inventory_review_status({"status": "needs_human_review", "values": {"x": "double_read"}}) == "needs_human_review"

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None
if Draft202012Validator:
    errors = list(Draft202012Validator(inventory_schema).iter_errors(inventory))
    assert not errors, [error.message for error in errors]
    errors = list(Draft202012Validator(review_schema).iter_errors(review))
    assert not errors, [error.message for error in errors]

rows = {row["source_id"]: row for row in inventory["files"]}
full = rows["SRC-FULL0000001"]
partial = rows["SRC-PART0000001"]
blocked = rows["SRC-BLOCK000001"]

# Stable-ID lookup survives ocr/ -> bucket movement.
assert full["file_id"] == "FILE-FULL-1"
assert full["sidecar_path"] == full_rel
assert full["bucket_path"] == str(pathlib.PurePosixPath(full_rel).parent)
assert full["high_risk_review_status"] == "passed_independent_reread"
assert review["sources"]["FILE-FULL-1"]["sidecar_path"].startswith("ocr/")

# Verified individual values do not silently upgrade a partial review.
assert partial["sidecar_path"] == part_rel
assert partial["high_risk_review_status"] == "needs_human_review"

# Phase-0 values are mapped onto the schema vocabulary, including blocked input.
assert full["read_mode"] == "model_vision_assist"
assert full["extractor_provenance"]["llm_role"] == "transcription"
assert full["adapter"] == "temp_raster"
assert partial["adapter"] == "pdf_pages"
assert blocked["read_mode"] == "stub_unreadable"
assert blocked["adapter"] == "unsupported_stub"
assert blocked["sidecar_path"] is None and blocked["bucket_path"] is None

row_schema = inventory_schema["properties"]["files"]["items"]["properties"]
for row in inventory["files"]:
    assert row["read_mode"] in row_schema["read_mode"]["enum"]
    assert row["adapter"] in row_schema["adapter"]["enum"]
    assert row["extractor_provenance"]["llm_role"] in (
        row_schema["extractor_provenance"]["properties"]["llm_role"]["enum"]
    )
PY

# The value-binding gate also resolves the moved sidecar through its stable ID.
python3 - "$WORK/candidates.json" "$FULL_REL" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(
    json.dumps({"candidates": [{"target_doc": sys.argv[2], "old_value": "67.61 U/mL"}]}) + "\n",
    encoding="utf-8",
)
PY
python3 "$SKILL/scripts/gates/gate_candidate_binding.py" \
  "$WORK/candidates.json" "$PATIENT" --json "$WORK/binding.json" >/dev/null
python3 - "$WORK/binding.json" <<'PY'
import json
import pathlib
import sys

result = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["pass"] is True
assert result["candidates"][0]["binding"] == "verified"
PY

# Completion logging is a separate, explicit final action after Phase 4 gates.
python3 "$SKILL/scripts/build_inventory_index.py" \
  "$PATIENT" --run-mode full --finalize-log --run-id RUN-20260814T000000Z-A1B2C3 >/dev/null
python3 - "$PATIENT/update_log.json" <<'PY'
import json
import pathlib
import sys

log = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert log["schema"] == "update_log_v1"
assert len(log["runs"]) == 1
assert log["runs"][0]["run_id"] == "RUN-20260814T000000Z-A1B2C3"
assert log["runs"][0]["status"] == "ready_for_final_validation"
assert log["runs"][0]["run_mode"] == "full"
assert log["runs"][0]["missing_sidecars"] == []
PY

echo "ok: inventory/review stable-ID lifecycle"
