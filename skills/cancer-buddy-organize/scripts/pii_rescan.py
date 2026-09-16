#!/usr/bin/env python3
"""pii_rescan.py — deterministic SHAPE-floor PII backstop on 段 1 LLM sidecars.

Two independent residue layers guard the PII gate (organizer-prompt-phase1-transcribe.md
§2.5), trust-but-verify:
  - Layer 1 — **semantic agent scan** (references/pii-rescan-prompt.md): the PRIMARY,
    generalizing scan. Reads meaning, flags ANY identifying category — including ones
    no regex pre-encodes (出生地/籍贯, 职业/工作单位, 家属姓名, 民族, clinician
    signatures, 检验号/标本号 …). Owns ALL label/semantic detection.
  - Layer 2 — **THIS script**: the deterministic, zero-network, reproducible backstop.
    It scans ONLY for pure-shape identifiers (身份证18位 / 中国手机 / 座机 / E.164 /
    US-SSN / ≥11位数字ID / email / host-absolute path / cloud-account path / an
    identity-deny-list token). These are zero-false-negative shapes; the point of a
    deterministic second opinion is to catch a leak even if both LLM passes (the §2.4
    masker + Layer 1) share a blind spot.

The 段 1 LLM masker (§2.4) is the primary redactor. The sidecar MD is the
**single downstream plaintext boundary** (timeline / case_text / profile / 摘要渲染 HTML
all read the MD and NEVER re-read the original source file), so any plaintext PII that
survives leaks all the way through — hence the two-layer gate. This script runs AFTER
the worker writes sidecars and BEFORE 段 2 consumes them. It does NOT rely on the
LLM's `## PII` self-report and never performs OCR. Label/semantic catching that used to
live here (姓名:/住院号:/签名/检验号 …) moved to Layer 1 — those arms were brittle
(could not generalize) and historically false-fired on clean records.

Scope (matches phase1-transcribe.md §2.4 — "touches PII tokens ONLY"):
  - For SIDECARS: only the OCR body is scanned. The full sidecar header block
    (`SOURCE:` / `READ_MODE:` / `ADAPTER:` / `ADAPTER_PROVENANCE:` / `CONFIDENCE:`
    / `FILE_ID:` / `MODALITY:`, plus the legacy `ORIGINAL:`) and the `## PII`
    trailer are provenance metadata, not clinical content — skipped.
  - For DELIVERED (non-sidecar) surfaces (DELIVERED_SURFACES — INDEX.md /
    source_inventory.json / update_log.json / AGENTS.md / 病情简要总结.html) AND
    SYNTHESIZED surfaces (SYNTHESIZED_SURFACES — case_text.md / timeline.md /
    review_summary.md / review_flags.md / profile.json / readiness.json /
    extracted_fields.json / .case_summary_data.json and the NINE structured JSON
    products — the count is `validate_structured_outputs.STRUCTURED_FILES`, and
    `readiness.json` and `timeline.json` are two of the nine (fix spec C14; the docs
    said "six" while the list carried nine, so a reader auditing coverage by the prose
    would conclude three products were unscanned) — the file is scanned WHOLE
    (no header exemption) for
    email/absolute-path/account/standalone-shape leaks + a patient-identity deny-list —
    see scan_delivered_surfaces(). These shipped/synthesized artifacts were the real leak
    path the body-only scan missed (a real run leaked 身份证 + 手机 into case_text.md and
    the real name into profile.json). On synthesized surfaces the loose ≥11-digit shape is
    suppressed (de-identified raw-filename timestamps like 微信图片_<14位>.jpg would else
    false-fire); semantic categories there (出生地/职业/民族…) are Layer-1's job.
  - Clinical fidelity wins: this gate flags ONLY pure-shape standalone
    identifiers. It does NOT flag clinical dates, lab values, drug names, TNM,
    molecular markers, or age — those carry no reliable standalone PII shape signature and are
    left untouched by this regex layer. This does not declare them safe to share;
    task minimization and combination risk belong to Layer 1. Semantic / label-based PII
    (姓名/住院号/出生地/职业/签名 …) is Layer 1's job (pii-rescan-prompt.md).
  - Locale-agnostic by SHAPE: the standalone patterns (中国身份证/手机/座机 +
    email + US-SSN + international/E.164 phone + ≥11-digit numeric id) fire on any
    record regardless of language — a shape is a shape.

This is a *detector*, not an auto-rewriter: medical-record redaction is a
judgement task (phase1-transcribe.md §2.4 — "not a fixed regex list"), so the fix is
made by the agent re-reading the flagged line in context and re-masking, then
re-running this gate until it passes. A regex auto-replace here would risk
eating a clinical character adjacent to the matched span.

Usage:
    python3 scripts/pii_rescan.py <patient_dir_or_sidecar_dir_or_file> [...]

If given a directory, every `*.md` under `<dir>/ocr/` is scanned (the 段 1
central staging dir); if `<dir>/ocr/` does not exist, every `*.md` under the
buckets `01_…14_` is scanned (post-段 2 co-located sidecars). A direct path
to a single `.md` file scans just that file.

Each file is scanned line-by-line for the standalone shape patterns. (The former
cross-line label/value straddle detection moved out with the label arms — a bare
digit run on its own line is still caught by the standalone shapes, and label
context is Layer 1's semantic job.)

Output: human-readable findings to stderr; a one-line machine summary to stdout:
    PII_RESCAN: files=<N> clean=<N> with_residue=<N> findings=<N>

Exit codes:
    0  — no residue found (gate PASSES — safe to proceed to 段 2)
    1  — at least one plaintext-PII residue found (gate FAILS — re-mask + re-run)
    2  — bad invocation / nothing to scan
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MASK_TOKEN = "[PII_MASKED]"

# Standalone high-precision SHAPE identifiers (no label needed). Locale-agnostic by
# shape — these fire on any record regardless of language. This is the ENTIRE
# detector surface of the deterministic backstop: pure shapes with ~zero false
# negatives. Label/semantic PII (姓名/住院号/出生地/职业/签名/检验号 …) is owned by
# Layer 1 (references/pii-rescan-prompt.md), NOT here — those label arms were
# removed because they could not generalize and historically false-fired.
_STANDALONE = [
    (re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"), "id_number"),  # 中国身份证 18-digit
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "phone"),                # 中国手机
    (re.compile(r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)"), "phone"),      # 中国座机
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "email"),                # email (any locale)
    (re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"), "id_number"),      # US SSN shape
    (re.compile(r"(?<![\w+])\+\d[\d\s().-]{6,}\d"), "phone"),          # E.164 / international (must start with +)
    (re.compile(r"(?<!\d)\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"), "phone"),  # US 10-digit w/ separators
    # Long bare digit run (≥11): facility 检验号 (e.g. 24080800634), 18-digit 医疗代码 /
    # 病案号. A residue gate over-detects: clinical lab values carry decimals/units and dates
    # carry separators, so an 11+ digit unbroken run is an identifier, not a clinical value.
    (re.compile(r"(?<!\d)\d{11,}(?!\d)"), "numeric_id"),
]

# --------------------------------------------------------------------------- #
# The REWRITE set (fix spec A7) — deliberately NARROWER than the detect set above.
#
# Detection and rewriting are different jobs with opposite error costs. A detector may
# over-fire: a human reads the flag, looks at the line, and moves on. A REWRITER that
# over-fires destroys a clinical value in the only copy anything downstream will ever
# read, and it does so silently — the deleted characters are not in the output to notice.
#
# Two patterns were in the shared set and are now DETECT-ONLY, because each one eats real
# lab lines:
#   US 10-digit `\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}` — matches `淀粉酶 105 350 1200`
#       (result, then the two ends of the printed reference range: 3 digits, 3 digits,
#       4 digits, separated by spaces). That is an entire lab row, and masking it leaves
#       the archive asserting an amylase of "[PII_MASKED]".
#   E.164 `\+\d[\d\s().-]{6,}\d` — matches `+3 1.2 (2.4)` style annotated deltas and any
#       signed value followed by parenthesised numbers.
# Both stay in _STANDALONE so the gate still REPORTS them for a human; neither rewrites.
#
# Added instead: label-anchored Chinese record identifiers, which have no standalone shape
# (a 7-digit 住院号 is indistinguishable from a lab value) but are unambiguous once the
# label is adjacent. The label itself is preserved; only the digits after it are replaced.
_LABELLED_ID_RE = re.compile(
    r"(?P<label>住院号|门诊号|病案号|检验号|标本号|条形码|条码号)"
    r"(?P<sep>\s*[:：#＃]?\s*)"
    r"(?P<value>[A-Za-z]{0,3}\d{4,})"
)
_MASK_PATTERNS = [
    (re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"), "id_number"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "phone"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "email"),
    (re.compile(r"(?<!\d)\d{11,}(?!\d)"), "numeric_id"),
]
# Shapes that make a BARE SCALAR (a frontmatter leaf with no surrounding text) an
# identifier. A leaf is all-or-nothing: there is no clinical character to preserve beside
# it, so a 7-digit bare number under a key is far more likely to be 住院号 than a lab
# value — but only when the KEY says so, which is why the caller passes the key in.
# The ASCII arm is WORD-BOUNDED and the short ambiguous tokens are gone. `tel` as a bare
# substring matched "Telomere length", so a telomere measurement of 5200 was replaced with
# [PII_MASKED] — over-rewriting a clinical value, which is the exact failure A7 narrows the
# rewrite set to avoid. `name` is likewise dropped: a numeric leaf under a key containing
# "name" is not an identifier shape, and the real 姓名 leak is a STRING, which the semantic
# pass owns. CJK terms need no boundary — they are unambiguous as substrings.
_ID_KEY_RE = re.compile(
    r"(住院号|门诊号|病案号|就诊卡号|检验号|标本号|样本号|条形码|条码号|身份证|证件号|"
    r"手机号|联系电话|联系方式|"
    r"\b(?:mrn|medical_record(?:_number)?|patient_id|accession|barcode|"
    r"phone(?:_number)?|mobile|telephone|email|id_?card)\b)",
    re.IGNORECASE,
)
_BARE_ID_VALUE_RE = re.compile(r"^[A-Za-z]{0,3}\d{4,}$")

# fix spec B10 — the TIMESTAMP EXEMPTION for the loose ">=11 bare digits" arm.
#
# `采集时间: 20240808143000` is a compact datetime, not an identifier, and it is the single
# most common long-digit leaf a Chinese LIS export produces. The generic numeric_id shape
# cannot tell it from a 病案号 — nothing about the digits says which it is — so the KEY has
# to. Masking it costs the archive the collection time of a specimen, which is the one
# fact the whole timeline is built on, and it does so invisibly: downstream sees
# `[PII_MASKED]` and cannot tell whether the page never printed a time.
#
# The exemption is narrow by construction: it applies ONLY to the loose numeric_id arm
# (身份证 / 手机 / email shapes still mask, because none of them is a plausible timestamp),
# and ONLY when the key is not ALSO an identifier key — `_ID_KEY_RE` wins, so a
# 「条码号」 or 「住院号」 leaf is masked no matter what other word sits in the key.
_TIMESTAMP_KEY_RE = re.compile(
    r"时间|日期|采集|报告|送检|出生|生日|受检|检测日|审核"
    r"|\b(?:date|time|datetime|timestamp|collected|reported|sampled|dob|dos)\b",
    re.IGNORECASE,
)
# Reported on the span list so the skip is AUDITABLE. A silent exemption and a silent
# leak look identical from outside; this one says "a shape matched here and was
# deliberately not rewritten, because the key said it was a time".
SKIPPED_AS_TIMESTAMP = "skipped_as_timestamp"


def scan_line(line: str) -> list[tuple[str, str]]:
    """Return list of (pii_type, matched_snippet) for SHAPE residue on this line.

    Only standalone shape identifiers — label/semantic PII is Layer 1's job. A
    masked value (`[PII_MASKED]`) has no digits/email shape, so it never matches."""
    findings: list[tuple[str, str]] = []
    if not line.strip():
        return findings
    for pattern, pii_type in _STANDALONE:
        for m in pattern.finditer(line):
            findings.append((pii_type, m.group(0)))
    return findings


def mask_text(text: str) -> tuple[str, list[dict]]:
    """Replace every REWRITE-set identifier with MASK_TOKEN. Returns (masked, spans).

    SCOPE, stated plainly: this is the deterministic SHAPE masker, and it is the FLOOR,
    not the masker. It handles 身份证 / 中国手机 / email / >=11-digit runs / label-anchored
    record numbers (住院号 / 门诊号 / 病案号 / 检验号 / 标本号 / 条码号). It CANNOT see
    姓名, 出生地, 职业, 家属姓名, 民族 or clinician signatures; those have no shape and
    remain Layer 1's (the semantic agent pass) job. A page that has only been through this
    function is NOT cleared for a downstream context.

    WHAT IT DELIBERATELY DOES NOT REWRITE (fix spec A7). The US 10-digit phone shape and
    the E.164 shape stay in the DETECT set and are never rewritten here, because both
    match ordinary laboratory rows: `淀粉酶 105 350 1200` is a result followed by the two
    ends of the printed reference range, and it matches `\d{3}[\s]\d{3}[\s]\d{4}`
    exactly. Masking it would delete the amylase value and its reference range from the
    only copy anything downstream reads, silently. Over-detection costs a human one
    glance; over-REWRITING costs the archive a clinical fact it cannot get back.

    SPANS, NOT SNIPPETS. The return value records `{kind, len, line}` per replacement and
    never the matched text. This function is called while DERIVING the masked copy, and
    its return value flows into a manifest that downstream reads — echoing the identifier
    into that manifest would reintroduce exactly the leak the masking just closed.

    Clinical fidelity is preserved: no pattern here matches a drug name, dose, unit,
    variant, TNM stage or clinical date. Overlapping matches (an 18-digit 身份证 also
    matches the >=11-digit run) are merged into one span so the output can never contain a
    half-masked identifier.
    """
    out_lines: list[str] = []
    spans_out: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        spans: list[tuple[int, int, str]] = []
        for pattern, pii_type in _MASK_PATTERNS:
            for m in pattern.finditer(line):
                spans.append((m.start(), m.end(), pii_type))
        for m in _LABELLED_ID_RE.finditer(line):
            spans.append((m.start("value"), m.end("value"), "record_number"))
        if not spans:
            out_lines.append(line)
            continue
        spans.sort(key=lambda x: (x[0], -x[1]))
        merged: list[tuple[int, int, str]] = []
        for start, end, kind in spans:
            if merged and start < merged[-1][1]:
                prev_start, prev_end, prev_kind = merged[-1]
                # keep the more specific label when two shapes overlap
                merged[-1] = (prev_start, max(prev_end, end),
                              prev_kind if prev_kind != "numeric_id" else kind)
                continue
            merged.append((start, end, kind))
        masked = line
        for start, end, kind in reversed(merged):
            spans_out.append({"kind": kind, "len": end - start, "line": i})
            masked = masked[:start] + MASK_TOKEN + masked[end:]
        out_lines.append(masked)
    tail = "\n" if text.endswith("\n") else ""
    spans_out.sort(key=lambda s: (s["line"], s["kind"]))
    return "\n".join(out_lines) + tail, spans_out


def _bare_digit_carveouts(probe: str, key: str, original):
    """The two KEY-driven carve-outs, applied identically to a numeric and a string leaf.

    Returns `(masked_value, spans)` when a carve-out fires, or None to mean "no carve-out
    applies — mask this leaf the ordinary way".

    `probe` is the leaf rendered as bare digits with any sign stripped; `original` is the
    value to hand back untouched when the timestamp exemption fires.

    WHY ONE FUNCTION AND NOT TWO (fix spec C10 + the string/int parity fix)
        The type a leaf happens to arrive as is an accident of the parser, not a property
        of the datum. YAML `住院号: -12345` is an int; `住院号: "-12345"` — same page, same
        field, quoted because the export tool quoted it — is a str. They were being judged
        by two different code paths, and the paths disagreed in BOTH directions:

          * `住院号: "-12345"` was NOT masked. The str branch went straight to mask_text(),
            which has no identifier-key arm at all, and five digits match none of its
            zero-false-positive shapes. The int branch masked the identical value.
          * `采集时间: "20240808143000"` WAS masked. The str branch hit the loose
            ">=11 bare digits" arm with no key to excuse it, so the specimen collection
            time — the fact the timeline is built on — became `[PII_MASKED]`, while the
            int form of the same timestamp was correctly exempted.

        Two branches that answer the same question differently are not two features; the
        quoting style of an upstream export decided whether a hospital number leaked.
    """
    is_id_key = bool(_ID_KEY_RE.search(key or ""))
    # Carve-out 1 — an identifier KEY plus an identifier SHAPE. Masked whole, because a
    # bare record number carries no clinical payload worth preserving.
    if is_id_key and _BARE_ID_VALUE_RE.match(probe):
        return MASK_TOKEN, [{"kind": "record_number", "len": len(probe), "line": 0}]
    # Carve-out 2 — a compact datetime under a time-shaped key. `_ID_KEY_RE` wins above,
    # so a 「条码号」/「住院号」 leaf is never excused no matter what other word is in the key.
    remasked, found = mask_text(probe)
    if found:
        if (not is_id_key
                and _TIMESTAMP_KEY_RE.search(key or "")
                and all(f["kind"] == "numeric_id" for f in found)):
            # Not rewritten, but RECORDED: `masked_spans` stays empty for this leaf
            # (nothing was masked) and the skip is named, so a reviewer can see which
            # shapes the key excused.
            return original, [{"kind": SKIPPED_AS_TIMESTAMP,
                               "len": len(probe), "line": 0, "key": str(key or "")}]
        return MASK_TOKEN, found
    return None


def mask_scalar(value, key: str = "") -> tuple[object, list[dict]]:
    """Mask ONE frontmatter leaf. Returns (masked_value, spans).

    A leaf is not a line of prose: there is no surrounding clinical text to protect, and a
    partial replacement inside a bare scalar would produce a value that is neither the
    original nor a clean mask. So a leaf is all-or-nothing.

      str leaf     -> mask_text() (a value like "联系电话 13800138000" keeps its label)
      numeric leaf -> str()ed and shape-tested; a bare 4+ digit run under an IDENTIFIER
                      key (住院号 / MRN / accession / 条码号 ...) becomes the STRING
                      "[PII_MASKED]". This is the case a text-only masker misses entirely:
                      YAML `住院号: 0012345` parses to an int, an int has no line to scan,
                      and the identifier travels into every downstream context as a number.

    The key is required for the numeric arm, and only for it: masking every bare number in
    a transcription's frontmatter would erase every lab value on the page.
    """
    spans: list[dict] = []
    if isinstance(value, str):
        # A string leaf whose ENTIRE content is one signed digit run is a scalar datum,
        # not prose, and it gets the same key-driven carve-outs the int branch gets.
        # Restricted to the all-digits case on purpose: a mixed string such as
        # "报告时间 20240808143000 住院号 12345678901" must NOT be excused wholesale by its
        # time-shaped key, or the exemption becomes a place to hide a second identifier.
        probe = value.strip()
        signless = probe.lstrip("+-")
        if signless and signless.isdigit():
            carved = _bare_digit_carveouts(signless, key, value)
            if carved is not None:
                return carved
        masked, spans = mask_text(value)
        return masked, spans
    if isinstance(value, bool) or value is None:
        return value, spans
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            # A FLOAT LEAF IS NEVER AN IDENTIFIER (found while validating B10 on a real
            # ingest run; the defect is older than B10 and is fixed here because it is in
            # this function). `repr(0.15000000000000002)` is 19 characters containing a
            # 17-digit unbroken run, and the loose ">=11 bare digits" arm matched it — so
            # every `span.bbox` coordinate that landed on a binary-inexact value was
            # rewritten to the STRING "[PII_MASKED]" inside the masked sidecar. That
            # silently destroys the page anchor gate_faithfulness (A20) checks bbox area
            # and page against, and it destroys it selectively, on whichever coordinates
            # happened to be inexact.
            #
            # No identifier in this archive is written with a decimal point: 住院号 /
            # 检验号 / 身份证 / 手机 are integer or alphanumeric strings. A float is a
            # measured quantity by construction, so the honest rule is that the shape arm
            # does not apply to it at all — rather than trying to teach the regex about
            # floating-point repr, which is an open-ended fight it would keep losing.
            return value, spans
        raw = "%d" % value
        # fix spec B10 — judge the shape on the ABSOLUTE value. `住院号: -12345` parsed to
        # int -12345, `"%d"` rendered `-12345`, and `^[A-Za-z]{0,3}\d{4,}$` does not match a
        # leading minus — so a negative-signed identifier walked straight through the leaf
        # masker. A sign is not part of an identifier's shape; it is a transcription
        # artefact (an OCR'd 「—12345」, a spreadsheet that typed the column as a number).
        probe = raw.lstrip("+-")
        # An identifier-shaped number under a NON-identifier key is still masked when it
        # carries a zero-false-positive standalone shape (>=11 digits, 身份证, 手机).
        carved = _bare_digit_carveouts(probe, key, value)
        if carved is not None:
            return carved
        return value, spans
    # fix spec B10 — FAIL CLOSED on a type this masker does not understand.
    #
    # The old `return value, spans` tail was a silent bypass with the widest possible
    # mouth: anything that was not str/bool/None/int/float was handed back UNMASKED and
    # counted as clean. The frontmatter parser is JSON-typed today, so nothing should ever
    # reach here — which is precisely why reaching here means an assumption broke
    # (a PyYAML path that yields datetime.date, a binary leaf, a custom object), and the
    # one thing a masker must never do when its assumptions break is emit the input.
    # The caller in ingest_transcripts.py catches this and marks the page `invalid`,
    # writing NEITHER copy.
    raise TypeError(
        f"mask_scalar: unmaskable leaf type {type(value).__name__!r} under key {str(key)!r}. "
        "Refusing to pass it through unmasked — a leaf this function cannot inspect is a "
        "leaf it cannot clear"
    )


def mask_structure(node, key: str = "") -> tuple[object, list[dict]]:
    """Recursively mask every LEAF of a parsed frontmatter structure (fix spec A7).

    The previous implementation json.dumps()ed the whole frontmatter, ran the line masker
    over the serialized text, and json.loads()ed it back — with a bare `except
    JSONDecodeError: masked_fm = fm` fallback. That fallback is the defect: masking a
    string that happens to contain a quote, or replacing a numeric token so the result is
    `"page": [PII_MASKED]`, breaks the JSON, and the handler then wrote the UNMASKED
    frontmatter to the downstream-readable copy. A masking failure silently became a
    masking bypass.

    Walking the structure removes the failure mode rather than handling it: there is no
    serialization round-trip to break, keys are never masked (they are schema names, not
    content), and a numeric leaf is reachable, which a text pass over JSON could only
    reach by accident.
    """
    spans: list[dict] = []
    if isinstance(node, dict):
        # In this schema the SEMANTIC key of a value is not always its own dict key. A
        # transcription's `fields[]` entry is `{"label": "住院号", "value": 12345}`: the key
        # of the numeric leaf is the literal string "value", which says nothing, while the
        # thing that makes it an identifier sits in a sibling. Without this, every
        # identifier a model lifted OUT of the body and INTO fields[] survived masking
        # untouched — and fields[] is precisely where downstream reads values from.
        sibling_label = ""
        for cand in ("label", "name", "field", "key"):
            if isinstance(node.get(cand), str):
                sibling_label = node[cand]
                break
        out_d = {}
        for k, v in node.items():
            ctx = str(k)
            if sibling_label and k in ("value", "raw_value", "text", "source_reported_text"):
                ctx = f"{sibling_label} {k}"
            child, found = mask_structure(v, key=ctx)
            out_d[k] = child
            spans.extend(found)
        return out_d, spans
    if isinstance(node, list):
        out_l = []
        for v in node:
            child, found = mask_structure(v, key=key)
            out_l.append(child)
            spans.extend(found)
        return out_l, spans
    return mask_scalar(node, key=key)


# --------------------------------------------------------------------------- #
# Sidecar scaffold — ONE definition, shared (fix spec A24/A35)
#
# verify_native_text.py used to carry its own copy of this logic with a different rule for
# where the header ends, so the two scripts disagreed about which bytes were "content":
# pii_rescan skipped a `SOURCE:` line ANYWHERE in the file, while verify_native_text
# stopped stripping at the first non-header line. A source whose clinical text legitimately
# contains a line beginning `SOURCE:` was scanned differently by the gate than by the
# faithfulness check. Both now call these functions.
#
# The header exemption is ANCHORED AT THE START OF THE FILE: only the unbroken run of
# provenance lines (and an optional YAML frontmatter block) at the top is scaffold. A
# `SOURCE:` line in the middle of a transcription is page content and IS scanned — a
# letterhead can say anything, including something that looks like a header key, and an
# exemption that floats is an exemption an attacker can position.
# --------------------------------------------------------------------------- #
_HEADER_KEYS = (
    "SOURCE:", "ORIGINAL:", "READ_MODE:", "ADAPTER:", "ADAPTER_PROVENANCE:",
    "CONFIDENCE:", "FILE_ID:", "MODALITY:", "SOURCE_ID:", "PAGE_RANGE:",
)
_PII_TRAILER_RE = re.compile(r"^##\s+PII\b")


def strip_bom(text: str) -> str:
    return text[1:] if text.startswith("\ufeff") else text


def scaffold_bounds(text: str) -> tuple[int, int]:
    """Return (body_start_index, body_end_index) as 0-based line indices, end-exclusive.

    Scaffold = (a) an optional leading YAML frontmatter block delimited by `---`, or an
    unbroken run of `KEY:` provenance lines and blank lines at the very top of the file,
    and (b) everything from a `## PII` trailer onward.
    """
    lines = strip_bom(text).splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        # A24: sidecars are YAML frontmatter + `# 全文`. Close on the NEXT `---`; if the
        # block never closes, treat nothing as scaffold rather than swallowing the file.
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    else:
        while start < len(lines):
            s = lines[start].strip()
            if not s or any(s.startswith(k) for k in _HEADER_KEYS):
                start += 1
                continue
            break
    end = len(lines)
    for i in range(start, len(lines)):
        if _PII_TRAILER_RE.match(lines[i].strip()):
            end = i
            break
    return start, end


def strip_scaffold(text: str) -> str:
    """The sidecar's CONTENT: no provenance header, no frontmatter, no `## PII` trailer."""
    lines = strip_bom(text).splitlines()
    start, end = scaffold_bounds(text)
    return "\n".join(lines[start:end]).strip("\n")


def scan_sidecar(path: Path) -> list[tuple[int, str, str]]:
    """Scan one MD sidecar's BODY (skip the leading scaffold + `## PII` trailer).

    The scaffold boundary is computed ONCE, by scaffold_bounds(), and is ANCHORED AT THE
    START OF THE FILE (fix spec A24). The previous implementation skipped any line
    beginning `SOURCE:` / `FILE_ID:` / ... wherever it appeared, which meant a transcribed
    letterhead reading `SOURCE: ...` mid-page was exempt from the PII gate — a floating
    exemption is one an attacker (or an unlucky form) can position. It also disagreed with
    verify_native_text's own copy of the rule; both now share this module's functions.

    Returns list of (line_no_1based, pii_type, snippet)."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        # A sidecar that is not UTF-8 cannot be scanned, and "cannot be scanned" must never
        # read as "scanned clean".
        return [(0, "undecodable", str(e))]
    except Exception as e:  # unreadable sidecar is itself a finding-worthy state
        return [(0, "unreadable", str(e))]

    lines = strip_bom(text).splitlines()
    start, end = scaffold_bounds(text)
    results: list[tuple[int, str, str]] = []
    for i in range(start, end):
        for pii_type, snippet in scan_line(lines[i]):
            results.append((i + 1, pii_type, snippet))
    return results


# --------------------------------------------------------------------------- #
# Delivered-surface (non-sidecar) PII scan — US-001
#
# The sidecar-body scan above deliberately skips header blocks and only looks at
# OCR clinical text. But the pipeline ALSO ships machine/human artifacts that are
# NOT sidecars — INDEX.md, source_inventory.json, update_log.json, and the
# patient-facing 病情简要总结.html. A real run
# leaked the patient's name (in a `<name>-报告.pdf` filename copied verbatim into
# original_path) and the uploader's cloud/email account (in absolute paths) into
# exactly these files. They were never scanned because collect_sidecars() only
# globs sidecars. This block closes that hole: these surfaces are scanned WHOLE
# (no header exemption) for standalone identifiers, path/account leaks, name-in-
# filename patterns, and any token on a patient-identity deny-list.
# --------------------------------------------------------------------------- #
DELIVERED_SURFACES = [
    "INDEX.md",
    "source_inventory.json",
    "update_log.json",
    "病情简要总结.html",
    "AGENTS.md",  # agent-facing recall pointer; embeds profile.json one_line_condition — shipped, so scan it
    # visit-prep ships its patient-facing HTML into the same patient_dir; it is gated by
    # validate_visit_prep_html.py at production time, but the export boundary (export_share →
    # validate_structured_outputs) must ALSO shape-scan it so a later standalone export can't
    # ship un-rescanned PII. (Its data JSON visit_prep_data.json is intermediate render state.)
    "就诊准备包.html",
]

# Synthesized downstream surfaces — built by 段 2 from the masked sidecars, then read
# by downstream sub-skills AND shipped by export_share.py. A real run leaked the 患者
# 身份证 + 手机 (pure SHAPES) into case_text.md and the real name into profile.json's
# mis-named `name_redacted` field — and NEITHER was scanned, because they are neither
# bucket sidecars nor in DELIVERED_SURFACES. The deterministic shape floor now scans
# them too (closes the shape/denylist export hole). NOTE: purely-SEMANTIC leaks here
# (出生地/籍贯/职业/民族 — no shape signature) are still Layer-1's job (pii-rescan-prompt.md);
# this floor only adds the shape/denylist backstop on these files.
SYNTHESIZED_SURFACES = [
    # prose the patient / downstream sub-skills actually read
    "case_text.md",
    "timeline.md",
    "review_summary.md",
    "review_flags.md",
    # the profile + the run's own state
    "profile.json",
    "readiness.json",
    # organize v3 (fix spec A17): the open-field ledger and the nine structured products.
    # These were the gap: the files that DO ship — every structured JSON a consumer
    # reads and every field the open-world path extracts — were never scanned at all.
    # Two 段 1 build intermediates came OFF the delivered list in the same change
    # (fix spec A17); they no longer exist in the v4 contract and export_share refuses
    # any leftovers, so scanning them only produced findings nobody could act on.
    "extracted_fields.json",
    ".case_summary_data.json",
    "patient_summary.json",
    # fix spec B9. `timeline.md` was on this list from the start and `timeline.json` was
    # not — an omission with no principle behind it. The JSON is the machine face of the
    # SAME synthesized content: it is one of the nine structured products, every downstream
    # sub-skill reads it in preference to the prose, and export_share ships it. A shape
    # that would have been caught in timeline.md sailed through in timeline.json.
    "timeline.json",
    "molecular.json",
    "treatment_lines.json",
    "labs.json",
    "longitudinal_observations.json",
    "missing_items.json",
    "comorbidities.json",
]

_DENYLIST_FILE = ".identity_denylist.json"

# Path / account leaks (host-absolute paths, cloud accounts, emails). Safe on EVERY
# delivered surface incl. the patient HTML — clinical prose never contains these.
_PATH_PII = [
    (re.compile(r"/Users/[^/\s\"']+"), "local_user_path"),                       # absolute home → OS username
    (re.compile(r"(?:CloudStorage|坚果云|OneDrive|Dropbox|iCloud)[^\s\"'\\]*"), "cloud_account_path"),
]

# <2-4 CJK personal name>-<Latin> prefixing a report filename: 张测试-OncoFusion报告.
# Applied ONLY to filename/index/provenance surfaces — NOT to the patient HTML, where
# it FALSE-FIRES on legitimate verbatim CJK-term-hyphen-Latin oncology entities
# (微卫星-MSI / 信迪利单抗-PD-1 / 免疫组化-IHC / 基因检测-NGS …) the producer must render,
# fail-closing a clean record. Real patient names in the HTML are still caught by the
# identity deny-list arm (load_deny_tokens / .identity_denylist.json); name-prefixed
# UPLOAD filenames only ever appear in the index/provenance surfaces anyway.
_FILENAME_PII = [
    (re.compile(r"[一-龥]{2,4}-[A-Za-z]"), "name_in_filename"),
]

# Surfaces that carry verbatim clinical prose → skip the filename-name regex (it
# false-fires on legitimate CJK-term-hyphen-Latin oncology entities like 微卫星-MSI).
# The patient HTML + every synthesized clinical surface qualify; identity deny-list +
# path/account/standalone shape patterns still apply to them.
_CLINICAL_PROSE_SURFACES = {"病情简要总结.html", "就诊准备包.html", "AGENTS.md", *SYNTHESIZED_SURFACES}


def load_deny_tokens(patient_dir: Path) -> set[str]:
    """Patient-identity deny-list (US-001 bootstrap).

    `patient_summary.name` is masked to null downstream, so it cannot seed the
    list. Two seeds that survive masking: (1) an optional `.identity_denylist.json`
    (list of strings, or {"tokens":[...]}), written by 段 1 before it masks; and
    (2) CJK personal names harvested from the verbatim `raw/` filenames the patient
    uploaded (`张测试-OncoFusion报告.pdf` → `张测试`). Any of these tokens appearing
    in a delivered surface is a leak."""
    tokens: set[str] = set()
    f = patient_dir / _DENYLIST_FILE
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            seq = data if isinstance(data, list) else (data.get("tokens", []) if isinstance(data, dict) else [])
            for t in seq:
                if isinstance(t, str) and len(t.strip()) >= 2:
                    tokens.add(t.strip())
        except Exception:
            pass
    raw = patient_dir / "raw"
    if raw.is_dir():
        for p in raw.rglob("*"):
            m = re.match(r"([一-龥]{2,4})[-_]", p.name)
            if m:
                tokens.add(m.group(1))
    return tokens


def scan_delivered_file(path: Path, deny_tokens: set[str], apply_filename_name: bool = True,
                        drop_numeric_id: bool = False) -> list[tuple[int, str, str]]:
    """Scan a shipped non-sidecar file WHOLE (no header exemption).

    apply_filename_name=False skips the CJK-name-in-filename regex for clinical-prose
    surfaces (the patient HTML + synthesized surfaces), where it false-fires on verbatim
    oncology entities; the identity deny-list + path/account/standalone patterns still apply.

    drop_numeric_id=True suppresses the loose ≥11-digit `numeric_id` shape on synthesized
    surfaces — they legitimately embed de-identified raw filenames like
    `微信图片_20260220175937.jpg` (a 14-digit timestamp, NOT PII) that would false-fire and
    fail-close the gate on every patient. The structured 身份证 (id_number), phone, and email
    shapes stay active, so a real 身份证/手机/住院号 leak is still caught; bare ≥11-digit facility
    serials in these files are Layer-1's (semantic) responsibility."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return [(0, "unreadable", str(e))]
    pats = list(_PATH_PII) + (list(_FILENAME_PII) if apply_filename_name else [])
    results: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pii_type, snippet in scan_line(line):
            if drop_numeric_id and pii_type == "numeric_id":
                continue
            results.append((i, pii_type, snippet))
        for pat, pii_type in pats:
            for m in pat.finditer(line):
                results.append((i, pii_type, m.group(0)[:48]))
        for tok in deny_tokens:
            if tok and tok in line:
                results.append((i, "identity_denylist", tok))
    return results


def scan_delivered_surfaces(patient_dir: Path, deny_tokens: set[str] | None = None):
    """Return ({filename: findings}, deny_tokens) for every present delivered AND
    synthesized surface (whole-file shape/path/account/deny-list scan)."""
    if deny_tokens is None:
        deny_tokens = load_deny_tokens(patient_dir)
    out: dict[str, list[tuple[int, str, str]]] = {}
    for name in DELIVERED_SURFACES + SYNTHESIZED_SURFACES:
        p = patient_dir / name
        if p.is_file():
            findings = scan_delivered_file(
                p, deny_tokens,
                apply_filename_name=name not in _CLINICAL_PROSE_SURFACES,
                # Suppress the loose ≥11-digit shape on ALL clinical-prose surfaces (synthesized
                # + the patient-facing HTMLs + AGENTS.md): they embed de-identified raw-filename
                # timestamps (微信图片_<14位>.jpg) that would else false-fire and fail-close the gate.
                # Structured delivered surfaces (INDEX/source_inventory/dotfiles/update_log) keep it.
                drop_numeric_id=name in _CLINICAL_PROSE_SURFACES,
            )
            if findings:
                out[name] = findings
    return out, deny_tokens


def collect_sidecars(target: Path) -> list[Path]:
    if target.is_file() and target.suffix.lower() == ".md":
        return [target]
    if not target.is_dir():
        return []
    # 段 1 invokes the gate as `pii_rescan.py "$patient_dir/ocr"` — i.e. the
    # target IS the staging dir. Scan its *.md directly (without this, the dir-arg
    # path below would look for a nonexistent <ocr>/ocr/ child and scan nothing).
    if target.name == "ocr":
        return sorted(target.glob("*.md"))
    # A leftover / re-created ocr/ staging dir MUST NOT short-circuit the bucket
    # scan. It used to `return` here, which meant every post-段 2 sidecar went
    # unscanned while the gate still printed "PII rescan ... all pass" — a
    # fail-OPEN that a bare `mkdir ocr` was enough to trigger. Union, never return.
    out: list[Path] = []
    ocr_dir = target / "ocr"
    if ocr_dir.is_dir():
        out.extend(sorted(ocr_dir.glob("*.md")))
    # post-段 2: sidecars co-located in NN_ buckets
    buckets = sorted(target.glob("[0-9][0-9]_*"))
    for b in buckets:
        if b.is_dir():
            out.extend(sorted(b.rglob("*.md")))
    # 对话增量模式 notes carry the VERBATIM user chat quote (possible name / MRN /
    # phone). They normally live under <NN_bucket>/conversation_notes/ (already covered
    # above), but a lazy-archive misfile can drop them at a ROOT conversation_notes/
    # with no NN_ prefix — scan conversation_notes/*.md WHEREVER it lands so a conversation note
    # can never escape the PII gate.
    out.extend(sorted(target.rglob("conversation_notes/*.md")))
    # de-dup (a note under an NN_ bucket would match both globs)
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


USAGE = """usage: pii_rescan.py <patient_dir|sidecar_dir|sidecar.md> [...]

Deterministic SHAPE-floor PII gate (Layer 2). Scans sidecar bodies plus every delivered
and synthesized surface for standalone identifier shapes, host-absolute paths, cloud
accounts and identity deny-list tokens. Semantic PII (姓名/出生地/职业/家属名 …) is
Layer 1's job — references/pii-rescan-prompt.md — and this gate does not replace it.

  exit 0  no residue (gate passes)
  exit 1  residue found (re-mask in context and re-run until findings=0)
  exit 2  bad invocation / nothing to scan
"""


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv[1:]):
        print(USAGE)
        return 0
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2

    sidecars: list[Path] = []
    dir_args: list[Path] = []
    for arg in argv[1:]:
        p = Path(arg).resolve()
        if p.is_dir() and p.name != "ocr":
            dir_args.append(p)
        sidecars.extend(collect_sidecars(p))

    # de-dup preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for s in sidecars:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    sidecars = uniq

    # delivered-surface scan (US-001) — only meaningful for a patient_dir arg
    delivered_total = 0
    delivered_seen: set[Path] = set()
    for d in dir_args:
        if d in delivered_seen:
            continue
        delivered_seen.add(d)
        surfaces, deny = scan_delivered_surfaces(d)
        for name, findings in surfaces.items():
            delivered_total += len(findings)
            print(f"\nRESIDUE (delivered surface): {d / name}", file=sys.stderr)
            for line_no, pii_type, snippet in findings:
                loc = f"L{line_no}" if line_no else "(file)"
                print(f"  {loc}  [{pii_type}]  {snippet!r}", file=sys.stderr)

    if not sidecars and not dir_args:
        print("ERROR: no .md sidecars found to scan", file=sys.stderr)
        return 2

    total_findings = 0
    files_with_residue = 0
    for sc in sidecars:
        findings = scan_sidecar(sc)
        if findings:
            files_with_residue += 1
            total_findings += len(findings)
            print(f"\nRESIDUE: {sc}", file=sys.stderr)
            for line_no, pii_type, snippet in findings:
                loc = f"L{line_no}" if line_no else "(file)"
                print(f"  {loc}  [{pii_type}]  {snippet!r}", file=sys.stderr)

    clean = len(sidecars) - files_with_residue
    print(
        f"PII_RESCAN: files={len(sidecars)} clean={clean} "
        f"with_residue={files_with_residue} findings={total_findings} "
        f"delivered_surface_findings={delivered_total}"
    )

    if total_findings or delivered_total:
        if total_findings:
            print(
                "\nGATE FAILED (sidecar body): plaintext PII residue survived 段 1 "
                "redaction. Re-read each flagged line in context, mask the PII token(s) to "
                f"{MASK_TOKEN} (clinical chars untouched — §2.2a / §2.4), and re-run "
                "this gate until findings=0 BEFORE proceeding to 段 2.",
                file=sys.stderr,
            )
        if delivered_total:
            print(
                "\nGATE FAILED (delivered surface): PII leaked into a shipped index/"
                "provenance/HTML artifact (filename, absolute path, account, or a "
                "deny-listed identity token). These are NOT fixed by re-masking a "
                "sidecar. Fix at the PRODUCER: use the de-identified raw handle (the "
                "段 1 de-id raw filename / source_id) in original_path / raw_path / "
                "INDEX — the verbatim upload name stays ONLY in raw/_FILENAME_MAPPING.md "
                "(inside raw/, never a delivered surface); relativize any absolute path; "
                "coarse-grain the HTML. The identifier must never reach INDEX.md / "
                "source_inventory.json / dotfiles / 病情简要总结.html. Then re-run until findings=0.",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
