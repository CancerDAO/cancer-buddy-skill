#!/usr/bin/env bash
# phase0_prepare.sh — Kimi/lite 绑定的确定性前置（零 LLM）。
#
# 一次性完成：原件 sha256 → 预分配 source_id(SRC-<hash12>) → 拷入 raw/（保原名子目录）
# → HEIC/PDF 批量转码到 .staging/rasters/<source_id>/ → 写 phase0_manifest.json。
# worker 只消费 manifest 给定的 ID 与 raster 路径，不自造 ID（消灭跨 slice ID 漂移）。
# 转不动的文件记 blocked 进 manifest，绝不静默跳过。
#
# 用法: phase0_prepare.sh <patient_dir> <input_dir> [<input_dir>...]
# 依赖: shasum；HEIC 转码用 sips(macOS)；PDF 用 pdftoppm(poppler)。缺哪个,对应文件记 blocked。
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: phase0_prepare.sh <patient_dir> <input_dir>..." >&2; exit 2; }
PATIENT_DIR="$1"; shift
RASTER_ROOT="$PATIENT_DIR/.staging/rasters"
mkdir -p "$PATIENT_DIR/raw" "$PATIENT_DIR/ocr" "$RASTER_ROOT"
MANIFEST="$PATIENT_DIR/phase0_manifest.json"

entries="[]"
add_entry() { entries="$(python3 - "$entries" "$1" <<'EOF'
import json, sys
entries = json.loads(sys.argv[1]); entries.append(json.loads(sys.argv[2]))
print(json.dumps(entries, ensure_ascii=False))
EOF
)"; }

total=0; blocked=0
for input_dir in "$@"; do
  subdir="$(basename "$input_dir")"
  while IFS= read -r -d '' f; do
    base="$(basename "$f")"
    case "$base" in .DS_Store|._*) continue;; esac
    total=$((total+1))
    sha="$(shasum -a 256 "$f" | cut -d' ' -f1)"
    sid="SRC-${sha:0:12}"
    mkdir -p "$PATIENT_DIR/raw/$subdir"
    cp -n "$f" "$PATIENT_DIR/raw/$subdir/$base" 2>/dev/null || true
    raw_rel="raw/$subdir/$base"
    ext="$(echo "${base##*.}" | tr 'A-Z' 'a-z')"
    rasters="[]"; status="ok"
    rdir="$RASTER_ROOT/$sid"; mkdir -p "$rdir"
    case "$ext" in
      jpg|jpeg|png|webp|gif)
        rasters="[\"$(cd "$PATIENT_DIR" && python3 -c "import os.path,sys;print(os.path.relpath(sys.argv[1], '.'))" "$PATIENT_DIR/raw/$subdir/$base" 2>/dev/null || echo "$raw_rel")\"]";;
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
  done < <(find "$input_dir" -maxdepth 1 -type f -print0 | sort -z)
done

python3 - "$entries" "$total" "$blocked" > "$MANIFEST" <<'EOF'
import json, sys
print(json.dumps({"schema": "phase0_manifest_v1", "total": int(sys.argv[2]),
                  "blocked": int(sys.argv[3]), "sources": json.loads(sys.argv[1])},
                 ensure_ascii=False, indent=1))
EOF
echo "phase0: total=$total blocked=$blocked manifest=$MANIFEST"
