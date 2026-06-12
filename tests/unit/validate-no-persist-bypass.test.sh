#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"

tmpdir="$(mktemp -d)"
trap "rm -rf \"$tmpdir\"" EXIT
patient_dir="$tmpdir/PT-ABC123"
mkdir -p "$patient_dir"

PATIENT_DIR="$patient_dir" "$PYTHON" - <<'PY'
import datetime as dt
import json
import os
from pathlib import Path

pd = Path(os.environ["PATIENT_DIR"])
bucket = pd / "07_检验" / "其他"
mirror = pd / "90_原始文件镜像" / "input"
bucket.mkdir(parents=True, exist_ok=True)
mirror.mkdir(parents=True, exist_ok=True)

(bucket / "lab.jpg").write_bytes(b"synthetic-redacted-image")
(mirror / "lab.jpg").write_bytes(b"synthetic-redacted-image")
(bucket / "lab.md").write_text(
    "SOURCE: synthetic lab\n"
    "READ_MODE: model_vision\n"
    "ADAPTER: temp_raster\n"
    "ORIGINAL: 90_原始文件镜像/input/lab.jpg\n\n"
    "Tumor marker CEA result 4.49 ng/ml.\n\n"
    "## PII\n"
    "masked: none\n",
    encoding="utf-8",
)

now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
ref = "07_检验/其他/lab.md#L1-L2"

(pd / "patient_summary.json").write_text(json.dumps({
    "patient_code": "PT-ABC123",
    "schema_version": "1",
    "generated_at": now,
    "diagnosis": {
        "primary": "CRC",
        "source_refs": [ref],
    },
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(pd / "timeline.md").write_text(
    "# Timeline\n\n"
    "- 2026-01-09 CEA 4.49 ng/ml [[src:07_检验/其他/lab.md#L1-L2]]\n",
    encoding="utf-8",
)
(pd / "case_text.md").write_text(
    "CEA was within reference range. [[src:07_检验/其他/lab.md#L1-L2]]\n",
    encoding="utf-8",
)

(pd / "source_inventory.json").write_text(json.dumps({
    "schema": "source_inventory_v1",
    "patient_dir": str(pd),
    "generated_at": now,
    "files": [{
        "source_id": "s001",
        "original_path": "lab.jpg",
        "mirror_path": "90_原始文件镜像/input/lab.jpg",
        "bucket_path": "07_检验/其他/lab.jpg",
        "sidecar_path": "07_检验/其他/lab.md",
        "modality": "image",
        "read_mode": "model_vision",
        "adapter": "temp_raster",
        "adapter_provenance": "synthetic fixture",
        "persist": False,
        "redaction_required": True,
        "redaction_strategy": "llm_region_image",
        "redacted_path": None,
        "notes": None,
    }],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

set +e
out="$("$PYTHON" "$REPO_ROOT/skills/cancer-buddy-organize/scripts/validate_structured_outputs.py" "$patient_dir" 2>&1)"
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  echo "FAIL: validator accepted a formally cited source marked persist:false" >&2
  echo "$out" >&2
  exit 1
fi
if ! grep -q "persist:false" <<<"$out"; then
  echo "FAIL: validator failed for the wrong reason; expected persist:false error" >&2
  echo "$out" >&2
  exit 1
fi

PATIENT_DIR="$patient_dir" "$PYTHON" - <<'PY'
import datetime as dt
import json
import os
from pathlib import Path

pd = Path(os.environ["PATIENT_DIR"])
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

inventory_path = pd / "source_inventory.json"
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
inventory["files"][0]["persist"] = True
inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(pd / "redaction_manifest.json").write_text(json.dumps({
    "schema": "redaction_manifest_v2",
    "patient_dir": str(pd),
    "generated_at": now,
    "files": [{
        "id": "f001",
        "source_id": "s001",
        "source_kind": "image",
        "bucket_path": "07_检验/其他/lab.jpg",
        "mirror_path": "90_原始文件镜像/input/lab.jpg",
        "redacted_candidate_path": None,
        "redacted_payload_path": None,
        "adapter_frame": {
            "frame_kind": "image",
            "coordinate_space": "normalized_0_1",
            "width": 1,
            "height": 1,
            "dpi": None,
            "page_count": None,
            "notes": None,
        },
        "regions": [{
            "region_id": "r001",
            "category": "patient_name",
            "locator_type": "normalized_bbox",
            "locator": {"x": 0, "y": 0, "width": 0.1, "height": 0.1},
            "confidence": "high",
        }],
        "status": "pending",
    }],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(pd / "source_redaction_status.json").write_text(json.dumps({
    "schema": "source_redaction_status_v1",
    "patient_dir": str(pd),
    "updated_at": now,
    "summary": {
        "total": 1,
        "pending": 0,
        "done": 1,
        "failed": 0,
        "blocked": 0,
        "not_required": 0,
    },
    "files": [{
        "source_id": "s001",
        "status": "done",
        "strategy": "llm_region_image",
        "redacted_path": "07_检验/其他/lab.jpg",
        "qa_passed": True,
        "coverage_passed": True,
        "llm_qa_passed": True,
        "qa_report_id": "qa-synthetic",
        "original_deleted": True,
        "reason": None,
        "linked_redaction_manifest_id": "f001",
    }],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

"$PYTHON" "$REPO_ROOT/skills/cancer-buddy-organize/scripts/validate_structured_outputs.py" "$patient_dir" >/tmp/cb-no-persist-bypass-validate.out

echo "validate-no-persist-bypass.test.sh: PASS"
