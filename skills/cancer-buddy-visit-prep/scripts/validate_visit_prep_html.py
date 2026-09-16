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
  5. CONTEXTUAL MINIMIZATION — age and other quasi-identifiers have no reliable
                             universal regex rule. This form validator does not
                             declare them safe; the producer must include them
                             only when necessary and authorized.
  6. SKELETON present       — the template's fixed, patient-independent scaffold is
                             intact: header div, footer div, snapshot-box div, and
                             at least the snapshot + questions + bring <h2> sections.
  7. NO internal_qc LEAK    — the 「请医生确认」 box (.q-confirm) and the 医生速览 box
                             (.snapshot-box) carry no internal_qc marker: `读数1` /
                             `读数2` (two parallel candidate readings), the machine
                             tokens `needs_human_review` / `internal_qc` / the four
                             internal_qc categories. organize v3 routes those flags
                             to review_flags.md, never to the doctor-facing surface.
                             This is a *region-scoped* denylist — it says nothing
                             about the rest of the document, and it asserts no
                             content must EXIST (rule: never over-fit one patient).
  8. internal_qc COLLAPSED  — if the sibling `.visit_prep_data.json` declares
                             `internal_qc_count > 0` (or a non-empty
                             `internal_qc_flags[]`), the rendered HTML must carry
                             the collapsed `.qc-note` line and show that same
                             count. An internal_qc flag that is neither shown as a
                             collapsed line nor routed to the doctor is silently
                             dropped — that is the failure this catches.
  9. NO forbidden read      — the data JSON must not mention
                             `open_verification_status` or `extracted_fields`
                             anywhere (key or value). `open_verification_status`
                             belongs to organize's `extracted_fields.json`
                             open-fields surface, which visit-prep may never read;
                             its presence here is direct evidence the consumer
                             read a file it is not on the reader list for. It is
                             also a DIFFERENT field from the structured-JSON
                             `verification_status` (`unverified` /
                             `clinician_verified` / `disputed` / `withdrawn`, the
                             last only on `timeline.json` events), with a different
                             value domain; confusing the two is the bug this
                             catches.
 10. ADMISSION BASIS        — if the data declares the optional audit array
                             `snapshot_admission[]`, every entry is checked: the
                             `basis` is from the fixed enum, an admitting basis
                             matches `admitted: true` (and a blocking one
                             `admitted: false` + a `null` snapshot cell), a
                             per-field `high_risk_fields` basis carries its
                             `label`, and the legacy bases require
                             `legacy_flag_fallback: true`. Crucially: when the
                             inventory row HAS `high_risk_fields[]`, the cell must
                             be decided by that array — declaring the row-level
                             `high_risk_review_status` basis while
                             `high_risk_fields_present` is true is an ERROR (the
                             row-level value is a derived summary and kills
                             sibling fields that did pass their second read).
                             Absent the array, the A13 legacy row-level basis is
                             allowed and must be flagged as a fallback. A declared
                             audit array must also cover every populated snapshot
                             cell — omitting one would leave it unaudited.

Usage:
    python3 scripts/validate_visit_prep_html.py <rendered.html> [template.html]
                                                [--data <.visit_prep_data.json>]
                                                [--allow-token TOKEN]...
    python3 scripts/validate_visit_prep_html.py --help

If [template.html] is omitted it defaults to
    <skill>/references/templates/visit-prep.template.html
If --data is omitted the validator looks for `.visit_prep_data.json` next to the
rendered HTML; if that file does not exist, checks 8-10 are reported as SKIPPED
(not a failure) so a stand-alone HTML can still be shape-checked. Passing --data
explicitly makes the file mandatory. Check 10 is additionally skipped when the
data carries no `snapshot_admission[]` — the audit array is optional, but a
declared one is held to the full contract.

--allow-token whitelists one denylist token for check 7. Use sparingly and only
for a clinically real string; it can never whitelist `needs_human_review` or any
other machine token.

Exit codes:
    0  — all form invariants hold
    1  — at least one invariant violated
    2  — bad invocation / unreadable input
"""
from __future__ import annotations

import argparse
import json
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
# Age and quasi-identifiers require contextual minimization and combination-risk
# review. A shape regex cannot decide whether age is necessary or identifying, so
# this validator neither requires nor categorically permits it. DOB retains a
# high-precision shape guard; semantic review covers the wider context.


# --- internal_qc leakage denylist (check 7) ---------------------------------
# organize v3 routes `review_flags[].audience == internal_qc` to review_flags.md
# and a single collapsed patient-facing line. None of these markers may surface in
# the doctor-facing regions. Tokens are matched case-insensitively on the VISIBLE
# text of the region only (comments/tags stripped), so template authoring notes
# and CSS class names never trip it.
INTERNAL_QC_TOKENS = [
    "读数1",
    "读数2",
    "读数 1",
    "读数 2",
    "needs_human_review",
    "internal_qc",
    "transcription_disagreement",
    "ocr_artifact",
    "untrusted_content_marker",
    "pii_semantic_deferred",
]
# One entry was removed here (fix spec B15): the bone-cement polymer abbreviation
# used to sit in this list as a "transcription-noise" string, but it is a REAL
# clinical term that a spine/ortho record legitimately prints, so it fired on correct
# documents and had to be escaped with --allow-token. A denylist whose intended use
# requires a per-patient waiver is a false-positive generator, not an internal_qc leak
# detector. What remains are machine tokens organize never writes into clinical prose.
# Never whitelistable: these are machine tokens that cannot be a real clinical string.
UNWAIVABLE_TOKENS = {
    "needs_human_review",
    "internal_qc",
    "transcription_disagreement",
    "ocr_artifact",
    "untrusted_content_marker",
    "pii_semantic_deferred",
}

# Doctor-facing regions scanned by check 7: (class, human label).
DOCTOR_FACING_REGIONS = [
    ("q-confirm", "「请医生确认」box"),
    ("snapshot-box", "医生速览 box"),
]

QC_NOTE_CLASS_RE = re.compile(r'<div class="[^"]*\bqc-note\b[^"]*"')

# --- forbidden-read markers in the data JSON (check 9) -----------------------
# visit-prep is NOT on the reader list for organize's `extracted_fields.json`
# (only the 段 2 `open_fields_filing` group writes/reads it). `open_verification_status`
# is that file's own status field, with its own value domain, and is easy to confuse
# with the structured-JSON `verification_status`
# (`unverified|clinician_verified|disputed`). Either string appearing in the data a
# consumer produced is direct evidence of a forbidden read.
FORBIDDEN_DATA_MARKERS = [
    "open_verification_status",
    "extracted_fields",
]

# --- snapshot admission basis enum (check 10) --------------------------------
SNAPSHOT_CELLS = {
    "snapshot_diagnosis",
    "snapshot_molecular",
    "snapshot_current_line",
    "snapshot_key_labs",
}
# basis -> (admits?, requires_label?, requires_legacy_fallback?)
ADMISSION_BASES = {
    "verification_status==clinician_verified": (True, False, False),
    "high_risk_fields.status==passed_independent_reread": (True, True, False),
    "legacy_v2_unverified": (True, False, True),
    "legacy_row_level_high_risk_review_status": (None, False, True),
    "high_risk_fields.status==needs_human_review": (False, True, False),
    "verification_status==disputed": (False, False, False),
    # timeline-only; a retracted event never admits a value (see VERIFICATION_STATUS_VALUES)
    "verification_status==withdrawn": (False, False, False),
    "no_value": (False, False, False),
}
# The only `verification_status` values that exist on the consumer side. Anything
# else in a basis string means the producer read some other status field.
#
# `withdrawn` is real but NARROW: only `timeline.json`'s event rows carry it
# (timeline.schema.json), where it marks an event the source itself retracted. The
# other structured JSONs have the three-value enum. It is listed here so that a
# basis string naming it is not rejected as a typo, but it NEVER admits a value:
# a retracted event is not evidence, so any snapshot cell resting on it renders
# `val_pending` exactly as `disputed` does.
VERIFICATION_STATUS_VALUES = ("unverified", "clinician_verified", "disputed", "withdrawn")


def extract_div_regions(html: str, cls: str) -> list[str]:
    """Every <div class="… cls …">…</div> region, depth-balanced on <div>/</div>.

    Returns raw HTML slices. An unbalanced document simply yields a region that
    runs to EOF, which still gets scanned — fail-closed, never fail-silent.
    """
    open_re = re.compile(r'<div\b[^>]*class="[^"]*\b' + re.escape(cls) + r'\b[^"]*"[^>]*>', re.IGNORECASE)
    tag_re = re.compile(r"</?div\b", re.IGNORECASE)
    regions: list[str] = []
    for m in open_re.finditer(html):
        depth = 0
        end = len(html)
        for tm in tag_re.finditer(html, m.start()):
            depth += 1 if tm.group(0).lower() == "<div" else -1
            if depth == 0:
                end = tm.end() + html[tm.end():].find(">") + 1
                break
        regions.append(html[m.start():end])
    return regions


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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="validate_visit_prep_html.py",
        description=(
            "Form-invariant validator for a rendered 就诊准备包.html. Checks only "
            "template-fixed, patient-independent invariants (style/classes/markers/"
            "PII/skeleton) plus the organize-v3 internal_qc routing gate: no "
            "internal_qc marker in the doctor-facing regions, and an internal_qc "
            "flag count that is declared in the data must appear as the collapsed line. "
            "It also refuses a data file that mentions extracted_fields / "
            "open_verification_status (a forbidden read) and, when snapshot_admission[] "
            "is declared, that each snapshot cell was admitted per-field from "
            "high_risk_fields[] rather than from the row-level summary."
        ),
        epilog=(
            "exit 0 = all invariants hold | exit 1 = violation | exit 2 = bad "
            "invocation. It never asserts that specific clinical content EXISTS: a "
            "patient with zero labs / zero review_flags is a valid pack."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("rendered", metavar="rendered.html", help="the rendered visit-prep pack to check")
    ap.add_argument(
        "template", metavar="template.html", nargs="?", default=None,
        help="template to compare against (default: <skill>/references/templates/visit-prep.template.html)",
    )
    ap.add_argument(
        "--data", metavar="PATH", default=None,
        help=(".visit_prep_data.json backing this render. Default: the sibling file "
              "next to rendered.html; if absent, check 8 is SKIPPED. Passing it "
              "explicitly makes the file mandatory."),
    )
    ap.add_argument(
        "--allow-token", metavar="TOKEN", action="append", default=[],
        help=("whitelist one internal_qc denylist token for check 7 (repeatable). "
              "Machine tokens such as needs_human_review can never be whitelisted."),
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    rendered_path = Path(args.rendered).resolve()
    template_path = Path(args.template).resolve() if args.template else DEFAULT_TEMPLATE
    data_explicit = args.data is not None
    data_path = Path(args.data).resolve() if data_explicit else rendered_path.parent / ".visit_prep_data.json"

    waived = {tok for tok in args.allow_token if tok not in UNWAIVABLE_TOKENS}
    refused = sorted(set(args.allow_token) & UNWAIVABLE_TOKENS)

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

    # 5. Context-dependent age/quasi-identifier minimization is enforced by the
    #    producer's authorization + semantic review, not by a universal regex.

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

    # 7. NO internal_qc LEAK into the doctor-facing regions --------------------
    if refused:
        errors.append(
            "--allow-token refused for machine token(s) that can never be a real "
            "clinical string: " + ", ".join(refused)
        )
    denylist = [tok for tok in INTERNAL_QC_TOKENS if tok not in waived]
    for cls, label in DOCTOR_FACING_REGIONS:
        regions = extract_div_regions(rendered, cls)
        if not regions:
            # Absence is handled by check 6 for snapshot-box; q-confirm may legally
            # be absent only if the template itself dropped it, which check 2/6
            # already surfaces. Nothing to scan here either way.
            continue
        rtext = " ".join(visible_text(r) for r in regions)
        low = rtext.lower()
        for tok in denylist:
            if tok.lower() in low:
                errors.append(
                    f"internal_qc marker {tok!r} leaked into the {label} — "
                    f"audience=internal_qc flags belong in review_flags.md + the "
                    f"collapsed .qc-note line, never in the doctor-facing surface"
                )

    # 8. internal_qc flags are collapsed, not silently dropped ------------------
    qc_check = "SKIPPED (no .visit_prep_data.json)"
    data = None
    if data_path.exists():
        try:
            data = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"cannot parse data JSON {data_path}: {e}")
            qc_check = "ERROR"
    elif data_explicit:
        print(f"ERROR: --data file not found: {data_path}", file=sys.stderr)
        return 2

    if isinstance(data, dict):
        raw_count = data.get("internal_qc_count") or 0
        try:
            qc_count = int(raw_count)
        except (TypeError, ValueError):
            errors.append(f"internal_qc_count is not an integer: {raw_count!r}")
            qc_count = 0
        qc_flags = data.get("internal_qc_flags") or []
        if not isinstance(qc_flags, list):
            errors.append("internal_qc_flags must be a list when present")
            qc_flags = []
        if qc_flags and len(qc_flags) != qc_count:
            errors.append(
                f"internal_qc_flags has {len(qc_flags)} entr(ies) but "
                f"internal_qc_count is {qc_count} — the audit list and the "
                f"patient-facing count must agree"
            )
        effective = max(qc_count, len(qc_flags))
        has_note = bool(QC_NOTE_CLASS_RE.search(rendered))
        if effective > 0 and not has_note:
            errors.append(
                f"{effective} internal_qc review_flag(s) declared in "
                f"{data_path.name} but the rendered HTML has no collapsed "
                f".qc-note line — internal_qc flags were silently dropped"
            )
        elif effective == 0 and has_note:
            errors.append(
                "rendered HTML carries the collapsed .qc-note line but "
                f"{data_path.name} declares no internal_qc flag"
            )
        elif effective > 0:
            # the collapsed line must show the same N the data declares
            note_text = " ".join(visible_text(r) for r in extract_div_regions(rendered, "qc-note"))
            if not re.search(r"(?<!\d)" + str(effective) + r"(?!\d)", note_text):
                errors.append(
                    f"collapsed .qc-note line does not show the declared "
                    f"internal_qc count {effective}: {note_text.strip()[:120]!r}"
                )
        qc_check = f"{effective} internal_qc flag(s) collapsed" if effective else "0 internal_qc flags"

    # 9. NO forbidden read: `extracted_fields.json` / `open_verification_status` --
    admission_check = "SKIPPED (no .visit_prep_data.json)"
    if data is not None:
        raw_data_text = data_path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_DATA_MARKERS:
            if marker in raw_data_text:
                errors.append(
                    f"forbidden read marker {marker!r} present in {data_path.name} — "
                    f"visit-prep may never read extracted_fields.json or its "
                    f"open_verification_status — that is a different field with a "
                    f"different value domain, NOT the structured-JSON "
                    f"verification_status (unverified|clinician_verified|disputed, "
                    f"plus withdrawn on timeline.json events only)"
                )

    # 10. ADMISSION BASIS: per-field high_risk_fields[], not the row-level summary
    if isinstance(data, dict):
        admission = data.get("snapshot_admission")
        legacy = bool(data.get("legacy_flag_fallback"))
        if admission is None:
            admission_check = "SKIPPED (no snapshot_admission[])"
        elif not isinstance(admission, list):
            errors.append("snapshot_admission must be a list when present")
            admission_check = "ERROR"
        else:
            # A cell (notably snapshot_key_labs) may carry several labels with
            # different statuses — dedupe on (cell, label), not on cell alone.
            seen_cells: set[tuple[str, str]] = set()
            cell_admitted: dict[str, bool] = {}
            for i, entry in enumerate(admission):
                where = f"snapshot_admission[{i}]"
                if not isinstance(entry, dict):
                    errors.append(f"{where} must be an object")
                    continue
                cell = entry.get("cell")
                if cell not in SNAPSHOT_CELLS:
                    errors.append(
                        f"{where}.cell {cell!r} is not one of {sorted(SNAPSHOT_CELLS)}"
                    )
                    continue
                key = (cell, str(entry.get("label") or ""))
                if key in seen_cells:
                    errors.append(
                        f"{where}: (cell={cell!r}, label={key[1]!r}) declared more than once"
                    )
                seen_cells.add(key)

                basis = entry.get("basis")
                if basis not in ADMISSION_BASES:
                    hint = ""
                    if isinstance(basis, str) and "verification_status" in basis and not any(
                        f"=={v}" in basis for v in VERIFICATION_STATUS_VALUES
                    ):
                        hint = (
                            " — the only verification_status values are "
                            + "/".join(VERIFICATION_STATUS_VALUES)
                            + "; for a per-field decision use "
                            "high_risk_fields.status==passed_independent_reread"
                        )
                    errors.append(
                        f"{where}.basis {basis!r} is not an allowed admission basis"
                        f"{hint}. Allowed: " + ", ".join(sorted(ADMISSION_BASES))
                    )
                    continue
                admits, needs_label, needs_legacy = ADMISSION_BASES[basis]
                admitted = entry.get("admitted")
                if not isinstance(admitted, bool):
                    errors.append(f"{where}.admitted must be a boolean, got {admitted!r}")
                    continue
                cell_admitted[cell] = cell_admitted.get(cell, False) or admitted
                if admits is not None and admitted != admits:
                    errors.append(
                        f"{where}: basis {basis!r} implies admitted={admits} but the "
                        f"entry declares admitted={admitted}"
                    )
                if needs_label and not entry.get("label"):
                    errors.append(
                        f"{where}: basis {basis!r} decides ONE field of "
                        f"high_risk_fields[], so `label` is required"
                    )
                if needs_legacy and not legacy:
                    errors.append(
                        f"{where}: basis {basis!r} is a fallback path but "
                        f"legacy_flag_fallback is not true — never fall back silently"
                    )
                # A13: the row-level summary may only decide a cell when the
                # inventory row genuinely has no high_risk_fields[] array.
                if basis == "legacy_row_level_high_risk_review_status":
                    present = entry.get("high_risk_fields_present")
                    if present is not False:
                        errors.append(
                            f"{where}: the row-level high_risk_review_status may only "
                            f"decide a cell when the inventory row has NO "
                            f"high_risk_fields[] (declare high_risk_fields_present: "
                            f"false). It is a derived summary — judging a single cell "
                            f"with it kills sibling fields that DID pass their "
                            f"independent second read."
                        )
                elif basis.startswith("high_risk_fields.") and entry.get(
                    "high_risk_fields_present"
                ) is False:
                    errors.append(
                        f"{where}: basis {basis!r} reads high_risk_fields[] but the "
                        f"entry declares high_risk_fields_present: false"
                    )
            # A cell with no admitted field at all must render val_pending → null.
            # (A cell where SOME label passed keeps that label's value; the blocked
            #  siblings simply never appear — that is exactly what per-field
            #  high_risk_fields[] buys over the row-level summary.)
            for cell, any_admitted in sorted(cell_admitted.items()):
                if not any_admitted and data.get(cell) is not None:
                    bases = sorted(
                        {
                            str(e.get("basis"))
                            for e in admission
                            if isinstance(e, dict) and e.get("cell") == cell
                        }
                    )
                    errors.append(
                        f"snapshot_admission: NO field of cell {cell!r} was admitted "
                        f"(bases: {', '.join(bases)}) but {cell} carries a value "
                        f"{data.get(cell)!r} — it must be null so the template "
                        f"renders val_pending"
                    )
            # A declared audit array may not silently omit a cell that carries a
            # value — that would let an unaudited cell slip past the gate. Null
            # cells need no entry (nothing was admitted to audit).
            for cell in sorted(SNAPSHOT_CELLS):
                if data.get(cell) is not None and cell not in cell_admitted:
                    errors.append(
                        f"snapshot_admission is declared but carries no entry for "
                        f"{cell!r}, which holds a value — every populated snapshot "
                        f"cell must record what admitted it"
                    )
            n_adm = sum(1 for v in cell_admitted.values() if v)
            n_fields = len(admission)
            admission_check = (
                f"{n_adm}/{len(cell_admitted)} snapshot cell(s) admitted "
                f"over {n_fields} field decision(s)"
                + (" [legacy fallback]" if legacy else "")
            )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"FAIL: {len(errors)} form-invariant violation(s) in {rendered_path.name}", file=sys.stderr)
        return 1

    print(f"visit-prep HTML form-invariants OK ({rendered_path.name})")
    print(f"  internal_qc routing: {qc_check}")
    print(f"  snapshot admission: {admission_check}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
