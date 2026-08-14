#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/cancer-buddy-organize"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PATIENT="$WORK/PT-PHASE0-DEID"
INPUT="$WORK/患者原始资料_20260220180000"
ORIGINAL_NAME="微信图片_20260220175937.JpG"
NESTED_DIR="$INPUT/住院病历_患者姓名"
NESTED_NAME="病理图片_20260304112233.PnG"
DUPLICATE_NAME="同一图片副本_20260405123456.jpg"
mkdir -p "$PATIENT" "$INPUT" "$NESTED_DIR"
printf 'synthetic image bytes\nwith exact-copy sentinel\n' > "$INPUT/$ORIGINAL_NAME"
printf 'nested synthetic image bytes\n' > "$NESTED_DIR/$NESTED_NAME"
cp "$INPUT/$ORIGINAL_NAME" "$NESTED_DIR/$DUPLICATE_NAME"
printf 'ignored metadata\n' > "$NESTED_DIR/.DS_Store"
printf 'ignored resource fork\n' > "$NESTED_DIR/._病理图片.png"

bash "$SKILL/scripts/phase0_prepare.sh" "$PATIENT" "$INPUT" >/dev/null

python3 - "$PATIENT" "$INPUT/$ORIGINAL_NAME" "$ORIGINAL_NAME" "$(basename "$INPUT")" \
  "$NESTED_DIR/$NESTED_NAME" "$NESTED_NAME" "$(basename "$NESTED_DIR")" \
  "$DUPLICATE_NAME" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

patient = pathlib.Path(sys.argv[1])
original = pathlib.Path(sys.argv[2])
original_name = sys.argv[3]
input_dir_name = sys.argv[4]
nested_original = pathlib.Path(sys.argv[5])
nested_name = sys.argv[6]
nested_dir_name = sys.argv[7]
duplicate_name = sys.argv[8]
manifest_path = patient / "phase0_manifest.json"
manifest_text = manifest_path.read_text(encoding="utf-8")
manifest = json.loads(manifest_text)

assert original_name not in manifest_text
assert nested_name not in manifest_text
assert duplicate_name not in manifest_text
assert input_dir_name not in manifest_text
assert nested_dir_name not in manifest_text
assert manifest["total"] == 2 and manifest["blocked"] == 0
assert len(manifest["sources"]) == 2

rows = {row["source_id"]: row for row in manifest["sources"]}
expected = [(original, "jpg"), (nested_original, "png")]
expected_paths = []
for source_path, extension in expected:
    original_bytes = source_path.read_bytes()
    sha256 = hashlib.sha256(original_bytes).hexdigest()
    source_id = f"SRC-{sha256[:12]}"
    expected_raw_path = f"raw/{source_id}/source.{extension}"
    expected_paths.append(expected_raw_path)
    row = rows[source_id]

    assert "original_name" not in row
    assert row["source_id"] == source_id
    assert row["raw_path"] == expected_raw_path
    assert row["raster_paths"] == [expected_raw_path]
    assert row["sha256"] == sha256
    assert not re.search(
        r"20260220175937|20260304112233|微信图片|病理图片|患者原始资料|住院病历",
        row["raw_path"],
    )

    raw_copy = patient / expected_raw_path
    assert raw_copy.is_file()
    assert raw_copy.read_bytes() == original_bytes
    assert hashlib.sha256(raw_copy.read_bytes()).hexdigest() == sha256

original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
assert sum(row["sha256"] == original_sha for row in manifest["sources"]) == 1

mapping_path = patient / "raw/_FILENAME_MAPPING.md"
mapping = mapping_path.read_text(encoding="utf-8")
assert original_name in mapping
assert nested_name in mapping
assert duplicate_name in mapping
for expected_raw_path in expected_paths:
    assert expected_raw_path in mapping
assert mapping.count(expected_paths[0]) == 2
PY

# A truncated source_id collision must stop before a second content unit is accepted.
COLLISION_PATIENT="$WORK/PT-PHASE0-COLLISION"
COLLISION_INPUT="$WORK/collision-input"
FAKEBIN="$WORK/fakebin"
mkdir -p "$COLLISION_PATIENT" "$COLLISION_INPUT" "$FAKEBIN"
printf 'collision-a\n' > "$COLLISION_INPUT/a.jpg"
printf 'collision-b\n' > "$COLLISION_INPUT/b.jpg"
cat > "$FAKEBIN/shasum" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
file="${!#}"
if grep -q 'collision-a' "$file"; then tail_char="1"; else tail_char="2"; fi
digest="aaaaaaaaaaaa"
for _ in $(seq 1 52); do digest="$digest$tail_char"; done
printf '%s  %s\n' "$digest" "$file"
SH
chmod +x "$FAKEBIN/shasum"
if PATH="$FAKEBIN:$PATH" bash "$SKILL/scripts/phase0_prepare.sh" \
  "$COLLISION_PATIENT" "$COLLISION_INPUT" >"$WORK/collision.out" 2>"$WORK/collision.err"; then
  echo "expected truncated source_id collision to fail closed" >&2
  exit 1
fi
grep -q 'source_id collision' "$WORK/collision.err"

echo "ok: phase0 raw paths are stable and de-identified"
