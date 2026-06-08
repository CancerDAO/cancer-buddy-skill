#!/usr/bin/env python3
"""Validate a rendered 病情简要总结 case-summary HTML against its template.

This checks **shape invariants only** — properties that are fixed by the template
and independent of which patient was rendered. It NEVER asserts that any specific
clinical content exists (e.g. "must have N labs", "must have a .lab-grid"), because
the renderer is a 0..N data-driven engine: a patient with no labs legitimately has
no .lab-item, and a section with no data renders a "资料缺失" placeholder rather
than disappearing. Asserting content existence would false-positive on real
patients, so we only assert form.

Checks:
  (a) The output <style> block is byte-for-byte identical to the template <style>.
  (b) Every CSS class used in the output is a subset of the template's class set
      (catches hand-authored / hallucinated CSS classes).
  (c) After stripping HTML comments, no residual `{{` placeholder remains.
  (d) No PII — national ID (18-digit) / mobile (1[3-9]\\d{9}) / landline, and no
      PII label (姓名/住院号/门诊号/病案号/检验号/报告号/床号/身份证/电话/...)
      followed by an un-masked number.
  (e) No precise age — \\d{1,3}\\s*岁.
  (f) Skeleton present — .header + .footer + an <h2> for every template section
      (the template always renders every section, even when empty).
  (g) Provenance — the render_html_template.py `template_sha256:` comment is
      present AND equals the SHA-256 of the supplied --template. This proves the
      HTML was machine-rendered from THIS gold-standard template, not hand-written
      (the hard gate in SKILL.md Step 12 requires this `template_sha` in the final
      report). On success the sha is echoed to stdout as `template_sha=<hex>`.

Any failed check exits non-zero.

Usage:
    python3 scripts/validate_case_summary_html.py --html OUT.html --template TMPL.html

Exit codes:
    0  — all shape invariants hold
    1  — at least one invariant failed
    2  — bad invocation / unreadable input
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# --- regexes ---------------------------------------------------------------

_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# class="a b c" or class='a b c'
_CLASS_ATTR_RE = re.compile(r"""\bclass\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
# class selectors inside a <style> block: .foo, .foo.bar (each token captured)
_CSS_CLASS_RE = re.compile(r"\.([A-Za-z_][\w-]*)")
_H2_RE = re.compile(r"<h2\b", re.IGNORECASE)

# (d) PII patterns — mirror redact_ocr.py standalone patterns
_ID_CARD_RE = re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]")
_MOBILE_RE = re.compile(r"1[3-9]\d{9}")
_LANDLINE_RE = re.compile(r"0\d{2,3}[-\s]?\d{7,8}")

# PII label followed by an un-masked value (digits / digit-ish id). The value may
# sit immediately after the label or be separated by a colon / whitespace. We only
# flag when an actual number follows — a masked label like "住院号：[PII_MASKED]"
# is fine.
_PII_LABEL = (
    r"(?:姓\s*名|身份证号?码?|住院号|住院病历号|病历号|病案号|门诊号|就诊号|就诊卡号"
    r"|检验号|检验单号|报告号|报告单号|样本号|标本号|床\s*号|病\s*床|床\s*位"
    r"|电\s*话|手\s*机|联系电话|联系方式)"
)
_PII_LABEL_VALUE_RE = re.compile(_PII_LABEL + r"\s*[:：]?\s*([0-9][0-9A-Za-z\-]{2,})")

# (e) precise age
_AGE_RE = re.compile(r"\d{1,3}\s*岁")

# (g) provenance comment emitted by render_html_template.py
_PROVENANCE_RE = re.compile(r"template_sha256:\s*([0-9a-f]{64})", re.IGNORECASE)

# Skeleton classes that the template *always* renders (patient-independent).
_REQUIRED_CLASSES = ("header", "footer")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_style(html: str) -> str | None:
    m = _STYLE_RE.search(html)
    return m.group(1) if m else None


def _used_classes(html: str) -> set[str]:
    """All classes appearing in class="..." attributes."""
    used: set[str] = set()
    for m in _CLASS_ATTR_RE.finditer(html):
        for tok in m.group(1).split():
            if tok:
                used.add(tok)
    return used


def _template_classes(style_block: str) -> set[str]:
    """All class names declared as selectors in the template <style> block."""
    return set(_CSS_CLASS_RE.findall(style_block))


def _strip_comments(html: str) -> str:
    return _COMMENT_RE.sub("", html)


def check(html: str, template: str, errors: list[str]) -> str | None:
    """Run shape invariants; append failures to `errors`. Returns the
    template_sha extracted from the HTML provenance comment (or None)."""
    tmpl_style = _extract_style(template)
    out_style = _extract_style(html)

    # (g) provenance — extract template_sha early so we can return it even when
    # later style checks short-circuit. Proves the HTML was machine-rendered from
    # THIS template (the SKILL.md Step 12 hard gate needs this in its report).
    pm = _PROVENANCE_RE.search(html)
    template_sha = pm.group(1).lower() if pm else None
    if template_sha is None:
        errors.append(
            "(g) provenance missing — no `template_sha256:` comment; HTML may be "
            "hand-written rather than rendered via render_html_template.py"
        )
    else:
        expected = _sha256(template)
        if template_sha != expected:
            errors.append(
                f"(g) provenance mismatch — HTML template_sha256={template_sha} "
                f"but supplied --template hashes to {expected}; HTML not rendered "
                "from THIS template"
            )

    if tmpl_style is None:
        errors.append("template has no <style> block — cannot establish baseline")
        return template_sha
    if out_style is None:
        errors.append("(a) output has no <style> block")
        return template_sha

    # (a) byte-for-byte identical <style>
    if out_style != tmpl_style:
        errors.append(
            "(a) output <style> differs from template <style> (must be byte-identical)"
        )

    tmpl_classes = _template_classes(tmpl_style)

    # (b) used classes ⊆ template classes
    used = _used_classes(html)
    rogue = sorted(c for c in used if c not in tmpl_classes)
    if rogue:
        errors.append(
            "(b) output uses CSS class(es) absent from template: " + ", ".join(rogue)
        )

    # (c) no residual {{ after stripping comments
    body_no_comments = _strip_comments(html)
    if "{{" in body_no_comments:
        # find a small context window for the first occurrence
        idx = body_no_comments.find("{{")
        snippet = body_no_comments[idx : idx + 40].replace("\n", " ")
        errors.append(f"(c) residual unrendered placeholder: …{snippet!r}")

    # PII / age checks run on comment-stripped content (template comments carry
    # label words / examples that are scaffold, not patient data).
    scan = body_no_comments

    # (d) PII
    if _ID_CARD_RE.search(scan):
        errors.append("(d) PII: 18-digit national ID pattern present")
    if _MOBILE_RE.search(scan):
        errors.append("(d) PII: mobile-number pattern 1[3-9]\\d{9} present")
    if _LANDLINE_RE.search(scan):
        errors.append("(d) PII: landline-number pattern present")
    for m in _PII_LABEL_VALUE_RE.finditer(scan):
        if "[PII_MASKED]" in m.group(0):
            continue
        frag = m.group(0).replace("\n", " ")
        errors.append(f"(d) PII: label followed by un-masked value: {frag!r}")

    # (e) precise age
    am = _AGE_RE.search(scan)
    if am:
        errors.append(f"(e) precise age present: {am.group(0)!r}")

    # (f) skeleton present
    for cls in _REQUIRED_CLASSES:
        if cls not in used:
            errors.append(f"(f) skeleton missing required class .{cls}")
    # one <h2> per template section. The template emits exactly one <h2> per
    # section and always renders every section, so the output's <h2> count must
    # be >= the template's (extra would be a rogue, but that's content not shape
    # — we only require the full skeleton is present).
    tmpl_h2 = len(_H2_RE.findall(_strip_comments(template)))
    out_h2 = len(_H2_RE.findall(body_no_comments))
    if out_h2 < tmpl_h2:
        errors.append(
            f"(f) skeleton missing section <h2> headers: "
            f"template has {tmpl_h2}, output has {out_h2}"
        )

    return template_sha


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html", required=True, help="rendered case-summary HTML to validate")
    ap.add_argument("--template", required=True, help="case-summary.template.html baseline")
    args = ap.parse_args()

    html_path = Path(args.html)
    tmpl_path = Path(args.template)
    for p, name in ((html_path, "--html"), (tmpl_path, "--template")):
        if not p.is_file():
            print(f"ERROR: {name} not a file: {p}", file=sys.stderr)
            return 2

    try:
        html = _read(html_path)
        template = _read(tmpl_path)
    except Exception as e:
        print(f"ERROR: cannot read input: {e}", file=sys.stderr)
        return 2

    errors: list[str] = []
    template_sha = check(html, template, errors)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Echo the provenance sha so the SKILL.md Step 12 hard-gate report can quote it.
    print(f"case-summary HTML OK — shape invariants hold ({html_path}) template_sha={template_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
