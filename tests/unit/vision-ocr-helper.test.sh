#!/usr/bin/env bash
# ORG-P1-01 — the Apple Vision second-read engine (scripts/vision_ocr.swift via scripts/run_ocr_engine.py):
#   * builds into $CB_ORGANIZE_CACHE_DIR (a temp dir here) and reads a synthetic rendered page;
#   * the same image read twice gives byte-identical JSON (a deterministic engine);
#   * the normalised document has the run_ocr_engine shape (engine / channel / pages / lines / confidence);
#   * `orient` finds the clockwise turn for a page rotated 90 / 180 / 270 degrees and writes an upright copy,
#     printing no recognised text;
#   * `which` picks apple_vision first; pinned `none` → exit 3.
# Skips off macOS, without swiftc, or without Pillow (used to draw the synthetic page).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ "$(uname -s)" != "Darwin" ]] || ! command -v swiftc >/dev/null 2>&1; then
  echo "SKIP: Apple Vision helper needs macOS + swiftc" >&2; exit 0
fi
if ! python3 -c "import PIL" 2>/dev/null; then
  echo "SKIP: Pillow not installed (draws the synthetic page)" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

CB_ORGANIZE_CACHE_DIR="$tmp/cache" python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, os, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO, TMP = Path(sys.argv[1]), Path(sys.argv[2])
S = REPO / "skills" / "cancer-buddy-organize" / "scripts"
passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def font(size):
    for f in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if Path(f).is_file():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


im = Image.new("RGB", (1200, 420), "white")
d = ImageDraw.Draw(im)
for i, line in enumerate(("SYNTHETIC ORDER SHEET", "DATE 2030-01-08", "CARBOPLATIN 300 mg")):
    d.text((40, 40 + 110 * i), line, font=font(56), fill="black")
page = TMP / "page.png"
im.save(page)
for deg in (90, 180, 270):
    im.rotate(-deg, expand=True).save(TMP / f"page_r{deg}.png")  # turned `deg` degrees clockwise


def roe(*args, env=None):
    return subprocess.run([sys.executable, str(S / "run_ocr_engine.py"), *args], capture_output=True, text=True, env=env)


p = roe("which")
check("which → apple_vision on macOS", p.returncode == 0 and json.loads(p.stdout)["engine"] == "apple_vision", p.stdout + p.stderr)
check("the helper is compiled into the cache dir, keyed by source hash",
      any(x.name.startswith("vision_ocr-") for x in (TMP / "cache").iterdir()), str(list((TMP / "cache").iterdir())))
p1 = roe("read", str(page), "--out", str(TMP / "a.json"), "--engine", "apple_vision")
p2 = roe("read", str(page), "--out", str(TMP / "b.json"), "--engine", "apple_vision")
check("read exit 0 twice", p1.returncode == 0 and p2.returncode == 0, p1.stderr + p2.stderr)
a, b = (TMP / "a.json").read_bytes(), (TMP / "b.json").read_bytes()
check("the same image read twice → byte-identical output", a == b)
doc = json.loads(a)
check("document shape: tool / engine / channel / scale",
      (doc["tool"], doc["engine"], doc["channel"], doc["confidence_scale"]) ==
      ("run_ocr_engine", "apple_vision", "deterministic_ocr:apple_vision", "0-1"), str({k: doc[k] for k in ("tool", "engine")}))
lines = doc["pages"][0]["lines"]
check("lines carry text, a 0-1 confidence, a bbox and candidates",
      lines and all(isinstance(l["text"], str) and 0 <= l["confidence"] <= 1 and len(l["bbox"]) == 4
                    and isinstance(l["candidates"], list) for l in lines), str(lines)[:300])
joined = " ".join(l["text"] for l in lines)
check("the synthetic page is read (2030-01-08 / 300 mg)", "2030-01-08" in joined and "300" in joined, joined)
check("provenance: revision and OS version recorded", "revision" in (doc.get("engine_version") or "") and doc.get("os_version"))

for deg, want in ((0, 0), (90, 270), (180, 180), (270, 90)):
    src = page if deg == 0 else TMP / f"page_r{deg}.png"
    p = roe("orient", str(src), "--out-dir", str(TMP / "o"), "--engine", "apple_vision")
    out = json.loads(p.stdout) if p.returncode == 0 else {}
    check(f"orient: page turned {deg}° → rotate {want}° clockwise", out.get("content_rotation") == want, p.stdout + p.stderr)
    check(f"orient {deg}°: prints no recognised text", "2030" not in p.stdout and "CARBOPLATIN" not in p.stdout, p.stdout)
    if out.get("oriented"):
        up = Image.open(out["oriented"])
        check(f"orient {deg}°: the upright copy is landscape like the original", up.size[0] > up.size[1], str(up.size))

p = roe("which", env=dict(os.environ, CB_ORGANIZE_OCR_ENGINE="none"))
check("which with the engine pinned to none → exit 3", p.returncode == 3, p.stdout)

print(f"vision-ocr-helper: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
