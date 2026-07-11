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
  (d) No PII — national ID (18-digit) / mobile / landline / email / US-SSN /
      international(E.164) phone, and no PII label (zh 姓名/住院号/门诊号/病案号/检验号/
      报告号/床号/身份证/电话 OR en patient name/MRN/patient id/SSN/phone/...) followed
      by an un-masked value. Runs an unconditional zh∪en∪locale-agnostic union.
  (e) (removed) Precise age is now ALLOWED — clinical-trial matching needs the
      exact age. DOB / birthplace / occupation stay barred upstream (producer +
      pii_rescan), not in this shape gate.
  (f) Skeleton present — .header + .footer + an <h2> for every template section
      (the template always renders every section, even when empty).
  (g) Provenance — the render_html_template.py `template_sha256:` comment is
      present AND equals the SHA-256 of the supplied --template. This proves the
      HTML was machine-rendered from THIS gold-standard template, not hand-written
      (the hard gate in SKILL.md Step 12 requires this `template_sha` in the final
      report). On success the sha is echoed to stdout as `template_sha=<hex>`.
  (h) Print-safe / no-JS floor — the trend charts are inline SVG ONLY. No
      <script>, <canvas>, <foreignObject>, <iframe>, <object>, <embed>, and no
      on*= event-handler attribute may appear. <canvas> silently drops out of the
      Chrome→PDF print path (so a canvas chart would ship blank), and script/
      handlers must never reach a patient-facing file.
  (i) SVG element allowlist — every tag appearing inside an <svg>…</svg> block
      must be one of a small static set (svg/g/path/polyline/line/circle/rect/
      text/title/desc). Catches anything smuggled into the chart markup.

  (j) Core-completeness (OPTIONAL — only when --profile AND --data are supplied;
      absent → skipped, so the validator stays backward-compatible). HARD-FAILS if
      a CORE SINGLETON field is present in source but missing/empty in the rendered
      summary: **stage** (profile.summary.stage OR flat profile.stage vs
      data.stage — the solid one), **driver** (molecular.json variants/
      somatic_variants/drivers vs data.molecular_rows — best-effort), **current
      regimen** (treatment_lines.json lines vs data.treatment_lines — best-effort).
      Deliberately does NOT gate labs/comorbidities — those are curated for a
      one-pager and forcing them would clutter; only always-core singletons.

  (k) line_label auto-ordinal gate (OPTIONAL — only when --data is supplied;
      does NOT need --profile). HARD-FAILS when >=2 treatment_lines[].line_label
      values are BARE sequential Chinese ordinals matching ^[一二三四五六七八九十]+线$
      (一线/二线/三线…), the signature of deriving labels from the `line` integer —
      which the prompt forbids (surgery / neoadjuvant mislabeled as a numbered
      "line" is clinically wrong; intent labels 新辅助/维持/姑息… must be used). The
      >=2 threshold spares a single legitimately-verbatim "姑息一线"/"一线" from the
      record. Skips when --data absent / unreadable / has no treatment_lines.

  Note: the anti-fabrication numeric-integrity gate (every plotted point must
  exist in longitudinal_observations.json) lives in compute_sparklines.py, not
  here — this validator only sees normalized pixel coordinates, from which the raw
  clinical values cannot be recovered. SKILL.md Step 12 wires that gate in.

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
import json
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

# (d) PII patterns — deterministic text-only residue checks
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

# English / Latin PII labels (colon-MANDATORY — single Latin words appear in
# ordinary prose, so a real colon is required to avoid false-firing).
_PII_LABEL_EN = (
    r"(?i)(?:patient\s*name|pt\.?\s*name|mrn|medical\s*record\s*(?:no\.?|number|#)?"
    r"|patient\s*id|account\s*(?:no\.?|number|#)?|ssn|social\s*security(?:\s*(?:no\.?|number))?"
    r"|phone|mobile|cell(?:\s*phone)?|telephone|tel|fax|admission\s*(?:no\.?|number|id)"
    r"|encounter\s*(?:no\.?|id)|visit\s*(?:no\.?|id)|chart\s*(?:no\.?|number)|bed(?:\s*(?:no\.?|number|#))?)"
)
_PII_LABEL_EN_VALUE_RE = re.compile(_PII_LABEL_EN + r"\s*[:：]\s*([0-9A-Za-z][0-9A-Za-z.\-@]{2,})")

# Locale-agnostic high-precision standalone identifiers.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_INTL_PHONE_RE = re.compile(r"(?<![\w+])\+\d[\d\s().-]{6,}\d")
_US_PHONE_RE = re.compile(r"(?<!\d)\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")

# (e) precise age is intentionally NOT guarded here anymore — the case summary now
#     retains the exact age (clinical-trial matching needs it). DOB / birthplace /
#     occupation remain barred, enforced upstream at the producer + pii_rescan.
#     The sibling validate_visit_prep_html.py dropped the same guard in the same
#     change, so the two remain ALIGNED (both age-permissive, DOB still barred). Do
#     NOT re-add an exact-age guard to either without doing the same to the other.

# (g) provenance comment emitted by render_html_template.py
_PROVENANCE_RE = re.compile(r"template_sha256:\s*([0-9a-f]{64})", re.IGNORECASE)

# (h) print-safe / no-JS floor — tags/attrs that must NEVER appear in the output.
_FORBIDDEN_TAG_RE = re.compile(
    r"<\s*(script|canvas|foreignobject|iframe|object|embed|applet|form)\b", re.IGNORECASE
)
_EVENT_HANDLER_RE = re.compile(r"<[^>]*?\son[a-z]+\s*=", re.IGNORECASE)

# (i) SVG element allowlist — tags permitted inside an <svg>…</svg> block.
_SVG_BLOCK_RE = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)
_TAG_NAME_RE = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9]*)")
_SVG_ALLOWED = {"svg", "g", "path", "polyline", "polygon", "line", "circle",
                "ellipse", "rect", "text", "tspan", "title", "desc", "defs",
                "lineargradient", "radialgradient", "stop"}

# Skeleton classes that the template *always* renders (patient-independent).
_REQUIRED_CLASSES = ("header", "page-footer")


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
    for m in _PII_LABEL_EN_VALUE_RE.finditer(scan):
        if "[PII_MASKED]" in m.group(0):
            continue
        frag = m.group(0).replace("\n", " ")
        errors.append(f"(d) PII: en label followed by un-masked value: {frag!r}")
    if _EMAIL_RE.search(scan):
        errors.append("(d) PII: email-address pattern present")
    if _SSN_RE.search(scan):
        errors.append("(d) PII: US SSN pattern present")
    if _INTL_PHONE_RE.search(scan):
        errors.append("(d) PII: international/E.164 phone pattern present")
    if _US_PHONE_RE.search(scan):
        errors.append("(d) PII: US phone-number pattern present")

    # (e) precise age is now ALLOWED — clinical-trial matching needs the exact age.
    # Only DOB/birthplace/occupation stay barred, and those are enforced upstream
    # (case-summary-html-prompt.md producer rules + pii_rescan PII scan), not here.
    # The former \d{1,3}岁 / "<n> years old" guard was removed intentionally.

    # (h) print-safe / no-JS floor — scan the RAW html (not comment-stripped: a
    # forbidden tag hidden in a comment is still suspicious, but the template's
    # authoring comments are inert; we scan body_no_comments to avoid flagging
    # scaffold notes while still catching any real emitted tag).
    ft = _FORBIDDEN_TAG_RE.search(body_no_comments)
    if ft:
        errors.append(f"(h) forbidden tag <{ft.group(1).lower()}> present — charts must be inline SVG only (no script/canvas/embed)")
    eh = _EVENT_HANDLER_RE.search(body_no_comments)
    if eh:
        frag = eh.group(0)[:40].replace("\n", " ")
        errors.append(f"(h) inline event-handler attribute present: {frag!r}")

    # (i) SVG element allowlist
    for block in _SVG_BLOCK_RE.findall(body_no_comments):
        for tag in _TAG_NAME_RE.findall(block):
            if tag.lower() not in _SVG_ALLOWED:
                errors.append(f"(i) disallowed element <{tag}> inside <svg> block")
                break

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


# --- (j) core-completeness gate (optional; needs --profile + --data) ----------
# Shape checks (a)-(i) intentionally never assert that clinical content exists,
# because most sections are curated 0..N (a patient with no labs legitimately has
# none). But a few CORE SINGLETON fields are ALWAYS-present when the source has
# them — dropping them silently is a correctness failure, not a one-pager choice.
# This gate (only when --profile + --data are supplied) HARD-FAILS if such a field
# is present in source but missing/empty in the rendered summary. It deliberately
# does NOT gate labs/comorbidities (those are curated — forcing them would clutter).


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _truthy(v) -> bool:
    """A source value counts as present unless it's None/empty/placeholder."""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() not in ("", "null", "None", "资料缺失")
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def core_completeness_check(profile_path: str | None, data_path: str | None, errors: list[str]) -> None:
    """Optional gate: if a CORE SINGLETON field is present in source but absent from
    the rendered summary data, HARD-FAIL. Absent args (or unreadable files) → skip,
    so the validator stays backward-compatible when called without --profile/--data."""
    if not profile_path or not data_path:
        return
    profile = _load_json(Path(profile_path))
    data = _load_json(Path(data_path))
    if not isinstance(profile, dict) or not isinstance(data, dict):
        return  # best-effort: can't read one of them → skip the gate, don't crash

    # stage (the SOLID one): profile.summary.stage OR flat profile.stage.
    summary = profile.get("summary") if isinstance(profile.get("summary"), dict) else {}
    src_stage = summary.get("stage") if _truthy(summary.get("stage")) else profile.get("stage")
    if _truthy(src_stage) and not _truthy(data.get("stage")):
        errors.append("(j) core field 分期 present in source but absent from summary")

    # driver (best-effort): molecular.json sibling of the profile.
    mol = _load_json(Path(profile_path).parent / "molecular.json")
    if isinstance(mol, dict):
        has_variants = any(
            isinstance(mol.get(k), list) and mol.get(k)
            for k in ("variants", "somatic_variants", "drivers")
        )
        if has_variants and not _truthy(data.get("molecular_rows")):
            errors.append(
                "(j) core field 驱动基因 present in source (molecular.json variants/"
                "somatic_variants/drivers) but molecular_rows empty in summary"
            )

    # current regimen (best-effort): treatment_lines.json sibling of the profile.
    tl = _load_json(Path(profile_path).parent / "treatment_lines.json")
    if isinstance(tl, dict) and tl.get("lines") and not _truthy(data.get("treatment_lines")):
        errors.append(
            "(j) core field 当前方案 present in source (treatment_lines.json lines) "
            "but treatment_lines empty in summary"
        )


# --- (k) line_label auto-ordinal gate (optional; needs --data) ----------------
# Fix 3b: the case-summary-html-prompt forbids deriving 一线/二线/三线 line labels
# from the `line` integer (surgery / neoadjuvant mislabeled as "lines" is
# clinically wrong; intent labels 新辅助/维持/姑息… or neutral 第N段治疗 must be
# used instead). A real regression produced 一线…十二线. This deterministic gate
# HARD-FAILS when >=2 treatment_lines[].line_label values are BARE sequential
# Chinese ordinals matching ^[一二三四五六七八九十]+线$ — the signature of
# auto-derivation. The >=2 threshold means a SINGLE legitimately-verbatim
# "姑息一线"/"一线" copied from the record does NOT false-positive. Backward-
# compatible: skips when --data is absent, unreadable, or has no treatment_lines.
_BARE_ORDINAL_LINE_RE = re.compile(r"^[一二三四五六七八九十]+线$")


def line_label_ordinal_check(data_path: str | None, errors: list[str]) -> None:
    if not data_path:
        return
    data = _load_json(Path(data_path))
    if not isinstance(data, dict):
        return  # unreadable / not an object → skip (backward-compatible)
    lines = data.get("treatment_lines")
    if not isinstance(lines, list) or not lines:
        return  # no treatment_lines → nothing to gate
    ordinals = [
        item["line_label"]
        for item in lines
        if isinstance(item, dict)
        and isinstance(item.get("line_label"), str)
        and _BARE_ORDINAL_LINE_RE.match(item["line_label"].strip())
    ]
    if len(ordinals) >= 2:
        errors.append(
            "(k) line_label 疑似自动序数派生(一线/二线…),违反 intent-based 规则: "
            + ", ".join(ordinals)
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html", required=True, help="rendered case-summary HTML to validate")
    ap.add_argument("--template", required=True, help="case-summary.template.html baseline")
    ap.add_argument("--profile", help="patient profile.json — enables the (j) core-completeness gate")
    ap.add_argument("--data", help=".case_summary_data.json render data — enables the (j) core-completeness gate")
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
    # (j) optional core-completeness gate — only runs when both --profile and --data
    # are supplied (backward-compatible: absent → skipped entirely).
    core_completeness_check(args.profile, args.data, errors)
    # (k) line_label auto-ordinal gate — runs whenever --data is supplied (does not
    # require --profile), skips otherwise. Backward-compatible.
    line_label_ordinal_check(args.data, errors)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Echo the provenance sha so the SKILL.md Step 12 hard-gate report can quote it.
    print(f"case-summary HTML OK — shape invariants hold ({html_path}) template_sha={template_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
