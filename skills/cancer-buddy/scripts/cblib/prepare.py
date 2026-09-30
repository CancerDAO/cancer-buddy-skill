"""organize stage 0: inputs -> raw/ originals + per-page images/text in .work/pages/.

No model involved. Idempotent: re-running with the same files adds nothing.
"""
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from .common import (load_json, write_json, sha256_file, now_iso, new_patient_code,
                     patients_root, PATIENT_CODE_RE)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
HEIC_EXT = {".heic", ".heif"}
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm"}
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".rar", ".7z")
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
RENDER_DPI = 150


# --- input discovery ----------------------------------------------------------

def _is_archive(p: Path) -> bool:
    return p.name.lower().endswith(ARCHIVE_SUFFIXES)


def _unpack(archive: Path, dest: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                fname = info.filename
                if not (info.flag_bits & 0x800):          # legacy zip names from Chinese Windows
                    try:
                        fname = fname.encode("cp437").decode("gbk")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                target = (dest / fname).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    continue                              # path traversal
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    elif name.endswith((".rar", ".7z")):
        subprocess.run(["tar", "-xf", str(archive), "-C", str(dest)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    else:
        with tarfile.open(archive) as t:
            safe = [m for m in t.getmembers()
                    if not m.name.startswith("/") and ".." not in Path(m.name).parts]
            t.extractall(dest, members=safe)


def _walk_inputs(paths, tmp_root: Path):
    """Yield (file_path, display_name). Archives are unpacked (recursively) into tmp_root."""
    stack = [(Path(p).expanduser(), Path(p).name) for p in paths]
    n = 0
    while stack:
        p, shown = stack.pop(0)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    stack.append((child, str(Path(shown) / child.relative_to(p))))
            continue
        if not p.is_file():
            continue
        parts = Path(shown).parts
        if p.name in JUNK_NAMES or "__MACOSX" in parts or p.name.startswith("._"):
            continue
        if _is_archive(p):
            n += 1
            dest = tmp_root / f"a{n}"
            dest.mkdir(parents=True)
            try:
                _unpack(p, dest)
            except Exception as e:                        # noqa: BLE001 - report, keep going
                yield p, shown, f"archive_unreadable: {e}"
                continue
            stack.append((dest, shown))
            continue
        yield p, shown, None


# --- page extraction ------------------------------------------------------------

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _pdf_pages(pdf: Path, out_dir: Path) -> dict:
    """Render every page to PNG and save its text layer. Returns page info."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None
    pages, any_text = 0, False
    if fitz is not None:
        with fitz.open(pdf) as doc:
            pages = doc.page_count
            for i, page in enumerate(doc, 1):
                page.get_pixmap(dpi=RENDER_DPI).save(str(out_dir / f"p{i:03d}.png"))
                text = page.get_text("text").replace("\f", "\n").strip()
                (out_dir / f"p{i:03d}.txt").write_text(text, encoding="utf-8")
                any_text = any_text or len(text) > 20
        return {"page_count": pages, "text_layer": any_text}
    if not (_have("pdftoppm") and _have("pdftotext")):
        raise RuntimeError("需要 PyMuPDF（pip install pymupdf）或 poppler（brew install poppler）来处理 PDF")
    subprocess.run(["pdftoppm", "-r", str(RENDER_DPI), "-png", str(pdf), str(out_dir / "p")], check=True)
    rendered = sorted(out_dir.glob("p-*.png"))
    for i, img in enumerate(rendered, 1):
        img.rename(out_dir / f"p{i:03d}.png")
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(i), "-l", str(i), str(pdf), "-"],
                             capture_output=True, text=True).stdout.replace("\f", "\n").strip()
        (out_dir / f"p{i:03d}.txt").write_text(txt, encoding="utf-8")
        any_text = any_text or len(txt) > 20
    return {"page_count": len(rendered), "text_layer": any_text}


def _docx_text(path: Path) -> str:
    import re
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml).strip()


_XL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_XL_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_XL_DATE_IDS = set(range(14, 23)) | {45, 46, 47}


def _xlsx_text(path: Path) -> str:
    """Every sheet as a Markdown table, standard library only. Dates come back as dates, not serials."""
    import re
    import datetime as dt
    import xml.etree.ElementTree as ET

    def col_index(ref):
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group(0):
            n = n * 26 + ord(ch) - 64
        return n - 1

    def cell_text(x):
        return (x or "").replace("|", "/").replace("\r", " ").replace("\n", " ").strip()

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_XL}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_XL}t")))
        date_styles, time_styles = set(), set()
        if "xl/styles.xml" in names:
            st = ET.fromstring(z.read("xl/styles.xml"))
            custom = {int(n.get("numFmtId")): n.get("formatCode", "") for n in st.iter(f"{_XL}numFmt")}
            xfs = st.find(f"{_XL}cellXfs")
            for i, xf in enumerate(xfs if xfs is not None else []):
                fid = int(xf.get("numFmtId", 0))
                code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fid, "")).lower()
                if fid in _XL_DATE_IDS or "y" in code or "d" in code:
                    date_styles.add(i)
                if fid in (18, 19, 20, 21, 22, 45, 46, 47) or "h" in code:
                    time_styles.add(i)
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                target = r.get("Target", "").lstrip("/")
                rels[r.get("Id")] = target if target.startswith("xl/") else "xl/" + target
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        out = []
        for sheet in wb.iter(f"{_XL}sheet"):
            target = rels.get(sheet.get(_XL_REL))
            if not target or target not in names:
                continue
            rows = []
            for row in ET.fromstring(z.read(target)).iter(f"{_XL}row"):
                cells = {}
                for c in row.findall(f"{_XL}c"):
                    t, v = c.get("t"), c.find(f"{_XL}v")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{_XL}t"))
                    elif v is None:
                        continue
                    elif t == "s":
                        val = shared[int(v.text)]
                    elif t == "b":
                        val = "TRUE" if v.text == "1" else "FALSE"
                    elif t in ("str", "e"):
                        val = v.text or ""
                    else:
                        val = v.text or ""
                        style = int(c.get("s", 0))
                        if style in date_styles and re.match(r"^-?\d+(\.\d+)?$", val):
                            when = dt.datetime(1899, 12, 30) + dt.timedelta(days=float(val))
                            val = when.strftime("%Y-%m-%d %H:%M" if style in time_styles or when.time() != dt.time(0)
                                                else "%Y-%m-%d")
                    cells[col_index(c.get("r", "A"))] = cell_text(val)
                if any(cells.values()):
                    rows.append(cells)
            out.append(f"## 工作表：{sheet.get('name', '')}\n")
            if not rows:
                out.append("（空表）\n")
                continue
            width = max(max(r) for r in rows) + 1
            table = [[r.get(i, "") for i in range(width)] for r in rows]
            out.append("| " + " | ".join(table[0]) + " |")
            out.append("|" + "---|" * width)
            out += ["| " + " | ".join(r) + " |" for r in table[1:]]
            out.append("")
    return "\n".join(out).strip()


def _extract_pages(src: Path, out_dir: Path) -> dict:
    ext = src.suffix.lower()
    if ext == ".pdf":
        info = _pdf_pages(src, out_dir)
        info["kind"] = "pdf"
        return info
    out_dir.mkdir(parents=True, exist_ok=True)
    if ext in IMAGE_EXT:
        shutil.copyfile(src, out_dir / f"p001{ext}")
        return {"kind": "image", "page_count": 1, "text_layer": False}
    if ext in HEIC_EXT:
        if not _have("sips"):
            raise RuntimeError("HEIC 照片需要 macOS 的 sips 转换；请先把照片导出为 JPG")
        subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(out_dir / "p001.jpg")],
                       check=True, stdout=subprocess.DEVNULL)
        return {"kind": "image", "page_count": 1, "text_layer": False}
    if ext == ".docx":
        (out_dir / "p001.txt").write_text(_docx_text(src), encoding="utf-8")
        return {"kind": "text", "page_count": 1, "text_layer": True}
    if ext in (".xlsx", ".xlsm"):
        (out_dir / "p001.txt").write_text(_xlsx_text(src), encoding="utf-8")
        return {"kind": "text", "page_count": 1, "text_layer": True}
    if ext in TEXT_EXT:
        (out_dir / "p001.txt").write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        return {"kind": "text", "page_count": 1, "text_layer": True}
    return {"kind": "unsupported", "page_count": 0, "text_layer": False}


# --- patient dir --------------------------------------------------------------------

def _init_patient(patient_dir: Path, locale: str) -> None:
    for d in ("raw", ".work/pages", ".work/transcripts", ".work/tasks", "library"):
        (patient_dir / d).mkdir(parents=True, exist_ok=True)
    if not (patient_dir / "library/index.json").exists():
        write_json(patient_dir / "library/index.json", {"entries": []})
    if not (patient_dir / "profile.json").exists():
        write_json(patient_dir / "profile.json", {
            "schema": "cancer_buddy_profile_v3", "patient_code": patient_dir.name,
            "locale": locale, "generated_at": now_iso(), "privacy": "local_only",
            "summary": {}, "source_refs": []})


def _next_source_id(inv: dict) -> str:
    nums = [int(f["source_id"][1:]) for f in inv["files"] if f["source_id"][1:].isdigit()]
    return f"s{(max(nums) + 1) if nums else 1:03d}"


def _upgrade_v1(patient_dir: Path, inv: dict) -> list:
    """A v1 archive: park old transcripts in raw/_legacy_<ts>/, register raw originals as sources."""
    ts = now_iso().replace(":", "").replace("-", "")[:15]
    legacy = patient_dir / "raw" / f"_legacy_{ts}"
    moved = []
    for child in sorted(patient_dir.iterdir()):
        if child.is_dir() and (child.name[:3] in {f"{i:02d}_" for i in range(1, 15)} or child.name.startswith("99_")
                               or child.name == "ocr"):
            legacy.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(legacy / child.name))
            moved.append(child.name)
    originals = [p for p in sorted((patient_dir / "raw").rglob("*"))
                 if p.is_file() and not any(part.startswith(("_", ".")) for part in p.relative_to(patient_dir / "raw").parts)]
    return originals, moved


def prepare(inputs, patient_dir=None, locale="zh") -> dict:
    if patient_dir:
        patient_dir = Path(patient_dir).expanduser()
    else:
        patient_dir = patients_root() / new_patient_code()
    new_patient = not (patient_dir / "profile.json").exists()
    if new_patient and not PATIENT_CODE_RE.match(patient_dir.name):
        raise SystemExit(f"患者目录名必须是 PT-XXXXXXXXXX 形式：{patient_dir.name}")
    _init_patient(patient_dir, locale)

    inv_path = patient_dir / "source_inventory.json"
    inv = load_json(inv_path) or {"files": [], "skipped_inputs": []}
    inv.setdefault("files", [])
    inv.setdefault("skipped_inputs", [])
    known = {f["sha256"]: f.get("source_id", "v1") for f in inv["files"] if f.get("sha256")}
    known.update({s["sha256"]: "skipped" for s in inv["skipped_inputs"] if s.get("sha256")})

    added, skipped, upgraded = [], [], []
    run_mode = "full" if new_patient else "incremental"

    candidates = []                                     # (path, shown_name, in_raw_already)
    if inv.get("contract") != "v2" and not new_patient:
        originals, upgraded = _upgrade_v1(patient_dir, inv)
        inv["files"] = [f for f in inv["files"] if f.get("contract") == "v2"]
        known = {f["sha256"]: f["source_id"] for f in inv["files"]}
        candidates += [(p, p.relative_to(patient_dir).as_posix(), True) for p in originals]
        run_mode = "v1_upgrade"
    inv["contract"] = "v2"

    mapping = patient_dir / "raw" / "_FILENAME_MAPPING.md"
    if not mapping.exists():
        mapping.write_text("# 原始文件名对照（仅限本机，受控）\n\n| source_id | 原始文件名 |\n|---|---|\n", encoding="utf-8")

    n_skip = len(inv["skipped_inputs"])

    def skip(shown, reason, digest):
        nonlocal n_skip
        n_skip += 1
        handle = f"skip-{n_skip:03d}"
        with open(mapping, "a", encoding="utf-8") as f:
            f.write(f"| {handle} | {shown.replace('|', '/')} |\n")
        skipped.append({"input_ref": f"raw/_FILENAME_MAPPING.md#{handle}", "reason": reason, "sha256": digest})

    with tempfile.TemporaryDirectory(prefix="cb-unpack-") as tmp:
        stream = [(p, s, True, None) for p, s, _ in candidates]
        stream += [(p, s, False, err) for p, s, err in _walk_inputs(inputs, Path(tmp))]
        for path, shown, in_raw, err in stream:
            if err:
                skip(shown, err, None)
                continue
            if path.stat().st_size == 0:
                skip(shown, "empty_file", None)
                continue
            digest = sha256_file(path)
            if digest in known:
                skip(shown, f"duplicate_of:{known[digest]}", digest)
                continue
            sid = _next_source_id(inv)
            if in_raw:
                raw_path = path
            else:
                raw_path = patient_dir / "raw" / f"{sid}{path.suffix.lower()}"
                shutil.copy2(path, raw_path)
            try:
                info = _extract_pages(raw_path, patient_dir / ".work" / "pages" / sid)
            except Exception as e:                      # noqa: BLE001
                info = {"kind": "unsupported", "page_count": 0, "text_layer": False, "error": str(e)}
            entry = {
                "source_id": sid, "contract": "v2",
                "original_name_ref": f"raw/_FILENAME_MAPPING.md#{sid}",
                "raw_path": raw_path.relative_to(patient_dir).as_posix(),
                "sha256": digest, "size_bytes": raw_path.stat().st_size,
                "kind": info["kind"], "page_count": info["page_count"], "text_layer": info["text_layer"],
                "sidecar_paths": [], "doc_kinds": [], "added_at": now_iso(),
            }
            if info.get("error"):
                entry["error"] = info["error"]
            inv["files"].append(entry)
            known[digest] = sid
            with open(mapping, "a", encoding="utf-8") as f:
                f.write(f"| {sid} | {shown.replace('|', '/')} |\n")
            added.append({"source_id": sid, "kind": info["kind"], "pages": info["page_count"]})

    inv["skipped_inputs"].extend(skipped)
    write_json(inv_path, inv)
    # One open run accumulates every prepare until finish closes it.
    run_path = patient_dir / ".work" / "run.json"
    run = load_json(run_path) or {}
    if not run or run.get("finished"):
        run = {"started_at": now_iso(), "run_mode": run_mode, "added": [], "finished": False}
    if run_mode == "v1_upgrade":
        run["run_mode"] = run_mode
    run["added"] += [a["source_id"] for a in added]
    write_json(run_path, run)
    return {"patient_dir": str(patient_dir), "patient_code": patient_dir.name, "new_patient": new_patient,
            "run_mode": run_mode, "added": added, "skipped": skipped, "legacy_moved": upgraded}
