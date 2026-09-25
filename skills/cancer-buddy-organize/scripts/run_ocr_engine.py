#!/usr/bin/env python3
"""run_ocr_engine.py — the deterministic OCR engine behind the second read (phase1 §2, §4 C/E).

The engine never produces sidecar text: second_read_align.py --apply calls read_images() once per
page AFTER the model transcription is written, and compares. The worker itself only runs
`which` (which engine this host has) and `orient` (upright copies of the page images before anyone
reads them — the model and the engine see the same pixels; it prints the rotation, never any text).

Engines, in `auto` order:
  apple_vision — scripts/vision_ocr.swift (VNRecognizeTextRequest, accurate, zh-Hans + en-US, no
                 language correction), compiled once per source hash into
                 $CB_ORGANIZE_CACHE_DIR (default ~/.cache/cancer-buddy-organize)/vision_ocr-<sha12>;
                 macOS with swiftc only. Confidence 0–1 per observation (line).
  tesseract    — `tesseract <img> stdout -l chi_sim+eng tsv` (eng alone when chi_sim is missing);
                 confidence 0–100 per word.
  none         — no engine: exit 3 from `which`; the second read is then single-channel (every span
                 “无信号”), never a model re-read.

Normalised output (one JSON document for all pages of a source):
  {tool, version, engine, channel: deterministic_ocr:<engine>, engine_version, os_version, languages,
   confidence_scale, no_signal_below, pages: [{page, image, image_sha256, width, height,
   lines: [{text, confidence, bbox, candidates?, words?: [{text, confidence, bbox}]}]}]}

CLI:
    run_ocr_engine.py which [--engine auto]
    run_ocr_engine.py orient <image> --out-dir <patient_dir>/raw/_extract [--engine auto]
    run_ocr_engine.py read <image>… --out <file> [--engine auto]      (second_read_align.py does this)
    run_ocr_engine.py parse-tsv <tesseract.tsv> --out <file> [--image <image>]   (replay of a saved TSV)
Exit: 0 ok; 2 bad invocation; 3 no engine on this host; 4 the engine failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SWIFT_SRC = HERE / "vision_ocr.swift"
CACHE_ENV = "CB_ORGANIZE_CACHE_DIR"
ENGINE_ENV = "CB_ORGANIZE_OCR_ENGINE"  # tests pin an engine (or none) without touching PATH
ORDER = ("apple_vision", "tesseract")
SCALE = {"apple_vision": "0-1", "tesseract": "0-100"}
NO_SIGNAL_BELOW = {"apple_vision": 0.5, "tesseract": 50.0}


class EngineError(RuntimeError):
    pass


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_dir() -> Path:
    env = os.environ.get(CACHE_ENV)
    return Path(env) if env else Path.home() / ".cache" / "cancer-buddy-organize"


# ------------------------------------------------------------------ availability

def vision_binary(build: bool = True) -> Path | None:
    """The compiled Apple Vision helper (built on first use, cached by source hash)."""
    if platform.system() != "Darwin" or not SWIFT_SRC.is_file() or not shutil.which("swiftc"):
        return None
    tag = hashlib.sha256(SWIFT_SRC.read_bytes()).hexdigest()[:12]
    out = cache_dir() / f"vision_ocr-{tag}"
    if out.is_file() and os.access(out, os.X_OK):
        return out
    if not build:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(f".tmp{os.getpid()}")
    proc = subprocess.run(["swiftc", "-O", "-o", str(tmp), str(SWIFT_SRC)], capture_output=True, text=True,
                          timeout=600)
    if proc.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return None
    tmp.replace(out)
    return out


def tesseract_langs() -> list[str]:
    if not shutil.which("tesseract"):
        return []
    proc = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=60)
    have = {l.strip() for l in (proc.stdout + proc.stderr).splitlines()}
    return [l for l in ("chi_sim", "eng") if l in have] or (["eng"] if "eng" in have else [])


def available(name: str) -> bool:
    if name == "apple_vision":
        return vision_binary() is not None
    if name == "tesseract":
        return bool(tesseract_langs())
    return False


def pick_engine(requested: str = "auto") -> str | None:
    """apple_vision → tesseract → None; $CB_ORGANIZE_OCR_ENGINE (apple_vision | tesseract | none) pins it."""
    pinned = os.environ.get(ENGINE_ENV)
    if pinned:
        requested = pinned
    if requested == "none":
        return None
    if requested != "auto":
        return requested if available(requested) else None
    for name in ORDER:
        if available(name):
            return name
    return None


# ------------------------------------------------------------------ engines

def _run_vision(image: Path, mode: str = "recognize") -> dict:
    binary = vision_binary()
    if binary is None:
        raise EngineError("the Apple Vision helper is not available (macOS + swiftc)")
    proc = subprocess.run([str(binary), mode, str(image)], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise EngineError(proc.stderr.strip()[:300] or f"vision_ocr exit {proc.returncode}")
    return json.loads(proc.stdout)


def _vision_page(image: Path, page_no: int, rel: str) -> tuple[dict, dict]:
    doc = _run_vision(image)
    obs = doc.get("observations") or []
    # reading order: top to bottom (bbox is top-left origin, normalised), then left to right
    obs.sort(key=lambda o: (round((o["bbox"][1] + o["bbox"][3] / 2) * 50), o["bbox"][0]))
    lines = [{"text": o.get("text", ""), "confidence": o.get("confidence"), "bbox": o.get("bbox"),
              "candidates": o.get("candidates") or []} for o in obs]
    page = {"page": page_no, "image": rel, "image_sha256": _sha256(image), "width": doc.get("width"),
            "height": doc.get("height"), "lines": lines}
    meta = {"engine_version": f"VNRecognizeTextRequest revision {doc.get('revision')}",
            "os_version": doc.get("os_version"), "languages": doc.get("languages")}
    return page, meta


def parse_tsv(tsv_text: str) -> list[dict]:
    """Tesseract TSV → lines (grouped by block / paragraph / line) with their words and confidences;
    a line's confidence is its lowest word confidence."""
    rows = tsv_text.splitlines()
    if not rows:
        return []
    head = rows[0].split("\t")
    idx = {k: i for i, k in enumerate(head)}
    lines: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows[1:]:
        c = r.split("\t")
        if len(c) < len(head) or c[idx["level"]] != "5":
            continue
        text = c[idx["text"]]
        if not text.strip():
            continue
        try:
            conf = float(c[idx["conf"]])
        except ValueError:
            conf = -1.0
        key = (int(c[idx["page_num"]]), int(c[idx["block_num"]]), int(c[idx["par_num"]]), int(c[idx["line_num"]]))
        bbox = [int(c[idx["left"]]), int(c[idx["top"]]), int(c[idx["width"]]), int(c[idx["height"]])]
        if key not in lines:
            lines[key] = {"words": []}
            order.append(key)
        lines[key]["words"].append({"text": text, "confidence": conf, "bbox": bbox})
    out = []
    for key in order:
        ws = lines[key]["words"]
        x0 = min(w["bbox"][0] for w in ws)
        y0 = min(w["bbox"][1] for w in ws)
        x1 = max(w["bbox"][0] + w["bbox"][2] for w in ws)
        y1 = max(w["bbox"][1] + w["bbox"][3] for w in ws)
        out.append({"text": " ".join(w["text"] for w in ws), "confidence": min(w["confidence"] for w in ws),
                    "bbox": [x0, y0, x1 - x0, y1 - y0], "words": ws})
    return out


def _tesseract_version() -> str | None:
    proc = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=60)
    first = (proc.stdout or proc.stderr).splitlines()
    return first[0].strip() if first else None


def _tesseract_page(image: Path, page_no: int, rel: str) -> tuple[dict, dict]:
    langs = tesseract_langs()
    if not langs:
        raise EngineError("tesseract is not installed")
    proc = subprocess.run(["tesseract", str(image), "stdout", "-l", "+".join(langs), "tsv"], capture_output=True,
                          text=True, timeout=600)
    if proc.returncode != 0:
        raise EngineError(proc.stderr.strip()[:300] or f"tesseract exit {proc.returncode}")
    page = {"page": page_no, "image": rel, "image_sha256": _sha256(image), "width": None, "height": None,
            "lines": parse_tsv(proc.stdout)}
    return page, {"engine_version": _tesseract_version(), "os_version": platform.platform(), "languages": langs}


def _doc(engine: str, pages: list[dict], meta: dict) -> dict:
    return {"tool": "run_ocr_engine", "version": "1", "engine": engine, "channel": f"deterministic_ocr:{engine}",
            "engine_version": meta.get("engine_version"), "os_version": meta.get("os_version"),
            "languages": meta.get("languages"), "confidence_scale": SCALE[engine],
            "no_signal_below": NO_SIGNAL_BELOW[engine], "pages": pages}


def _relpath(image: Path, base: Path | None) -> str:
    if base is not None:
        try:
            return image.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    return image.name


def read_images(images: list[Path], engine: str, patient_dir: Path | None = None) -> dict:
    fn = {"apple_vision": _vision_page, "tesseract": _tesseract_page}.get(engine)
    if fn is None:
        raise EngineError(f"unknown engine {engine!r}")
    pages, meta = [], {}
    for n, img in enumerate(images, start=1):
        page, meta = fn(img, n, _relpath(img, patient_dir))
        pages.append(page)
    return _doc(engine, pages, meta)


# ------------------------------------------------------------------ orientation

def _exif_rotation(image: Path) -> int:
    try:
        from PIL import Image
        with Image.open(image) as im:
            o = im.getexif().get(0x0112, 1)
    except Exception:
        return 0
    return {3: 180, 6: 90, 8: 270}.get(o, 0)


def _content_rotation(image: Path, engine: str | None) -> tuple[int, str]:
    """Clockwise degrees that make the text upright, from the engine (no text is returned)."""
    if engine == "apple_vision":
        doc = _run_vision(image, "orient")
        return int(doc.get("rotation", 0)) % 360, "apple_vision"
    if engine == "tesseract" and shutil.which("tesseract"):
        proc = subprocess.run(["tesseract", str(image), "stdout", "--psm", "0", "-l", "osd"], capture_output=True,
                              text=True, timeout=300)
        for line in (proc.stdout or "").splitlines():
            if line.startswith("Rotate:"):
                try:
                    return int(line.split(":", 1)[1].strip()) % 360, "tesseract_osd"
                except ValueError:
                    break
    return 0, "none"


def _rotate(src: Path, dst: Path, exif_deg: int, content_deg: int) -> str:
    """Write the upright copy: EXIF applied, then the content rotation (clockwise); no EXIF left."""
    try:
        from PIL import Image, ImageOps
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            if content_deg:
                im = im.rotate(-content_deg, expand=True)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.save(dst)
        return "pil"
    except ImportError:
        pass
    if shutil.which("sips"):
        deg = (exif_deg + content_deg) % 360
        subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(dst)], capture_output=True, timeout=120)
        if deg:
            subprocess.run(["sips", "-r", str(deg), str(dst)], capture_output=True, timeout=120)
        return "sips"
    shutil.copyfile(src, dst)
    return "copy"


def orient(image: Path, out_dir: Path, engine: str | None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = image.stem
    dst = out_dir / f"{stem}.oriented.png"
    exif = _exif_rotation(image)
    tmp = out_dir / f"{stem}.exif.png"
    _rotate(image, tmp, exif, 0)
    content, method = _content_rotation(tmp, engine)
    tool = _rotate(tmp, dst, 0, content)
    tmp.unlink(missing_ok=True)
    return {"oriented": dst.as_posix(), "exif_rotation": exif, "content_rotation": content,
            "method": method, "writer": tool, "sha256": _sha256(dst)}


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("which")
    w.add_argument("--engine", default="auto")
    o = sub.add_parser("orient")
    o.add_argument("image")
    o.add_argument("--out-dir", required=True)
    o.add_argument("--engine", default="auto")
    r = sub.add_parser("read")
    r.add_argument("images", nargs="+")
    r.add_argument("--out", required=True)
    r.add_argument("--engine", default="auto")
    r.add_argument("--patient-dir")
    t = sub.add_parser("parse-tsv")
    t.add_argument("tsv")
    t.add_argument("--out", required=True)
    t.add_argument("--image")
    a = ap.parse_args(argv)
    if a.cmd == "which":
        e = pick_engine(a.engine)
        print(json.dumps({"engine": e, "channel": f"deterministic_ocr:{e}" if e else "none"}))
        if e == "tesseract":
            print("WARN: only tesseract is available as the second-read engine — it reads fewer printed Chinese "
                  "characters correctly, so more high-risk fields stay single-channel; on macOS install the Xcode "
                  "command-line tools (swiftc) for apple_vision", file=sys.stderr)
        elif e is None:
            print("WARN: no OCR engine — every high-risk field will be a single-channel read (no second read)",
                  file=sys.stderr)
        return 0 if e else 3
    if a.cmd == "orient":
        e = pick_engine(a.engine)
        try:
            print(json.dumps(orient(Path(a.image), Path(a.out_dir), e), ensure_ascii=False))
        except EngineError as ex:
            print(json.dumps({"error": str(ex)}), file=sys.stderr)
            return 4
        return 0
    if a.cmd == "read":
        e = pick_engine(a.engine)
        if e is None:
            print(json.dumps({"error": "no deterministic OCR engine on this host"}), file=sys.stderr)
            return 3
        try:
            doc = read_images([Path(p) for p in a.images], e, Path(a.patient_dir) if a.patient_dir else None)
        except EngineError as ex:
            print(json.dumps({"error": str(ex)}), file=sys.stderr)
            return 4
        Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"engine": e, "pages": len(doc["pages"]), "out": a.out}))
        return 0
    if a.cmd == "parse-tsv":
        tsv = Path(a.tsv)
        img = Path(a.image) if a.image else None
        page = {"page": 1, "image": img.name if img else None,
                "image_sha256": _sha256(img) if img and img.is_file() else None, "width": None, "height": None,
                "lines": parse_tsv(tsv.read_text(encoding="utf-8", errors="replace"))}
        doc = _doc("tesseract", [page], {"engine_version": None, "os_version": None, "languages": None})
        Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"engine": "tesseract", "lines": len(page["lines"]), "out": a.out}))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
