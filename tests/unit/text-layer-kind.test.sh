#!/usr/bin/env bash
# ORG-P0-03 — scripts/text_layer_kind.py page types on four synthetic PDFs (made with PyMuPDF here):
#   born-digital text → born_digital; an image-only page → absent; an image page with an invisible OCR
#   text layer → embedded_ocr; a born-digital layer with a damaged glyph run (`le!t`) → born_digital
#   plus glyph_anomaly_lines. Also the born-digital identity check of second_read_align.py --text-layer.
# Skips when PyMuPDF is not installed (the poppler fallback is exercised when poppler is present).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import fitz" 2>/dev/null; then
  echo "SKIP: PyMuPDF (fitz) not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, os, shutil, subprocess, sys
from pathlib import Path
import fitz

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


def grey_pixmap():
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 80), False)
    pix.clear_with(200)
    return pix


def pdf(name, build):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    build(page)
    out = TMP / name
    doc.save(out)
    return out


born = pdf("born.pdf", lambda p: p.insert_text((72, 90), "Synthetic discharge summary 2030-01-10\nleft lung nodule 8 mm",
                                               fontsize=12))
image_only = pdf("image.pdf", lambda p: p.insert_image(p.rect, pixmap=grey_pixmap()))


def ocr_layer(p):
    p.insert_image(p.rect, pixmap=grey_pixmap())
    p.insert_text((72, 90), "Synthetic scanned page 2030-01-10", fontsize=12, render_mode=3)


embedded = pdf("embedded.pdf", ocr_layer)
damaged = pdf("damaged.pdf", lambda p: p.insert_text((72, 90), "Synthetic report\nThe le!t lung shows a nodule", fontsize=12))


def run(path, env=None):
    p = subprocess.run([sys.executable, str(S / "text_layer_kind.py"), str(path)], capture_output=True, text=True,
                       env=env)
    return p.returncode, (json.loads(p.stdout) if p.returncode == 0 else p.stderr)


for label, path, want in [("born-digital", born, "born_digital"), ("image only", image_only, "absent"),
                          ("image + invisible OCR layer", embedded, "embedded_ocr"), ("damaged glyphs", damaged, "born_digital")]:
    rc, doc = run(path)
    kinds = [p["kind"] for p in doc["pages"]] if rc == 0 else doc
    check(f"{label} → {want}", rc == 0 and kinds == [want], str(kinds))

rc, doc = run(damaged)
lines = doc["pages"][0]["glyph_anomaly_lines"] if rc == 0 else []
check("damaged glyph run listed (le!t)", any("le!t" in l["text"] for l in lines), str(lines))
rc, doc = run(born)
check("a clean born-digital layer lists no glyph anomaly", rc == 0 and doc["pages"][0]["glyph_anomaly_lines"] == [], str(doc))
check("summary lists the born-digital page", rc == 0 and doc["summary"]["born_digital"] == [1], str(doc))
rc, doc = run(TMP / "missing.pdf")
check("missing file → exit 2", rc == 2, str(doc))
(TMP / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
rc, doc = run(TMP / "broken.pdf")
check("unreadable PDF → exit 2 (the worker writes a stub)", rc == 2, str(doc))

# the born-digital identity check (second_read_align.py --text-layer): the text layer is the body, no OCR
pd = TMP / "pd"
(pd / "ocr").mkdir(parents=True)
(pd / "raw" / "_extract").mkdir(parents=True)
layer = pd / "raw" / "_extract" / "s002.text_layer.txt"
layer.write_text("Synthetic discharge summary 2030-01-10\nleft lung nodule 8 mm\n", encoding="utf-8")
hdr = ("SOURCE: discharge_summary\nFILE_ID: s002\nEXTRACTOR: p1-s002-1\nPRIMARY_CHANNEL: text_layer\nSECOND_READ_CHANNEL: none\n"
       "INDEPENDENT_REREAD: false\nREAD_MODE: native_text\nADAPTER: pdf_pages\nCONFIDENCE: medium\nSHA256: " + "cd" * 32 +
       "\nPAGE_LABEL: null\nMODALITY: text\n")
sc = pd / "ocr" / "s002.md"
sc.write_text(hdr + "\nSynthetic discharge summary 2030-01-10\nleft lung nodule 8 mm\n\n## PII\n\nmasked: none\n", encoding="utf-8")
p = subprocess.run([sys.executable, str(S / "second_read_align.py"), "--apply", str(sc), "--patient-dir", str(pd),
                    "--text-layer", str(layer)], capture_output=True, text=True)
out = json.loads(p.stdout) if p.returncode == 0 else {}
t = sc.read_text(encoding="utf-8")
check("born-digital identity: exit 0, not_applicable", p.returncode == 0 and out.get("high_risk_review_status") == "not_applicable",
      p.stdout + p.stderr)
check("born-digital identity: 2/2 lines match, no OCR engine line", "identity: 2/2" in t and "engine: text_layer_identity" in t, t)
check("born-digital identity: SECOND none, INDEPENDENT false, CONFIDENCE medium",
      "SECOND_READ_CHANNEL: none" in t and "INDEPENDENT_REREAD: false" in t and "CONFIDENCE: medium" in t)
sys.path.insert(0, str(S))
import second_read_align as sra
check("born-digital identity: --check passes", sra.check(sc, pd)[0] == [], str(sra.check(sc, pd)))
sc.write_text(t.replace("left lung nodule 8 mm", "left lung nodule 9 mm"), encoding="utf-8")
check("born-digital identity: a body edit after the check → body_sha256 ERROR", any("body_sha256" in e for e in sra.check(sc, pd)[0]))
sc.write_text(hdr.replace("PRIMARY_CHANNEL: text_layer", "PRIMARY_CHANNEL: llm_vision") + "\nx\n\n## PII\n\nmasked: none\n",
              encoding="utf-8")
p = subprocess.run([sys.executable, str(S / "second_read_align.py"), "--apply", str(sc), "--patient-dir", str(pd),
                    "--text-layer", str(layer)], capture_output=True, text=True)
check("--text-layer on a sidecar whose primary is not text_layer → exit 2", p.returncode == 2, p.stderr)

# poppler fallback (only when poppler is installed)
if all(shutil.which(t) for t in ("pdfinfo", "pdfimages", "pdftotext", "pdffonts")):
    env = dict(os.environ, CB_TEXT_LAYER_METHOD="poppler")
    for label, path, want in [("born-digital", born, "born_digital"), ("image only", image_only, "absent")]:
        rc, doc = run(path, env)
        check(f"poppler fallback: {label} → {want}", rc == 0 and doc["method"] == "poppler"
              and [p["kind"] for p in doc["pages"]] == [want], str(doc)[:300])

print(f"text-layer-kind: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
