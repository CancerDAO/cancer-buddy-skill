#!/usr/bin/env bash
# Synthetic waveform-report regression: no real patient image or clinical data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

patient="$tmp/PT-WAVEFORM"
sid="SRC-ECG00000001"
rel="07_检验/心电图功能检查/2026-01-02_心电图报告_合成机构_来源${sid}.md"
mkdir -p "$patient/raw/$sid" "$(dirname "$patient/$rel")" \
  "$patient/.staging/rasters/$sid"
printf 'synthetic HEIC placeholder only; no patient content\n' > "$patient/raw/$sid/source.heic"
printf 'synthetic raster placeholder only\n' > "$patient/.staging/rasters/$sid/page1.jpg"

cat > "$patient/$rel" <<EOF
source_id: $sid
original: $sid
read_mode: model_vision_assist
profile: lite
doc_kind: waveform_report
waveform_interpretation: not_performed

# 脱敏转录

- 机构：合成机构
- 报告类型：心电图报告
- 报告日期：2026-01-02

## 文字区逐字转录

心率：60 bpm
医生诊断：窦性心律

## 图形主体声明

主体为波形/图形，未被转录为文本；系统未对波形作出解读，需由临床/专科医生解读。

## 不确定项

无
EOF

cat > "$patient/phase0_manifest.json" <<EOF
{
  "schema": "phase0_manifest_v1",
  "total": 1,
  "blocked": 0,
  "sources": [{
    "source_id": "$sid",
    "raw_path": "raw/$sid/source.heic",
    "sha256": "synthetic",
    "status": "ok",
    "raster_paths": [".staging/rasters/$sid/page1.jpg"]
  }]
}
EOF

python3 "$ORG/scripts/build_inventory_index.py" "$patient" --run-mode full >/dev/null
cat > "$patient/timeline.md" <<EOF
- 2026-01-02：来源书面结论为“窦性心律” [[src:$rel#L13-L14]]
EOF

python3 "$VAL" "$patient" >"$tmp/valid.out" 2>"$tmp/valid.err"
python3 - "$patient" "$rel" <<'PY'
import json
import pathlib
import sys

patient = pathlib.Path(sys.argv[1])
rel = sys.argv[2]
inventory = json.loads((patient / "source_inventory.json").read_text(encoding="utf-8"))
row = inventory["files"][0]
assert row["doc_kind"] == "waveform_report", row
assert row["raw_path"].startswith("raw/"), row
assert row["adapter"] == "temp_raster", row
assert row["sidecar_path"] == rel, row
PY

# The special type must carry its explicit non-interpretation declaration.
sed -i '/^waveform_interpretation: not_performed$/d' "$patient/$rel"
if python3 "$VAL" "$patient" >"$tmp/missing-declaration.out" 2>"$tmp/missing-declaration.err"; then
  echo "expected waveform sidecar without non-interpretation declaration to fail" >&2
  exit 1
fi
grep -q 'requires waveform_interpretation: not_performed' "$tmp/missing-declaration.err"
sed -i '5i waveform_interpretation: not_performed' "$patient/$rel"

# The filed sidecar and inventory must agree about the specialized doc kind.
python3 - "$patient/source_inventory.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["files"][0].pop("doc_kind")
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
if python3 "$VAL" "$patient" >"$tmp/missing-inventory-kind.out" 2>"$tmp/missing-inventory-kind.err"; then
  echo "expected waveform inventory without doc_kind to fail" >&2
  exit 1
fi
grep -q 'source_inventory doc_kind must be waveform_report' "$tmp/missing-inventory-kind.err"
python3 "$ORG/scripts/build_inventory_index.py" "$patient" --run-mode full >/dev/null

# The explicit waveform exception must not silently permit a text-volume failure label.
printf '\nquality: insufficient_text\n' >> "$patient/$rel"
if python3 "$VAL" "$patient" >"$tmp/bad.out" 2>"$tmp/bad.err"; then
  echo "expected waveform quality-marker regression to fail" >&2
  exit 1
fi
grep -q 'must not use insufficient_text' "$tmp/bad.err"

echo "ok: waveform report contract preserves text evidence, raw linkage, and safe anchors"
