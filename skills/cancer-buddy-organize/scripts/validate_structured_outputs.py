#!/usr/bin/env python3
"""Total acceptance gate for a finished organize run.

This script is the single deterministic form gate the orchestrator runs after 段 2 (and
after 摘要渲染 HTML generation) to decide "is this patient_dir actually done?". It does
NOT make any medical or content judgement — every check here is a *form/безопасность*
invariant that is fixed regardless of which patient was processed. The LLM still
owns ingestion / narrative / classification; this gate only verifies the deterministic
products line up. Native/deterministic extraction and independent human/second-read review remain upstream
requirements; an LLM is not treated as the sole character source.

Gate sections (each contributes to one aggregated exit code):

  [1] Structured JSON schema + anchor:
      For each present structured output (patient_summary / timeline / molecular /
      treatment_lines / labs / comorbidities / missing_items, plus the conditional
      longitudinal_observations when the patient has timeseries/trended data),
      validate against references/schemas/<name>.schema.json (Draft 2020-12 via
      jsonschema>=4.18, with a lighter fallback when jsonschema is absent) and
      verify every source_refs[] / source_ref anchor resolves to an existing
      markdown file. A file that is absent is skipped (longitudinal is optional).

  [2] PII residue rescan — Layer 2 (pii_rescan.py, deterministic SHAPE floor):
      Independently re-scan every text-masked MD sidecar, the delivered
      (non-sidecar) surfaces (DELIVERED_SURFACES — INDEX.md / source_inventory.json /
      update_log.json / 病情简要总结.html),
      AND the synthesized surfaces (SYNTHESIZED_SURFACES — case_text.md / profile.json /
      patient_summary.json / timeline.md / review_summary.md / review_flags.md) for
      pure-SHAPE leaks (身份证/手机/座机/email/SSN/≥11位数字/绝对路径/云账号/deny-list
      token, seeded from raw/ filenames; the loose ≥11-digit shape is suppressed on the
      synthesized surfaces to avoid false-firing on de-identified raw-filename timestamps).
      This is the deterministic, zero-network half of the two-layer PII gate. The PRIMARY,
      generalizing half is Layer 1 — the semantic agent scan
      (references/pii-rescan-prompt.md), dispatched by the orchestrator at the 段 3
      gate point, which catches label/semantic categories (姓名/出生地/职业/家属名/
      签名/检验号…) over the same surfaces. This script enforces only Layer 2; the
      orchestrator enforces Layer 1 separately. Text-only; no OCR/image dependency.

  [2b] Lab source-shape + NORMALIZATION CONSISTENCY — deterministic, no medical judgement.
      Note the name: it compares labs.json `value` with the `raw_value` beside it, which
      the same pass wrote, so it proves normalization invented nothing and proves nothing
      about whether the page was read right. The cross-source half is [2c]
      gate_field_provenance, which checks raw_value against the transcript it came FROM.

  [2c] Lab source-shape integrity — deterministic, no medical judgement:
      verifies that every extracted result keeps its own date, unit, reference
      range, report flag, provenance and source refs. It never calculates an
      abnormal flag or compares a patient value with a clinical threshold.

  [3] Source inventory:
      source_inventory.json MUST exist and every content unit must have a
      text-masked MD sidecar plus a raw_path back to its verbatim original in raw/.
      Organization preserves source bytes under host access control; retention and
      sharing are governed separately. There is no image-level source-redaction gate. Sources
      cited by formal outputs must be persist:true with a co-located .md sidecar
      in its bucket (the original itself lives once in raw/, never copied into a bucket).

  [3b] Bucket-taxonomy enforcement (gate_bucket_taxonomy, CB-P0-1) —
      deterministic, no medical judgement: every top-level `NN_` domain dir and
      every typed sub-bucket one level down MUST be a pinned slug (zh OR en) from
      references/bucket_taxonomy.json (mirror of bucket-taxonomy.md §1.1/§1.1a).
      Non-pinned dirs (a classifier echoing an incoming source-folder name, an
      off-taxonomy domain) are collected as violations and FAIL, each printed
      with the pinned slug expected for its NN prefix.

  [3c] Molecular-report transcription coverage — deterministic WARN only. Empty
      structured sections prompt comparison with the report's own table of
      contents; the gate does not assume a report should contain germline, PGx,
      VUS, or any particular gene.

  [3e] Open-world gates (organize v3 / taxonomy scheme_version 4):
      gate_extracted_fields  — extracted_fields.json is schema-validated; every
        lab/molecular entry must carry its unit (lab) and verbatim
        source_reported_text; every open_ref.source_id must exist in
        source_inventory.json; and NO formal JSON may cite it (Q8 — it is not a
        legal source library for charts or core-completeness).
      gate_clinical_class_completeness — the molecular/lab completeness floors key
        off inventory `clinical_class`, not off the bucket path, so a novel gene
        panel filed under 15_未分类资料/ can no longer slip past them silently.
      gate_high_risk_denominator — the set of high-risk fields is RECOMPUTED from the
        archive's own page frontmatter through scripts/_high_risk.py and the inventory's
        high_risk_fields[] must cover it. Every other high-risk check verifies the quality
        of a declared claim; this one verifies that the claim set is complete, which is
        what stops `high_risk_fields: []` from being the cheapest way to pass all of them.
      gate_settled_wording — the retired `settled_fact` / `settled_via` vocabulary (A23)
        may not reappear on any delivered surface.
      gate_transcripts — every inventory row that declares a transcript_path must
        have that file on disk under raw/transcript/; the bucket sidecar beside it
        must not carry unmasked PII shapes; and raw/transcript/ must never be
        referenced from anything outside raw/.
      gate_projection_coverage — readiness.json.projection_coverage must exist and
        cover every inventory source_id, with summary numbers matching per_source.
      gate_review_flag_audience — every review flag declares an audience, and the
        four QC categories are pinned to internal_qc so transcription noise can
        never be rendered to a family as 「请医生确认」.

  [4] Case-summary HTML shape (validate_case_summary_html.py):
      If 病情简要总结.html exists, it must pass the shape+provenance invariants
      against references/templates/case-summary.template.html — including the
      template_sha provenance proving it was machine-rendered (not hand-written).

Usage:
    python3 scripts/validate_structured_outputs.py <patient_dir>
    python3 scripts/validate_structured_outputs.py --help

Exit codes:
    0  — every REQUIRED artifact exists and every artifact present passed every gate.
         FOUR things are required and their absence is a failure, because each absence
         used to disable checks rather than fail them:
           * readiness.json — carries review_flags[] + projection_coverage; deleting it
             used to switch off three gates at once;
           * update_log.json (B7) — the only record of which run added what and whether
             the semantic PII pass ran; deleting it used to erase a deferred-PII debt
             along with the history that owed it;
           * source_inventory.json's `scheme_version` declaration (B4) — omitting it used
             to be READ as "legacy 3", which skipped every open-world gate;
           * the jsonschema library itself — without it every schema-level gate silently
             degrades to a two-key existence check, which is not a weaker pass but no
             pass at all.
         Everything else that is absent is skipped, never failed
         (longitudinal_observations.json, extracted_fields.json, gap_asks.json, the
         摘要渲染 HTML …). Exit 0 therefore means "nothing required is missing and nothing
         present is malformed", NOT "the archive is complete" — completeness is
         readiness.json.projection_coverage's job, and WARNs printed above the verdict do
         not change the code.

         A scheme-3 archive (source_inventory.json EXPLICITLY declaring scheme_version 3)
         is read against the v3 contract: the open-world gates are SKIPPED and a single
         WARN says so and names scripts/migrate_v3_to_v4.py. Exit 0 on such an archive
         means "readable", not "checked against the v4 floors". An archive that declares
         nothing is not that case and is not read leniently — see B4 above.
    1  — at least one gate failure
    2  — bad invocation
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import unicodedata
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = REPO_ROOT / "references" / "schemas"
CASE_SUMMARY_TEMPLATE = REPO_ROOT / "references" / "templates" / "case-summary.template.html"
# The case-summary deliverable keeps a single, language-INDEPENDENT filename across
# all locales — only the scaffold *inside* the HTML localizes (SKILL.md §i18n,
# case-summary-html-prompt.md). This mirrors the `NN_` bucket-prefix policy
# (SKILL.md:78): a stable key downstream can match on, never a per-locale string.
# The renderer (SKILL.md 摘要渲染 `--out`) writes this exact name, so this gate's
# literal stays in lock-step with the producer — do not localize one without the other.
CASE_SUMMARY_HTML_NAME = "病情简要总结.html"
CASE_SUMMARY_DATA_NAME = ".case_summary_data.json"
SOURCE_INVENTORY_NAME = "source_inventory.json"
EXTRACTED_FIELDS_NAME = "extracted_fields.json"
READINESS_NAME = "readiness.json"
UPDATE_LOG_NAME = "update_log.json"
# The verbatim per-page transcription vault. It sits under raw/ so it inherits raw/'s
# host access control; nothing outside raw/ may reference it and export refuses it.
TRANSCRIPT_PREFIX = "raw/transcript/"
# Domain 15 is the OPEN archive. It is deliberately NOT anchorable (Q7): formal JSON
# cites 01_..14_ only, and open fields carry their own extracted_fields open_ref.
OPEN_DOMAIN_NN = "15"
_OPEN_DOMAIN_ANCHOR_RE = re.compile(r"^15_")
# review-flag categories that are QC noise by construction: they describe how the
# archive was READ, never what a clinician should decide. Pinning them to internal_qc
# is what stops a decimal-point disagreement reaching a family as 「请医生确认」.
INTERNAL_QC_ONLY_CATEGORIES = {
    "transcription_disagreement",
    "ocr_artifact",
    "untrusted_content_marker",
    "pii_semantic_deferred",
}
# Independent-channel vocabulary, mirrored from source_inventory.schema.json.
REREAD_CHANNELS = {
    "text_layer", "barcode", "deterministic_ocr", "alternate_vision_model", "human", "none",
}
FAITHFULNESS_METHODS = {"native_text_identity", "vision_second_read", "sampled_reread"}
# text_layer_kind values for which `reread_channel: text_layer` is a REAL independent
# channel. The gate excludes exactly two: `absent` (no text layer exists) and
# `embedded_ocr` (the layer is a scanner's own OCR of the same pixels). `not_applicable`
# is included because a unit with no page raster — VCF, DICOM header, timeseries payload
# — gets its characters from a deterministic adapter, and that IS independent of vision.
TEXT_LAYER_CHANNEL_KINDS = {"born_digital", "not_applicable"}
PII_SEMANTIC_STATES = {"clean", "deferred", "failed"}
RUN_MODES = {"full", "incremental", "conversation_incremental", "migration"}
# read_modes whose characters came out of a model. They are the ones that MUST declare
# a transcript_path (schema if/then + gate_transcripts): omitting it used to skip every
# transcript assertion, which made "no transcript declared" cheaper than a checkable one.
MODEL_VISION_READ_MODES = {"model_vision_primary", "model_vision_assist"}


def _legacy_transcript_exempt(entry) -> bool:
    """C3 — is this row the one migration case that has no page to go back to?

    `legacy_transcript_unavailable: true` is written by scripts/migrate_v3_to_v4.py and
    by nothing else. It marks a scheme-3 row whose characters a MODEL read at a time when
    no per-page transcript was kept. Four gates would otherwise demand of it something
    that cannot exist:

      * gate_transcripts — a transcript_path pointing at a file nobody ever wrote;
      * gate_high_risk_denominator — a recomputed high-risk set the row must cover with
        second-read records, when the second read would have to re-open pages that are
        no longer transcribed anywhere;
      * gate_faithfulness — a faithfulness-*.json span into that same absent page;
      * gate_human_sample — a spot-check plan over fields nobody can sample.

    The first was already exempt (B6). The other three are exempt here, and they are
    exempt for the SAME reason and at the SAME price: migration rewrites metadata, it
    does not re-read documents, so demanding evidence of a re-read would make every
    pre-v4 archive permanently unmigratable — the archive would have to fabricate the
    records or stay on a scheme nothing validates.

    The price is NOT waived, only moved. gate_projection_coverage counts every such row
    in `projection_coverage.summary.unreadable_sources` and requires a `review_flag` with
    `category: coverage_gap` — and, since C3, says so even when readiness.json is absent
    or unreadable, so the exemption can never be collected in silence. What the flag buys
    is quiet about a FILE that was never written; what it can never buy is quiet about
    the fact that these pages can no longer be checked by anyone.
    """
    return isinstance(entry, dict) and entry.get("legacy_transcript_unavailable") is True
FORMAL_MARKDOWN_FILES = ("timeline.md", "case_text.md", "review_summary.md", "review_flags.md")
# Q7 is an ANCHOR rule, not a JSON rule: a settled fact resting on 15_ is the same
# contract breach whether it was written as a source_refs[] entry or as a [[src:15_…]]
# in prose a consumer follows. INDEX.md is included because it is the archive's own
# routing surface — the first thing a bare session reads.
ANCHOR_SCAN_MARKDOWN_FILES = FORMAL_MARKDOWN_FILES + ("INDEX.md",)
UPDATE_LOG_SCHEMA = "update_log.schema.json"
HUMAN_SAMPLE_PLAN_NAME = "human_sample_plan.json"
HUMAN_SAMPLE_RESULT_NAME = "human_sample_result.json"
HUMAN_SAMPLE_PLAN_SCHEMA = "human_sample_plan.schema.json"
HUMAN_SAMPLE_RESULT_SCHEMA = "human_sample_result.schema.json"
# The spot-check verdict vocabulary (B11 / R3 P1-10), mirrored from
# human_sample_result.schema.json. `unreadable` is the load-bearing third value: a cell
# the checker could not make out is NOT a match, and folding it into one used to turn an
# unverifiable field into a verified one at zero cost.
HUMAN_SAMPLE_VERDICTS = {"match", "mismatch", "unreadable"}
# run_modes that may legally carry pii_semantic: deferred (B5). `incremental` earns it by
# adding only native_text sources (a pure text increment can be audited later);
# `migration` earns it by adding no source characters AT ALL — migrate_v3_to_v4.py
# rewrites metadata in place, so there is nothing new to semantically scan and the debt
# it records is the pre-existing archive's, not the migration's. Both must still write the
# readiness flag: an unwritten debt is indistinguishable from a pass nobody ran.
PII_DEFERRABLE_RUN_MODES = {"incremental", "migration"}
# A23 regression guard (B19). `settled_fact` / `settled_via` were the pre-v4 way of saying
# 「this value was double-checked」, and they are banned because they name a CONCLUSION with
# no channel attached. The only surviving `settled` in the contract is
# extracted_fields.json's own `open_verification_status`, which this pattern does not
# match: the two banned tokens are compound, the permitted one is the bare word.
_SETTLED_WORDING_RE = re.compile(r"settled_fact|settled_via")
GAP_ASKS_NAME = "gap_asks.json"
GAP_ASKS_SCHEMA = "gap_asks.schema.json"
# The staging dir for masked page transcriptions. 段 2 moves every page into its bucket
# and then removes the directory; a finished archive therefore has NO ocr/ at all.
OCR_STAGING_DIR = "ocr"
_MTIME_EPS = 1e-9

# Make sibling gate modules importable (pii_rescan / validate_case_summary_html).
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

STRUCTURED_FILES = {
    "patient_summary.json": "patient_summary.schema.json",
    "timeline.json": "timeline.schema.json",
    "molecular.json": "molecular.schema.json",
    "treatment_lines.json": "treatment_lines.schema.json",
    "labs.json": "labs.schema.json",
    "comorbidities.json": "comorbidities.schema.json",
    # Conditional output: only written when the patient has timeseries / trended
    # data (wearable / PRO / lab trends). validate_one() skips it when absent, so
    # a patient with no longitudinal data never fails this gate; when present it
    # is schema-validated like every other structured output.
    "longitudinal_observations.json": "longitudinal_observations.schema.json",
    "missing_items.json": "missing_items.schema.json",
    "readiness.json": "readiness.schema.json",
}

ANCHOR_RE = re.compile(
    r"^(([0-9]{2}_[^\s/]+(/[^\s/]+)*\.md(#L\d+(-L\d+)?|#[A-Za-z0-9_-]+)?)|(conversation:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?))$"
)
MD_SRC_RE = re.compile(r"\[\[src:([^\]]+)\]\]")

try:
    from jsonschema import Draft202012Validator  # type: ignore

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# The high-risk DENOMINATOR (B1). scripts/_high_risk.py is the single authority, shared
# with scripts/plan_second_read.py — the planner decides what to re-read and this gate
# decides what MUST have been re-read, and those two answers have to come out of the same
# table or the difference between them is just drift. Import failure is not survivable:
# without it gate_high_risk_denominator cannot compute the set it exists to compare
# against, and a reconciliation with an empty left-hand side always passes.
try:
    import _high_risk  # noqa: E402  (sibling module; sys.path was extended above)

    HAS_HIGH_RISK = True
    _HIGH_RISK_IMPORT_ERROR = ""
except Exception as _exc:  # pragma: no cover - environment defect
    HAS_HIGH_RISK = False
    _HIGH_RISK_IMPORT_ERROR = str(_exc)


# --------------------------------------------------------------------------- #
# [1] structured JSON schema + anchor (ORIGINAL behavior, preserved verbatim)
# --------------------------------------------------------------------------- #
def collect_source_refs(obj, path="$"):
    """Yield (jsonpath, anchor) tuples for every source_refs / source_ref entry in `obj`.

    Most structured files carry a plural `source_refs: [...]` per fact; the
    longitudinal_observations store carries a singular `source_ref: "<anchor>"`
    per observation. Both are collected so their anchors are validated."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_refs" and isinstance(v, list):
                for i, ref in enumerate(v):
                    yield f"{path}.source_refs[{i}]", ref
            elif k == "source_ref" and isinstance(v, str):
                yield f"{path}.source_ref", v
            yield from collect_source_refs(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from collect_source_refs(item, f"{path}[{i}]")


SOURCE_REF_PREFIX = "source:"


def _is_legal_source_ref(ref) -> bool:
    """The three forms a review flag / structured output may use (A39).

    A bucket anchor, `source:<source_id>`, or null. A bare repo-relative path such as
    `AGENTS.md#L61` is deliberately NOT one: it names a file in the tree rather than a
    filed clinical source, so a consumer following it lands somewhere with no inventory
    row, no provenance layer and no verification status.
    """
    if ref is None:
        return True
    if not isinstance(ref, str):
        return False
    return bool(ANCHOR_RE.match(ref)) or ref.startswith(SOURCE_REF_PREFIX)


def validate_anchors(patient_dir: Path, data, fname: str, errors: list):
    known_sids = None
    for jpath, ref in collect_source_refs(data):
        # A39: a source_ref may legitimately be null. Forcing a string made producers
        # invent an anchor for a value that has none — a patient-reported figure, or a
        # 15_ open source that is deliberately not anchorable — and a fabricated anchor
        # is strictly worse than an honest absence.
        if ref is None:
            continue
        if not isinstance(ref, str):
            errors.append(f"{fname}: {jpath} is not a string: {ref!r}")
            continue
        # `source:<source_id>` points at an inventoried UPLOAD rather than at a filed
        # sidecar span. It is the honest form for open material: attributable, checkable
        # against the inventory, and incapable of pretending to be a citable location.
        if ref.startswith(SOURCE_REF_PREFIX):
            sid = ref[len(SOURCE_REF_PREFIX):].strip()
            if known_sids is None:
                known_sids = {
                    s for s in (_entry_id(e) for e in _inventory_entries(patient_dir)) if s
                }
            if not sid:
                errors.append(f"{fname}: {jpath} is an empty source reference: {ref!r}")
            elif known_sids and sid not in known_sids:
                errors.append(
                    f"{fname}: {jpath} → {ref}: no row with source_id {sid!r} in "
                    f"{SOURCE_INVENTORY_NAME} — a source: reference must name an inventoried "
                    "upload, or it is a pointer at nothing wearing a checkable shape"
                )
            continue
        if not ANCHOR_RE.match(ref):
            errors.append(
                f"{fname}: {jpath} does not match anchor regex: {ref!r}"
            )
            continue
        if ref.startswith("conversation:"):
            continue
        # Resolve and check existence (strip any #fragment)
        rel = ref.split("#", 1)[0]
        # Q7: domain 15 is an OPEN archive, not a citable clinical domain. Its
        # sub-bucket slugs are written by a model from untrusted source text, and its
        # contents are by definition material no pinned schema anticipated — so a
        # formal output must never rest a fact on one. The open projection carries its
        # own pointer instead (extracted_fields.json open_ref = {source_id, page, bbox}),
        # which anchors to the raw page image rather than to a model-named directory.
        if _OPEN_DOMAIN_ANCHOR_RE.match(rel):
            errors.append(
                f"{fname}: {jpath} → {rel}: 15_ is not anchorable; use "
                "extracted_fields.open_ref (open fields never enter a settled-fact surface)"
            )
            continue
        target = patient_dir / rel
        if not target.is_file():
            errors.append(
                f"{fname}: {jpath} dangling anchor — file not found: {rel}"
            )


# Legacy structured outputs that predate a schema bump. A pre-bump archive is not
# corrupt — it was correct under the contract in force when it was written — so it
# must stay READABLE (validate against the older shape) while being WARNed as due
# for a re-organize. Blocking it would strand every archive built before the bump.
# Map: file → {legacy schema_version: how to relax the current schema in memory}.
LEGACY_SCHEMA_VERSIONS = {
    # patient_summary v2 had no time anchors on demographics: `age` was a bare
    # scalar beside `sex`, which is exactly why cross-year reports collided into a
    # permanent `disputed`. v2.1 adds `*_as_of` + `age_observations[]` + `birth_year`.
    # A v2 archive can still be read — but its age/weight/ECOG carry no as-of date,
    # so a consumer cannot tell which report they came from. Hence: WARN + re-organize.
    "patient_summary.json": {
        "2": {
            "drop_required": {
                "demographics": ("age_as_of", "age_observations", "birth_year",
                                 "height_cm_as_of", "weight_kg_as_of", "ecog_as_of"),
            },
            "note": (
                "patient_summary.json is schema_version 2 (pre-time-anchor). "
                "demographics.age / weight_kg / height_cm / ecog carry no `_as_of` "
                "source date, so downstream cannot tell which report each value came "
                "from and must not present them as current. Re-run organize to upgrade "
                "to 2.1 (adds *_as_of + age_observations[] + birth_year)."
            ),
        }
    },
}


def _relax_readiness_v2(schema: dict) -> dict:
    """Relax readiness.schema.json to the shape a pre-v4 archive actually wrote.

    schema_version "2" predates three v4 fields, and an archive written before they
    existed is not corrupt — it was correct under the contract in force at the time.
    Blocking it would strand every archive built before the bump, which is why A13
    routes it here instead: read it leniently, WARN, and point at the migration
    script that fills the gaps deterministically (audience derived from category,
    projection_coverage generated as a conservative skeleton).

    Exactly four things are relaxed, and every other constraint — closed
    additionalProperties, types, the resolution_status enum — still applies:
      * review_flags[].audience stops being required (v3 had no such field);
      * review_flags[].category stops being enum-checked (v3 was free-form);
      * current_source_values[].source_ref drops its anchor pattern (v3 wrote bare
        strings);
      * projection_coverage stops being structurally pinned (v3 had none).
    """
    if isinstance(schema.get("properties", {}).get("schema_version"), dict):
        schema["properties"]["schema_version"] = {"type": "string"}
    flags = schema.get("properties", {}).get("review_flags", {}).get("items")
    if isinstance(flags, dict):
        if isinstance(flags.get("required"), list):
            flags["required"] = [f for f in flags["required"] if f != "audience"]
        fprops = flags.get("properties", {})
        if isinstance(fprops.get("category"), dict):
            fprops["category"].pop("enum", None)
        csv = fprops.get("current_source_values", {}).get("items", {})
        if isinstance(csv, dict):
            sref = csv.get("properties", {}).get("source_ref")
            if isinstance(sref, dict):
                sref.pop("pattern", None)
    cov = schema.get("properties", {}).get("projection_coverage")
    if isinstance(cov, dict):
        cov.pop("required", None)
        cov.pop("additionalProperties", None)
        cov.pop("properties", None)
    return schema


def _relax_source_inventory_v3(schema: dict) -> dict:
    """Relax source_inventory.schema.json to the pre-open-world (scheme 3) row shape.

    scheme 3 had no open world at all: no `kind`, no `clinical_class`, no
    `text_layer_kind`, no `transcript_path`, and it carried the free-form `doc_type`
    the v4 schema replaced with `doc_kind`. Those rows are readable — what they are
    not is checkable against the v4 floors, which is precisely what the WARN says.
    The conditional allOf rules are dropped with them: requiring a transcript_path of
    a scheme-3 row would be demanding a file the scheme never defined.
    """
    items = schema.get("properties", {}).get("files", {}).get("items")
    if isinstance(items, dict):
        if isinstance(items.get("required"), list):
            items["required"] = [
                f for f in items["required"] if f not in ("kind", "clinical_class")
            ]
        items.pop("allOf", None)
        props = items.get("properties")
        if isinstance(props, dict):
            # scheme 3 wrote doc_type; additionalProperties:false would reject it.
            props.setdefault("doc_type", {"type": "string"})
    if isinstance(schema.get("properties", {}).get("scheme_version"), dict):
        schema["properties"]["scheme_version"] = {"type": "integer"}
    return schema


# A13: a v3 archive stays READABLE. Detection is per-file and keyed on the version the
# file itself declares — source_inventory by `scheme_version` (absent or 3),
# readiness by `schema_version` "2" — because those are the only two self-descriptions
# that exist before a migration has run. Each entry names the relax function and the
# WARN text; the WARN always names scripts/migrate_v3_to_v4.py, since "read leniently"
# is a grace period, not a resting place.
LEGACY_ARCHIVE_SCHEMAS = {
    SOURCE_INVENTORY_NAME: {
        "version_key": "scheme_version",
        # B4: (3,) — NOT (None, 3). An inventory that omits scheme_version is not an old
        # archive, it is an archive that did not say, and the two used to be the same
        # thing here: deleting one line silently relaxed the whole v4 schema. Absence is
        # now its own ERROR in gate_scheme_version, which names both legal declarations.
        "legacy_values": (3,),
        "fn": _relax_source_inventory_v3,
        "note": (
            "source_inventory.json declares scheme_version 3 — the pre-open-world "
            "scheme with no kind / clinical_class / text_layer_kind / transcript_path. It is read "
            "against the v3 shape and the v4-only gates are skipped for it, so this archive is NOT "
            "being checked against the open-world floors. Run scripts/migrate_v3_to_v4.py to upgrade "
            "it to scheme 4"
        ),
    },
    READINESS_NAME: {
        "version_key": "schema_version",
        "legacy_values": ("2",),
        "fn": _relax_readiness_v2,
        "note": (
            "readiness.json declares schema_version 2 — it predates review_flags[].audience, the "
            "category enum and projection_coverage. It is read against the v2 shape, which means "
            "unlabelled flags are NOT being caught here. Run scripts/migrate_v3_to_v4.py to upgrade "
            "it to schema_version 3"
        ),
    },
}


def _legacy_relax_for(fname: str, data) -> tuple:
    """Return (relax_fn, note) when `data` declares a legacy version, else (None, None)."""
    spec = LEGACY_ARCHIVE_SCHEMAS.get(fname)
    if not spec or not isinstance(data, dict):
        return None, None
    declared = data.get(spec["version_key"])
    if declared in spec["legacy_values"]:
        return spec["fn"], spec["note"]
    return None, None


_LEGACY_ARCHIVE_CACHE: dict = {}


def archive_is_legacy_v3(patient_dir: Path) -> bool:
    """True when the ARCHIVE (not one file) was written against taxonomy scheme 3.

    Keyed on source_inventory.json's own `scheme_version`, because that is the
    archive's self-description. This is the gate-level switch, deliberately separate
    from the file-level schema relaxation above: a v4 archive whose readiness.json
    still says "2" gets a lenient READ of that one file and full-strength gates
    everywhere else. A missing or unparseable inventory is NOT legacy — that case has
    its own hard error and must not buy leniency by being broken.

    B4: the declaration must be EXPLICIT. `scheme_version` absent used to mean "legacy",
    which made the entire open-world gate set — open-domain filing, clinical_class floors,
    per-field second-read independence, human spot-check, faithfulness coverage,
    projection coverage, review-flag audience, field provenance, the denominator
    reconciliation — skippable by deleting a single key from a JSON file. That is the
    cheapest bypass a gate can have, and it looked like backward compatibility.
    Un-declared is now an ERROR of its own (gate_scheme_version), never a free pass.
    """
    inv = patient_dir / SOURCE_INVENTORY_NAME
    try:
        key = (str(inv), inv.stat().st_mtime_ns, inv.stat().st_size)
    except OSError:
        return False
    if key in _LEGACY_ARCHIVE_CACHE:
        return _LEGACY_ARCHIVE_CACHE[key]
    try:
        data = json.loads(inv.read_text(encoding="utf-8"))
    except Exception:
        _LEGACY_ARCHIVE_CACHE[key] = False
        return False
    verdict = isinstance(data, dict) and data.get("scheme_version") == 3
    _LEGACY_ARCHIVE_CACHE[key] = verdict
    return verdict


def inventory_unparseable(patient_dir: Path) -> bool:
    """True when source_inventory.json exists but is not readable JSON.

    Every open-world gate reads the inventory through _inventory_entries(), which
    returns [] on a parse failure. That turned one broken file into a SILENT pass of
    the clinical_class floors, the open_ref orphan check and the coverage reconciliation
    at once. The gates now ask this question first and say out loud that they could not
    run, instead of reporting nothing and being mistaken for clean.
    """
    inv = patient_dir / SOURCE_INVENTORY_NAME
    if not inv.is_file():
        return False
    try:
        json.loads(inv.read_text(encoding="utf-8"))
    except Exception:
        return True
    return False


def _blocked_by_unparseable_inventory(patient_dir: Path, gate: str, errors: list) -> bool:
    if inventory_unparseable(patient_dir):
        errors.append(
            f"{gate}: {SOURCE_INVENTORY_NAME} is not parseable JSON, so this gate could not run. "
            "An unreadable inventory is not an empty one — fix the file and re-run; until then "
            "every inventory-keyed floor below is UNCHECKED, not passed"
        )
        return True
    return False


# The two row keys scheme 4 added and scheme 3 never had. They are the discriminator for
# a HALF-migrated archive: a header that says 4 over rows still written to 3.
V4_REQUIRED_ROW_KEYS = ("kind", "clinical_class")


def gate_scheme_version(patient_dir: Path, errors: list) -> None:
    """The archive must SAY which contract it was written to (B4, R3 P0-4 / P2-5).

    Two failures used to be one silence.

      * `scheme_version` absent. It was read as "legacy 3", so every v4-only gate skipped
        itself — the open-world floors, the second-read independence checks, the coverage
        reconciliation, all of it — and the archive still exited 0 with one WARN. Deleting
        a single key was the cheapest possible bypass of the entire open-world half of
        this script, and it wore the costume of backward compatibility. It is now an
        ERROR that names both legal answers, because an archive whose contract nobody
        declared cannot be checked against either one.

      * `scheme_version: 4` over rows that are still scheme 3 (no `kind`, no
        `clinical_class`). That is a MIXED archive: the header claims the full contract,
        the rows cannot satisfy it, and the schema violations it produces read as a dozen
        unrelated defects rather than as one unfinished migration. The ERROR here says
        what it actually is and names the command that fixes it.
    """
    inv = patient_dir / SOURCE_INVENTORY_NAME
    if not inv.is_file():
        return  # gate_source_inventory owns presence
    try:
        data = json.loads(inv.read_text(encoding="utf-8"))
    except Exception:
        return  # inventory_unparseable owns parse failures
    if not isinstance(data, dict):
        return
    declared = data.get("scheme_version")
    if declared is None:
        errors.append(
            f"{SOURCE_INVENTORY_NAME}: no scheme_version — declare `scheme_version: 4` (or 3 for a "
            "genuine pre-v4 archive). An omitted version used to be READ as 3, which skipped every "
            "open-world gate at once: open-domain filing, the clinical_class floors, per-field "
            "second-read independence, the human spot-check, faithfulness coverage, projection "
            "coverage, review-flag audience, field provenance and the high-risk denominator "
            "reconciliation. Silence is not a version, and it must not be the cheapest way to pass"
        )
        return
    if declared != 4:
        return  # 3 is handled by the legacy branch; anything else is a schema enum error

    rows = data.get("files")
    incomplete: list[str] = []
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        lacking = [k for k in V4_REQUIRED_ROW_KEYS if k not in row]
        if lacking:
            rid = row.get("source_id") or row.get("file_id") or f"files[{i}]"
            incomplete.append(f"{rid} (no {'/'.join(lacking)})")
    if incomplete:
        errors.append(
            f"{SOURCE_INVENTORY_NAME}: declares scheme_version 4 but {len(incomplete)} row(s) are "
            f"still scheme-3 shaped: {', '.join(incomplete[:6])}"
            f"{' …' if len(incomplete) > 6 else ''}. This is a HALF-migrated archive, not a broken "
            "one — the header promises the open-world contract that the rows cannot answer to, so "
            "the schema violations below are one unfinished migration wearing a dozen faces. Run "
            "`python3 scripts/migrate_v3_to_v4.py <patient_dir> --force` to fill the v4 row fields "
            "deterministically (kind from read_mode, clinical_class from the bucket number), then "
            "re-run this gate"
        )

    # C12: appended AFTER the half-migration diagnosis above, because when an archive is
    # both half-migrated and carrying a stale readiness.json, the row-shape ERROR is the
    # one that explains the pile of schema violations below it and must stay first.
    # The two version keys must agree about which generation this archive IS. A v4
    # inventory over a readiness.json still declaring schema_version "2" was a WARN, and
    # a WARN is the wrong verdict because the v2 shape is precisely the one with no
    # review_flags[].audience, no category enum and no projection_coverage — the fields
    # three gates read. So the archive claimed the current contract on the surface that
    # files documents, and kept the pre-v4 shape on the surface that declares what a
    # human must look at, and the combination was passable. Half a migration is not a
    # version; it is a v4 archive whose review surface nobody is checking.
    readiness_path = patient_dir / READINESS_NAME
    if readiness_path.is_file():
        try:
            rd = json.loads(readiness_path.read_text(encoding="utf-8"))
        except Exception:
            rd = None
        if isinstance(rd, dict) and rd.get("schema_version") == "2":
            errors.append(
                f"{SOURCE_INVENTORY_NAME} declares scheme_version 4 but {READINESS_NAME} still "
                'declares schema_version "2" — a MIXED archive, not a legacy one. Schema 2 is the '
                "readiness shape that predates review_flags[].audience, the category enum and "
                "projection_coverage, i.e. exactly the fields gate_review_flag_audience and "
                "gate_projection_coverage read. Reading it leniently (which is what used to "
                "happen, with a WARN) left a CURRENT archive's review surface unchecked, so QC "
                "noise could still reach a family as 「请医生确认」 and an unprojected source "
                'could go uncounted. Run `python3 scripts/migrate_v3_to_v4.py "<patient_dir>" '
                '--force` to bring readiness.json to schema_version "3", or declare the whole '
                "archive scheme_version 3 if it genuinely is one"
            )


def _relax_schema_for_legacy(schema: dict, relax: dict) -> dict:
    """Return an in-memory copy of `schema` accepting the legacy shape.

    Only two things are relaxed: the pinned `schema_version` const, and the
    `required` lists named in `drop_required`. Every other constraint — closed
    `additionalProperties`, types, enums, ranges — still applies, so a legacy
    archive is read leniently but never validated loosely.
    """
    legacy = copy.deepcopy(schema)
    # Substitute, never pop: every one of these schemas is additionalProperties:false,
    # so REMOVING the property definition turns the legacy value into "additional
    # property not allowed" — a confusing failure in the exact path that exists to make
    # old archives readable. Widening the constraint is what was meant.
    if isinstance(legacy.get("properties", {}).get("schema_version"), dict):
        legacy["properties"]["schema_version"] = {"type": "string"}
    for prop, fields in relax.get("drop_required", {}).items():
        block = legacy.get("properties", {}).get(prop)
        if isinstance(block, dict) and isinstance(block.get("required"), list):
            block["required"] = [f for f in block["required"] if f not in fields]
    return legacy


def validate_one(patient_dir: Path, fname: str, schema_name: str, errors: list,
                 warnings: list | None = None):
    path = patient_dir / fname
    if not path.is_file():
        return  # missing is OK — only validate what exists

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        errors.append(f"{fname}: not parseable JSON: {e}")
        return

    if HAS_JSONSCHEMA:
        schema_path = SCHEMA_DIR / schema_name
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            # A pre-bump archive is not corrupt — it was correct under the contract in
            # force when it was written. Blocking it would strand every archive built
            # before the bump, so it is read against the older shape and WARNed as due
            # for a re-organize (see LEGACY_SCHEMA_VERSIONS). Every other constraint —
            # closed additionalProperties, types, enums, ranges — still applies.
            legacy_note = None
            declared = data.get("schema_version") if isinstance(data, dict) else None
            legacy_map = LEGACY_SCHEMA_VERSIONS.get(fname, {})
            if isinstance(declared, str) and declared in legacy_map:
                relax = legacy_map[declared]
                schema = _relax_schema_for_legacy(schema, relax)
                legacy_note = relax.get("note") or f"{fname}: legacy schema_version {declared}"
            # A13: the v3/v4 split. A file that declares the older scheme is read
            # against the older shape and WARNed, never failed — the alternative is
            # stranding every archive written before the bump.
            relax_fn, archive_note = _legacy_relax_for(fname, data)
            # C12: the file-level relaxation is bought by the ARCHIVE's declaration, not
            # by this file's own. readiness.json at schema_version "2" inside an archive
            # that declares scheme_version 4 used to be read leniently and WARNed — which
            # meant review_flags[].audience, the category enum and projection_coverage
            # went unchecked on a CURRENT archive, and the only thing standing between a
            # clinician and an unlabelled QC flag was a warning line. A v4 archive is held
            # to v4 readiness; the mismatch is an ERROR in gate_scheme_version naming the
            # migration, and the schema below is applied at full strength.
            if (
                relax_fn is not None
                and fname == READINESS_NAME
                and not archive_is_legacy_v3(patient_dir)
            ):
                relax_fn, archive_note = None, None
            if relax_fn is not None:
                schema = relax_fn(copy.deepcopy(schema))
                legacy_note = archive_note
            validator = Draft202012Validator(schema)
            for err in validator.iter_errors(data):
                errors.append(
                    f"{fname}: schema violation at "
                    f"{'.'.join(str(p) for p in err.absolute_path) or '$'}: {err.message}"
                )
            if legacy_note is not None and warnings is not None:
                warnings.append(f"legacy_schema: {legacy_note}")
        except Exception as e:
            errors.append(f"{fname}: schema load failed for {schema_name}: {e}")
    else:
        # Light fallback: top-level required keys
        if not isinstance(data, dict):
            errors.append(f"{fname}: root must be object, got {type(data).__name__}")
            return
        for k in ("patient_code", "schema_version"):
            if k not in data:
                errors.append(f"{fname}: missing required top-level field {k}")

    validate_anchors(patient_dir, data, fname, errors)


def validate_doc_schema(fname: str, data, schema_name: str, errors: list,
                       warnings: list | None = None) -> None:
    if not HAS_JSONSCHEMA:
        if not isinstance(data, dict):
            errors.append(f"{fname}: root must be object, got {type(data).__name__}")
        return
    schema_path = SCHEMA_DIR / schema_name
    if not schema_path.is_file():
        errors.append(f"{fname}: schema file missing: {schema_name}")
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        # A13 v3/v4 split — see _legacy_relax_for. A pre-bump file is read against the
        # shape it was written to and WARNed as due for scripts/migrate_v3_to_v4.py.
        relax_fn, archive_note = _legacy_relax_for(fname, data)
        if relax_fn is not None:
            schema = relax_fn(copy.deepcopy(schema))
            if warnings is not None:
                warnings.append(f"legacy_schema: {archive_note}")
        for err in Draft202012Validator(schema).iter_errors(data):
            loc = ".".join(str(p) for p in err.absolute_path) or "$"
            errors.append(f"{fname}: schema violation at {loc}: {err.message}")
    except Exception as e:
        errors.append(f"{fname}: schema load failed for {schema_name}: {e}")


# Artifacts whose ABSENCE is itself a defect. Everything else in STRUCTURED_FILES is
# legitimately optional (a patient with no longitudinal data writes no
# longitudinal_observations.json), but readiness.json is where the archive declares what
# it does NOT have: review_flags[] and projection_coverage. Treating it as optional meant
# deleting one file silently disabled gate_projection_coverage, gate_review_flag_audience
# and its own schema validation at once — the cheapest bypass in the whole gate.
REQUIRED_STRUCTURED_FILES = (READINESS_NAME,)


def gate_structured(patient_dir: Path, errors: list, warnings: list | None = None) -> None:
    for fname in REQUIRED_STRUCTURED_FILES:
        if not (patient_dir / fname).is_file():
            errors.append(
                f"{fname}: missing — this is a REQUIRED product, not an optional one. It carries "
                "review_flags[] (what a human must look at) and projection_coverage (what was read "
                "but never reached a structured slot); with it absent, an archive that lifted "
                "nothing is indistinguishable from a complete one and three gates go silent"
            )
    for fname, schema_name in STRUCTURED_FILES.items():
        validate_one(patient_dir, fname, schema_name, errors, warnings)


# --------------------------------------------------------------------------- #
# [2] PII residue rescan
# --------------------------------------------------------------------------- #
def gate_pii_rescan(patient_dir: Path, errors: list) -> None:
    try:
        import pii_rescan  # sibling module
    except Exception as e:
        errors.append(f"pii_rescan: could not import gate module: {e}")
        return

    sidecars = pii_rescan.collect_sidecars(patient_dir)
    total = 0
    for sc in sidecars:
        findings = pii_rescan.scan_sidecar(sc)
        for line_no, pii_type, snippet in findings:
            total += 1
            loc = f"L{line_no}" if line_no else "(file)"
            try:
                rel = sc.relative_to(patient_dir)
            except ValueError:
                rel = sc
            errors.append(f"pii_rescan: {rel} {loc} [{pii_type}] {snippet!r}")
    if total:
        errors.append(
            f"pii_rescan: {total} plaintext-PII residue finding(s) in sidecars — "
            "re-mask to [PII_MASKED] (clinical chars untouched) and re-run"
        )

    # US-001: the sidecar scan above intentionally skips header blocks and only
    # covers OCR bodies. Delivered (non-sidecar) artifacts (DELIVERED_SURFACES —
    # INDEX.md / source_inventory.json / update_log.json / 病情简要总结.html)
    # AND synthesized surfaces (SYNTHESIZED_SURFACES —
    # case_text.md / profile.json / patient_summary.json / timeline.md / review_summary.md /
    # review_flags.md) are NOT exempt: real runs leaked the patient name (in a
    # `<name>-报告.pdf` filename copied into original_path), the uploader's cloud/email
    # account (absolute paths), AND 身份证 + 手机 into case_text.md / a real name into
    # profile.json. scan_delivered_surfaces scans both lists whole (Layer-2 shape floor),
    # seeded by a patient-identity deny-list.
    try:
        surfaces, _deny = pii_rescan.scan_delivered_surfaces(patient_dir)
    except Exception as e:
        errors.append(f"pii_rescan(delivered): could not scan delivered surfaces: {e}")
        surfaces = {}
    delivered_total = 0
    for name, findings in surfaces.items():
        for line_no, pii_type, snippet in findings:
            delivered_total += 1
            loc = f"L{line_no}" if line_no else "(file)"
            errors.append(f"pii_rescan(delivered): {name} {loc} [{pii_type}] {snippet!r}")
    if delivered_total:
        errors.append(
            f"pii_rescan(delivered): {delivered_total} PII leak(s) in shipped index/"
            "provenance/HTML artifacts — relativize paths / strip name-bearing basenames / "
            "coarse-grain the HTML so no identity, account, or absolute local path ships"
        )


# --------------------------------------------------------------------------- #
# [2b] lab source-shape integrity — deterministic, NO medical judgement
# --------------------------------------------------------------------------- #
def gate_lab_source_shape(patient_dir: Path, errors: list) -> None:
    labs_path = patient_dir / "labs.json"
    if not labs_path.is_file():
        return
    try:
        labs = json.loads(labs_path.read_text(encoding="utf-8"))
    except Exception:
        return  # the structured gate already reports parse failures
    panels = labs.get("panels") if isinstance(labs, dict) else None
    if not isinstance(panels, list):
        return

    for panel in panels:
        if not isinstance(panel, dict):
            continue
        analyte = panel.get("analyte", "<?>")
        for v in panel.get("values", []) or []:
            if not isinstance(v, dict):
                continue
            date = v.get("date", "?")
            required = ("unit", "reference_range", "report_flag", "critical_flag", "provenance_layer", "verification_status", "source_refs")
            missing = [key for key in required if key not in v]
            if missing:
                errors.append(
                    f"lab_source_shape: labs '{analyte}' {date} missing source-preserving key(s): "
                    + ", ".join(missing)
                )


# A number as a report may legitimately print it: optional sign, digits, optional
# decimal part, optional scientific exponent. The leading sign is only consumed when it
# is NOT preceded by a digit, so "3.5-9.5" tokenizes as a RANGE (3.5, 9.5) instead of
# (3.5, -9.5) — the old behavior, which reported "value 9.5 not found in 3.5-9.5".
_NUM_TOKEN_RE = re.compile(r"(?<![\d.])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_IMPOSSIBLE_NUM_RE = re.compile(r"(?<!\d)\d+\.\d+\.\d+(?!\d)")
_FULLWIDTH_MAP = str.maketrans("\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\uff0e\uff0d\uff1c\uff1e\uff05",
                               "0123456789.-<>%")
# Unit conversions that are pure arithmetic on the SAME quantity. Deliberately tiny and
# explicit: a blanket "try every power of ten" would make this check toothless, because
# a dropped decimal point (11.2 -> 112) is itself a power of ten. A factor is applied
# only when the SOURCE STRING carries a unit of its own that differs from the unit the
# row declares — i.e. only when a conversion demonstrably happened.
# key: (unit printed in raw_value, unit declared on the row) -> multiply raw by factor
_UNIT_FACTORS = {
    ("mg", "g"): 0.001,
    ("g", "mg"): 1000.0,
    ("ug", "mg"): 0.001,
    ("mg", "ug"): 1000.0,
    ("ml", "l"): 0.001,
    ("l", "ml"): 1000.0,
    ("10^9/l", "/ul"): 1000.0,
    ("/ul", "10^9/l"): 0.001,
    ("10^9/l", "10^3/ul"): 1.0,
    ("10^3/ul", "10^9/l"): 1.0,
    ("10^12/l", "10^6/ul"): 1.0,
    ("10^6/ul", "10^12/l"): 1.0,
}
_UNIT_TOKEN_RE = re.compile(
    r"(10\^(?:3|6|9|12)\s*/\s*[a-zA-Z\u00b5]+|[a-zA-Z\u00b5]+\s*/\s*[a-zA-Z\u00b5]+|[a-zA-Z\u00b5]+)"
)


def _norm_unit(u: str) -> str:
    """Lower-case, de-space and fold the micro sign so 'µL' and 'uL' are one unit."""
    return (
        u.strip().lower().replace(" ", "")
        .replace("\u00b5", "u").replace("\u03bc", "u")
        .replace("\u00d7", "x")
    )


def _numeric_candidates(raw_value: str, unit) -> set:
    """Every number this source string can be said to have PRINTED, as floats.

    Pure normalization bookkeeping, no clinical judgement: it answers "did the
    normalized value come from a number the source actually shows?", never "is this
    number plausible for a human?". Four legitimate transformations are recognised,
    because each was producing a false ERROR on correct data:
      * thousands separators and full-width digits ("12,500", "３.２１");
      * scientific notation ("1.2e3" -> 1200);
      * a percentage read as a fraction ("42.3%" -> 0.423) and back;
      * both ends of a printed range ("3.5-9.5") and comparator prefixes ("<0.5").
    Unit conversion is applied ONLY when the source string carries its own unit that
    differs from the declared one — see _UNIT_FACTORS for why that restraint matters.
    """
    probe = raw_value.replace(",", "").replace("\uff0c", "").replace("\u3000", " ")
    probe = probe.translate(_FULLWIDTH_MAP)
    tokens: list[float] = []
    for m in _NUM_TOKEN_RE.finditer(probe):
        try:
            tokens.append(float(m.group(0)))
        except ValueError:
            continue
    cands: set = set()
    for tok in tokens:
        cands.add(tok)
        cands.add(-tok)
    # percentage <-> fraction, only when the source actually prints a percent sign
    if "%" in probe:
        for tok in tokens:
            cands.add(tok / 100.0)
            cands.add(tok * 100.0)
    # unit conversion, only when the source prints a unit different from the row's
    declared = _norm_unit(unit) if isinstance(unit, str) else ""
    if declared:
        printed_units = {
            _norm_unit(m.group(0)) for m in _UNIT_TOKEN_RE.finditer(probe)
        }
        for pu in printed_units:
            factor = _UNIT_FACTORS.get((pu, declared))
            if factor is not None:
                for tok in tokens:
                    cands.add(tok * factor)
    return cands


def gate_numeric_integrity(patient_dir: Path, errors: list) -> None:
    """labs.json NORMALIZATION CONSISTENCY — deterministic, NO medical judgement.

    Read the name precisely: this gate compares `value` with the `raw_value` recorded
    beside it, and both of those were written by the SAME pass. It can therefore prove
    that normalization did not invent a number, and it can prove nothing whatsoever
    about whether the page was read correctly — when the page is misread, both fields
    are wrong together and this gate stays green. The earlier docstring called itself
    "transcription integrity", which was a claim it had no standing to make. The
    cross-source half of that question lives in gate_field_provenance, which checks
    raw_value against the transcript/masked sidecar the number was lifted FROM.

    Nothing here compares a value with a threshold, calculates an abnormal flag, or
    decides whether a number is plausible for a human — those are clinical judgements
    this gate is forbidden to make.

    Four legitimate normalizations are recognised (each was previously a false ERROR on
    correct data): scientific notation, percent↔fraction, both ends of a printed range,
    and an explicit unit conversion — see _numeric_candidates.
    """
    gate_lab_source_shape(patient_dir, errors)

    labs_path = patient_dir / "labs.json"
    if not labs_path.is_file():
        return
    try:
        labs = json.loads(labs_path.read_text(encoding="utf-8"))
    except Exception:
        return  # the structured gate already reports parse failures
    panels = labs.get("panels") if isinstance(labs, dict) else None
    if not isinstance(panels, list):
        return

    for panel in panels:
        if not isinstance(panel, dict):
            continue
        analyte = panel.get("analyte", "<?>")
        for v in panel.get("values", []) or []:
            if not isinstance(v, dict):
                continue
            date = v.get("date", "?")
            raw_value = v.get("raw_value")
            value = v.get("value")
            unit = v.get("unit")

            # A present-but-blank unit defeats the source-shape rule it pretends to satisfy.
            if isinstance(unit, str) and not unit.strip():
                errors.append(
                    f"numeric_integrity: labs '{analyte}' {date}: unit is present but blank — "
                    "use null when the report prints no unit, so the absence is visible"
                )

            if raw_value is None:
                errors.append(
                    f"numeric_integrity: labs '{analyte}' {date}: raw_value is null — a laboratory "
                    "row with no source-reported string cannot be checked against anything, by this "
                    "gate or by a human. The whole point of keeping raw_value beside value is that "
                    "the source layer survives normalization; null deletes the only evidence and "
                    "leaves a bare number that looks equally trustworthy"
                )
                continue
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue

            # "1.2.3" cannot be a number in any locale: it is a transcription artifact.
            bad = _IMPOSSIBLE_NUM_RE.search(raw_value)
            if bad:
                errors.append(
                    f"numeric_integrity: labs '{analyte}' {date}: raw_value contains an "
                    f"impossible numeric token {bad.group(0)!r} — re-read this field from "
                    "the source page (this is the decimal-point/phantom-glyph failure mode)"
                )

            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue  # non-numeric normalized values (e.g. "阴性") are not comparable
            cands = _numeric_candidates(raw_value, unit)
            if not cands:
                continue  # raw_value carries no number at all (e.g. "未检出") — nothing to compare
            target = float(value)
            tol = max(1e-9, abs(target) * 1e-9)
            if any(abs(c - target) <= tol for c in cands):
                continue
            errors.append(
                f"numeric_integrity: labs '{analyte}' {date}: normalized value {value!r} does "
                f"not appear in its own source-reported raw_value {raw_value!r} — normalization "
                "must not introduce a number the source never printed; keep the source value and "
                "record any conversion as an additive, labelled layer"
            )


# --------------------------------------------------------------------------- #
# [2c] field provenance — the CROSS-SOURCE half of numeric integrity (A19)
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


def _parse_page_frontmatter(text: str):
    """Return the page frontmatter as a dict, or None.

    Prefers ingest_transcripts.parse_frontmatter so the producer and this reader can
    never drift on the YAML subset they agree about; falls back to a minimal reader
    (JSON-valued keys only) when that module is unavailable, so the gate degrades to
    less coverage rather than to a crash.
    """
    try:
        import ingest_transcripts  # sibling module, the producer of this format

        fm, _body, err = ingest_transcripts.parse_frontmatter(text)
        if err is None and isinstance(fm, dict):
            return fm
    except Exception:
        pass
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    data: dict = {}
    key, buf = None, []

    def _flush():
        if key is None:
            return
        blob = "\n".join(buf).strip()
        if blob[:1] in "[{":
            try:
                data[key] = json.loads(blob)
            except json.JSONDecodeError:
                data[key] = blob
        else:
            data[key] = blob.strip('"')

    for line in m.group(1).splitlines():
        if not line.startswith((" ", "\t")) and ":" in line and (key is None or buf):
            stripped = line.split(":", 1)[0].strip()
            if stripped and " " not in stripped:
                _flush()
                key, rest = stripped, line.split(":", 1)[1].strip()
                buf = [rest]
                continue
        buf.append(line)
    _flush()
    return data


def _read_surface(patient_dir: Path, path: Path, parts: list, surfaces: list) -> None:
    try:
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return
    try:
        surfaces.append(path.relative_to(patient_dir).as_posix())
    except ValueError:
        surfaces.append(path.as_posix())


def _source_evidence(patient_dir: Path, entry: dict) -> tuple[str, list[str]]:
    """Return (haystack_text, surfaces_read) for one inventory row.

    B3 / WP3 P0-1 — WHICH surface is authoritative, and why it is not the cheapest one.

    This used to read the masked bucket sidecar FIRST and fall back to raw/transcript/
    only when no masked surface existed. That inverted the question the gate asks. The
    sidecar is DERIVED: the same段 2 pass that wrote labs.json also wrote it, so finding a
    number in the sidecar proves only that one pass agreed with itself — a value misread
    as 9.99 lands in labs.json AND in the sidecar, and the gate confirmed the misreading.
    The transcript is the only surface written by a different pass (段 1, from the page
    image) and is therefore the only one that can contradict段 2.

    So: whenever a transcript for this source EXISTS, raw/transcript/ is the ONLY surface
    read. A deterministic script is permitted there (A27 forbids models and downstream
    consumers, not this gate), and "permitted but expensive" was the wrong trade — the
    cheap surface answered a different question.

    Presence on disk, not the declaration, is the trigger. Keying it to
    `transcript_path` alone would have rebuilt the hole A14 closed one level down: a row
    that simply omits the key would be judged against the derived sidecar again, so
    "declare no transcript" would once more be cheaper than declaring a checkable one —
    and the transcript would be sitting right there, unread. (The missing declaration is
    still its own ERROR, in gate_transcripts. This gate just refuses to be paid by it.)

    Rows with no transcript at all — a native_text source whose characters were taken
    byte-for-byte — legitimately have only the sidecar, and that is what gets read.
    """
    parts: list[str] = []
    surfaces: list[str] = []
    sid = _entry_id(entry)
    tpath = entry.get("transcript_path")

    transcripts: list[Path] = []
    if sid:
        transcripts.extend(sorted((patient_dir / TRANSCRIPT_PREFIX / sid).glob("page-*.md")))
    if isinstance(tpath, str) and tpath.startswith(TRANSCRIPT_PREFIX):
        declared = patient_dir / tpath
        if declared.is_file() and declared not in transcripts:
            transcripts.append(declared)
    if transcripts:
        for page in transcripts:
            _read_surface(patient_dir, page, parts, surfaces)
        return "\n".join(parts), surfaces

    sidecar = entry.get("sidecar_path")
    if isinstance(sidecar, str):
        sc = patient_dir / sidecar
        if sc.is_file():
            _read_surface(patient_dir, sc, parts, surfaces)
    if sid:
        for staged in sorted((patient_dir / OCR_STAGING_DIR / sid).glob("page-*.md")):
            _read_surface(patient_dir, staged, parts, surfaces)
    return "\n".join(parts), surfaces


def _evidence_probe(text: str) -> str:
    """Collapse a surface into a form a source string can be searched in."""
    probe = text.replace(",", "").replace("\uff0c", "")
    probe = probe.translate(_FULLWIDTH_MAP)
    return re.sub(r"\s+", "", probe)


# Minimum length of a frontmatter string before it may be used as EVIDENCE. WP3 P0-1: the
# containment test below is bidirectional (`needle in probe or probe in needle`), so a
# frontmatter value of "" made `"" in needle` true for every raw_value on the page and
# turned the whole gate into a no-op for that source — and a one-character probe like "0"
# or "5" is inside almost any number, which is the same hole one digit wider. Two
# characters is not a quality threshold; it is the floor below which a substring match
# carries no information at all.
_MIN_EVIDENCE_PROBE = 2


def _frontmatter_field_strings(text: str) -> list[str]:
    """Every usable fields[].value / source_reported_text a page frontmatter declares.

    "Usable" excludes the empty string and anything that collapses to fewer than
    _MIN_EVIDENCE_PROBE characters — see the constant above for why those are not weak
    evidence but anti-evidence.
    """
    fm = _parse_page_frontmatter(text)
    out: list[str] = []
    if not isinstance(fm, dict):
        return out
    fields = fm.get("fields")
    if isinstance(fields, list):
        for f in fields:
            if not isinstance(f, dict):
                continue
            for key in ("value", "source_reported_text"):
                v = f.get(key)
                if v is None:
                    continue
                as_text = str(v)
                if len(_evidence_probe(as_text)) < _MIN_EVIDENCE_PROBE:
                    continue
                out.append(as_text)
    return out


def gate_field_provenance(patient_dir: Path, errors: list) -> None:
    """Every labs.json raw_value must be findable in the source it claims to come from.

    gate_numeric_integrity compares two fields the same pass wrote, so it cannot see a
    misread page. This one crosses the boundary: the source-reported string must
    actually occur in that source's own transcription — either as a page frontmatter
    fields[].value / source_reported_text, or verbatim in the page text. A number that
    appears nowhere in the document it cites is either a transcription slip or a value
    imported from somewhere else, and both are exactly what "provenance" is supposed to
    make impossible.

    Scope limits, stated rather than assumed:
      * it verifies PRESENCE of the source string, not that the right cell was read —
        a value lifted from the wrong row of the right page still passes here;
      * a masked span can legitimately hide a value (PII shape), which is reported as
        what it is rather than as a fabrication;
      * a scheme-3 archive is skipped (it has no per-page transcription contract).
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "field_provenance", errors):
        return
    labs_path = patient_dir / "labs.json"
    if not labs_path.is_file():
        return
    try:
        labs = json.loads(labs_path.read_text(encoding="utf-8"))
    except Exception:
        return  # the structured gate already reports parse failures
    panels = labs.get("panels") if isinstance(labs, dict) else None
    if not isinstance(panels, list):
        return

    entries = _inventory_entries(patient_dir)
    if not entries:
        return
    by_sidecar = {
        e.get("sidecar_path"): e for e in entries if isinstance(e.get("sidecar_path"), str)
    }
    cache: dict = {}

    for panel in panels:
        if not isinstance(panel, dict):
            continue
        analyte = panel.get("analyte", "<?>")
        for v in panel.get("values", []) or []:
            if not isinstance(v, dict):
                continue
            raw_value = v.get("raw_value")
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue
            date = v.get("date", "?")
            refs = [
                _anchor_sidecar_path(r)
                for _, r in collect_source_refs(v)
            ]
            rows = [by_sidecar[r] for r in refs if r and r in by_sidecar]
            if not rows:
                continue  # dangling/absent ref — gate_source_inventory owns that case
            ok = False
            surfaces_seen: list[str] = []
            needle = _evidence_probe(raw_value)
            if not needle:
                continue  # nothing to look for; gate_numeric_integrity owns empty raw_value
            for row in rows:
                sid = _entry_id(row) or "<?>"
                if sid not in cache:
                    cache[sid] = _source_evidence(patient_dir, row)
                text, surfaces = cache[sid]
                surfaces_seen.extend(surfaces)
                if not text:
                    continue
                if needle and needle in _evidence_probe(text):
                    ok = True
                    break
                probes = [_evidence_probe(s) for s in _frontmatter_field_strings(text)]
                if any(
                    p and len(p) >= _MIN_EVIDENCE_PROBE
                    and (needle in p or p in needle)
                    for p in probes
                ):
                    ok = True
                    break
            if ok or not surfaces_seen:
                continue
            errors.append(
                f"field_provenance: labs '{analyte}' {date}: source-reported raw_value "
                f"{raw_value!r} does not occur in the source it cites "
                f"({', '.join(sorted(set(surfaces_seen))[:3])}) — a value that is nowhere in its "
                "own document was either misread or imported from elsewhere. Re-read the field "
                "from the page; if the string is legitimately masked there (a PII shape), record "
                "that instead of carrying a number with no reachable source"
            )


# --------------------------------------------------------------------------- #
# [3] source inventory (protected original deep-link + extraction provenance)
# --------------------------------------------------------------------------- #
def _read_json_file(patient_dir: Path, fname: str, errors: list):
    path = patient_dir / fname
    if not path.is_file():
        errors.append(f"{fname}: missing — final archive requires source inventory")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{fname}: not parseable JSON: {e}")
        return None


def _file_entries(doc) -> list:
    if isinstance(doc, dict) and isinstance(doc.get("files"), list):
        return doc["files"]
    return []


def _entry_id(entry: dict) -> str | None:
    value = entry.get("source_id", entry.get("id"))
    return value if isinstance(value, str) else None


def _entry_bool(entry: dict, key: str, default: bool) -> bool:
    value = entry.get(key)
    if isinstance(value, bool):
        return value
    return default


def _anchor_sidecar_path(ref: str) -> str | None:
    """The bucket sidecar a ref resolves to, or None when it names no sidecar.

    Three ref forms name no sidecar and must not be looked up as one: a conversation
    anchor (the fact came from chat, not a document), `source:<source_id>` (an
    inventoried upload with no citable span — A39), and null."""
    if not isinstance(ref, str):
        return None
    ref = ref.strip()
    if not ref or ref.startswith("conversation:") or ref.startswith(SOURCE_REF_PREFIX):
        return None
    return ref.split("#", 1)[0]


def collect_formal_source_ref_paths(patient_dir: Path) -> set[str]:
    """Return bucket-relative sidecar paths cited by formal patient artifacts."""
    refs: set[str] = set()
    for fname in STRUCTURED_FILES:
        path = patient_dir / fname
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            # The structured gate reports parse failures; avoid duplicate noise here.
            continue
        for _, ref in collect_source_refs(data):
            rel = _anchor_sidecar_path(ref)
            if rel:
                refs.add(rel)

    for fname in FORMAL_MARKDOWN_FILES:
        path = patient_dir / fname
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for match in MD_SRC_RE.finditer(text):
            rel = _anchor_sidecar_path(match.group(1))
            if rel:
                refs.add(rel)
    return refs


def gate_source_inventory(patient_dir: Path, errors: list) -> None:
    inventory = _read_json_file(patient_dir, SOURCE_INVENTORY_NAME, errors)
    if inventory is None:
        return
    validate_doc_schema(SOURCE_INVENTORY_NAME, inventory, "source_inventory.schema.json", errors)

    inventory_files = _file_entries(inventory)
    if not inventory_files:
        errors.append(f"{SOURCE_INVENTORY_NAME}: files[] must list every content unit")
        return

    sidecar_entries: dict[str, dict] = {}
    persisted_source_ids: set[str] = set()
    for i, entry in enumerate(inventory_files):
        if not isinstance(entry, dict):
            errors.append(f"{SOURCE_INVENTORY_NAME}: files[{i}] must be an object")
            continue
        sid = _entry_id(entry)
        if not sid:
            errors.append(f"{SOURCE_INVENTORY_NAME}: files[{i}] missing stable source_id/id")
            continue

        # raw_path is a protected relative pointer, not an authorization token.
        raw = entry.get("raw_path")
        if not isinstance(raw, str) or not raw.startswith("raw/"):
            errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: raw_path must point under raw/")

        sidecar = entry.get("sidecar_path")
        if not isinstance(sidecar, str) or not sidecar.endswith(".md"):
            errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: sidecar_path must point to a .md sidecar")
        else:
            if sidecar.startswith("ocr/"):
                errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: final sidecar_path must be bucket-co-located, not ocr/")
            if not (patient_dir / sidecar).is_file():
                errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: sidecar_path not found: {sidecar}")
            sidecar_entries[sidecar] = entry

        # Hard rule 3: `passed_independent_reread` is a CLAIM about how a value was
        # verified, and the only thing that makes it true is a channel independent of the
        # first read. Without this check the claim is self-certifying: the schema
        # describes the rule, nothing enforces it, and a run can mark every high-risk
        # field verified having read each one exactly once. That is the failure mode this
        # gate exists to prevent, so it is an ERROR, not advice.
        if entry.get("high_risk_review_status") == "passed_independent_reread":
            channel = entry.get("reread_channel")
            if channel in (None, "", "none"):
                errors.append(
                    f"{SOURCE_INVENTORY_NAME}: {sid}: high_risk_review_status is "
                    f"passed_independent_reread but reread_channel is {channel!r} — an "
                    "independent second read means a DIFFERENT channel (born-digital text "
                    "layer / barcode / parseable deterministic OCR / a different model / a "
                    "human). Re-prompting the same model on the same image is a tie-break and "
                    "never sets this status; if no channel was available the value stays "
                    "needs_human_review"
                )
            elif channel not in REREAD_CHANNELS:
                errors.append(
                    f"{SOURCE_INVENTORY_NAME}: {sid}: reread_channel {channel!r} is not one of "
                    f"{sorted(REREAD_CHANNELS)}"
                )

        if _entry_bool(entry, "persist", True):
            persisted_source_ids.add(sid)

    formal_refs = collect_formal_source_ref_paths(patient_dir)
    if formal_refs and not persisted_source_ids:
        errors.append(
            f"{SOURCE_INVENTORY_NAME}: all sources are persist:false, but formal "
            f"artifacts cite {len(formal_refs)} source sidecar(s); cited medical "
            "sources must remain persist:true"
        )
    for rel in sorted(formal_refs):
        entry = sidecar_entries.get(rel)
        if not entry:
            errors.append(f"{SOURCE_INVENTORY_NAME}: formal source ref has no inventory row: {rel}")
            continue
        sid = _entry_id(entry) or "<?>"
        if not _entry_bool(entry, "persist", True):
            errors.append(
                f"{SOURCE_INVENTORY_NAME}: {sid}: formal source ref {rel} is marked "
                "persist:false; medical sources cited by formal outputs must remain "
                "persist:true"
            )
        bucket_path = entry.get("bucket_path")
        if bucket_path in (None, ""):
            errors.append(
                f"{SOURCE_INVENTORY_NAME}: {sid}: formal source ref {rel} has no "
                "bucket_path; Phase2 must co-locate the text-masked .md sidecar in its bucket (original stays in raw/) "
                "or report archive_persist_ready:false"
            )


# --------------------------------------------------------------------------- #
# [3a] open-domain filing, human spot-check, and per-field second-read independence
# --------------------------------------------------------------------------- #
def _provenance_runs(patient_dir: Path) -> list:
    """Every raw/_provenance/<run_id>/ directory, oldest name first."""
    root = patient_dir / "raw" / "_provenance"
    if not root.is_dir():
        return []
    return sorted([d for d in root.iterdir() if d.is_dir()], key=lambda d: d.name)


def _sample_key(item) -> tuple:
    if not isinstance(item, dict):
        return ()
    return (
        str(item.get("source_id", "")),
        str(item.get("page", "")),
        str(item.get("label", "")),
    )


def _human_verdicts(patient_dir: Path) -> dict:
    """(source_id, page, label) -> verdict, merged across every run that recorded one.

    Also indexed by (source_id, label) so a field claiming `reread_channel: human`
    still resolves when the page number is recorded on only one side.
    """
    out: dict = {}
    for run in _provenance_runs(patient_dir):
        res = run / "human_sample_result.json"
        if not res.is_file():
            continue
        try:
            data = json.loads(res.read_text(encoding="utf-8"))
        except Exception:
            continue
        for v in (data.get("verdicts") or []) if isinstance(data, dict) else []:
            if not isinstance(v, dict):
                continue
            verdict = v.get("verdict")
            out[_sample_key(v)] = verdict
            out[(str(v.get("source_id", "")), str(v.get("label", "")))] = verdict
    return out


def gate_open_domain_filing(patient_dir: Path, errors: list) -> None:
    """15_ holds kind=novel and nothing else — in both directions (A3).

    A TYPE gap and a QUALITY gap are orthogonal, and collapsing them is what makes an
    open archive useless. `15_未分类资料/` answers "we have no pinned type for this
    document". A blurred, truncated or low-confidence page is a different problem: it
    stays in its best-matching clinical bucket as `kind: unreadable` with a
    `coverage_gap` / `internal_qc` review flag, because filing it under 15_ would make
    「we do not know what this report type is」 and 「we could not read this report」
    indistinguishable — and the second one is the one a human must act on.

    Both directions are enforced, because either alone is a door:
      * a sidecar under 15_ whose row is not kind=novel (with a real novel_reason) —
        15_ becomes the dumping ground the reason field exists to prevent;
      * a kind=novel row filed anywhere else — the row claims the open-world
        exemptions (no pinned slot expected) while sitting in a closed-world bucket
        whose consumers assume the opposite.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "open_domain", errors):
        return
    for entry in _inventory_entries(patient_dir):
        sid = _entry_id(entry) or "<?>"
        sidecar = entry.get("sidecar_path")
        kind = entry.get("kind")
        in_open = isinstance(sidecar, str) and _OPEN_DOMAIN_ANCHOR_RE.match(sidecar)
        if in_open:
            if kind != "novel":
                errors.append(
                    f"open_domain: {sid}: sidecar {sidecar} is filed under {OPEN_DOMAIN_NN}_ but the "
                    f"row declares kind={kind!r} — the open domain takes kind=novel and nothing "
                    "else. A page that is merely unclear/truncated/low-confidence is a QUALITY gap: "
                    "it belongs in its best-matching 01_..14_ bucket as kind=unreadable with a "
                    "review flag (category=coverage_gap, audience=internal_qc), not here"
                )
            reason = entry.get("novel_reason")
            if not isinstance(reason, str) or len(reason.strip()) < 8:
                errors.append(
                    f"open_domain: {sid}: filed under {OPEN_DOMAIN_NN}_ with novel_reason "
                    f"{reason!r} — every open-world filing must say, in the organizer's own words "
                    "and citing what the document actually is, why no pinned domain fits. Eight "
                    "characters is not a threshold of quality, it is a floor against the empty "
                    "string that turns 15_ into an unaudited dumping ground"
                )
        elif kind == "novel" and isinstance(sidecar, str):
            errors.append(
                f"open_domain: {sid}: kind=novel but the sidecar is filed at {sidecar}, outside "
                f"{OPEN_DOMAIN_NN}_. A novel row claims the open-world contract — no pinned slot "
                "was expected, its content is reached by clinical_class rather than by path, and "
                "it is not anchorable — while sitting in a closed-world bucket whose consumers "
                "assume the opposite. Either file it under 15_<slug>/ or classify it as known"
            )


def gate_human_sample(patient_dir: Path, errors: list) -> None:
    """The human spot-check is a RESULT, not a plan (A4).

    Splitting the file in two is the whole point. `human_sample_plan.json` is written by
    a script: here are the fields a human must check, chosen by a seed the run cannot
    influence. `human_sample_result.json` is written by the human: here is what I saw.
    One file that contained both meant the run could describe its own verification —
    the sampling and the verdict came out of the same pass, so 「人工抽查通过」 was
    self-certifying and cost nothing.

    Three assertions:
      1. a plan with no result is an unfinished check, not a passed one;
      2. every planned item needs a verdict — a partial result covering only the
         fields that happened to agree is worse than no sampling, because it reads
         as complete;
      3. two or more mismatches make the archive NOT DELIVERABLE. One mismatch is a
         transcription defect to fix; a second one says the transcription pass itself
         is unreliable on this material, and no amount of per-field patching restores
         confidence in the pages nobody sampled.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    mismatches: list[str] = []
    plans_seen = 0
    for run in _provenance_runs(patient_dir):
        plan_path = run / HUMAN_SAMPLE_PLAN_NAME
        if not plan_path.is_file():
            continue
        plans_seen += 1
        rel_run = run.relative_to(patient_dir).as_posix()
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"human_sample: {rel_run}/{HUMAN_SAMPLE_PLAN_NAME} is not parseable JSON: {exc}")
            continue
        # B11: both halves are schema-validated. They were the only two provenance
        # artifacts the gate read by hand — which meant a plan could be an object with a
        # `sample` of strings, or a result could spell its verdict 「ok」, and the
        # bespoke checks below simply skipped what they did not recognise.
        validate_doc_schema(
            f"{rel_run}/{HUMAN_SAMPLE_PLAN_NAME}", plan, HUMAN_SAMPLE_PLAN_SCHEMA, errors
        )
        result_path = run / HUMAN_SAMPLE_RESULT_NAME
        if not result_path.is_file():
            errors.append(
                f"human_sample: {rel_run}/human_sample_plan.json exists but "
                f"{rel_run}/human_sample_result.json does not — the plan is the ASK, not the "
                "answer. A planned spot-check with no recorded verdicts is an unfinished "
                "verification; it must never be reported as one that passed"
            )
            continue
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"human_sample: {rel_run}/{HUMAN_SAMPLE_RESULT_NAME} is not parseable JSON: {exc}")
            continue
        validate_doc_schema(
            f"{rel_run}/{HUMAN_SAMPLE_RESULT_NAME}", result, HUMAN_SAMPLE_RESULT_SCHEMA, errors
        )
        if not isinstance(result, dict) or not isinstance(result.get("verdicts"), list):
            errors.append(
                f"human_sample: {rel_run}/{HUMAN_SAMPLE_RESULT_NAME} has no verdicts[] array"
            )
            continue
        for key in ("performed_by", "performed_at"):
            if not result.get(key):
                errors.append(
                    f"human_sample: {rel_run}/human_sample_result.json is missing {key} — an "
                    "unattributed, undated human check is not a record of one"
                )
        verdict_keys = {_sample_key(v) for v in result["verdicts"] if isinstance(v, dict)}
        planned = plan.get("sample") if isinstance(plan, dict) else None
        for item in planned if isinstance(planned, list) else []:
            key = _sample_key(item)
            if key and key not in verdict_keys:
                errors.append(
                    f"human_sample: {rel_run}: planned sample {key[0]} p{key[1]} {key[2]!r} has no "
                    "verdict in human_sample_result.json — a partial result that covers only the "
                    "fields which happened to agree reads downstream as a completed spot-check"
                )
        for v in result["verdicts"]:
            if not isinstance(v, dict):
                continue
            verdict = v.get("verdict")
            # R3 P1-10: the vocabulary is closed, and the value that matters most is the
            # one that is neither pass nor fail. A checker who could not make out the cell
            # records `unreadable`; anything unrecognised — 「ok」, 「通过」, 「n/a」 — was
            # previously counted as "not a mismatch", i.e. silently as a pass. An
            # unverifiable cell recorded as verified is the exact failure the human
            # spot-check exists to catch.
            if verdict not in HUMAN_SAMPLE_VERDICTS:
                errors.append(
                    f"human_sample: {rel_run}: verdict {verdict!r} for {v.get('source_id')} "
                    f"p{v.get('page')} {v.get('label')!r} is not one of "
                    f"{sorted(HUMAN_SAMPLE_VERDICTS)} — an unrecognised verdict is counted as "
                    "'not a mismatch', which means an unreadable or failed check reads downstream "
                    "as a passed one. `unreadable` exists precisely so 「我看不清」 has somewhere "
                    "honest to go"
                )
            if verdict == "mismatch":
                mismatches.append(f"{rel_run}:{v.get('source_id')} p{v.get('page')} {v.get('label')!r}")

    # B1: a plan is MANDATORY once any source has a computed high-risk field. Keying the
    # whole gate off 「a plan file happens to exist」 made the human spot-check opt-in: no
    # plan, no result required, no error, and 「人工抽查」 was satisfied by never starting
    # one. The trigger is the denominator, not the artifact.
    if plans_seen == 0 and not _blocked_by_unparseable_inventory(
        patient_dir, "human_sample", errors
    ):
        computed = _deterministic_high_risk(patient_dir)
        with_high_risk = sorted(sid for sid, labels in computed.items() if labels)
        if with_high_risk:
            total = sum(len(computed[sid]) for sid in with_high_risk)
            errors.append(
                f"human_sample: no raw/_provenance/<run>/{HUMAN_SAMPLE_PLAN_NAME} exists, but "
                f"{len(with_high_risk)} source(s) carry {total} high-risk field(s) recomputed from "
                f"their own page frontmatter ({', '.join(with_high_risk[:5])}"
                f"{' …' if len(with_high_risk) > 5 else ''}). The human spot-check is not a "
                "feature a run may decline: machine channels can agree with each other and both be "
                "wrong on the same handwriting, and the sampled human read is the only arm that "
                "leaves that failure mode. Run scripts/plan_second_read.py to write the plan, then "
                f"record the verdicts in {HUMAN_SAMPLE_RESULT_NAME}"
            )

    if len(mismatches) >= 2:
        errors.append(
            f"human_sample: {len(mismatches)} human-verified MISMATCHES ({'; '.join(mismatches[:5])})"
            " — this archive is not deliverable. One mismatch is a field to re-read; two say the "
            "transcription pass is unreliable on THIS material, and the pages nobody sampled carry "
            "the same unmeasured error rate. Re-transcribe the affected sources and re-sample; do "
            "not patch the sampled fields and ship"
        )


# ---------------------------------------------------------------------------- #
# B1 — the high-risk DENOMINATOR, recomputed from the archive's own pages
# ---------------------------------------------------------------------------- #
_DENOMINATOR_CACHE: dict = {}


def _frontmatter_labels(text: str) -> list[str]:
    """Every fields[].label a page frontmatter declares, in page order."""
    fm = _parse_page_frontmatter(text)
    out: list[str] = []
    if not isinstance(fm, dict):
        return out
    fields = fm.get("fields")
    for f in fields if isinstance(fields, list) else []:
        if isinstance(f, dict) and isinstance(f.get("label"), str) and f["label"].strip():
            out.append(f["label"])
    # The page's OWN self-report is folded in: `high_risk: [label…]` is what 段 1 thought
    # was risky. It is never trusted as the whole denominator (that is the entire point of
    # recomputing), but a label the model volunteered and the inventory then dropped is a
    # regression in the other direction and belongs in the same reconciliation.
    self_reported = fm.get("high_risk")
    for label in self_reported if isinstance(self_reported, list) else []:
        if isinstance(label, str) and label.strip():
            out.append(label)
    return out


def _is_transcribed_source(patient_dir: Path, entry: dict) -> bool:
    """Is this a source whose characters a MODEL read? (the denominator's scope)

    B1 scopes the reconciliation to sources with a transcript, and the reason is A35: a
    native_text unit's characters were taken byte-for-byte from a born-digital file and
    verified by scripts/verify_native_text.py as `native_text_identity`. There is no
    second channel to demand of it, its inventory row is `not_applicable` by contract,
    and requiring high_risk_fields[] entries for it would force an archive to invent
    re-reads of bytes that were never re-read by anything.

    Scope is decided by THREE tests, not one, for the same reason the surface choice is:
    keying it to the declared transcript_path alone would make omitting the key a way out
    of the denominator, which is the hole one level down from the one this gate closes.
    """
    tpath = entry.get("transcript_path")
    if isinstance(tpath, str) and tpath.startswith(TRANSCRIPT_PREFIX):
        return True
    if entry.get("read_mode") in MODEL_VISION_READ_MODES:
        return True
    sid = _entry_id(entry)
    if sid and any((patient_dir / TRANSCRIPT_PREFIX / sid).glob("page-*.md")):
        return True
    return False


def _label_surfaces(patient_dir: Path, entry: dict) -> list[Path]:
    """Every file that can carry this source's page frontmatter.

    Deliberately a UNION rather than the first hit. For the denominator the failure that
    matters is missing a label, not counting one twice: a page whose masked sidecar has
    already been moved into its bucket and a page still staged under ocr/ must contribute
    the same set, and a transcript that exists while the sidecar's frontmatter was
    trimmed must not shrink what the archive is held to. Labels are not PII-bearing
    content — masking rewrites VALUES — so reading the masked surfaces first costs
    nothing and the verbatim vault only fills gaps.
    """
    out: list[Path] = []
    sid = _entry_id(entry)
    sidecar = entry.get("sidecar_path")
    if isinstance(sidecar, str):
        sc = patient_dir / sidecar
        if sc.is_file():
            out.append(sc)
    if sid:
        out.extend(sorted((patient_dir / OCR_STAGING_DIR / sid).glob("page-*.md")))
        out.extend(sorted((patient_dir / TRANSCRIPT_PREFIX / sid).glob("page-*.md")))
    tpath = entry.get("transcript_path")
    if isinstance(tpath, str) and tpath.startswith(TRANSCRIPT_PREFIX):
        declared = patient_dir / tpath
        if declared.is_file() and declared not in out:
            out.append(declared)
    return out


def _deterministic_high_risk(patient_dir: Path) -> dict:
    """source_id -> {label: high_risk_class} recomputed from the pages themselves.

    This is the DENOMINATOR, and the reason it is recomputed rather than read is that
    every other copy of it is written by the party being measured. 段 1 emits
    `high_risk: []`, ingest carries that forward, the inventory row records
    `high_risk_fields: []`, the derivation turns that into
    `high_risk_review_status: not_applicable`, and every gate downstream reads
    「nothing here needed a second read」 — for a page whose frontmatter, three lines
    above, declares 住院号 and 白细胞计数 and 剂量. Nothing in that chain is a lie; the
    chain simply never crosses back to the source. This function is the crossing.
    """
    key = str(patient_dir)
    if key in _DENOMINATOR_CACHE:
        return _DENOMINATOR_CACHE[key]
    out: dict = {}
    if HAS_HIGH_RISK:
        for entry in _inventory_entries(patient_dir):
            sid = _entry_id(entry)
            if not sid or not _is_transcribed_source(patient_dir, entry):
                continue
            # C3: a migrated row still HAS labels — its masked sidecar survived the v3
            # archive — but it has no page anyone can go back to. Counting those labels
            # into the denominator would mean demanding second-read records, a
            # faithfulness span and a human sample for a document that cannot be
            # re-opened; the only way to satisfy that is to invent them. The gap is
            # recorded as a gap instead (unreadable_sources + coverage_gap), which is
            # the honest shape of 「we can no longer check this」.
            if _legacy_transcript_exempt(entry):
                continue
            found: dict = out.setdefault(sid, {})
            for path in _label_surfaces(patient_dir, entry):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for label in _frontmatter_labels(text):
                    if label in found:
                        continue
                    cls = _high_risk.classify_label(label)
                    if cls is not None:
                        found[label] = cls
    _DENOMINATOR_CACHE[key] = out
    return out


def _fold_label(label: str) -> str:
    """NFKC + zero-width/bidi strip + casefold + whitespace collapse — the classifier's face."""
    import unicodedata
    t = unicodedata.normalize("NFKC", str(label))
    t = re.sub(r"[\u200b-\u200d\ufeff\u2060\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", t)
    return re.sub(r"\s+", " ", t).strip().casefold()

def gate_high_risk_denominator(patient_dir: Path, errors: list) -> None:
    """The set of high-risk fields is recomputed, not accepted (B1 / R3 P0-1).

    Every other high-risk check in this file verifies the QUALITY of a declared claim:
    is this channel independent, is the model id different, is there a human verdict.
    Not one of them asked whether the claim set was COMPLETE — so the whole structure
    rested on the run's own answer to 「which fields are high-risk?」, and the cheapest
    answer was 「none」. An inventory row with `high_risk_fields: []` derived cleanly to
    `not_applicable`, satisfied gate_high_risk_fields (nothing to check), satisfied
    gate_faithfulness (nothing required), and never reached gate_human_sample. A page
    full of identifiers, lab values and doses passed every field-level gate by declaring
    that it had no fields.

    This gate recomputes the set from the page frontmatter the archive itself stores, via
    the one shared table in scripts/_high_risk.py, and requires the declaration to COVER
    it. Three shapes of the same failure:

      * declared ⊉ computed — a label the page prints and the classifier recognises, with
        no record of a second read;
      * `high_risk_fields: []` while the computed set is non-empty — stated separately
        because it is the total version of the same thing and the message should say so;
      * `high_risk_fields: []` with a row-level status other than not_applicable — the
        row claims an outcome for an array it does not have.

    Over-declaring is always legal: the archive may record second reads for fields the
    table does not know about. Only shrinking below the computed floor is an error.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "high_risk_denominator", errors):
        return
    if not HAS_HIGH_RISK:
        errors.append(
            "high_risk_denominator: could not import scripts/_high_risk.py "
            f"({_HIGH_RISK_IMPORT_ERROR}) — the high-risk field set cannot be recomputed, so the "
            "reconciliation this gate exists for would compare the archive's claims against an "
            "EMPTY set and pass everything. A denominator that fails to load is not a smaller "
            "denominator"
        )
        return
    computed = _deterministic_high_risk(patient_dir)

    for entry in _inventory_entries(patient_dir):
        sid = _entry_id(entry) or "<?>"
        # C3: skipped here as well as in _deterministic_high_risk, because this loop can
        # reach the row through its own declaration. migrate_v3_to_v4.py writes
        # high_risk_fields: [] + high_risk_review_status: not_applicable on such a row,
        # which the empty-array branch below would otherwise have to adjudicate — and the
        # only adjudication available is 「produce records for pages that no longer
        # exist」. The coverage ledger holds this row instead.
        if _legacy_transcript_exempt(entry):
            continue
        derived_set = computed.get(sid) or {}
        raw_fields = entry.get("high_risk_fields")
        fields = [f for f in raw_fields if isinstance(f, dict)] if isinstance(raw_fields, list) else []
        declared_labels = {
            f["label"] for f in fields if isinstance(f.get("label"), str) and f["label"].strip()
        }

        if not fields:
            if derived_set:
                sample = sorted(derived_set.items())[:6]
                errors.append(
                    f"high_risk_denominator: {sid}: high_risk_fields[] is EMPTY, but this source's "
                    f"own page frontmatter declares {len(derived_set)} high-risk field(s) — "
                    + ", ".join(f"{lab!r} ({cls})" for lab, cls in sample)
                    + (" …" if len(derived_set) > 6 else "")
                    + ". An empty array derives to high_risk_review_status: not_applicable, which "
                    "every downstream gate reads as 「nothing here needed a second read」. That is "
                    "the archive certifying its own exemption from the one check that exists "
                    "because a single wrong character changes a dose, a date or an identifier. "
                    "Record one entry per field with its channel, or record it as "
                    "needs_human_review — but it may not be absent"
                )
            elif entry.get("high_risk_review_status") != "not_applicable":
                errors.append(
                    f"high_risk_denominator: {sid}: high_risk_fields[] is empty but "
                    f"high_risk_review_status is {entry.get('high_risk_review_status')!r} — the "
                    "row-level value is a DERIVED summary of that array, and the only summary an "
                    "empty array supports is not_applicable. A row asserting an outcome for "
                    "records it does not hold is asserting it about nothing"
                )
            continue

        # Compare labels after the same NFKC / zero-width folding the classifier applies:
        # a run that declares `WBC` for a page printing `Ｗ Ｂ Ｃ` has covered that field.
        folded_declared = {_fold_label(x) for x in declared_labels}
        missing = sorted(lab for lab in derived_set if _fold_label(lab) not in folded_declared)
        if missing:
            shown = ", ".join(f"{lab!r} ({derived_set[lab]})" for lab in missing[:6])
            errors.append(
                f"high_risk_denominator: {sid}: {len(missing)} high-risk field(s) appear in this "
                f"source's page frontmatter but have no entry in high_risk_fields[]: {shown}"
                f"{' …' if len(missing) > 6 else ''}. The denominator of the second-read coverage "
                "metric is computed from the pages (scripts/_high_risk.py), never accepted from "
                "the run being measured — a run that chooses its own denominator can report full "
                "coverage of a set it shrank. Add an entry per field (status may be "
                "needs_human_review); declaring MORE than the table knows about is always legal"
            )


def _derived_high_risk_status(fields: list) -> str:
    """The row-level summary the per-field records imply."""
    if not fields:
        return "not_applicable"
    statuses = [f.get("status") for f in fields if isinstance(f, dict)]
    if any(s == "needs_human_review" for s in statuses):
        return "needs_human_review"
    if statuses and all(s == "passed_independent_reread" for s in statuses):
        return "passed_independent_reread"
    if statuses and all(s == "not_applicable" for s in statuses):
        return "not_applicable"
    return "needs_human_review"


def gate_high_risk_fields(patient_dir: Path, errors: list) -> None:
    """Per-field second-read independence — the claim is now checkable (A5).

    The row-level `high_risk_review_status` was a single word covering every high-risk
    field in a document, so 「passed」 could rest on one field verified through a
    born-digital text layer while the handwritten dose beside it was read once. The
    per-field array makes each claim carry its own channel, and this gate checks the
    three ways a channel can be asserted but not exist:

      * `text_layer` on a page whose text_layer_kind is NOT born_digital. On `absent`
        there is no text layer; on `embedded_ocr` the "text layer" is a scanner's own
        OCR of the same pixels. Neither is independent of the first read — it is the
        same image twice, which the contract has always called a tie-break.
      * `alternate_vision_model` with no reread_model_id, or one equal to
        transcribe_model_id. Same model, same image, different prompt is the exact
        thing the independence rule exists to exclude; without the two ids recorded the
        claim was not even falsifiable.
      * `human` with no verdict in human_sample_result.json. 「人工核对过」 must point
        at the record of the human doing it, or it is a placeholder for "no channel".

    And it checks the derivation itself: a row summarising a needs_human_review field
    as passed is a contradiction inside one object.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "high_risk_fields", errors):
        return
    verdicts = _human_verdicts(patient_dir)
    verdict_sids = {k[0] for k in verdicts if isinstance(k, tuple) and k}

    for entry in _inventory_entries(patient_dir):
        sid = _entry_id(entry) or "<?>"
        tlk = entry.get("text_layer_kind")
        transcribe_model = entry.get("transcribe_model_id")
        fields = entry.get("high_risk_fields")
        fields = [f for f in fields if isinstance(f, dict)] if isinstance(fields, list) else []

        # row-level channel is a summary of the same vocabulary and obeys the same rules
        row_channel = entry.get("reread_channel")
        checks = [(None, row_channel, entry.get("high_risk_review_status"), entry.get("reread_model_id"))]
        checks += [
            (f.get("label"), f.get("reread_channel"), f.get("status"), f.get("reread_model_id"))
            for f in fields
        ]

        for label, channel, status, model_id in checks:
            where = f"{sid}" if label is None else f"{sid} field {label!r}"
            if channel == "text_layer" and tlk not in TEXT_LAYER_CHANNEL_KINDS:
                errors.append(
                    f"high_risk_fields: {where}: reread_channel=text_layer but text_layer_kind="
                    f"{tlk!r} — an impossible channel. The text layer is an INDEPENDENT read in "
                    "exactly two cases: born_digital (real embedded glyphs from the producing "
                    "application) and not_applicable (a unit with no page raster at all, whose "
                    "characters came from a deterministic adapter — a VCF, a DICOM header, a "
                    "timeseries payload). With absent there is no text layer, and with "
                    "embedded_ocr the layer is a scanner's own OCR of the very pixels the model "
                    "read — the same image twice, which the contract has always called a "
                    "tie-break. Either record the channel that actually ran, or leave the field "
                    "needs_human_review"
                )
            # The model-id pair is recorded PER FIELD: the row-level reread_channel is a
            # summary and carries no model id of its own, so asking it for one would
            # manufacture an error on a correctly-written row.
            if channel == "alternate_vision_model" and label is not None:
                if not isinstance(model_id, str) or not model_id.strip():
                    errors.append(
                        f"high_risk_fields: {where}: reread_channel=alternate_vision_model with no "
                        "reread_model_id — the independence claim is not even falsifiable without "
                        "the id of the model that produced the second read"
                    )
                elif isinstance(transcribe_model, str) and model_id.strip() == transcribe_model.strip():
                    errors.append(
                        f"high_risk_fields: {where}: reread_model_id {model_id!r} is the SAME model "
                        f"as transcribe_model_id — re-prompting one model on one image, including a "
                        "cropped region, is a tie-break and never an independent channel. Use a "
                        "different model, a different modality, or a human"
                    )
            if channel == "human":
                # B1: the `label is not None` guard used to exempt the ROW-LEVEL summary,
                # which is the one place `human` costs nothing to write — a row could
                # summarise its channel as 「人工」 with no per-field entry and no verdict
                # anywhere, and the exemption was invisible because the per-field rule
                # looked strict. A row claiming human review must point at a human having
                # reviewed SOMETHING in this source; a field claiming it must point at
                # that field.
                if label is None:
                    if sid not in verdict_sids:
                        errors.append(
                            f"high_risk_fields: {where}: row-level reread_channel=human but NO "
                            "verdict for this source exists in any raw/_provenance/<run>/"
                            "human_sample_result.json. The row-level channel is a summary of the "
                            "per-field records, and a summary of 「a person checked this」 with no "
                            "person and no record is the cheapest unverifiable claim in the whole "
                            "structure. Use `none` when no independent channel ran"
                        )
                else:
                    key = (sid, str(entry.get("page", "")), str(label))
                    if key not in verdicts and (sid, str(label)) not in verdicts:
                        errors.append(
                            f"high_risk_fields: {where}: reread_channel=human but no matching verdict "
                            "exists in any raw/_provenance/<run>/human_sample_result.json. `human` is "
                            "not a no-channel placeholder — it is a claim that a person read this field "
                            "off the original, and the record of them doing it is what makes it true"
                        )
            if status == "passed_independent_reread" and channel in (None, "", "none"):
                errors.append(
                    f"high_risk_fields: {where}: status=passed_independent_reread with "
                    f"reread_channel={channel!r} — with no channel the value stays "
                    "needs_human_review; an unverified field recorded as verified is the one "
                    "failure mode this whole structure exists to prevent"
                )

        if fields:
            derived = _derived_high_risk_status(fields)
            declared = entry.get("high_risk_review_status")
            if declared != derived:
                errors.append(
                    f"high_risk_fields: {sid}: high_risk_review_status is {declared!r} but its own "
                    f"high_risk_fields[] imply {derived!r} — the row-level value is a DERIVED "
                    "summary (any needs_human_review wins; all-passed is the only way to passed; "
                    "no high-risk fields is not_applicable), not an independent assertion. A "
                    "summary that disagrees with the records it summarises is how a "
                    "needs_human_review field reaches a consumer labelled verified"
                )
            if any(f.get("reread_channel") == "alternate_vision_model" for f in fields) and not (
                isinstance(transcribe_model, str) and transcribe_model.strip()
            ):
                errors.append(
                    f"high_risk_fields: {sid}: a field claims reread_channel=alternate_vision_model "
                    "but the row records no transcribe_model_id — without the FIRST read's model id "
                    "there is nothing for the second one to be different from"
                )


# --------------------------------------------------------------------------- #
# [3b] bucket-taxonomy enforcement (CB-P0-1) — deterministic, NO medical
# judgement. The 段 2 classifier is instructed to re-file every source onto
# the pinned v3 taxonomy (bucket-taxonomy.md §1.1 / §1.1a) and to NEVER echo an
# incoming source-folder name. A synthetic regression fixture reproduces the drift (echoed
# `06_分子与组学/基因检测`, `11_不良反应`, `13_其他专科检查`,
# `04_诊断与分期/影像报告`). This gate closes that at mkdir time: every
# top-level `NN_` domain dir and every typed sub-bucket one level down MUST be a
# pinned slug from bucket_taxonomy.json (zh OR en form). Any non-pinned dir is a
# violation printed with the pinned slug that WAS expected for its NN prefix.
# --------------------------------------------------------------------------- #
BUCKET_TAXONOMY_JSON = REPO_ROOT / "references" / "bucket_taxonomy.json"
_DOMAIN_DIR_RE = re.compile(r"^\d{2}_")
_NN_PREFIX_RE = re.compile(r"^\d{2}_")
# Fallback used only if bucket_taxonomy.json predates scheme 4 and carries no regex.
_DEFAULT_OPEN_SLUG_RE = r"^[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9-]{1,23}$"
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _reserved_sub_bucket_names(tax: dict) -> set[str]:
    """Every name an OPEN sub-bucket slug may not be.

    A slug under 15_ is written by a model out of untrusted source text. Shape
    validation alone is not enough: a slug that merely *looks* fine but equals a
    pinned clinical slug, an infra dir, or the universal fallback would let an
    open, model-named directory impersonate a closed-world bucket and re-route
    sources past the gates that guard it. Hence an explicit blacklist composed
    from the taxonomy itself (so it can never drift) plus the pinned extras.
    """
    reserved: set[str] = set()
    for d in tax.get("domains", []):
        for key in ("zh", "en"):
            val = d.get(key)
            if isinstance(val, str):
                reserved.add(val)
                # also the bare slug without its NN_ prefix
                reserved.add(val.split("_", 1)[1] if "_" in val else val)
        for sb in d.get("sub_buckets", []) or []:
            reserved.update(v for v in (sb.get("zh"), sb.get("en")) if isinstance(v, str))
    for ib in tax.get("infra_buckets", []):
        for key in ("zh", "en"):
            val = ib.get(key)
            if isinstance(val, str):
                reserved.add(val)
                reserved.add(val.split("_", 1)[1] if "_" in val else val)
        reserved.update(x for x in ib.get("sub_buckets_ascii", []) or [] if isinstance(x, str))
    reserved.update(x for x in tax.get("ascii_infra_dirs", []) or [] if isinstance(x, str))
    for sb in tax.get("universal_fallback_sub_buckets", []) or []:
        reserved.update(v for v in (sb.get("zh"), sb.get("en")) if isinstance(v, str))
    explicit = (tax.get("reserved_sub_bucket_names") or {}).get("explicit") or []
    reserved.update(x for x in explicit if isinstance(x, str))
    return reserved


def _open_sub_bucket_violation(name: str, slug_re, reserved: set[str]) -> str | None:
    """Return why `name` is an illegal OPEN sub-bucket slug, or None if it is legal.

    Ordered so the *reason* is the most useful one: structural abuse first
    (traversal / separators / control chars), then the shape, then impersonation.
    """
    if name in (".", "..") or ".." in name:
        return "contains '..' (path traversal)"
    if "/" in name or "\\" in name:
        return "contains a path separator"
    if _CONTROL_CHARS_RE.search(name):
        return "contains a control character"
    if name.startswith("."):
        return "starts with '.' (hidden/dotfile namespace)"
    if _NN_PREFIX_RE.match(name):
        return "starts with an NN_ domain prefix — an open sub-bucket must not look like a domain"
    if len(name) > 24:
        return f"is {len(name)} characters long (max 24)"
    if not slug_re.match(name):
        return ("does not match open_sub_bucket_slug_regex (CJK/Latin/digits/hyphen, "
                "2-24 chars, must start alphanumeric or CJK)")
    if name in reserved:
        return ("collides with a reserved name (a pinned domain/sub-bucket slug, an infra "
                "dir, or the universal fallback) — an open slug must not impersonate a "
                "closed-world bucket")
    return None


def _load_bucket_taxonomy(errors: list):
    try:
        return json.loads(BUCKET_TAXONOMY_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"bucket_taxonomy: cannot load {BUCKET_TAXONOMY_JSON.name}: {e}")
        return None


def gate_bucket_taxonomy(patient_dir: Path, errors: list) -> None:
    tax = _load_bucket_taxonomy(errors)
    if tax is None:
        return

    # full-domain-slug -> domain record (both zh + en forms map to it)
    domain_by_slug: dict[str, dict] = {}
    # NN prefix -> (zh full slug, en full slug) for the "expected" hint
    expected_by_nn: dict[str, tuple[str, str]] = {}
    for d in tax.get("domains", []):
        domain_by_slug[d["zh"]] = d
        domain_by_slug[d["en"]] = d
        expected_by_nn[d["nn"]] = (d["zh"], d["en"])

    infra_top: dict[str, dict] = {}
    for ib in tax.get("infra_buckets", []):
        infra_top[ib["zh"]] = ib
        infra_top[ib["en"]] = ib
        expected_by_nn.setdefault(ib["nn"], (ib["zh"], ib["en"]))

    ascii_infra = set(tax.get("ascii_infra_dirs", []))
    fallback_subs: set[str] = set()
    for sb in tax.get("universal_fallback_sub_buckets", []):
        fallback_subs.update((sb["zh"], sb["en"]))

    reserved_subs = _reserved_sub_bucket_names(tax)
    raw_slug_re = tax.get("open_sub_bucket_slug_regex") or _DEFAULT_OPEN_SLUG_RE
    try:
        open_slug_re = re.compile(raw_slug_re)
    except re.error as exc:
        errors.append(
            f"bucket_taxonomy: open_sub_bucket_slug_regex does not compile ({exc}); "
            "falling back to the built-in pattern"
        )
        open_slug_re = re.compile(_DEFAULT_OPEN_SLUG_RE)

    def _allowed_subs(domain: dict) -> set[str]:
        allowed: set[str] = set()
        for s in domain.get("sub_buckets", []):
            allowed.update((s["zh"], s["en"]))
        # `其他/other` fallback child + ASCII infra dirs (high_confidence /
        # uncertain / conversation_notes) are always allowed under a clinical
        # domain (bucket-taxonomy.md §1.1a note + §1.1b fallback).
        return allowed | fallback_subs | ascii_infra

    for child in sorted(patient_dir.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if not _DOMAIN_DIR_RE.match(name):
            # non-`NN_` dirs (raw/ ocr/ 99_… handled below, plus anything ASCII
            # infra) are not scanned as clinical domains here.
            continue

        if name in domain_by_slug:
            domain = domain_by_slug[name]
            if domain.get("open_sub_buckets") is True:
                # OPEN domain (scheme 4: 15_未分类资料 only). Its children are not
                # pinned — they are model-written slugs — so they are validated by
                # shape + reserved-name blacklist instead of by whitelist. The
                # fallback 其他/other and the ASCII infra dirs stay allowed so an
                # open domain behaves like every other one for the organizer.
                # `raw` / `ocr` are the vault and the staging dir. Under a PINNED domain
                # a stray dir with one of those names is a harmless infra convention; under
                # an OPEN domain, where the slug was written by a model out of the
                # document's own text, a directory literally named `raw` is an
                # impersonation of the access-controlled vault. They stay reserved here.
                always_ok = fallback_subs | (ascii_infra - {"raw", "ocr"})
                for sub in sorted(child.iterdir()):
                    if not sub.is_dir() or sub.name in always_ok:
                        continue
                    why = _open_sub_bucket_violation(sub.name, open_slug_re, reserved_subs)
                    if why:
                        errors.append(
                            f"bucket_taxonomy: {name}/{sub.name} is an illegal open "
                            f"sub-bucket slug — it {why}. The slug is written by a model "
                            "from untrusted source text and must satisfy "
                            "bucket_taxonomy.json open_sub_bucket_slug_regex and miss "
                            "reserved_sub_bucket_names; rename it (the material stays, "
                            "novel is never quarantine)"
                        )
                continue
            allowed = _allowed_subs(domain)
            for sub in sorted(child.iterdir()):
                if not sub.is_dir():
                    continue
                if sub.name not in allowed:
                    zh, en = domain["zh"], domain["en"]
                    errors.append(
                        f"bucket_taxonomy: {name}/{sub.name} is not a pinned sub-bucket "
                        f"of {zh}; re-file onto a pinned slug from bucket_taxonomy.json "
                        f"(domain {domain['nn']} pinned sub-buckets: "
                        f"{', '.join(s['zh'] for s in domain.get('sub_buckets', []))}) "
                        f"or the fallback 其他/other"
                    )
        elif name in infra_top:
            ib = infra_top[name]
            allowed = set(ib.get("sub_buckets_ascii", [])) | ascii_infra
            for sub in sorted(child.iterdir()):
                if not sub.is_dir():
                    continue
                if sub.name not in allowed:
                    errors.append(
                        f"bucket_taxonomy: {name}/{sub.name} is not a pinned child of "
                        f"infra bucket {ib['zh']} (allowed: {', '.join(sorted(allowed))})"
                    )
        else:
            # A `NN_` top-level dir whose slug is NOT pinned — the classic drift
            # (echoed an incoming source-folder name / an off-taxonomy domain).
            nn = name[:2]
            hint = expected_by_nn.get(nn)
            if hint:
                zh, en = hint
                expect = f"expected the pinned {nn}_ domain slug '{zh}' (en: '{en}')"
            else:
                expect = (
                    f"'{nn}_' is not a pinned domain number — valid domains are 01_..15_ "
                    "(see bucket_taxonomy.json); re-file its contents onto the correct "
                    "clinical domain"
                )
            errors.append(
                f"bucket_taxonomy: top-level dir '{name}' is not a pinned domain slug; {expect}"
            )


# --------------------------------------------------------------------------- #
# [3c] Molecular-report transcription coverage — deterministic WARN, NO medical
# judgement. Empty arrays are compared with the source report's own sections;
# this gate does not assert that any report should contain germline, PGx, VUS, or
# a particular gene. WARNs do not change the exit code.
# --------------------------------------------------------------------------- #
def _inventory_entries(patient_dir: Path) -> list:
    """Every inventory row, or [] when the inventory is missing/unparseable.

    Read-only helper shared by the open-world gates; gate_source_inventory owns
    reporting that the file is missing or malformed, so this one stays silent.
    """
    inv = patient_dir / SOURCE_INVENTORY_NAME
    if not inv.is_file():
        return []
    try:
        data = json.loads(inv.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [e for e in _file_entries(data) if isinstance(e, dict)]


def _entry_doc_kind(entry: dict) -> str:
    """doc_kind, falling back to the legacy free-form doc_type.

    `doc_type` was never in source_inventory.schema.json (additionalProperties:false),
    so a row carrying it could not validate — yet gate_ngs_completeness read it. v3
    names the field `doc_kind`; the fallback keeps pre-v3 archives readable instead of
    silently losing their only type signal.
    """
    for key in ("doc_kind", "doc_type"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _has_ngs_source(patient_dir: Path) -> bool:
    # (a) an NGS sidecar filed under the pinned NGS sub-bucket (zh or en form).
    for pat in ("06_*/NGS报告/*.md", "06_*/ngs/*.md"):
        if any(patient_dir.glob(pat)):
            return True
    # (b) an NGS / molecular entry in source_inventory.json.
    for entry in _inventory_entries(patient_dir):
        for key in ("bucket_path", "sidecar_path"):
            val = entry.get(key)
            if isinstance(val, str) and ("NGS报告" in val or "/ngs/" in val.lower()):
                return True
        if "NGS" in _entry_doc_kind(entry).upper():
            return True
        # (c) v3: the completeness floor keys off clinical_class, NOT off the path.
        # This is the whole point of the enum — a molecular report that the
        # classifier filed somewhere unexpected (or under the open domain 15_,
        # which has no pinned NGS sub-bucket at all) used to be invisible here,
        # so molecular.json came back empty with zero warnings and a downstream
        # tumour board opened an empty file believing the archive had nothing.
        if entry.get("clinical_class") == "molecular":
            return True
    return False


def _labs_cited_sidecars(patient_dir: Path) -> set[str]:
    """Bucket-relative sidecar paths cited by labs.json source_refs."""
    labs_path = patient_dir / "labs.json"
    if not labs_path.is_file():
        return set()
    try:
        labs = json.loads(labs_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    out: set[str] = set()
    for _, ref in collect_source_refs(labs):
        rel = _anchor_sidecar_path(ref)
        if rel:
            out.add(rel)
    return out


def _extracted_entries(patient_dir: Path) -> list:
    path = patient_dir / EXTRACTED_FIELDS_NAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


# Label fragments that say "this page carries laboratory or molecular content".
# A word list is legitimate HERE and only here, because it is a DENOMINATOR binding:
# it decides which rows must be LOOKED AT, never what any of them means. A hit does not
# classify the document — it says that `clinical_class: unknown` on a page whose own
# transcript declares a lab value or a variant is a filing defect, because `unknown` is
# what routes a source past the molecular and lab floors. Missing a term costs coverage,
# never a wrong answer; that asymmetry is what makes the list safe.
_LAB_LABEL_HINTS = (
    "\u5355\u4f4d", "\u53c2\u8003\u503c", "\u53c2\u8003\u8303\u56f4", "\u68c0\u9a8c", "\u5316\u9a8c",
    "\u8840\u5e38\u89c4", "\u751f\u5316", "\u8ba1\u6570", "\u6d53\u5ea6", "\u542b\u91cf",
    "\u80bf\u7624\u6807\u5fd7\u7269", "mg/", "g/l", "mmol", "umol", "\u00b5mol", "iu/", "u/l",
    "ng/ml", "ug/ml", "10^9", "10^12", "cea", "ca19-9", "ca125", "afp", "psa", "wbc", "hgb", "plt",
)
_MOLECULAR_LABEL_HINTS = (
    "\u57fa\u56e0", "\u7a81\u53d8", "\u6241\u5e73", "\u878d\u5408", "\u6269\u589e", "\u7a81\u53d8\u4e30\u5ea6",
    "\u80da\u7cfb", "\u4f53\u7ec6\u80de", "\u5fae\u536b\u661f", "\u7a33\u5b9a", "\u6d4b\u5e8f",
    "vaf", "hgvs", "c.", "p.", "exon", "msi", "tmb", "pd-l1", "her2", "egfr", "kras", "alk", "braf",
    "ngs", "variant", "fusion", "allele frequency",
)


def _clinical_content_hits(patient_dir: Path, entry: dict) -> set:
    """Which clinical-content classes this source's OWN transcript declares.

    Reads the page frontmatter fields[] (masked surface preferred, see _source_evidence)
    and matches labels/units against the denominator word lists above. Returns a subset
    of {"lab", "molecular"}.
    """
    text, _surfaces = _source_evidence(patient_dir, entry)
    if not text:
        return set()
    labels: list[str] = []
    fm = _parse_page_frontmatter(text)
    if isinstance(fm, dict) and isinstance(fm.get("fields"), list):
        for f in fm["fields"]:
            if isinstance(f, dict):
                for key in ("label", "unit", "source_reported_text"):
                    v = f.get(key)
                    if isinstance(v, str):
                        labels.append(v)
    if not labels:
        return set()
    blob = " ".join(labels).lower()
    hits = set()
    if any(h in blob for h in _LAB_LABEL_HINTS):
        hits.add("lab")
    if any(h in blob for h in _MOLECULAR_LABEL_HINTS):
        hits.add("molecular")
    return hits


def gate_clinical_class_completeness(patient_dir: Path, errors: list) -> None:
    """clinical_class → structured-output floors. ERROR, not WARN.

    Open-world filing must not become a way to bypass the invariants that closed-world
    filing enforces. Two floors, both keyed off the inventory's own declared
    clinical_class so the bucket path is irrelevant:

      * kind=novel + clinical_class=molecular ⇒ molecular.json must exist and be
        non-empty. A novel gene panel is the exact case the open domain was added
        for; if it can be archived while molecular.json stays empty, the archive
        reads as "no molecular data" and everything downstream inherits that lie.
        WARN is not enough here — gate_ngs_completeness already WARNs for known
        sources, and a WARN nobody must act on is what let this through.

      * clinical_class=lab ⇒ the source's values must have landed SOMEWHERE — a
        labs.json row citing its sidecar, or a lab entry in extracted_fields.json.
        Neither means the numbers were transcribed and then dropped on the floor.

    kind=unreadable is exempt from both: nothing could be lifted from it. It is not
    forgiven, though — gate_projection_coverage requires it to be declared there, so
    it shows up as an uncovered source instead of vanishing.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "clinical_class", errors):
        return
    entries = _inventory_entries(patient_dir)
    if not entries:
        return

    mol_path = patient_dir / "molecular.json"
    mol_empty = True
    mol_present = mol_path.is_file()
    if mol_present:
        try:
            mol = json.loads(mol_path.read_text(encoding="utf-8"))
            if isinstance(mol, dict):
                mol_empty = all(
                    _is_empty_array(mol, k) for k in ("variants", "germline", "pharmacogenomics")
                )
        except Exception:
            mol_empty = True

    labs_refs = _labs_cited_sidecars(patient_dir)
    ef_entries = _extracted_entries(patient_dir)
    ef_lab_sources = {
        e.get("source_id") for e in ef_entries if e.get("clinical_class") == "lab"
    }

    reported_molecular = False
    for entry in entries:
        sid = _entry_id(entry) or "<?>"
        kind = entry.get("kind")
        cls = entry.get("clinical_class")
        if kind == "unreadable":
            continue

        # The floor keys off clinical_class ALONE. It used to require kind == "novel"
        # as well, which meant the single most ordinary archive — a KNOWN NGS report
        # filed in its pinned bucket beside an empty molecular.json — fell through to a
        # WARN that does not change the exit code. The open-world case was gated and the
        # common case was not.
        if cls == "molecular" and not reported_molecular:
            if not mol_present:
                reported_molecular = True
                errors.append(
                    f"clinical_class: {sid}: a source declares clinical_class=molecular "
                    "but molecular.json does not exist — no filing route skips the "
                    "molecular floor; transcribe the report's own variant/germline/PGx tables "
                    "(no actionability inference) or state explicitly why it carries none"
                )
            elif mol_empty:
                reported_molecular = True
                errors.append(
                    f"clinical_class: {sid}: a source declares clinical_class=molecular "
                    "but molecular.json has no variants, germline or pharmacogenomics rows — "
                    "verify against the source report's own section inventory; an empty "
                    "molecular.json beside a molecular source reads downstream as 'no molecular "
                    "data exists'"
                )

        if cls == "unknown":
            hits = _clinical_content_hits(patient_dir, entry)
            if hits:
                errors.append(
                    f"clinical_class: {sid}: declares clinical_class=unknown, but its own "
                    f"transcript carries {'/'.join(sorted(hits))} content (fields[] with "
                    "laboratory units/reference ranges or variant nomenclature). `unknown` is the "
                    "value that routes a source AROUND the molecular and lab floors, so using it "
                    "on a page that plainly holds those values is not a cautious classification — "
                    "it is the cheapest way to make the floors disappear. Set the class the "
                    "content shows; `unknown` is for material that genuinely resists it"
                )

        if cls == "lab":
            sidecar = entry.get("sidecar_path")
            has_lab_row = isinstance(sidecar, str) and sidecar in labs_refs
            has_open_lab = sid in ef_lab_sources
            if not has_lab_row and not has_open_lab:
                errors.append(
                    f"clinical_class: {sid}: declares clinical_class=lab but no labs.json value "
                    f"cites its sidecar ({sidecar!r}) and extracted_fields.json holds no lab entry "
                    "for it — the results were read and then lost. File them in labs.json with "
                    "their own date/unit/reference range, or (for a genuinely unmappable panel) "
                    "as extracted_fields entries carrying unit + source_reported_text"
                )


def _is_empty_array(obj, key: str) -> bool:
    v = obj.get(key)
    return not (isinstance(v, list) and len(v) > 0)


def gate_ngs_completeness(patient_dir: Path, warnings: list) -> None:
    if not _has_ngs_source(patient_dir):
        return
    mol_path = patient_dir / "molecular.json"
    if not mol_path.is_file():
        warnings.append(
            "ngs_completeness: an NGS source is present but molecular.json is missing "
            "— the somatic variant table / germline / pharmacogenomics were not lifted"
        )
        return
    try:
        mol = json.loads(mol_path.read_text(encoding="utf-8"))
    except Exception:
        return  # the structured gate already reports parse failures
    if not isinstance(mol, dict):
        return
    empty = [k for k in ("variants", "germline", "pharmacogenomics") if _is_empty_array(mol, k)]
    if empty:
        warnings.append(
            "ngs_completeness: an NGS source is present but molecular.json "
            f"{'/'.join(empty)} {'is' if len(empty) == 1 else 'are'} empty — verify the "
            "source report's own section/table inventory. Empty arrays are valid when those "
            "sections are absent; if present, transcribe every source row without actionability inference"
        )


# --------------------------------------------------------------------------- #
# [3d] update_log edit-trail freshness (CB-P2-1) — deterministic WARN, NO
# medical judgement. update_log.json is written ONLY by the 段 2 LLM step; a
# manual edit to profile.json (fixing a value by hand, patching a field) bypasses
# it, so the changelog silently goes stale and the archive is no longer
# reproducible from the organize flow. This advisory floor catches that: if
# update_log.json exists AND profile.json was modified more recently than
# update_log.json itself, warn that profile.json was edited outside the organize
# flow with no changelog entry. mtime-vs-mtime is the robust comparison (no
# dependency on parsing per-entry timestamp formats/timezones). WARN only — a
# stale changelog is a hygiene signal, never a hard block. No update_log.json →
# skip silently (a first run / a run that legitimately produced no changelog).
# --------------------------------------------------------------------------- #
def gate_update_log_freshness(patient_dir: Path, warnings: list) -> None:
    update_log = patient_dir / "update_log.json"
    profile = patient_dir / "profile.json"
    if not update_log.is_file():
        return  # no changelog to compare against — nothing to assert
    if not profile.is_file():
        return  # no profile.json — the structured/other gates own that case
    try:
        profile_mtime = profile.stat().st_mtime
        update_log_mtime = update_log.stat().st_mtime
    except OSError:
        return
    if profile_mtime > update_log_mtime + _MTIME_EPS:
        warnings.append(
            "update_log_freshness: profile.json edited outside the organize flow "
            "— no changelog entry; re-run organize or append an update_log entry."
        )


# --------------------------------------------------------------------------- #
# [3e] open-world gates (organize v3) — deterministic, NO medical judgement
# --------------------------------------------------------------------------- #
# Files that are ALLOWED to name raw/transcript/ : the registries whose job is to
# record where the verbatim transcript lives. Everything else naming it is a leak of
# the controlled surface into a context that is not access-controlled.
# A17/B12: `.phase1_sources.json` was removed from the contract, and leaving it in this
# allowlist left a named file that may legally point at the verbatim vault while nothing
# writes or audits it — a permanently open door with no room behind it.
_TRANSCRIPT_REGISTRY_FILES = {SOURCE_INVENTORY_NAME}
# INVERTED on purpose. The old allowlist of eight text suffixes meant a leak simply had
# to be written to a .log / .ndjson / .ts / no-suffix file to become invisible; the
# containment rule is about who can READ the path, and a reader does not care about the
# extension. So everything is scanned except formats that cannot carry a readable path
# for a human or a model to follow.
_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif",
    ".pdf", ".zip", ".gz", ".bz2", ".xz", ".7z", ".tar", ".rar",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
    ".mp3", ".mp4", ".mov", ".avi", ".wav", ".m4a", ".dcm", ".bam", ".cram", ".woff", ".woff2",
    ".pyc", ".so", ".dylib", ".o",
}
# Read whole files up to this size; anything larger is streamed in overlapping chunks so
# a 200MB export log cannot hide a leak simply by being big. The old 4MB skip was a
# size-gated bypass: write the path past byte 4,000,000 and the scan never looked.
_CONTAINMENT_WHOLE_FILE_MAX = 16 * 1024 * 1024
_CONTAINMENT_CHUNK = 4 * 1024 * 1024


def _file_mentions(path: Path, needle: str) -> bool:
    """True when `needle` occurs in `path`, whatever the file's size.

    Small files are read whole; large ones are streamed in chunks that overlap by
    len(needle)-1 characters, so a match straddling a chunk boundary is still found.
    """
    size = path.stat().st_size
    if size <= _CONTAINMENT_WHOLE_FILE_MAX:
        return needle in path.read_text(encoding="utf-8", errors="replace")
    overlap = max(len(needle) - 1, 0)
    tail = ""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        while True:
            chunk = fh.read(_CONTAINMENT_CHUNK)
            if not chunk:
                return False
            if needle in tail + chunk:
                return True
            tail = chunk[-overlap:] if overlap else ""


def gate_extracted_fields(patient_dir: Path, errors: list) -> None:
    """extracted_fields.json — the open projection, held to the same floors.

    The open key/value store exists so a real finding in a report no schema anticipated
    is not silently dropped. It must not become the cheap door around the invariants:

      * schema-validated like every other structured output;
      * a lab entry carries its unit, a lab/molecular entry carries the verbatim
        source_reported_text — the same source-shape floor labs.json enforces, so
        filing a number here is never *easier* than filing it properly;
      * every open_ref.source_id resolves to an inventory row (no orphan pointers);
      * Q8: no formal output may cite this file. It is not a legal source library for
        charts or core-completeness, and open fields never enter a settled-fact
        surface. A formal artifact that mentions it is a contract breach, not a typo.
    """
    path = patient_dir / EXTRACTED_FIELDS_NAME
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{EXTRACTED_FIELDS_NAME}: not parseable JSON: {exc}")
            data = None
        if data is not None:
            validate_doc_schema(
                EXTRACTED_FIELDS_NAME, data, "extracted_fields.schema.json", errors
            )
            known_sids = {
                sid for sid in (_entry_id(e) for e in _inventory_entries(patient_dir)) if sid
            }
            entries = data.get("entries") if isinstance(data, dict) else None
            for i, e in enumerate(entries if isinstance(entries, list) else []):
                if not isinstance(e, dict):
                    errors.append(f"{EXTRACTED_FIELDS_NAME}: entries[{i}] must be an object")
                    continue
                label = e.get("label", "<?>")
                cls = e.get("clinical_class")
                if cls in ("lab", "molecular"):
                    srt = e.get("source_reported_text")
                    if not isinstance(srt, str) or not srt.strip():
                        errors.append(
                            f"{EXTRACTED_FIELDS_NAME}: entries[{i}] ({label!r}, {cls}) has no "
                            "source_reported_text — a lab/molecular value that cannot be checked "
                            "against the page verbatim is not reviewable"
                        )
                if cls == "lab":
                    unit = e.get("unit")
                    if not isinstance(unit, str) or not unit.strip():
                        errors.append(
                            f"{EXTRACTED_FIELDS_NAME}: entries[{i}] ({label!r}) is a lab value "
                            "with no unit — a unitless laboratory number is uninterpretable"
                        )
                open_ref = e.get("open_ref")
                if isinstance(open_ref, dict):
                    ref_sid = open_ref.get("source_id")
                    if known_sids and isinstance(ref_sid, str) and ref_sid not in known_sids:
                        errors.append(
                            f"{EXTRACTED_FIELDS_NAME}: entries[{i}] ({label!r}) open_ref.source_id "
                            f"{ref_sid!r} is not in {SOURCE_INVENTORY_NAME} — an open field must "
                            "point back at an inventoried source"
                        )

    # Q8 — the containment check runs whether or not the file exists: a formal output
    # RESTING ON a store that is not even there is the same contract breach.
    #
    # Scoped to citations, not to the word. The previous version failed any formal file
    # whose bytes contained the string "extracted_fields" anywhere, which caught the
    # thing it was aimed at and also caught a reviewer's note explaining that a value
    # was deliberately NOT taken from the open projection. Punishing the sentence that
    # documents the rule teaches producers to stop writing it. What Q8 actually forbids
    # is DERIVING a formal fact from the open store, and a derivation shows up in
    # exactly two places: a source_ref/anchor pointing at it, or a chart declaring it as
    # a data source. Prose that merely mentions it is allowed.
    for fname in list(STRUCTURED_FILES) + ["profile.json", CASE_SUMMARY_DATA_NAME]:
        fpath = patient_dir / fname
        if not fpath.is_file():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        for jpath, ref in collect_source_refs(data):
            if isinstance(ref, str) and EXTRACTED_FIELDS_STEM in ref:
                errors.append(
                    f"{fname}: {jpath} cites {ref!r} — the open projection is NOT a legal source "
                    "library for formal outputs (Q8). A settled fact may not rest on an open "
                    "field; if the value belongs in this output, transcribe it into this output's "
                    "own schema with its own source_refs pointing at the sidecar"
                )
        for where in _chart_data_sources(data):
            if EXTRACTED_FIELDS_STEM in where:
                errors.append(
                    f"{fname}: a chart/series declares {where!r} as its data source — per Q8 the "
                    "open projection never feeds a chart and never enters the core-completeness "
                    "judgement. 摘要渲染 plots known slots only; an open field has no trend line"
                )

    for fname in ANCHOR_SCAN_MARKDOWN_FILES:
        fpath = patient_dir / fname
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in MD_SRC_RE.finditer(text):
            if EXTRACTED_FIELDS_STEM in match.group(1):
                errors.append(
                    f"{fname}: anchor [[src:{match.group(1)}]] points at the open projection — "
                    "Q8. Open fields carry their own open_ref back to the page image and are "
                    "never anchor targets for a narrative surface"
                )


EXTRACTED_FIELDS_STEM = "extracted_fields"
# Keys a render-data file uses to say "this series was computed from X". Narrow and
# explicit: the check must catch a chart wired to the open store without firing on
# ordinary prose that happens to contain the same word.
_CHART_SOURCE_KEYS = {
    "data_source", "dataSource", "source_file", "sourceFile", "series_source",
    "chart_source", "from_file", "dataset",
}


def _chart_data_sources(obj, path="$"):
    """Yield every declared chart/series data-source string in `obj`."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _CHART_SOURCE_KEYS and isinstance(v, str):
                yield v
            yield from _chart_data_sources(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _chart_data_sources(item, f"{path}[{i}]")


def gate_markdown_anchors(patient_dir: Path, errors: list) -> None:
    """Q7 in the narrative surfaces too — 15_ is not anchorable ANYWHERE.

    validate_anchors enforced this over JSON source_refs[] only, so the identical
    citation written as [[src:15_未分类资料/…]] inside timeline.md / case_text.md /
    review_summary.md / INDEX.md sailed through. Those files are not decoration: they
    are what a human reads and what a bare session follows, so a fact anchored there to
    an open, model-named directory is a settled fact resting on 15_ — precisely what Q7
    forbids. Being the *human* surface makes it worse, not lighter.

    Open material is cited the one way it can be: extracted_fields.json's own
    open_ref = {source_id, page, bbox}, which points at the page image rather than at a
    slug a model wrote out of untrusted source text.
    """
    for fname in ANCHOR_SCAN_MARKDOWN_FILES:
        fpath = patient_dir / fname
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in MD_SRC_RE.finditer(text):
            ref = match.group(1).strip()
            rel = ref.split("#", 1)[0]
            if _OPEN_DOMAIN_ANCHOR_RE.match(rel):
                errors.append(
                    f"{fname}: anchor [[src:{ref}]] points into {OPEN_DOMAIN_NN}_ — the open "
                    "archive is not anchorable (Q7), in prose exactly as in JSON. Its sub-bucket "
                    "slugs are written by a model from untrusted source text and its contents are "
                    "by definition material no pinned schema anticipated; a statement a human "
                    "reads must not rest on one. Cite the open field through "
                    "extracted_fields.json open_ref {source_id, page, bbox}, or transcribe the "
                    "value into a formal output with a real sidecar anchor"
                )


def gate_settled_wording(patient_dir: Path, errors: list) -> None:
    """`settled_fact` / `settled_via` may not reappear anywhere (A23 regression gate, B19).

    Under the old contract a verified high-risk value was recorded as a 「settled fact」
    with a `settled_via` note. A23 deleted that vocabulary for one reason: it named a
    CONCLUSION and left the channel optional, so 「settled」 could be written by the same
    pass that did the reading, and downstream had no way to ask 「settled by what?」. The
    replacement says the channel first — `high_risk_fields[].status:
    passed_independent_reread` plus `reread_channel` — and is unwriteable without one.

    A deleted vocabulary comes back unless something watches for it: a prompt that still
    remembers the old key, a partially-updated template, a consumer that writes what it
    used to read. So this scans the delivered surfaces for the two banned tokens.

    What it deliberately does NOT catch is the bare word `settled`:
    `extracted_fields.json.open_verification_status: settled` is the one legal survivor
    (A16), because there it means 「this OPEN field's two reads agreed」 — a statement
    about an unanchorable candidate value, not a verified clinical fact. Matching the
    compound tokens only is what keeps this gate from firing on the contract itself.
    """
    if archive_is_legacy_v3(patient_dir):
        return  # the vocabulary was legal under scheme 3; that is what legacy MEANS
    # pathlib's `*.json` already matches leading-dot names — unlike a shell glob, fnmatch
    # has no hidden-file rule — so globbing `.*.json` as well collected
    # .case_summary_data.json TWICE and printed every hit in it twice. A duplicated ERROR
    # is not a harsher gate, it is a miscount: it makes one defect look like two and
    # invites a reader to "fix" a second occurrence that does not exist. Collected through
    # a set, then ordered, so the output is deduplicated AND stable.
    seen: set = set()
    targets: list[Path] = []
    for cand in sorted(patient_dir.glob("*.json")) + [
        patient_dir / name for name in ANCHOR_SCAN_MARKDOWN_FILES
    ]:
        try:
            key = cand.resolve()
        except OSError:
            key = cand
        if key in seen or not cand.is_file():
            continue
        seen.add(key)
        targets.append(cand)

    for path in targets:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = [
            (i, line.strip())
            for i, line in enumerate(text.splitlines(), 1)
            if _SETTLED_WORDING_RE.search(line)
        ]
        if not hits:
            continue
        rel = path.relative_to(patient_dir).as_posix()
        shown = "; ".join(f"L{i}: {line[:70]}" for i, line in hits[:3])
        errors.append(
            f"settled_wording: {rel} still uses the retired `settled_fact` / `settled_via` "
            f"vocabulary ({len(hits)} line(s)) — {shown}"
            f"{' …' if len(hits) > 3 else ''}. A23 removed it because it names the CONCLUSION "
            "and leaves the channel optional: 「settled」 could be written by the same pass that "
            "did the reading, and nothing downstream could ask 「settled by what?」. The only "
            "legal way to record a verified high-risk value is high_risk_fields[].status: "
            "passed_independent_reread beside its reread_channel. (extracted_fields.json's "
            "open_verification_status: settled is the one permitted survivor and is not matched "
            "here.)"
        )


def gate_transcripts(patient_dir: Path, errors: list) -> None:
    """raw/transcript/ — the verbatim vault stays whole, and stays contained.

    Three assertions:
      1. every inventory row declaring a transcript_path has that file on disk (a
         declared-but-absent transcript makes the provenance chain a promise instead
         of a record);
      2. the masked bucket sidecar derived from a transcribed source carries no
         unmasked PII shapes — the transcript is the ONLY place unmasked text is
         allowed to exist, and the sidecar is the only surface downstream reads;
      3. nothing outside raw/ references raw/transcript/ (except the registries whose
         job is to record it). A path handed to a downstream reader is an invitation
         to open it, which routes the unmasked page around raw/'s access control.
    """
    try:
        import pii_rescan  # sibling module
    except Exception as exc:
        errors.append(f"transcripts: could not import pii_rescan for the shape check: {exc}")
        pii_rescan = None

    legacy = archive_is_legacy_v3(patient_dir)
    for entry in _inventory_entries(patient_dir):
        tpath = entry.get("transcript_path")
        sid = _entry_id(entry) or "<?>"
        if not isinstance(tpath, str) or not tpath:
            # Omitting the key used to skip all three assertions below, which made "no
            # transcript declared" strictly cheaper than a declared, checkable one. A
            # unit whose characters came out of a model must say where the verbatim
            # page lives; a scheme-3 archive predates the contract and is exempt.
            if (
                not legacy
                and entry.get("read_mode") in MODEL_VISION_READ_MODES
                # B6: a scheme-3 row migrated into v4 CANNOT produce a transcript — the
                # pages were read by a model before per-page transcripts existed, and the
                # file was never written. Demanding one would make every pre-v4 archive
                # permanently unmigratable. The exemption is narrow (only
                # migrate_v3_to_v4.py writes this flag) and it is PAID FOR in
                # gate_projection_coverage, which counts the row as unreadable and
                # requires a coverage_gap flag. It buys silence about the transcript, not
                # about the coverage.
                and entry.get("legacy_transcript_unavailable") is not True
            ):
                errors.append(
                    f"transcripts: {sid}: read_mode={entry.get('read_mode')!r} but no "
                    "transcript_path — a unit whose characters were written by a model MUST "
                    "record where its verbatim per-page transcription lives (raw/transcript/"
                    "<source_id>/page-NNN.md). Without it the faithfulness chain is a promise: "
                    "nothing can be re-read, nothing can be sampled, and this gate's assertions "
                    "all short-circuit into silence"
                )
            continue
        if not tpath.startswith(TRANSCRIPT_PREFIX):
            errors.append(
                f"transcripts: {sid}: transcript_path {tpath!r} must live under "
                f"{TRANSCRIPT_PREFIX} — it is unmasked character truth and inherits raw/'s "
                "access control from its location, not from a promise"
            )
            continue
        if not (patient_dir / tpath).is_file():
            errors.append(
                f"transcripts: {sid}: transcript_path not found on disk: {tpath} — a declared "
                "verbatim transcript that does not exist breaks the faithfulness chain"
            )

        sidecar = entry.get("sidecar_path")
        if pii_rescan is not None and isinstance(sidecar, str):
            sc = patient_dir / sidecar
            if sc.is_file():
                findings = pii_rescan.scan_sidecar(sc)
                if findings:
                    kinds = sorted({f[1] for f in findings})
                    errors.append(
                        f"transcripts: {sid}: masked sidecar {sidecar} still carries "
                        f"{len(findings)} unmasked PII shape(s) [{', '.join(kinds)}] while the "
                        f"verbatim transcript exists at {tpath} — the sidecar is the derived, "
                        "MASKED surface; re-mask to [PII_MASKED] leaving clinical characters "
                        "untouched (the transcript itself is never re-masked)"
                    )

    # containment scan
    for f in sorted(patient_dir.rglob("*")):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(patient_dir)
        except ValueError:
            continue
        parts = rel.parts
        if parts and parts[0] == "raw":
            continue  # inside the vault, self-reference is fine
        if rel.as_posix() in _TRANSCRIPT_REGISTRY_FILES:
            continue
        if f.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            leaked = _file_mentions(f, TRANSCRIPT_PREFIX)
        except OSError:
            continue
        if leaked:
            errors.append(
                f"transcripts: {rel.as_posix()} references {TRANSCRIPT_PREFIX} — the verbatim "
                "transcript must never be reachable from a downstream-readable surface. Only "
                f"{', '.join(sorted(_TRANSCRIPT_REGISTRY_FILES))} may record the path; everything "
                "else cites the masked sidecar"
            )


# --------------------------------------------------------------------------- #
# [C5] page completeness — the denominator is the PAGE SET, not the pages that
#      happened to come back
# --------------------------------------------------------------------------- #
_TRANSCRIPT_PAGE_RE = re.compile(r"^page-(\d+)\.md$")


def _safe_sid(sid) -> bool:
    """Is this source_id safe to use as a PATH COMPONENT? (A9)

    Degrades to a conservative inline check rather than to `True` if _pathsafe cannot be
    imported: a path-safety helper that fails open is worse than none, because the caller
    believes it ran.
    """
    try:
        import _pathsafe

        return _pathsafe.is_safe_component(sid)
    except Exception:
        return (
            isinstance(sid, str)
            and 0 < len(sid) <= 64
            and "/" not in sid
            and "\\" not in sid
            and sid not in (".", "..")
            and not any(ord(c) < 32 for c in sid)
        )


def _contained_in(path: Path, root: Path) -> bool:
    try:
        import _pathsafe

        return _pathsafe.contained(path, root)
    except Exception:
        try:
            return not os.path.relpath(
                os.path.realpath(path), os.path.realpath(root)
            ).startswith("..")
        except Exception:
            return False


def _as_page_number(value):
    """A pages.json / frontmatter page value as an int, or None. Accepts "7" and 7."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _transcript_pages(patient_dir: Path, entry: dict) -> dict:
    """page number -> Path for every raw/transcript/<source_id>/page-NNN.md this row has.

    The declared `transcript_path` is folded in but is never the only input: a row may
    name one page while the directory holds five, and the question this answers is 「which
    pages came back」, not 「which page did the row choose to mention」.

    A9: `source_id` carries no pattern in source_inventory.schema.json, so it is a value
    an untrusted document's filename flowed into, not a token. It is passed through
    _pathsafe.is_safe_component before it is joined to a path and the result is asserted
    to be contained in patient_dir, because "s1/../../../etc" is a legal JSON string and
    a read-only gate that follows it is still a gate that reads outside the archive.
    """
    out: dict = {}
    sid = _entry_id(entry)
    if sid and not _safe_sid(sid):
        sid = None
    if sid:
        for p in sorted((patient_dir / TRANSCRIPT_PREFIX / sid).glob("page-*.md")):
            num = None
            m = _TRANSCRIPT_PAGE_RE.match(p.name)
            if m:
                num = int(m.group(1))
            if num is not None and p.is_file():
                out[num] = p
    tpath = entry.get("transcript_path")
    if isinstance(tpath, str) and tpath.startswith(TRANSCRIPT_PREFIX):
        declared = patient_dir / tpath
        m = _TRANSCRIPT_PAGE_RE.match(declared.name)
        if m and declared.is_file() and _contained_in(declared, patient_dir):
            out.setdefault(int(m.group(1)), declared)
    return out


def _declared_pages(patient_dir: Path) -> dict:
    """source_id -> {page number: kind}, merged across every run's pages.json.

    Merge rule: a page READ by any run stays read. If run-1 gave up on page 4 and run-2
    transcribed it, the archive owes a transcript for page 4; the reverse (run-1 read it,
    run-2 marked it unreadable) must not retire the obligation either, because the page
    demonstrably could be read once. Taking the last writer would let a later, lazier run
    shrink the page set — which is the same move at page granularity that
    gate_high_risk_denominator exists to stop at field granularity.
    """
    out: dict = {}
    for run in _provenance_runs(patient_dir):
        pj = run / "pages.json"
        if not pj.is_file():
            continue
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = data.get("pages") if isinstance(data, dict) else data
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            sid = row.get("source_id")
            page = _as_page_number(row.get("page"))
            if not isinstance(sid, str) or not sid or page is None:
                continue
            per = out.setdefault(sid, {})
            kind = row.get("kind")
            if per.get(page) is None or per.get(page) == "unreadable":
                per[page] = kind
    return out


def gate_page_completeness(patient_dir: Path, errors: list, warnings: list) -> None:
    """Every page prepare_pages.py could read must have come back as a transcript (C5).

    The gates around this one all measure per-page or per-field quality: is this span
    real, is this channel independent, does this number occur in its source. Every one of
    them iterates over what EXISTS. So the cheapest way to pass all of them at once was
    never to cheat on a page — it was to lose one. A five-page report that yields four
    transcripts has four clean pages, four verified spans, a faithful sidecar set and a
    field provenance record that reconciles perfectly; the fifth page — the one carrying
    the 剂量 or the 分期 or the variant — simply is not part of any denominator, and
    nothing anywhere in the archive says a page went missing.

    pages.json is the only surface written BEFORE the transcription pass, by a
    deterministic script that counted the pages in the file. That makes it the one
    honest statement of how many pages the document has, and this gate is the
    reconciliation against it:

      * every page prepare_pages.py marked anything other than `unreadable` must have a
        raw/transcript/<sid>/page-NNN.md — the missing page NUMBERS are listed, because
        「4 of 5 pages transcribed」 is not actionable and 「page 3 is missing」 is;
      * `unreadable` pages are exempt BY NAME: prepare_pages.py already recorded that it
        could not rasterize or read them, and that record is itself the disclosure. An
        unreadable page is a declared gap; an absent page is an undeclared one.

    Two scopes are deliberately NOT covered. A source with no transcripts at all whose
    characters no model read (`native_text` taken byte-for-byte, verified as
    `native_text_identity`) has no per-page transcript by contract — demanding one would
    force every born-digital text file to invent page files. And a migrated row
    (`legacy_transcript_unavailable`) is exempt for the reason C3 gives, paid for in
    projection_coverage.

    The inverse — transcripts exist but pages.json does not — is a WARN, not an ERROR:
    the provenance record may legitimately predate this contract or have been pruned, and
    the gate cannot tell a dropped page from a page that was never claimed. It says so
    rather than passing silently, because 「I could not measure this」 and 「I measured
    this and it was fine」 must never print the same way.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "page_completeness", errors):
        return
    declared_all = _declared_pages(patient_dir)
    for entry in _inventory_entries(patient_dir):
        sid = _entry_id(entry)
        if not sid:
            continue
        if _legacy_transcript_exempt(entry):
            continue
        have = _transcript_pages(patient_dir, entry)
        declared = declared_all.get(sid)
        if declared is None:
            if have:
                warnings.append(
                    f"page_completeness: {sid} has {len(have)} transcript page(s) under "
                    f"{TRANSCRIPT_PREFIX}{sid}/ but no run's pages.json lists it, so the page set "
                    "this source was SUPPOSED to yield cannot be recovered. Nothing here is known "
                    "to be wrong — and nothing here is known to be complete either: a dropped page "
                    "and a page that never existed look identical from this side. Re-run "
                    "scripts/prepare_pages.py --run-id <run> to restore the page manifest"
                )
            continue
        if not have and not _is_transcribed_source(patient_dir, entry):
            # A native_text unit's characters were taken byte-for-byte from the file and
            # verified as native_text_identity (A35). It has no per-page transcript by
            # contract, and demanding one would make every born-digital text source fail.
            continue
        expected = sorted(p for p, kind in declared.items() if kind != "unreadable")
        missing = [p for p in expected if p not in have]
        if not missing:
            continue
        unreadable = sorted(p for p, kind in declared.items() if kind == "unreadable")
        errors.append(
            f"page_completeness: {sid}: pages.json records {len(expected)} readable page(s) but "
            f"{TRANSCRIPT_PREFIX}{sid}/ holds {len(have)} — missing page(s) "
            f"{', '.join(str(p) for p in missing)}"
            + (f" (page(s) {', '.join(str(p) for p in unreadable)} are declared unreadable and are "
               "not counted)" if unreadable else "")
            + ". A page that never came back is not a page with a problem — it is a page with no "
            "row in any denominator: no high-risk field, no faithfulness span, no sample, no "
            "provenance record, and no flag. Every other gate in this file would report this "
            "archive as clean. Re-transcribe the missing page(s) into "
            f"{TRANSCRIPT_PREFIX}{sid}/page-NNN.md, or — if the page genuinely cannot be read — "
            "record it as kind: unreadable in pages.json so the gap is declared rather than absent"
        )


# --------------------------------------------------------------------------- #
# [C6] sidecar <-> transcript consistency — the derived surface may not drift
# --------------------------------------------------------------------------- #
_PII_MASK_TOKEN = "[PII_MASKED]"
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u2060"), None)
# Characters that continue a "word" for the whole-word test below. Digits, latin letters
# and the three characters that glue a number together (`.`, `-`, `_`) are all included,
# so "3.2" does NOT match inside "3.21" and "WBC" does not match inside "WBCX". CJK is
# deliberately absent: Chinese has no word boundaries, so a substring match is the only
# available test there and widening the class would simply make every CJK value fail.
_VALUE_WORD_CHARS = set("0123456789abcdefghijklmnopqrstuvwxyz._-")


def _consistency_norm(value) -> str:
    """NFKC-fold, de-zero-width, drop thousands separators, collapse runs of whitespace.

    Whitespace is COLLAPSED, never removed. Deleting it entirely would weld a value to
    its unit — "3.21 10^9/L" becomes "3.2110^9/l", whose first numeric token is 3.2110 —
    and a token that spans two printed numbers compares equal to neither.
    """
    text = unicodedata.normalize("NFKC", str(value)).translate(_ZERO_WIDTH)
    text = text.replace(",", "").replace("\uff0c", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def _num_token_list(probe: str) -> list:
    out: list = []
    for m in _NUM_TOKEN_RE.finditer(probe):
        try:
            out.append(float(m.group(0)))
        except ValueError:
            continue
    return out


def _whole_word_in(needle: str, hay: str) -> bool:
    """`needle` occurs in `hay` with no word character on either side."""
    if not needle or not hay:
        return False
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return False
        j = i + len(needle)
        before_ok = i == 0 or hay[i - 1] not in _VALUE_WORD_CHARS
        after_ok = j == len(hay) or hay[j] not in _VALUE_WORD_CHARS
        if before_ok and after_ok:
            return True
        start = i + 1


def _values_agree(a, b) -> bool:
    """Does the sidecar value `a` say the same thing as the transcript value `b`?

    Three tests, narrowest first:
      1. normalized equality — the overwhelmingly common case, since ingest DERIVES the
         sidecar from the transcript and only masking should change a value;
      2. numeric token equality — the same numbers, printed the same way, in the same
         order. "3.5-9.5" and "3.5 - 9.5" agree; "3.21" and "9.99" do not, and no amount
         of formatting tolerance may ever make them;
      3. whole-word containment either way, for the one legitimate asymmetry: a value
         that carries its unit or its comparator on one side only ("3.21" vs
         "3.21 10^9/L"). Word boundaries are what keep this from degenerating — "3.2"
         does not match inside "3.21", which is exactly the decimal-point slip the gate
         is for.
    """
    na, nb = _consistency_norm(a), _consistency_norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = _num_token_list(na), _num_token_list(nb)
    if ta and tb and len(ta) == len(tb) and all(x == y for x, y in zip(ta, tb)):
        return True
    return _whole_word_in(na, nb) or _whole_word_in(nb, na)


def _frontmatter_fields(text: str) -> list:
    """[(label, value_str)] for every fields[] entry a page frontmatter declares."""
    fm = _parse_page_frontmatter(text)
    out: list = []
    if not isinstance(fm, dict):
        return out
    fields = fm.get("fields")
    for f in fields if isinstance(fields, list) else []:
        if not isinstance(f, dict):
            continue
        value = f.get("value")
        if value is None:
            continue
        label = f.get("label") if isinstance(f.get("label"), str) else "<?>"
        out.append((label, str(value)))
    return out


def gate_sidecar_transcript_consistency(patient_dir: Path, errors: list) -> None:
    """A masked sidecar may lose a value to masking. It may not gain a different one (C6).

    raw/transcript/<sid>/page-NNN.md is what 段 1 read off the page. The bucket sidecar is
    that same page with PII shapes rewritten to [PII_MASKED] — a DERIVED file, and the only
    legal difference between the two is the masking. Every consumer downstream reads the
    sidecar and nothing else (A27), so a value that drifts between the two is a value the
    whole archive believes and no page ever printed.

    Nothing else catches it. gate_field_provenance reads the transcript when one exists,
    so it validates labs.json against the right surface and never compares the two
    surfaces to each other. gate_transcripts checks the sidecar for unmasked PII — a
    different question in the opposite direction. gate_numeric_integrity compares two
    fields the same pass wrote. So a sidecar carrying 9.99 where the transcript says 3.21
    passed every gate in this file: labs.json could be built from either one, the anchors
    resolve, the spans are real, and the number a clinician eventually reads came from
    whichever file the synthesis pass happened to open.

    The comparison is per PAGE, against that page's transcript fields[] (plus
    source_reported_text), and it is one-directional: every sidecar value must be findable
    in the transcript. The transcript is allowed to hold values the sidecar dropped —
    段 2 projects a subset — but the sidecar may never hold one the transcript does not.

    Two exclusions, both principled rather than convenient:
      * a value containing [PII_MASKED] is SKIPPED. Masking is the one transformation
        that legitimately destroys the original, so demanding the masked form be findable
        in the transcript would make correct masking an error;
      * a value shorter than two characters after normalization is skipped, for the
        reason _MIN_EVIDENCE_PROBE gives: a one-character probe is inside almost any
        string, so matching it proves nothing and failing it means nothing.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "sidecar_transcript_consistency", errors):
        return
    for entry in _inventory_entries(patient_dir):
        sid = _entry_id(entry) or "<?>"
        if _legacy_transcript_exempt(entry):
            continue
        pages = _transcript_pages(patient_dir, entry)
        if not pages:
            continue  # no transcript: gate_field_provenance reads the sidecar instead (B3)
        sidecar = entry.get("sidecar_path")
        if not isinstance(sidecar, str) or not sidecar:
            continue  # gate_source_inventory owns a row with no sidecar
        sc = patient_dir / sidecar
        if not sc.is_file():
            continue  # gate_source_inventory owns a sidecar that is not on disk
        try:
            sc_text = sc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sc_fm = _parse_page_frontmatter(sc_text)
        page = _as_page_number(sc_fm.get("page")) if isinstance(sc_fm, dict) else None
        if page is not None and page in pages:
            targets = [pages[page]]
            where = f"page {page}"
        else:
            # The sidecar did not say which page it is, or named one with no transcript
            # (gate_page_completeness owns THAT). Comparing against the union is the
            # honest fallback: it still catches a value that appears nowhere in the
            # source, and it refuses to manufacture an error out of page bookkeeping.
            targets = [pages[p] for p in sorted(pages)]
            where = f"all {len(targets)} transcript page(s)"
        pool: list = []
        t_field_count = 0
        for t in targets:
            try:
                t_text = t.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            pool.extend(_frontmatter_field_strings(t_text))
            t_field_count += len(_frontmatter_fields(t_text))
        sc_fields = [(l, v) for l, v in _frontmatter_fields(sc_text) if _PII_MASK_TOKEN not in v]
        if not pool:
            if sc_fields and t_field_count == 0:
                errors.append(
                    f"sidecar_transcript_consistency: {sid}: {sidecar} declares "
                    f"{len(sc_fields)} field(s) but its own transcript ({where}) declares none — "
                    "an empty transcript fields[] cannot be the origin of a populated sidecar; "
                    "re-derive the sidecar from the transcript (scripts/ingest_transcripts.py)"
                )
            continue
        for label, value in _frontmatter_fields(sc_text):
            if _PII_MASK_TOKEN in value:
                continue
            if len(_evidence_probe(value)) < _MIN_EVIDENCE_PROBE:
                continue
            if any(_values_agree(value, candidate) for candidate in pool):
                continue
            errors.append(
                f"sidecar_transcript_consistency: {sid}: {sidecar} declares "
                f"{label!r} = {value!r}, which does not match ANY fields[].value in its own "
                f"transcript ({where} under {TRANSCRIPT_PREFIX}{sid}/). The sidecar is DERIVED "
                "from the transcript and the only legal difference between them is masking — a "
                "value present in one and absent from the other is a value that drifted after the "
                "page was read. Every downstream consumer reads the sidecar and nothing else, so "
                "this is the number a clinician would eventually see. Re-derive the sidecar from "
                "the transcript (scripts/ingest_transcripts.py); if the value is legitimately "
                f"masked, write {_PII_MASK_TOKEN} rather than a different value"
            )


def gate_projection_coverage(patient_dir: Path, errors: list) -> None:
    """readiness.json.projection_coverage must exist and account for every source.

    "Best effort" projection with no coverage number is indistinguishable from a
    complete one: a report can be fully transcribed, correctly filed, and contribute
    zero structured facts, with nothing anywhere saying so. This gate makes the
    absence countable. It asserts shape and arithmetic only — whether an unprojected
    field class mattered clinically is not a question a script may answer.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    if _blocked_by_unparseable_inventory(patient_dir, "projection_coverage", errors):
        return
    # C3: the legacy population is identified BEFORE the early returns below, because
    # those returns are exactly how the exemption could be collected for free. Three gates
    # stand down for a `legacy_transcript_unavailable` row on the promise that this gate
    # records the gap; if readiness.json is missing or unreadable, that promise is not
    # merely unkept, it is unkeepable, and the archive has taken the exemption and paid
    # nothing. gate_structured already reports a missing readiness.json — but it reports
    # it as a missing file, which says nothing about the rows that are now unchecked by
    # anyone. The debt is named here, next to the rows that incurred it.
    legacy_entries_early = [e for e in _inventory_entries(patient_dir) if _legacy_transcript_exempt(e)]

    def _unpaid(reason: str) -> None:
        if not legacy_entries_early:
            return
        sids = sorted(str(_entry_id(e)) for e in legacy_entries_early)
        errors.append(
            f"projection_coverage: {len(sids)} source(s) claim legacy_transcript_unavailable: "
            f"true ({', '.join(sids[:5])}{' …' if len(sids) > 5 else ''}), which exempts them from "
            "the transcript requirement, the high-risk denominator, faithfulness coverage and the "
            f"human spot-check — but {reason}, so summary.unreadable_sources and the coverage_gap "
            "flag that PAY for those four exemptions cannot be read. An exemption whose price is "
            "unverifiable is not an exemption, it is an unrecorded hole: the pages behind these "
            "rows can never be re-read, re-sampled or independently verified, and right now "
            "nothing in this archive says so"
        )

    readiness_path = patient_dir / READINESS_NAME
    if not readiness_path.is_file():
        # gate_structured owns presence policy (readiness.json is REQUIRED there)
        _unpaid(f"{READINESS_NAME} does not exist")
        return
    try:
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    except Exception:
        _unpaid(f"{READINESS_NAME} is not parseable JSON")
        return  # the structured gate already reports parse failures
    if not isinstance(readiness, dict):
        _unpaid(f"{READINESS_NAME} is not a JSON object")
        return

    cov = readiness.get("projection_coverage")
    if not isinstance(cov, dict):
        errors.append(
            f"{READINESS_NAME}: projection_coverage is missing — every run must declare, per "
            "source, which field classes never reached a structured slot (empty list = fully "
            "projected). Without it an incomplete archive is indistinguishable from a complete one"
        )
        return

    entries = _inventory_entries(patient_dir)
    inv_sids = {sid for sid in (_entry_id(e) for e in entries) if sid}
    novel_sids = {
        _entry_id(e) for e in entries if e.get("kind") == "novel" and _entry_id(e)
    }
    # B6: a migrated row with no transcript is UNREADABLE in the only sense this number
    # means — nothing can re-read it, nothing can sample it, nothing can verify it — even
    # though its kind may legitimately be `known` (the v3 archive did classify it). Both
    # populations are counted here, because a coverage figure that excluded the sources
    # nobody can check again would be measuring exactly the wrong set.
    legacy_unavailable_sids = {
        _entry_id(e)
        for e in entries
        if e.get("legacy_transcript_unavailable") is True and _entry_id(e)
    }
    unreadable_sids = {
        _entry_id(e) for e in entries if e.get("kind") == "unreadable" and _entry_id(e)
    } | legacy_unavailable_sids

    per_source = cov.get("per_source")
    if not isinstance(per_source, list):
        errors.append(f"{READINESS_NAME}: projection_coverage.per_source must be an array")
        return
    covered: set[str] = set()
    fully = 0
    for i, row in enumerate(per_source):
        if not isinstance(row, dict):
            errors.append(f"{READINESS_NAME}: projection_coverage.per_source[{i}] must be an object")
            continue
        sid = row.get("source_id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"{READINESS_NAME}: projection_coverage.per_source[{i}] has no source_id")
            continue
        if sid in covered:
            errors.append(
                f"{READINESS_NAME}: projection_coverage.per_source lists {sid} more than once"
            )
        covered.add(sid)
        classes = row.get("unprojected_field_classes")
        if not isinstance(classes, list):
            errors.append(
                f"{READINESS_NAME}: projection_coverage.per_source[{i}] ({sid}) "
                "unprojected_field_classes must be an array (empty = fully projected)"
            )
            continue
        if not classes:
            fully += 1

    if inv_sids:
        for sid in sorted(inv_sids - covered):
            errors.append(
                f"{READINESS_NAME}: projection_coverage omits source {sid} — every inventoried "
                "source must be accounted for, ESPECIALLY novel and unreadable ones (those are "
                "exactly the sources a coverage number would otherwise hide)"
            )
        for sid in sorted(covered - inv_sids):
            errors.append(
                f"{READINESS_NAME}: projection_coverage lists {sid}, which has no row in "
                f"{SOURCE_INVENTORY_NAME}"
            )

    if legacy_unavailable_sids:
        has_coverage_gap = any(
            isinstance(f, dict) and f.get("category") == "coverage_gap"
            for f in (readiness.get("review_flags") or [])
        )
        if not has_coverage_gap:
            errors.append(
                f"{READINESS_NAME}: {len(legacy_unavailable_sids)} source(s) carry "
                f"legacy_transcript_unavailable: true ({', '.join(sorted(legacy_unavailable_sids)[:5])}"
                f"{' …' if len(legacy_unavailable_sids) > 5 else ''}) but no review_flag has "
                "category=coverage_gap. The migration exemption lets such a row skip the transcript "
                "requirement; it does not let the archive forget that these pages can never be "
                "re-read, re-sampled or independently verified. That fact belongs where humans "
                "look — one flag, category coverage_gap, audience internal_qc"
            )

    summary = cov.get("summary")
    if not isinstance(summary, dict):
        errors.append(f"{READINESS_NAME}: projection_coverage.summary must be an object")
        return
    # sources_total is reconciled against the INVENTORY, not against per_source. Keying
    # it to len(covered) made the summary self-consistent by construction: an empty
    # per_source[] produced sources_total 0, which "agreed" with itself while the
    # archive held a dozen sources. A summary may only be checked against something it
    # did not write.
    expected = {
        "sources_total": len(inv_sids) if inv_sids else len(covered),
        "sources_fully_projected": fully,
    }
    if inv_sids:
        expected["novel_sources"] = len(novel_sids)
        expected["unreadable_sources"] = len(unreadable_sids)
        if not per_source:
            errors.append(
                f"{READINESS_NAME}: projection_coverage.per_source is EMPTY while "
                f"{SOURCE_INVENTORY_NAME} lists {len(inv_sids)} source(s) — an empty coverage "
                "table is not a coverage of zero gaps, it is the absence of the measurement. "
                "Every inventoried source needs a row, even (especially) the unreadable ones"
            )
    for key, want in expected.items():
        got = summary.get(key)
        if got != want:
            errors.append(
                f"{READINESS_NAME}: projection_coverage.summary.{key} is {got!r} but the data says "
                f"{want} — a summary that disagrees with its own rows is worse than no summary"
            )


def gate_review_flag_audience(patient_dir: Path, errors: list) -> None:
    """Every review flag says who it is for, and QC noise can never claim a clinician.

    Before this, visit-prep rendered every flag as 「请医生确认」 — a decimal-point
    disagreement and a genuine cross-source contradiction looked identical to a
    family, so the real ones drowned. audience is required, and the four categories
    that describe how the archive was READ (never what a clinician should decide) are
    pinned to internal_qc so the routing cannot be re-litigated per run.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    readiness_path = patient_dir / READINESS_NAME
    if not readiness_path.is_file():
        return
    try:
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    except Exception:
        return
    flags = readiness.get("review_flags") if isinstance(readiness, dict) else None
    if not isinstance(flags, list):
        return

    # Pinning four categories to internal_qc stops QC noise CLAIMING a clinician, but it
    # said nothing about the opposite move: label everything `source_conflict` /
    # `clinician`, or ship review_flags: [], and the internal QC surface is empty while
    # the archive still contains unresolved read defects. There is no distribution rule
    # that could catch that without judging content — so instead the archive's own
    # deterministic facts are bound to the flags they require. A needs_human_review row
    # is not an opinion; it is a state the run recorded, and it must remain visible on
    # the surface that owns it.
    qc_categories = {f.get("category") for f in flags if isinstance(f, dict)}
    unresolved = [
        _entry_id(e) or "<?>"
        for e in _inventory_entries(patient_dir)
        if e.get("high_risk_review_status") == "needs_human_review"
    ]
    if unresolved and not (qc_categories & {"transcription_disagreement", "source_faithfulness"}):
        errors.append(
            f"{READINESS_NAME}: {len(unresolved)} inventory row(s) "
            f"({', '.join(sorted(unresolved)[:5])}) record high_risk_review_status="
            "needs_human_review, but review_flags[] carries no transcription_disagreement / "
            "source_faithfulness flag. The unverified high-risk field is a fact the run itself "
            "wrote down; if it never reaches the internal QC surface, nobody is ever asked to "
            "resolve it and the archive reads as though every high-risk value was checked"
        )
    for i, flag in enumerate(flags):
        if not isinstance(flag, dict):
            continue
        fid = flag.get("id", f"review_flags[{i}]")
        audience = flag.get("audience")
        category = flag.get("category")
        if audience not in ("clinician", "internal_qc"):
            errors.append(
                f"{READINESS_NAME}: review flag {fid} has no usable audience "
                f"({audience!r}) — must be 'clinician' (a real cross-source clinical "
                "question) or 'internal_qc' (quality noise the organizing side owns). "
                "An unlabelled flag gets rendered to the family as a doctor action"
            )
            continue
        if category in INTERNAL_QC_ONLY_CATEGORIES and audience != "internal_qc":
            errors.append(
                f"{READINESS_NAME}: review flag {fid} has category {category!r} with "
                f"audience {audience!r} — this category describes how the archive was read, "
                "not a clinical decision, so it must be internal_qc"
            )


def gate_update_log_provenance(patient_dir: Path, errors: list, warnings: list) -> None:
    """update_log.runs[] — deferred PII passes stay visible; method names stay closed.

    A text-only increment may auditably defer the semantic PII pass
    (pii_semantic: deferred) so a 14-line lab result does not cost four subagents.
    "Auditable" is only true if something keeps saying the debt exists — hence the
    WARN, every run, until it is paid by the next full run / image increment / export.
    faithfulness_method is enum-checked because an unrecognised value silently means
    "some verification happened", which is exactly the claim that must not be vague.
    """
    path = patient_dir / UPDATE_LOG_NAME
    if not path.is_file():
        # B7: absence used to skip the gate. That made the PII-deferral audit optional in
        # the one direction it must never be: an archive with a deferred semantic scan
        # could delete its own update log and the debt vanished with it — no run history,
        # no deferral to find, no export refusal. The file is how the archive says how it
        # came to be, and an archive that will not say is not finishable.
        errors.append(
            f"{UPDATE_LOG_NAME}: missing — this is a REQUIRED product. It is the only place the "
            "archive records WHICH run added which sources, whether the semantic PII pass actually "
            "ran, and what verification backed it. With it absent, a deferred PII pass leaves no "
            "trace, export_share.py has nothing to refuse on, and a later run cannot tell whether "
            "it may short-circuit. Write it with at least one runs[] entry for the run that built "
            "this archive"
        )
        return
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{UPDATE_LOG_NAME}: not parseable JSON: {exc}")
        return
    validate_doc_schema(UPDATE_LOG_NAME, log, UPDATE_LOG_SCHEMA, errors, warnings)
    runs = log.get("runs") if isinstance(log, dict) else None
    if not isinstance(runs, list):
        errors.append(
            f"{UPDATE_LOG_NAME}: runs must be an array, got "
            f"{type(runs).__name__ if runs is not None else 'nothing'} — every check below "
            "(deferred-PII legality, faithfulness_method vocabulary, run_mode history) iterates "
            "it, so a non-list runs[] does not weaken this gate, it silently removes it"
        )
        return
    if not runs:
        errors.append(
            f"{UPDATE_LOG_NAME}: no runs recorded — runs[] is EMPTY. Every archive was built by "
            "at least one run, so an empty history is not a history of doing nothing, it is the "
            "absence of the record. It is also the same bypass B7 closed one level up: deleting "
            "the file was an error, and emptying its only array reproduced the effect exactly — "
            "no deferred PII pass to find, no run_mode for export_share.py to anchor on, and "
            "nothing for a later incremental run to short-circuit against. Write one runs[] entry "
            "for the run that built this archive"
        )
        # deliberately NOT a `return`: the faithfulness_method scan over
        # raw/_provenance/**/faithfulness-*.json below does not read runs[] at all, and
        # bailing out here would have let an empty runs[] switch off a check that has
        # nothing to do with it — the same shape of silent-skip this error exists to stop.
        # The per-run loop over an empty list is a no-op, so falling through costs nothing.

    # The three conditions that make a deferral AUDITABLE rather than merely absent.
    # Recorded once here so the WARN below and the ERROR beside it cannot drift apart.
    flagged_deferred = False
    readiness_path = patient_dir / READINESS_NAME
    if readiness_path.is_file():
        try:
            rd = json.loads(readiness_path.read_text(encoding="utf-8"))
            flagged_deferred = any(
                isinstance(f, dict) and f.get("category") == "pii_semantic_deferred"
                for f in (rd.get("review_flags") or [])
            )
        except Exception:
            flagged_deferred = False

    deferred: list[str] = []
    for i, run in enumerate(runs):
        if not isinstance(run, dict):
            continue
        rid = run.get("run_id") or run.get("id") or f"runs[{i}]"
        state = run.get("pii_semantic")
        if state is None:
            # Omitting the key used to skip every check below it — the deferral legality
            # test, the fail-closed test, the readiness-flag reconciliation — so a run
            # that simply did not say was cheaper than one that said "deferred" and
            # cheaper than one that said "failed". export_share.py already reads this key
            # directly and refuses on an unpaid deferral; a run that leaves it unset makes
            # that independent check read the archive as clean. The three states are
            # exhaustive by construction: the pass ran (clean), it is owed (deferred), or
            # it broke (failed). There is no fourth thing a finished run can be.
            errors.append(
                f"{UPDATE_LOG_NAME}: {rid}: no pii_semantic — every run must record whether the "
                f"semantic PII pass ran, is owed or failed (one of {sorted(PII_SEMANTIC_STATES)}). "
                "Silence here is read downstream as 「nothing to worry about」 by the one check "
                "(export_share.py) whose whole job is to refuse an unpaid deferral, so an unset "
                "key is strictly cheaper than an honest 'deferred' — which is the shape this gate "
                "exists to remove"
            )
        else:
            if state not in PII_SEMANTIC_STATES:
                errors.append(
                    f"{UPDATE_LOG_NAME}: {rid}: pii_semantic {state!r} is not one of "
                    f"{sorted(PII_SEMANTIC_STATES)} — the semantic PII pass is fail-closed and "
                    "its state vocabulary is closed with it"
                )
            elif state == "deferred":
                deferred.append(str(rid))
                # "Auditable deferral" is a narrow exemption, not a mood. It exists so a
                # 14-line text increment does not cost four subagents — and it is only
                # honest while all three of its preconditions hold. Any one of them
                # missing turns it into an unrun safety pass wearing the word "deferred".
                run_mode = run.get("run_mode")
                added = run.get("added_sources") or []
                non_native = [
                    a.get("source_id")
                    for a in added
                    if isinstance(a, dict) and a.get("read_mode") != "native_text"
                ]
                # B5: TWO run modes may defer, for opposite reasons. `incremental` defers
                # because its new surface is small and text-only, so the debt is bounded
                # and auditable. `migration` defers because it reads NO source characters
                # at all — migrate_v3_to_v4.py rewrites metadata in place, and demanding a
                # semantic pass over an archive the migration never touched would make
                # every pre-v4 archive unmigratable without first re-running organize.
                # What neither buys is silence: both must carry the readiness flag below.
                if run_mode not in PII_DEFERRABLE_RUN_MODES:
                    errors.append(
                        f"{UPDATE_LOG_NAME}: {rid}: pii_semantic=deferred on a run_mode="
                        f"{run_mode!r} run — deferral is legal only for "
                        f"{sorted(PII_DEFERRABLE_RUN_MODES)}. A full run re-reads everything, so "
                        "there is no small surface to defer; a conversation run adds no uploaded "
                        "source at all. In both cases 'deferred' means the semantic pass simply "
                        "did not run, which is an unrun safety pass wearing a label"
                    )
                if non_native and run_mode != "migration":
                    errors.append(
                        f"{UPDATE_LOG_NAME}: {rid}: pii_semantic=deferred but this run added "
                        f"non-native_text source(s) {non_native[:5]} — only a pure text increment "
                        "may defer. A pixel page is exactly where the semantic pass earns its "
                        "keep: a name in a letterhead, a signature, a 住院号 in a stamp are "
                        "invisible to the deterministic shape floor, so deferring on an image "
                        "source ships unmasked identity with nothing left to catch it"
                    )
                if not flagged_deferred:
                    errors.append(
                        f"{UPDATE_LOG_NAME}: {rid}: pii_semantic=deferred but {READINESS_NAME} "
                        "carries no review_flag with category=pii_semantic_deferred — the debt is "
                        "only auditable if it is written where humans look. An entry buried in "
                        "the update log that no review surface repeats is indistinguishable from "
                        "a pass nobody ran"
                    )
            elif state == "failed":
                errors.append(
                    f"{UPDATE_LOG_NAME}: {rid}: pii_semantic=failed — the semantic PII pass is "
                    "fail-closed; the archive is not finishable until it passes"
                )
        method = run.get("faithfulness_method")
        if method is not None and method not in FAITHFULNESS_METHODS:
            errors.append(
                f"{UPDATE_LOG_NAME}: {rid}: faithfulness_method {method!r} is not one of "
                f"{sorted(FAITHFULNESS_METHODS)}"
            )

    for fpath in sorted((patient_dir / "raw" / "_provenance").rglob("faithfulness-*.json")):
        try:
            rec = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        method = rec.get("faithfulness_method") if isinstance(rec, dict) else None
        if method is not None and method not in FAITHFULNESS_METHODS:
            errors.append(
                f"{fpath.relative_to(patient_dir).as_posix()}: faithfulness_method {method!r} is "
                f"not one of {sorted(FAITHFULNESS_METHODS)}"
            )

    if deferred:
        warnings.append(
            f"pii_semantic_deferred: {len(deferred)} run(s) deferred the semantic PII scan "
            f"({', '.join(deferred)}). This is allowed ONLY for a text-only increment and the "
            "debt is still owed — run the semantic pass before the next full run, any image "
            "increment, or any export, and record a readiness review_flag with "
            "category=pii_semantic_deferred / audience=internal_qc"
        )


def _page_totals(patient_dir: Path) -> dict:
    """(source_id -> page_total) from every run's pages.json."""
    totals: dict = {}
    for run in _provenance_runs(patient_dir):
        pages = run / "pages.json"
        if not pages.is_file():
            continue
        try:
            data = json.loads(pages.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = data.get("pages") if isinstance(data, dict) else data
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            sid = row.get("source_id")
            total = row.get("page_total")
            if isinstance(sid, str) and isinstance(total, int):
                totals[sid] = max(totals.get(sid, 0), total)
    return totals


def gate_faithfulness(patient_dir: Path, errors: list) -> None:
    """段 2.5 must have RUN, and its spans must point somewhere real (A20).

    Two separate failures used to be invisible. The first: no faithfulness record at
    all. faithfulness_method was enum-checked only when present, so a run that skipped
    verification entirely passed more easily than one that did it and recorded a
    method — the classic shape where honesty costs and silence is free. The second:
    spans that are syntactically perfect and semantically empty. The validator never
    read a bbox, so [0, 0, 1, 1] — "it is somewhere on this page" — satisfied every
    high-risk field, and a span could name a page the document does not have.

    Hence: at least one faithfulness-*.json per archive; every high_risk_fields[] label
    covered by one; bbox area within [1e-4, 0.5] (below that the box cannot contain a
    legible value, above it the box is not a location); span.page consistent with the
    record's own page; and page ≤ the source's page_total from pages.json.

    What it does NOT do is judge whether the cropped region actually shows the value —
    that is the reread's job, and no script can stand in for it.
    """
    if archive_is_legacy_v3(patient_dir):
        return
    entries = _inventory_entries(patient_dir)
    if not entries:
        return
    # B1: the required set is the UNION of what the archive declared and what the pages
    # themselves imply. Keying it to the declaration alone made 段 2.5 coverage a function
    # of the same array gate_high_risk_denominator exists to stop the run from choosing:
    # empty high_risk_fields[] → nothing required → 「100% of high-risk fields verified」
    # over a set of size zero. The union is what makes that sentence mean something.
    computed = _deterministic_high_risk(patient_dir)
    required: set = set()
    for e in entries:
        sid = _entry_id(e)
        # C3: a migrated row cannot be span-verified — there is no page image and no
        # transcript to draw a bbox on. Requiring a faithfulness record for it would make
        # the only passing move a fabricated span, which is strictly worse than a
        # recorded gap. gate_projection_coverage is where this row is accounted for.
        if _legacy_transcript_exempt(e):
            continue
        hrf = e.get("high_risk_fields")
        for f in hrf if isinstance(hrf, list) else []:
            if isinstance(f, dict) and f.get("label") is not None:
                required.add((sid, str(f.get("label"))))
        for label in (computed.get(sid) or {}):
            required.add((sid, str(label)))

    records: list = []
    for run in _provenance_runs(patient_dir):
        for fpath in sorted(run.glob("faithfulness-*.json")):
            try:
                records.append((fpath, json.loads(fpath.read_text(encoding="utf-8"))))
            except Exception as exc:
                errors.append(
                    f"faithfulness: {fpath.relative_to(patient_dir).as_posix()} is not parseable "
                    f"JSON: {exc}"
                )

    if not records:
        if required:
            errors.append(
                "faithfulness: no raw/_provenance/<run>/faithfulness-*.json exists, but the "
                f"inventory declares {len(required)} high-risk field(s). 段 2.5 is MANDATORY — "
                "the legal exemption for a born-digital source is a recorded "
                "faithfulness_method: native_text_identity from verify_native_text.py, not the "
                "absence of a record. A run that verified nothing must not be cheaper to pass "
                "than one that did"
            )
        return

    totals = _page_totals(patient_dir)
    covered: set = set()
    for fpath, rec in records:
        rel = fpath.relative_to(patient_dir).as_posix()
        if not isinstance(rec, dict):
            continue
        checks = rec.get("checks") or rec.get("fields") or []
        for i, chk in enumerate(checks if isinstance(checks, list) else []):
            if not isinstance(chk, dict):
                continue
            sid = chk.get("source_id") or rec.get("source_id")
            label = chk.get("label")
            if label is not None:
                covered.add((sid, str(label)))
            page = chk.get("page")
            span = chk.get("span")
            if not isinstance(span, dict):
                continue
            span_page = span.get("page")
            if isinstance(page, int) and isinstance(span_page, int) and span_page != page:
                errors.append(
                    f"faithfulness: {rel} checks[{i}] ({label!r}): span.page {span_page} != the "
                    f"record's own page {page} — a span that points at a different page than the "
                    "field it verifies is not evidence of anything"
                )
            eff_page = span_page if isinstance(span_page, int) else page
            total = totals.get(sid)
            if isinstance(eff_page, int) and isinstance(total, int) and eff_page > total:
                errors.append(
                    f"faithfulness: {rel} checks[{i}] ({label!r}): page {eff_page} but source "
                    f"{sid} has only {total} page(s) per pages.json — the span points outside the "
                    "document"
                )
            bbox = span.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4 and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox
            ):
                x0, y0, x1, y1 = (float(v) for v in bbox)
                area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
                if area < 1e-4:
                    errors.append(
                        f"faithfulness: {rel} checks[{i}] ({label!r}): bbox area {area:.2e} is "
                        "below 1e-4 of the page — a box that small cannot contain the value it "
                        "claims to locate, so the crop verified nothing"
                    )
                elif area > 0.5:
                    errors.append(
                        f"faithfulness: {rel} checks[{i}] ({label!r}): bbox area {area:.2f} covers "
                        "more than half the page — [0,0,1,1] and its neighbours say 'somewhere on "
                        "this page', which is the absence of a location. A span must narrow the "
                        "search enough that a human can check it"
                    )
        method = rec.get("faithfulness_method")
        if method is not None and method not in FAITHFULNESS_METHODS:
            errors.append(
                f"faithfulness: {rel}: faithfulness_method {method!r} is not one of "
                f"{sorted(FAITHFULNESS_METHODS)}"
            )

    for sid, label in sorted(required - covered, key=lambda k: (str(k[0]), k[1])):
        errors.append(
            f"faithfulness: {sid} field {label!r} is declared high-risk but no faithfulness record "
            "covers it — 段 2.5 is 100% of high-risk fields plus sampling elsewhere, not sampling "
            "throughout. The fields chosen for unconditional verification are precisely the ones "
            "where a single wrong character changes a dose, a date or a variant"
        )


def gate_ocr_staging_cleared(patient_dir: Path, errors: list) -> None:
    """A finished archive has no ocr/ at all (A29).

    ocr/ is a staging area: 段 1 writes the masked page copies there and 段 2 moves each
    one into its bucket. A leftover ocr/ is not clutter — it is a masked sidecar that
    never reached a bucket, so it has no inventory row, no anchor and no place in any
    coverage number, while still sitting in the archive looking like content. Deleting
    the directory is the completion signal; anything still inside it is work that was
    started and dropped, including under _inbox/ and _reports/.
    """
    ocr = patient_dir / OCR_STAGING_DIR
    if not ocr.is_dir():
        return
    leftovers = [
        f.relative_to(patient_dir).as_posix()
        for f in sorted(ocr.rglob("*"))
        if f.is_file()
    ]
    if leftovers:
        errors.append(
            f"ocr_staging: {len(leftovers)} file(s) remain under {OCR_STAGING_DIR}/ "
            f"({', '.join(leftovers[:5])}{' …' if len(leftovers) > 5 else ''}) — 段 2 must move "
            "every masked page into its bucket and then remove the directory. A page left in "
            "staging has no inventory row and no anchor: it is invisible to every gate and to "
            "every consumer, while the archive looks as though it holds the material"
        )
    else:
        errors.append(
            f"ocr_staging: {OCR_STAGING_DIR}/ still exists (empty) — the completed state is that "
            "the directory is GONE. An empty staging dir is the one case where 'nothing here' and "
            "'never cleaned up' look identical, so the contract removes the directory itself"
        )


def gate_gap_asks(patient_dir: Path, errors: list) -> None:
    """gap_asks.json, when present, is schema-valid (A30). Absent is fine — not every
    archive has asked the patient for anything yet."""
    path = patient_dir / GAP_ASKS_NAME
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{GAP_ASKS_NAME}: not parseable JSON: {exc}")
        return
    validate_doc_schema(GAP_ASKS_NAME, data, GAP_ASKS_SCHEMA, errors)


# --------------------------------------------------------------------------- #
# [4] case-summary HTML shape + provenance
# --------------------------------------------------------------------------- #
def gate_case_summary_html(patient_dir: Path, errors: list) -> None:
    data_path = patient_dir / CASE_SUMMARY_DATA_NAME
    if data_path.is_file():
        try:
            render_data = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{CASE_SUMMARY_DATA_NAME}: not parseable JSON: {exc}")
        else:
            validate_doc_schema(
                CASE_SUMMARY_DATA_NAME,
                render_data,
                "case_summary_data.schema.json",
                errors,
            )

    # (j) core completeness — A21. The check has always existed in
    # validate_case_summary_html.py, but it only ran when a caller happened to pass
    # --profile AND --data. The aggregate gate never did, so the one gate that catches
    # "分期 / 驱动基因 / 当前方案 present in the source and dropped from the summary"
    # was, in practice, never executed. An optional safety check that nothing invokes is
    # indistinguishable from an absent one, so presence of both inputs IS the trigger.
    profile_path = patient_dir / "profile.json"
    if profile_path.is_file() and data_path.is_file():
        try:
            import validate_case_summary_html as vch_core  # sibling module

            core_errors: list[str] = []
            vch_core.core_completeness_check(str(profile_path), str(data_path), core_errors)
            for e in core_errors:
                errors.append(f"{CASE_SUMMARY_DATA_NAME}: {e}")
        except Exception as exc:
            errors.append(
                f"{CASE_SUMMARY_DATA_NAME}: core-completeness gate could not run ({exc}) — "
                "profile.json and the render data are both present, so this check is mandatory; "
                "a gate that silently declines to run is a gate that is not there"
            )

    html_path = patient_dir / CASE_SUMMARY_HTML_NAME
    if not html_path.is_file():
        return  # 摘要渲染 HTML not generated yet — not an error here
    if not CASE_SUMMARY_TEMPLATE.is_file():
        errors.append(
            f"{CASE_SUMMARY_HTML_NAME}: cannot validate — template missing at "
            f"{CASE_SUMMARY_TEMPLATE}"
        )
        return
    try:
        import validate_case_summary_html as vch  # sibling module
    except Exception as e:
        errors.append(f"{CASE_SUMMARY_HTML_NAME}: could not import validator: {e}")
        return
    try:
        html_text = html_path.read_text(encoding="utf-8")
        template_text = CASE_SUMMARY_TEMPLATE.read_text(encoding="utf-8")
    except Exception as e:
        errors.append(f"{CASE_SUMMARY_HTML_NAME}: unreadable input: {e}")
        return
    sub_errors: list[str] = []
    vch.check(html_text, template_text, sub_errors)
    for e in sub_errors:
        errors.append(f"{CASE_SUMMARY_HTML_NAME}: {e}")


# --------------------------------------------------------------------------- #
# entry point — one aggregated exit code
# --------------------------------------------------------------------------- #
def gate_agents_md(patient_dir: Path, errors: list) -> None:
    """AGENTS.md must be the fully-filled template, not a stub.

    A bare session whose cwd is this directory loads AGENTS.md and NOTHING else —
    the red lines inlined in it are the only guardrails present. A stub therefore
    is not a cosmetic defect: it silently removes the floor. `fill_agents_md.py
    --check` re-verifies placeholders, routing anchors, the inlined red lines and
    the template sha256 without writing.
    """
    agents_md = patient_dir / "AGENTS.md"
    if not agents_md.exists():
        errors.append("AGENTS.md missing — run 段 3 (scripts/fill_agents_md.py)")
        return
    checker = SCRIPT_DIR / "fill_agents_md.py"
    if not checker.exists():
        errors.append("fill_agents_md.py missing — cannot verify AGENTS.md")
        return
    proc = subprocess.run(
        [sys.executable, str(checker), str(patient_dir), "--check"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        errors.append(f"agents_md: {detail[-1] if detail else 'verification failed'}")


def gate_no_rogue_agents_md(patient_dir: Path, errors: list) -> None:
    """Exactly one AGENTS.md, at the top level.

    Nested copies are never written by organize, never overwritten by a re-run and
    never scanned by the PII gate — so one dropped into a user-supplied folder is a
    persistent, invisible context injection on every session opened in that subtree.
    """
    found = sorted(p for p in patient_dir.rglob("AGENTS.md") if p.is_file())
    rogue = [p for p in found if p.parent != patient_dir]
    for p in rogue:
        errors.append(
            f"agents_md: unexpected nested {p.relative_to(patient_dir)} — "
            "only <patient_dir>/AGENTS.md is authoritative; quarantine it under 99_无关文件/"
        )
    for name in ("CLAUDE.md", "AGENT.md"):
        for p in sorted(patient_dir.rglob(name)):
            if p.is_file():
                errors.append(
                    f"agents_md: agent-instruction file {p.relative_to(patient_dir)} "
                    "must not live inside a patient archive"
                )


def gate_untrusted_content(patient_dir: Path, warnings: list) -> None:
    """Scan archive text for instruction-shaped content. WARNING, never blocking.

    Deliberately non-blocking: a false positive would kill a real medical record
    ('胃旁路' contains bypass), while a false negative still faces every downstream
    safety gate. Hits are surfaced here and recorded in readiness.json.review_flags[]
    so a human sees them; they never change this script's exit code.
    """
    scanner = SCRIPT_DIR / "scan_untrusted_markers.py"
    if not scanner.exists():
        return
    # `--json` takes a PATH (it writes the report to a file); invoking it with no value
    # made argparse fail, the subprocess exit non-zero and stdout empty — so this gate
    # has been reporting "no parseable report" instead of scanning, silently, every run.
    # `--stdout-json` is the streaming form, and a non-zero exit is now surfaced rather
    # than collapsed into the same generic message.
    proc = subprocess.run(
        [sys.executable, str(scanner), str(patient_dir), "--stdout-json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        warnings.append(
            f"untrusted_content: scanner exited {proc.returncode} "
            f"({detail[-1] if detail else 'no output'}) — the injection-marker scan did NOT run. "
            "This stays a WARN because the scan is advisory by design, but treat the archive as "
            "unscanned rather than clean"
        )
        return
    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        warnings.append("untrusted_content: scanner produced no parseable report")
        return
    findings = report.get("findings") or []
    high = [f for f in findings if f.get("severity") == "high"]
    medium = [f for f in findings if f.get("severity") == "medium"]
    if not findings:
        return
    warnings.append(
        f"untrusted_content: {len(high)} high / {len(medium)} medium instruction-shaped "
        f"hit(s) across {report.get('files_scanned', '?')} file(s) — treat that text as "
        "data to be quoted, never as instructions to follow"
    )
    for f in (high + medium)[:5]:
        warnings.append(
            f"untrusted_content:   {f.get('file', f.get('path', '?'))}:{f.get('line', '?')} "
            f"[{f.get('severity')}] {f.get('rule_id', f.get('rule', '?'))}"
        )
    flags = report.get("review_flags") or []
    if flags:
        _merge_review_flags(patient_dir, flags, warnings)


def _merge_review_flags(patient_dir: Path, flags: list, warnings: list) -> None:
    """Append scanner flags into readiness.json.review_flags[], idempotently.

    Re-running must not duplicate rows, hence an identity key. It is
    (category, affected_field, issue) and NOT (category, detail): `detail` is a key no
    producer emits, so every flag hashed to (category, None) and, after the first merge,
    a second flagged FILE was silently dropped as a duplicate of the first. The scanner's
    category is fixed per rule set, so the file is what distinguishes one flag from
    another.

    `category` is now an enum in readiness.schema.json and every flag carries
    `audience` — the scanner emits audience=internal_qc, so merged rows validate.
    """
    readiness = patient_dir / "readiness.json"
    if not readiness.exists():
        return
    try:
        data = json.loads(readiness.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        warnings.append("untrusted_content: readiness.json unreadable — flags not recorded")
        return
    existing = data.get("review_flags")
    if not isinstance(existing, list):
        return
    def _identity(f: dict) -> tuple:
        return (f.get("category"), f.get("affected_field"), f.get("issue"))

    seen = {_identity(f) for f in existing if isinstance(f, dict)}
    added = [f for f in flags if _identity(f) not in seen]
    if not added:
        return
    # A37: this merge used to run AFTER gate_review_flag_audience, so a flag written in
    # here was never audience-checked by the gate that exists to check exactly that —
    # the one flag category produced by a script rather than by the synthesis pass was
    # the one nobody validated. Ordering is fixed in main(); this is the belt-and-braces
    # half, because a scanner that ever emitted an unlabelled flag would otherwise write
    # an invalid readiness.json and fail schema validation with a confusing message.
    for f in added:
        if not isinstance(f, dict):
            continue
        if f.get("audience") not in ("clinician", "internal_qc"):
            f["audience"] = "internal_qc"
            warnings.append(
                f"untrusted_content: merged flag {f.get('category')!r}/"
                f"{f.get('affected_field')!r} carried no audience — defaulted to internal_qc "
                "(an instruction-shaped-text finding describes the INPUT, never a clinical "
                "question, so it must never render to a family as 「请医生确认」)"
            )
        # The scanner points at wherever it found the text — `AGENTS.md#L61`, a bucket
        # sidecar, anything in the tree. Only three forms are legal source_refs (A39),
        # and a non-bucket file path is none of them, so writing it straight through
        # produced a readiness.json that failed its own schema. The location is real
        # information, though: it moves into `issue`, where it is prose, and source_ref
        # becomes null — an honest "this does not resolve to a citable span".
        for cv in f.get("current_source_values") or []:
            if not isinstance(cv, dict):
                continue
            ref = cv.get("source_ref")
            if ref is None or _is_legal_source_ref(ref):
                continue
            cv["source_ref"] = None
            if ref not in (f.get("issue") or ""):
                f["issue"] = f"{f.get('issue', '')} [发现位置: {ref}]".strip()
    data["review_flags"] = existing + added
    try:
        readiness.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        warnings.append("untrusted_content: could not write readiness.json review_flags")
        return
    warnings.append(
        f"untrusted_content: recorded {len(added)} flag(s) in readiness.json.review_flags[]"
    )


USAGE = """usage: validate_structured_outputs.py <patient_dir>

Total deterministic acceptance gate for a finished organize run. It makes no medical
or content judgement — every check is a form/safety invariant that holds regardless of
which patient was processed.

Exit codes:
  0  every REQUIRED artifact exists (readiness.json + the jsonschema library) and every
     artifact present passed every gate. A form verdict, NOT a completeness verdict: an
     optional artifact that is absent is skipped, never failed
     (longitudinal_observations.json, extracted_fields.json, gap_asks.json, the
     摘要渲染 HTML, update_log.json ...). WARNs are printed above the verdict and never
     change it. A scheme-3 archive is read leniently and WARNed, not failed.
     "Complete" is readiness.json.projection_coverage's question, not this script's.
  1  at least one gate failed (each printed as ERROR: ... on stderr)
  2  bad invocation (no patient_dir, or not a directory)
"""


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        return 0
    if len(sys.argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2

    patient_dir = Path(sys.argv[1]).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []

    # A13: one WARN naming the archive's scheme, emitted before anything else, so a
    # reader of the output knows which contract the verdict below was reached under.
    if archive_is_legacy_v3(patient_dir):
        warnings.append(
            "legacy_archive: source_inventory.json explicitly declares taxonomy scheme_version 3. "
            "The open-world gates — open-domain filing, clinical_class floors, per-field "
            "second-read independence, human spot-check, faithfulness coverage, projection "
            "coverage, review-flag audience, field provenance — are SKIPPED for this archive, "
            "because scheme 3 never defined the fields they read. This is a readable verdict, not "
            "a clean bill of health: run scripts/migrate_v3_to_v4.py to upgrade it to scheme 4 and "
            "get the full gate"
        )

    # B4: runs FIRST, because "which contract is this archive written to?" is the
    # question every gate below silently answered for itself.
    gate_scheme_version(patient_dir, errors)
    gate_structured(patient_dir, errors, warnings)
    gate_pii_rescan(patient_dir, errors)
    # gate_numeric_integrity runs gate_lab_source_shape itself, then adds the
    # value-vs-raw_value check; calling both would double every shape error.
    gate_numeric_integrity(patient_dir, errors)
    gate_field_provenance(patient_dir, errors)
    gate_bucket_taxonomy(patient_dir, errors)
    gate_source_inventory(patient_dir, errors)
    gate_open_domain_filing(patient_dir, errors)
    # B1: the denominator is established BEFORE the per-field quality checks, because
    # those checks say nothing about a set that was allowed to be empty.
    gate_high_risk_denominator(patient_dir, errors)
    gate_high_risk_fields(patient_dir, errors)
    gate_human_sample(patient_dir, errors)
    gate_clinical_class_completeness(patient_dir, errors)
    gate_extracted_fields(patient_dir, errors)
    gate_markdown_anchors(patient_dir, errors)
    gate_settled_wording(patient_dir, errors)
    gate_transcripts(patient_dir, errors)
    # C5 / C6 run immediately after gate_transcripts because all three read the same
    # vault and ask the three different questions it can be wrong in: does the declared
    # transcript exist (transcripts), did EVERY readable page produce one
    # (page_completeness), and does the masked copy downstream reads still say what the
    # transcript says (sidecar_transcript_consistency). The middle one has to precede
    # faithfulness and the denominator conceptually — both of those measure coverage OF
    # the pages that came back, so neither can see a page that never did.
    gate_page_completeness(patient_dir, errors, warnings)
    gate_sidecar_transcript_consistency(patient_dir, errors)
    gate_faithfulness(patient_dir, errors)
    gate_ocr_staging_cleared(patient_dir, errors)
    gate_gap_asks(patient_dir, errors)
    gate_projection_coverage(patient_dir, errors)
    # A37: the scanner's flags are MERGED before the audience gate runs, so a
    # script-written flag faces the same check as a model-written one. Running the merge
    # afterwards meant the only flags produced deterministically were the only flags
    # never validated.
    gate_untrusted_content(patient_dir, warnings)
    gate_review_flag_audience(patient_dir, errors)
    gate_case_summary_html(patient_dir, errors)
    gate_agents_md(patient_dir, errors)
    gate_no_rogue_agents_md(patient_dir, errors)
    gate_ngs_completeness(patient_dir, warnings)
    gate_update_log_freshness(patient_dir, warnings)
    gate_update_log_provenance(patient_dir, errors, warnings)

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if not HAS_JSONSCHEMA:
        # A14: this was a WARN, which meant one missing library silently downgraded
        # EVERY schema-level gate to a two-key existence check while the script still
        # printed "acceptance gate OK" and exited 0. A verdict that cannot be reached
        # must not be reported as a pass.
        errors.append(
            "jsonschema is not installed — every schema-level gate is INOPERATIVE without it "
            "(enums, closed additionalProperties, required fields, the v3/v4 legacy branching all "
            "stop being enforced), leaving only a two-key existence check. That is not a weaker "
            "pass, it is no pass at all. Install with `pip install 'jsonschema>=4.18'` and re-run"
        )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(
        f"acceptance gate OK — structured outputs + PII rescan + normalization consistency + "
        f"field provenance + source inventory + taxonomy v4 + open-domain filing + per-field "
        f"second-read independence + high-risk denominator + human spot-check + "
        f"clinical_class floors + open projection "
        f"+ anchors (Q7/Q8) + transcripts + page completeness + sidecar/transcript consistency "
        f"+ faithfulness + ocr staging + projection coverage + "
        f"review-flag audience + case-summary HTML all pass for what is PRESENT ({patient_dir}); "
        f"missing OPTIONAL artifacts were skipped, so this is a form verdict, not a completeness "
        f"verdict"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
