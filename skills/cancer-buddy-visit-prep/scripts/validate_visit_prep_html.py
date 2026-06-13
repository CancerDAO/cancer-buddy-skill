#!/usr/bin/env python3
"""Form-invariant validator for a rendered 就诊准备包.html (visit-prep pack).

This validator checks ONLY *form* invariants — properties that are fixed by the
template and are INDEPENDENT of which patient was rendered. It deliberately makes
**no content-existence assertions**: it never requires a `.lab-grid`, a confirm
question, a treatment line, or any data-bearing element to be present. A patient
with zero labs / zero review-flags / zero changes is a perfectly valid pack, and
asserting "must contain X" would falsely fail them. Over-fitting to one patient's
shape is therefore structurally avoided.

What it asserts (all derived from the template at runtime, nothing patient-specific):

  1. STYLE byte-exact      — the rendered <style>…</style> block is byte-for-byte
                             identical to the template's. (Catches any hand-edited
                             CSS / a hand-written HTML that didn't come from the
                             template + renderer.)
  2. CLASS ⊆ template      — every class token used in the rendered HTML is one the
                             template declares. (Catches injected/hand-authored
                             markup with novel classes.)
  3. NO residual markers   — no live `{{…}}` placeholder and no LOOP / RENDER_IF /
                             RENDER_IF_NOT / END marker comment survived rendering.
  4. NO PII                — no 18-digit national ID, CN mobile/landline, US SSN,
                             international(E.164)/US phone, email, or explicit
                             birth-date leaked into a patient-visible artifact.
                             (Locale-independent deterministic patterns only —
                             never a name allow/deny list; zh∪en∪locale-agnostic
                             union runs unconditionally.)
  5. NO exact age          — no `<n>岁` / `aged <n>` / `<n> years old` / `<n> yo`
                             precise age; only decade bands (e.g. 50+) allowed.
  6. SKELETON present       — the template's fixed, patient-independent scaffold is
                             intact: header div, footer div, snapshot-box div, and
                             at least the snapshot + questions + bring <h2> sections.

Usage:
    python3 scripts/validate_visit_prep_html.py <rendered.html> [template.html]

If [template.html] is omitted it defaults to
    <skill>/references/templates/visit-prep.template.html

Exit codes:
    0  — all form invariants hold
    1  — at least one invariant violated
    2  — bad invocation / unreadable input
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_TEMPLATE = SKILL_DIR / "references" / "templates" / "visit-prep.template.html"

STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
CLASS_ATTR_RE = re.compile(r'class\s*=\s*"([^"]*)"')
PLACEHOLDER_RE = re.compile(r"\{\{\s*[A-Za-z0-9_.\-]+\s*\}\}")
MARKER_RE = re.compile(
    r"<!--\s*(?:LOOP|END\s+LOOP|RENDER_IF|RENDER_IF_NOT|END\s+RENDER_IF)\b",
    re.IGNORECASE,
)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# --- PII / exact-age red-flag patterns (deterministic, locale-independent) ----
# Unconditional zh∪en∪locale-agnostic union — a residue gate must over-detect, so
# every pattern fires regardless of the pack's locale.
PII_PATTERNS = [
    ("national_id_18", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("mobile_11", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("landline_cn", re.compile(r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("ssn_us", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("phone_intl", re.compile(r"(?<![\w+])\+\d[\d\s().\-]{6,}\d")),
    ("phone_us", re.compile(r"(?<!\d)\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")),
    ("birth_date", re.compile(r"(?:出生|生于|出生日期|date of birth|DOB|born|birth\s*date)\D{0,6}\d{4}\D?\d{1,2}\D?\d{1,2}", re.IGNORECASE)),
]
# Exact age: "<n>岁" / "aged 47" / "age 47" / "47 years old" / "47 yo" — but allow
# decade bands like "50+".
EXACT_AGE_PATTERNS = [
    ("age_sui", re.compile(r"(?<!\d)\d{1,3}\s*岁")),
    ("age_en", re.compile(r"\bage[d]?\s*[:：]?\s*\d{1,3}\b(?!\s*\+)", re.IGNORECASE)),
    ("age_years_old", re.compile(r"\b\d{1,3}\s*(?:years?\s*old|yrs?\s*old|y/?o)\b", re.IGNORECASE)),
]


def extract_style(text: str) -> str | None:
    m = STYLE_RE.search(text)
    return m.group(0) if m else None


def class_universe(text: str) -> set[str]:
    classes: set[str] = set()
    for m in CLASS_ATTR_RE.finditer(text):
        for tok in m.group(1).split():
            # template loop bodies may carry a {{lab_class}}-style placeholder; the
            # rendered side never should, but skip placeholder tokens defensively.
            if "{{" in tok:
                continue
            classes.add(tok)
    return classes


def visible_text(html: str) -> str:
    """HTML with comments and tags stripped — what a reader actually sees.
    Used for PII / age scans so we don't false-positive on template comments."""
    no_comments = COMMENT_RE.sub("", html)
    no_style = STYLE_RE.sub("", no_comments)
    return re.sub(r"<[^>]+>", " ", no_style)


def main() -> int:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("usage: validate_visit_prep_html.py <rendered.html> [template.html]", file=sys.stderr)
        return 2

    rendered_path = Path(sys.argv[1]).resolve()
    template_path = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else DEFAULT_TEMPLATE

    try:
        rendered = rendered_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot read rendered HTML {rendered_path}: {e}", file=sys.stderr)
        return 2
    try:
        template = template_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot read template {template_path}: {e}", file=sys.stderr)
        return 2

    errors: list[str] = []

    # 1. STYLE byte-exact -----------------------------------------------------
    tpl_style = extract_style(template)
    out_style = extract_style(rendered)
    if tpl_style is None:
        errors.append("template has no <style> block — cannot establish style baseline")
    elif out_style is None:
        errors.append("rendered HTML has no <style> block")
    elif out_style != tpl_style:
        errors.append(
            "style block is NOT byte-identical to the template "
            "(CSS was hand-edited or HTML was not produced by the renderer)"
        )

    # 2. CLASS ⊆ template -----------------------------------------------------
    tpl_classes = class_universe(template)
    out_classes = class_universe(rendered)
    novel = sorted(out_classes - tpl_classes)
    if novel:
        errors.append(
            "rendered HTML uses class(es) not declared in the template: "
            + ", ".join(novel)
        )

    # 3. NO residual markers --------------------------------------------------
    rendered_no_comments = COMMENT_RE.sub("", rendered)
    residual_ph = sorted(set(PLACEHOLDER_RE.findall(rendered_no_comments)))
    if residual_ph:
        errors.append("residual {{…}} placeholder(s) survived: " + ", ".join(residual_ph))
    residual_markers = MARKER_RE.findall(rendered)
    if residual_markers:
        errors.append(f"{len(residual_markers)} LOOP/RENDER_IF marker comment(s) survived rendering")

    # 4. NO PII ---------------------------------------------------------------
    vtext = visible_text(rendered)
    for name, pat in PII_PATTERNS:
        m = pat.search(vtext)
        if m:
            errors.append(f"possible PII leak [{name}]: {m.group(0)!r}")

    # 5. NO exact age ---------------------------------------------------------
    for name, pat in EXACT_AGE_PATTERNS:
        m = pat.search(vtext)
        if m:
            errors.append(f"exact age leaked [{name}]: {m.group(0)!r} (only decade bands like 50+ allowed)")

    # 6. SKELETON present -----------------------------------------------------
    for cls, label in (
        ("header", "header div"),
        ("footer", "footer div"),
        ("snapshot-box", "snapshot-box div"),
    ):
        # tolerant of extra classes / order: class="... <cls> ..."
        if not re.search(r'<div class="[^"]*\b' + re.escape(cls) + r'\b[^"]*"', rendered):
            errors.append(f"missing template skeleton: {label}")
    h2_count = len(re.findall(r"<h2\b", rendered))
    # snapshot + questions + bring always render (block 4 is followup-only) → ≥ 3.
    if h2_count < 3:
        errors.append(f"expected ≥3 always-on <h2> sections, found {h2_count}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"FAIL: {len(errors)} form-invariant violation(s) in {rendered_path.name}", file=sys.stderr)
        return 1

    print(f"visit-prep HTML form-invariants OK ({rendered_path.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
