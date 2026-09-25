#!/usr/bin/env python3
"""page_completeness.py — missing / duplicate page detector for a patient archive (O-04).

A multi-page document photographed page by page arrives as several sidecars, each
carrying the page label the document prints ("第2页，共3页", "共1页/第1页", …). This
script groups those sidecars into documents and reports which printed pages are
absent (a red `missing_pages` gap for missing_items.json) and which were received
more than once (duplicate prints — informational, never a gap).

Deterministic and read-only. No medical judgement: it only compares printed page
numbers. Grouping key = date + document-type folder + institution slug + page total:
  * date            — the sidecar filename's `YYYY-MM-DD_` prefix ("undated" otherwise);
  * folder          — the bucket-relative directory (e.g. 03_病程与叙事文书/门诊病历);
  * institution     — `institution_slug()` of the filename (the segment after the
                      document type, with trailing `_s001` / `_p2` / `_v2` handles removed);
  * page total      — the "共 y 页" number, so a 2-page and a 3-page document from the
                      same visit never merge.
Two complete sets of the same document (e.g. 1/2+2/2 printed twice) give pages
{1,2} with each page counted twice: no gap, duplicates reported. UNEVEN copies (page 1
received twice, page 2 once) are not assumed to be reprints: the second copy may be a
different document of the same key that lacks its page 2, so every page with fewer copies
than the most-copied page is reported as a missing_pages gap whose reason says it may also
be a repeated photo (`duplicates[].uneven: true`). One sidecar that
covers several printed pages carries every page's label, `；`-separated
("第1页，共3页；第2页，共3页；第3页，共3页"); each page is registered in its group
(segments with different totals go to their own groups), and segments that do not
parse are listed under partially_labeled.

Page-label sources, in priority order:
  1. the sidecar header `PAGE_LABEL:` line (current contract);
  2. source_inventory.json files[].page_label for that sidecar_path;
  3. LEGACY: a body line `page_label: …` / `- page_label: …` (the ad-hoc "文档候选"
     block earlier Phase-1 workers wrote). Reported with label_source=legacy_body_line.

Label grammars parsed (full-width/half-width, 页 or 頁, optional spaces/punctuation/brackets):
  第x页，共y页 · 第x页 共y页 · 第x页/共y页 · 第x页(共y页) · 第x页【共y页】 · 共y页，第x页 ·
  共y页/第x页 · 第x/y页 · x/y页 · 页码：x/y · Page x of y · P x/y · x/y (the whole label, y ≤ 999).
  Chinese numerals 一…九十九 are accepted. Several labels in one PAGE_LABEL without `；`
  ("第1页 共3页 第2页 共3页") register every page.
Anything else ("单页", "未见页码", "无页码") is recorded as unlabeled, never guessed.
The institution slug drops a trailing handle segment: s001 / f002 / p3 / v2 / pg1 / in-003 /
s004-1, and the row's own source_id / file_id from source_inventory.json (e.g. prior-20290601).

CLI:
    page_completeness.py <patient_dir> [--inventory PATH] [--json]
Exit: 0 always for a readable archive (it is a reporter; the validator decides
whether an unrecorded gap is an ERROR); 2 = bad invocation.

Importable: parse_page_label(text) -> (page_no, page_total) | None,
parse_page_labels(text) -> ([(page_no, page_total), …], [unparsed segments]),
body_page_label(line) -> [(page_no, page_total), …] (explicit label shapes only, for the
validator's "printed label not transcribed into PAGE_LABEL" check),
institution_slug(filename, handles=()) -> str, analyze(patient_dir, inventory=None) -> dict.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

_SIDECAR_DIR_RE = re.compile(r"^\d{2}_")
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
_HANDLE_SUFFIX_RE = re.compile(r"^(?:s|f|p|v|pg|page|in-?)\d+(?:-\d+)?$", re.IGNORECASE)
_HEADER_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*):(?:\s|$)")
_LEGACY_LABEL_RE = re.compile(r"^\s*(?:[-*]\s*)?page_label\s*[:：]\s*(.+?)\s*$")

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_NUM = r"([0-9]+|[一二两三四五六七八九十〇零]+)"
_YE = r"[页頁]"
_SEP = r"[\s,，、;；/|·.。()（）【】\[\]]*"
# (pattern, order, body_ok): body_ok marks the explicit shapes that also count when found in a
# sidecar BODY line (body_page_label); `P x/y` is too generic for free text.
_LABEL_PATTERNS = [
    # 第x页，共y页 / 第x页 共y页 / 第x页/共y页 / 第x页(共y页) / 第x页【共y页】
    (re.compile(r"第\s*" + _NUM + r"\s*" + _YE + _SEP + r"共\s*" + _NUM + r"\s*" + _YE), "xy", True),
    # 共y页，第x页 / 共y页/第x页
    (re.compile(r"共\s*" + _NUM + r"\s*" + _YE + _SEP + r"第\s*" + _NUM + r"\s*" + _YE), "yx", True),
    # 第x/y页
    (re.compile(r"第\s*" + _NUM + r"\s*/\s*" + _NUM + r"\s*" + _YE), "xy", True),
    # 页码：x/y
    (re.compile(r"页码\s*[:：]?\s*([0-9]+)\s*/\s*([0-9]+)(?![0-9])"), "xy", True),
    # x/y页
    (re.compile(r"(?<![0-9/])([0-9]+)\s*/\s*([0-9]+)\s*" + _YE), "xy", True),
    # Page x of y
    (re.compile(r"\bpage\s*([0-9]+)\s*(?:of|/)\s*([0-9]+)\b", re.IGNORECASE), "xy", True),
    # P x/y
    (re.compile(r"(?<![A-Za-z])[Pp]\.?\s*([0-9]+)\s*/\s*([0-9]+)(?![0-9])"), "xy", False),
]
_BARE_FRACTION_RE = re.compile(r"^\s*([0-9]+)\s*/\s*([0-9]+)\s*$")
_BARE_FRACTION_MAX_TOTAL = 999


def _cn_to_int(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    if not tok:
        return None
    if tok == "十":
        return 10
    if "十" in tok:
        head, _, tail = tok.partition("十")
        tens = _CN_DIGITS.get(head, None) if head else 1
        ones = _CN_DIGITS.get(tail, None) if tail else 0
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(tok) == 1:
        return _CN_DIGITS.get(tok)
    return None


def _label_matches(norm: str, body_only: bool = False) -> list[tuple[int, int, int, int]]:
    """Non-overlapping label matches in `norm`: [(start, end, page_no, page_total)], by position."""
    found: list[tuple[int, int, int, int]] = []
    for pat, order, body_ok in _LABEL_PATTERNS:
        if body_only and not body_ok:
            continue
        for m in pat.finditer(norm):
            a, b = _cn_to_int(m.group(1)), _cn_to_int(m.group(2))
            if a is None or b is None:
                continue
            x, y = (a, b) if order == "xy" else (b, a)
            found.append((m.start(), m.end(), x, y))
    found.sort(key=lambda f: (f[0], -(f[1] - f[0])))
    out: list[tuple[int, int, int, int]] = []
    for f in found:
        if out and f[0] < out[-1][1]:
            continue  # overlaps an earlier (or longer) match: 「共3页 第2页」 inside 「第1页 共3页 第2页 共3页」
        out.append(f)
    return out


def parse_page_label(text: str | None) -> tuple[int, int] | None:
    """Return (page_no, page_total) for a printed page label, or None when unparseable."""
    if not isinstance(text, str) or not text.strip():
        return None
    norm = unicodedata.normalize("NFKC", text)
    hits = _label_matches(norm)
    if hits:
        return hits[0][2], hits[0][3]
    m = _BARE_FRACTION_RE.match(norm)
    if m and int(m.group(2)) <= _BARE_FRACTION_MAX_TOTAL:
        return int(m.group(1)), int(m.group(2))
    return None


def body_page_label(line: str | None) -> list[tuple[int, int]]:
    """Explicit printed page labels (第x页共y页 / Page x of y / x/y页 / 页码 x/y …) on one body line;
    [] when none. A bare fraction or `P x/y` never counts here (dates, ratios, markers)."""
    if not isinstance(line, str) or not line.strip():
        return []
    return [(x, y) for _, _, x, y in _label_matches(unicodedata.normalize("NFKC", line), body_only=True)
            if 1 <= x <= y]


def parse_page_labels(text: str | None) -> tuple[list[tuple[int, int]], list[str]]:
    """All printed page labels of one sidecar: ([(page_no, page_total), …], [unparsed segments]).

    A sidecar covering several printed pages lists each page's label verbatim, separated
    by `；`/`;` (organizer-prompt-phase1-ocr.md §3 PAGE_LABEL), e.g.
    "第1页，共3页；第2页，共3页；第3页，共3页". Each segment is parsed on its own, so a
    complete multi-page PDF registers every page. When the text is not a `；`-list whose
    segments parse, the whole text is parsed as a single label (parse_page_label)."""
    if not isinstance(text, str) or not text.strip():
        return [], []
    norm = unicodedata.normalize("NFKC", text)
    segments = [seg.strip() for seg in re.split(r"[;；]", norm) if seg.strip()]
    if len(segments) > 1:
        parsed = [(seg, parse_page_label(seg)) for seg in segments]
        pages = [p for _, p in parsed if p is not None]
        if pages:
            return pages, [seg for seg, p in parsed if p is None]
    hits = _label_matches(norm)
    if len(hits) > 1:
        # several labels without `；` (「第1页 共3页 第2页 共3页」): every page registers — reading only
        # the first would report the others as missing
        return [(x, y) for _, _, x, y in hits], []
    single = parse_page_label(norm)
    return ([single], []) if single else ([], [norm.strip()])


def institution_slug(filename: str, handles=()) -> str:
    """Institution segment of a `YYYY-MM-DD_<doctype>_<institution>[_s001].md` name.

    A trailing handle segment is dropped: the generic shapes (_HANDLE_SUFFIX_RE: s001, f002, p3,
    v2, pg1, in-003, s004-1 — content units of one original) and any of `handles` (the row's own
    source_id / file_id from source_inventory.json, with an optional `-k`), so one document's
    pages never split into groups that report each other as missing.
    Returns "unknown" when the filename carries no institution segment."""
    stem = Path(filename).stem
    parts = stem.split("_")
    if parts and _DATE_PREFIX_RE.match(parts[0] + "_"):
        parts = parts[1:]
    # drop the document-type segment
    parts = parts[1:] if parts else parts
    own = {h for h in handles if isinstance(h, str) and h}

    def is_handle(seg: str) -> bool:
        if _HANDLE_SUFFIX_RE.match(seg):
            return True
        return any(seg == h or re.fullmatch(re.escape(h) + r"-\d+", seg) for h in own)

    while parts and is_handle(parts[-1]):
        parts = parts[:-1]
    slug = "_".join(p for p in parts if p)
    return slug or "unknown"


def _header_page_label(text: str) -> str | None:
    lines = text.splitlines()
    for line in lines:
        if not line.strip():
            break
        m = _HEADER_LINE_RE.match(line)
        if not m:
            break
        if m.group(1) == "PAGE_LABEL":
            val = line[len("PAGE_LABEL") + 1:].strip()
            return None if val.lower() in ("", "null", "none", "无", "n/a") else val
    return None


def _legacy_body_label(text: str) -> str | None:
    for line in text.splitlines():
        m = _LEGACY_LABEL_RE.match(line)
        if m:
            return m.group(1)
    return None


def _inventory_rows(patient_dir: Path, inventory: Path | None) -> dict[str, dict]:
    inv_path = inventory or (patient_dir / "source_inventory.json")
    if not inv_path.is_file():
        return {}
    try:
        doc = json.loads(inv_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {row["sidecar_path"]: row for row in (doc.get("files", []) if isinstance(doc, dict) else [])
            if isinstance(row, dict) and isinstance(row.get("sidecar_path"), str)}


def _load_inventory_labels(patient_dir: Path, inventory: Path | None) -> dict[str, str]:
    return {rel: row["page_label"] for rel, row in _inventory_rows(patient_dir, inventory).items()
            if isinstance(row.get("page_label"), str) and row["page_label"].strip()}


def collect_sidecars(patient_dir: Path) -> list[Path]:
    out: list[Path] = []
    for top in sorted(patient_dir.iterdir()):
        if not top.is_dir() or not _SIDECAR_DIR_RE.match(top.name) or top.name.startswith("99_"):
            continue
        for p in sorted(top.rglob("*.md")):
            if "conversation_notes" in p.parts:
                continue
            out.append(p)
    return out


def analyze(patient_dir: Path | str, inventory: Path | str | None = None) -> dict:
    patient_dir = Path(patient_dir)
    inv_rows = _inventory_rows(patient_dir, Path(inventory) if inventory else None)
    inv_labels = _load_inventory_labels(patient_dir, Path(inventory) if inventory else None)
    groups: dict[str, dict] = {}
    unlabeled: list[dict] = []
    invalid: list[dict] = []
    partial: list[dict] = []
    for sc in collect_sidecars(patient_dir):
        rel = sc.relative_to(patient_dir).as_posix()
        try:
            text = sc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        label, source = _header_page_label(text), "header"
        if label is None and rel in inv_labels:
            label, source = inv_labels[rel], "inventory"
        if label is None:
            legacy = _legacy_body_label(text)
            if legacy is not None:
                label, source = legacy, "legacy_body_line"
        pages, unparsed = parse_page_labels(label)
        if not pages:
            unlabeled.append({"sidecar": rel, "page_label": label, "label_source": source if label else None})
            continue
        if unparsed:
            partial.append({"sidecar": rel, "page_label": label, "unparsed_segments": unparsed})
        m = _DATE_PREFIX_RE.match(sc.name)
        date = m.group(1) if m else "undated"
        folder = sc.parent.relative_to(patient_dir).as_posix()
        row = inv_rows.get(rel) or {}
        inst = institution_slug(sc.name, [row.get("source_id"), row.get("file_id")])
        for page_no, page_total in pages:
            if page_total < 1 or page_no < 1 or page_no > page_total:
                invalid.append({"sidecar": rel, "page_label": label, "page_no": page_no, "page_total": page_total})
                continue
            key = f"{date}|{folder}|{inst}|{page_total}"
            g = groups.setdefault(key, {
                "group_key": key, "date": date, "folder": folder, "institution_slug": inst,
                "page_total": page_total, "pages": {}, "sidecars": [],
            })
            g["pages"].setdefault(page_no, []).append(rel)
            g["sidecars"].append({"sidecar": rel, "page_no": page_no, "page_label": label, "label_source": source})

    out_groups, gaps, duplicates = [], [], []
    for key in sorted(groups):
        g = groups[key]
        total = g["page_total"]
        copies = {n: len(refs) for n, refs in g["pages"].items()}
        most = max(copies.values())
        # every page with fewer copies than the most-copied one is short: with one copy per page this
        # is the plain missing page; with uneven copies (page 1 twice, page 2 once) the extra page-1
        # copy may be a second document of the same key lacking its page 2 — never assumed a reprint
        short = [n for n in range(1, total + 1) if copies.get(n, 0) < most]
        uneven = most > 1 and any(0 < copies.get(n, 0) < most for n in range(1, total + 1))
        present = sorted(n for n in g["pages"] if copies[n] == most) if uneven else sorted(g["pages"])
        missing = [n for n in range(1, total + 1) if n not in g["pages"]]
        dups = {str(n): refs for n, refs in sorted(g["pages"].items()) if len(refs) > 1}
        entry = {
            "group_key": key, "date": g["date"], "folder": g["folder"],
            "institution_slug": g["institution_slug"], "page_total": total,
            "pages_present": sorted(g["pages"]), "pages_missing": missing,
            "duplicate_pages": sorted(int(k) for k in dups), "sidecars": g["sidecars"],
        }
        out_groups.append(entry)
        if short:
            pages = "、".join(str(n) for n in short)
            if uneven:
                reason = (f"同一组文书标注共 {total} 页，其中第 "
                          + "、".join(str(n) for n in present) + f" 页收到 {most} 份、第 {pages} 页份数更少："
                          f"可能是另一份同类文书缺第 {pages} 页，也可能是同一页重复拍摄；请核对，补齐后可完整转录。")
            else:
                reason = f"同一份文书标注共 {total} 页，档案中缺第 {pages} 页；补齐后可完整转录该次记录。"
            gaps.append({
                "gap_type": "missing_pages", "severity": "red", "group_key": key,
                "pages_present": present, "pages_missing": short, "page_total": total,
                "document_category": f"{g['folder'].split('/')[-1]}（{g['date']}，共 {total} 页）",
                "reason_for_artifact": reason,
            })
        if dups:
            duplicates.append({"group_key": key, "duplicate_pages": sorted(int(k) for k in dups),
                               "copies": {k: len(v) for k, v in dups.items()}, "uneven": uneven})
    return {
        "tool": "page_completeness",
        "version": "1",
        "groups": out_groups,
        "gaps": gaps,
        "duplicates": duplicates,
        "unlabeled": unlabeled,
        "invalid": invalid,
        "partially_labeled": partial,
        "counts": {
            "sidecars_labeled": sum(len(g["sidecars"]) for g in out_groups),
            "groups": len(out_groups), "gaps": len(gaps), "duplicates": len(duplicates),
            "unlabeled": len(unlabeled), "invalid": len(invalid),
            "partially_labeled": len(partial),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report missing / duplicate printed pages per document group.")
    ap.add_argument("patient_dir")
    ap.add_argument("--inventory", default=None, help="source_inventory.json path (default <patient_dir>/source_inventory.json)")
    ap.add_argument("--json", action="store_true", help="print the full JSON report (default: summary + JSON)")
    args = ap.parse_args(argv)
    pdir = Path(args.patient_dir)
    if not pdir.is_dir():
        print(f"ERROR: {pdir} is not a directory", file=sys.stderr)
        return 2
    report = analyze(pdir, args.inventory)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.json:
        c = report["counts"]
        print(f"PAGE_COMPLETENESS: groups={c['groups']} gaps={c['gaps']} duplicates={c['duplicates']} "
              f"unlabeled={c['unlabeled']} invalid={c['invalid']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
