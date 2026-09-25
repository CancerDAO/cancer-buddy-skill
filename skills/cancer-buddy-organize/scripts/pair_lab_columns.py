#!/usr/bin/env python3
"""pair_lab_columns.py — mechanical column pairing for a lab table (O-03, organizer-prompt-phase1-ocr.md §7).

Two inputs, both deterministic — the model never pairs a number to an analyte itself:

  --tsv FILE   tesseract TSV (the default OCR channel prints every word with its box). Words are
               clustered into physical rows by their vertical centre and assigned to the column
               whose header (检验项目 / 结果 / 单位 / 参考范围 / 提示 …) is horizontally nearest; each
               row's result is its `value` (pairing_method = bbox — a formal value, because the row
               and the column come from coordinates, not from the order of a linear text).
  --text FILE  linear OCR text (no coordinates): the engine emits the table column by column, so
               nothing binds a number to its analyte. The one rule that is safe to apply
               mechanically, per column:
                 * items == results → results are paired to items BY POSITION and emitted as
                   `candidate_value` (pairing_method = linear_position). A candidate is not a
                   confirmed value: labs.json keeps `value: null`, and candidates never feed
                   trends, charts or the case summary.
                 * the unit / reference-range / flag columns are counted SEPARATELY; a column is
                   paired only when its own count equals the item count, otherwise it is null for
                   every item and its count + raw strings are recorded.
                 * items != results → every pairing is refused (pairing_method = none).
                 * any value-zone token that is neither a result, a unit, a range nor a flag
                   (refused_reason = unclassified_value_zone_tokens): it may be a result the
                   classifier cannot read, and letting it drop would let another token refill the
                   count and shift every candidate by one.
                 * exactly ONE item line and ONE result, nothing unclassified → pairing_method =
                   single_value: the number is the item's `value` (nothing to mis-align). An item
                   merged from several lines is not "one item" (血红蛋白 + 血小板计数(PLT) would be).
                 * a `<x` / `>x` token is AMBIGUOUS (a below/above-limit result or a one-sided
                   reference range); it counts as a result only when the range column is already
                   complete (ranges == items), otherwise the table is refused
                   (refused_reason = ambiguous_inequality_token).
  --columns FILE  JSON {"items": [...], "values": [...], "units": [...], "ranges": [...],
               "flags": [...]} when columns were split upstream (linear_position rules).

Token classification (structural — no analyte or clinical lexicon):
  number      `150.20`, `402.6小`, `118.2个` (a trailing 小/个 is an OCR rendering of an arrow glyph:
              recorded as an artifact note, NEVER promoted to report_flag), `11.20↑`, `98↓`, `56 H`
              (a printed flag attached to the result: kept as the pair's `flag_glyph` and in the
              note — never promoted to report_flag unless the flag COLUMN itself pairs)
  titer       `1:320`
  qualitative 阴性 阳性 弱阳性 可疑 ± + ++ 1+ … 4+ negative positive (a result — except after the
              reference-range header of a linear text, where it is that column's reference value)
  ambiguous   `<0.50`, `>1000`, `<1:100` — see above
  range       `0--6.9`, `0-5`, `3.5~5.5`, `≥3`, `<=30`
  unit        a token with a `/` (U/ml, 10^9/L, 个/HP, 次/分) or a standalone unit (%, fL, 秒 …)
  flag        a standalone ↑ ↓ H L 高 低 (printed flag column)
  name        text inside the item zone; in the "（CODE）" form an item continues only while it
              has an unclosed bracket or the next line starts one / is `<digits>（` (so 血红蛋白 then
              血小板计数(PLT) are TWO items). Lines with `：`/`:`/`，` are report metadata and ignored
              (a bare titer `1:320` is not).

Output (stdout): JSON {status: paired|refused, refused_reason, pairing_method (linear_position |
single_value | bbox | none), pairing_confidence (high|medium|low|null), counts {items, item_lines,
items_merged, results (= values), units, ranges, flags, ambiguous, unclassified, …},
columns_paired, column_decisions {value, unit, range, flag: paired | null_count_mismatch |
refused_all | absent}, column_raw, pairs[], notes[]}. Each pair carries the labs.json v2.1 fields
(raw_value, candidate_value, value, unit, reference_range, pairing_method, pairing_confidence,
pairing_note) plus flag_glyph. The sidecar `## 列配对` block records this output (phase1 §7) and
validate_structured_outputs.py re-runs this script on the recorded input and binds labs.json to it.
Exit: 0 = paired; 3 = refused; 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

ITEM_HEADERS = ("检验项目", "项目", "项目名称", "检测项目", "检验名称")
RESULT_HEADERS = ("结果", "检验结果")
UNIT_HEADERS = ("单位",)
RANGE_HEADERS = ("参考范围", "参考值", "参考区间")
FLAG_HEADERS = ("提示", "标志")
COLUMN_HEADERS = RESULT_HEADERS + UNIT_HEADERS + RANGE_HEADERS + FLAG_HEADERS
# OCR renderings of ↑/↓ arrows seen on linear photo OCR (e.g. `402.6小`, `118.2个`).
ARTIFACT_GLYPHS = ("小", "个")
FLAG_TOKENS = ("↑", "↓", "↑↑", "↓↓", "H", "L", "HH", "LL", "高", "低")
STANDALONE_UNITS = ("%", "‰", "fL", "fl", "pg", "g", "mg", "U", "IU", "s", "sec", "mmHg", "kPa", "倍",
                    "秒", "分", "分钟")
QUALITATIVE_RE = re.compile(r"^(?:阴性|阳性|弱阳性|强阳性|可疑|±|\+{1,4}|[1-4]\+|neg(?:ative)?|pos(?:itive)?|"
                            r"non-?reactive|reactive)(?:\s*[（(][^）)]*[）)])?$", re.IGNORECASE)
MAX_ITEM_LINES = 2000  # refuse a larger item zone (the merge is linear, but a table is never this long)

_FLAG_SUFFIX = r"(↑↑|↓↓|↑|↓|HH|LL|H|L|高|低|\*)"
_NUM_RE = re.compile(r"^([<>]\s*)?([+-]?\d+(?:\.\d+)?)\s*((?:" + "|".join(ARTIFACT_GLYPHS) + r")*)\s*"
                     + _FLAG_SUFFIX + r"?$")
_TITER_RE = re.compile(r"^([<>≤≥]\s*)?(\d+\s*:\s*\d+)$")
_RANGE_RE = re.compile(
    r"^(?:(?:≥|≤|>=|<=)\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:-{1,2}|–|—|~|～|至)\s*\d+(?:\.\d+)?)$"
)
_UNIT_RE = re.compile(r"^(?:[×x]?10\^?\d+|[A-Za-zμµ个次]+)/(?:[A-Za-zμµ0-9.^]+|分钟|分|秒|天|日|周)$")
_META_RE = re.compile(r"[：:，]")
_CODE_RE = re.compile(r"[（(]([^（）()]+)[）)]\s*$")
_CLOSERS = ("）", ")")
_OPENERS = ("（", "(")
_CONT_START_RE = re.compile(r"^(?:[（(]|\d+\s*[（(])")


def _norm(line: str) -> str:
    # NFKC folds full-width digits/letters but keeps CJK parentheses as ASCII; keep the
    # original for raw strings and use the folded form only for classification.
    return unicodedata.normalize("NFKC", line).strip()


def _is_meta(t: str) -> bool:
    return bool(_META_RE.search(t)) and not _TITER_RE.match(t)


def classify(token: str) -> str:
    t = _norm(token)
    if not t:
        return "blank"
    if t in ARTIFACT_GLYPHS:
        return "artifact"
    if t in FLAG_TOKENS:
        return "flag"
    if t in COLUMN_HEADERS or t in ITEM_HEADERS:
        return "header"
    m = _NUM_RE.match(t)
    if m:
        return "ambiguous" if m.group(1) else "number"
    m = _TITER_RE.match(t)
    if m:
        return "ambiguous" if m.group(1) else "titer"
    if _RANGE_RE.match(t):
        return "range"
    if QUALITATIVE_RE.match(t):
        return "qualitative"
    if _UNIT_RE.match(t) or t in STANDALONE_UNITS:
        return "unit"
    return "other"


def _split_value(token: str) -> tuple[str, list[str], str | None]:
    """'118.2个' -> ('118.2', ['个'], None); '11.20↑' -> ('11.20', [], '↑'); '<0.50' -> ('<0.50', [], None)."""
    t = _norm(token)
    m = _NUM_RE.match(t)
    if not m:
        return re.sub(r"\s+", "", t), [], None
    value = re.sub(r"\s+", "", (m.group(1) or "") + m.group(2))
    return value, list(m.group(3) or ""), m.group(4)


def _merge_item_lines(lines: list[str]) -> list[str]:
    """Item names from the item zone. In the "（CODE）" form a name wrapped over several lines is
    joined — but only while the text so far has an unclosed bracket, or the NEXT line starts a
    bracket / is `<digits>（…` (人附睾蛋白 + 4（HE4）); any other line starts a new item. Linear in
    the number of lines (the old `buf +=` + NFKC of the whole buffer was quadratic)."""
    if not lines:
        return []
    paren_mode = any(_norm(l).endswith(_CLOSERS) for l in lines)
    if not paren_mode:
        return list(lines)
    items: list[str] = []
    parts: list[str] = []
    depth = 0
    for i, line in enumerate(lines):
        s = line.strip()
        parts.append(s)
        n = _norm(s)
        depth += sum(n.count(o) for o in _OPENERS) - sum(n.count(c) for c in _CLOSERS)
        nxt = _norm(lines[i + 1]) if i + 1 < len(lines) else ""
        if depth > 0 or (nxt and _CONT_START_RE.match(nxt) and not n.endswith(_CLOSERS)):
            continue
        items.append("".join(parts))
        parts, depth = [], 0
    if parts:
        items.append("".join(parts))
    return items


def _item_code(item: str) -> str | None:
    m = _CODE_RE.search(_norm(item))
    return m.group(1).strip() if m else None


def _value_entry(raw: str, kind: str) -> dict:
    value, glyphs, flag = _split_value(raw) if kind in ("number", "ambiguous") else (re.sub(r"\s+", "", _norm(raw)), [], None)
    return {"raw": raw, "value": value, "artifact_glyphs": glyphs, "flag_glyph": flag,
            "ambiguous": kind == "ambiguous", "kind": kind}


def columns_from_text(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    col_idx = [i for i, l in enumerate(lines) if _norm(l) in COLUMN_HEADERS]
    item_idx = [i for i, l in enumerate(lines) if _norm(l) in ITEM_HEADERS]
    start = None
    for i in reversed(item_idx):
        if any(c > i for c in col_idx):
            start = i
            break
    if start is None:
        return {"error": "no_item_header"}
    first_col = min(c for c in col_idx if c > start)
    # Everything between the item header and the first column header is item text.
    # Nothing is moved out of this zone: a stray number here makes the item count
    # disagree with the value count, which refuses the pairing (the safe failure).
    item_lines = [l for l in lines[start + 1:first_col] if not _is_meta(_norm(l)) and classify(l) != "header"]
    if len(item_lines) > MAX_ITEM_LINES:
        return {"error": "item_zone_too_long", "item_lines": len(item_lines)}
    items = _merge_item_lines(item_lines)
    values: list[dict] = []
    units: list[str] = []
    ranges: list[str] = []
    flags: list[str] = []
    other: list[str] = []
    orphan_glyphs: list[str] = []
    zone = None
    for l in lines[first_col:]:
        n = _norm(l)
        if _is_meta(n):
            continue
        kind = classify(l)
        if kind == "header":
            zone = "range" if n in RANGE_HEADERS else ("result" if n in RESULT_HEADERS else "other")
            continue
        if kind == "qualitative" and zone == "range":
            ranges.append(l)  # 阴性 under 参考范围 is that item's reference value
        elif kind in ("number", "ambiguous", "titer", "qualitative"):
            values.append(_value_entry(l, kind))
        elif kind == "artifact":
            if values:
                values[-1]["artifact_glyphs"].append(n)
                values[-1].setdefault("standalone_glyph_lines", []).append(l)
            else:
                orphan_glyphs.append(l)
        elif kind == "range":
            ranges.append(l)
        elif kind == "unit":
            units.append(l)
        elif kind == "flag":
            flags.append(l)
        else:
            other.append(l)
    return {"items": items, "item_lines": len(item_lines), "values": values, "units": units, "ranges": ranges,
            "flags": flags, "unclassified": other, "orphan_glyphs": orphan_glyphs}


def columns_from_json(doc: dict) -> dict:
    # Pre-split columns: the upstream split already decided which column a `<x` token
    # belongs to, so a `<x` in values[] is a result (never ambiguous).
    values = []
    for v in doc.get("values") or []:
        kind = classify(str(v))
        e = _value_entry(str(v), kind if kind in ("number", "titer", "qualitative", "ambiguous") else "other")
        e["ambiguous"] = False
        values.append(e)
    items = [str(x) for x in doc.get("items") or []]
    return {"items": items, "item_lines": len(items), "values": values,
            "units": [str(x) for x in doc.get("units") or []],
            "ranges": [str(x) for x in doc.get("ranges") or []],
            "flags": [str(x) for x in doc.get("flags") or []],
            "unclassified": [v["raw"] for v in values if v["kind"] == "other"], "orphan_glyphs": []}


_REFUSED_ALL = {"value": "refused_all", "unit": "refused_all", "range": "refused_all", "flag": "refused_all"}


def _refused(reason: str, note: str, counts: dict, column_raw: dict, items: list[str]) -> dict:
    return {"tool": "pair_lab_columns", "version": "2", "status": "refused", "refused_reason": reason,
            "pairing_method": "none", "pairing_confidence": None,
            "counts": counts, "columns_paired": {"value": False, "unit": False, "range": False, "flag": False},
            "column_decisions": dict(_REFUSED_ALL), "column_raw": column_raw,
            "pairs": [{"position": i + 1, "item": it, "item_code": _item_code(it), "raw_value": None,
                       "candidate_value": None, "value": None, "unit": None, "reference_range": None,
                       "flag": None, "flag_glyph": None, "artifact_glyphs": [], "pairing_method": "none",
                       "pairing_confidence": None, "pairing_note": note} for i, it in enumerate(items)],
            "notes": [note]}


def pair(cols: dict) -> dict:
    if cols.get("error"):
        note = ("未找到检验项目表头，无法确定项目列，拒绝配对。" if cols["error"] == "no_item_header"
                else f"项目区有 {cols.get('item_lines')} 行（上限 {MAX_ITEM_LINES}），不是一张检验表，拒绝配对。")
        rep = _refused(cols["error"], note, {}, {}, [])
        return rep
    items, values = cols["items"], cols["values"]
    n = len(items)
    counts = {"items": n, "item_lines": cols.get("item_lines", n),
              "items_merged": cols.get("item_lines", n) - n,
              "values": len(values), "results": len(values), "units": len(cols["units"]),
              "ranges": len(cols["ranges"]), "flags": len(cols["flags"]),
              "ambiguous": sum(1 for v in values if v.get("ambiguous")),
              "artifact_glyphs": sum(len(v["artifact_glyphs"]) for v in values) + len(cols["orphan_glyphs"]),
              "flag_glyphs": sum(1 for v in values if v.get("flag_glyph")),
              "unclassified": len(cols["unclassified"])}
    column_raw = {"items": items, "values": [v["raw"] for v in values], "units": cols["units"],
                  "ranges": cols["ranges"], "flags": cols["flags"],
                  "unclassified": cols["unclassified"], "orphan_glyphs": cols["orphan_glyphs"]}
    count_text = (f"项目 {n} / 数值 {counts['values']} / 单位 {counts['units']} / "
                  f"参考范围 {counts['ranges']}" + (f" / 旗标 {counts['flags']}" if counts["flags"] else ""))
    ambiguous_refusal = counts["ambiguous"] > 0 and counts["ranges"] < n
    if n == 0:
        return _refused("no_items", f"{count_text}：项目区为空，拒绝配对。", counts, column_raw, items)
    if cols["unclassified"]:
        odd = "、".join(cols["unclassified"][:6])
        return _refused("unclassified_value_zone_tokens",
                        f"{count_text}：数值区有无法归类的内容「{odd}」，可能是读不出的结果，按位置配对会错位，"
                        "拒绝配对（任何数值都不绑定到项目）。", counts, column_raw, items)
    if ambiguous_refusal:
        amb = "、".join(v["raw"] for v in values if v.get("ambiguous"))
        return _refused("ambiguous_inequality_token",
                        f"{count_text}：数值区含「{amb}」这类带不等号的数，可能是结果也可能是参考范围，"
                        "而参考范围列不全，无法判定其归属，拒绝配对（任何数值都不绑定到项目）。", counts, column_raw, items)
    if n != len(values):
        return _refused("item_value_count_mismatch",
                        f"{count_text}：项目数与数值数不一致，拒绝配对（任何数值都不绑定到项目）。",
                        counts, column_raw, items)
    unit_ok = counts["units"] == n
    range_ok = counts["ranges"] == n
    flag_ok = counts["flags"] == n
    unpaired = []
    if not unit_ok:
        unpaired.append(f"单位列 {counts['units']} 个")
    if not range_ok:
        unpaired.append(f"参考范围列 {counts['ranges']} 个")
    if counts["flags"] and not flag_ok:
        unpaired.append(f"旗标列 {counts['flags']} 个")
    clean = (unit_ok and range_ok and (flag_ok or counts["flags"] == 0) and not cols["orphan_glyphs"])
    # one item LINE + one result: nothing can be mis-aligned, so the result is the item's value.
    # An item merged from several lines, or an orphan glyph, keeps it a (low) candidate.
    single = n == 1 and counts["item_lines"] == 1 and not cols["orphan_glyphs"]
    method = "single_value" if single else "linear_position"
    if single:
        confidence = "high" if clean else "medium"
    else:
        confidence = "medium" if clean and counts["items_merged"] == 0 else "low"
    notes: list[str] = []
    if unpaired:
        notes.append(f"{count_text}：" + "、".join(unpaired) + f"与项目数 {n} 不等，该列不配对、置空。")
    if counts["items_merged"]:
        notes.append(f"项目区 {counts['item_lines']} 行合并为 {n} 个项目（跨行项目名）。")
    pairs = []
    for i, (it, v) in enumerate(zip(items, values)):
        pn = (f"报告只有一个项目、一个结果（{count_text}），按单值配对。" if single
              else f"线性文本按位置配对的候选值（{count_text}），需对照原件核实。")
        if unpaired:
            pn += "未配对列：" + "、".join(unpaired) + "。"
        if v["artifact_glyphs"]:
            pn += ("结果串含疑似箭头识别伪影「" + "".join(v["artifact_glyphs"]) +
                   "」，未作为报告旗标写入。")
        if v.get("flag_glyph"):
            pn += f"结果串带印刷标记「{v['flag_glyph']}」（候选标记，未写入 report_flag）。"
        pairs.append({
            "position": i + 1, "item": it, "item_code": _item_code(it),
            "raw_value": v["raw"],
            "candidate_value": None if single else v["value"],
            "value": v["value"] if single else None,
            "unit": cols["units"][i] if unit_ok else None,
            "reference_range": cols["ranges"][i] if range_ok else None,
            "flag": cols["flags"][i] if flag_ok else None,
            "flag_glyph": v.get("flag_glyph"),
            "artifact_glyphs": v["artifact_glyphs"],
            "pairing_method": method, "pairing_confidence": confidence,
            "pairing_note": pn,
        })
    decision = {True: "paired", False: "null_count_mismatch"}
    return {"tool": "pair_lab_columns", "version": "2", "status": "paired", "refused_reason": None,
            "pairing_method": method, "pairing_confidence": confidence,
            "counts": counts,
            "columns_paired": {"value": True, "unit": unit_ok, "range": range_ok, "flag": flag_ok},
            "column_decisions": {"value": "paired", "unit": decision[unit_ok], "range": decision[range_ok],
                                 "flag": decision[flag_ok]},
            "column_raw": column_raw, "pairs": pairs, "notes": notes}


# --------------------------------------------------------------------------- #
# --tsv: row clustering on tesseract word boxes → pairing_method bbox
# --------------------------------------------------------------------------- #
def _tsv_words(tsv: str) -> list[dict]:
    rows = [r.split("\t") for r in tsv.splitlines() if r.strip()]
    if not rows:
        return []
    head = rows[0]
    try:
        ix = {k: head.index(k) for k in ("level", "left", "top", "width", "height", "conf", "text")}
    except ValueError:
        return []
    words = []
    for r in rows[1:]:
        if len(r) <= ix["text"]:
            continue
        try:
            level = int(r[ix["level"]])
            left, top, width, height = (int(float(r[ix[k]])) for k in ("left", "top", "width", "height"))
            conf = float(r[ix["conf"]])
        except ValueError:
            continue
        text = r[ix["text"]].strip()
        if level != 5 or not text or conf < 0 or height <= 0:
            continue
        words.append({"left": left, "right": left + width, "yc": top + height / 2, "h": height, "text": text})
    return words


def _rows(words: list[dict]) -> list[list[dict]]:
    """Physical rows: words sorted by vertical centre; a word joins the current row while its centre
    is within half the median word height of the row's mean centre."""
    if not words:
        return []
    tol = statistics.median(w["h"] for w in words) * 0.5
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["yc"], w["left"])):
        if rows and abs(w["yc"] - statistics.fmean(x["yc"] for x in rows[-1])) <= tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["left"]) for r in rows]


def _phrases(row: list[dict], gap: float) -> list[dict]:
    """Adjacent words closer than `gap` are one cell phrase (tesseract splits CJK per character)."""
    out: list[dict] = []
    for w in row:
        if out and w["left"] - out[-1]["right"] <= gap:
            prev = out[-1]
            sep = " " if re.match(r"[A-Za-z0-9]", w["text"]) and re.search(r"[A-Za-z0-9]$", prev["text"]) else ""
            prev["text"] += sep + w["text"]
            prev["right"] = w["right"]
        else:
            out.append({"left": w["left"], "right": w["right"], "text": w["text"]})
    for p in out:
        p["xc"] = (p["left"] + p["right"]) / 2
    return out


def pair_tsv(tsv: str) -> dict:
    words = _tsv_words(tsv)
    if not words:
        return _refused("no_words", "TSV 中没有可用的词框，拒绝配对。", {}, {}, [])
    gap = statistics.median(w["h"] for w in words) * 0.8
    table = [_phrases(r, gap) for r in _rows(words)]
    header_i, anchors = None, []
    for i, phrases in enumerate(table):
        roles = []
        for p in phrases:
            t = _norm(p["text"]).replace(" ", "")
            role = ("item" if t in ITEM_HEADERS else "result" if t in RESULT_HEADERS else "unit" if t in UNIT_HEADERS
                    else "range" if t in RANGE_HEADERS else "flag" if t in FLAG_HEADERS else None)
            if role:
                roles.append((role, p["xc"]))
        if any(r == "item" for r, _ in roles) and any(r == "result" for r, _ in roles):
            header_i, anchors = i, roles
            break
    if header_i is None:
        return _refused("no_item_header", "未找到同一行的检验项目与结果表头，无法按坐标定列，拒绝配对。", {}, {}, [])
    anchors = sorted(anchors, key=lambda a: a[1])
    roles_present = {r for r, _ in anchors}

    def cells(phrases):
        out: dict[str, list[str]] = {}
        for p in phrases:
            role = min(anchors, key=lambda a: abs(a[1] - p["xc"]))[0]
            out.setdefault(role, []).append(p["text"])
        return {k: " ".join(v) for k, v in out.items()}

    data: list[dict] = []
    for phrases in table[header_i + 1:]:
        c = cells(phrases)
        if not c.get("item") and not c.get("result"):
            if data:
                break
            continue
        if c.get("item") and _is_meta(_norm(c["item"])) and not c.get("result"):
            break  # footer (检验者：… 审核：…)
        data.append(c)
    # an item wrapped onto the next row: an item-only row whose next row's item starts a bracket or
    # is `<digits>（` is joined to it
    merged: list[dict] = []
    for c in data:
        if merged and not merged[-1].get("result") and c.get("item") and _CONT_START_RE.match(_norm(c["item"])):
            prev = merged.pop()
            c = dict(c, item=(prev.get("item") or "") + c["item"])
        merged.append(c)
    pairs = []
    for i, c in enumerate(merged):
        raw = c.get("result")
        kind = classify(raw) if raw else "blank"
        ok = kind in ("number", "titer", "qualitative", "ambiguous")
        value, glyphs, flag_glyph = (_split_value(raw) if kind in ("number", "ambiguous")
                                     else ((re.sub(r"\s+", "", _norm(raw)), [], None) if ok else (None, [], None)))
        item = c.get("item") or ""
        conf = None
        if ok:
            conf = "high" if item and (c.get("unit") or c.get("range")) and kind in ("number", "titer") else "medium"
        note = ("按坐标同行配对（bbox）。" if ok else
                f"该行结果列{'为空' if not raw else '内容「' + raw + '」无法作为一个结果'}，不配对。")
        if glyphs:
            note += "结果串含疑似箭头识别伪影「" + "".join(glyphs) + "」，未作为报告旗标写入。"
        if flag_glyph:
            note += f"结果串带印刷标记「{flag_glyph}」（候选标记，未写入 report_flag）。"
        pairs.append({
            "position": i + 1, "item": item, "item_code": _item_code(item) if item else None,
            "raw_value": raw, "candidate_value": None, "value": value if ok else None,
            "unit": c.get("unit"), "reference_range": c.get("range"), "flag": c.get("flag"),
            "flag_glyph": flag_glyph, "artifact_glyphs": glyphs,
            "pairing_method": "bbox" if ok else "none", "pairing_confidence": conf, "pairing_note": note,
        })
    paired = [p for p in pairs if p["pairing_method"] == "bbox"]
    counts = {"rows": len(pairs), "rows_paired": len(paired), "words": len(words),
              "items": len(pairs), "results": len(paired)}
    if not paired:
        return _refused("no_rows", "表头下没有带结果的数据行，拒绝配对。", counts, {}, [p["item"] for p in pairs])
    decisions = {"value": "paired"}
    for col in ("unit", "range", "flag"):
        decisions[col] = "paired" if col in roles_present else "absent"
    confs = {p["pairing_confidence"] for p in paired}
    return {"tool": "pair_lab_columns", "version": "2", "status": "paired", "refused_reason": None,
            "pairing_method": "bbox", "pairing_confidence": "high" if confs == {"high"} else "medium",
            "counts": counts, "columns_paired": {k: v == "paired" for k, v in decisions.items()},
            "column_decisions": decisions,
            "column_raw": {"items": [p["item"] for p in pairs], "values": [p["raw_value"] for p in pairs]},
            "pairs": pairs, "notes": [] if len(paired) == len(pairs) else
            [f"{len(pairs) - len(paired)} 行没有可用结果，未配对。"]}


def run_input(path: Path) -> dict:
    """Pair whatever `path` holds by its suffix (.tsv → bbox, .json → columns, else linear text);
    the validator calls this on the input a `## 列配对` record names."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".tsv":
        return pair_tsv(text)
    if path.suffix.lower() == ".json":
        return pair(columns_from_json(json.loads(text)))
    return pair(columns_from_text(text))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mechanical lab column pairing (bbox from TSV boxes; position candidates from linear text).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="linear OCR text file ('-' = stdin)")
    src.add_argument("--tsv", help="tesseract TSV (word boxes) of the lab table page")
    src.add_argument("--columns", help="JSON file with pre-split columns")
    ap.add_argument("--out", help="also write the JSON report here (raw/_extract/<source_id>.lab<k>.pairing.json)")
    args = ap.parse_args(argv)
    try:
        if args.text:
            text = sys.stdin.read() if args.text == "-" else Path(args.text).read_text(encoding="utf-8")
            rep = pair(columns_from_text(text))
        elif args.tsv:
            rep = pair_tsv(Path(args.tsv).read_text(encoding="utf-8"))
        else:
            rep = pair(columns_from_json(json.loads(Path(args.columns).read_text(encoding="utf-8"))))
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read input: {exc}", file=sys.stderr)
        return 2
    out = json.dumps(rep, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0 if rep["status"] == "paired" else 3


if __name__ == "__main__":
    sys.exit(main())
