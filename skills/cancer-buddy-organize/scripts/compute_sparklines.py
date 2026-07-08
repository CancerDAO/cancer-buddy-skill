#!/usr/bin/env python3
"""Enrich case_summary_data.json with inline-SVG trend geometry (stdlib only, ZERO medical logic).

The 段D case-summary renderer (render_html_template.py) is a dumb string
substitutor — it cannot compute chart geometry. This helper is the deterministic,
patient-agnostic layer that turns a numeric series into the coordinate strings the
template's inline `<svg>` markup consumes. It knows NOTHING about cancer, labs, or
what a "good" trend is: it only maps (timestamp, value) pairs onto a fixed viewBox.

It reads each `trend_charts[]` chart and each `lab_trends[]` row already assembled by
the 段D subagent (values copied VERBATIM from longitudinal_observations.json /
labs.json — never invented, never re-derived here) and injects, per series:

  - svg_points   : "x1,y1 x2,y2 …"            → <polyline points="…">
  - svg_area_d   : "M x1,y1 L … L xn,yB L x1,yB Z" → <path d="…"> (filled area; hero only)
  - direction    : "down" | "up" | "flat" | "single"  (deterministic; MOST RECENT
                   segment = last point vs previous; drives the ▲/▼ arrow GLYPH
                   only — the badge colour is neutral, no good/bad valence)
  - point_count  : number of numeric points actually plotted

For each chart's `treatment_markers[]` it injects `marker_x` (x on the SAME
time axis as the series) so a regimen-change guide line lines up with the curve —
that is the 指标↔治疗方案 correspondence. Time-proportional x (by calendar day)
keeps irregular follow-up intervals honest; even-spacing would lie about tempo.

ANTI-FABRICATION GATE (optional, fail-closed): with --longitudinal / --labs, every
plotted value MUST appear (metric + value) in the source store. A curve point with
no backing observation is a fabricated data point — the single most dangerous
failure for a patient-facing trend — and aborts with exit 3. Wire these in the
pipeline (SKILL.md Step 12) so no invented point can ship.

Charts are inline SVG ONLY — no <canvas>, no <script> — because the delivery PDF
print path drops canvas (see project delivery notes). This helper never emits an
element; it only emits coordinate strings the template's static SVG consumes.

CLI:
    python3 compute_sparklines.py --data case_summary_data.json            # enrich in place
    python3 compute_sparklines.py --data D.json --out enriched.json        # write elsewhere
    python3 compute_sparklines.py --data D.json --longitudinal L.json --labs labs.json  # + integrity gate

Exit codes:
    0  — enriched OK
    2  — bad invocation / unreadable / malformed input
    3  — anti-fabrication gate failed (a plotted value is absent from the source store)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Fixed viewBoxes — the template's <svg viewBox> MUST match these.
HERO_W, HERO_H, HERO_PAD = 360.0, 120.0, 12.0
SPARK_W, SPARK_H, SPARK_PAD = 120.0, 32.0, 5.0
_EPS = 1e-9


# ----- parsing helpers -------------------------------------------------------
def _to_float(v):
    """Return v as float, or None if not numeric. Accepts int/float and numeric
    strings (tolerates a leading comparator like '<' / '>' and stray spaces)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().lstrip("<>≤≥").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _to_ordinal(ts):
    """ISO date / date-time string → day ordinal (int), or None if unparseable.
    Only the calendar-day resolution matters for a follow-up trend axis."""
    if not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    # normalise a trailing Z and take the date part for day-resolution.
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).date().toordinal()
    except ValueError:
        pass
    try:
        return date.fromisoformat(s[:10]).toordinal()
    except ValueError:
        return None


def _fmt(n: float) -> str:
    """Compact fixed-precision coordinate (1 dp), no trailing '.0' noise."""
    r = round(n, 1)
    if r == int(r):
        return str(int(r))
    return str(r)


# ----- geometry --------------------------------------------------------------
def _numeric_series(series):
    """Filter to plottable points [(ordinal, value, raw_value)], sorted by day.
    Points with a non-numeric value or unparseable timestamp are dropped."""
    pts = []
    if not isinstance(series, list):
        return pts
    for p in series:
        if not isinstance(p, dict):
            continue
        v = _to_float(p.get("v"))
        o = _to_ordinal(p.get("t"))
        if v is None or o is None:
            continue
        pts.append((o, v, p.get("v")))
    pts.sort(key=lambda x: x[0])
    return pts


def _x_axis(ordinals, w: float, pad: float):
    """Map day-ordinals → x pixels, time-proportional. Single/degenerate span →
    everything centred so a lone point renders mid-canvas."""
    lo, hi = min(ordinals), max(ordinals)
    span = hi - lo
    inner = w - 2 * pad
    if span <= 0:
        cx = pad + inner / 2
        return lambda o: cx, lo, hi
    return lambda o: pad + (o - lo) / span * inner, lo, hi


def _y_of(v: float, vmin: float, vmax: float, h: float, pad: float) -> float:
    """Value → y pixels (SVG y grows downward, so higher value = smaller y).
    Flat series (vmax==vmin) sits on the vertical midline."""
    inner = h - 2 * pad
    if vmax - vmin < _EPS:
        return h / 2
    return h - pad - (v - vmin) / (vmax - vmin) * inner


def _direction(pts):
    """Trend direction from the MOST RECENT segment (last point vs the previous
    one), NOT first-vs-last. A marker that responded then progressed (e.g. CEA
    dipped deeply on treatment, then rose again) must read as the recent rise, not
    the net drop from baseline — first-vs-last would paint a rising cancer marker
    as an "improving" ▼. The arrow is a direction glyph only; clinical valence
    (down=good vs down=bad) is metric-dependent and is NOT encoded in the colour
    (see the neutral .trend-badge.up/.down colour in the template)."""
    if len(pts) < 2:
        return "single" if pts else "flat"
    prev, last = pts[-2][1], pts[-1][1]
    if abs(last - prev) < _EPS:
        return "flat"
    return "down" if last < prev else "up"


def _enrich_series(obj, w, h, pad, with_area: bool, with_dots: bool = False):
    """Inject svg_points / (svg_area_d) / (dots[]) / direction / point_count into obj.

    A polyline/area needs ≥2 points, so svg_points/svg_area_d are emitted only
    then (a 1-point series → "" so no degenerate line renders); the lone point
    still surfaces via dots[] (hero) and the numeric current_value. dots[] carries
    per-vertex {cx,cy} for the open-circle markers in the reference design.
    Returns list of (raw_value) actually plotted, for the integrity gate."""
    pts = _numeric_series(obj.get("series"))
    obj["point_count"] = len(pts)
    obj["direction"] = _direction(pts)
    if pts:
        # raw first/last plotted values, for a readout panel ("current value")
        obj["last_value"] = str(pts[-1][2])
        obj["first_value"] = str(pts[0][2])
    else:
        obj["last_value"] = ""
        obj["first_value"] = ""
    if not pts:
        obj["svg_points"] = ""
        if with_area:
            obj["svg_area_d"] = ""
        if with_dots:
            obj["dots"] = []
        return []
    xf, _, _ = _x_axis([o for o, _, _ in pts], w, pad)
    vmin = min(v for _, v, _ in pts)
    vmax = max(v for _, v, _ in pts)
    coords = [(xf(o), _y_of(v, vmin, vmax, h, pad)) for o, v, _ in pts]
    obj["svg_points"] = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in coords) if len(coords) >= 2 else ""
    if with_area:
        if len(coords) >= 2:
            base = h - pad
            d = ["M", f"{_fmt(coords[0][0])},{_fmt(coords[0][1])}"]
            for x, y in coords[1:]:
                d += ["L", f"{_fmt(x)},{_fmt(y)}"]
            d += ["L", f"{_fmt(coords[-1][0])},{_fmt(base)}",
                  "L", f"{_fmt(coords[0][0])},{_fmt(base)}", "Z"]
            obj["svg_area_d"] = " ".join(d)
        else:
            obj["svg_area_d"] = ""
    if with_dots:
        obj["dots"] = [{"cx": _fmt(x), "cy": _fmt(y)} for x, y in coords]
    return [raw for _, _, raw in pts]


# Vertical de-collision: badges whose x fall within BADGE_GAP viewBox units are
# stacked onto successive rows so the ①② numbers never overlap on a small chart.
BADGE_GAP = 26.0
BADGE_CY0 = 10.0      # first-row badge centre y
BADGE_DY = 15.0       # row spacing


def _enrich_markers(hero, w, pad):
    """Place treatment-line markers on the hero series' time axis (clamped to the
    plotted span) and inject, per marker: idx, marker_date, marker_x (dashed-line
    x, TRUE date position), badge_cy/badge_ty (vertically de-collided badge, so
    close markers never overlap), and badge_pct (x as a % of chart width, for the
    fixed-size HTML hover tooltip that does NOT shrink with the chart)."""
    markers = hero.get("treatment_markers")
    if not isinstance(markers, list) or not markers:
        return
    dict_markers = [m for m in markers if isinstance(m, dict)]
    pts = _numeric_series(hero.get("series"))
    if not pts:
        for i, m in enumerate(dict_markers):
            m["idx"] = i + 1
            t = m.get("t")
            m["marker_date"] = t[:7] if isinstance(t, str) and len(t) >= 7 else (t or "")
            m["marker_x"] = _fmt(pad)
            m["marker_x_left"] = _fmt(pad - 6)
            m["badge_pct"] = _fmt(pad / w * 100)
            m["badge_cy"] = _fmt(BADGE_CY0)
            m["badge_ty"] = _fmt(BADGE_CY0 + 3.3)
        return
    ordinals = [o for o, _, _ in pts]
    xf, lo, hi = _x_axis(ordinals, w, pad)
    for i, m in enumerate(dict_markers):
        m["idx"] = i + 1  # 1-based label shared by the on-chart badge + the legend
        t = m.get("t")
        m["marker_date"] = t[:7] if isinstance(t, str) and len(t) >= 7 else (t or "")
        o = _to_ordinal(t)
        x = pad if o is None else xf(max(lo, min(hi, o)))
        m["_x"] = x
        m["marker_x"] = _fmt(x)
        m["marker_x_left"] = _fmt(x - 6)
        m["badge_pct"] = _fmt(x / w * 100)
    # de-collide badges vertically: process left-to-right, drop to the next row
    # whenever a badge would sit within BADGE_GAP of the last badge on that row.
    row_last_x = []
    for m in sorted(dict_markers, key=lambda mm: mm["_x"]):
        x = m["_x"]
        row = next((r for r, lx in enumerate(row_last_x) if x - lx >= BADGE_GAP), None)
        if row is None:
            row = len(row_last_x)
            row_last_x.append(x)
        else:
            row_last_x[row] = x
        cy = BADGE_CY0 + row * BADGE_DY
        m["badge_cy"] = _fmt(cy)
        m["badge_ty"] = _fmt(cy + 3.3)
        del m["_x"]


# ----- anti-fabrication gate -------------------------------------------------
def _source_index(paths):
    """Build {metric_lower: set_of_value_reprs} from longitudinal / labs stores.
    Values are indexed both as canonical float repr (when numeric) and as the
    raw string, so '1.81' matches 1.81 and a categorical value matches verbatim."""
    idx: dict[str, set] = {}

    def add(metric, value):
        if metric is None:
            return
        key = str(metric).strip().lower()
        bucket = idx.setdefault(key, set())
        f = _to_float(value)
        if f is not None:
            bucket.add(("num", round(f, 6)))
        bucket.add(("str", str(value).strip()))

    for p in paths:
        if not p:
            continue
        try:
            doc = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        # longitudinal_observations.json → observations[].{metric,value}
        for o in doc.get("observations", []):
            if isinstance(o, dict):
                add(o.get("metric"), o.get("value"))
        # labs.json (labs.schema.json) → panels[].{analyte, values[].value}
        for panel in doc.get("panels", []):
            if not isinstance(panel, dict):
                continue
            analyte = panel.get("analyte")
            for v in panel.get("values", []) or []:
                if isinstance(v, dict):
                    add(analyte, v.get("value"))
        # tolerant fallback for a flat labs[] shape (older/other exports)
        for row in doc.get("labs", []) or []:
            if isinstance(row, dict):
                name = row.get("lab_name") or row.get("name") or row.get("analyte")
                val = row.get("value") if row.get("value") is not None else row.get("lab_value")
                add(name, val)
    return idx


def _value_backed(idx, metric, raw_value) -> bool:
    if metric is None:
        return False
    bucket = idx.get(str(metric).strip().lower())
    if not bucket:
        return False
    f = _to_float(raw_value)
    if f is not None and ("num", round(f, 6)) in bucket:
        return True
    return ("str", str(raw_value).strip()) in bucket


def _integrity_violations(data, idx):
    """Return list of human-readable violations: plotted (metric,value) with no
    backing observation in the source store."""
    bad = []
    for chart in data.get("trend_charts", []) or []:
        if isinstance(chart, dict) and isinstance(chart.get("series"), list):
            for p in chart["series"]:
                if isinstance(p, dict) and _to_float(p.get("v")) is not None:
                    if not _value_backed(idx, chart.get("metric"), p.get("v")):
                        bad.append(f"trend_charts[{chart.get('metric')!r}] value {p.get('v')!r} @ {p.get('t')!r}")
    for row in data.get("lab_trends", []) or []:
        if isinstance(row, dict) and isinstance(row.get("series"), list):
            for p in row["series"]:
                if isinstance(p, dict) and _to_float(p.get("v")) is not None:
                    if not _value_backed(idx, row.get("lab_name"), p.get("v")):
                        bad.append(f"lab_trends[{row.get('lab_name')!r}] value {p.get('v')!r} @ {p.get('t')!r}")
    return bad


# ----- driver ----------------------------------------------------------------
def enrich(data: dict) -> dict:
    # 关键趋势 = 0..N featured charts (the skill decides how many are clinically
    # salient — one dominant marker → 1, several drivers → a few, none → []).
    for chart in data.get("trend_charts", []) or []:
        if isinstance(chart, dict):
            _enrich_series(chart, HERO_W, HERO_H, HERO_PAD, with_area=True, with_dots=True)
            _enrich_markers(chart, HERO_W, HERO_PAD)
    for row in data.get("lab_trends", []) or []:
        if isinstance(row, dict):
            _enrich_series(row, SPARK_W, SPARK_H, SPARK_PAD, with_area=False)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject inline-SVG trend geometry into case_summary_data.json (deterministic, zero medical logic).")
    ap.add_argument("--data", required=True, help="path to case_summary_data.json")
    ap.add_argument("--out", help="output path (default: overwrite --data in place)")
    ap.add_argument("--longitudinal", help="longitudinal_observations.json for the anti-fabrication gate")
    ap.add_argument("--labs", help="labs.json for the anti-fabrication gate")
    args = ap.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot read/parse --data: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("ERROR: --data root must be a JSON object", file=sys.stderr)
        return 2

    if args.longitudinal or args.labs:
        idx = _source_index([args.longitudinal, args.labs])
        violations = _integrity_violations(data, idx)
        if violations:
            print("ERROR: anti-fabrication gate — plotted value(s) absent from source store:", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 3

    enrich(data)

    out = args.out or args.data
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n_charts = sum(1 for c in (data.get("trend_charts") or []) if isinstance(c, dict))
    n_labs = sum(1 for r in (data.get("lab_trends") or []) if isinstance(r, dict))
    print(f"enriched → {out} (trend charts={n_charts}, lab_trend rows={n_labs})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
