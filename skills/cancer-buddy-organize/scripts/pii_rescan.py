#!/usr/bin/env python3
"""pii_rescan.py — deterministic SHAPE-floor PII backstop on Phase-1 LLM sidecars.

Two independent residue layers guard the PII gate (organizer-prompt-phase1-ocr.md
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

The Phase-1 LLM masker (§2.4) is the primary redactor. The sidecar MD is the
**single downstream plaintext boundary** (timeline / case_text / profile / 段D HTML
all read the MD and NEVER re-read the original source file), so any plaintext PII that
survives leaks all the way through — hence the two-layer gate. This script runs AFTER
the worker writes sidecars and BEFORE Phase 2 consumes them. It does NOT rely on the
LLM's `## PII` self-report and never performs OCR. Label/semantic catching that used to
live here (姓名:/住院号:/签名/检验号 …) moved to Layer 1 — those arms were brittle
(could not generalize) and historically false-fired on clean records.

Scope (matches phase1-ocr.md §2.4 — "touches PII tokens ONLY"):
  - For SIDECARS: only the OCR body is scanned. The full sidecar header block
    (`SOURCE:` / `READ_MODE:` / `ADAPTER:` / `ADAPTER_PROVENANCE:` / `CONFIDENCE:`
    / `FILE_ID:` / `MODALITY:`, plus the legacy `ORIGINAL:`) and the `## PII`
    trailer are provenance metadata, not clinical content — skipped.
  - For DELIVERED (non-sidecar) surfaces (DELIVERED_SURFACES — INDEX.md /
    source_inventory.json / .rename_plan.json / .phase1_sources.json / update_log.json /
    病情简要总结.html) AND SYNTHESIZED surfaces (SYNTHESIZED_SURFACES — case_text.md /
    profile.json / patient_summary.json / timeline.md / review_summary.md /
    review_flags.md) the file is scanned WHOLE (no header exemption) for
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
judgement task (phase1-ocr.md §2.4 — "not a fixed regex list"), so the fix is
made by the agent re-reading the flagged line in context and re-masking, then
re-running this gate until it passes. A regex auto-replace here would risk
eating a clinical character adjacent to the matched span.

Usage:
    python3 scripts/pii_rescan.py <patient_dir_or_sidecar_dir_or_file> [...]

If given a directory, every `*.md` under `<dir>/ocr/` is scanned (the Phase-1
central staging dir); if `<dir>/ocr/` does not exist, every `*.md` under the
buckets `01_…14_` is scanned (post-Phase-2 co-located sidecars). A direct path
to a single `.md` file scans just that file.

Each file is scanned line-by-line for the standalone shape patterns. (The former
cross-line label/value straddle detection moved out with the label arms — a bare
digit run on its own line is still caught by the standalone shapes, and label
context is Layer 1's semantic job.)

Output: human-readable findings to stderr; a one-line machine summary to stdout:
    PII_RESCAN: files=<N> clean=<N> with_residue=<N> findings=<N>

Exit codes:
    0  — no residue found (gate PASSES — safe to proceed to Phase 2)
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


def scan_sidecar(path: Path) -> list[tuple[int, str, str]]:
    """Scan one MD sidecar's BODY (skip header + `## PII` trailer).

    Returns list of (line_no_1based, pii_type, snippet)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # unreadable sidecar is itself a finding-worthy state
        return [(0, "unreadable", str(e))]

    lines = text.splitlines()
    in_pii_trailer = False
    results: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines, start=1):
        # Skip the sidecar header block (provenance metadata, not OCR body).
        # The header per phase1-ocr.md is SOURCE/READ_MODE/ADAPTER/ADAPTER_PROVENANCE
        # /FILE_ID/MODALITY (+CONFIDENCE on the SOURCE line; legacy ORIGINAL:). These carry
        # enum/provenance tokens, never PII, so skipping them avoids both noise and any
        # header false-fire (e.g. FILE_ID: a stable source_id that must not trip numeric_id).
        if line.startswith((
            "SOURCE:", "ORIGINAL:", "READ_MODE:", "ADAPTER:",
            "ADAPTER_PROVENANCE:", "CONFIDENCE:", "FILE_ID:", "MODALITY:",
            # organize-lite lower-case provenance. `original:` is required to
            # contain only the stable source_id; the protected raw_path lives
            # in phase0_manifest/source_inventory, never in this header.
            "source_id:", "original:", "read_mode:", "profile:",
        )):
            continue
        # `## PII` trailer is metadata — stop scanning the body once we hit it
        if re.match(r"^##\s+PII\b", line):
            in_pii_trailer = True
            continue
        if in_pii_trailer:
            continue
        # per-line standalone shape identifiers
        for pii_type, snippet in scan_line(line):
            results.append((i, pii_type, snippet))
    return results


# --------------------------------------------------------------------------- #
# Delivered-surface (non-sidecar) PII scan — US-001
#
# The sidecar-body scan above deliberately skips header blocks and only looks at
# OCR clinical text. But the pipeline ALSO ships machine/human artifacts that are
# NOT sidecars — INDEX.md, source_inventory.json, the .rename_plan/.phase1_sources
# dotfiles, update_log.json, and the patient-facing 病情简要总结.html. A real run
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
    "high_risk_review.json",
    ".rename_plan.json",
    ".phase1_sources.json",
    "update_log.json",
    "病情简要总结.html",
    "AGENTS.md",  # agent-facing recall pointer; embeds profile.json one_line_condition — shipped, so scan it
    # visit-prep ships its patient-facing HTML into the same patient_dir; it is gated by
    # validate_visit_prep_html.py at production time, but the export boundary (export_share →
    # validate_structured_outputs) must ALSO shape-scan it so a later standalone export can't
    # ship un-rescanned PII. (Its data JSON visit_prep_data.json is intermediate render state.)
    "就诊准备包.html",
]

# Synthesized downstream surfaces — built by Phase 2 from the masked sidecars, then read
# by downstream sub-skills AND shipped by export_share.py. A real run leaked the 患者
# 身份证 + 手机 (pure SHAPES) into case_text.md and the real name into profile.json's
# mis-named `name_redacted` field — and NEITHER was scanned, because they are neither
# bucket sidecars nor in DELIVERED_SURFACES. The deterministic shape floor now scans
# them too (closes the shape/denylist export hole). NOTE: purely-SEMANTIC leaks here
# (出生地/籍贯/职业/民族 — no shape signature) are still Layer-1's job (pii-rescan-prompt.md);
# this floor only adds the shape/denylist backstop on these files.
SYNTHESIZED_SURFACES = [
    "case_text.md",
    "profile.json",
    "patient_summary.json",
    "timeline.md",
    "review_summary.md",
    "review_flags.md",
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
    (list of strings, or {"tokens":[...]}), written by Phase-1 before it masks; and
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


def load_system_locators(patient_dir: Path) -> set[str]:
    """Return archive-generated pseudonymous IDs that are safe shape exceptions.

    The loose numeric-ID backstop must not reject a legitimate ``SRC-`` whose
    hash prefix happens to contain only digits.  Only values derived from the
    protected Phase-0 manifest / pinned run state are trusted here; arbitrary
    tokens found in delivered prose do not gain an exception.
    """
    tokens: set[str] = set()
    if re.fullmatch(r"PT-[A-F0-9]+(?:_\d+)?", patient_dir.name):
        tokens.add(patient_dir.name)
    for name in ("phase0_manifest.json", ".organize_run.json"):
        path = patient_dir / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if name == "phase0_manifest.json" and isinstance(data, dict):
            for row in data.get("sources", []):
                if not isinstance(row, dict):
                    continue
                for key in ("source_id", "file_id"):
                    value = row.get(key)
                    if isinstance(value, str) and value:
                        tokens.add(value)
        elif isinstance(data, dict):
            value = data.get("run_id")
            if isinstance(value, str) and value:
                tokens.add(value)
    return tokens


def scan_delivered_file(path: Path, deny_tokens: set[str], apply_filename_name: bool = True,
                        drop_numeric_id: bool = False,
                        system_locators: set[str] | None = None) -> list[tuple[int, str, str]]:
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
        shape_line = line
        for token in sorted(system_locators or (), key=len, reverse=True):
            shape_line = shape_line.replace(token, "[SYSTEM_LOCATOR]")
        for pii_type, snippet in scan_line(shape_line):
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
    system_locators = load_system_locators(patient_dir)
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
                system_locators=system_locators,
            )
            if findings:
                out[name] = findings
    return out, deny_tokens


def collect_sidecars(target: Path) -> list[Path]:
    if target.is_file() and target.suffix.lower() == ".md":
        return [target]
    if not target.is_dir():
        return []
    # Phase-1 invokes the gate as `pii_rescan.py "$patient_dir/ocr"` — i.e. the
    # target IS the staging dir. Scan its *.md directly (without this, the dir-arg
    # path below would look for a nonexistent <ocr>/ocr/ child and scan nothing).
    if target.name == "ocr":
        return sorted(target.glob("*.md"))
    # A leftover / re-created ocr/ staging dir MUST NOT short-circuit the bucket
    # scan. It used to `return` here, which meant every post-Phase-2 sidecar went
    # unscanned while the gate still printed "PII rescan ... all pass" — a
    # fail-OPEN that a bare `mkdir ocr` was enough to trigger. Union, never return.
    out: list[Path] = []
    ocr_dir = target / "ocr"
    if ocr_dir.is_dir():
        out.extend(sorted(ocr_dir.glob("*.md")))
    # post-Phase-2: sidecars co-located in NN_ buckets
    buckets = sorted(target.glob("[0-9][0-9]_*"))
    for b in buckets:
        if b.is_dir():
            out.extend(sorted(b.rglob("*.md")))
    # 段C conversation notes carry the VERBATIM user chat quote (possible name / MRN /
    # phone). They normally live under <NN_bucket>/conversation_notes/ (already covered
    # above), but a lazy-archive misfile can drop them at a ROOT conversation_notes/
    # with no NN_ prefix — scan conversation_notes/*.md WHEREVER it lands so a 段C note
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


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: pii_rescan.py <patient_dir|sidecar_dir|sidecar.md> [...]", file=sys.stderr)
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
                "\nGATE FAILED (sidecar body): plaintext PII residue survived Phase-1 "
                "redaction. Re-read each flagged line in context, mask the PII token(s) to "
                f"{MASK_TOKEN} (clinical chars untouched — §2.2a / §2.4), and re-run "
                "this gate until findings=0 BEFORE proceeding to Phase 2.",
                file=sys.stderr,
            )
        if delivered_total:
            print(
                "\nGATE FAILED (delivered surface): PII leaked into a shipped index/"
                "provenance/HTML artifact (filename, absolute path, account, or a "
                "deny-listed identity token). These are NOT fixed by re-masking a "
                "sidecar. Fix at the PRODUCER: use the de-identified raw handle (the "
                "Phase-1 de-id raw filename / source_id) in original_path / raw_path / "
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
