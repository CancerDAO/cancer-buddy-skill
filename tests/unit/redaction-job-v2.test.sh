#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -c 'from PIL import Image; from reportlab.pdfgen import canvas; from docx import Document; from openpyxl import Workbook' >/dev/null 2>&1; then
  echo "SKIP: redaction-job-v2.test.sh requires Pillow, reportlab, python-docx, openpyxl" >&2
  exit 0
fi

if ! command -v pdftoppm >/dev/null 2>&1; then
  echo "SKIP: redaction-job-v2.test.sh requires pdftoppm" >&2
  exit 0
fi

tmpdir="$(mktemp -d)"
trap "rm -rf \"$tmpdir\"" EXIT
patient_dir="$tmpdir/PT-REDACTION-V2"
mkdir -p "$patient_dir"

PATIENT_DIR="$patient_dir" "$PYTHON" - <<'PY'
import datetime as dt
import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from docx import Document
from openpyxl import Workbook

pd = Path(os.environ["PATIENT_DIR"])
bucket = pd / "07_检验" / "其他"
mirror = pd / "90_原始文件镜像" / "input"
bucket.mkdir(parents=True, exist_ok=True)
mirror.mkdir(parents=True, exist_ok=True)

sources = [
    ("f001", "s001", "image", "llm_region_image", "synthetic_image.jpg", "image"),
    ("f002", "s002", "pdf", "llm_region_pdf", "synthetic_pdf.pdf", "text"),
    ("f003", "s003", "docx", "llm_structured_docx", "synthetic_docx.docx", "structured"),
    ("f004", "s004", "xlsx", "llm_structured_sheet", "synthetic_sheet.xlsx", "structured"),
    ("f005", "s005", "txt", "llm_text_rewrite", "synthetic_text.txt", "text"),
]

img = Image.new("RGB", (400, 200), "white")
ImageDraw.Draw(img).text((20, 20), "MASKME-IMAGE", fill="black")
img.save(bucket / "synthetic_image.jpg")

c = canvas.Canvas(str(bucket / "synthetic_pdf.pdf"))
c.drawString(30, 750, "MASKME-PDF")
c.save()

doc = Document()
doc.add_paragraph("MASKME-DOCX")
doc.save(bucket / "synthetic_docx.docx")

wb = Workbook()
ws = wb.active
ws.title = "Sheet1"
ws["A1"] = "MASKME-XLSX"
wb.save(bucket / "synthetic_sheet.xlsx")

(bucket / "synthetic_text.txt").write_text("label: MASKME-TXT\nclinical: EGFR L858R\n", encoding="utf-8")

for _, _, _, _, name, _ in sources:
    shutil.copy2(bucket / name, mirror / name)
    (bucket / f"{Path(name).stem}.md").write_text(
        "SOURCE: synthetic | CONFIDENCE: high\n"
        "READ_MODE: llm_text_payload\n"
        "ADAPTER: text_payload\n"
        f"ORIGINAL: 90_原始文件镜像/input/{name}\n\n"
        "No identifying content.\n\n"
        "## PII\n"
        "masked: none\n",
        encoding="utf-8",
    )

def frame(frame_kind, coordinate_space, **extra):
    base = {
        "frame_kind": frame_kind,
        "coordinate_space": coordinate_space,
        "width": extra.pop("width", None),
        "height": extra.pop("height", None),
        "dpi": extra.pop("dpi", None),
        "page_count": extra.pop("page_count", None),
        "notes": extra.pop("notes", None),
    }
    base.update(extra)
    return base

regions = {
    "f001": [{
        "region_id": "r001",
        "category": "patient_name",
        "locator_type": "normalized_bbox",
        "locator": {"x": -0.05, "y": 0.0, "width": 0.55, "height": 0.35},
        "confidence": "high",
    }],
    "f002": [{
        "region_id": "r001",
        "category": "patient_name",
        "locator_type": "page_normalized_bbox",
        "locator": {"page": 1, "x": 0.0, "y": 0.0, "width": 0.5, "height": 0.18},
        "confidence": "high",
    }],
    "f003": [{
        "region_id": "r001",
        "category": "patient_name",
        "locator_type": "xml_path",
        "locator": {"part": "word/document.xml", "text_node_index": 0},
        "confidence": "high",
    }],
    "f004": [{
        "region_id": "r001",
        "category": "patient_name",
        "locator_type": "cell",
        "locator": {"sheet": "Sheet1", "cell": "A1"},
        "confidence": "high",
    }],
    "f005": [{
        "region_id": "r001",
        "category": "patient_name",
        "locator_type": "line_span",
        "locator": {"line": 1, "start": 7, "end": 17},
        "confidence": "high",
    }],
}
frames = {
    "f001": frame("image", "normalized_0_1", width=400, height=200),
    "f002": frame("pdf_page", "normalized_0_1", dpi=150, page_count=1),
    "f003": frame("docx_xml", "xml_locator"),
    "f004": frame("xlsx_sheet", "cell"),
    "f005": frame("text", "line_span"),
}

now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
manifest_files = []
inventory_files = []
for fid, sid, kind, strategy, name, modality in sources:
    manifest_files.append({
        "id": fid,
        "source_id": sid,
        "source_kind": kind,
        "bucket_path": f"07_检验/其他/{name}",
        "mirror_path": f"90_原始文件镜像/input/{name}",
        "redacted_candidate_path": None,
        "redacted_payload_path": None,
        "adapter_frame": frames[fid],
        "regions": regions[fid],
        "status": "pending",
    })
    inventory_files.append({
        "source_id": sid,
        "original_path": name,
        "mirror_path": f"90_原始文件镜像/input/{name}",
        "bucket_path": f"07_检验/其他/{name}",
        "sidecar_path": f"07_检验/其他/{Path(name).stem}.md",
        "modality": modality,
        "read_mode": "llm_text_payload",
        "adapter": "text_payload",
        "adapter_provenance": "synthetic fixture",
        "persist": True,
        "redaction_required": True,
        "redaction_strategy": strategy,
        "redacted_path": None,
        "notes": None,
    })

(pd / "redaction_manifest.json").write_text(json.dumps({
    "schema": "redaction_manifest_v2",
    "patient_dir": str(pd),
    "generated_at": now,
    "files": manifest_files,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(pd / "source_inventory.json").write_text(json.dumps({
    "schema": "source_inventory_v1",
    "patient_dir": str(pd),
    "generated_at": now,
    "files": inventory_files,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

"$PYTHON" "$REPO_ROOT/skills/cancer-buddy-organize/scripts/run_redaction_job.py" prepare "$patient_dir" >/tmp/cb-redaction-prepare.out

PATIENT_DIR="$patient_dir" "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

pd = Path(os.environ["PATIENT_DIR"])
status = json.loads((pd / "redaction_status.json").read_text(encoding="utf-8"))
assert status["summary"]["redacted_pending_qa"] == 5, status
qa = {
    "schema": "llm_redaction_qa_v1",
    "report_id": "qa-synthetic",
    "files": [{"id": e["id"], "pass": True, "categories_checked": ["patient_name"], "reason": None} for e in status["files"]],
}
(pd / "llm_redaction_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

"$PYTHON" "$REPO_ROOT/skills/cancer-buddy-organize/scripts/run_redaction_job.py" commit "$patient_dir" --qa-report "$patient_dir/llm_redaction_qa.json" >/tmp/cb-redaction-commit.out

PATIENT_DIR="$patient_dir" "$PYTHON" - <<'PY'
import json
import os
import zipfile
from pathlib import Path

from openpyxl import load_workbook

pd = Path(os.environ["PATIENT_DIR"])
status = json.loads((pd / "redaction_status.json").read_text(encoding="utf-8"))
assert status["summary"]["done"] == 5, status
for entry in status["files"]:
    assert entry["coverage_passed"] is True, entry
    assert entry["llm_qa_passed"] is True, entry
    assert entry["qa_passed"] is True, entry
    assert entry["original_deleted"] is True, entry

txt = (pd / "07_检验/其他/synthetic_text.txt").read_text(encoding="utf-8")
assert "MASKME-TXT" not in txt and "[PII_MASKED]" in txt, txt

with zipfile.ZipFile(pd / "07_检验/其他/synthetic_docx.docx") as z:
    xml = z.read("word/document.xml").decode("utf-8")
assert "MASKME-DOCX" not in xml and "[PII_MASKED]" in xml

wb = load_workbook(pd / "07_检验/其他/synthetic_sheet.xlsx")
assert wb["Sheet1"]["A1"].value == "[PII_MASKED]"

assert (pd / "07_检验/其他/synthetic_pdf.pdf").read_bytes().startswith(b"%PDF")
PY

"$PYTHON" "$REPO_ROOT/skills/cancer-buddy-organize/scripts/validate_structured_outputs.py" "$patient_dir" >/tmp/cb-redaction-validate.out

echo "redaction-job-v2.test.sh: PASS"
