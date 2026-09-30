"""Static, offline charts (inline SVG) for lab / observation series and treatment episodes.

Rules this module enforces (SPEC §3.1, §6, §7 charts):
  - only numbers the source report printed (``value``); ``candidate_value`` is never plotted;
  - each point keeps its own report's unit, reference range and flags;
  - incomparable units never share an axis: the unit of the most recent point wins, the others
    are reported as ``excluded``;
  - a method change breaks the line into segments (same axis, no connecting line);
  - "comparable points" = points that share the chosen unit, counted across method segments;
  - no trend arrows, no verdict titles; red only for points the report itself flagged critical;
    in-range is not green (purple / neutral palette).

Public API:
  series_for(patient_dir, metric) -> dict | None
  trend_candidates(patient_dir, limit=4) -> list[str]
  svg_trend(series, width=640, height=220, title=None) -> str
  verdict_words(text) -> list[str]
  render_chart_page(patient_dir, metric, out=None, title=None) -> Path
  svg_treatment_timeline(episodes, start=None, end=None, width=640) -> str
"""
import datetime as _dt
import html
import math
import re
from pathlib import Path

from .common import load_json, read_frontmatter, today

# --- palette -------------------------------------------------------------------------
INK = "#2d2640"
MUTED = "#6f6a7d"
GRID = "#e4e1ea"
LINE = "#6a4c93"
BAND = "#efe9f7"
CRITICAL = "#c0392b"          # only for points the report flagged critical
BAR = "#8e7cc3"
BAR_OPEN = "#b9aedb"
FONT = ("-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',"
        "'Noto Sans CJK SC','Source Han Sans SC',sans-serif")

TUMOR_MARKERS = ("CEA", "CA19-9", "CA125", "CA15-3", "AFP", "PSA", "NSE", "CYFRA21-1", "SCC", "PROGRP")
TUMOR_MARKER_BUCKETS = ("肿瘤标志物", "tumor_markers")

VERDICT_WORDS = ("好转", "恶化", "进展", "有效", "无效", "控制", "稳定了", "缓解", "加重", "改善", "变差", "变好",
                 "复发", "improv", "worse", "progress", "respon", "stable disease", "effective", "failing")


def verdict_words(text) -> list:
    """Verdict-like words found in ``text`` (case-insensitive). Empty list = neutral."""
    t = str(text or "").lower()
    return [w for w in VERDICT_WORDS if w.lower() in t]


# --- small parsing helpers -------------------------------------------------------------

def _parse_date(s):
    """'YYYY', 'YYYY-MM', 'YYYY-MM-DD' (or ISO datetime) -> date (first day of period) or None."""
    if not s:
        return None
    m = re.match(r"^(\d{4})(?:[-/.](\d{1,2}))?(?:[-/.](\d{1,2}))?", str(s))
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1))
    except ValueError:
        return None


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    m = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*", str(v))
    return float(m.group(1)) if m else None


def _norm_key(s) -> str:
    return re.sub(r"[\s_]+", "", str(s or "")).upper()


def _norm_unit(u) -> str:
    return re.sub(r"\s+", "", str(u or "")).replace("µ", "μ").lower()


def _fmt(v) -> str:
    if v is None:
        return ""
    if float(v).is_integer():
        return str(int(v))
    return ("%.3f" % v).rstrip("0").rstrip(".")


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _ref_path(ref):
    return str(ref or "").split("#", 1)[0]


# --- series ----------------------------------------------------------------------------

def _lab_points(patient_dir, metric):
    labs = load_json(Path(patient_dir) / "labs.json", {}) or {}
    key = _norm_key(metric)
    label, points, skipped = None, [], []
    for panel in labs.get("panels") or []:
        names = {_norm_key(panel.get("analyte")), _norm_key(panel.get("normalized_analyte"))}
        if key not in names:
            continue
        label = label or panel.get("normalized_analyte") or panel.get("analyte")
        for v in panel.get("values") or []:
            refs = v.get("source_refs") or ([v["source_ref"]] if v.get("source_ref") else [])
            p = {"date": v.get("date"), "value": _num(v.get("value")), "raw_value": v.get("raw_value"),
                 "unit": v.get("unit"), "reference_range": v.get("reference_range"),
                 "report_flag": v.get("report_flag"), "critical_flag": bool(v.get("critical_flag")),
                 "method": v.get("method"), "source_ref": refs[0] if refs else None,
                 "provenance_layer": v.get("provenance_layer")}
            if v.get("value") is None:
                # candidate_value (misaligned table read) is never a value.
                reason = "unverified_read" if v.get("candidate_value") is not None else "missing"
                skipped.append({"point": p, "reason": reason})
            elif p["value"] is None or _parse_date(p["date"]) is None:
                skipped.append({"point": p, "reason": "not_numeric" if p["value"] is None else "no_date"})
            else:
                points.append(p)
    return label, points, skipped


def _obs_points(patient_dir, metric):
    obs = load_json(Path(patient_dir) / "longitudinal_observations.json", {}) or {}
    key = _norm_key(metric)
    label, points, skipped = None, [], []
    for o in obs.get("observations") or []:
        if _norm_key(o.get("metric")) != key:
            continue
        label = label or o.get("metric")
        p = {"date": o.get("timestamp"), "value": _num(o.get("value")), "raw_value": o.get("value"),
             "unit": o.get("unit"), "reference_range": o.get("reference_range"), "report_flag": None,
             "critical_flag": False, "method": o.get("method_or_device"), "source_ref": o.get("source_ref"),
             "provenance_layer": o.get("provenance_layer")}
        if p["value"] is None or _parse_date(p["date"]) is None:
            skipped.append({"point": p, "reason": "missing" if o.get("value") is None else "not_numeric"})
        else:
            points.append(p)
    return label, points, skipped


def series_for(patient_dir, metric):
    """Series for one analyte/metric from labs.json (falls back to longitudinal_observations.json).

    Returns None when the metric is not in the archive at all. Otherwise::

      {"metric", "label", "unit",           # unit = unit of the most recent plotted point
       "points":   [...],                   # comparable points (same unit), date-sorted
       "segments": [[...], ...],            # points split where the method changes
       "excluded": [{"point", "reason"}],   # other units / null values (candidate never plotted)
       "method_changes": [{"date", "from", "to"}],
       "reference_range": str | None,       # only when every comparable point shares it
       "is_tumor_marker": bool}

    Each point: date, value, unit, reference_range, report_flag, critical_flag, method, source_ref.
    """
    label, points, skipped = _lab_points(patient_dir, metric)
    src = "labs"
    if not points and not skipped:
        label, points, skipped = _obs_points(patient_dir, metric)
        src = "observations"
    if not points and not skipped:
        return None
    points.sort(key=lambda p: _parse_date(p["date"]))
    excluded = list(skipped)
    unit = points[-1]["unit"] if points else None
    comparable = []
    for p in points:
        if _norm_unit(p["unit"]) == _norm_unit(unit):
            comparable.append(p)
        else:
            excluded.append({"point": p, "reason": "unit"})
    segments, changes = [], []
    for p in comparable:
        if segments and (p["method"] or "") != (segments[-1][-1]["method"] or ""):
            changes.append({"date": p["date"], "from": segments[-1][-1]["method"], "to": p["method"]})
            segments.append([p])
        elif segments:
            segments[-1].append(p)
        else:
            segments.append([p])
    ranges = {str(p["reference_range"] or "") for p in comparable}
    rr = ranges.pop() if len(ranges) == 1 else None
    return {"metric": metric, "label": label or metric, "unit": unit, "points": comparable,
            "segments": segments, "excluded": excluded, "method_changes": changes,
            "reference_range": rr or None, "source": src,
            "is_tumor_marker": _is_tumor_marker(label or metric, comparable)}


def _is_tumor_marker(label, points) -> bool:
    if _norm_key(label) in {_norm_key(m) for m in TUMOR_MARKERS}:
        return True
    for p in points:
        parts = _ref_path(p.get("source_ref")).split("/")
        if len(parts) > 1 and parts[1] in TUMOR_MARKER_BUCKETS:
            return True
    return False


def _all_metrics(patient_dir):
    out = []
    labs = load_json(Path(patient_dir) / "labs.json", {}) or {}
    for panel in labs.get("panels") or []:
        name = panel.get("normalized_analyte") or panel.get("analyte")
        if name and name not in out:
            out.append(name)
    obs = load_json(Path(patient_dir) / "longitudinal_observations.json", {}) or {}
    for o in obs.get("observations") or []:
        if o.get("metric") and o["metric"] not in out:
            out.append(o["metric"])
    return out


def trend_candidates(patient_dir, limit=4) -> list:
    """Metrics with >= 2 comparable points. Tumor markers first, then the rest by most recent
    point date (newest first). Ties: canonical tumor-marker order, then point count (never the main order)."""
    rows = []
    for m in _all_metrics(patient_dir):
        s = series_for(patient_dir, m)
        if not s or len(s["points"]) < 2:
            continue
        latest = _parse_date(s["points"][-1]["date"])
        tm_rank = next((i for i, t in enumerate(TUMOR_MARKERS) if _norm_key(t) == _norm_key(s["label"])), len(TUMOR_MARKERS))
        rows.append((0 if s["is_tumor_marker"] else 1, -latest.toordinal(), tm_rank, -len(s["points"]), m))
    rows.sort()
    return [r[-1] for r in rows[:limit]] if limit else [r[-1] for r in rows]


# --- SVG trend ---------------------------------------------------------------------------

def _range_bounds(rr):
    """'0-5' / '3.5-9.5' / '0～37' -> (lo, hi); anything else -> None."""
    m = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*[-–—~～至]\s*([-+]?\d+(?:\.\d+)?)\s*", str(rr or ""))
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    return (lo, hi) if hi > lo else None


def _nice_ticks(lo, hi, n=4):
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out


def default_title(series, locale="zh") -> str:
    unit = series.get("unit") or ""
    if str(locale).lower().startswith("zh"):
        t = f"{series['label']} 各次报告的数值（{unit}），按检测日期排列"
        if series.get("reference_range"):
            t += "；浅色带是报告自带的参考范围"
        return t + "。以原报告为准。"
    t = f"{series['label']} as printed on each report ({unit}), by test date"
    if series.get("reference_range"):
        t += "; the light band is the report's own reference range"
    return t + ". The original reports are authoritative."


def svg_trend(series, width=640, height=220, title=None, locale="zh") -> str:
    """Inline SVG line chart. Real time spacing on x; value labels on dots; no arrows."""
    pts = series.get("points") or []
    zh = str(locale).lower().startswith("zh")
    ml, mr, mt, mb = 52, 20, 22, 40
    pw, ph = width - ml - mr, height - mt - mb
    dates = [_parse_date(p["date"]) for p in pts]
    d0 = min(dates) if dates else _dt.date.today()
    d1 = max(dates) if dates else d0
    dspan = max((d1 - d0).days, 1)
    vals = [p["value"] for p in pts]
    band = _range_bounds(series.get("reference_range"))
    lo_v = min(vals + ([band[0]] if band else [])) if vals else 0.0
    hi_v = max(vals + ([band[1]] if band else [])) if vals else 1.0
    if hi_v == lo_v:
        hi_v, lo_v = hi_v + 1, lo_v - 1
    pad = (hi_v - lo_v) * 0.12
    lo_v, hi_v = lo_v - pad, hi_v + pad
    if min(vals or [0]) >= 0 and lo_v < 0:
        lo_v = 0.0

    def X(d):
        if len(pts) == 1:
            return ml + pw / 2
        return ml + pw * ((d - d0).days / dspan)

    def Y(v):
        return mt + ph * (1 - (v - lo_v) / (hi_v - lo_v))

    t = title or default_title(series, locale)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
           f'style="max-width:{width}px;height:auto" role="img" aria-label="{_esc(t)}" '
           f'font-family="{_esc(FONT)}" font-size="12">',
           f"<title>{_esc(t)}</title>"]
    if band:
        y_hi, y_lo = Y(min(band[1], hi_v)), Y(max(band[0], lo_v))
        out.append(f'<rect x="{ml}" y="{y_hi:.1f}" width="{pw}" height="{max(y_lo - y_hi, 0):.1f}" fill="{BAND}"/>')
        out.append(f'<text x="{ml + pw - 4}" y="{y_hi + 13:.1f}" text-anchor="end" fill="{MUTED}">'
                   f'{_esc(("参考范围 " if zh else "ref. ") + str(series.get("reference_range")))}</text>')
    for tv in _nice_ticks(lo_v, hi_v):
        y = Y(tv)
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{ml - 6}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{_esc(_fmt(tv))}</text>')
    out.append(f'<text x="{ml}" y="{mt - 8}" fill="{MUTED}">{_esc(series.get("unit") or "")}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}" stroke="{MUTED}" stroke-width="1"/>')
    # method-change markers (the line itself is broken there)
    for ch in series.get("method_changes") or []:
        x = X(_parse_date(ch["date"])) - 6
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mt}" y2="{mt + ph}" stroke="{MUTED}" '
                   f'stroke-dasharray="3 3" stroke-width="1"/>')
        out.append(f'<text x="{x - 3:.1f}" y="{mt + 12}" text-anchor="end" fill="{MUTED}">'
                   f'{"检测方法变更" if zh else "method changed"}</text>')
    for seg in series.get("segments") or [pts]:
        if len(seg) >= 2:
            coords = " ".join(f"{X(_parse_date(p['date'])):.1f},{Y(p['value']):.1f}" for p in seg)
            out.append(f'<polyline points="{coords}" fill="none" stroke="{LINE}" stroke-width="2"/>')
    # date labels: always the latest; others only where they do not collide (greedy from the right)
    label_idx, last_x = set(), float("inf")
    for i in range(len(pts) - 1, -1, -1):
        x = X(dates[i])
        if last_x - x >= 74:
            label_idx.add(i)
            last_x = x
    for i, p in enumerate(pts):
        x, y = X(dates[i]), Y(p["value"])
        color = CRITICAL if p.get("critical_flag") else LINE
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="#fff" stroke-width="1.5"/>')
        val = _fmt(p["value"]) + (" " + str(p["report_flag"]) if p.get("report_flag") else "")
        anchor = "middle"
        if x - ml < 30:
            anchor = "start"
        elif ml + pw - x < 30:
            anchor = "end"
        dx = {"start": -4, "end": 4, "middle": 0}[anchor]
        out.append(f'<text x="{x + dx:.1f}" y="{y - 9:.1f}" text-anchor="{anchor}" '
                   f'fill="{CRITICAL if p.get("critical_flag") else INK}">{_esc(val)}</text>')
        if i in label_idx:
            out.append(f'<text x="{x + dx:.1f}" y="{mt + ph + 18}" text-anchor="{anchor}" fill="{MUTED}">'
                       f'{_esc(str(p["date"])[:10])}</text>')
    out.append("</svg>")
    return "\n".join(out)


# --- treatment swimlane ------------------------------------------------------------------

def svg_treatment_timeline(episodes, start=None, end=None, width=640, locale="zh") -> str:
    """One row per regimen episode. Bars from started_at to ended_at; an ongoing episode (or one
    without an end date) runs to ``end`` with a faded, dashed right edge (open-ended, no arrow).
    Labels: regimen + cycle_label_verbatim, verbatim."""
    zh = str(locale).lower().startswith("zh")
    eps = [e for e in episodes or [] if isinstance(e, dict)]
    dated = [e for e in eps if _parse_date(e.get("started_at"))]
    s = _parse_date(start) or (min(_parse_date(e["started_at"]) for e in dated) if dated else None)
    ends = [_parse_date(e.get("ended_at")) for e in dated if _parse_date(e.get("ended_at"))]
    e_ = _parse_date(end) or max(ends + [_parse_date(today())] if dated else [_parse_date(today())])
    if s is None:
        s = e_ - _dt.timedelta(days=365)
    if e_ <= s:
        e_ = s + _dt.timedelta(days=30)
    row_h, ml, mr, mt = 34, 12, 12, 8
    h = mt + row_h * max(len(eps), 1) + 30
    pw = width - ml - mr
    span = (e_ - s).days

    def X(d):
        return ml + pw * max(0, min(1, (d - s).days / span))

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {h}" width="100%" '
           f'style="max-width:{width}px;height:auto" role="img" '
           f'aria-label="{"治疗时间轴" if zh else "Treatment timeline"}" font-family="{_esc(FONT)}" font-size="12">',
           '<defs><linearGradient id="cb-open" x1="0" x2="1" y1="0" y2="0">'
           f'<stop offset="0" stop-color="{BAR}"/><stop offset="1" stop-color="{BAR_OPEN}" stop-opacity="0.35"/>'
           "</linearGradient></defs>"]
    base = mt + row_h * max(len(eps), 1)
    for y in range(s.year, e_.year + 2):
        d = _dt.date(y, 1, 1)
        if s <= d <= e_:
            x = X(d)
            out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mt}" y2="{base}" stroke="{GRID}"/>')
            out.append(f'<text x="{x:.1f}" y="{base + 18}" text-anchor="middle" fill="{MUTED}">{y}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{base}" y2="{base}" stroke="{MUTED}"/>')
    for i, ep in enumerate(eps):
        y = mt + i * row_h
        label = " ".join(str(x) for x in (ep.get("regimen") or ("方案不详" if zh else "regimen unknown"),
                                          ep.get("cycle_label_verbatim")) if x)
        d_start = _parse_date(ep.get("started_at"))
        if not d_start:
            out.append(f'<text x="{ml}" y="{y + 20}" fill="{MUTED}">{_esc(label)}（{"开始日期不详" if zh else "start date unknown"}）</text>')
            continue
        d_end = _parse_date(ep.get("ended_at"))
        is_open = d_end is None or ep.get("status") == "ongoing"
        x0 = X(d_start)
        x1 = X(d_end if d_end and not is_open else e_)
        x1 = max(x1, x0 + 6)
        fill = "url(#cb-open)" if is_open else BAR
        out.append(f'<rect x="{x0:.1f}" y="{y + 4}" width="{x1 - x0:.1f}" height="12" rx="3" fill="{fill}"/>')
        if is_open:
            out.append(f'<line x1="{x1:.1f}" x2="{x1:.1f}" y1="{y + 2}" y2="{y + 18}" stroke="{BAR}" stroke-dasharray="2 2"/>')
        tail = ("（进行中）" if zh else " (ongoing)") if ep.get("status") == "ongoing" else ""
        anchor, tx = ("start", x0) if x0 < ml + pw * 0.6 else ("end", x1)
        out.append(f'<text x="{tx:.1f}" y="{y + 30}" text-anchor="{anchor}" fill="{INK}">{_esc(label + tail)}</text>')
    out.append("</svg>")
    return "\n".join(out)


# --- standalone chart page ----------------------------------------------------------------

_SIDECAR_CACHE = {}


def source_label(patient_dir, ref) -> str:
    """'<doc_kind> <doc_date>' for a sidecar ref, falling back to the file name."""
    path = _ref_path(ref)
    if not path:
        return ""
    if path.startswith("conversation:"):
        return "对话记录"
    key = (str(patient_dir), path)
    if key not in _SIDECAR_CACHE:
        p = Path(patient_dir) / path
        meta = {}
        if p.is_file():
            meta, _ = read_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        kind = str(meta.get("doc_kind") or "")
        if kind.startswith("novel:"):
            kind = kind[6:]
        _SIDECAR_CACHE[key] = " ".join(x for x in (kind, meta.get("doc_date")) if x) or Path(path).stem
    return _SIDECAR_CACHE[key]


def _safe_name(s) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", str(s)).strip("_") or "metric"


def _locale(patient_dir):
    prof = load_json(Path(patient_dir) / "profile.json", {}) or {}
    return prof.get("locale") or "zh"


def chart_questions(series, locale="zh") -> list:
    zh = str(locale).lower().startswith("zh")
    lab = series["label"]
    if zh:
        q = [f"这几次 {lab} 的数值，医生看的时候一般会结合哪些其他检查？"]
        if series.get("method_changes"):
            q.append(f"{lab} 这次换了检测方法，前后几次的数值能直接放在一起比吗？")
        elif series.get("excluded"):
            q.append(f"有一次 {lab} 的单位和其他几次不同，这次结果该怎么对照着看？")
        q.append(f"下一次复查 {lab} 一般安排在什么时候？")
    else:
        q = [f"When you look at these {lab} results, what else do you usually look at alongside them?"]
        if series.get("method_changes"):
            q.append(f"The {lab} test method changed. Can the results before and after be compared directly?")
        q.append(f"When is the next {lab} test usually scheduled?")
    return q[:3]


def render_chart_page(patient_dir, metric, out=None, title=None) -> Path:
    """Write charts/<metric>_趋势.html (standalone, printable, offline). Raises ValueError when
    fewer than 2 comparable points exist or the title contains verdict words."""
    patient_dir = Path(patient_dir)
    locale = _locale(patient_dir)
    zh = str(locale).lower().startswith("zh")
    if title is not None and verdict_words(title):
        raise ValueError(f"图表标题含有判断性的词（{'、'.join(verdict_words(title))}）。标题只写读图指引，不写结论。"
                         if zh else f"Chart title contains verdict wording ({', '.join(verdict_words(title))}).")
    s = series_for(patient_dir, metric)
    n = len(s["points"]) if s else 0
    if n < 2:
        if zh:
            msg = f"目前只有 {n} 次记录，再测一次就能看到变化" if n == 1 else f"档案里没有 {metric} 的可用记录，暂时画不了图"
        else:
            msg = (f"Only {n} result so far; one more test will show a change" if n == 1
                   else f"No usable {metric} results in the archive yet")
        raise ValueError(msg)
    t = title or default_title(s, locale)
    svg = svg_trend(s, title=t, locale=locale)
    rows = []
    allp = [(p, None) for p in s["points"]] + [(x["point"], x["reason"]) for x in s["excluded"]]
    allp.sort(key=lambda r: (_parse_date(r[0]["date"]) or _dt.date.min))
    reason_txt = {"unit": "单位不同，未画入图" if zh else "different unit; not plotted",
                  "unverified_read": "表格对不齐，读数未核实，未画入图" if zh else "misaligned table; unverified, not plotted",
                  "missing": "资料缺失" if zh else "missing",
                  "not_numeric": "不是数字，未画入图" if zh else "not a number; not plotted",
                  "no_date": "日期不详，未画入图" if zh else "no date; not plotted"}
    for p, reason in allp:
        shown = (_esc(p["raw_value"] if p["raw_value"] not in (None, "") else _fmt(p["value"]))
                 if reason not in ("unverified_read", "missing") else _esc("资料缺失" if zh else "missing"))
        flag = _esc(p.get("report_flag") or "")
        cls = ' class="crit"' if p.get("critical_flag") else ""
        rows.append(f"<tr><td>{_esc(p['date'] or '')}</td><td{cls}>{shown}</td><td>{flag}</td><td>{_esc(p.get('unit') or '')}</td>"
                    f"<td>{_esc(p.get('reference_range') or '')}</td><td>{_esc(p.get('method') or '')}</td>"
                    f"<td>{_esc(source_label(patient_dir, p.get('source_ref')))}<br><span class=ref>{_esc(p.get('source_ref') or '')}</span></td>"
                    f"<td>{_esc(reason_txt.get(reason, '')) if reason else ''}</td></tr>")
    notes = []
    for ch in s["method_changes"]:
        notes.append((f"{ch['date']} 起检测方法由“{ch['from'] or '未写明'}”变为“{ch['to'] or '未写明'}”，图中的线在这里断开，前后数值不直接相连。"
                      if zh else f"From {ch['date']} the method changed ({ch['from']} → {ch['to']}); the line is broken there."))
    for x in s["excluded"]:
        p = x["point"]
        if x["reason"] == "unit":
            notes.append((f"{p['date']} 这次的单位是 {p['unit']}，和图中的 {s['unit']} 不同，没有画进图里（不做换算）。"
                          if zh else f"{p['date']}: unit {p['unit']} differs from {s['unit']}; not plotted (no conversion)."))
        elif x["reason"] == "unverified_read":
            notes.append((f"{p['date']} 这次化验单表格对不齐，数值未核实，没有画进图里。"
                          if zh else f"{p['date']}: the table row was misaligned; the reading is unverified and not plotted."))
    if not s.get("reference_range"):
        notes.append("各次报告的参考范围不完全相同，所以图上不画参考范围带，请看下表每次报告自己的范围。"
                     if zh else "Reference ranges differ between reports, so no band is drawn; see each report's range below.")
    if any(p.get("critical_flag") for p in s["points"]):
        notes.append("红色的点是报告本身标了“危急值”的结果。" if zh else "Red dots are results the report itself flagged as critical.")
    qs = chart_questions(s, locale)
    L = (lambda z, e: z if zh else e)
    page = f"""<!DOCTYPE html>
<html lang="{'zh-CN' if zh else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="cancer-buddy v2 chart">
<title>{_esc(s['label'])} {L('趋势', 'trend')}</title>
<style>
@page {{ size: A4; margin: 14mm; }}
body {{ font-family: {FONT}; color: {INK}; background: #fff; margin: 0 auto; max-width: 760px; padding: 16px; font-size: 14px; line-height: 1.6; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }}
.guide {{ color: {MUTED}; margin: 0 0 12px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; }}
th, td {{ border-bottom: 1px solid {GRID}; padding: 4px 6px; text-align: left; vertical-align: top; }}
th {{ background: #f6f4f9; }}
.crit {{ color: {CRITICAL}; font-weight: 600; }}
.ref {{ color: {MUTED}; font-size: 12px; word-break: break-all; }}
.box {{ background: #f6f4f9; border-radius: 6px; padding: 8px 12px; margin: 12px 0; }}
footer {{ color: {MUTED}; font-size: 12px; margin-top: 16px; }}
@media print {{ body {{ font-size: 10pt; }} }}
</style></head><body>
<h1>{_esc(s['label'])} {L('各次结果', 'results')}</h1>
<p class="guide">{_esc(t)}</p>
{svg}
<h2 style="font-size:16px">{L('每一次的数值和出处', 'Every result and its source')}</h2>
<div style="overflow-x:auto"><table><thead><tr><th>{L('日期', 'Date')}</th><th>{L('结果', 'Result')}</th><th>{L('报告标记', 'Flag')}</th><th>{L('单位', 'Unit')}</th><th>{L('参考范围（该次报告）', 'Reference range (that report)')}</th><th>{L('方法', 'Method')}</th><th>{L('出处', 'Source')}</th><th>{L('说明', 'Note')}</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{('<div class="box"><b>' + L('读图时请注意', 'Notes') + '</b><ul>' + ''.join('<li>' + _esc(n_) + '</li>' for n_ in notes) + '</ul></div>') if notes else ''}
<div class="box"><b>{L('可以问医生的问题', 'Questions you could ask')}</b><ul>{''.join('<li>' + _esc(q) + '</li>' for q in qs)}</ul></div>
<footer>{L('数值照抄各次原报告，图只用来帮助翻看；数值的变化是观察，不等于疗效判断。本页是资料索引，不替代主诊医生的判断。', 'Values are copied from each report; changes are observations, not a judgement of treatment effect. This page does not replace your care team.')}　{L('生成日期', 'Generated')} {today()}</footer>
</body></html>
"""
    if out is None:
        out = patient_dir / "charts" / f"{_safe_name(s['label'])}_趋势.html"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
