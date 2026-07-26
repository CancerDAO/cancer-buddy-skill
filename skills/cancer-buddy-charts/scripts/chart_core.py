#!/usr/bin/env python3
"""Geometry + style primitives for cancer-buddy clinical charts (stdlib only).

This is layer 1 of a two-layer design (see references/chart-catalog.md §generalisation):

    layer 1 — primitives (THIS FILE): axes, reference bands, label de-collision,
              furniture, palette, SVG assembly. Covers ANY chart type.
    layer 2 — recipes (render_chart.py): C1..C10 are recipes composed from these
              primitives. A chart type nobody anticipated is a NEW RECIPE, not a
              new engine — that is what makes the skill generalise instead of
              being a 10-chart lookup table.

ZERO medical logic, by construction. This module maps (value, date, range) onto
pixels and picks a colour from a fixed token table. It does not know what a lab
value means, whether a trend is good, or which marker matters. Parsing a
reference-range STRING is string parsing, not clinical judgement — deciding what
being outside that range MEANS is clinical judgement and lives nowhere in this
codebase.

Two rendering channels, deliberately separated (see SKILL.md):

  channel A — 段D case-summary embed. Geometry is injected as coordinate STRINGS
              into a hand-written SVG skeleton in case-summary.template.html.
              render_html_template.py html.escape()s every {{value}}, so no
              markup can be smuggled through data. viewBox units, not pt.
  channel B — standalone chart file (paths B and C). This module assembles the
              whole SVG itself and escapes text itself. viewBox unit == 1pt, so
              font sizes are literal pt and cannot drift with container width.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_EPS = 1e-9

# ─────────────────────────────────────────────────────────────────────────────
# Palette — CancerDAO token table, extracted from case-summary.template.html.
# SSOT: references/chart-style.md. Do not invent colours outside this table.
# ─────────────────────────────────────────────────────────────────────────────
INK = "#2b2340"          # primary text / dark ground
MUTED = "#8b7fa6"        # secondary text
MUTED_DEEP = "#574a6e"   # tertiary text
PRIMARY = "#6b4bb3"      # main accent
PRIMARY_HI = "#7c5cff"   # brighter accent (series stroke)
LADDER = ["#f4ecff", "#ece4fb", "#e7d1ff", "#c9a4ff", "#a678ee"]  # light → deep
AMBER = "#b7791f"        # out-of-range OUTLINE (never fill)
AMBER_BG = "#fdf3e2"
CRIT = "#c0392b"         # ONLY for values the SOURCE REPORT flagged critical
CRIT_BG = "#fdeeee"
CARD = "#ffffff"
CARD_ALT = "#fcfaff"
RULE = "#ece4fb"         # hairline rules / furniture
BAND = "#f4ecff"         # reference-range band fill

# Deliberately absent: green. Green reads as "good", which is a clinical verdict
# we have no authority to give. In-range points use PRIMARY, not green.
# See references/chart-style.md §red-restraint.

# Typography — channel B uses viewBox unit == 1pt, so these are literal pt.
# Floor is 8pt body / 10pt figures: patients with cancer skew older than 60 and
# routinely PRINT these charts to hand to a clinician. lieflat's 6.5px floor is
# for on-screen ops dashboards and is not transferable.
FS_BODY = 8.0
FS_AXIS = 8.0
FS_VALUE = 10.0
FS_TITLE = 11.0
FS_MIN = 8.0             # validate_chart_svg.py enforces this
FONT_STACK = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", '
              '"Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif')


# ─────────────────────────────────────────────────────────────────────────────
# Parsing — byte-compatible with compute_sparklines.py for the fields channel A
# already ships. Any behaviour change here breaks the 段D golden template.
# ─────────────────────────────────────────────────────────────────────────────
def to_float(v):
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


_CENSOR_LEFT = ("<", "＜", "≤", "<=")
_CENSOR_RIGHT = (">", "＞", "≥", ">=")


def censoring(raw):
    """Detect a censored reading: 'left' for '<5.0', 'right' for '>1000', else None.

    A value reported as '<5.0' is NOT a measurement of 5.0 — the true value lies
    somewhere below the assay's limit of detection and could be 0.1 or 4.9.
    Plotting it as 5.0 is false precision, which is the quiet cousin of
    fabrication. We still plot it (dropping the point would break the series and
    lose more information than it protects), but the marker is drawn differently
    and the reading note says how many points are censored, so the patient and
    their clinician can see which vertices are bounds rather than readings.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.startswith(_CENSOR_LEFT):
        return "left"
    if s.startswith(_CENSOR_RIGHT):
        return "right"
    return None


def to_ordinal(ts):
    """ISO date / date-time string → day ordinal (int), or None if unparseable."""
    if not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).date().toordinal()
    except ValueError:
        pass
    try:
        return date.fromisoformat(s[:10]).toordinal()
    except ValueError:
        return None


def fmt(n: float) -> str:
    """Compact fixed-precision coordinate (1 dp), no trailing '.0' noise."""
    r = round(n, 1)
    if r == int(r):
        return str(int(r))
    return str(r)


def esc(s) -> str:
    """XML text escape for channel B (channel A is escaped by the template
    renderer instead). Escapes the full set including quotes, so the same helper
    is safe in both text nodes and attribute values."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


# ─────────────────────────────────────────────────────────────────────────────
# Reference ranges
# ─────────────────────────────────────────────────────────────────────────────
# Accepts the shapes Chinese and English lab reports actually print. Returns
# (lo, hi) with either bound possibly None for one-sided ranges, or None when the
# string cannot be parsed UNAMBIGUOUSLY. Never guesses: a sex-split range
# ("男 13.0-17.5 女 11.5-15.0") returns None rather than picking a side, because
# picking would require knowing the patient's sex AND deciding it applies — both
# clinical judgements. A None result is not a failure; it renders as an explicit
# "本次报告未提供可解析的参考区间" note, which is itself useful information.
_NUM = r"[-+]?\d+(?:\.\d+)?"
_RANGE_RE = re.compile(rf"^\s*({_NUM})\s*(?:-|–|—|~|～|to|至)\s*({_NUM})\s*$", re.I)
_UPPER_RE = re.compile(rf"^\s*(?:<|＜|≤|<=|小于|不高于|不大于)\s*({_NUM})\s*$")
_LOWER_RE = re.compile(rf"^\s*(?:>|＞|≥|>=|大于|不低于|不小于)\s*({_NUM})\s*$")
# A second numeric pair anywhere means the string encodes MORE than one range
# (sex-split, age-split, method-split) → ambiguous, refuse.
_MULTI_RE = re.compile(rf"{_NUM}\s*(?:-|–|—|~|～)\s*{_NUM}")


def parse_reference_range(raw):
    """Reference-range string → (lo, hi) | None. Pure string parsing.

    (lo, None)  = lower bound only   (e.g. '>10')
    (None, hi)  = upper bound only   (e.g. '<5.0')
    None        = unparseable or ambiguous — DO NOT draw a band, say so instead.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # strip a trailing unit that some reports append inside the range field
    s = re.sub(r"\s*(?:mg/L|ng/mL|g/L|U/mL|IU/mL|mmol/L|umol/L|µmol/L|%|10\^\d+/L)\s*$",
               "", s, flags=re.I).strip()
    if len(_MULTI_RE.findall(s)) > 1:
        return None  # more than one range encoded — ambiguous, refuse to guess
    m = _RANGE_RE.match(s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo, hi) if lo <= hi else (hi, lo)
    m = _UPPER_RE.match(s)
    if m:
        return (None, float(m.group(1)))
    m = _LOWER_RE.match(s)
    if m:
        return (float(m.group(1)), None)
    return None


def range_status(value, ref):
    """Classify a value against a parsed range. Returns one of:
        'in'      — inside the range
        'out'     — outside the range
        'unknown' — no parseable range (or non-numeric value)

    NOTE the deliberate absence of severity grading ('high', 'critical',
    'grade 3'…). Distance outside a reference interval is not severity; grading
    it would be a clinical judgement. Criticality is only ever transcribed from
    the source report's own flag — see Palette.point_colour.
    """
    v = to_float(value)
    if v is None or not ref:
        return "unknown"
    lo, hi = ref
    if lo is not None and v < lo - _EPS:
        return "out"
    if hi is not None and v > hi + _EPS:
        return "out"
    return "in"


def point_colour(status: str, source_flagged_critical: bool = False):
    """Semantic colour assignment — the red-restraint rule (chart-style.md).

    Red is reserved for values the SOURCE REPORT itself flagged critical. A
    merely out-of-range value gets an amber OUTLINE, never a red fill: being
    outside a reference interval is extremely common and usually not clinically
    meaningful, while a screenful of red is a high-intensity anxiety signal for a
    cancer patient that can drive real harm (a midnight ER trip, self-stopping a
    drug). We transcribe the report's alarm; we do not raise our own.

    Returns (stroke, fill) — fill 'none' means outline-only.
    """
    if source_flagged_critical:
        return (CRIT, CRIT_BG)
    if status == "out":
        return (AMBER, "none")
    if status == "in":
        return (PRIMARY, CARD)
    return (MUTED, CARD)


# ─────────────────────────────────────────────────────────────────────────────
# Axes
# ─────────────────────────────────────────────────────────────────────────────
class TimeAxis:
    """Day-ordinal → x pixels, TIME-PROPORTIONAL.

    Even spacing would lie about tempo: four labs over eight years and four labs
    over four weeks must not look alike. A single point (or a degenerate span)
    centres, so a lone reading renders mid-canvas instead of collapsing to the
    left edge.
    """

    def __init__(self, ordinals, w: float, pad: float):
        ordinals = [o for o in ordinals if o is not None]
        self.w, self.pad = w, pad
        self.inner = w - 2 * pad
        if not ordinals:
            self.lo = self.hi = None
            self.span = 0
        else:
            self.lo, self.hi = min(ordinals), max(ordinals)
            self.span = self.hi - self.lo

    @property
    def degenerate(self) -> bool:
        return self.lo is None or self.span <= 0

    def x(self, o) -> float:
        if self.degenerate or o is None:
            return self.pad + self.inner / 2
        return self.pad + (o - self.lo) / self.span * self.inner

    def x_clamped(self, o) -> float:
        """x for a date that may fall outside the plotted span (e.g. a treatment
        start earlier than the first lab) — clamped onto the axis so the guide
        line stays inside the canvas."""
        if o is None or self.lo is None:
            return self.pad
        return self.x(max(self.lo, min(self.hi, o)))

    def gap_days(self):
        """Largest gap between consecutive plotted days, for the reading-note
        generator ('中间有 N 个月空档'). Returns (days, after_index) or None."""
        return None  # computed by the recipe, which holds the ordered points


def time_unit_grid(lo_ord: int, hi_ord: int, target=(18, 60)):
    """Split a span into countable calendar units. Returns (ordinals, unit_name).

    The Lupi lesson that transfers to clinical data is that density must come
    from a HONEST countable unit, not from decoration and never from invented
    points. Follow-up series are sparse (3–15 readings), so the countable unit
    is not the reading — it is the calendar. Twenty-nine months in which only
    twelve had a test is a true statement, and drawing all twenty-nine makes the
    sixteen empty ones visible instead of hiding them inside a long line.

    Picks the finest unit whose count lands in `target`, so a 3-week span reads
    in days and a 10-year span reads in quarters.
    """
    import datetime as _dt
    span = max(1, hi_ord - lo_ord)
    lo_d, hi_d = _dt.date.fromordinal(lo_ord), _dt.date.fromordinal(hi_ord)

    def days(step):
        return [lo_ord + i * step for i in range(span // step + 1)]

    def months(step):
        out, y, m = [], lo_d.year, lo_d.month
        while (y, m) <= (hi_d.year, hi_d.month):
            out.append(_dt.date(y, m, 1).toordinal())
            m += step
            while m > 12:
                m -= 12
                y += 1
        return out

    for gen, name in ((lambda: days(1), "天"), (lambda: days(7), "周"),
                      (lambda: months(1), "个月"), (lambda: months(3), "个季度"),
                      (lambda: months(12), "年")):
        got = gen()
        if target[0] <= len(got) <= target[1]:
            return got, name
    # nothing landed in range: fall back to the coarsest that is not absurd
    return (months(12) if span > 3650 else months(3)), ("年" if span > 3650 else "个季度")


class ValueAxis:
    """Value → y pixels. SVG y grows downward, so a higher value sits higher.

    When a reference range is supplied the domain is EXPANDED to include it, so
    the band is always visible and a point sitting just inside the boundary
    reads as just inside — an auto-scaled domain that clipped the band would
    silently exaggerate how far out a value is.
    """

    def __init__(self, values, h: float, pad: float, ref=None, include_zero=False):
        vals = [to_float(v) for v in values]
        vals = [v for v in vals if v is not None]
        self.h, self.pad = h, pad
        self.inner = h - 2 * pad
        if not vals:
            self.vmin = self.vmax = 0.0
            self.flat = True
            return
        vmin, vmax = min(vals), max(vals)
        if ref:
            lo, hi = ref
            if lo is not None:
                vmin, vmax = min(vmin, lo), max(vmax, lo)
            if hi is not None:
                vmin, vmax = min(vmin, hi), max(vmax, hi)
        if include_zero:
            vmin = min(vmin, 0.0)
        # headroom so markers/labels at the extremes are not flush to the edge
        if vmax - vmin > _EPS:
            margin = (vmax - vmin) * 0.08
            vmin, vmax = vmin - margin, vmax + margin
        self.vmin, self.vmax = vmin, vmax
        self.flat = (vmax - vmin) < _EPS

    def y(self, v) -> float:
        f = to_float(v)
        if f is None or self.flat:
            return self.h / 2
        return self.h - self.pad - (f - self.vmin) / (self.vmax - self.vmin) * self.inner


# ─────────────────────────────────────────────────────────────────────────────
# Label de-collision
# ─────────────────────────────────────────────────────────────────────────────
def stack_rows(positions, min_gap: float, row0: float, row_dy: float):
    """1-D de-collision by stacking onto successive rows.

    Same algorithm the existing treatment-marker badges use: walk left to right,
    drop to the next row whenever a label would sit within min_gap of the last
    label already on that row. Returns a list of row indices parallel to
    `positions` (input order preserved). Callers turn a row index into a y with
    row0 + row * row_dy.

    Shrinking the font to fit is NOT an option (chart-style.md §type): below the
    8pt floor a printed chart stops being readable for the actual audience.
    """
    order = sorted(range(len(positions)), key=lambda i: positions[i])
    rows = [0] * len(positions)
    row_last = []
    for i in order:
        p = positions[i]
        row = next((r for r, lx in enumerate(row_last) if p - lx >= min_gap), None)
        if row is None:
            row = len(row_last)
            row_last.append(p)
        else:
            row_last[row] = p
        rows[i] = row
    return rows


def row_y(row: int, row0: float, row_dy: float) -> float:
    return row0 + row * row_dy


def text_width(s, size: float) -> float:
    """Estimate rendered width. CJK glyphs are full-width, ASCII roughly 0.55em.

    An estimate is enough because it only has to be conservative: over-estimating
    pushes labels slightly further apart, which is harmless, while
    under-estimating lets them overlap, which is not.
    """
    w = 0.0
    for ch in str(s):
        w += size if ord(ch) > 0x2E80 else size * 0.55
    return w


class LabelPlacer:
    """2-D collision avoidance for point labels.

    Row-stacking (`stack_rows`) only works when every label shares one baseline —
    axis ticks, marker badges. For values printed above their own data point it
    fails silently: each label starts from a DIFFERENT y, so shifting one by a
    row offset does not necessarily separate it from its neighbour, and two
    points at similar heights collide no matter which "row" they were assigned.
    That is how "29.9" and "25.3" printed as "29.25.3".

    So place labels as rectangles in absolute coordinates: walk left to right,
    and lift a label until it clears everything already placed. Lifting (never
    shrinking) is deliberate — the 8pt floor exists for readers who will print
    this and read it with reading glasses.
    """

    def __init__(self, pad: float = 1.5, step: float = 2.0, max_lift: int = 14):
        self.boxes = []
        self.pad = pad
        self.step = step
        self.max_lift = max_lift

    def place(self, cx: float, y_anchor: float, text, size: float,
              gap: float = 6.0, upward: bool = True):
        """Return the baseline y for a label centred on cx above/below y_anchor.

        Returns None when it cannot be placed within max_lift attempts — the
        caller should then drop the label rather than draw it on top of another.
        """
        w = text_width(text, size) + self.pad * 2
        h = size * 1.15
        x1, x2 = cx - w / 2, cx + w / 2
        top = (y_anchor - gap - h) if upward else (y_anchor + gap)
        for _ in range(self.max_lift):
            box = (x1, top, x2, top + h)
            if not any(self._hit(box, b) for b in self.boxes):
                self.boxes.append(box)
                return top + h * 0.82          # baseline inside the box
            top += -(h + self.step) if upward else (h + self.step)
        return None

    def reserve(self, x1: float, y1: float, x2: float, y2: float):
        """Block out an area labels must not enter (axis strip, legend, band)."""
        self.boxes.append((x1, y1, x2, y2))

    def _hit(self, a, b) -> bool:
        return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def truncate(text, max_chars: int):
    """Truncate a long label, returning (shown, full). The caller MUST emit the
    full string in a <title> so nothing is lost — CJK regimen names and analyte
    names routinely blow past any sane column width."""
    s = str(text)
    if len(s) <= max_chars:
        return s, s
    return s[: max_chars - 1] + "…", s


# ─────────────────────────────────────────────────────────────────────────────
# SVG assembly (channel B)
# ─────────────────────────────────────────────────────────────────────────────
class Svg:
    """Static-SVG builder. Emits literal markup only — never a <script>, never a
    <canvas>, never an external reference. The output must survive being printed
    to PDF, screenshotted into a family group chat, and forwarded to a second
    -opinion clinician, all looking identical.

    viewBox unit == 1pt in channel B, so every font-size below is literal pt and
    cannot drift when a container resizes.
    """

    def __init__(self, w: float, h: float, label: str = ""):
        self.w, self.h = w, h
        self.label = label
        self.parts = []

    # -- primitives ----------------------------------------------------------
    def raw(self, markup: str):
        self.parts.append(markup)
        return self

    def line(self, x1, y1, x2, y2, stroke=RULE, width=0.6, dash=None, cap="butt"):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
            f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="{cap}"{d}/>')
        return self

    def rect(self, x, y, w, h, fill=BAND, stroke="none", width=0.6, rx=0.0):
        r = f' rx="{fmt(rx)}"' if rx else ""
        self.parts.append(
            f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(max(0.0, w))}" '
            f'height="{fmt(max(0.0, h))}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{width}"{r}/>')
        return self

    def circle(self, cx, cy, r, fill=CARD, stroke=PRIMARY, width=1.4, title=None):
        t = f"<title>{esc(title)}</title>" if title else ""
        self.parts.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{width}">{t}</circle>' if t else
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{width}"/>')
        return self

    def polyline(self, coords, stroke=PRIMARY_HI, width=1.6, dash=None):
        if len(coords) < 2:
            return self
        pts = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in coords)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{stroke}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{d}/>')
        return self

    def path(self, d, fill="none", stroke="none", width=1.0):
        self.parts.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
        return self

    def text(self, x, y, s, size=FS_BODY, fill=INK, anchor="start", weight=400,
             title=None, letter_spacing=None):
        if size < FS_MIN - _EPS:
            raise ValueError(
                f"font-size {size}pt is below the {FS_MIN}pt floor — widen the "
                f"chart or move the label out; never shrink type to fit "
                f"(chart-style.md §type)")
        ls = f' letter-spacing="{letter_spacing}"' if letter_spacing else ""
        t = f"<title>{esc(title)}</title>" if title else ""
        self.parts.append(
            f'<text x="{fmt(x)}" y="{fmt(y)}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}"{ls}>{t}{esc(s)}</text>')
        return self

    # -- furniture -----------------------------------------------------------
    def rail(self, x1, x2, y, ticks=None, tick_h=2.0):
        """A hairline baseline with optional tick posts.

        Sparse clinical series (3–15 points) look impoverished with data alone.
        Density has to come from the furniture — rails, rungs, ticks, ledger
        rules — not from inventing data points. This is the one lieflat lesson
        that matters most for our data shape.
        """
        self.line(x1, y, x2, y, stroke=RULE, width=0.8)
        for tx in (ticks or []):
            self.line(tx, y - tick_h, tx, y, stroke=RULE, width=0.6)
        return self

    def band(self, x1, x2, y_hi, y_lo, fill=BAND):
        """Reference-range band. Drawn UNDER the data, never over it."""
        self.rect(x1, min(y_hi, y_lo), x2 - x1, abs(y_lo - y_hi), fill=fill)
        return self

    # -- output --------------------------------------------------------------
    def markup(self) -> str:
        role = f' role="img" aria-label="{esc(self.label)}"' if self.label else ' role="img"'
        return (f'<svg viewBox="0 0 {fmt(self.w)} {fmt(self.h)}" '
                f'width="{fmt(self.w)}pt" height="{fmt(self.h)}pt" '
                f'preserveAspectRatio="xMidYMid meet" '
                f'xmlns="http://www.w3.org/2000/svg"{role}>'
                + "".join(self.parts) + "</svg>")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page wrapper (channel B)
# ─────────────────────────────────────────────────────────────────────────────
PAGE_CSS = f"""
*{{box-sizing:border-box}}
body{{margin:0;padding:16pt;background:{CARD_ALT};color:{INK};
     font-family:{FONT_STACK};font-size:{FS_BODY}pt;line-height:1.5}}
.card{{background:{CARD};border-radius:6pt;padding:14pt 16pt 12pt;
      max-width:520pt;margin:0 auto}}
h1{{font-size:{FS_TITLE}pt;font-weight:700;margin:0 0 3pt;line-height:1.4}}
.sub{{font-size:{FS_BODY}pt;color:{MUTED_DEEP};margin:0 0 10pt;line-height:1.5}}
.fig{{margin:0 0 8pt}}
.fig svg{{max-width:100%;height:auto;display:block}}
.legend{{font-size:{FS_BODY}pt;color:{MUTED_DEEP};margin:6pt 0 0;
        display:flex;flex-wrap:wrap;gap:4pt 12pt}}
.src{{font-size:{FS_BODY}pt;color:{MUTED};margin-top:9pt;padding-top:7pt;
     border-top:0.6pt solid {RULE};letter-spacing:0.02em}}
.note{{font-size:{FS_BODY}pt;color:{MUTED_DEEP};background:{AMBER_BG};
      border-left:2pt solid {AMBER};padding:6pt 8pt;margin:8pt 0 0;border-radius:3pt}}
@media print{{body{{background:{CARD};padding:0}}.card{{max-width:none}}}}
"""


def page(title: str, reading_note: str, figure_markup: str, legend_items,
         source_line: str, caveats=None) -> str:
    """Wrap a figure into a self-contained, printable, zero-dependency HTML file.

    Card anatomy (four parts, always all four):
      1. title        — the READING GUIDE (what to watch for), never a verdict
      2. subtitle     — units, time span, series legend, comparability warnings
      3. figure       — inline SVG
      4. source line  — where every number came from

    No <script>, no external font, no CDN. The file must render identically
    offline, on a phone, and on paper.
    """
    legend = ""
    if legend_items:
        legend = ('<div class="legend">'
                  + "".join(f"<span>{esc(x)}</span>" for x in legend_items)
                  + "</div>")
    notes = "".join(f'<div class="note">{esc(c)}</div>' for c in (caveats or []))
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN"><head><meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        f"<title>{esc(title)}</title><style>{PAGE_CSS}</style></head><body>"
        f'<div class="card"><h1>{esc(title)}</h1>'
        f'<div class="sub">{esc(reading_note)}</div>'
        f'<div class="fig">{figure_markup}</div>'
        f"{legend}{notes}"
        f'<div class="src">{esc(source_line)}</div>'
        "</div></body></html>\n"
    )
