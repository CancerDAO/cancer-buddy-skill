#!/usr/bin/env bash
# phase0_prepare.sh — Kimi/lite 绑定的确定性前置（零 LLM）。
#
# 一次性完成：原件 sha256 → 预分配 source_id(SRC-<hash12>) → 拷入 raw/（去标识路径）
# → HEIC/PDF 批量转码到 .staging/rasters/<source_id>/ → 写 phase0_manifest.json。
# worker 只消费 manifest 给定的 ID 与 raster 路径，不自造 ID（消灭跨 slice ID 漂移）。
# 转不动的文件记 blocked 进 manifest，绝不静默跳过。
# 原始上传名只写入 raw/_FILENAME_MAPPING.md；manifest 和 worker 路径均不暴露原名。
#
# 用法: phase0_prepare.sh <patient_dir> <input_dir> [<input_dir>...]
# 依赖: shasum；HEIC 转码用 sips(macOS)；PDF 用 pdftoppm(poppler)。缺哪个,对应文件记 blocked。
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: phase0_prepare.sh <patient_dir> <input_dir>..." >&2; exit 2; }
PATIENT_DIR="$1"; shift
RASTER_ROOT="$PATIENT_DIR/.staging/rasters"
mkdir -p "$PATIENT_DIR/raw" "$PATIENT_DIR/ocr" "$RASTER_ROOT"
MANIFEST="$PATIENT_DIR/phase0_manifest.json"
FILENAME_MAPPING="$PATIENT_DIR/raw/_FILENAME_MAPPING.md"

entries="[]"
add_entry() { entries="$(python3 - "$entries" "$1" <<'EOF'
import json, sys
entries = json.loads(sys.argv[1]); entries.append(json.loads(sys.argv[2]))
print(json.dumps(entries, ensure_ascii=False))
EOF
)"; }

total=0; blocked=0
for input_dir in "$@"; do
  while IFS= read -r -d '' f; do
    base="$(basename "$f")"
    case "$base" in .DS_Store|._*) continue;; esac
    sha="$(shasum -a 256 "$f" | cut -d' ' -f1)"
    sid="SRC-${sha:0:12}"
    dedupe_state="$(python3 - "$entries" "$sid" "$sha" <<'EOF'
import json, sys

entries = json.loads(sys.argv[1])
source_id, sha256 = sys.argv[2:4]
if any(row["source_id"] == source_id and row["sha256"] != sha256 for row in entries):
    print("collision")
elif any(row["sha256"] == sha256 for row in entries):
    print("duplicate")
else:
    print("new")
EOF
)"
    if [[ "$dedupe_state" == "collision" ]]; then
      echo "phase0: source_id collision for $sid; full sha256 differs" >&2
      exit 1
    fi
    if [[ "$dedupe_state" == "duplicate" ]]; then
      add_entry "$(python3 - "$sid" "$base" "$sha" <<'EOF'
import json, sys
print(json.dumps({"source_id": sys.argv[1], "original_name": sys.argv[2],
                  "sha256": sys.argv[3], "content_duplicate": True},
                 ensure_ascii=False))
EOF
)"
      continue
    fi
    total=$((total+1))
    ext="$(printf '%s' "${base##*.}" | tr 'A-Z' 'a-z')"
    [[ "$base" == *.* ]] || ext=""
    if [[ "$ext" =~ ^[a-z0-9]{1,10}$ ]]; then
      safe_ext="$ext"
    else
      safe_ext="bin"
    fi
    raw_rel="raw/$sid/source.$safe_ext"
    mkdir -p "$PATIENT_DIR/raw/$sid"
    [[ -e "$PATIENT_DIR/$raw_rel" ]] || cp "$f" "$PATIENT_DIR/$raw_rel"
    raw_sha="$(shasum -a 256 "$PATIENT_DIR/$raw_rel" | cut -d' ' -f1)"
    [[ "$raw_sha" == "$sha" ]] || {
      echo "phase0: raw copy checksum mismatch for $sid" >&2
      exit 1
    }
    rasters="[]"; status="ok"
    rdir="$RASTER_ROOT/$sid"; mkdir -p "$rdir"
    case "$ext" in
      jpg|jpeg|png|webp|gif)
        rasters="[\"$raw_rel\"]";;
      heic|heif)
        if command -v sips >/dev/null && sips -s format jpeg "$f" --out "$rdir/page1.jpg" >/dev/null 2>&1; then
          rasters="[\".staging/rasters/$sid/page1.jpg\"]"
        else status="blocked_transcode"; blocked=$((blocked+1)); fi;;
      pdf)
        if command -v pdftoppm >/dev/null && pdftoppm -png -r 150 "$f" "$rdir/page" >/dev/null 2>&1; then
          rasters="$(python3 - "$rdir" "$sid" <<'EOF'
import json, pathlib, sys
pages = sorted(pathlib.Path(sys.argv[1]).glob("page*.png"))
print(json.dumps([f".staging/rasters/{sys.argv[2]}/{p.name}" for p in pages]))
EOF
)"
          [[ "$rasters" == "[]" ]] && { status="blocked_transcode"; blocked=$((blocked+1)); }
        else status="blocked_transcode"; blocked=$((blocked+1)); fi;;
      *) status="blocked_unsupported"; blocked=$((blocked+1));;
    esac
    add_entry "$(python3 - "$sid" "$base" "$raw_rel" "$sha" "$status" "$rasters" <<'EOF'
import json, sys
print(json.dumps({"source_id": sys.argv[1], "original_name": sys.argv[2], "raw_path": sys.argv[3],
                  "sha256": sys.argv[4], "status": sys.argv[5], "raster_paths": json.loads(sys.argv[6])},
                 ensure_ascii=False))
EOF
)"
  done < <(find "$input_dir" -type f ! -name '.DS_Store' ! -name '._*' -print0 | sort -z)
done

python3 - "$entries" "$total" "$blocked" "$FILENAME_MAPPING" > "$MANIFEST" <<'EOF'
import json, pathlib, sys

sources = json.loads(sys.argv[1])
manifest_sources = []
mapping_rows = []
canonical_by_sha = {
    source["sha256"]: source
    for source in sources
    if not source.get("content_duplicate")
}
for source in sources:
    source = dict(source)
    original_name = source.pop("original_name")
    canonical = canonical_by_sha[source["sha256"]]
    mapping_rows.append((original_name, canonical["raw_path"], source["source_id"]))
    if source.pop("content_duplicate", False):
        continue
    manifest_sources.append(source)

if len(manifest_sources) != int(sys.argv[2]):
    raise SystemExit("phase0: internal content-dedupe count mismatch")
blocked_count = sum(row["status"].startswith("blocked_") for row in manifest_sources)
if blocked_count != int(sys.argv[3]):
    raise SystemExit("phase0: internal blocked count mismatch")

def md_cell(value):
    return (str(value).replace("\\", "\\\\").replace("|", "\\|")
            .replace("\r", "\\r").replace("\n", "\\n"))

mapping = [
    "# Protected filename mapping",
    "",
    "This audit-only file stays under `raw/` and is excluded from exports.",
    "",
    "| verbatim_upload_name | deid_raw_name | source_id |",
    "|---|---|---|",
]
mapping.extend(
    f"| {md_cell(original)} | {md_cell(raw_path)} | {md_cell(source_id)} |"
    for original, raw_path, source_id in mapping_rows
)
pathlib.Path(sys.argv[4]).write_text("\n".join(mapping) + "\n", encoding="utf-8")

print(json.dumps({"schema": "phase0_manifest_v1", "total": int(sys.argv[2]),
                  "blocked": int(sys.argv[3]), "sources": manifest_sources},
                 ensure_ascii=False, indent=1))
EOF
echo "phase0: total=$total blocked=$blocked manifest=$MANIFEST"
