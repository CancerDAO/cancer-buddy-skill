#!/usr/bin/env python3
"""Total acceptance gate for a finished organize run.

This script is the single deterministic form gate the orchestrator runs after Phase 2 (and
after 段D HTML generation) to decide "is this patient_dir actually done?". It does
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
      markdown file. On a current-contract archive every file but longitudinal_observations.json
      (plus profile.json) must exist (REQUIRED_CURRENT_FILES); jsonschema is required there too — the
      light fallback runs only on a legacy archive and then says the schema rules were not verified.

  [2] PII residue rescan — Layer 2 (pii_rescan.py, deterministic SHAPE floor):
      Independently re-scan every text-masked MD sidecar, the delivered
      (non-sidecar) surfaces (DELIVERED_SURFACES — INDEX.md / source_inventory.json /
      .rename_plan.json / .phase1_sources.json / update_log.json / 病情简要总结.html),
      AND the synthesized surfaces (SYNTHESIZED_SURFACES — case_text.md / profile.json /
      patient_summary.json / timeline.md / review_summary.md / review_flags.md) for
      pure-SHAPE leaks (身份证/手机/座机/email/SSN/≥11位数字/绝对路径/云账号/deny-list
      token, seeded from raw/ filenames; the loose ≥11-digit shape is suppressed on the
      synthesized surfaces to avoid false-firing on de-identified raw-filename timestamps).
      This is the deterministic, zero-network half of the two-layer PII gate. The PRIMARY,
      generalizing half is Layer 1 — the semantic agent scan
      (references/pii-rescan-prompt.md), dispatched by the orchestrator (SKILL.md
      Step 11.5), which catches label/semantic categories (姓名/出生地/职业/家属名/
      签名/检验号…) over the same surfaces. This script enforces only Layer 2; the
      orchestrator enforces Layer 1 separately. Text-only; no OCR/image dependency.

  [2b] Lab source-shape integrity — deterministic, no medical judgement:
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

  [4] Case-summary HTML shape (validate_case_summary_html.py):
      If 病情简要总结.html exists, it must pass the shape+provenance invariants
      against references/templates/case-summary.template.html — including the
      template_sha provenance proving it was machine-rendered (not hand-written).

  [5] Contract generation + legacy leniency. The schemas pin the CURRENT versions
      (readiness/timeline/labs/… "2.1", patient_summary "2.2", source_inventory
      "source_inventory_v2.1", acute_findings/update_log "1"). An archive written under
      an older contract is not corrupt: in a wholly LEGACY archive a document at a
      version listed in LEGACY_SCHEMA_VERSIONS is validated against an in-memory relaxed
      copy of the schema (version const swapped, only the fields introduced later
      dropped from `required`; closed shapes/types/enums still apply) and reported as
      WARN. An archive is "current" as soon as it carries ANY current-contract marker
      (generation_markers: organize_meta.json, readiness.json ≥ 2.1, a structured file at its
      current version, an update_log entry with workers[], a sidecar header naming EXTRACTOR;
      `--generation <dir>` prints the verdict — acute_findings.json is NOT a marker: it is a
      safety surface every pass writes, a Phase-2-only pass on a legacy archive included);
      then the v2.1 gates
      below FAIL (on a legacy archive they WARN), and a structured file still at a legacy
      version is a "mixed-version archive" ERROR, validated against the strict schema — a run
      cannot write an old version number to skip the new required fields.

  [6] v2.1 gates (O-01..O-09) — deterministic bindings, no medical judgement:
      acute_findings.json present (always written; missing on a legacy archive = WARN) + each
      finding ↔ exactly one timeline `acute_finding` event (current archives; on a legacy
      archive timeline_event_id may be null) + line-anchored source_ref whose verbatim text is on the cited
      line + acuity follows the fixed class table, and a non-default acuity_basis_text / a
      stated change_vs_prior.verbatim is quoted from the cited report; sidecar header
      block (pinned keys only, EXTRACTOR ∈ update_log workers, INDEPENDENT_REREAD never
      true for an llm_vision reread, SHA256 a real digest — exactly `none` on a
      prior-archive digest — header ↔ inventory agreement) for the sidecars written under
      this contract (carried-over sidecars of an update-type run: one WARN; run_mode full
      / legacy_upgrade re-transcribes every sidecar); one line numbering
      (str.splitlines(): no form feed / splitlines-only break in a sidecar of this
      contract); review-flag semantics (document_intent needs two agreeing independent
      reads, uncertain_ids / cross-doc refs resolve, [OCR_UNCERTAIN:U-nnn] ↔ `## 不确定字段`
      entries whose line holds the token, whose field_class / layout / layout_intent are
      pinned values, whose candidates exist only for drug_name / ihc_marker / ln_station,
      are whole lines of that class's lexicon, and are `high` only on a complete reading
      at distance 0 with every other reading ≤ 1 edit; kind legibility only for layout
      none; an anchor_coverage_gap flag is kind other / severity red); every printed-page
      gap recorded in missing_items.json; readiness recency fields recomputed from a real
      run date (>14 days needs a warning with the day count; as_of_run_date is the local
      run date, ±1 day of the UTC ledger timestamps); every original under raw/ and every
      logged input is in files[] or skipped_inputs[]; prior-archive digest facts (PS
      statements included) carry provenance_layer prior_archive and never feed current
      status, and a digest's marks agree (source_kind ↔ 既往档案摘录 sub-bucket ↔ SOURCE header;
      a header-less digest is a legacy WARN); update_log schema + timeout/killed workers
      recorded as degradations + no v1 ledger without a full / legacy_upgrade run over
      header-less sidecars (the partial-upgrade trap); conflict_group / medication_refs /
      antineoplastic ↔ episode integrity; profile.latest_status = the ongoing episode's
      regimen / status_as_of / status_basis (as_of null only for an undated self-report);
      profile.json demographics (PS text bound to its source line). Added after the independent
      review: an ellipsis-only quote never binds; acuity_basis_text / change_vs_prior.verbatim on
      the cited line(s) (acuity_basis_ref for another line of the same report) holding the
      acute-findings.md §4.1 pinned words; exam/report dates, status_basis_text and setting_basis
      found in the cited sources; orphan sidecars, header enums, EXTRACTOR phase + files, `## PII`
      last, a body page label left out of PAGE_LABEL; all §1.3 uncertainty keys, reading channels =
      header channels, candidates = scripts/lexicon_candidates.py, every token flagged, §6.1
      severity rows; lab values = the sidecar `## 列配对` record, re-computed from its input by
      pair_lab_columns.py; every missing-page gap flagged; single-file Phase 1 redispatch; the
      clean semantic PII scan recorded in organize_meta.json; the 段D narrative leads with the
      emergent/urgent findings. Added after the Phase-2 replays of legacy archives: a render
      that predates emergent/urgent findings needs Phase 2's pinned stale notice in
      review_summary.md and readiness warnings (legacy archives too; --final: the re-render is
      mandatory); a translated acute quote (verbatim_is_translation) ↔ its sidecar's
      foreign_language_paraphrase flag; a record citing a digest (any of its three marks) is
      prior_archive — never mixed with originals — and never enters longitudinal_observations;
      nothing cites a sidecar flagged prior_archive_digest_unrecognised; function_description
      is clinician wording found in a cited original; a self-reported current regimen keeps its
      患者自述：/家属自述： marker in profile.summary. Added after the verifier's review of those
      replays: the 段D lead is neutral (报告写到, not 报告原文写到) and marks a translated finding
      中文转述; a caveat quoting a translation starts 中文转述，非报告原句：; profile.summary.current_regimen
      minus its marker = latest_status.regimen, and a marker only on a self-reported ongoing
      episode; a conversation_notes/ record never counts as an original (function_description,
      self-report-vs-original conflict grading). Added after the second verifier pass: a translated
      quote is checked in the caveat's quotation slot only (after a colon / opening quote mark, the
      longest finding quote filling it — never a substring of another finding's original); an absent
      or null latest_status is required (ERROR current, WARN legacy) and reads as regimen null; the
      self-report marker names the speaker whatever the summary block's layer, and a marker alone is
      not a regimen; a retired-lead render is named as predating the 段D contract (SKILL.md Step 12
      re-renders on any .case_summary_data.json ERROR). Each gate runs crash-safe (one ERROR line per crash).

Usage:
    python3 scripts/validate_structured_outputs.py <patient_dir> [--readonly]
    python3 scripts/validate_structured_outputs.py --generation <patient_dir>   # current | legacy

    --readonly  never write into the archive (the untrusted-content scan otherwise
                records its review flags in readiness.json). Use it for any check that
                is neither the organize run's own terminal gate nor the Phase 2 worker's
                own §9 run (SMTB intake, audits, replays).

Exit codes:
    0  — all present artifacts pass every gate (missing optional artifacts are OK)
    1  — at least one gate failure
    2  — bad invocation
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = REPO_ROOT / "references" / "schemas"
CASE_SUMMARY_TEMPLATE = REPO_ROOT / "references" / "templates" / "case-summary.template.html"
# The case-summary deliverable keeps a single, language-INDEPENDENT filename across
# all locales — only the scaffold *inside* the HTML localizes (SKILL.md §i18n,
# case-summary-html-prompt.md). This mirrors the `NN_` bucket-prefix policy
# (SKILL.md:78): a stable key downstream can match on, never a per-locale string.
# The renderer (SKILL.md Step 12 `--out`) writes this exact name, so this gate's
# literal stays in lock-step with the producer — do not localize one without the other.
CASE_SUMMARY_HTML_NAME = "病情简要总结.html"
CASE_SUMMARY_DATA_NAME = ".case_summary_data.json"
SOURCE_INVENTORY_NAME = "source_inventory.json"
FORMAL_MARKDOWN_FILES = ("timeline.md", "case_text.md", "review_summary.md", "review_flags.md")

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
    # Conditional: the ask-once ledger, written only by scripts/record_gap_ask.py when an invitation is made.
    "gap_asks.json": "gap_asks.schema.json",
    # Always written by Phase 2 (`findings: []` when none), on a legacy archive too — it is a
    # safety surface, not a contract marker. It has no legacy version, so its own schema and
    # source bindings are checked strictly whatever the archive's generation (gate_acute_findings).
    "acute_findings.json": "acute_findings.schema.json",
}

# Which key carries a document's contract version (default: schema_version).
SCHEMA_VERSION_KEY = {"source_inventory.json": "schema"}

# Legacy structured outputs that predate a schema bump. A pre-bump archive is not
# corrupt — it was correct under the contract in force when it was written — so it
# must stay READABLE (validated against the older shape) while being WARNed as due
# for a re-organize. Blocking it would strand every archive built before the bump.
# Map: file → {legacy version: how to relax the current schema in memory}.
# `drop_required` maps a "/"-separated path inside the schema ("" = root) to the
# fields that became required only in a later version.
_PS21_ANCHORS = ("age_as_of", "age_observations", "birth_year",
                 "height_cm_as_of", "weight_kg_as_of", "ecog_as_of")
LEGACY_SCHEMA_VERSIONS = {
    # patient_summary v2 had no time anchors on demographics: `age` was a bare
    # scalar beside `sex`, which is exactly why cross-year reports collided into a
    # permanent `disputed`. v2.1 added `*_as_of` + `age_observations[]` + `birth_year`;
    # v2.2 adds `performance_status_verbatim[]`.
    "patient_summary.json": {
        "2": {
            "drop_required": {"properties/demographics": _PS21_ANCHORS + ("performance_status_verbatim",)},
            "note": (
                "patient_summary.json is schema_version 2 (pre-time-anchor). "
                "demographics.age / weight_kg / height_cm / ecog carry no `_as_of` "
                "source date, so downstream cannot tell which report each value came "
                "from and must not present them as current. Re-run organize to upgrade "
                "to 2.2 (adds *_as_of + age_observations[] + birth_year + performance_status_verbatim[])."
            ),
        },
        "2.1": {"drop_required": {"properties/demographics": ("performance_status_verbatim",)}},
    },
    "readiness.json": {"2": {"drop_required": {
        "": ("latest_source_date", "days_since_latest", "as_of_run_date"),
        "properties/review_flags/items": ("severity", "kind"),
    }}},
    "timeline.json": {"2": {"drop_required": {"properties/events/items": ("conflict_group", "acute_finding_id")}}},
    "molecular.json": {"2": {"drop_required": {"": ("hla_typing",)}}},
    "treatment_lines.json": {"2": {"drop_required": {"properties/episodes/items": ("status", "status_basis")}}},
    "labs.json": {"2": {"drop_required": {"properties/panels/items/properties/values/items": ("pairing_method",)}}},
    "comorbidities.json": {"2": {"drop_required": {"$defs/medication": ("administration_setting", "setting_basis")}}},
    "missing_items.json": {"2": {"drop_required": {"properties/document_gaps/items": ("severity",)}}},
    "source_inventory.json": {"source_inventory_v2": {"drop_required": {
        "": ("skipped_inputs",),
        "properties/files/items": ("sha256", "size_bytes", "page_count", "page_label",
                                   "source_kind", "second_read_channel", "independent_reread"),
        "properties/files/items/properties/extractor_provenance": ("worker_id",),
    }}},
}

# The archive-level contract marker: readiness.json at or above this version (or an
# organize_meta.json written by write_organize_meta.py) = current-contract archive.
CURRENT_READINESS_VERSION = (2, 1)
UPDATE_LOG_NAME = "update_log.json"
ORGANIZE_META_NAME = "organize_meta.json"
ACUTE_FINDINGS_NAME = "acute_findings.json"
RESERVED_WORKER_IDS = {"orchestrator", "main", "manual", "host", "self", "user"}
# update_log run modes that re-transcribe EVERY original (sidecar_contract_scope): a full run,
# and a legacy upgrade (D1: an archive of an earlier contract is re-read by Phase 1 in full —
# there is no partial upgrade that raises some files' versions and leaves the rest).
FULL_RUN_MODES = ("full", "legacy_upgrade")
STALE_DAYS = 14

# Fixed finding_class → default acuity table (references/acute-findings.md §3; prose + rationale in
# references/acute-findings.md). Only three adjustments exist: a source critical flag
# (→ emergent), the source's own urgency wording (raises the default), and the source
# stating old/chronic/unchanged (→ incidental). The model never triages.
ACUTE_CLASS_DEFAULT = {
    "thrombus_embolism": "urgent",
    "perforation_free_air": "emergent",
    "hemorrhage": "emergent",
    "obstruction": "urgent",
    "effusion_large_or_increasing": "urgent",
    "pneumonitis_ild_suspected": "urgent",
    "fracture_cortical_break": "urgent",
    "critical_result_flag": "emergent",
    "clinical_correlation_requested": "incidental",
    "other_source_flagged": "incidental",
}
ACUITY_RANK = {"incidental": 0, "urgent": 1, "emergent": 2}

# The source wording each acuity adjustment rests on (acute-findings.md §4.1 — the ```text block
# there lists these exact values; tests/eval/lint/13-organize-prompt-contracts.sh check H keeps the
# two in parity). acuity_basis_text must quote the cited line(s) AND contain one of these (NFKC +
# casefold; Latin words match as whole words). 「无显著变化」 alone never demotes a finding: the
# chronic basis needs the report's own 陈旧 / 慢性 wording, and a thrombus also its unchanged
# comparison (§3 row).
# Escalation is a ROUTE written in the §3 row of a class, never a generic "one level up": only the
# classes below have one, each to one target acuity and on its own pinned words. Every other class
# keeps its default whatever urgency or 新发 wording the report uses (新发 then goes to
# change_vs_prior.direction new) — so a new pneumonitis stays urgent, never emergent.
ESCALATION_ROUTES = {
    "thrombus_embolism": ("emergent", ("大面积", "骑跨", "massive", "saddle")),
    "other_source_flagged": ("urgent", ("尽快", "立即", "急诊", "urgent", "urgently", "immediate", "immediately",
                                        "emergency", "emergent", "新发", "较前加重", "new", "worsened", "worsening")),
}
# within other_source_flagged, the "new / worse" words raise only a secondary obstructive change
# (阻塞性炎症 / 阻塞性肺不张 …, acute-findings.md §2): the finding's own quote must name it
OBSTRUCTIVE_ONLY_ESCALATION = ("新发", "较前加重", "new", "worsened", "worsening")
OBSTRUCTIVE_WORDS = ("阻塞", "obstructive")
ACUITY_BASIS_TOKENS = {
    "source_wording_chronic": ("陈旧", "慢性", "old", "chronic"),
    "source_critical_flag": ("危急", "临床重要", "critical", "clinically significant"),
    "source_wording_escalation": tuple(dict.fromkeys(t for _, toks in ESCALATION_ROUTES.values() for t in toks)),
}
THROMBUS_STABLE_TOKENS = ("无变化", "无显著变化", "无明显变化", "未见明显变化", "变化不大", "大致同前", "相仿",
                          "stable", "unchanged", "similar")
# the §3 rows that list a chronic → incidental adjustment; every other class has none
CHRONIC_ADJUSTABLE_CLASSES = ("thrombus_embolism", "hemorrhage", "fracture_cortical_break")


def has_basis_token(text, tokens) -> str | None:
    """The first pinned token `text` contains (CJK: substring; Latin: whole word), else None."""
    if not isinstance(text, str):
        return None
    t = unicodedata.normalize("NFKC", text).casefold()
    for tok in tokens:
        tk = tok.casefold()
        if re.fullmatch(r"[a-z ]+", tk):
            if re.search(r"(?<![a-z])" + re.escape(tk) + r"(?![a-z])", t):
                return tok
        elif tk in t:
            return tok
    return None

ANCHOR_RE = re.compile(
    r"^(([0-9]{2}_[^\s/]+(/[^\s/]+)*\.md(#L\d+(-L\d+)?|#[A-Za-z0-9_-]+)?)|(conversation:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?))$"
)
MD_SRC_RE = re.compile(r"\[\[src:([^\]]+)\]\]")

try:
    from jsonschema import Draft202012Validator  # type: ignore

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


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


def validate_anchors(patient_dir: Path, data, fname: str, errors: list):
    for jpath, ref in collect_source_refs(data):
        if not isinstance(ref, str):
            errors.append(f"{fname}: {jpath} is not a string: {ref!r}")
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
        target = patient_dir / rel
        if not target.is_file():
            errors.append(
                f"{fname}: {jpath} dangling anchor — file not found: {rel}"
            )


def _relax_schema_for_legacy(schema: dict, version_key: str, legacy_version: str,
                             relax: dict) -> dict:
    """Return an in-memory copy of `schema` accepting the legacy shape.

    Only two things are relaxed: the pinned version const (replaced by the legacy
    value — NOT removed: with `additionalProperties: false` a removed property would
    make the version key itself a violation) and the `required` lists named in
    `drop_required` (paths inside the schema, "" = root). Every other constraint —
    closed `additionalProperties`, types, enums, ranges, conditionals — still applies,
    so a legacy archive is read leniently but never validated loosely."""
    legacy = copy.deepcopy(schema)
    legacy.setdefault("properties", {})[version_key] = {"const": legacy_version}
    for ptr, fields in (relax.get("drop_required") or {}).items():
        node = legacy
        for seg in [s for s in ptr.split("/") if s]:
            node = node.get(seg) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict) and isinstance(node.get("required"), list):
            node["required"] = [f for f in node["required"] if f not in fields]
    return legacy


def _version_tuple(v) -> tuple:
    if not isinstance(v, str):
        return ()
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts)


def schema_for_document(fname: str, schema: dict, data) -> tuple[dict, str | None]:
    """Pick the schema to validate `data` with; returns (schema, legacy WARN note | None)."""
    version_key = SCHEMA_VERSION_KEY.get(fname, "schema_version")
    version = data.get(version_key) if isinstance(data, dict) else None
    relax = LEGACY_SCHEMA_VERSIONS.get(fname, {}).get(version) if isinstance(version, str) else None
    if relax is None:
        return schema, None
    current = (schema.get("properties", {}).get(version_key) or {}).get("const")
    note = relax.get("note")
    if note and fname == "patient_summary.json" and version == "2":
        # a Phase-2-only pass may already have written some anchors while keeping the legacy number:
        # name only the fields that are really missing (the static text misled downstream readers)
        demo = data.get("demographics") if isinstance(data.get("demographics"), dict) else {}
        missing = [k for k in _PS21_ANCHORS + ("performance_status_verbatim",) if k not in demo]
        note = (f"patient_summary.json is schema_version 2 (pre-time-anchor); demographics lacks "
                f"{', '.join(missing)} — values without their `_as_of` source date must not be presented as "
                "current. Re-run organize (legacy_upgrade) to reach 2.2." if missing else
                "patient_summary.json is schema_version 2 but already carries the 2.2 demographics anchors; "
                "legacy_upgrade raises the version with the rest of the archive.")
    note = note or (
        f"{fname} is {version_key} {version!r} (current {current!r}) — read leniently: the "
        f"fields introduced after {version!r} are not enforced. Re-run organize to upgrade."
    )
    return _relax_schema_for_legacy(schema, version_key, version, relax), f"legacy_schema: {note}"


def _load_schema(schema_name: str) -> dict:
    return json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))


def _mixed_version_error(fname: str, schema: dict, data) -> str:
    key = SCHEMA_VERSION_KEY.get(fname, "schema_version")
    ver = data.get(key) if isinstance(data, dict) else None
    cur = (schema.get("properties", {}).get(key) or {}).get("const")
    return (
        f"mixed-version archive: {fname} is {key} {ver!r}, current contract requires {cur!r} — "
        "this archive carries a current-contract marker (organize_meta.json, readiness.json ≥ 2.1, a "
        "structured file at its current version, update_log workers[] or a sidecar "
        "EXTRACTOR — `validate_structured_outputs.py --generation <dir>` lists them), so every structured "
        "file is held to the current schema; legacy leniency applies only to a wholly legacy archive (a "
        "run may not write an old version to skip the new required fields). "
        f"{LEGACY_UPGRADE_HINT}"
    )


# One wording for every message that tells a run how a legacy archive becomes current (D1/D2).
LEGACY_UPGRADE_HINT = (
    "A legacy archive becomes current only through run_mode legacy_upgrade (every original "
    "re-transcribed by Phase 1 under the 12-key header, then Phase 2); a Phase-2-only rewrite keeps "
    "the legacy schema_version numbers and writes no organize_meta.json, so the archive stays legacy "
    "(read leniently, WARN)."
)


def _pick_schema(fname: str, schema: dict, data, errors: list, warnings: list | None,
                 current: bool) -> dict:
    """Legacy relax for a wholly legacy archive (WARN); strict + ERROR inside a current one."""
    relaxed, note = schema_for_document(fname, schema, data)
    if note is None:
        return schema
    if current:
        errors.append(_mixed_version_error(fname, schema, data))
        return schema
    if warnings is not None:
        warnings.append(note)
    return relaxed


def validate_one(patient_dir: Path, fname: str, schema_name: str, errors: list,
                 warnings: list | None = None, current: bool | None = None):
    path = patient_dir / fname
    if not path.is_file():
        return  # presence is gate_required_current_files' job (current archives only)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        errors.append(f"{fname}: not parseable JSON: {e}")
        return

    if current is None:
        current = archive_generation(patient_dir) == "current"
    if HAS_JSONSCHEMA:
        try:
            schema = _pick_schema(fname, _load_schema(schema_name), data, errors, warnings, current)
            validator = Draft202012Validator(schema)
            for err in validator.iter_errors(data):
                errors.append(
                    f"{fname}: schema violation at "
                    f"{'.'.join(str(p) for p in err.absolute_path) or '$'}: {err.message}"
                )
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
                        warnings: list | None = None, current: bool = False) -> None:
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
        schema = _pick_schema(fname, schema, data, errors, warnings, current)
        for err in Draft202012Validator(schema).iter_errors(data):
            loc = ".".join(str(p) for p in err.absolute_path) or "$"
            errors.append(f"{fname}: schema violation at {loc}: {err.message}")
    except Exception as e:
        errors.append(f"{fname}: schema load failed for {schema_name}: {e}")


def gate_structured(patient_dir: Path, errors: list, warnings: list | None = None,
                    generation: str | None = None) -> None:
    current = _generation(patient_dir, generation)
    for fname, schema_name in STRUCTURED_FILES.items():
        validate_one(patient_dir, fname, schema_name, errors, warnings, current)


# Written by every Phase 2 run on a current-contract archive (an empty domain is an empty array,
# never an omitted file — phase2 §5). acute_findings.json / update_log.json / source_inventory.json
# have their own presence checks; longitudinal_observations.json and review_flags.md are conditional.
REQUIRED_CURRENT_FILES = (
    "profile.json", "readiness.json", "patient_summary.json", "timeline.json", "molecular.json",
    "treatment_lines.json", "labs.json", "comorbidities.json", "missing_items.json",
)


def gate_required_current_files(patient_dir: Path, errors: list, warnings: list | None = None,
                                generation: str | None = None) -> None:
    """DoD 1 on a current archive: a missing core file is an ERROR — readiness.json carries every
    review flag and the recency fields, so its absence would silently skip those gates."""
    if not _generation(patient_dir, generation):
        return
    for fname in REQUIRED_CURRENT_FILES:
        if not (patient_dir / fname).is_file():
            errors.append(f"{fname}: missing — a current-contract archive always has it (Phase 2 writes it "
                          "every run; an empty domain is written with empty arrays, never omitted)")


# --------------------------------------------------------------------------- #
# [5] contract generation — which gates FAIL vs WARN
# --------------------------------------------------------------------------- #
def _load_json_quiet(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _current_version_const(fname: str) -> str | None:
    """The version const the current schema pins for `fname` (None when unknown)."""
    schema_name = STRUCTURED_FILES.get(fname) or ("source_inventory.schema.json" if fname == SOURCE_INVENTORY_NAME else None)
    if not schema_name:
        return None
    try:
        schema = _load_schema(schema_name)
    except (OSError, ValueError):
        return None
    key = SCHEMA_VERSION_KEY.get(fname, "schema_version")
    const = (schema.get("properties", {}).get(key) or {}).get("const")
    return const if isinstance(const, str) else None


def generation_markers(patient_dir: Path) -> list[str]:
    """Every current-contract marker the archive carries (empty list = wholly legacy archive).

    An archive is current as soon as ANY of these exists, so a run cannot write one old number
    (readiness "2") or skip organize_meta.json to downgrade every v2.1 gate to WARN:
      * organize_meta.json;
      * readiness.json schema_version ≥ 2.1;
      * a structured file whose version was bumped (LEGACY_SCHEMA_VERSIONS) at its CURRENT const;
      * an update_log.json entry carrying workers[] (the v1 ledger of this contract — a v1 ledger
        with legacy-shaped entries only, e.g. `{at, run_mode, source_ids, summary}`, is not one);
      * a bucket sidecar header naming EXTRACTOR (the 12-key header of this contract).
    acute_findings.json is deliberately NOT a marker: it is a safety surface that every pass writes,
    including a Phase-2-only pass on a legacy archive (organizer-prompt-phase2-synthesis.md §4.0), so its
    presence must not flip the archive to the current contract.
    The three real legacy archives and synlib.make_legacy carry none of these."""
    markers: list[str] = []
    if (patient_dir / ORGANIZE_META_NAME).is_file():
        markers.append(ORGANIZE_META_NAME)
    r = _load_json_quiet(patient_dir / "readiness.json")
    if isinstance(r, dict) and _version_tuple(r.get("schema_version")) >= CURRENT_READINESS_VERSION:
        markers.append(f"readiness.json schema_version {r.get('schema_version')!r}")
    for fname in LEGACY_SCHEMA_VERSIONS:
        if fname == "readiness.json":
            continue
        doc = _load_json_quiet(patient_dir / fname)
        if not isinstance(doc, dict):
            continue
        key = SCHEMA_VERSION_KEY.get(fname, "schema_version")
        const = _current_version_const(fname)
        if const is not None and doc.get(key) == const:
            markers.append(f"{fname} {key} {const!r}")
    if _update_log_workers(patient_dir):
        markers.append(f"{UPDATE_LOG_NAME} entries with workers[]")
    try:
        import pii_rescan  # sibling: the one header parser
        for sc in _bucket_sidecars(patient_dir):
            if pii_rescan.parse_header(sc.read_text(encoding="utf-8", errors="replace")).get("EXTRACTOR", "").strip():
                markers.append(f"sidecar header EXTRACTOR ({sc.relative_to(patient_dir).as_posix()})")
                break
    except Exception:
        pass
    return markers


def archive_generation(patient_dir: Path) -> str:
    """'current' when the archive carries any current-contract marker (generation_markers), else 'legacy'."""
    return "current" if generation_markers(patient_dir) else "legacy"


def _router(errors: list, warnings: list | None, current: bool):
    """Return add(msg): ERROR on a current-contract archive, WARN on a legacy one."""
    def add(msg: str) -> None:
        if current:
            errors.append(msg)
        elif warnings is not None:
            warnings.append(f"legacy archive: {msg}")
    return add


def _generation(patient_dir: Path, generation: str | None) -> bool:
    return (generation or archive_generation(patient_dir)) == "current"


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
            errors.append(f"pii_rescan: {rel} {loc} [{pii_type}] {pii_rescan.mask_snippet(snippet, pii_type)}")
    if total:
        errors.append(
            f"pii_rescan: {total} plaintext-PII residue finding(s) in sidecars — "
            "re-mask to [PII_MASKED] (clinical chars untouched) and re-run"
        )

    # the identity deny-list must be readable: an unparseable file (two workers appending to one
    # file used to produce one) would silently switch the identity arm off — fail closed.
    deny_problems: list[str] = []
    pii_rescan.load_deny_tokens(patient_dir, deny_problems)
    for msg in deny_problems:
        errors.append(f"pii_rescan(denylist): {msg}")

    # US-001: the sidecar scan above covers sidecars (header values, body, appendix blocks and
    # the `## PII` trailer). Delivered (non-sidecar) artifacts (DELIVERED_SURFACES —
    # INDEX.md / source_inventory.json / .rename_plan.json / .phase1_sources.json /
    # update_log.json / 病情简要总结.html) AND synthesized surfaces (SYNTHESIZED_SURFACES —
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
            errors.append(f"pii_rescan(delivered): {name} {loc} [{pii_type}] "
                          f"{pii_rescan.mask_snippet(snippet, pii_type)}")
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


def gate_numeric_integrity(patient_dir: Path, errors: list) -> None:
    """Compatibility wrapper; performs source-shape checks only.

    No threshold comparison, abnormality/severity calculation, or clinical
    interpretation occurs here.
    """
    gate_lab_source_shape(patient_dir, errors)


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
    if not isinstance(ref, str):
        return None
    ref = ref.strip()
    if not ref or ref.startswith("conversation:"):
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


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gate_source_inventory(patient_dir: Path, errors: list, warnings: list | None = None,
                          generation: str | None = None) -> None:
    inventory = _read_json_file(patient_dir, SOURCE_INVENTORY_NAME, errors)
    if inventory is None:
        return
    current = _generation(patient_dir, generation)
    validate_doc_schema(SOURCE_INVENTORY_NAME, inventory, "source_inventory.schema.json", errors, warnings,
                        current=current)
    add = _router(errors, warnings, current)

    inventory_files = _file_entries(inventory)
    if not inventory_files:
        errors.append(f"{SOURCE_INVENTORY_NAME}: files[] must list every content unit")
        return
    file_ids = {e.get("file_id") for e in inventory_files if isinstance(e, dict)}
    for e in inventory_files:
        if isinstance(e, dict) and e.get("superseded_by") is not None:
            if e["superseded_by"] not in file_ids or e["superseded_by"] == e.get("file_id"):
                errors.append(f"{SOURCE_INVENTORY_NAME}: {e.get('file_id')} superseded_by {e['superseded_by']!r} names no "
                              "other files[] row (upload-reconciliation.md: 替换 records a relation to the later upload)")

    try:
        import check_bucket_path as cbp  # sibling module — the one bucket whitelist
        tax = cbp.load_taxonomy()
    except Exception as e:
        errors.append(f"bucket_taxonomy: cannot load the pre-write whitelist: {e}")
        cbp, tax = None, None

    sidecar_entries: dict[str, dict] = {}
    persisted_source_ids: set[str] = set()
    sha_owner: dict[str, str] = {}
    for i, entry in enumerate(inventory_files):
        if not isinstance(entry, dict):
            errors.append(f"{SOURCE_INVENTORY_NAME}: files[{i}] must be an object")
            continue
        sid = _entry_id(entry)
        if not sid:
            errors.append(f"{SOURCE_INVENTORY_NAME}: files[{i}] missing stable source_id/id")
            continue

        # raw_path is a protected relative pointer, not an authorization token. A
        # prior-archive digest has no original in this packet: its raw_path is null and
        # digest_of names the earlier archive instead (never a placeholder pointer file).
        raw = entry.get("raw_path")
        if entry.get("source_kind") == "prior_archive_digest":
            if raw is not None:
                errors.append(
                    f"{SOURCE_INVENTORY_NAME}: {sid}: prior_archive_digest raw_path must be null "
                    "— there is no original in this packet; do not point at a placeholder file"
                )
            digest = entry.get("digest_of")
            if not isinstance(digest, dict) or not digest.get("archive_ref") \
                    or not digest.get("sidecar_refs"):
                errors.append(
                    f"{SOURCE_INVENTORY_NAME}: {sid}: prior_archive_digest requires digest_of "
                    "{archive_ref, archive_generated_at, sidecar_refs[]}"
                )
        elif not isinstance(raw, str) or not raw.startswith("raw/"):
            errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: raw_path must point under raw/")
        else:
            # O-07: recorded content hash / size must match the original when it is on disk.
            raw_file = patient_dir / raw
            sha = entry.get("sha256")
            if raw_file.is_file() and isinstance(sha, str):
                try:
                    actual = _sha256_path(raw_file)
                    size = raw_file.stat().st_size
                except OSError:
                    actual, size = None, None
                if actual and actual != sha:
                    add(f"{SOURCE_INVENTORY_NAME}: {sid}: sha256 does not match the original at {raw}")
                size_rec = entry.get("size_bytes")
                if isinstance(size_rec, int) and size is not None and size_rec != size:
                    add(f"{SOURCE_INVENTORY_NAME}: {sid}: size_bytes {size_rec} does not match the original ({size})")
            if isinstance(sha, str):
                owner = sha_owner.setdefault(sha, sid)
                if owner != sid:
                    add(
                        f"{SOURCE_INVENTORY_NAME}: {sid}: same sha256 as {owner} — a byte-identical "
                        "upload is one source; record the copy in skipped_inputs (reason duplicate_sha256)"
                    )

        # O-09: the recorded bucket paths must be on the whitelist, not only the dirs on disk.
        if cbp is not None and tax is not None:
            for key in ("sidecar_path", "bucket_path"):
                val = entry.get(key)
                if isinstance(val, str) and val:
                    msg = cbp.bucket_path_violation(val, tax)
                    if msg:
                        add(f"bucket_taxonomy: {SOURCE_INVENTORY_NAME} {sid}.{key}: {msg}")

        sidecar = entry.get("sidecar_path")
        if not isinstance(sidecar, str) or not sidecar.endswith(".md"):
            errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: sidecar_path must point to a .md sidecar")
        else:
            if sidecar.startswith("ocr/"):
                errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: final sidecar_path must be bucket-co-located, not ocr/")
            if not (patient_dir / sidecar).is_file():
                errors.append(f"{SOURCE_INVENTORY_NAME}: {sid}: sidecar_path not found: {sidecar}")
            sidecar_entries[sidecar] = entry

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


_JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def gate_input_completeness(patient_dir: Path, errors: list, warnings: list | None = None,
                            generation: str | None = None) -> None:
    """O-07: nothing the user supplied is silently dropped.

      (a) every original under raw/ (organize infrastructure `raw/_*` excluded; OS junk —
          .DS_Store / __MACOSX / AppleDouble / zero-byte — excluded) is a files[].raw_path
          or has its sha256 in skipped_inputs[] (duplicate / quarantined / user-excluded …);
      (b) every input of the latest update_log entry that reconciled inputs is in
          files[].sha256 ∪ skipped_inputs[].sha256.
    ERROR on a current-contract archive, WARN on a legacy one."""
    add = _router(errors, warnings, _generation(patient_dir, generation))
    inv = _load_json_quiet(patient_dir / SOURCE_INVENTORY_NAME)
    if not isinstance(inv, dict):
        return  # gate_source_inventory reports the missing / unparseable inventory
    rows = [r for r in _file_entries(inv) if isinstance(r, dict)]
    raw_paths = {r.get("raw_path") for r in rows if isinstance(r.get("raw_path"), str)}
    file_sha = {r.get("sha256") for r in rows if isinstance(r.get("sha256"), str)}
    skipped = [x for x in (inv.get("skipped_inputs") or []) if isinstance(x, dict)]
    skip_sha = {x.get("sha256") for x in skipped if isinstance(x.get("sha256"), str)}
    raw_dir = patient_dir / "raw"
    unaccounted: list[str] = []
    if raw_dir.is_dir():
        import inventory_hash as ih  # sibling: the one definition of vault infrastructure
        for f in ih._walk(raw_dir):
            rel = f.relative_to(raw_dir).as_posix()
            if ih.is_vault_infra(rel):
                continue  # raw/_extract/, raw/_identity_denylist/, raw/_legacy_<ts>/, _FILENAME_MAPPING.md …
            if f.name in _JUNK_NAMES or f.name.startswith("._") or "__MACOSX" in rel.split("/"):
                continue
            if f"raw/{rel}" in raw_paths:
                continue
            try:
                if f.is_symlink():
                    # never followed: a link is accounted for by its own text's hash (reason symlink)
                    if ih.symlink_digest(f)[0] in skip_sha:
                        continue
                elif f.stat().st_size == 0 or _sha256_path(f) in skip_sha | file_sha:
                    continue
            except OSError:
                pass
            unaccounted.append(f"raw/{rel}")
    if unaccounted:
        add(f"input_completeness: {len(unaccounted)} original(s) under raw/ are neither a "
            f"source_inventory files[].raw_path nor a skipped_inputs[] entry "
            f"({', '.join(unaccounted[:5])}{' …' if len(unaccounted) > 5 else ''}) — every input is "
            "ingested (a stub if unreadable) or recorded as skipped with its reason, never dropped")
    last = _latest_input_entry(_update_log_entries(patient_dir))
    if last is not None:
        missing = [x.get("source_id") or "?" for x in last["inputs"]
                   if isinstance(x, dict) and isinstance(x.get("sha256"), str)
                   and x["sha256"] not in file_sha | skip_sha]
        if missing:
            add(f"input_completeness: {len(missing)} input(s) of the latest update_log entry are in neither "
                f"source_inventory files[] nor skipped_inputs[] by sha256 ({', '.join(map(str, missing[:5]))})")


# --------------------------------------------------------------------------- #
# [3b] bucket-taxonomy enforcement (CB-P0-1) — deterministic, NO medical
# judgement. The Phase-2 classifier is instructed to re-file every source onto
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


def _load_bucket_taxonomy(errors: list):
    try:
        return json.loads(BUCKET_TAXONOMY_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"bucket_taxonomy: cannot load {BUCKET_TAXONOMY_JSON.name}: {e}")
        return None


def gate_bucket_taxonomy(patient_dir: Path, errors: list, warnings: list | None = None,
                         generation: str | None = None) -> None:
    """On-disk bucket dirs vs bucket_taxonomy.json (terminal half of the whitelist).

    The whitelist logic lives in check_bucket_path.py — the SAME function Phase 2 calls
    before any mkdir/move (pre-write check) — so the two can never drift apart. On top of the
    pinned slugs: raw/ ocr/ never sit under a clinical domain, an original (any non-.md file)
    never lives in a bucket, and no directory is deeper than <domain>/<sub-bucket> (ERROR on a
    current archive, WARN on a legacy one)."""
    tax = _load_bucket_taxonomy(errors)
    if tax is None:
        return
    try:
        import check_bucket_path as cbp  # sibling module
    except Exception as e:
        errors.append(f"bucket_taxonomy: could not import check_bucket_path: {e}")
        return
    add = _router(errors, warnings, _generation(patient_dir, generation))

    for child in sorted(patient_dir.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if not _DOMAIN_DIR_RE.match(name):
            # non-`NN_` dirs (raw/ ocr/ library/ …) are not clinical domains.
            continue
        msg = cbp.top_level_violation(name, tax)
        if msg:
            errors.append(f"bucket_taxonomy: {msg}")
            continue
        for sub in sorted(child.iterdir()):
            if not sub.is_dir():
                continue
            msg = cbp.sub_bucket_violation(name, sub.name, tax)
            if msg:
                errors.append(f"bucket_taxonomy: {msg}")
        for f in sorted(child.rglob("*")):
            rel = f.relative_to(patient_dir)
            if f.name in _JUNK_NAMES or f.name.startswith("._"):
                continue
            if f.is_dir() and len(rel.parts) > cbp.MAX_BUCKET_DEPTH:
                add(f"bucket_taxonomy: {rel.as_posix()} is deeper than <domain>/<sub-bucket>")
            elif f.is_file() and f.suffix.lower() != ".md":
                add(f"bucket_taxonomy: {rel.as_posix()} is not a .md sidecar — originals live once in raw/, "
                    "never in a bucket")


# --------------------------------------------------------------------------- #
# [3c] Molecular-report transcription coverage — deterministic WARN, NO medical
# judgement. Empty arrays are compared with the source report's own sections;
# this gate does not assert that any report should contain germline, PGx, VUS, or
# a particular gene. WARNs do not change the exit code.
# --------------------------------------------------------------------------- #
def _has_ngs_source(patient_dir: Path) -> bool:
    # (a) an NGS sidecar filed under the pinned NGS sub-bucket (zh or en form).
    for pat in ("06_*/NGS报告/*.md", "06_*/ngs/*.md"):
        if any(patient_dir.glob(pat)):
            return True
    # (b) an NGS entry in source_inventory.json (bucket_path / sidecar_path).
    inv = patient_dir / SOURCE_INVENTORY_NAME
    if inv.is_file():
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
        except Exception:
            data = None
        for entry in _file_entries(data) if data is not None else []:
            if not isinstance(entry, dict):
                continue
            for key in ("bucket_path", "sidecar_path"):
                val = entry.get(key)
                if isinstance(val, str) and ("NGS报告" in val or "/ngs/" in val.lower()):
                    return True
            dt = entry.get("doc_type")
            if isinstance(dt, str) and ("NGS" in dt.upper()):
                return True
    return False


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
# [3d] update_log edit-trail freshness (CB-P2-1, O-04/O-09) — deterministic WARN,
# NO medical judgement. Content hashes, never mtimes: an mtime comparison false-fires
# on a plain `cp -R` and misses an edit that preserved the timestamp. Two checks:
#   (a) inputs — against the LATEST entry that reconciled inputs (non-empty inputs[]):
#       every source_inventory files[].sha256 must be among its inputs[].sha256, and
#       every logged input must still be in the inventory (unless listed in removed[]);
#       otherwise inputs changed outside the flow.
#   (b) outputs — against the MOST RECENT outputs[] row recording each file, across ALL
#       entries (later entries override earlier ones): a 段C conversation entry
#       (inputs: []) rewrites timeline.json / patient_summary.json and records their new
#       hashes. A structured file whose current bytes hash differently from its latest
#       recorded hash was edited outside the organize flow with no changelog entry.
# A legacy update_log without hashes gets one WARN (cannot be verified). WARN only —
# a stale changelog is a hygiene signal, never a hard block. No update_log.json, or
# one with no entries → skip silently (a first run / nothing to compare).
# --------------------------------------------------------------------------- #
def gate_update_log_freshness(patient_dir: Path, warnings: list) -> None:
    update_log = patient_dir / UPDATE_LOG_NAME
    if not update_log.is_file():
        return  # no changelog to compare against — nothing to assert
    doc = _load_json_quiet(update_log)
    entries = doc.get("entries") if isinstance(doc, dict) else (doc if isinstance(doc, list) else None)
    if not isinstance(entries, list) or not entries:
        return
    dict_entries = [e for e in entries if isinstance(e, dict)]
    last = _latest_input_entry(dict_entries) \
        or (entries[-1] if isinstance(entries[-1], dict) else {})
    inputs = last.get("inputs")
    hashed = isinstance(inputs, list) and all(
        isinstance(x, dict) and isinstance(x.get("sha256"), str) for x in inputs)
    outputs = _logged_outputs(dict_entries)
    if not hashed and not outputs:
        warnings.append(
            "update_log_freshness: update_log.json records no content hashes (legacy shape) — "
            "whether inputs or outputs changed outside the organize flow cannot be verified; "
            "re-run organize so entries[].inputs[] carry sha256."
        )
        return
    if hashed:
        inv = _load_json_quiet(patient_dir / SOURCE_INVENTORY_NAME)
        inv_sha: dict[str, str] = {}
        for row in _file_entries(inv) if isinstance(inv, dict) else []:
            if isinstance(row, dict) and isinstance(row.get("sha256"), str):
                inv_sha.setdefault(row["sha256"], _entry_id(row) or "?")
        logged = {x["sha256"]: x.get("source_id") for x in inputs}
        removed = {str(x) for x in (last.get("removed") or [])}
        unlogged = sorted(sid for sha, sid in inv_sha.items() if sha not in logged)
        if unlogged:
            warnings.append(
                f"update_log_freshness: source_inventory lists {len(unlogged)} input(s) whose "
                f"sha256 is not in the latest update_log entry ({', '.join(unlogged[:5])}) — "
                "inputs changed outside the organize flow; re-run organize (incremental) so the "
                "change is logged."
            )
        vanished = sorted(str(sid) for sha, sid in logged.items()
                          if sha not in inv_sha and str(sid) not in removed)
        if vanished and inv_sha:
            warnings.append(
                f"update_log_freshness: {len(vanished)} logged input(s) are no longer in "
                f"source_inventory and not listed in removed[] ({', '.join(vanished[:5])})."
            )
    for fname, logged_sha in outputs.items():
        target = patient_dir / fname
        if not target.is_file():
            continue
        try:
            current = _sha256_path(target)
        except OSError:
            continue
        if current != logged_sha:
            warnings.append(
                f"update_log_freshness: {fname} edited outside the organize flow — its "
                "content no longer matches the hash the latest update_log entry recording it "
                "logged; re-run organize or append an update_log entry."
            )


def _logged_outputs(entries: list[dict]) -> dict[str, str]:
    """{file: sha256} from the most recent outputs[] row that records each file — later
    entries override earlier ones, so a 段C entry's new timeline.json hash replaces the
    full run's, and a file only the full run recorded keeps that run's hash."""
    out: dict[str, str] = {}
    for e in entries:
        rows = e.get("outputs") if isinstance(e.get("outputs"), list) else []
        for o in rows:
            if isinstance(o, dict) and isinstance(o.get("file"), str) and isinstance(o.get("sha256"), str):
                out[o["file"]] = o["sha256"]
    return out


# --------------------------------------------------------------------------- #
# [4] case-summary HTML shape + provenance
# --------------------------------------------------------------------------- #
# case-summary-html-prompt.md「急性/附带发现」: with emergent/urgent findings the 病情概要 narrative's
# FIRST sentence is this lead followed by each finding's label and date (labels and dates only). The lead is
# neutral — 「报告写到」, never 「报告原文写到」 — because a finding registered from a Chinese rendering of a
# foreign-language report (verbatim_is_translation, acute-findings.md §2.4) is in the same list: its item carries
# ACUTE_LEAD_TRANSLATION_MARK inside its date parentheses, 「<label>（<日期>，中文转述）」. A caveat quoting that
# finding introduces the quote with ACUTE_CAVEAT_TRANSLATION_PREFIX, never 「报告原文：」.
# tests/eval/lint/13 (check N) pins all three in case-summary-html-prompt.md.
ACUTE_SUMMARY_LEAD = "资料中有报告写到需要尽快告知治疗团队的发现："
ACUTE_LEAD_TRANSLATION_MARK = "中文转述"
ACUTE_CAVEAT_TRANSLATION_PREFIX = "中文转述，非报告原句："
# the lead of 段D renders made before the neutral lead (b1624f4..6c69146): named in the ERROR so the orchestrator
# knows the render predates the contract (SKILL.md Step 12 re-renders on any .case_summary_data.json ERROR)
RETIRED_ACUTE_SUMMARY_LEAD = "资料中有报告原文写到需要尽快告知治疗团队的发现："


def _urgent_findings(acute_doc) -> list[dict]:
    findings = acute_doc.get("findings") if isinstance(acute_doc, dict) else None
    return [f for f in (findings or []) if isinstance(f, dict) and f.get("acuity") in ("emergent", "urgent")]


def _lead_marks_translation(first_norm: str, label_norm: str) -> bool:
    """True when some occurrence of the label in the (normalised) first sentence is followed by its
    parenthesised date group holding 中文转述 — 「<label>（<日期>，中文转述）」 (NFKC: （ → ( and ， → ,)."""
    mark = _norm_text(ACUTE_LEAD_TRANSLATION_MARK)
    start = 0
    while label_norm:
        i = first_norm.find(label_norm, start)
        if i < 0:
            return False
        rest = first_norm[i + len(label_norm):]
        close = rest.find(")")
        if rest.startswith("(") and close > 0 and mark in rest[:close]:
            return True
        start = i + 1
    return False


def _lead_missing(acute_doc, render_data) -> tuple[list[str], list[dict]]:
    """(problems, findings the 段D narrative's first sentence does not name correctly). The emergent/urgent
    findings of acute_findings.json lead the 段D narrative: its first sentence (up to the first 。) starts with
    ACUTE_SUMMARY_LEAD and names every such finding's label and its date (exam_date, else report_date, when
    the source gives one); a verbatim_is_translation finding's item is marked 中文转述 in its date parentheses."""
    urgent = _urgent_findings(acute_doc)
    if not urgent or not isinstance(render_data, dict):
        return [], []
    narrative = render_data.get("case_summary_narrative")
    first = narrative.split("。", 1)[0] if isinstance(narrative, str) else ""
    if not first.startswith(ACUTE_SUMMARY_LEAD):
        retired = first.startswith(RETIRED_ACUTE_SUMMARY_LEAD)
        return ([f"case_summary_narrative's first sentence must start 「{ACUTE_SUMMARY_LEAD}」 and list the "
                 f"{len(urgent)} emergent/urgent finding(s) (case-summary-html-prompt.md 急性/附带发现)"
                 + (" — it starts with the retired lead 「资料中有报告原文写到…」: the render predates the current 段D "
                    "contract, and its acute_findings_sha256 stamp proves the data, not the contract; the 段D "
                    "re-render (SKILL.md Step 12) is due whether or not a finding changed" if retired else "")], urgent)
    out, missing = [], []
    first_norm = _norm_text(first)
    for f in urgent:
        label = f.get("label")
        day = f.get("exam_date") or f.get("report_date")
        if isinstance(label, str) and _norm_text(label) not in first_norm:
            out.append(f"case_summary_narrative's first sentence does not name {f.get('finding_id')} ({label!r})")
            missing.append(f)
        elif isinstance(day, str) and day not in first:
            out.append(f"case_summary_narrative's first sentence names {f.get('finding_id')} without its date {day}")
            missing.append(f)
        elif f.get("verbatim_is_translation") is True and isinstance(label, str) \
                and not _lead_marks_translation(first_norm, _norm_text(label)):
            out.append(f"case_summary_narrative's first sentence names {f.get('finding_id')} ({label!r}), a Chinese "
                       "rendering of a foreign-language report (verbatim_is_translation), without "
                       f"「{ACUTE_LEAD_TRANSLATION_MARK}」 in its date parentheses — write 「<label>（<日期>，"
                       f"{ACUTE_LEAD_TRANSLATION_MARK}）」 (acute-findings.md §2.4)")
            missing.append(f)
    return out, missing


# The quotation slot a caveat quotes a finding in (case-summary-html-prompt.md「急性/附带发现」: 「报告原文：<verbatim_text>
# （<日期>，<来源文书>）——…」): right after a colon or an opening quote mark (or at the start of the caveat), and
# followed — past an optional closing quote mark — by 「（」「；」「——」「。」 or the end of the caveat. The text in a slot
# is the LONGEST verbatim_text of acute_findings.json that fills it, so a translated finding's words that happen to
# sit inside another finding's correctly quoted original (「充盈缺损」 inside 「报告原文：…分支充盈缺损……」) are that
# other finding's quote, and a phrase elsewhere in a sentence is no quote at all. tests/eval/lint/13 (check N) pins
# this sentence in case-summary-html-prompt.md and runs the prompt's two caveat forms through translated_caveat_problems.
ACUTE_CAVEAT_QUOTE_SLOT_RULE = ("引文位置（冒号或开引号之后，其后紧接“（”“；”“——”“。”或该条结尾；按占满这个位置的最长一条"
                                "发现原句计）")
_QUOTE_OPENERS = "「『“‘\"'"
_QUOTE_CLOSERS = "」』”’\"'"
_QUOTE_ENDS = ("(", ";", "—", "。")  # NFKC: （ → (, ； → ;


def _slot_quote_len(t: str, p: int, q: str) -> int:
    """len(q) when q fills the quotation slot starting at t[p] (see ACUTE_CAVEAT_QUOTE_SLOT_RULE), else 0."""
    if not q or not t.startswith(q, p):
        return 0
    after = t[p + len(q):]
    if after[:1] and after[:1] in _QUOTE_CLOSERS:
        after = after[1:]
    return len(q) if after == "" or after.startswith(_QUOTE_ENDS) else 0


def translated_caveat_problems(acute_doc, render_data) -> list[tuple[str, dict]]:
    """[(problem, finding)] for every verbatim_is_translation finding (any acuity) whose verbatim_text a render
    caveat puts in a quotation slot (ACUTE_CAVEAT_QUOTE_SLOT_RULE) without ACUTE_CAVEAT_TRANSLATION_PREFIX right
    before it — a Chinese rendering shown as the report's own words (「报告原文：…」「报告写道：…」, or bare).
    The slot holds the longest finding quote that fills it; an untranslated finding whose verbatim_text is the same
    words keeps its 「报告原文：」 quote unless the parentheses after it name only the translated finding's date."""
    findings = [f for f in (acute_doc.get("findings") if isinstance(acute_doc, dict) else None) or []
                if isinstance(f, dict) and isinstance(f.get("verbatim_text"), str) and _norm_text(f["verbatim_text"])]
    caveats = render_data.get("caveats") if isinstance(render_data, dict) else None
    texts = [_norm_text(c["caveat_text"]) for c in (caveats if isinstance(caveats, list) else [])
             if isinstance(c, dict) and isinstance(c.get("caveat_text"), str)]
    if not any(f.get("verbatim_is_translation") is True for f in findings):
        return []
    prefix = _norm_text(ACUTE_CAVEAT_TRANSLATION_PREFIX)
    quotes = [(_norm_text(f["verbatim_text"]), f) for f in findings]

    def day(f) -> str | None:
        d = f.get("exam_date") or f.get("report_date")
        return d if isinstance(d, str) and d else None

    bad: list[dict] = []
    for t in texts:
        slots = {0} | {i + 1 for i, ch in enumerate(t) if ch == ":" or ch in _QUOTE_OPENERS}
        for p in sorted(slots):
            if t[p:p + 1] and t[p:p + 1] in _QUOTE_OPENERS:
                continue  # the slot after this opening mark is checked on its own
            fill = max((_slot_quote_len(t, p, q) for q, _ in quotes), default=0)
            if not fill:
                continue
            quoted = [f for q, f in quotes if len(q) == fill and _slot_quote_len(t, p, q)]
            intro = t[:p][:-1] if t[p - 1:p] and t[p - 1:p] in _QUOTE_OPENERS else t[:p]
            if intro.endswith(prefix):
                continue  # labelled as a rendering
            translated = [f for f in quoted if f.get("verbatim_is_translation") is True]
            twins = [f for f in quoted if f.get("verbatim_is_translation") is not True]
            after = t[p + fill:]
            after = after[1:] if after[:1] and after[:1] in _QUOTE_CLOSERS else after
            paren = after[1:after.find(")")] if after.startswith("(") and ")" in after else ""
            # the same words registered from an original report too: it is that finding's quote unless the
            # parentheses name the translated finding's date and not the original's
            if twins and not all(day(f) and day(f) in paren and not any(day(g) and day(g) in paren for g in twins)
                                 for f in translated):
                continue
            bad.extend(f for f in translated if not any(f is b for b in bad))
    return [(f"caveats quote {f.get('finding_id')} (verbatim_is_translation: a Chinese rendering of a "
             f"foreign-language report) without 「{ACUTE_CAVEAT_TRANSLATION_PREFIX}」 right before the quote — a "
             "rendering is never introduced as 「报告原文：」 or quoted bare (case-summary-html-prompt.md 急性/附带发现, "
             "acute-findings.md §2.4)", f) for f in bad]


def case_summary_acute_problems(acute_doc, render_data) -> list[str]:
    """[] = OK / nothing to check (see _lead_missing and translated_caveat_problems)."""
    return _lead_missing(acute_doc, render_data)[0] + [m for m, _ in translated_caveat_problems(acute_doc, render_data)]


# phase2 §7 「段D 过期提示」: while the render predates emergent/urgent findings (stale / unstamped render, or a
# 病情简要总结.html with no render data to check), Phase 2 writes this pinned sentence — followed by each missing
# finding's 「<label>（<date>）」 — as a line of review_summary.md AND an entry of readiness.json.warnings[]. It stays
# true after the (mandatory) re-render, so nobody has to remove it. tests/eval/lint/13 pins it in the prompt.
CASE_SUMMARY_STALE_NOTICE = ("本次登记了需要尽快告知治疗团队的发现，登记时现有的病情简要总结.html 还没有写入它们"
                             "（该文件若未在本次之后重新生成，请以 acute_findings.json 为准）：")


def stale_notice_problems(patient_dir: Path, missing: list[dict]) -> list[str]:
    """What is absent of the stale notice for `missing` findings: [] = both places carry the pinned
    sentence naming every missing finding's label."""
    head = _norm_text(CASE_SUMMARY_STALE_NOTICE)
    labels = [_norm_text(f["label"]) for f in missing if isinstance(f.get("label"), str)]

    def names_all(s: str) -> bool:
        return all(lb in s for lb in labels)

    out = []
    try:
        lines = (patient_dir / "review_summary.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    if not any(head in _norm_text(l) and names_all(_norm_text(l)) for l in lines):
        out.append("review_summary.md")
    r = _load_json_quiet(patient_dir / "readiness.json")
    ws = [w for w in (r.get("warnings") or []) if isinstance(w, str)] if isinstance(r, dict) else []
    if not any(_norm_text(w).startswith(head) and names_all(_norm_text(w)) for w in ws):
        out.append("readiness.json warnings[]")
    return out


# The 段D render stamps the sha256 of the acute_findings.json it read (scripts/
# stamp_case_summary_sources.py), which separates "段D read the finding and left it out" (fresh) from
# "the findings changed after 段D rendered" (stale / unstamped).
CASE_SUMMARY_ACUTE_STAMP = "acute_findings_sha256"


def case_summary_render_state(patient_dir: Path, render_data) -> str:
    """'fresh' — the render's acute_findings_sha256 is the current acute_findings.json's sha256;
    'stale' — it names another version (the file changed after 段D rendered); 'unstamped' — no stamp
    (a render from before the stamp existed, or a 段D run that skipped the stamping step)."""
    stamp = render_data.get(CASE_SUMMARY_ACUTE_STAMP) if isinstance(render_data, dict) else None
    if not isinstance(stamp, str):
        return "unstamped"
    try:
        current = _sha256_path(patient_dir / ACUTE_FINDINGS_NAME)
    except OSError:
        return "stale"
    return "fresh" if stamp == current else "stale"


def gate_case_summary_html(patient_dir: Path, errors: list, warnings: list | None = None,
                           generation: str | None = None, final: bool = False) -> None:
    # The narrative lead (case_summary_acute_problems) — a safety surface, so the same on a legacy and a
    # current archive (a legacy_phase2_only pass writes acute_findings.json and 段D re-renders on it too):
    #   fresh render (stamp == current acute_findings.json) → ERROR: 段D read the finding and left it out;
    #   stale / unstamped render, or a 病情简要总结.html without render data to check → the re-render is
    #     mandatory (SKILL.md Step 12, no freshness question); until it happens Phase 2's pinned stale notice
    #     (CASE_SUMMARY_STALE_NOTICE, phase2 §7) must name the missing findings in review_summary.md AND
    #     readiness.json warnings[] — ERROR when either is absent, WARN "段D stale" when both are there;
    #   --final → ERROR on any stale lead: the terminal gate asserts the mandatory re-render happened.
    # "Leads with" includes the translation labels (acute-findings.md §2.4): a verbatim_is_translation finding is
    # marked 中文转述 in the lead, and a caveat quoting it starts ACUTE_CAVEAT_TRANSLATION_PREFIX — an urgent
    # finding's caveat follows the lead's routing, an incidental one's is ERROR (fresh) / WARN (stale).
    current = _generation(patient_dir, generation)
    acute_doc = _load_json_quiet(patient_dir / ACUTE_FINDINGS_NAME)

    def stale(problems: list[str], missing: list[dict], state: str, where: str) -> None:
        ids = ", ".join(str(f.get("finding_id")) for f in missing)
        if final:
            for msg in problems:
                errors.append(f"{where}: {msg} — 段D stale ({state} render) at the terminal gate: a new or changed "
                              "emergent/urgent finding makes the 段D re-render mandatory; re-run 段D (Step 12)")
            return
        absent = stale_notice_problems(patient_dir, missing)
        if absent:
            errors.append(f"{where}: 段D stale ({state} render) — it does not lead with (or mislabels) emergent/urgent finding(s) "
                          f"{ids}, and the pinned stale notice naming them is missing from {' and '.join(absent)} "
                          f"(phase2 §7: a line starting 「{CASE_SUMMARY_STALE_NOTICE[:24]}…」 followed by each "
                          "missing finding's label); the re-render (SKILL.md Step 12) is mandatory")
        elif warnings is not None:
            warnings.append(f"{'' if current else 'legacy archive: '}{where}: 段D stale ({state} render: "
                            f"acute_findings.json changed after 段D rendered; {ids} not in its lead) — the stale "
                            "notice is in place; the re-render (SKILL.md Step 12) is mandatory")

    data_path = patient_dir / CASE_SUMMARY_DATA_NAME
    html_path = patient_dir / CASE_SUMMARY_HTML_NAME
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
            problems, missing = _lead_missing(acute_doc, render_data)
            # a translated quote in the caveats (acute-findings.md §2.4): an emergent/urgent finding's follows the
            # lead's routing (it is part of carrying that finding correctly); an incidental one's is an ERROR on a
            # fresh render and a WARN on a stale one (its re-render is not mandatory, SKILL.md Step 12)
            incidental: list[str] = []
            for msg, f in translated_caveat_problems(acute_doc, render_data):
                if f.get("acuity") in ("emergent", "urgent"):
                    problems.append(msg)
                    if not any(f is m for m in missing):
                        missing.append(f)
                else:
                    incidental.append(msg)
            state = case_summary_render_state(patient_dir, render_data) if problems or incidental else None
            for msg in incidental:
                if state == "fresh":
                    errors.append(f"{CASE_SUMMARY_DATA_NAME}: {msg} — re-run 段D (Step 12)")
                elif warnings is not None:
                    warnings.append(f"{CASE_SUMMARY_DATA_NAME}: {msg} ({state} render: it predates the current "
                                    "acute_findings.json — the next 段D render writes it correctly)")
            if problems:
                if state == "fresh":
                    for msg in problems:
                        errors.append(f"{CASE_SUMMARY_DATA_NAME}: {msg} — this render read the current acute_findings.json "
                                      f"({CASE_SUMMARY_ACUTE_STAMP} matches); re-run 段D (Step 12)")
                else:
                    stale(problems, missing, state, CASE_SUMMARY_DATA_NAME)
    elif html_path.is_file() and _urgent_findings(acute_doc):
        # an older 段D left no render data: nothing shows the HTML carries the findings
        urgent = _urgent_findings(acute_doc)
        stale([f"{CASE_SUMMARY_HTML_NAME} has no {CASE_SUMMARY_DATA_NAME} to show it leads with the "
               f"{len(urgent)} emergent/urgent finding(s)"], urgent, "unverifiable", CASE_SUMMARY_HTML_NAME)

    html_path = patient_dir / CASE_SUMMARY_HTML_NAME
    if not html_path.is_file():
        return  # 段D HTML not generated yet — not an error here
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
# sha256 of every agents-md.template.md this repository has shipped before the current one
# (`git log -- references/templates/agents-md.template.md`). An AGENTS.md stamped with one of
# them was filled correctly by an earlier build: re-filling it is hygiene (WARN), not a broken
# archive. An unknown sha is still an ERROR (a hand-edited template or a forged stamp).
KNOWN_PRIOR_TEMPLATE_SHAS = frozenset({
    "8069660844a53e5e1a7850b1ec27459826ac647413c90a38d169434fdda6f881",  # main @ d84b7eb
    "cf16f5977f950b121dedba6a29b306b90923231236f1507ab0f14188d25fb8ca",  # a22f07c
    "b714e730baee377d74d92acaca31fdde24069c42c460b6829707f6e1139089f6",  # d1369a2
    "7dded9a7072c02a113db6e0d6dd178c02ee90e146f9ac30d15dfc960e0ac9f24",  # ce38127
    "941d1182d7b4224cb02378f82787157f108772ce02d341e383d7806168460d5e",  # b5219b1
    "9e4ac6835c8be45327812694f72cf8883b52a96092cc666ef42e71ef6420b812",  # fb8df3e
    "f27ffae52ca7088b4073328c4f16abdbd198021e2977640c30778bf88fd8450b",  # c7e8d71
})
_AGENTS_STAMP_RE = re.compile(r"<!--\s*generated-by: fill_agents_md\.py \| template_sha256: ([0-9a-f]{64})\s*-->")


def gate_agents_md(patient_dir: Path, errors: list, warnings: list | None = None,
                   generation: str | None = None) -> None:
    """AGENTS.md must be the fully-filled template, not a stub.

    A bare session whose cwd is this directory loads AGENTS.md and NOTHING else —
    the red lines inlined in it are the only guardrails present. A stub therefore
    is not a cosmetic defect: it silently removes the floor. `fill_agents_md.py
    --check` re-verifies placeholders, routing anchors, the inlined red lines and
    the template sha256 without writing.

    When the ONLY failure is the template stamp, and the archive is legacy or the stamp is a
    template this repository shipped before (KNOWN_PRIOR_TEMPLATE_SHAS), it is a WARN: the file
    was filled correctly by an earlier build, and every archive organized before a template edit
    must stay readable (SMTB runs this gate with --readonly on them).
    """
    agents_md = patient_dir / "AGENTS.md"
    if not agents_md.exists():
        errors.append("AGENTS.md missing — run Step 13 (scripts/fill_agents_md.py)")
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
    if proc.returncode == 0:
        return
    out = (proc.stderr or proc.stdout or "").strip().splitlines()
    problems = [l.strip()[2:] for l in out if l.strip().startswith("- ")]
    # A file filled from an earlier vetted template differs from today's in exactly two ways: the
    # stamp, and the routing anchors added since (e.g. acute_findings.json). A stub, a residual
    # placeholder, a wrong first line or a missing red line is a real defect in any era → ERROR.
    stale_only = problems and any(p.startswith("template_sha256 mismatch") for p in problems) and all(
        p.startswith(("template_sha256 mismatch", "routing table incomplete")) for p in problems)
    if stale_only:
        try:
            m = _AGENTS_STAMP_RE.search(agents_md.read_text(encoding="utf-8"))
        except OSError:
            m = None
        stamp = m.group(1) if m else None
        if stamp in KNOWN_PRIOR_TEMPLATE_SHAS or not _generation(patient_dir, generation):
            if warnings is not None:
                warnings.append(f"agents_md: AGENTS.md was filled from an earlier template (sha {str(stamp)[:12]}…) — "
                                "re-run scripts/fill_agents_md.py to refresh it")
            return
    errors.append(f"agents_md: {out[-1] if out else 'verification failed'}")


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


AGENTS_TEMPLATE = REPO_ROOT / "references" / "templates" / "agents-md.template.md"


def _template_quoted_hit(patient_dir: Path, finding: dict, cache: dict) -> bool:
    """True for a hit on a top-level AGENTS.md line that appears VERBATIM in the vetted
    AGENTS.md template (the template quotes injection phrases as examples to ignore).

    Line-level, not file-level: `fill_agents_md.py --check` proves the template stamp
    and anchors, not byte equality, so text appended to AGENTS.md must stay flagged."""
    if finding.get("file") != "AGENTS.md":
        return False
    if "template" not in cache:
        try:
            cache["template"] = {l.strip() for l in AGENTS_TEMPLATE.read_text(encoding="utf-8").splitlines() if l.strip()}
            cache["agents"] = (patient_dir / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        except OSError:
            cache["template"], cache["agents"] = set(), []
    line = finding.get("line")
    lines = cache["agents"]
    return isinstance(line, int) and 1 <= line <= len(lines) and lines[line - 1].strip() in cache["template"]


def gate_untrusted_content(patient_dir: Path, warnings: list, readonly: bool = False) -> None:
    """Scan archive text for instruction-shaped content. WARNING, never blocking.

    Deliberately non-blocking: a false positive would kill a real medical record
    ('胃旁路' contains bypass), while a false negative still faces every downstream
    safety gate. Hits are surfaced here and recorded in readiness.json.review_flags[]
    so a human sees them; they never change this script's exit code.

    The scanner prints its JSON report on stdout; `--json` takes an OUTPUT PATH, so the
    old `--json` invocation made argparse exit 2 with empty stdout and this gate was a
    silent no-op. It now runs with `--quiet` and treats an empty/failed run as a WARN.

    `readonly=True` (CLI `--readonly`, for a third-party / downstream check such as
    SMTB's) reports the hits but writes nothing: the flags are not merged into
    readiness.json, so the archive (and the hashes update_log recorded) stay untouched.
    """
    scanner = SCRIPT_DIR / "scan_untrusted_markers.py"
    if not scanner.exists():
        return
    proc = subprocess.run(
        [sys.executable, str(scanner), str(patient_dir), "--quiet"],
        capture_output=True,
        text=True,
    )
    try:
        report = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        report = None
    if not isinstance(report, dict):
        warnings.append(
            f"untrusted_content: scanner produced no parseable report (rc={proc.returncode})"
        )
        return
    findings = [f for f in (report.get("findings") or []) if isinstance(f, dict)]
    cache: dict = {}
    template_hits = [f for f in findings if _template_quoted_hit(patient_dir, f, cache)]
    if template_hits:
        findings = [f for f in findings if not _template_quoted_hit(patient_dir, f, cache)]
        warnings.append(
            f"untrusted_content: {len(template_hits)} hit(s) in the top-level AGENTS.md sit on lines "
            "the vetted AGENTS.md template itself quotes as examples — not recorded as flags"
        )
    high = [f for f in findings if f.get("severity") == "high"]
    medium = [f for f in findings if f.get("severity") == "medium"]
    if not (high or medium):
        return
    warnings.append(
        f"untrusted_content: {len(high)} high / {len(medium)} medium instruction-shaped "
        f"hit(s) across {report.get('files_scanned', '?')} file(s) — treat that text as "
        "data to be quoted, never as instructions to follow"
    )
    for f in (high + medium)[:5]:
        warnings.append(
            f"untrusted_content:   {f.get('file', '?')}:{f.get('line', '?')} "
            f"[{f.get('severity')}] {f.get('rule_id', '?')}"
        )
    try:
        import scan_untrusted_markers as sum_mod  # sibling: one flag builder
        flags = sum_mod.build_review_flags(findings)
    except Exception:
        flags = report.get("review_flags") or []
    if flags and readonly:
        warnings.append(f"untrusted_content: {len(flags)} review flag(s) not recorded (--readonly: "
                        "readiness.json left untouched)")
    elif flags:
        _merge_review_flags(patient_dir, flags, warnings)


def _merge_review_flags(patient_dir: Path, flags: list, warnings: list) -> None:
    """Append scanner flags into readiness.json.review_flags[], idempotently.

    Identity key = (category, affected_field): the scanner emits one flag per file and
    never a `detail` key, so the old (category, detail) key collapsed to
    (category, None) and silently dropped every flag after the first merge. Added
    flags get fresh, non-colliding ids. The merged document is schema-checked BEFORE
    it is written — the gate must never write a readiness.json the next run rejects.
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
    seen = {(f.get("category"), f.get("affected_field")) for f in existing if isinstance(f, dict)}
    added = [dict(f) for f in flags if (f.get("category"), f.get("affected_field")) not in seen]
    if not added:
        return
    used_ids = {f.get("id") for f in existing if isinstance(f, dict)}
    n = 0
    for f in added:
        while True:
            n += 1
            fid = f"UNTRUSTED-{n:03d}"
            if fid not in used_ids:
                break
        f["id"] = fid
        used_ids.add(fid)
    candidate = dict(data)
    candidate["review_flags"] = existing + added
    if HAS_JSONSCHEMA:
        problems: list[str] = []
        validate_doc_schema("readiness.json", candidate, "readiness.schema.json", problems)
        if problems:
            warnings.append(
                "untrusted_content: merged review_flags would not validate — readiness.json "
                f"left unchanged ({problems[0]})"
            )
            return
    try:
        before_sha = _sha256_path(readiness)
        readiness.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        warnings.append("untrusted_content: could not write readiness.json review_flags")
        return
    warnings.append(
        f"untrusted_content: recorded {len(added)} flag(s) in readiness.json.review_flags[]"
    )
    _resync_logged_output(patient_dir, "readiness.json", before_sha, warnings)


def _resync_logged_output(patient_dir: Path, fname: str, before_sha: str, warnings: list) -> None:
    """After this gate rewrote `fname`, move the outputs[] hash of the LATEST update_log entry
    that records `fname` along (the same entry gate_update_log_freshness compares against) —
    but only when that hash still named the pre-write bytes (the flow's own output). A file
    already edited outside the flow keeps its mismatch visible."""
    path = patient_dir / UPDATE_LOG_NAME
    doc = _load_json_quiet(path)
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        return
    rows: list[dict] = []
    for e in reversed(entries):
        outputs = e.get("outputs") if isinstance(e, dict) else None
        rows = [o for o in outputs if isinstance(o, dict) and o.get("file") == fname] if isinstance(outputs, list) else []
        if rows:
            break
    if not rows or any(o.get("sha256") != before_sha for o in rows):
        return
    try:
        after_sha = _sha256_path(patient_dir / fname)
        for o in rows:
            o["sha256"] = after_sha
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        warnings.append(f"untrusted_content: could not re-sync the update_log outputs[] hash of {fname}")


# --------------------------------------------------------------------------- #
# [6] v2.1 gates (O-01..O-09). Each takes (patient_dir, errors, warnings,
# generation=None): FAIL on a current-contract archive, WARN on a legacy one.
# --------------------------------------------------------------------------- #
_LINE_ANCHOR_RE = re.compile(r"#L(\d+)(?:-L(\d+))?$")
_UNCERTAIN_TOKEN_RE = re.compile(r"\[OCR_UNCERTAIN(?::(U-\d+))?\]")
_UNCERTAIN_BLOCK_HEADING = "## 不确定字段"
DIGEST_SUB_BUCKETS = ("既往档案摘录", "prior-archive-digest")

# `## 不确定字段` entry vocabulary (organizer-prompt-phase1-ocr.md §5/§6).
# tests/eval/lint/13-organize-prompt-contracts.sh fails when the phase1 §5 example lists a
# value these tuples do not accept.
UNCERTAIN_LAYOUTS = ("none", "strikethrough", "overprint", "crop", "stamp", "shadow_stain_fold")
UNCERTAIN_FIELD_CLASSES = ("drug_name", "ihc_marker", "ln_station", "date", "number", "unit", "stage",
                           "variant", "diagnosis_text", "regimen_connector", "cycle_number", "other")
# the only field classes that get lexicon candidates, and the lexicon each one draws from;
# every other class (incl. other) writes `candidates: []`
FIELD_CLASS_LEXICON = {"drug_name": "oncology_drugs", "ihc_marker": "ihc_markers", "ln_station": "ln_stations"}
CANDIDATE_CONFIDENCE = ("high", "medium", "low")
# a reading that resolved only some of its characters: phase1 §5 writes one `?` per unresolved
# character (`4L?`, so the edit distance counts it as one character); `[?]` / ？ / □ / U+FFFD
# are recognised as the same mark in a sidecar written otherwise.
PARTIAL_READING_MARKERS = ("[?]", "?", "？", "□", "\ufffd")
# review-flag category of an anchor gap (anchor-contract.md §5): kind other, severity red
ANCHOR_GAP_CATEGORY = "anchor_coverage_gap"
# acute-findings.md §2.4: a sidecar holding only a translation of a foreign-language report — one
# other / yellow flag per sidecar (not per finding)
FOREIGN_PARAPHRASE_CATEGORY = "foreign_language_paraphrase"
# phase2 §6.1: on a LEGACY archive, a value the old structured files carry that no sidecar line supports
# (e.g. a sex recorded only in the old JSON) is kept and flagged other / yellow — never dropped or
# invented. A current-contract archive has no such values: there an unanchored value is an anchor gap.
LEGACY_UNSUPPORTED_CATEGORY = "legacy_value_unsupported"
# phase2 §4.0: on a LEGACY archive (legacy_phase2_only) a digest-looking sidecar that carries none of the three
# digest marks (既往档案摘录 sub-bucket / inventory source_kind prior_archive_digest / SOURCE header) is
# flagged other / yellow and no new fact is taken from it until legacy_upgrade rewrites it; a value the old
# structured files already held is kept with a legacy_value_unsupported flag (that rule wins — never drop).
PRIOR_DIGEST_UNRECOGNISED_CATEGORY = "prior_archive_digest_unrecognised"
LEGACY_ONLY_CATEGORIES = (LEGACY_UNSUPPORTED_CATEGORY, PRIOR_DIGEST_UNRECOGNISED_CATEGORY)
_CANDIDATE_AFFIXES = ("no.", "组", "站")
# every key of a `## 不确定字段` entry (references/schemas/README.md; phase1 §5) — all required on a current sidecar
UNCERTAIN_ENTRY_KEYS = ("id", "line", "field_class", "readings", "candidates", "cross_doc_supported",
                        "layout", "layout_intent")
CROSS_DOC_STATUSES = ("supported", "contradicted", "none")

# Pinned sidecar header VALUES (organizer-prompt-phase1-ocr.md §2/§3; the key list and its
# order are pii_rescan.PINNED_HEADER_KEYS). tests/eval/lint/13-organize-prompt-contracts.sh
# fails when the prompt's SOURCE list and this tuple drift apart.
SIDECAR_SOURCE_TYPES = (
    "discharge_summary", "admission_note", "progress_note", "outpatient_note", "order_sheet",
    "prescription", "pathology_report", "ihc_report", "ngs_report", "imaging_report", "lab_report",
    "consult_note", "procedure_note", "certificate", "patient_supplement", "image_only",
    "prior_archive_digest", "unsupported",
)
SIDECAR_CONFIDENCE = ("low", "medium", "high")
# header READ_MODE / ADAPTER / MODALITY values (phase1 §3 table = source_inventory.schema.json enums);
# checked on the header itself, so a sidecar with no inventory row cannot carry free text there.
SIDECAR_READ_MODES = ("native_text", "deterministic_ocr", "table_parser", "barcode_parser", "hybrid_verified",
                      "model_vision_assist", "stub_unreadable", "prior_archive_digest")
SIDECAR_ADAPTERS = ("none", "temp_raster", "pdf_pages", "docx_payload", "spreadsheet_payload", "text_payload",
                    "archive_unpacked", "unsupported_stub")
SIDECAR_MODALITIES = ("text", "image", "structured", "omics_raw", "timeseries", "binary_other")
# update_log workers[].phase values of the workers that write sidecars (phase1 §0; SKILL.md Steps 3-4)
SIDECAR_WRITER_PHASES = ("phase1", "phase1_retry", "phase1_continuation", "phase1_digest", "stub")
# `<category>[:<engine>]`; only deterministic_ocr names an engine (phase1 §2 channel table).
READ_CHANNEL_RE = re.compile(
    r"^(?:text_layer|table_parser|deterministic_ocr:[A-Za-z0-9_.-]+|barcode|human|llm_vision"
    r"|prior_archive_sidecar|none)$"
)
_NO_PAGE_LABEL = ("", "null", "none", "无", "n/a")


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def _quote_segments(text: str) -> list[str]:
    """The literal pieces of a quote: NFKC (…… → ......), split at every elision of ≥ 3 dots."""
    return re.split(r"\.{3,}", unicodedata.normalize("NFKC", text))


def _word_chars(seg: str) -> int:
    """Characters that carry wording: not whitespace, punctuation (P*) or separators (Z*)."""
    return sum(1 for ch in seg if not ch.isspace() and unicodedata.category(ch)[0] not in "PZ")


def quote_problem(text) -> str | None:
    """A quote must carry source words: at least one elision-separated segment with ≥ 2 word
    characters. An ellipsis-only quote (`……`, `...`) or bare punctuation binds nothing, so it
    would pass every 'segment appears in the source' check. None = OK."""
    if not isinstance(text, str):
        return None
    if not any(_word_chars(seg) >= 2 for seg in _quote_segments(text)):
        return f"quote {text.strip()[:16]!r} holds no source words (only an ellipsis / punctuation)"
    return None


def anchor_line_binding(patient_dir: Path, ref: str, verbatim: str | None) -> str | None:
    """Check a `path.md#Ln[-Lm]` anchor: the line range exists and every segment of
    `verbatim` (elisions written as …… / ...) appears on those lines; an ellipsis-only quote
    is rejected (quote_problem). None = OK."""
    if not isinstance(ref, str):
        return "source_ref is not a string"
    m = _LINE_ANCHOR_RE.search(ref)
    if not m:
        return f"{ref!r} carries no #L<n> line anchor"
    target = patient_dir / ref.split("#", 1)[0]
    if not target.is_file():
        return None  # validate_anchors reports the dangling file
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return f"{ref!r} unreadable"
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    if a < 1 or b < a or b > len(lines):
        return f"{ref!r} points outside the file ({len(lines)} lines)"
    if verbatim is None:
        return None
    bad = quote_problem(verbatim)
    if bad:
        return f"{bad} — cannot be bound to {ref}"
    block = _norm_text("".join(lines[a - 1:b]))
    for seg in _quote_segments(verbatim):
        seg_n = _norm_text(seg)
        if seg_n and seg_n not in block:
            return f"verbatim text not found on {ref} (segment {seg.strip()[:24]!r})"
    return None


def _segments_in(body_norm: str, text: str) -> bool:
    return all(not _norm_text(seg) or _norm_text(seg) in body_norm for seg in _quote_segments(text))


def text_in_cited_file(patient_dir: Path, ref, text: str | None) -> str | None:
    """Every segment of `text` (elisions …… / ...) appears somewhere in the file `ref`
    points at (NFKC, whitespace-insensitive, whole file); an ellipsis-only quote is rejected.
    None = OK or nothing to check."""
    if not isinstance(text, str) or not text.strip() or not isinstance(ref, str):
        return None
    bad = quote_problem(text)
    if bad:
        return bad
    target = patient_dir / ref.split("#", 1)[0]
    if not target.is_file():
        return None  # validate_anchors reports the dangling file
    try:
        body = _norm_text(target.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return f"{ref!r} unreadable"
    if not _segments_in(body, text):
        return f"{text.strip()[:32]!r} does not appear in {ref.split('#', 1)[0]}"
    return None


def _conversation_note_files(patient_dir: Path) -> list[Path]:
    return sorted(p for p in patient_dir.rglob("conversation_notes/*.md") if p.is_file())


def text_in_any_cited_source(patient_dir: Path, refs, text) -> str | None:
    """A verbatim basis field (status_basis_text, a setting_basis segment): every segment appears
    in ONE of the files `refs` cite — a `conversation:<ISO>` anchor resolves to the archive's
    conversation_notes/*.md. None = OK or nothing to check."""
    if not isinstance(text, str) or not text.strip():
        return None
    bad = quote_problem(text)
    if bad:
        return bad
    files: list[Path] = []
    for ref in refs if isinstance(refs, list) else []:
        if not isinstance(ref, str):
            continue
        if ref.startswith("conversation:"):
            files.extend(_conversation_note_files(patient_dir))
        else:
            files.append(patient_dir / ref.split("#", 1)[0])
    seen: set[Path] = set()
    for f in files:
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        try:
            if _segments_in(_norm_text(f.read_text(encoding="utf-8", errors="replace")), text):
                return None
        except OSError:
            continue
    return f"{text.strip()[:32]!r} does not appear in any source the record cites"


_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")


def _date_forms(iso: str) -> list[str]:
    """The printed spellings of a YYYY-MM-DD date (NFKC, whitespace removed before matching)."""
    y, m, d = iso.split("-")
    mi, di = str(int(m)), str(int(d))
    forms = {f"{y}-{m}-{d}", f"{y}/{m}/{d}", f"{y}.{m}.{d}", f"{y}年{m}月{d}日", f"{y}{m}{d}",
             f"{y}-{mi}-{di}", f"{y}/{mi}/{di}", f"{y}.{mi}.{di}", f"{y}年{mi}月{di}日"}
    return sorted(forms)


def date_binding_problem(patient_dir: Path, ref, value) -> str | None:
    """An acute finding's exam_date / report_date comes from the report (acute-findings.md §5):
    it is the cited sidecar's filename date, or printed in that sidecar, or — a report split into
    page sidecars (§2.2) — printed in another sidecar of the same report (same folder, same
    filename date and institution). None = OK / nothing to check."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or not isinstance(ref, str) \
            or ref.startswith("conversation:"):
        return None
    target = patient_dir / ref.split("#", 1)[0]
    if not target.is_file():
        return None  # validate_anchors reports it
    m = _DATE_PREFIX_RE.match(target.name)
    if m and m.group(1) == value:
        return None
    if report_prints_date(patient_dir, ref, value):
        return None
    return (f"is neither the cited report's date ({target.name}) nor printed in it (or in another page of "
            "the same report) — dates come from the source, never from another document")


def _report_pages(target: Path) -> list[Path]:
    """The cited sidecar plus the other page sidecars of the SAME report: same folder, same filename
    date and same institution segment (phase2 §4.2 names every page by the report's 出具日期)."""
    m = _DATE_PREFIX_RE.match(target.name)
    try:
        import page_completeness as pc
        inst = pc.institution_slug(target.name)
    except Exception:
        return [target]
    pool = [target]
    if m and inst is not None:
        pool += [p for p in sorted(target.parent.glob(f"{m.group(1)}_*.md"))
                 if p != target and pc.institution_slug(p.name) == inst]
    return pool


def report_prints_date(patient_dir: Path, ref, value) -> bool:
    """True when a YYYY-MM-DD date is printed (any common spelling) in the cited report — the cited
    sidecar or another page of the same report (acute-findings.md §2.2 / §6 prior_date_stated)."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or not isinstance(ref, str):
        return False
    target = patient_dir / ref.split("#", 1)[0]
    if not target.is_file():
        return False
    forms = [_norm_text(x) for x in _date_forms(value)]
    for p in _report_pages(target):
        try:
            body = _norm_text(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if any(fm in body for fm in forms):
            return True
    return False


def _bucket_sidecars(patient_dir: Path) -> list[Path]:
    out: list[Path] = []
    for top in sorted(patient_dir.iterdir()):
        if not top.is_dir() or not _DOMAIN_DIR_RE.match(top.name) or top.name.startswith("99_"):
            continue
        for p in sorted(top.rglob("*.md")):
            if "conversation_notes" in p.parts:
                continue
            out.append(p)
    return out


def _inventory_rows(patient_dir: Path) -> dict[str, dict]:
    inv = _load_json_quiet(patient_dir / SOURCE_INVENTORY_NAME)
    rows: dict[str, dict] = {}
    for row in _file_entries(inv) if isinstance(inv, dict) else []:
        if isinstance(row, dict) and isinstance(row.get("sidecar_path"), str):
            rows[row["sidecar_path"]] = row
    return rows


def _update_log_entries(patient_dir: Path) -> list[dict] | None:
    doc = _load_json_quiet(patient_dir / UPDATE_LOG_NAME)
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        return None
    return [e for e in doc["entries"] if isinstance(e, dict)]


def _update_log_workers(patient_dir: Path) -> set[str] | None:
    entries = _update_log_entries(patient_dir)
    if entries is None:
        return None
    ids: set[str] = set()
    for e in entries:
        for w in e.get("workers") or []:
            if isinstance(w, dict) and isinstance(w.get("worker_id"), str):
                ids.add(w["worker_id"])
    return ids


def _update_log_worker_records(patient_dir: Path) -> dict[str, dict]:
    """{worker_id: {"phases": {…}, "files": {…}}} across every entry (a worker id may recur)."""
    out: dict[str, dict] = {}
    for e in _update_log_entries(patient_dir) or []:
        for w in e.get("workers") or []:
            if not isinstance(w, dict) or not isinstance(w.get("worker_id"), str):
                continue
            rec = out.setdefault(w["worker_id"], {"phases": set(), "files": set()})
            if isinstance(w.get("phase"), str):
                rec["phases"].add(w["phase"])
            rec["files"].update(x for x in (w.get("files") or []) if isinstance(x, str))
    return out


def _latest_input_entry(entries: list[dict] | None) -> dict | None:
    """The newest entry that reconciled the inputs (a non-empty inputs[]). An entry with
    `inputs: []` (e.g. a conversation-only turn) did not look at the originals."""
    for e in reversed(entries or []):
        if isinstance(e.get("inputs"), list) and e["inputs"]:
            return e
    return None


def _channel_category(ch: str | None) -> str:
    return (ch or "").strip().split(":", 1)[0].strip().lower()


def sidecar_contract_scope(patient_dir: Path) -> tuple[list[Path], list[Path]]:
    """Split bucket sidecars into (written under the current contract, carried-over legacy).

    An update-type run on an older archive does not re-transcribe the sidecars it did not
    touch, and those predate the pinned header (organize DoD 5: not retroactively
    required). A sidecar counts as CURRENT — full header / EXTRACTOR / uncertainty
    bookkeeping enforced — when any of:
      * its header names an EXTRACTOR (it claims the current contract);
      * any current-shape update_log entry (one with workers[]) has run_mode `full` or
        `legacy_upgrade` (FULL_RUN_MODES: both re-transcribe every source, and a legacy
        upgrade moves the old buckets aside first; an older ledger records the upgrade as
        `full`);
      * it has no source_inventory row (an unaccounted sidecar is never "legacy");
      * its source_id / file_id / sidecar path is in some entry's workers[].files (a
        worker of this contract was given or wrote it).
    Everything else is carried-over legacy: reported as one aggregated WARN. inputs[] and
    added[] are NOT used: the contract lists every original there, old or new. Without
    any current-shape entry (no workers[] anywhere) nothing can have been carried over
    into a current-contract run, so every sidecar is held to the header."""
    import pii_rescan
    entries = _update_log_entries(patient_dir) or []
    v1_entries = [e for e in entries if isinstance(e.get("workers"), list)]
    full_run = not v1_entries or any(e.get("run_mode") in FULL_RUN_MODES for e in v1_entries)
    touched: set[str] = set()
    for e in entries:
        for w in e.get("workers") or []:
            if isinstance(w, dict):
                touched.update(str(x) for x in (w.get("files") or []) if isinstance(x, str))
    rows = _inventory_rows(patient_dir)
    current: list[Path] = []
    legacy: list[Path] = []
    for sc in _bucket_sidecars(patient_dir):
        rel = sc.relative_to(patient_dir).as_posix()
        hdr = pii_rescan.parse_header(sc.read_text(encoding="utf-8", errors="replace"))
        row = rows.get(rel)
        handles = {rel}
        if row is not None:
            handles.update(str(row.get(k)) for k in ("source_id", "file_id") if isinstance(row.get(k), str))
        if hdr.get("EXTRACTOR", "").strip() or full_run or row is None or handles & touched:
            current.append(sc)
        else:
            legacy.append(sc)
    return current, legacy


def _is_digest_sidecar(patient_dir: Path, rel: str) -> bool:
    """A prior-archive digest: filed in the digest sub-bucket, headed `SOURCE: prior_archive_digest`,
    or inventoried with source_kind prior_archive_digest."""
    if any(f"/{b}/" in f"/{rel}" for b in DIGEST_SUB_BUCKETS):
        return True
    row = _inventory_rows(patient_dir).get(rel)
    if isinstance(row, dict) and row.get("source_kind") == "prior_archive_digest":
        return True
    try:
        import pii_rescan
        text = (patient_dir / rel).read_text(encoding="utf-8", errors="replace")
        return pii_rescan.parse_header(text).get("SOURCE", "").strip() == "prior_archive_digest"
    except Exception:
        return False


def _flag_cited_sidecars(patient_dir: Path, category: str) -> set[str]:
    """Sidecar paths the readiness.json review flags of `category` cite (current_source_values)."""
    r = _load_json_quiet(patient_dir / "readiness.json")
    out: set[str] = set()
    for f in (r.get("review_flags") or []) if isinstance(r, dict) else []:
        if not isinstance(f, dict) or f.get("category") != category:
            continue
        for cv in f.get("current_source_values") or []:
            if isinstance(cv, dict) and isinstance(cv.get("source_ref"), str):
                out.add(cv["source_ref"].split("#", 1)[0])
    return out


def _paraphrase_flagged_sidecars(patient_dir: Path) -> set[str]:
    return _flag_cited_sidecars(patient_dir, FOREIGN_PARAPHRASE_CATEGORY)


def gate_acute_findings(patient_dir: Path, errors: list, warnings: list | None = None,
                        generation: str | None = None) -> None:
    """O-02: acute_findings.json present, each finding ↔ one timeline event, anchored
    verbatim text, acuity per the fixed class table.

    acute_findings.json is a safety surface written on EVERY pass (phase2 §4.0/§5.5), a Phase-2-only
    pass on a legacy archive included, and it has no legacy version. So only two checks follow the
    archive's generation: a missing file (current → ERROR, legacy → WARN: the archive may predate the
    file) and the timeline linkage (current → every finding has exactly one `acute_finding` event;
    legacy → timeline_event_id may be null, because the legacy timeline is not rewritten to the current
    contract before legacy_upgrade — a non-null id must still resolve). Everything the file itself
    asserts — the fixed acuity table, quotes on the cited lines, dates — is an ERROR on either kind."""
    current = _generation(patient_dir, generation)
    presence = _router(errors, warnings, current)
    add = errors.append  # the file's own bindings: strict on every archive
    path = patient_dir / ACUTE_FINDINGS_NAME
    if not path.is_file():
        presence(f"{ACUTE_FINDINGS_NAME}: missing — it is always written (findings: [] when the "
                 "sources report none), so a missing file cannot be told apart from 'not checked'")
        return
    doc = _load_json_quiet(path)
    findings = doc.get("findings") if isinstance(doc, dict) else None
    if not isinstance(findings, list):
        return  # the structured gate reports the shape
    tl = _load_json_quiet(patient_dir / "timeline.json")
    events = [e for e in (tl.get("events") or []) if isinstance(e, dict)] if isinstance(tl, dict) else []
    events_by_id = {e.get("event_id"): e for e in events}
    # acute-findings.md §2.4 / §11: a finding quoted from a sidecar that holds only a Chinese rendering of a
    # foreign-language report is shown as a translation, never as the report's own words — so its
    # verbatim_is_translation is bound both ways to that sidecar's foreign_language_paraphrase flag.
    paraphrased = _paraphrase_flagged_sidecars(patient_dir)
    by_id: dict[str, dict] = {}
    for f in findings:
        if not isinstance(f, dict):
            continue
        fid = f.get("finding_id") if isinstance(f.get("finding_id"), str) else repr(f.get("finding_id"))
        if fid in by_id:
            add(f"{ACUTE_FINDINGS_NAME}: duplicate finding_id {fid}")
        by_id[fid] = f
        tid = f.get("timeline_event_id")
        ev = events_by_id.get(tid)
        if tid is None and not current:
            pass  # legacy archive: the acute_finding event comes with legacy_upgrade (phase2 §4.0)
        elif ev is None:
            add(f"{ACUTE_FINDINGS_NAME}: {fid} → timeline_event_id {tid!r} has no timeline.json event "
                "(every acute finding is also a timeline event; only on a legacy archive may it be null)")
        elif ev.get("category") != "acute_finding" or ev.get("acute_finding_id") != fid:
            add(f"{ACUTE_FINDINGS_NAME}: {fid} → timeline event {tid} must have category "
                f"acute_finding and acute_finding_id {fid} (has {ev.get('category')!r} / "
                f"{ev.get('acute_finding_id')!r})")
        cls, acuity, basis = f.get("finding_class"), f.get("acuity"), f.get("acuity_basis")
        default = ACUTE_CLASS_DEFAULT.get(cls) if isinstance(cls, str) else None
        if default and isinstance(acuity, str) and acuity in ACUITY_RANK:
            if basis == "class_default" and acuity != default:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} acuity {acuity} but acuity_basis class_default "
                    f"means {default} for {cls} (the fixed table; the model does not triage)")
            elif basis == "source_wording_escalation" and cls not in ESCALATION_ROUTES:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} {cls} has no escalation in the fixed table (only "
                    f"{' / '.join(ESCALATION_ROUTES)} do, acute-findings.md §3/§4) — keep the class default "
                    f"{default}; a 新发 / 较前加重 comparison goes in change_vs_prior.direction")
            elif basis == "source_wording_escalation" and acuity != ESCALATION_ROUTES[cls][0]:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} acuity_basis source_wording_escalation must raise "
                    f"the class default ({default}) to {ESCALATION_ROUTES[cls][0]} for {cls}, got {acuity}")
            elif basis == "source_critical_flag" and acuity != "emergent":
                add(f"{ACUTE_FINDINGS_NAME}: {fid} a source critical flag means emergent, got {acuity}")
            elif basis == "source_wording_chronic" and acuity != "incidental":
                add(f"{ACUTE_FINDINGS_NAME}: {fid} source chronic wording means incidental, got {acuity}")
        src_ref = f.get("source_ref")
        msg = anchor_line_binding(patient_dir, src_ref, f.get("verbatim_text"))
        if msg:
            add(f"{ACUTE_FINDINGS_NAME}: {fid} {msg}")
        src_rel = src_ref.split("#", 1)[0] if isinstance(src_ref, str) else None
        translated = f.get("verbatim_is_translation") is True
        if src_rel in paraphrased and not translated:
            add(f"{ACUTE_FINDINGS_NAME}: {fid} cites {src_rel}, which carries a {FOREIGN_PARAPHRASE_CATEGORY} flag (only a "
                "Chinese rendering of a foreign-language report), but verbatim_is_translation is not true — a rendering "
                "shown as the report's own words (acute-findings.md §2.4 / §11)")
        elif translated and src_rel not in paraphrased:
            add(f"{ACUTE_FINDINGS_NAME}: {fid} verbatim_is_translation true but {src_rel} has no {FOREIGN_PARAPHRASE_CATEGORY} "
                "review flag — a translated quote and its sidecar's flag go together (acute-findings.md §2.4)")
        # A non-default acuity and a stated change both rest on the SOURCE's own words
        # (acute-findings.md §4), quoted from the cited LINES — not anywhere in the file (an unrelated
        # 「未见」 elsewhere in the report is not the finding's wording) — and containing the
        # pinned wording of that adjustment (ACUITY_BASIS_TOKENS), or a model could write
        # 「陈旧」/「较前无显著变化」 to demote an embolism to incidental (and out of every urgent path).
        if basis in ACUITY_BASIS_TOKENS:
            text = f.get("acuity_basis_text")
            basis_ref = f.get("acuity_basis_ref") or src_ref
            if f.get("acuity_basis_ref") and isinstance(src_ref, str) and isinstance(f["acuity_basis_ref"], str) \
                    and f["acuity_basis_ref"].split("#", 1)[0] != src_ref.split("#", 1)[0]:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} acuity_basis_ref {f['acuity_basis_ref']!r} is not in the report "
                    f"the finding cites ({src_ref.split('#', 1)[0]}) — the adjustment is that report's own wording")
            msg = anchor_line_binding(patient_dir, basis_ref, text) if isinstance(text, str) else None
            if msg:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} acuity_basis {basis}: acuity_basis_text {msg} — an "
                    "acuity adjustment must quote the report's own wording on the cited line(s) "
                    "(another line of the report: name it in acuity_basis_ref)")
            elif isinstance(text, str):
                route_tokens = ESCALATION_ROUTES[cls][1] if basis == "source_wording_escalation" \
                    and cls in ESCALATION_ROUTES else ACUITY_BASIS_TOKENS[basis]
                if basis == "source_wording_escalation" and cls == "other_source_flagged" \
                        and has_basis_token(text, route_tokens) \
                        and not has_basis_token(text, tuple(t for t in route_tokens if t not in OBSTRUCTIVE_ONLY_ESCALATION)) \
                        and not has_basis_token(f.get("verbatim_text"), OBSTRUCTIVE_WORDS):
                    add(f"{ACUTE_FINDINGS_NAME}: {fid} other_source_flagged is raised by 新发 / 较前加重 only for a "
                        "secondary obstructive change (阻塞性炎症 / 阻塞性肺不张, acute-findings.md §3) — its "
                        "verbatim_text names none; otherwise only 尽快 / 立即 / 急诊 raise it")
                if not has_basis_token(text, route_tokens):
                    add(f"{ACUTE_FINDINGS_NAME}: {fid} acuity_basis {basis}: acuity_basis_text {text[:24]!r} holds none of "
                        f"the pinned words ({' / '.join(route_tokens)}; acute-findings.md §4.1) — "
                        "「无显著变化」 alone is not a chronic wording")
                if basis == "source_wording_chronic" and cls == "thrombus_embolism" \
                        and not has_basis_token(text, THROMBUS_STABLE_TOKENS):
                    add(f"{ACUTE_FINDINGS_NAME}: {fid} a thrombus is demoted only when the report says it is old "
                        "AND unchanged — acuity_basis_text holds no unchanged-comparison wording "
                        f"({' / '.join(THROMBUS_STABLE_TOKENS)})")
            if basis == "source_wording_chronic" and isinstance(cls, str) and cls in ACUTE_CLASS_DEFAULT \
                    and cls not in CHRONIC_ADJUSTABLE_CLASSES:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} {cls} has no chronic adjustment in the fixed table (only "
                    f"{' / '.join(CHRONIC_ADJUSTABLE_CLASSES)} do, acute-findings.md §3) — keep the class default")
        cvp = f.get("change_vs_prior") if isinstance(f.get("change_vs_prior"), dict) else {}
        if cvp.get("direction") not in (None, "not_stated"):
            # acute-findings.md §2.2: verbatim_text, source_ref and change_vs_prior come from one place
            msg = anchor_line_binding(patient_dir, src_ref, cvp.get("verbatim")) \
                if isinstance(cvp.get("verbatim"), str) else f"{cvp.get('verbatim')!r} is not a quote"
            if msg:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} change_vs_prior {cvp.get('direction')}: verbatim {msg} — "
                    "the comparison is the report's own wording on the cited line(s), never a summary")
        for key in ("exam_date", "report_date"):
            msg = date_binding_problem(patient_dir, src_ref, f.get(key))
            if msg:
                add(f"{ACUTE_FINDINGS_NAME}: {fid} {key} {f.get(key)!r} {msg}")
        # acute-findings.md §6: the comparison date is the report's own (any line of it, or another
        # page of the same report) — never a "last scan" looked up elsewhere in the archive
        pds = cvp.get("prior_date_stated")
        if pds is not None and isinstance(src_ref, str) and (patient_dir / src_ref.split("#", 1)[0]).is_file() \
                and not report_prints_date(patient_dir, src_ref, pds):
            add(f"{ACUTE_FINDINGS_NAME}: {fid} change_vs_prior.prior_date_stated {pds!r} is not printed in the cited "
                "report (or another page of it) — only a comparison date the report states is recorded")
        # acute-findings.md §5: only this archive's originals are registered — a digest of an earlier
        # archive (prior_archive) or a patient/caregiver statement never becomes an acute finding
        if f.get("provenance_layer") not in (None, "source_reported"):
            add(f"{ACUTE_FINDINGS_NAME}: {fid} provenance_layer {f.get('provenance_layer')!r} — acute findings are "
                "registered from this archive's originals only (source_reported); prior-archive digests and "
                "self-reports are history / escalation, not acute findings")
        if isinstance(src_ref, str) and _is_digest_sidecar(patient_dir, src_ref.split("#", 1)[0]):
            add(f"{ACUTE_FINDINGS_NAME}: {fid} cites the prior-archive digest {src_ref.split('#', 1)[0]} — a digest "
                "is history only and never the source of an acute finding (phase2 §5.9)")
    for ev in events:
        fid = ev.get("acute_finding_id")
        if ev.get("category") != "acute_finding" and fid in (None, ""):
            continue
        f = by_id.get(fid)
        if f is None:
            add(f"timeline.json: event {ev.get('event_id')} registers acute finding {fid!r} "
                f"that {ACUTE_FINDINGS_NAME} does not contain")
        elif f.get("timeline_event_id") != ev.get("event_id"):
            add(f"timeline.json: event {ev.get('event_id')} ↔ {fid}: the finding points at "
                f"{f.get('timeline_event_id')!r}, not this event")


def gate_sidecar_headers(patient_dir: Path, errors: list, warnings: list | None = None,
                         generation: str | None = None) -> None:
    """O-01/O-07/O-09: pinned sidecar header block; EXTRACTOR is a logged worker (the
    orchestrator never writes sidecars); an llm_vision reread is never independent;
    header and inventory row agree (worker, reread, channel, sha256).

    Scope: the sidecars written under the current contract (sidecar_contract_scope). On a
    current archive, carried-over legacy sidecars of an update-type run are one WARN; on a
    legacy archive every missing EXTRACTOR is one WARN."""
    import pii_rescan  # sibling module: the one header-block parser
    current = _generation(patient_dir, generation)
    if not _bucket_sidecars(patient_dir):
        return
    if not current:
        sidecars = _bucket_sidecars(patient_dir)
        missing = [p for p in sidecars
                   if not pii_rescan.parse_header(p.read_text(encoding="utf-8", errors="replace")).get("EXTRACTOR")]
        if missing and warnings is not None:
            warnings.append(
                f"legacy archive: sidecar_header: {len(missing)}/{len(sidecars)} sidecar(s) carry no "
                "EXTRACTOR worker id — the current contract requires the pinned header block with "
                "EXTRACTOR ∈ update_log workers[] (the orchestrator never writes sidecars)"
            )
        return
    scoped, carried = sidecar_contract_scope(patient_dir)
    if carried and warnings is not None:
        warnings.append(
            f"sidecar_header: {len(carried)} carried-over sidecar(s) from an earlier contract were not "
            "rewritten by this run's workers and carry no pinned header (not retroactively required; "
            "run_mode legacy_upgrade re-transcribes them): "
            f"{', '.join(p.relative_to(patient_dir).as_posix() for p in carried[:3])}"
            + (" …" if len(carried) > 3 else "")
        )
    if not scoped:
        return
    workers = _update_log_workers(patient_dir)
    if not workers:
        errors.append(f"sidecar_header: {UPDATE_LOG_NAME} lists no workers[] — cannot verify "
                      "which worker wrote each sidecar")
        workers = set()
    rows = _inventory_rows(patient_dir)
    worker_recs = _update_log_worker_records(patient_dir)
    import page_completeness as pc
    for sc in scoped:
        rel = sc.relative_to(patient_dir).as_posix()
        text = sc.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        hdr = pii_rescan.parse_header(text)
        if rel not in rows:
            # every header value is bound to (and PII-scanned on) its inventory row; an unaccounted
            # sidecar has neither — and SHA256 / PAGE_LABEL / FILE_ID would go unchecked
            errors.append(f"sidecar_header: {rel}: has no source_inventory.json files[] row — every bucket "
                          "sidecar is one content unit of the inventory (Phase 2 §4.6)")
        # `## PII` closes the sidecar: exactly one, and no heading after it (an early or duplicated
        # `## PII` heading used to hide everything after it from the PII shape scan)
        heads = [(i, l) for i, l in enumerate(lines) if re.match(r"^#{1,6}\s", l)]
        pii_heads = [i for i, l in heads if re.match(r"^##\s+PII\b", l)]
        if len(pii_heads) != 1:
            errors.append(f"sidecar_header: {rel}: {len(pii_heads)} `## PII` headings — exactly one, as the last "
                          "section (phase1 §4 G)")
        elif heads and heads[-1][0] != pii_heads[0]:
            errors.append(f"sidecar_header: {rel}: a heading follows `## PII` (line {heads[-1][0] + 1}) — `## PII` is "
                          "the last section of a sidecar")
        if not hdr:
            errors.append(f"sidecar_header: {rel}: no header block (pinned KEY: value lines at the top)")
            continue
        # a printed page label in the body must be transcribed into PAGE_LABEL (O-04.1: missing-page
        # detection reads only the header, so a label left in the body hides the gap)
        pl_hdr = hdr.get("PAGE_LABEL", "").strip()
        if pl_hdr.lower() in _NO_PAGE_LABEL:
            n_hdr = pii_rescan.header_block_length(lines)
            for i, line in enumerate(lines[n_hdr:], start=n_hdr + 1):
                if pc.body_page_label(line):
                    errors.append(f"sidecar_header: {rel}: line {i} prints a page label but PAGE_LABEL is "
                                  f"{pl_hdr or 'empty'!r} — transcribe the printed label verbatim into PAGE_LABEL")
                    break
        for key, allowed in (("READ_MODE", SIDECAR_READ_MODES), ("ADAPTER", SIDECAR_ADAPTERS),
                             ("MODALITY", SIDECAR_MODALITIES)):
            if key in hdr and hdr[key].strip() not in allowed:
                errors.append(f"sidecar_header: {rel}: {key} {hdr[key].strip()!r} is not one of {' | '.join(allowed)} "
                              "(organizer-prompt-phase1-ocr.md §3)")
        n = pii_rescan.header_block_length(lines)
        if n < len(lines) and lines[n].strip():
            m = pii_rescan.HEADER_LINE_RE.match(lines[n])
            what = f"unknown header key(s) {m.group(1)}" if m else f"line {n + 1} {lines[n][:24]!r}"
            errors.append(f"sidecar_header: {rel}: {what} — the header block holds pinned keys only and ends "
                          "at a blank line; anything else is outside the (PII-exempt) header and scanned as body")
        missing_keys = [k for k in pii_rescan.PINNED_HEADER_KEYS if k not in hdr]
        if missing_keys:
            errors.append(f"sidecar_header: {rel}: missing pinned header key(s) {', '.join(missing_keys)}")
        # exactly the 12 pinned keys, once each, in the pinned order (phase1 §3 「恰好 12 个键、
        # 按此顺序」): legacy keys (ADAPTER_PROVENANCE / ORIGINAL …) are known to the PII
        # parser but are not part of the current header.
        keys = [pii_rescan.HEADER_LINE_RE.match(l).group(1) for l in lines[:n]]
        extra = sorted({k for k in keys if k not in pii_rescan.PINNED_HEADER_KEYS})
        dups = sorted({k for k in keys if keys.count(k) > 1})
        if extra:
            errors.append(f"sidecar_header: {rel}: header key(s) {', '.join(extra)} are not part of the "
                          "pinned 12-key header")
        if dups:
            errors.append(f"sidecar_header: {rel}: duplicate header key(s) {', '.join(dups)}")
        if not (missing_keys or extra or dups) and keys != list(pii_rescan.PINNED_HEADER_KEYS):
            errors.append(f"sidecar_header: {rel}: header keys out of the pinned order — expected "
                          f"{' / '.join(pii_rescan.PINNED_HEADER_KEYS)}, got {' / '.join(keys)}")
        src = hdr.get("SOURCE", "").strip()
        if "SOURCE" in hdr and src not in SIDECAR_SOURCE_TYPES:
            errors.append(f"sidecar_header: {rel}: SOURCE {src!r} is not a pinned document type "
                          "(organizer-prompt-phase1-ocr.md §3; paths and handles belong in source_inventory)")
        for key in ("PRIMARY_CHANNEL", "SECOND_READ_CHANNEL"):
            if key in hdr and not READ_CHANNEL_RE.match(hdr[key].strip()):
                errors.append(f"sidecar_header: {rel}: {key} {hdr[key].strip()!r} is not a pinned channel value "
                              "(text_layer | table_parser | deterministic_ocr:<engine> | barcode | human | "
                              "llm_vision | prior_archive_sidecar | none)")
        ext = hdr.get("EXTRACTOR", "").strip()
        if not ext:
            errors.append(f"sidecar_header: {rel}: EXTRACTOR missing — every sidecar names the worker that wrote it")
        elif ext.lower() in RESERVED_WORKER_IDS:
            errors.append(f"sidecar_header: {rel}: EXTRACTOR {ext!r} is the orchestrator — sidecars are written by workers only")
        elif ext not in workers:
            errors.append(f"sidecar_header: {rel}: EXTRACTOR {ext!r} is not a worker in {UPDATE_LOG_NAME} entries[].workers[]")
        else:
            # the author is a sidecar-writing worker (Phase 1 / retry / continuation / digest / stub)
            # that was given this source — a Phase 2 worker, or any other logged worker, never writes one
            rec = worker_recs.get(ext) or {"phases": set(), "files": set()}
            if not rec["phases"] & set(SIDECAR_WRITER_PHASES):
                errors.append(f"sidecar_header: {rel}: EXTRACTOR {ext!r} is logged with phase "
                              f"{' / '.join(sorted(rec['phases'])) or 'none'} — sidecars are written by "
                              f"{' / '.join(SIDECAR_WRITER_PHASES)} workers only")
            row0 = rows.get(rel) or {}
            handles = {rel, hdr.get("FILE_ID", "").strip()} | {
                str(row0.get(k)) for k in ("source_id", "file_id") if isinstance(row0.get(k), str)}
            handles.discard("")
            if not handles & rec["files"]:
                errors.append(f"sidecar_header: {rel}: EXTRACTOR {ext!r} was not given this source — its update_log "
                              "workers[].files lists neither the FILE_ID / source_id nor the sidecar path")
        indep = hdr.get("INDEPENDENT_REREAD", "").strip().lower()
        if indep not in ("true", "false"):
            errors.append(f"sidecar_header: {rel}: INDEPENDENT_REREAD must be true or false")
        second = hdr.get("SECOND_READ_CHANNEL", "")
        primary = hdr.get("PRIMARY_CHANNEL", "")
        if indep == "true":
            c1, c2 = _channel_category(primary), _channel_category(second)
            if c2 in ("", "none", "null"):
                errors.append(f"sidecar_header: {rel}: INDEPENDENT_REREAD true without a second read channel")
            elif "llm_vision" in (c1, c2):
                errors.append(f"sidecar_header: {rel}: INDEPENDENT_REREAD must be false when a read "
                              "channel is llm_vision (a model reading the image is not an independent reread)")
            elif c1 == c2:
                errors.append(f"sidecar_header: {rel}: INDEPENDENT_REREAD true but both reads use channel {c1!r}")
        elif indep == "false":
            # the flag is mechanical in BOTH directions (phase1 §2: true iff the categories differ
            # and neither is llm_vision) — an under-claimed reread hides a real second read.
            c1, c2 = _channel_category(primary), _channel_category(second)
            if c1 not in ("", "none", "null") and c2 not in ("", "none", "null") and c1 != c2 \
                    and "llm_vision" not in (c1, c2):
                errors.append(f"sidecar_header: {rel}: INDEPENDENT_REREAD false although the reads use different "
                              f"channel categories ({c1} / {c2}) and neither is llm_vision — the flag is true iff that holds")
        if hdr.get("READ_MODE", "").strip() == "hybrid_verified" and indep != "true":
            errors.append(f"sidecar_header: {rel}: READ_MODE hybrid_verified is reserved for an independent reread "
                          "that agreed (INDEPENDENT_REREAD true)")
        # CONFIDENCE is rule-derived, not self-assessed (phase1 §3): any uncertain field or a stub
        # → low; INDEPENDENT_REREAD true with no uncertain field → high (low only for handwriting /
        # a photographed pack or screen, which a script cannot see); everything else medium.
        conf = hdr.get("CONFIDENCE", "").strip()
        body = "\n".join(lines[n:])
        uncertain = bool(_UNCERTAIN_TOKEN_RE.search(body)) or _UNCERTAIN_BLOCK_HEADING in body
        stub = "[INGESTION_BLOCKED" in body
        if "CONFIDENCE" in hdr:
            if conf not in SIDECAR_CONFIDENCE:
                errors.append(f"sidecar_header: {rel}: CONFIDENCE {conf!r} must be low | medium | high (rule-derived, "
                              "not a score)")
            elif (uncertain or stub) and conf != "low":
                errors.append(f"sidecar_header: {rel}: CONFIDENCE {conf} but the sidecar "
                              f"{'is an [INGESTION_BLOCKED] stub' if stub else 'carries uncertain fields'} → low")
            elif conf == "high" and indep != "true":
                errors.append(f"sidecar_header: {rel}: CONFIDENCE high requires INDEPENDENT_REREAD true")
            elif conf == "medium" and indep == "true":
                errors.append(f"sidecar_header: {rel}: CONFIDENCE medium with INDEPENDENT_REREAD true and no uncertain "
                              "field → high (or low for handwriting / a photographed pack or screen)")
        sha = hdr.get("SHA256", "").strip()
        row = rows.get(rel)
        if row is None:
            # no row to compare against: the header's own digest still has to be real
            if src == "prior_archive_digest":
                if sha != "none":
                    errors.append(f"sidecar_header: {rel}: prior-archive digest SHA256 {sha!r} must be exactly `none`")
            elif not re.fullmatch(r"[0-9a-f]{64}", sha):
                errors.append(f"sidecar_header: {rel}: SHA256 {sha!r} is not the 64-char lowercase hex digest of "
                              "the original (scripts/inventory_hash.py)")
        if row is not None:
            # header ↔ inventory: the header is the sidecar's own copy of its inventory row
            fid = hdr.get("FILE_ID", "").strip()
            if "FILE_ID" in hdr and isinstance(row.get("source_id"), str) and fid != row["source_id"]:
                errors.append(f"sidecar_header: {rel}: FILE_ID {fid!r} ≠ source_inventory source_id "
                              f"{row['source_id']!r} (FILE_ID is the original's source_id)")
            for key, col in (("READ_MODE", "read_mode"), ("ADAPTER", "adapter"), ("MODALITY", "modality")):
                if key in hdr and isinstance(row.get(col), str) and hdr[key].strip() != row[col]:
                    errors.append(f"sidecar_header: {rel}: {key} {hdr[key].strip()!r} ≠ source_inventory {col} {row[col]!r}")
            if "PAGE_LABEL" in hdr and "page_label" in row:
                pl = hdr["PAGE_LABEL"].strip()
                hdr_label = None if pl.lower() in _NO_PAGE_LABEL else pl
                if hdr_label != row.get("page_label"):
                    errors.append(f"sidecar_header: {rel}: PAGE_LABEL {pl!r} ≠ source_inventory page_label "
                                  f"{row.get('page_label')!r} (verbatim label, or none ↔ null)")
            is_digest = row.get("source_kind") == "prior_archive_digest"
            if "SOURCE" in hdr and (src == "prior_archive_digest") != is_digest:
                errors.append(f"sidecar_header: {rel}: SOURCE {src!r} but source_inventory source_kind is "
                              f"{row.get('source_kind')!r} — a prior-archive digest is SOURCE prior_archive_digest, "
                              "and only a digest is")
            if is_digest and _channel_category(primary) != "prior_archive_sidecar":
                errors.append(f"sidecar_header: {rel}: a prior-archive digest reads PRIMARY_CHANNEL prior_archive_sidecar, "
                              f"got {primary.strip()!r}")
            elif not is_digest and "prior_archive_sidecar" in (_channel_category(primary), _channel_category(second)):
                errors.append(f"sidecar_header: {rel}: prior_archive_sidecar is the digest channel only — this row is an upload")
            prov = row.get("extractor_provenance") if isinstance(row.get("extractor_provenance"), dict) else {}
            if ext and prov.get("worker_id") not in (None, ext):
                errors.append(f"sidecar_header: {rel}: EXTRACTOR {ext!r} ≠ source_inventory worker_id {prov.get('worker_id')!r}")
            if isinstance(row.get("independent_reread"), bool) and indep in ("true", "false") \
                    and row["independent_reread"] != (indep == "true"):
                errors.append(f"sidecar_header: {rel}: INDEPENDENT_REREAD {indep} ≠ source_inventory independent_reread")
            if isinstance(row.get("second_read_channel"), str) and second and row["second_read_channel"] != second:
                errors.append(f"sidecar_header: {rel}: SECOND_READ_CHANNEL {second!r} ≠ source_inventory {row['second_read_channel']!r}")
            if row.get("source_kind") == "prior_archive_digest":
                # a digest has no uploaded original: its header SHA256 is pinned to `none` (phase1
                # §3/§12, phase2 §4.6) and its inventory row's sha256 is null. A hash there would be
                # read as "the original's digest" by the sha256 diff and the header ↔ inventory
                # binding. (This gate runs on current-contract archives only; legacy archives are
                # the WARN branch above.)
                if sha != "none":
                    errors.append(f"sidecar_header: {rel}: prior-archive digest SHA256 {sha!r} must be exactly "
                                  "`none` — a digest has no uploaded original to hash (phase1 §12; inventory "
                                  "sha256 null)")
            elif not re.fullmatch(r"[0-9a-f]{64}", sha):
                errors.append(f"sidecar_header: {rel}: SHA256 {sha!r} is not the 64-char lowercase hex digest of "
                              "the original (scripts/inventory_hash.py) — a placeholder cannot be matched to the inventory")
            elif isinstance(row.get("sha256"), str) and row["sha256"] != sha:
                errors.append(f"sidecar_header: {rel}: SHA256 header ≠ source_inventory sha256")


# Characters str.splitlines() treats as a line break but `cat -n` / `grep -n` / `sed -n` do not
# (a lone \r is matched separately: \r\n is one break for both). anchor-contract.md §1a.
_SPLITLINES_ONLY_BREAKS = "\f\v\x1c\x1d\x1e\x85  "
_LONE_CR_RE = re.compile(r"\r(?!\n)")


def odd_line_breaks(raw: bytes) -> int:
    """How many line separators in a sidecar's bytes split lines for str.splitlines() only."""
    text = raw.decode("utf-8", errors="replace")
    return sum(text.count(ch) for ch in _SPLITLINES_ONLY_BREAKS) + len(_LONE_CR_RE.findall(text))


def gate_sidecar_line_breaks(patient_dir: Path, errors: list, warnings: list | None = None,
                             generation: str | None = None) -> None:
    """C10: one line numbering. Every `#L` anchor, `## 不确定字段` `line:` and verbatim binding
    counts lines as str.splitlines() does, which also breaks at a form feed (pdftotext puts one
    between pages) and the other separators above; cat -n does not, so the two counts drift.
    Phase 1 writes a page break as a newline: a sidecar of this contract that still holds one
    is an ERROR; carried-over / legacy sidecars are one WARN."""
    current = _generation(patient_dir, generation)
    if current:
        scoped, carried = sidecar_contract_scope(patient_dir)
    else:
        scoped, carried = [], _bucket_sidecars(patient_dir)
    for sc in scoped:
        n = odd_line_breaks(sc.read_bytes())
        if n:
            errors.append(f"line_breaks: {sc.relative_to(patient_dir).as_posix()}: {n} form feed / line separator(s) "
                          "that str.splitlines() counts as a line break but cat -n does not — write each page break "
                          "as a newline so every #L anchor and `line:` means the same line for tools and the validator "
                          "(schemas/anchor-contract.md §1a)")
    odd = [sc.relative_to(patient_dir).as_posix() for sc in carried if odd_line_breaks(sc.read_bytes())]
    if odd and warnings is not None:
        warnings.append(f"{'' if current else 'legacy archive: '}line_breaks: {len(odd)} "
                        f"{'carried-over ' if current else ''}sidecar(s) hold form feeds / line separators, so "
                        f"their line numbers differ between str.splitlines() and cat -n: {', '.join(odd[:3])}"
                        + (" …" if len(odd) > 3 else ""))


LEXICON_DIR_ENV = "CB_ORGANIZE_LEXICON_DIR"  # tests point this at a synthetic lexicon dir
_INTENT_VALUES = ("deleted", "amended")


def _lexicon_dir() -> Path:
    env = os.environ.get(LEXICON_DIR_ENV)
    return Path(env) if env else REPO_ROOT / "references" / "lexicons"


def _lexicon_entries(name, cache: dict) -> set[str] | None:
    """Full lines of references/lexicons/<name>.txt (NFKC, stripped); None = no such lexicon."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+(\.txt)?", name):
        return None
    stem = name[:-4] if name.endswith(".txt") else name
    if stem not in cache:
        path = _lexicon_dir() / f"{stem}.txt"
        try:
            cache[stem] = {unicodedata.normalize("NFKC", l).strip()
                           for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}
        except OSError:
            cache[stem] = None
    return cache[stem]


# ---- a minimal reader for the `## 不确定字段` YAML subset (no PyYAML dependency) ----
def _strip_yaml_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _split_top(s: str) -> list[str]:
    parts, depth, quote, buf = [], 0, None, ""
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    parts.append(buf)
    return [x for x in parts if x.strip()]


def _yaml_value(t: str):
    t = t.strip()
    if t.startswith("{") and t.endswith("}"):
        out = {}
        for part in _split_top(t[1:-1]):
            k, sep, v = part.partition(":")
            if sep:
                out[k.strip().strip("\"'")] = _yaml_value(v)
        return out
    if t.startswith("[") and t.endswith("]"):
        return [_yaml_value(x) for x in _split_top(t[1:-1])]
    if t in ("", "null", "~", "Null", "NULL"):
        return None
    if t in ("true", "false"):
        return t == "true"
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def parse_uncertain_entries(block: str) -> list[dict]:
    """Entries of a `## 不确定字段` block: `- id: U-nnn` items with scalar keys and the
    `readings` / `candidates` lists (flow `- {k: v}` or block `- k: v` items)."""
    entries: list[dict] = []
    cur: dict | None = None
    list_key: str | None = None
    item_indent = -1
    for raw in block.splitlines():
        line = _strip_yaml_comment(raw)
        if not line.strip():
            continue
        m = re.match(r"^(\s*)-\s*id\s*:\s*(.*)$", line)
        if m:
            cur = {"id": _yaml_value(m.group(2))}
            entries.append(cur)
            list_key, item_indent = None, -1
            continue
        if cur is None:
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^\s*-\s*(.*)$", line)
        if m and list_key is not None:
            body = m.group(1).strip()
            item_indent = indent + 2
            if body.startswith(("{", "[")) or ":" not in body:
                cur[list_key].append(_yaml_value(body))
            else:
                k, _, v = body.partition(":")
                cur[list_key].append({k.strip(): _yaml_value(v)})
            continue
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if list_key is not None and indent >= item_indent > 0 and cur[list_key] \
                and isinstance(cur[list_key][-1], dict):
            cur[list_key][-1][key] = _yaml_value(val)
            continue
        if val.strip() == "":
            cur[key] = []
            list_key, item_indent = key, -1
        else:
            cur[key] = _yaml_value(val)
            list_key, item_indent = None, -1
    return entries


def _uncertain_block(text: str) -> tuple[str, int]:
    """(`## 不确定字段` block text, heading offset or -1)."""
    pos = text.find(_UNCERTAIN_BLOCK_HEADING)
    if pos == -1:
        return "", -1
    rest = text[pos + len(_UNCERTAIN_BLOCK_HEADING):]
    nxt = re.search(r"^##\s", rest, re.MULTILINE)
    return (rest[:nxt.start()] if nxt else rest), pos


def _agreeing_independent_reads(entry: dict) -> bool:
    """≥ 2 non-null readings from DIFFERENT non-llm_vision channel categories, same text."""
    by_text: dict[str, set[str]] = {}
    for r in entry.get("readings") or []:
        if not isinstance(r, dict) or not isinstance(r.get("text"), str) or not r["text"].strip():
            continue
        cat = _channel_category(r.get("channel") if isinstance(r.get("channel"), str) else "")
        if not cat or cat == "llm_vision":
            continue
        by_text.setdefault(_norm_text(r["text"]), set()).add(cat)
    return any(len(cats) >= 2 for cats in by_text.values())


def _candidate_norm(s: str) -> str:
    """phase1 §5 candidate rule 1: NFKC + case fold, then strip a leading/trailing No. / 组 / 站."""
    t = unicodedata.normalize("NFKC", s).casefold().strip()
    changed = True
    while changed and t:
        changed = False
        for a in _CANDIDATE_AFFIXES:
            if t.startswith(a):
                t, changed = t[len(a):].strip(), True
            if t.endswith(a):
                t, changed = t[:-len(a)].strip(), True
    return t


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (insert / delete / substitute = 1 each), phase1 §5 rule 2."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def high_candidate_problem(entry: dict, text: str) -> str | None:
    """phase1 §5 rule 5 for a candidate marked `high`: distance 0 to at least one reading and
    ≤ 1 to every other reading. The distance-0 reading must be COMPLETE — a reading that
    resolved only part of its characters (`10R?`, PARTIAL_READING_MARKERS) cannot make a
    candidate high. Null readings (a channel that read nothing) are not readings. None = OK."""
    reads = [r["text"] for r in entry.get("readings") or []
             if isinstance(r, dict) and isinstance(r.get("text"), str) and r["text"].strip()]
    c = _candidate_norm(text)
    dist = [(_edit_distance(c, _candidate_norm(r)), r) for r in reads]
    exact = [r for d, r in dist if d == 0 and not any(m in r for m in PARTIAL_READING_MARKERS)]
    if not exact:
        partial = [r for r in reads if any(m in r for m in PARTIAL_READING_MARKERS)]
        why = (f"the reading(s) {', '.join(map(repr, partial))} resolved only part of the characters"
               if partial else "no reading equals it")
        return f"is marked high but {why} (high = a complete reading at distance 0)"
    far = [r for d, r in dist if d > 1]
    if far:
        return f"is marked high but reading {far[0]!r} is more than one edit away (high = every other reading ≤ 1)"
    return None


def _cross_ref_lines(patient_dir: Path, rows: dict[str, dict], ref) -> list[str]:
    """The cited line(s) of a cross_doc_supported ref: a bucket anchor, or the Phase-1 form
    `ocr/<source_id>.md#L<n>` resolved through source_inventory (source_id / file_id → sidecar)."""
    if not isinstance(ref, str):
        return []
    path, _, frag = ref.partition("#")
    targets: list[Path] = []
    if path.startswith("ocr/"):
        name = Path(path).stem
        targets = [patient_dir / rel for rel, row in rows.items()
                   if name in (row.get("source_id"), row.get("file_id"))]
    else:
        targets = [patient_dir / path]
    m = re.match(r"L(\d+)(?:-L(\d+))?$", frag)
    out: list[str] = []
    for tgt in targets:
        if not tgt.is_file():
            continue
        lines = tgt.read_text(encoding="utf-8", errors="replace").splitlines()
        if m:
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            out.extend(lines[a - 1:b])
        else:
            out.extend(lines)
    return out


def _rule6_extra_ok(patient_dir: Path, rows: dict[str, dict], entry: dict, got: list, exp: list,
                    lexicon_lines: list[str], reads: list) -> bool:
    """phase1 §5 rule 6: `got` is the mechanical list `exp` with its 3rd candidate replaced (or, when
    fewer than 3, one appended) by a whole lexicon line X, X's confidence by rule 5, and X printed on
    a line the entry's cross_doc_supported (status supported) refs cite."""
    import lexicon_candidates as lc
    if not got:
        return False
    head, (x_text, x_conf) = got[:-1], got[-1]
    if len(exp) >= lc.MAX_CANDIDATES:
        ok_shape = len(got) == len(exp) and head == exp[:-1]
    else:
        ok_shape = len(got) == len(exp) + 1 and head == exp
    if not ok_shape or not isinstance(x_text, str) or x_text in [t for t, _ in exp]:
        return False
    if unicodedata.normalize("NFKC", x_text).strip() not in lexicon_lines:
        return False
    live = [r for r in reads if isinstance(r, str) and r.strip()]
    if x_conf != lc.confidence(x_text, live):
        return False
    cds = entry.get("cross_doc_supported")
    if not isinstance(cds, dict) or cds.get("status") != "supported":
        return False
    needle = _norm_text(x_text).casefold()
    return any(needle in _norm_text(l).casefold() for ref in cds.get("refs") or []
               for l in _cross_ref_lines(patient_dir, rows, ref))


def gate_review_flag_semantics(patient_dir: Path, errors: list, warnings: list | None = None,
                               generation: str | None = None) -> None:
    """O-01: document_intent needs two agreeing independent reads; uncertain_ids and
    cross_doc_supported refs resolve; [OCR_UNCERTAIN:U-nnn] tokens ↔ `## 不确定字段`
    entries whose `line` holds the token and whose candidates are whole lexicon lines."""
    import pii_rescan
    current = _generation(patient_dir, generation)
    add = _router(errors, warnings, current)
    texts: dict[str, str] = {}

    def text_of(rel: str) -> str | None:
        if rel not in texts:
            p = patient_dir / rel
            texts[rel] = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        return texts[rel]

    def entries_of(rel: str) -> dict[str, dict]:
        block, _ = _uncertain_block(text_of(rel) or "")
        return {str(e.get("id")): e for e in parse_uncertain_entries(block)}

    # sidecar-internal uncertainty bookkeeping — for the sidecars written under the
    # current contract; carried-over legacy sidecars (and a legacy archive) only WARN.
    if current:
        scoped, carried = sidecar_contract_scope(patient_dir)
    else:
        scoped, carried = [], _bucket_sidecars(patient_dir)
    bare_carried = 0
    for sc in carried:
        bare_carried += sum(1 for t in _UNCERTAIN_TOKEN_RE.findall(text_of(sc.relative_to(patient_dir).as_posix()) or "") if not t)
    if bare_carried and warnings is not None:
        prefix = "" if current else "legacy archive: "
        warnings.append(f"{prefix}uncertainty: {bare_carried} bare [OCR_UNCERTAIN] token(s) in "
                        f"{'carried-over ' if current else ''}sidecars carry no id, engine readings or candidates "
                        "(current contract: [OCR_UNCERTAIN:U-nnn])")
    lex_cache: dict = {}
    lexicon_dir_missing = not _lexicon_dir().is_dir()
    unverified_candidates = 0
    import lexicon_candidates as lc  # sibling: the one candidate computation (phase1 §5 rules 1-5)
    rows_all = _inventory_rows(patient_dir)
    scoped_ids: dict[str, set[str]] = {}
    entries_by_rel: dict[str, dict[str, dict]] = {}
    for sc in scoped:
        rel = sc.relative_to(patient_dir).as_posix()
        text = text_of(rel) or ""
        lines = text.splitlines()
        hdr_ch = pii_rescan.parse_header(text)
        header_channels = {hdr_ch.get(k, "").strip() for k in ("PRIMARY_CHANNEL", "SECOND_READ_CHANNEL")}
        header_channels -= {"", "none", "null"}
        tokens = _UNCERTAIN_TOKEN_RE.findall(text)
        bare = sum(1 for t in tokens if not t)
        if bare:
            errors.append(f"uncertainty: {rel}: {bare} bare [OCR_UNCERTAIN] token(s) — each needs an id "
                          "([OCR_UNCERTAIN:U-003]) with its engine readings in `## 不确定字段`")
        ids = {t for t in tokens if t}
        block, pos = _uncertain_block(text)
        if pos != -1:
            pii_pos = re.search(r"^##\s+PII\b", text, re.MULTILINE)
            if pii_pos and pii_pos.start() < pos:
                errors.append(f"uncertainty: {rel}: `## 不确定字段` sits after `## PII` — it must come "
                              "before it (the PII scan stops at `## PII`)")
        parsed = parse_uncertain_entries(block)
        entries = {str(e.get("id")) for e in parsed}
        scoped_ids[rel] = set(ids)
        entries_by_rel[rel] = {str(e.get("id")): e for e in parsed}
        for uid in sorted(ids - entries):
            errors.append(f"uncertainty: {rel}: [OCR_UNCERTAIN:{uid}] has no `## 不确定字段` entry")
        for uid in sorted(entries - ids):
            errors.append(f"uncertainty: {rel}: `## 不确定字段` entry {uid} has no [OCR_UNCERTAIN:{uid}] token in the text")
        for e in parsed:
            uid = str(e.get("id"))
            # each entry records the raw per-channel readings (references/schemas/README.md)
            if not isinstance(e.get("readings"), list) or not e["readings"]:
                errors.append(f"uncertainty: {rel}: `## 不确定字段` entry {uid} has no readings (the raw per-channel strings)")
            # `line` is the sidecar line that carries the token
            ln = e.get("line")
            if isinstance(ln, bool) or not isinstance(ln, int) or not 1 <= ln <= len(lines):
                errors.append(f"uncertainty: {rel}: entry {uid} line {ln!r} is not a line of this sidecar")
            elif f"[OCR_UNCERTAIN:{uid}]" not in lines[ln - 1]:
                errors.append(f"uncertainty: {rel}: entry {uid} line {ln} does not carry [OCR_UNCERTAIN:{uid}]")
            # every §1.3 key is written (an omitted field_class skipped the lexicon binding, an omitted
            # layout the layout → kind rule)
            missing_keys = [k for k in UNCERTAIN_ENTRY_KEYS if k not in e]
            if missing_keys:
                errors.append(f"uncertainty: {rel}: entry {uid} lacks {', '.join(missing_keys)} — every entry writes "
                              f"all of {' / '.join(UNCERTAIN_ENTRY_KEYS)} (phase1 §5)")
            cds_e = e.get("cross_doc_supported")
            if "cross_doc_supported" in e:
                if not isinstance(cds_e, dict) or cds_e.get("status") not in CROSS_DOC_STATUSES \
                        or not isinstance(cds_e.get("refs"), list):
                    errors.append(f"uncertainty: {rel}: entry {uid} cross_doc_supported must be {{status: supported | "
                                  "contradicted | none, refs: [...]}")
                elif (cds_e["status"] == "none") != (not cds_e["refs"]):
                    errors.append(f"uncertainty: {rel}: entry {uid} cross_doc_supported {cds_e['status']} with "
                                  f"{len(cds_e['refs'])} ref(s) — supported / contradicted cite the other page's reading, "
                                  "none cites nothing")
            # each reading names a pinned channel, and one this sidecar's header says was used (a reading
            # credited to an extra channel would fake the two agreeing independent reads of a document intent)
            for r_ in (e.get("readings") if isinstance(e.get("readings"), list) else []):
                if not isinstance(r_, dict):
                    errors.append(f"uncertainty: {rel}: entry {uid} reading {r_!r} is not {{channel, text, confidence}}")
                    continue
                ch = r_.get("channel")
                if not isinstance(ch, str) or not READ_CHANNEL_RE.match(ch.strip()):
                    errors.append(f"uncertainty: {rel}: entry {uid} reading channel {ch!r} is not a pinned channel value")
                elif ch.strip() not in header_channels and not (
                        _channel_category(ch) == "deterministic_ocr"
                        and "deterministic_ocr" in {_channel_category(h) for h in header_channels}):
                    errors.append(f"uncertainty: {rel}: entry {uid} reading channel {ch.strip()!r} is neither the header's "
                                  f"PRIMARY_CHANNEL nor SECOND_READ_CHANNEL ({' / '.join(sorted(header_channels)) or 'none'})")
            # pinned entry vocabulary (phase1 §5/§6)
            fc = e.get("field_class")
            if not isinstance(fc, (str, type(None))):
                errors.append(f"uncertainty: {rel}: entry {uid} field_class {fc!r} must be one value")
                fc = None
            if "field_class" in e and fc not in UNCERTAIN_FIELD_CLASSES:
                errors.append(f"uncertainty: {rel}: entry {uid} field_class {fc!r} is not one of "
                              f"{' | '.join(UNCERTAIN_FIELD_CLASSES)}")
            if "layout" in e and e.get("layout") not in UNCERTAIN_LAYOUTS:
                errors.append(f"uncertainty: {rel}: entry {uid} layout {e.get('layout')!r} is not one of "
                              f"{' | '.join(UNCERTAIN_LAYOUTS)} (shadow / stain / fold / page curvature = shadow_stain_fold)")
            if "layout_intent" in e and e.get("layout_intent") not in (None,) + _INTENT_VALUES:
                errors.append(f"uncertainty: {rel}: entry {uid} layout_intent {e.get('layout_intent')!r} is not "
                              "null | deleted | amended")
            want_lex = FIELD_CLASS_LEXICON.get(fc)
            cands = e.get("candidates") if isinstance(e.get("candidates"), list) else []
            if e.get("candidates") not in (None, []) and not isinstance(e.get("candidates"), list):
                errors.append(f"uncertainty: {rel}: entry {uid} candidates must be a list")
            if cands and fc in UNCERTAIN_FIELD_CLASSES and want_lex is None:
                errors.append(f"uncertainty: {rel}: entry {uid} field_class {fc} gets no candidates (only "
                              f"{' / '.join(FIELD_CLASS_LEXICON)} draw lexicon candidates) — write candidates: []")
            # candidates come only from the pinned lexicons, whole lines (never a free correction)
            for c in cands:
                if not isinstance(c, dict):
                    errors.append(f"uncertainty: {rel}: entry {uid} candidate {c!r} is not {{text, lexicon, confidence}}")
                    continue
                lex_name = c.get("lexicon")
                lex_stem = lex_name[:-4] if isinstance(lex_name, str) and lex_name.endswith(".txt") else lex_name
                if want_lex is not None and lex_stem != want_lex:
                    errors.append(f"uncertainty: {rel}: entry {uid} candidate {c.get('text')!r} comes from lexicon "
                                  f"{lex_name!r}, but field_class {fc} draws from {want_lex}")
                conf = c.get("confidence")
                if conf not in CANDIDATE_CONFIDENCE:
                    errors.append(f"uncertainty: {rel}: entry {uid} candidate {c.get('text')!r} confidence {conf!r} "
                                  "must be high | medium | low (rule-derived)")
                elif conf == "high" and isinstance(c.get("text"), str):
                    why = high_candidate_problem(e, c["text"])
                    if why:
                        errors.append(f"uncertainty: {rel}: entry {uid} candidate {c['text']!r} {why}")
                if lexicon_dir_missing:
                    unverified_candidates += 1
                    continue
                entries_lex = _lexicon_entries(c.get("lexicon"), lex_cache)
                ctext = c.get("text")
                if entries_lex is None:
                    errors.append(f"uncertainty: {rel}: entry {uid} candidate lexicon {c.get('lexicon')!r} is not a "
                                  "references/lexicons/*.txt word list")
                elif not isinstance(ctext, str) or unicodedata.normalize("NFKC", ctext).strip() not in entries_lex:
                    errors.append(f"uncertainty: {rel}: entry {uid} candidate {ctext!r} is not a whole line of "
                                  f"lexicon {c.get('lexicon')!r} — candidates are lexicon entries, never free corrections")
            # the candidate LIST is mechanical (phase1 §5 rules 1-5, scripts/lexicon_candidates.py): it must be
            # the recomputed list; rule 6 may replace the 3rd (or append one) with a whole lexicon line that the
            # entry's cross_doc_supported refs print (the clear reading on another page of the slice)
            lex_name = FIELD_CLASS_LEXICON.get(fc) if isinstance(fc, str) else None
            if lex_name and not lexicon_dir_missing and isinstance(e.get("candidates"), list):
                lines_lex = lex_cache.setdefault(("lines", lex_name), lc.load_lexicon(lex_name, _lexicon_dir()))
                reads = [r_.get("text") for r_ in (e.get("readings") or []) if isinstance(r_, dict)]
                if lines_lex is not None:
                    exp = [(c["text"], c["confidence"]) for c in lc.compute(reads, lines_lex, lex_name)]
                    got = [(c.get("text"), c.get("confidence")) for c in e["candidates"] if isinstance(c, dict)]
                    if got != exp and not _rule6_extra_ok(patient_dir, rows_all, e, got, exp, lines_lex, reads):
                        errors.append(
                            f"uncertainty: {rel}: entry {uid} candidates {[g[0] for g in got]} are not the mechanical list "
                            f"{[x[0] for x in exp]} ({', '.join(f'{x[0]}={x[1]}' for x in exp) or 'none within distance'}) — "
                            "run scripts/lexicon_candidates.py and copy its output (phase1 §5 rules 1-5; rule 6 only adds a "
                            "lexicon line that a cross_doc_supported ref prints)")
            # a document-intent reading (deleted / amended) needs two agreeing independent reads
            if e.get("layout_intent") in _INTENT_VALUES:
                if pii_rescan.parse_header(text).get("INDEPENDENT_REREAD", "").strip().lower() != "true":
                    errors.append(f"uncertainty: {rel}: layout_intent deleted/amended without an independent reread "
                                  "— record `layout` only and state the literal reading")
                elif not _agreeing_independent_reads(e):
                    errors.append(f"uncertainty: {rel}: entry {uid} layout_intent {e['layout_intent']} but its readings "
                                  "do not show two agreeing reads from different non-llm_vision channels")
    if unverified_candidates and warnings is not None:
        warnings.append(f"uncertainty: {unverified_candidates} lexicon candidate(s) not verified — "
                        f"{_lexicon_dir()} is absent")

    r = _load_json_quiet(patient_dir / "readiness.json")
    flags = r.get("review_flags") if isinstance(r, dict) else None
    if not isinstance(flags, list):
        return
    rows = _inventory_rows(patient_dir)
    # every [OCR_UNCERTAIN:U-nnn] of a sidecar of this contract reaches the user and downstream only
    # through a readiness flag (phase2 §3; SKILL Steps 10/11 read review_flags[] only)
    covered: set[tuple[str, str]] = set()
    for f in flags:
        if not isinstance(f, dict):
            continue
        refs_f = [cv.get("source_ref") for cv in (f.get("current_source_values") or []) if isinstance(cv, dict)]
        cds_f = f.get("cross_doc_supported")
        refs_f += list(cds_f.get("refs") or []) if isinstance(cds_f, dict) and isinstance(cds_f.get("refs"), list) else []
        files_f = {x.split("#", 1)[0] for x in refs_f if isinstance(x, str)}
        for u in f.get("uncertain_ids") or []:
            if isinstance(u, str):
                covered.update((rel_f, u) for rel_f in files_f)
    for rel_s, ids_s in sorted(scoped_ids.items()):
        for uid in sorted(ids_s):
            if (rel_s, uid) not in covered:
                errors.append(f"uncertainty: {rel_s}: [OCR_UNCERTAIN:{uid}] has no readiness flag — a flag lists the channel "
                              f"readings and names it in uncertain_ids while citing this sidecar (phase2 §3)")
    paraphrase_flags: dict[str, list] = {}
    for f in flags:
        if not isinstance(f, dict):
            continue
        fid = f.get("id", "?")
        af_ = f.get("affected_field")
        if isinstance(af_, str) and re.search(r"[、,，;；]", af_):
            add(f"review_flags: {fid} affected_field {af_!r} lists several fields — one flag per affected field "
                "(phase2 §2)")
        cited = sorted({cv["source_ref"].split("#", 1)[0] for cv in (f.get("current_source_values") or [])
                        if isinstance(cv, dict) and isinstance(cv.get("source_ref"), str)
                        and _DOMAIN_DIR_RE.match(cv["source_ref"])})
        cds = f.get("cross_doc_supported")
        refs = cds.get("refs") if isinstance(cds, dict) and isinstance(cds.get("refs"), list) else []
        uids = [u for u in (f.get("uncertain_ids") or []) if isinstance(u, str)]
        if f.get("kind") == "document_intent":
            if not cited:
                add(f"review_flags: {fid} kind document_intent cites no sidecar — two agreeing "
                    "independent reads cannot be shown; downgrade to artifact")
            for rel in cited:
                text = text_of(rel)
                hdr = pii_rescan.parse_header(text) if text else {}
                row = rows.get(rel) or {}
                ok = hdr.get("INDEPENDENT_REREAD", "").strip().lower() == "true" \
                    and row.get("independent_reread", True) is True
                if not ok:
                    add(f"review_flags: {fid} kind document_intent but {rel} has no independent reread "
                        "(INDEPENDENT_REREAD true) — downgrade to artifact and state the literal reading")
            # O-01.2: only two agreeing independent reads make a document intent
            if cited and not uids:
                add(f"review_flags: {fid} kind document_intent names no uncertain_ids — the `## 不确定字段` "
                    "entry holding the two agreeing reads must be referenced; otherwise downgrade to artifact")
            elif cited:
                resolved = [entries_of(rel).get(u) for rel in cited for u in uids]
                backed = [e for e in resolved if isinstance(e, dict)
                          and e.get("layout_intent") in _INTENT_VALUES and _agreeing_independent_reads(e)]
                if not backed:
                    add(f"review_flags: {fid} kind document_intent but none of its uncertain_ids "
                        f"({', '.join(uids)}) is an entry with layout_intent deleted/amended backed by two agreeing "
                        "reads from different non-llm_vision channels — downgrade to artifact")
        # phase2 §6.1 rows 1-3: an uncertain HIGH-RISK field (every field_class but other) read with layout
        # none is red unless another page's clear reading supports it (supported → yellow allowed);
        # contradicted is always red
        if f.get("kind") == "legibility" and uids:
            found_e = [e for e in (entries_of(rel).get(u) for rel in cited for u in uids) if isinstance(e, dict)]
            high_risk = [e for e in found_e if e.get("layout") in (None, "none")
                         and isinstance(e.get("field_class"), str) and e["field_class"] != "other"]
            if high_risk and f.get("severity") != "red":
                statuses = set()
                for e in high_risk:
                    c_ = cds if isinstance(cds, dict) else e.get("cross_doc_supported")
                    statuses.add(c_.get("status") if isinstance(c_, dict) else None)
                if statuses - {"supported"}:
                    add(f"review_flags: {fid} grades an uncertain high-risk field "
                        f"({', '.join(sorted({str(e.get('field_class')) for e in high_risk}))}) {f.get('severity')!r} without "
                        "another page's supporting reading — legibility on a high-risk field is red unless "
                        "cross_doc_supported is supported (phase2 §6.1)")
        # phase2 §6.1 / §2.4: a patient/caregiver self-report (a conversation: anchor or conversation_notes/ record,
        # or a sidecar whose SOURCE is patient_supplement / filed under 14_患者自管补充/) that disagrees with ONE original is
        # conflict / yellow. red would bar the original's field from use as if two records disagreed;
        # the self-report sits beside it and never outranks it.
        if f.get("kind") == "conflict":
            cv_refs = [cv["source_ref"] for cv in (f.get("current_source_values") or [])
                       if isinstance(cv, dict) and isinstance(cv.get("source_ref"), str)]

            def _self_report(ref: str) -> bool:
                if _is_conversation_note(ref):  # a conversation: anchor or any conversation_notes/ record
                    return True
                rel_ = ref.split("#", 1)[0]
                if rel_.startswith("14_患者自管补充/"):
                    return True
                txt = text_of(rel_) if _DOMAIN_DIR_RE.match(rel_) else None
                return bool(txt) and pii_rescan.parse_header(txt).get("SOURCE", "").strip() == "patient_supplement"

            selfs = [x for x in cv_refs if _self_report(x)]
            originals = {x.split("#", 1)[0] for x in cv_refs if x not in selfs}
            if selfs and len(originals) == 1 and f.get("severity") != "yellow":
                add(f"review_flags: {fid} is a self-report vs one original ({sorted(originals)[0]}) graded "
                    f"{f.get('severity')!r} — a patient/caregiver statement that disagrees with an original is "
                    "conflict / yellow (phase2 §6.1, §2.4)")
        # C1: `legibility` is only for an entry read with layout none; a layout anomaly (strike /
        # overprint / crop / stamp / shadow_stain_fold) read literally is kind artifact (phase2 §6.1).
        # Entry ids restart per sidecar, so only the flag's own cited sidecars are consulted and
        # the flag fires only when every cited entry with that id records a layout anomaly.
        if f.get("kind") == "legibility":
            for uid in uids:
                found = [e for e in (entries_of(rel).get(uid) for rel in cited) if isinstance(e, dict)]
                if found and all(e.get("layout") not in (None, "none") for e in found):
                    layouts = sorted({str(e.get("layout")) for e in found})
                    add(f"review_flags: {fid} kind legibility but its uncertain entry {uid} records layout "
                        f"{', '.join(layouts)} — a layout anomaly read literally is kind artifact; legibility "
                        "is only for layout none")
        # an anchor gap is `other` / `red` (phase2 §6.1, anchor-contract.md §5): a fact without an
        # anchor cannot be used as a confirmed value — it is not a yellow "verify later" item.
        if f.get("category") == ANCHOR_GAP_CATEGORY:
            if f.get("severity") != "red":
                add(f"review_flags: {fid} category {ANCHOR_GAP_CATEGORY} has severity {f.get('severity')!r} — "
                    "an anchor gap is severity red (phase2 §6.1)")
            if f.get("kind") != "other":
                add(f"review_flags: {fid} category {ANCHOR_GAP_CATEGORY} has kind {f.get('kind')!r} — "
                    "an anchor gap is kind other (phase2 §6.1)")
        if f.get("category") in (FOREIGN_PARAPHRASE_CATEGORY,) + LEGACY_ONLY_CATEGORIES \
                and (f.get("kind"), f.get("severity")) != ("other", "yellow"):
            add(f"review_flags: {fid} category {f.get('category')} is kind other / severity yellow "
                f"(has {f.get('kind')!r} / {f.get('severity')!r}; phase2 §6.1)")
        if f.get("category") == LEGACY_UNSUPPORTED_CATEGORY and current:
            errors.append(f"review_flags: {fid} category {LEGACY_UNSUPPORTED_CATEGORY} exists only on a legacy "
                          f"archive — on a current-contract archive a value no sidecar supports is an "
                          f"{ANCHOR_GAP_CATEGORY} (other / red)")
        if f.get("category") == PRIOR_DIGEST_UNRECOGNISED_CATEGORY and current:
            errors.append(f"review_flags: {fid} category {PRIOR_DIGEST_UNRECOGNISED_CATEGORY} exists only on a legacy "
                          "archive — on a current-contract archive a header-less digest-looking sidecar is sent back to "
                          "Phase 1 (phase2 §4.1 / §4.2), never kept")
        if f.get("category") == FOREIGN_PARAPHRASE_CATEGORY:
            for rel in sorted(set(cited)):
                paraphrase_flags.setdefault(rel, []).append(fid)
        for ref in refs:
            if not isinstance(ref, str) or not ANCHOR_RE.match(ref):
                add(f"review_flags: {fid} cross_doc_supported ref {ref!r} is not a bucket anchor")
            elif not ref.startswith("conversation:") and not (patient_dir / ref.split("#", 1)[0]).is_file():
                add(f"review_flags: {fid} cross_doc_supported ref {ref!r} does not resolve")
        for uid in uids:
            pool = cited + [x.split("#", 1)[0] for x in refs if isinstance(x, str)]
            found = any((text_of(rel) or "").find(f"[OCR_UNCERTAIN:{uid}]") != -1 for rel in pool)
            if not found:
                add(f"review_flags: {fid} uncertain_id {uid} is not an [OCR_UNCERTAIN:{uid}] token in the "
                    "sidecar(s) the flag cites")
    for rel_p, fids in sorted(paraphrase_flags.items()):
        if len(fids) > 1:
            add(f"review_flags: {rel_p} has {len(fids)} {FOREIGN_PARAPHRASE_CATEGORY} flags ({', '.join(map(str, fids))}) — "
                "one per sidecar, not one per finding (acute-findings.md §2.4)")


_PAIRING_HEADING = "## 列配对"
_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)
_PAIR_FIELDS = ("pairing_method", "value", "candidate_value", "raw_value")
# methods whose numbers come from pair_lab_columns.py (so the record names the script's input)
_SCRIPT_METHODS = ("linear_position", "single_value", "bbox", "none")
# methods that rest on a born-digital table structure (the header must name such a channel)
_STRUCTURE_METHODS = ("native_table", "table_parser")


def pairing_records(text: str) -> list[dict] | None:
    """The ```json tables of a sidecar's `## 列配对` block (phase1 §7); None when there is no block."""
    pos = text.find(_PAIRING_HEADING)
    if pos == -1:
        return None
    rest = text[pos + len(_PAIRING_HEADING):]
    nxt = re.search(r"^##\s", rest, re.MULTILINE)
    block = rest[:nxt.start()] if nxt else rest
    out: list[dict] = []
    for m in _JSON_FENCE_RE.finditer(block):
        try:
            doc = json.loads(m.group(1))
        except ValueError:
            out.append({"__unparseable__": True})
            continue
        out.append(doc if isinstance(doc, dict) else {"__unparseable__": True})
    return out


def _cell(v) -> str | None:
    return None if v is None else str(v)


def _item_key(s) -> str:
    return _norm_text(str(s)).casefold()


def gate_lab_pairing(patient_dir: Path, errors: list, warnings: list | None = None,
                     generation: str | None = None) -> None:
    """O-03 is mechanical end to end: every lab value in labs.json equals the pairing its sidecar's
    `## 列配对` record holds (pairing_method / value / candidate_value / raw_value, matched by item),
    and that record equals what scripts/pair_lab_columns.py computes from the input it names
    (raw/_extract/<source_id>.lab<k>.<txt|tsv|json>) — so a bbox value is always script output and a
    linear candidate cannot be relabelled a confirmed value. Position-paired candidates carry a
    legibility / yellow flag and a refused table an artifact / red flag citing the sidecar (phase2
    §5.1). Current-contract sidecars only; carried-over / legacy ones are not re-checked."""
    import pair_lab_columns as plc
    import pii_rescan
    current = _generation(patient_dir, generation)
    if not current:
        return
    labs = _load_json_quiet(patient_dir / "labs.json")
    panels = labs.get("panels") if isinstance(labs, dict) else None
    if not isinstance(panels, list):
        return
    scoped = {p.relative_to(patient_dir).as_posix() for p in sidecar_contract_scope(patient_dir)[0]}
    by_sidecar: dict[str, list[tuple[str, dict]]] = {}
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        for v in panel.get("values") or []:
            if not isinstance(v, dict) or not isinstance(v.get("source_refs"), list):
                continue
            rels = {r.split("#", 1)[0] for r in v["source_refs"] if isinstance(r, str) and _DOMAIN_DIR_RE.match(r)}
            for rel in rels & scoped:
                by_sidecar.setdefault(rel, []).append((str(panel.get("analyte")), v))
    r_doc = _load_json_quiet(patient_dir / "readiness.json")
    flags = [f for f in (r_doc.get("review_flags") or []) if isinstance(f, dict)] if isinstance(r_doc, dict) else []

    def flagged(rel: str, kind: str, severity: str) -> bool:
        return any(f.get("kind") == kind and f.get("severity") == severity
                   and any(isinstance(cv, dict) and isinstance(cv.get("source_ref"), str)
                           and cv["source_ref"].split("#", 1)[0] == rel for cv in (f.get("current_source_values") or []))
                   for f in flags)

    raw_present = (patient_dir / "raw").is_dir()
    not_recomputed: list[str] = []
    for rel, values in sorted(by_sidecar.items()):
        text = (patient_dir / rel).read_text(encoding="utf-8", errors="replace")
        hdr = pii_rescan.parse_header(text)
        channel_cats = {_channel_category(hdr.get(key, "").strip()) for key in ("PRIMARY_CHANNEL", "SECOND_READ_CHANNEL")}
        records = pairing_records(text)
        if not records:
            errors.append(f"lab_pairing: {rel}: labs.json cites this sidecar but it has no `## 列配对` record "
                          "(phase1 §7: one ```json table per lab table — the pair_lab_columns.py output)")
            continue
        pairs: dict[str, list[dict]] = {}
        for k, rec in enumerate(records, start=1):
            if rec.get("__unparseable__") or not isinstance(rec.get("pairs"), list):
                errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} is not a JSON object with pairs[]")
                continue
            for pr in rec["pairs"]:
                if isinstance(pr, dict):
                    pairs.setdefault(_item_key(pr.get("item")), []).append(pr)
            method = rec.get("pairing_method")
            inp = rec.get("input")
            if method in _STRUCTURE_METHODS and not (channel_cats & {"text_layer", "table_parser"}):
                errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} claims {method} but the sidecar header names no "
                              "text_layer / table_parser channel — a photographed or scanned table is paired by the "
                              "script (bbox from the OCR TSV) or read row by row (llm_row_read, candidate only)")
            if method == "llm_row_read":
                if "llm_vision" not in channel_cats:
                    errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} is llm_row_read but the sidecar header names "
                                  "no llm_vision channel")
                if any(isinstance(pr, dict) and (pr.get("value") is not None or pr.get("candidate_value") is None)
                       for pr in rec["pairs"]):
                    errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} (llm_row_read) must keep value null and "
                                  "the model's reading in candidate_value — a model row read is never a confirmed value")
            if method in _SCRIPT_METHODS or rec.get("tool") == "pair_lab_columns":
                if not isinstance(inp, str) or not inp.startswith("raw/_extract/"):
                    errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} ({method}) names no script input "
                                  "(input: raw/_extract/<source_id>.lab<k>.<txt|tsv|json>)")
                    continue
                src = patient_dir / inp
                if not src.is_file():
                    if raw_present:
                        errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} input {inp} is missing — the "
                                      "recorded pairing cannot be reproduced")
                    else:
                        not_recomputed.append(rel)
                    continue
                try:
                    redo = plc.run_input(src)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"lab_pairing: {rel}: re-running pair_lab_columns.py on {inp} failed: {exc}")
                    continue
                want = [tuple(_cell(p.get(fld)) for fld in ("item",) + _PAIR_FIELDS) for p in redo.get("pairs", [])]
                got = [tuple(_cell(p.get(fld)) for fld in ("item",) + _PAIR_FIELDS)
                       for p in rec["pairs"] if isinstance(p, dict)]
                if want != got:
                    errors.append(f"lab_pairing: {rel}: `## 列配对` table {k} is not what scripts/pair_lab_columns.py "
                                  f"computes from {inp} ({redo.get('pairing_method')}, {len(want)} pairs) — copy the "
                                  "script output; the model never pairs values")
        for analyte, v in values:
            cands = pairs.get(_item_key(analyte), [])
            if not cands:
                errors.append(f"lab_pairing: labs.json {analyte!r} ({rel}) is not an item of that sidecar's "
                              "`## 列配对` record")
                continue
            if not any(all(_cell(v.get(fld)) == _cell(pr.get(fld)) for fld in _PAIR_FIELDS) for pr in cands):
                pr = cands[0]
                diff = [f"{fld} {v.get(fld)!r} ≠ {pr.get(fld)!r}" for fld in _PAIR_FIELDS
                        if _cell(v.get(fld)) != _cell(pr.get(fld))]
                errors.append(f"lab_pairing: labs.json {analyte!r} ({rel}) does not match its `## 列配对` pair: "
                              + "; ".join(diff))
        methods = {v.get("pairing_method") for _, v in values}
        if methods & {"linear_position", "llm_row_read"} and not flagged(rel, "legibility", "yellow"):
            errors.append(f"lab_pairing: {rel}: position-paired or model-read candidate values without a readiness "
                          "flag kind legibility / severity yellow citing this sidecar (phase2 §5.1)")
        refused = any(isinstance(rec, dict) and rec.get("pairing_method") == "none" for rec in records)
        if refused and not flagged(rel, "artifact", "red"):
            errors.append(f"lab_pairing: {rel}: a refused table (pairing_method none) without a readiness flag kind "
                          "artifact / severity red citing this sidecar (phase2 §5.1 / §6.1)")
    if not_recomputed and warnings is not None:
        warnings.append(f"lab_pairing: {len(set(not_recomputed))} lab sidecar(s) checked against their `## 列配对` record "
                        "only — raw/ is absent here, so the record was not re-computed from its input")


def gate_page_completeness(patient_dir: Path, errors: list, warnings: list | None = None,
                           generation: str | None = None) -> None:
    """O-04: every printed-page gap (page_completeness.py) is a missing_pages gap in
    missing_items.json with the same group_key / pages_missing / page_total."""
    import page_completeness as pc
    current = _generation(patient_dir, generation)
    add = _router(errors, warnings, current)
    rep = pc.analyze(patient_dir)
    mi = _load_json_quiet(patient_dir / "missing_items.json")
    gaps = mi.get("document_gaps") if isinstance(mi, dict) else None
    recorded = {g.get("group_key"): g for g in (gaps or [])
                if isinstance(g, dict) and g.get("gap_type") == "missing_pages" and isinstance(g.get("group_key"), str)}
    r_doc = _load_json_quiet(patient_dir / "readiness.json")
    flags = [f for f in (r_doc.get("review_flags") or []) if isinstance(f, dict)] if isinstance(r_doc, dict) else []
    group_sidecars = {g["group_key"]: {s["sidecar"] for s in g.get("sidecars", [])} for g in rep.get("groups", [])}

    def _ints(v) -> list:
        return sorted(x for x in v if isinstance(x, int)) if isinstance(v, list) else []

    for gap in rep["gaps"]:
        r = recorded.get(gap["group_key"])
        pages = "、".join(str(n) for n in gap["pages_missing"])
        if r is None:
            add(f"page_completeness: group {gap['group_key']} prints {gap['page_total']} page(s) but "
                f"page(s) {pages} are absent and missing_items.json has no missing_pages gap for it")
        elif _ints(r.get("pages_missing")) != gap["pages_missing"] or r.get("page_total") != gap["page_total"] \
                or _ints(r.get("pages_present")) != gap["pages_present"]:
            add(f"page_completeness: group {gap['group_key']} missing_items records pages_present "
                f"{r.get('pages_present')} / pages_missing {r.get('pages_missing')} / page_total {r.get('page_total')}, "
                f"the page labels show {gap['pages_present']} / {gap['pages_missing']} / {gap['page_total']} "
                "(copy scripts/page_completeness.py gaps[] verbatim)")
        # phase2 §5.8 / §6.1: each gap also has a completeness / red readiness flag citing its pages
        members = group_sidecars.get(gap["group_key"], set())
        cited = [f for f in flags if f.get("kind") == "completeness" and f.get("severity") == "red"
                 and any(isinstance(cv, dict) and isinstance(cv.get("source_ref"), str)
                         and cv["source_ref"].split("#", 1)[0] in members
                         for cv in (f.get("current_source_values") or []))]
        if not cited:
            add(f"page_completeness: group {gap['group_key']} has no readiness flag kind completeness / severity red "
                "citing one of its sidecars (phase2 §5.8: one flag per missing-page group)")
    detected = {g["group_key"] for g in rep["gaps"]}
    for key in sorted(k for k in recorded if k not in detected):
        if warnings is not None:
            warnings.append(f"page_completeness: missing_items lists a missing_pages gap for {key} that "
                            "the printed page labels do not show — check the grouping")


def gate_source_freshness(patient_dir: Path, errors: list, warnings: list | None = None,
                          generation: str | None = None) -> None:
    """O-04: readiness recency fields equal the recomputed values; > 14 days carries a
    warnings[] line stating the day count."""
    import source_freshness as sf
    current = _generation(patient_dir, generation)
    r = _load_json_quiet(patient_dir / "readiness.json")
    if not isinstance(r, dict):
        return
    if not current:
        # A Phase-2-only pass on a legacy archive writes the recency block too (phase2 §6.2, legacy note):
        # its as_of_run_date (the LOCAL run date) is the reference; without it, generated_at (UTC).
        as_of = sf._parse_date(r.get("as_of_run_date")) or sf._parse_date(r.get("generated_at"))
        if as_of is None or warnings is None:
            return
        rep = sf.compute(patient_dir, as_of)
        if r.get("latest_source_date") is not None or "days_since_latest" in r:
            if (r.get("latest_source_date"), r.get("days_since_latest")) != (rep["latest_source_date"], rep["days_since_latest"]):
                warnings.append(
                    f"legacy archive: source_freshness: readiness says {r.get('latest_source_date')!r} / "
                    f"{r.get('days_since_latest')!r} days but the sidecars give {rep['latest_source_date']!r} / "
                    f"{rep['days_since_latest']!r} as of {rep['as_of_run_date']} — re-run scripts/source_freshness.py")
            elif rep["stale"] and sf.stale_warning(rep["latest_source_date"], rep["days_since_latest"]) \
                    not in [w for w in (r.get("warnings") or []) if isinstance(w, str)]:
                warnings.append("legacy archive: source_freshness: newest source is "
                                f"{rep['days_since_latest']} days old but readiness.warnings[] lacks the stale-source sentence")
        elif rep["stale"]:
            warnings.append(
                f"legacy archive: source_freshness: newest dated source {rep['latest_source_date']} is "
                f"{rep['days_since_latest']} days before {rep['as_of_run_date']} (> {STALE_DAYS}) and "
                "readiness.json has no recency fields to say so"
            )
        return
    as_of = sf._parse_date(r.get("as_of_run_date"))
    if as_of is None:
        return  # schema reports the missing/invalid field
    # The day count is measured from THIS run's date (D6): as_of_run_date must be (±1 day) the
    # date of the LATEST run that reconciled the sources — the newest update_log entry with a
    # non-empty inputs[] (the run that wrote the recency fields; a 段C / relevance entry with
    # inputs: [] does not recompute them) — or, with no such entry, organize_meta.generated_at.
    # An earlier run's date is refused: pinned to an old full run, a later incremental run would
    # zero the count (36 → 5 days) and skip the stale warning. as_of_run_date is the LOCAL run date
    # while entries[].at / generated_at are UTC ISO timestamps: around midnight the two calendar
    # dates differ by one day — hence ±1.
    latest_entry = _latest_input_entry(_update_log_entries(patient_dir))
    run_date, run_from = None, None
    if latest_entry is not None and isinstance(latest_entry.get("at"), str):
        run_date, run_from = sf._parse_date(latest_entry["at"][:10]), "the latest update_log entry with inputs[]"
    if run_date is None:
        meta = _load_json_quiet(patient_dir / ORGANIZE_META_NAME)
        if isinstance(meta, dict) and isinstance(meta.get("generated_at"), str):
            run_date, run_from = sf._parse_date(meta["generated_at"][:10]), "organize_meta.generated_at"
    if run_date is not None and abs((as_of - run_date).days) > 1:
        errors.append(
            f"source_freshness: readiness.as_of_run_date {r.get('as_of_run_date')} is not the date of this run "
            f"({run_from}: {run_date}; ±1 day, because as_of_run_date is the LOCAL run date and that timestamp "
            "is UTC) — the recency count runs from the run date, never an earlier run's or a source's date"
        )
    # no considered source can postdate the run (a run date before the newest source is impossible;
    # sf.compute silently skips such sources)
    newest_any = sf.compute(patient_dir, date(9999, 12, 31))
    nd = sf._parse_date(newest_any.get("latest_source_date"))
    if nd is not None and (nd - as_of).days > 1:
        errors.append(f"source_freshness: {newest_any.get('latest_source_ref')} is dated {nd}, after "
                      f"readiness.as_of_run_date {as_of} — the run date cannot precede a source it read")
    rep = sf.compute(patient_dir, as_of)
    latest, days = r.get("latest_source_date"), r.get("days_since_latest")
    if latest != rep["latest_source_date"]:
        errors.append(
            f"source_freshness: readiness.latest_source_date {latest!r} but the newest dated source is "
            f"{rep['latest_source_date']!r} ({rep['latest_source_ref']}) — run scripts/source_freshness.py"
        )
    ld = sf._parse_date(latest)
    if ld is not None and isinstance(days, int) and days != (as_of - ld).days:
        errors.append(f"source_freshness: days_since_latest {days} ≠ {(as_of - ld).days} "
                      f"({r.get('as_of_run_date')} − {latest})")
    if isinstance(days, int) and not isinstance(days, bool) and days > STALE_DAYS:
        lines = [w for w in (r.get("warnings") or []) if isinstance(w, str)]
        canonical = sf.stale_warning(latest, days) if isinstance(latest, str) else None
        # the one sentence source_freshness.py prints (D5), verbatim — a substring match let
        # 「随访间隔 136 天内无影像」 stand in for a 36-day warning
        if canonical is None or canonical not in lines:
            errors.append(f"source_freshness: newest source is {days} days old (> {STALE_DAYS}) but "
                          "readiness.warnings[] does not hold the stale-source sentence"
                          + (f" — copy the warning source_freshness.py prints verbatim: “{canonical}”" if canonical else ""))
        flags = [f for f in (r.get("review_flags") or []) if isinstance(f, dict)]
        if not any(f.get("kind") == "completeness" and f.get("severity") == "yellow" for f in flags):
            errors.append(f"source_freshness: newest source is {days} days old (> {STALE_DAYS}) but readiness has no "
                          "review flag kind completeness / severity yellow for it (phase2 §6.1 / §6.2)")


def _walk_records(obj, path="$"):
    """Yield (jsonpath, dict) for every dict carrying a provenance_layer."""
    if isinstance(obj, dict):
        if "provenance_layer" in obj:
            yield path, obj
        for k, v in obj.items():
            yield from _walk_records(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_records(v, f"{path}[{i}]")


def _walk_any_refs(obj, path="$"):
    """Yield (jsonpath, dict) for every dict carrying source_refs / source_ref (with or without a layer)."""
    if isinstance(obj, dict):
        if "source_refs" in obj or "source_ref" in obj:
            yield path, obj
        for k, v in obj.items():
            yield from _walk_any_refs(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_any_refs(v, f"{path}[{i}]")


def _record_ref_paths(rec: dict) -> list[str]:
    refs = []
    if isinstance(rec.get("source_refs"), list):
        refs += [r for r in rec["source_refs"] if isinstance(r, str)]
    if isinstance(rec.get("source_ref"), str):
        refs.append(rec["source_ref"])
    return [r.split("#", 1)[0] for r in refs if not r.startswith("conversation:")]


def gate_prior_archive_usage(patient_dir: Path, errors: list, warnings: list | None = None,
                             generation: str | None = None) -> None:
    """O-06: a record that cites a prior-archive digest carries provenance_layer prior_archive (one record, one
    layer — digest facts never share a source_reported block with this archive's originals); prior_archive
    facts cite a digest; digests never feed current status or the current time series.

    A digest is recognised by any of its three marks — the 既往档案摘录 sub-bucket, an inventory row with
    source_kind prior_archive_digest, or the `SOURCE: prior_archive_digest` header (_is_digest_sidecar) — the
    same three the Phase 2 prompt names (phase2 §4.0 / §5.9). A digest-looking sidecar with none of them is
    flagged prior_archive_digest_unrecognised on a legacy archive, and no structured record may cite it."""
    import pii_rescan
    add = _router(errors, warnings, _generation(patient_dir, generation))
    rows = _inventory_rows(patient_dir)
    digests = {rel for rel, row in rows.items() if row.get("source_kind") == "prior_archive_digest"}
    for p in _bucket_sidecars(patient_dir):
        if any(part in DIGEST_SUB_BUCKETS for part in p.parts):
            digests.add(p.relative_to(patient_dir).as_posix())
    _digest_placement(patient_dir, rows, digests, add, warnings)
    # the header mark counts as well (after the placement check, which reports a headed digest filed elsewhere)
    for p in _bucket_sidecars(patient_dir):
        head = pii_rescan.parse_header(p.read_text(encoding="utf-8", errors="replace"))
        if head.get("SOURCE", "").strip() == "prior_archive_digest":
            digests.add(p.relative_to(patient_dir).as_posix())
    unrecognised = _flag_cited_sidecars(patient_dir, PRIOR_DIGEST_UNRECOGNISED_CATEGORY) - digests
    # phase2 §4.0 precedence: a value the OLD structured files already held is kept (legacy_value_unsupported),
    # even when its only support is such a sidecar — never dropped silently; nothing NEW is taken from it.
    kept = _flag_cited_sidecars(patient_dir, LEGACY_UNSUPPORTED_CATEGORY)
    docs = {fname: _load_json_quiet(patient_dir / fname) for fname in list(STRUCTURED_FILES) + ["profile.json"]}
    for fname, doc in docs.items():
        if doc is None or fname == "readiness.json":
            continue
        for jpath, refs in ((jp, _record_ref_paths(rec)) for jp, rec in _walk_any_refs(doc)):
            hit = sorted(r for r in refs if r in unrecognised)
            if hit and hit[0] in kept:
                add(f"prior_archive: {fname} {jpath} cites {hit[0]}, a digest-looking sidecar flagged "
                    f"{PRIOR_DIGEST_UNRECOGNISED_CATEGORY} — a value the old structured files held, kept with its "
                    f"{LEGACY_UNSUPPORTED_CATEGORY} flag (phase2 §4.0); legacy_upgrade rewrites the sidecar as a marked "
                    "digest and settles the value's layer")
            elif hit:
                add(f"prior_archive: {fname} {jpath} cites {hit[0]}, a digest-looking sidecar flagged "
                    f"{PRIOR_DIGEST_UNRECOGNISED_CATEGORY} — no new fact is taken from it until legacy_upgrade rewrites "
                    "it as a marked digest; a value the old structured files already held stays, but only with a "
                    f"{LEGACY_UNSUPPORTED_CATEGORY} flag citing that sidecar (phase2 §4.0)")
        for jpath, rec in _walk_records(doc):
            refs = _record_ref_paths(rec)
            layer = rec.get("provenance_layer")
            if refs and digests and any(r in digests for r in refs) and layer != "prior_archive":
                only = all(r in digests for r in refs)
                add(f"prior_archive: {fname} {jpath} "
                    + ("is sourced only from the prior-archive digest" if only else
                       "cites the prior-archive digest next to this archive's originals")
                    + f" but provenance_layer is {layer!r} — digest facts are prior_archive (history only) and a "
                    "record has one layer: never mix digest and originals in one record (phase2 §5.9)")
            if layer == "prior_archive" and not any(r in digests for r in refs):
                add(f"prior_archive: {fname} {jpath} is provenance_layer prior_archive but cites no "
                    "prior_archive_digest source")
    # phase2 §2.3: the performance-status time series is this archive's dated statements only — a digest
    # statement (prior_archive, often with as_of null) is history and never enters longitudinal_observations.
    lo = docs.get("longitudinal_observations.json")
    for i, ob in enumerate((lo.get("observations") or []) if isinstance(lo, dict) else []):
        if not isinstance(ob, dict):
            continue
        if ob.get("provenance_layer") == "prior_archive" or any(r in digests for r in _record_ref_paths(ob)):
            add(f"prior_archive: longitudinal_observations.json observations[{i}] ({ob.get('metric')!r}) comes from "
                "the prior-archive digest — a digest statement is history only and never part of the current "
                "time series (phase2 §2.3)")
    # D8: a performance-status statement restated from the digest is prior_archive (history, never
    # the current PS). Its item-level provenance_layer is optional, so an item WITHOUT one that
    # cites the digest is not seen by the walk above — check the PS lists explicitly.
    for fname, holder in (("patient_summary.json", "demographics"), ("profile.json", "demographics")):
        doc = docs.get(fname)
        demo = doc.get(holder) if isinstance(doc, dict) else None
        items = demo.get("performance_status_verbatim") if isinstance(demo, dict) else None
        for i, item in enumerate(items if isinstance(items, list) else []):
            if not isinstance(item, dict) or "provenance_layer" in item:
                continue
            refs = _record_ref_paths(item)
            if refs and digests and all(r in digests for r in refs):
                add(f"prior_archive: {fname} {holder}.performance_status_verbatim[{i}] cites only the prior-archive "
                    "digest but carries no provenance_layer prior_archive — a digest PS statement is history, "
                    "never the current performance status")
    if not digests:
        return

    def cites_digest(rec) -> bool:
        return isinstance(rec, dict) and any(r in digests for r in _record_ref_paths(rec))

    ps = docs.get("patient_summary.json")
    if isinstance(ps, dict) and cites_digest(ps.get("current_status")):
        add("prior_archive: patient_summary.current_status cites the prior-archive digest — "
            "a digest is history only, never current status")
    prof = docs.get("profile.json")
    if isinstance(prof, dict) and isinstance(prof.get("latest_status"), dict):
        refs = prof["latest_status"].get("source_refs") or []
        if any(isinstance(x, str) and x.split("#", 1)[0] in digests for x in refs):
            add("prior_archive: profile.latest_status cites the prior-archive digest — history only")
    tx = docs.get("treatment_lines.json")
    for ep in (tx.get("episodes") or []) if isinstance(tx, dict) else []:
        if isinstance(ep, dict) and ep.get("status") == "ongoing" and cites_digest(ep):
            add(f"prior_archive: treatment episode {ep.get('episode_id')} is ongoing on the strength of "
                "the prior-archive digest — a digest never establishes current therapy")
    cm = docs.get("comorbidities.json")
    for med in (cm.get("medications") or []) if isinstance(cm, dict) else []:
        if isinstance(med, dict) and str(med.get("use_status", "")).startswith("active") and cites_digest(med):
            add(f"prior_archive: medication {med.get('name')!r} is {med.get('use_status')} on the strength "
                "of the prior-archive digest — history only")


def _in_digest_bucket(rel: str) -> bool:
    parts = rel.split("/")
    return len(parts) >= 3 and parts[0].startswith("03_") and parts[1] in DIGEST_SUB_BUCKETS


def _digest_placement(patient_dir: Path, rows: dict[str, dict], digests: set[str], add, warnings) -> None:
    """D9: a prior-archive digest is recognised by any of its three marks — inventory source_kind, sub-bucket
    (03_病程与叙事文书/既往档案摘录 | 03_clinical_notes/prior-archive-digest) or the SOURCE header — and the marks
    must agree: a digest filed outside the sub-bucket or without its inventory row is still checked as a digest
    (gate_prior_archive_usage adds the header mark), but the archive disagrees with itself about what it is.
    A digest without the pinned header is a legacy digest (WARN: a legacy upgrade re-writes it)."""
    import pii_rescan
    where = "03_病程与叙事文书/既往档案摘录 (en 03_clinical_notes/prior-archive-digest)"
    for rel, row in sorted(rows.items()):
        if row.get("source_kind") == "prior_archive_digest" and not _in_digest_bucket(rel):
            add(f"prior_archive: {rel} is a source_kind prior_archive_digest row filed outside {where}")
        elif _in_digest_bucket(rel) and row.get("source_kind") != "prior_archive_digest":
            add(f"prior_archive: {rel} sits in the prior-archive digest sub-bucket but its source_inventory "
                f"source_kind is {row.get('source_kind')!r} — only a digest (source_kind prior_archive_digest) goes there")
    headerless: list[str] = []
    for p in _bucket_sidecars(patient_dir):
        rel = p.relative_to(patient_dir).as_posix()
        src = pii_rescan.parse_header(p.read_text(encoding="utf-8", errors="replace")).get("SOURCE", "").strip()
        if src == "prior_archive_digest" and rel not in digests:
            add(f"prior_archive: {rel} is a prior-archive digest (SOURCE prior_archive_digest) filed outside {where} "
                "with no source_kind prior_archive_digest row — its header alone makes it a digest (its facts are "
                "prior_archive, history only, and are checked as such), but its three marks disagree: file it in "
                f"{where} with a source_kind prior_archive_digest inventory row (legacy_upgrade re-files it)")
        elif rel in digests and not src:
            headerless.append(rel)
        elif rel in digests and src != "prior_archive_digest":
            add(f"prior_archive: {rel} is filed as a prior-archive digest but its header SOURCE is {src!r}")
    if headerless and warnings is not None:
        warnings.append(f"prior_archive: {len(headerless)} prior-archive digest(s) carry no pinned header "
                        f"(SOURCE: prior_archive_digest) — a legacy digest: run_mode legacy_upgrade re-writes it "
                        f"({', '.join(headerless[:3])}{' …' if len(headerless) > 3 else ''})")


def gate_update_log(patient_dir: Path, errors: list, warnings: list | None = None,
                    generation: str | None = None) -> None:
    """O-09: update_log.json follows update_log.schema.json; redispatched workers are logged."""
    current = _generation(patient_dir, generation)
    path = patient_dir / UPDATE_LOG_NAME
    if not path.is_file():
        if current:
            errors.append(f"{UPDATE_LOG_NAME}: missing — the run ledger (workers, input hashes, "
                          "degradations) is required")
        return
    doc = _load_json_quiet(path)
    if doc is None:
        errors.append(f"{UPDATE_LOG_NAME}: not parseable JSON")
        return
    problems: list[str] = []
    validate_doc_schema(UPDATE_LOG_NAME, doc, "update_log.schema.json", problems)
    if problems:
        if current:
            errors.extend(problems)
            if any("relevance" in e or "case_summary_stale" in e for e in problems):
                errors.append(
                    f"{UPDATE_LOG_NAME}: `relevance` / `case_summary_stale` are retired entry fields — the "
                    "orchestrator writes no structured JSON: a Phase 2 worker records the user's 段E decisions "
                    "as its own `run_mode: relevance_disposition` entry (decisions in `note`)")
        elif warnings is not None:
            warnings.append(f"legacy archive: {UPDATE_LOG_NAME}: legacy shape ({len(problems)} "
                            "deviation(s) from update_log.schema.json v1)")
        return
    workers = _update_log_workers(patient_dir) or set()
    recs = _update_log_worker_records(patient_dir)
    degraded = {d.get("worker_id") for e in doc.get("entries") or [] for d in e.get("degradations") or []}
    for e in doc.get("entries") or []:
        for d in e.get("degradations") or []:
            src_phases = (recs.get(d.get("worker_id")) or {}).get("phases", set())
            phase1_src = any(ph.startswith("phase1") and ph != "phase1_digest" for ph in src_phases)
            for wid in d.get("redispatched_as") or []:
                if wid not in workers:
                    errors.append(f"{UPDATE_LOG_NAME}: degradation of {d.get('worker_id')} redispatched as "
                                  f"{wid!r}, which is not in any entry's workers[]")
                elif phase1_src:
                    # SKILL.md Step 4 / O-09: each unfinished file of a stopped Phase 1 worker goes to its
                    # own single-file worker (p1-<source_id>-<n>), then a stub — never one multi-file retry
                    rec = recs.get(wid) or {"phases": set(), "files": set()}
                    if len(rec["files"]) != 1 and "stub" not in rec["phases"]:
                        errors.append(f"{UPDATE_LOG_NAME}: Phase 1 worker {d.get('worker_id')} was redispatched as {wid!r} "
                                      f"with {len(rec['files'])} files — unfinished files are redispatched as single-file "
                                      "workers (one source each) or a stub worker (SKILL.md Step 4)")
        for w in e.get("workers") or []:
            if str(w.get("worker_id", "")).lower() in RESERVED_WORKER_IDS:
                errors.append(f"{UPDATE_LOG_NAME}: worker_id {w.get('worker_id')!r} is reserved for the orchestrator")
            if w.get("status") in ("timeout", "killed") and w.get("worker_id") not in degraded:
                errors.append(f"{UPDATE_LOG_NAME}: worker {w.get('worker_id')!r} ended {w.get('status')} but no "
                              "degradations[] entry records it (reason + redispatched_as)")
    partial = partial_upgrade_problem(patient_dir, doc.get("entries") or [], current)
    if partial:
        _router(errors, warnings, current)(partial)


def partial_upgrade_problem(patient_dir: Path, entries: list, current: bool) -> str | None:
    """D1 partial-upgrade trap (phase2 §4.0/§8, SKILL.md「Legacy upgrade」): SKILL.md Step 1 takes a
    schema-"1" ledger as "this archive is on the current contract" and runs incrementally from
    then on. A ledger with no full / legacy_upgrade run (FULL_RUN_MODES) next to bucket sidecars
    without the pinned header (no EXTRACTOR) means no run of this contract ever re-transcribed
    the archive — a Phase-2-only rerun wrote the ledger. On a legacy archive one such sidecar is
    enough (WARN: the next run must be legacy_upgrade); a current-contract archive with SOME
    carried-over sidecars is the gate_sidecar_headers carried-over WARN, but one in which NO
    sidecar was written under this contract cannot be current (ERROR). None = no problem."""
    import pii_rescan
    if any(isinstance(e, dict) and e.get("run_mode") in FULL_RUN_MODES for e in entries):
        return None
    sidecars = _bucket_sidecars(patient_dir)
    bare = [p for p in sidecars
            if not pii_rescan.parse_header(p.read_text(encoding="utf-8", errors="replace")).get("EXTRACTOR", "").strip()]
    if not bare or (current and len(bare) < len(sidecars)):
        return None
    return (f"{UPDATE_LOG_NAME}: the schema_version \"1\" ledger records no full / legacy_upgrade run, yet "
            f"{len(bare)}/{len(sidecars)} bucket sidecar(s) carry no pinned header (no EXTRACTOR) — the archive "
            "was never re-transcribed under this contract, and SKILL.md Step 1 would take this ledger as an "
            "upgrade and skip it: run run_mode legacy_upgrade (a Phase-2-only rerun of a legacy archive writes "
            "no v1 ledger, phase2 §8)")


SELF_REPORT_LAYERS = ("patient_reported", "caregiver_reported")
# phase2 §5.7: the marker a self-reported current regimen keeps in profile.summary.current_regimen
SELF_REPORT_REGIMEN_MARKERS = {"patient_reported": "患者自述：", "caregiver_reported": "家属自述："}


def _is_conversation_note(ref: str) -> bool:
    """A conversation record — a `conversation:` anchor, or any file under a conversation_notes/ folder (段C writes
    them into the domain buckets too, e.g. 03_病程与叙事文书/conversation_notes/x.md): the patient's / caregiver's
    words in the chat, never an original document."""
    return ref.startswith("conversation:") or "conversation_notes" in ref.split("#", 1)[0].split("/")


def _is_self_report_sidecar(patient_dir: Path, ref: str) -> bool:
    """A patient / caregiver source that is not an original: a conversation record (any conversation_notes/
    path), a 14_患者自管补充/ sidecar, or a sidecar headed SOURCE: patient_supplement."""
    rel = ref.split("#", 1)[0]
    if rel.startswith("14_") or _is_conversation_note(ref):
        return True
    try:
        import pii_rescan
        text = (patient_dir / rel).read_text(encoding="utf-8", errors="replace")
    except (OSError, ImportError):
        return False
    return pii_rescan.parse_header(text).get("SOURCE", "").strip() == "patient_supplement"


def gate_record_links(patient_dir: Path, errors: list, warnings: list | None = None,
                      generation: str | None = None) -> None:
    """O-05/O-07: conflict_group has ≥ 2 events; medication_refs resolve to medication_id; an HLA row's
    optional report_date is the typing report's own date (phase2 §5.4)."""
    add = _router(errors, warnings, _generation(patient_dir, generation))
    mol = _load_json_quiet(patient_dir / "molecular.json")
    for i, h in enumerate((mol.get("hla_typing") or []) if isinstance(mol, dict) else []):
        if not isinstance(h, dict) or h.get("report_date") is None:
            continue
        refs_h = [r for r in (h.get("source_refs") or []) if isinstance(r, str) and _DOMAIN_DIR_RE.match(r)]
        if not refs_h or all(date_binding_problem(patient_dir, r, h["report_date"]) for r in refs_h):
            add(f"molecular.json: hla_typing[{i}] report_date {h['report_date']!r} is neither the filename date of "
                "the report it cites nor printed in it — a typing date comes from that report, never from another "
                "document (null when the report states none)")
    tl = _load_json_quiet(patient_dir / "timeline.json")
    groups: dict[str, list[str]] = {}
    for e in (tl.get("events") or []) if isinstance(tl, dict) else []:
        if isinstance(e, dict) and isinstance(e.get("conflict_group"), str) and e["conflict_group"]:
            groups.setdefault(e["conflict_group"], []).append(str(e.get("event_id")))
    for g, members in sorted(groups.items()):
        if len(members) < 2:
            add(f"timeline.json: conflict_group {g!r} has only event {members[0]} — a conflict group "
                "places at least two contradicting events side by side")
    tx = _load_json_quiet(patient_dir / "treatment_lines.json")
    cm = _load_json_quiet(patient_dir / "comorbidities.json")
    med_ids = {m.get("medication_id") for m in (cm.get("medications") or [])
               if isinstance(m, dict) and isinstance(m.get("medication_id"), str) and m["medication_id"]} \
        if isinstance(cm, dict) else set()
    referenced: set[str] = set()
    for ep in (tx.get("episodes") or []) if isinstance(tx, dict) else []:
        for ref in (ep.get("medication_refs") or []) if isinstance(ep, dict) else []:
            if not isinstance(ref, str):
                add(f"treatment_lines.json: episode {ep.get('episode_id')} medication_refs item {ref!r} is not a "
                    "medication_id string")
                continue
            referenced.add(ref)
            if ref not in med_ids:
                add(f"treatment_lines.json: episode {ep.get('episode_id')} medication_refs {ref!r} is not "
                    "a comorbidities.json medications[].medication_id")
    # O-05 / B2-B3 / B7: the verbatim basis fields are the SOURCE's words (schemas/README.md 「逐字」). SMTB
    # declares a regimen ongoing (and asks continue/hold) from status + status_basis_text, so an
    # invented 「第9程」 or 「出院带药」 would flow downstream as fact: each must appear in a source the
    # record cites (a conversation: anchor resolves to conversation_notes/).
    for ep in (tx.get("episodes") or []) if isinstance(tx, dict) else []:
        if not isinstance(ep, dict) or not isinstance(ep.get("status_basis_text"), str):
            continue
        msg = text_in_any_cited_source(patient_dir, ep.get("source_refs"), ep["status_basis_text"])
        if msg:
            add(f"treatment_lines.json: episode {ep.get('episode_id')} status_basis_text {msg} — it is the "
                f"source's own wording (status_basis {ep.get('status_basis')!r})")
    for m in (cm.get("medications") or []) if isinstance(cm, dict) else []:
        if not isinstance(m, dict) or m.get("administration_setting") in (None, "unknown") \
                or not isinstance(m.get("setting_basis"), str):
            continue
        for seg in [s for s in re.split(r"[；;]", m["setting_basis"]) if s.strip()]:
            msg = text_in_any_cited_source(patient_dir, m.get("source_refs"), seg.strip())
            if msg:
                add(f"comorbidities.json: medication {m.get('medication_id') or m.get('name')!r} "
                    f"administration_setting {m.get('administration_setting')}: setting_basis {msg} — the setting "
                    "rests on the source's own heading / department / route wording")
    # profile.latest_status is the snapshot of the ONGOING episode (phase2 §5.7; SMTB facts.py
    # reads it as a treatment_line current_status row next to the episode itself): its regimen,
    # as_of and (optional) status_basis are that episode's regimen, status_as_of and status_basis
    # — as_of is null only for the undated self-report form — and no ongoing episode → null.
    # latest_status is required (patient-profile-schema.md); an absent or null block reads as {regimen: null} — the
    # same way an absent current_regimen reads as null below — so neither the snapshot check nor the
    # current_regimen equality is skipped by dropping it.
    prof = _load_json_quiet(patient_dir / "profile.json")
    latest = prof.get("latest_status") if isinstance(prof, dict) else None
    if isinstance(prof, dict) and not isinstance(latest, dict):
        add(f"profile.json: latest_status is {'null' if 'latest_status' in prof else 'missing'} — it is required: "
            "the ongoing episode's {regimen, as_of, status_basis} snapshot, or {\"regimen\": null, …} when nothing "
            "is ongoing (patient-profile-schema.md; checked below as regimen null)")
        latest = {}
    if isinstance(latest, dict) and isinstance(tx, dict) and isinstance(tx.get("episodes"), list):
        ongoing = [ep for ep in tx["episodes"] if isinstance(ep, dict) and ep.get("status") == "ongoing"]
        reg = latest.get("regimen")
        if reg in (None, ""):
            if ongoing:
                add("profile.json: latest_status.regimen is null although treatment_lines.json has ongoing "
                    f"episode(s) {', '.join(str(ep.get('episode_id')) for ep in ongoing)} — latest_status "
                    "snapshots the ongoing episode")
        else:
            same = [ep for ep in ongoing if _norm_text(str(ep.get("regimen") or "")) == _norm_text(str(reg))]
            if not same:
                add(f"profile.json: latest_status.regimen {reg!r} is not the regimen of any ongoing "
                    "treatment_lines.json episode (latest_status is that episode's snapshot, never a "
                    "separately worded current regimen)")
            else:
                if latest.get("as_of") not in {ep.get("status_as_of") for ep in same}:
                    add(f"profile.json: latest_status.as_of {latest.get('as_of')!r} ≠ status_as_of of the ongoing "
                        f"episode {same[0].get('episode_id')} ({same[0].get('status_as_of')!r})")
                # B7: status_basis says what the snapshot rests on (an imaging-request indication is not
                # an administration record); when written it is the ongoing episode's status_basis.
                basis = latest.get("status_basis")
                if basis is not None and basis not in {ep.get("status_basis") for ep in same}:
                    add(f"profile.json: latest_status.status_basis {basis!r} ≠ status_basis of the ongoing episode "
                        f"{same[0].get('episode_id')} ({same[0].get('status_basis')!r})")
                if latest.get("as_of") is None and basis != "patient_reported":
                    add("profile.json: latest_status.as_of is null — only the undated self-report form has no date, "
                        "and then latest_status.status_basis is patient_reported (copied from the episode)")
    # phase2 §5.7: profile.summary has ONE provenance_layer, so a current regimen that rests on a self-report
    # (the ongoing episode is patient_reported / caregiver_reported) keeps its source marker there — a family
    # statement never reads as a source_reported regimen.
    summ = prof.get("summary") if isinstance(prof, dict) else None
    cur_reg = summ.get("current_regimen") if isinstance(summ, dict) else None
    # phase2 §5.7 / patient-profile-schema.md: summary.current_regimen, once its source marker is stripped, IS
    # latest_status.regimen (null when there is no ongoing episode) — the same snapshot, never a separately
    # worded current regimen. Checked whatever the summary block's layer (only the marker depends on it); an
    # absent key reads as null (and an absent latest_status as regimen null, above), so dropping either while an
    # episode is ongoing is reported too.
    if isinstance(summ, dict) and isinstance(latest, dict):
        cur_bare = _norm_text(cur_reg) if isinstance(cur_reg, str) else ""
        marker_used = None
        for mark in SELF_REPORT_REGIMEN_MARKERS.values():
            if cur_bare.startswith(_norm_text(mark)):
                cur_bare, marker_used = cur_bare[len(_norm_text(mark)):], mark
                break
        snap = latest.get("regimen")
        snap_bare = _norm_text(snap) if isinstance(snap, str) else ""
        if marker_used and not cur_bare:
            add(f"profile.json: summary.current_regimen {cur_reg!r} is the marker 「{marker_used}」 alone — a marker "
                "names who said which regimen, it is not a regimen and not null: write the regimen after it, or null "
                "when there is no ongoing episode (phase2 §5.7)")
        elif cur_bare != snap_bare:
            add(f"profile.json: summary.current_regimen {cur_reg!r} "
                + (f"(without its marker 「{marker_used}」) " if marker_used else "")
                + f"≠ latest_status.regimen {snap!r} — current_regimen is latest_status.regimen, with the "
                "患者自述：/家属自述： marker when the ongoing episode is a self-report, and null when there is no "
                "ongoing episode (phase2 §5.7)")
        elif marker_used and isinstance(tx, dict):
            layer = next((k for k, v in SELF_REPORT_REGIMEN_MARKERS.items() if v == marker_used), None)
            carriers = [ep for ep in tx.get("episodes") or [] if isinstance(ep, dict) and ep.get("status") == "ongoing"
                        and _norm_text(str(ep.get("regimen") or "")) == cur_bare]
            # the marker names the speaker: 患者自述： ↔ patient_reported, 家属自述： ↔ caregiver_reported — whatever
            # the summary block's own layer (a caregiver_reported block does not make 患者自述： right)
            if carriers and not any(ep.get("provenance_layer") == layer for ep in carriers):
                ep_layer = carriers[0].get("provenance_layer")
                right = SELF_REPORT_REGIMEN_MARKERS.get(ep_layer)
                add(f"profile.json: summary.current_regimen {cur_reg!r} carries the self-report marker 「{marker_used}」 "
                    f"but the ongoing episode {carriers[0].get('episode_id')} is {ep_layer!r} — the marker says the "
                    f"regimen rests on a {layer} statement; "
                    + (f"a {ep_layer} regimen is written 「{right}<方案>」" if right else
                       "an original's regimen is written without it") + " (phase2 §5.7)")
    if isinstance(cur_reg, str) and cur_reg.strip() and isinstance(tx, dict) \
            and summ.get("provenance_layer") not in SELF_REPORT_LAYERS:
        bare = _norm_text(cur_reg)
        for mark in SELF_REPORT_REGIMEN_MARKERS.values():
            if bare.startswith(_norm_text(mark)):
                bare = bare[len(_norm_text(mark)):]
                break
        for ep in tx.get("episodes") or []:
            if not isinstance(ep, dict) or ep.get("status") != "ongoing" \
                    or ep.get("provenance_layer") not in SELF_REPORT_LAYERS \
                    or _norm_text(str(ep.get("regimen") or "")) != bare:
                continue
            mark = SELF_REPORT_REGIMEN_MARKERS[ep["provenance_layer"]]
            if not _norm_text(cur_reg).startswith(_norm_text(mark)):
                add(f"profile.json: summary.current_regimen {cur_reg!r} is the {ep['provenance_layer']} episode "
                    f"{ep.get('episode_id')} under a {summ.get('provenance_layer')!r} summary block — a self-reported "
                    f"regimen keeps its marker 「{mark}」 there (phase2 §5.7)")
    # phase2 §5.7: demographics.function_description is a clinician's own wording, quoted from an original the
    # block cites — a patient / caregiver self-description stays a self-report event, never demographics.
    ps = _load_json_quiet(patient_dir / "patient_summary.json")
    demo = ps.get("demographics") if isinstance(ps, dict) else None
    fdesc = demo.get("function_description") if isinstance(demo, dict) else None
    if isinstance(fdesc, str) and fdesc.strip():
        originals = [r for r in (demo.get("source_refs") or [])
                     if isinstance(r, str) and _DOMAIN_DIR_RE.match(r) and not _is_self_report_sidecar(patient_dir, r)]
        msg = text_in_any_cited_source(patient_dir, originals, fdesc) if originals else \
            "cites no clinician original (only conversation records / patient-supplement sources, or none)"
        if msg:
            add(f"patient_summary.json: demographics.function_description {msg} — it holds a clinician source's own "
                "function wording only; a self-description stays a patient_reported / caregiver_reported timeline "
                "event (phase2 §5.7)")
    # O-05.3: an antineoplastic order is also a treatment episode (never only a medication row)
    for m in (cm.get("medications") or []) if isinstance(cm, dict) else []:
        if not isinstance(m, dict) or m.get("order_role") != "antineoplastic":
            continue
        mid = m.get("medication_id")
        if not mid:
            add(f"comorbidities.json: antineoplastic medication {m.get('name')!r} has no medication_id — "
                "it must be linked from a treatment_lines.json episode's medication_refs")
        elif mid not in referenced:
            add(f"comorbidities.json: antineoplastic medication {mid} ({m.get('name')!r}) is not referenced by "
                "any treatment_lines.json episode medication_refs — antineoplastic orders are also written "
                "into treatment_lines")


_PS_SCALES = {"PS", "ECOG", "KPS", "Zubrod", "unlabeled"}
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROVENANCE_LAYERS = ("source_reported", "patient_reported", "caregiver_reported", "system_normalized",
                     "prior_archive")


def profile_demographics_problems(profile: dict, summary: dict | None,
                                  patient_dir: Path | None = None) -> list[str]:
    """Shape of profile.json.demographics (references/schemas/README.md: sex / age / age_as_of /
    performance_status_verbatim / provenance_layer / source_refs), each PS text bound to
    the line its source_ref cites (when patient_dir is given), and equality with
    patient_summary (authoritative)."""
    out: list[str] = []
    demo = profile.get("demographics")
    if demo is None:
        return ["profile.json has no demographics block (sex / age / age_as_of / performance_status_verbatim)"]
    if not isinstance(demo, dict):
        return ["profile.demographics must be an object"]
    if demo.get("sex") is not None and not isinstance(demo.get("sex"), str):
        out.append("profile.demographics.sex must be string or null")
    age = demo.get("age")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 130):
        out.append("profile.demographics.age must be an integer 0-130 or null")
    if age is not None and not (isinstance(demo.get("age_as_of"), str) and _ISO_DAY.match(demo["age_as_of"])):
        out.append("profile.demographics.age_as_of (YYYY-MM-DD) is required whenever age is present")
    ps = demo.get("performance_status_verbatim", [])
    if not isinstance(ps, list):
        out.append("profile.demographics.performance_status_verbatim must be an array")
        ps = []
    for i, item in enumerate(ps):
        if not isinstance(item, dict):
            out.append(f"profile.demographics.performance_status_verbatim[{i}] must be an object")
            continue
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            out.append(f"performance_status_verbatim[{i}].text must be the verbatim wording")
        if item.get("as_of") is not None and not (isinstance(item["as_of"], str) and _ISO_DAY.match(item["as_of"])):
            out.append(f"performance_status_verbatim[{i}].as_of must be YYYY-MM-DD or null")
        if item.get("scale_label") not in _PS_SCALES:
            out.append(f"performance_status_verbatim[{i}].scale_label must be one of {sorted(_PS_SCALES)}")
        if "provenance_layer" in item and item["provenance_layer"] not in PROVENANCE_LAYERS:
            out.append(f"performance_status_verbatim[{i}].provenance_layer must be one of {list(PROVENANCE_LAYERS)} "
                       f"(optional; got {item['provenance_layer']!r})")
        if not isinstance(item.get("source_ref"), str):
            out.append(f"performance_status_verbatim[{i}].source_ref must be a string anchor")
        elif patient_dir is not None and isinstance(item.get("text"), str) \
                and not item["source_ref"].startswith("conversation:"):
            msg = anchor_line_binding(patient_dir, item["source_ref"], item["text"])
            if msg:
                out.append(f"performance_status_verbatim[{i}].text is not the source wording: {msg}")
    if demo.get("provenance_layer") not in PROVENANCE_LAYERS:
        out.append(f"profile.demographics.provenance_layer must be one of {list(PROVENANCE_LAYERS)} "
                   f"(got {demo.get('provenance_layer')!r})")
    refs = demo.get("source_refs")
    if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs):
        out.append("profile.demographics.source_refs must be an array of anchors")
    elif not refs and (demo.get("sex") is not None or age is not None or ps):
        out.append("profile.demographics.source_refs is empty although sex / age / PS are filled — "
                   "every demographic value cites its source")
    if isinstance(summary, dict) and isinstance(summary.get("demographics"), dict):
        sd = summary["demographics"]
        for key in ("sex", "age", "age_as_of"):
            if key in sd and demo.get(key) != sd.get(key):
                out.append(f"profile.demographics.{key} {demo.get(key)!r} ≠ patient_summary {sd.get(key)!r} "
                           "(patient_summary is authoritative; profile is its copy)")
        if "performance_status_verbatim" in sd and ps != sd.get("performance_status_verbatim"):
            out.append("profile.demographics.performance_status_verbatim ≠ patient_summary.demographics")
    return out


def gate_profile_demographics(patient_dir: Path, errors: list, warnings: list | None = None,
                              generation: str | None = None) -> None:
    """O-08: profile.json demographics (sex / age / age_as_of / PS verbatim)."""
    add = _router(errors, warnings, _generation(patient_dir, generation))
    prof = _load_json_quiet(patient_dir / "profile.json")
    if not isinstance(prof, dict):
        return
    summary = _load_json_quiet(patient_dir / "patient_summary.json")
    for msg in profile_demographics_problems(prof, summary if isinstance(summary, dict) else None,
                                             patient_dir):
        add(f"profile_demographics: {msg}")


def gate_organize_meta(patient_dir: Path, errors: list, warnings: list | None = None,
                       generation: str | None = None) -> None:
    """organize_meta.json follows its schema and records the clean semantic PII scan (DoD 3):
    SKILL.md Step 12.5 dispatches pii-rescan-prompt.md, and Step 17 passes the clean worker's id
    to write_organize_meta.py --pii-layer1. Without it the Layer-1 scan cannot be shown to have run."""
    path = patient_dir / ORGANIZE_META_NAME
    if not path.is_file():
        return
    doc = _load_json_quiet(path)
    if doc is None:
        errors.append(f"{ORGANIZE_META_NAME}: not parseable JSON")
        return
    validate_doc_schema(ORGANIZE_META_NAME, doc, "organize_meta.schema.json", errors)
    scan = doc.get("pii_layer1_scan") if isinstance(doc, dict) else None
    if not (isinstance(scan, dict) and scan.get("clean") is True and isinstance(scan.get("worker_id"), str)):
        errors.append(f"{ORGANIZE_META_NAME}: no pii_layer1_scan — the semantic PII scan (pii-rescan-prompt.md, "
                      "SKILL.md Step 12.5) must return clean=true and its worker id be recorded with "
                      "`write_organize_meta.py <dir> --pii-layer1 <worker_id>` (DoD 3)")


# Step 17 (SKILL.md, DoD 1–6): what a finished run leaves on a current-contract archive, beyond
# what Phase 2 itself writes. Phase 2 §9 runs the validator WITHOUT --final (organize_meta.json,
# AGENTS.md and the 段D HTML are written after it); the orchestrator's terminal gate runs WITH it.
# timeline.md / case_text.md: phase2 §0 writes both on every build (§7; empty sections, never a missing file).
FINAL_REQUIRED_FILES = ("organize_meta.json", "INDEX.md", "timeline.md", "case_text.md", "review_summary.md",
                        "AGENTS.md", CASE_SUMMARY_HTML_NAME)
# runs that ingest or rewrite the archive's clinical content — each is followed by Phase 2.5
INGEST_RUN_MODES = ("full", "legacy_upgrade", "incremental", "upload_reconciliation")
# the renderer's provenance comment (render_html_template.PROVENANCE_FMT; the same pattern
# validate_case_summary_html.py reads)
_TEMPLATE_SHA_RE = re.compile(r"template_sha256:\s*([0-9a-f]{64})", re.IGNORECASE)


def html_template_sha(patient_dir: Path) -> str | None:
    """The template_sha256 provenance comment of 病情简要总结.html (the value 段D returns), else None."""
    try:
        m = _TEMPLATE_SHA_RE.search((patient_dir / CASE_SUMMARY_HTML_NAME).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return m.group(1) if m else None


def gate_final_outputs(patient_dir: Path, errors: list, warnings: list | None = None,
                       generation: str | None = None) -> None:
    """--final (SKILL.md Step 17, the terminal gate): on a current-contract archive the run's closing
    products exist — organize_meta.json, INDEX.md, timeline.md, case_text.md (phase2 §0 always writes both),
    review_summary.md (Step 9 MANDATORY), AGENTS.md and the 段D HTML, whose render data carries the
    acute_findings_sha256 stamp — ocr/ is gone or empty (a leftover sidecar is a fact that never reached the structured
    files), and Phase 2.5 left its trace: an update_log entry at or after the last ingest run lists a
    `phase2_5` worker (Step 11.5 always dispatches the recording faithfulness_patch). A legacy archive
    (a Phase-2-only pass, which writes no organize_meta.json) gets one WARN instead."""
    if not _generation(patient_dir, generation):
        if warnings is not None:
            warnings.append("final: legacy archive — the closing-product checks apply after legacy_upgrade")
        return
    for name in FINAL_REQUIRED_FILES:
        if not (patient_dir / name).is_file():
            errors.append(f"final: {name} missing — a finished run leaves it (SKILL.md Step 17 / Definition of Done)")
    render = _load_json_quiet(patient_dir / CASE_SUMMARY_DATA_NAME)
    if (patient_dir / CASE_SUMMARY_HTML_NAME).is_file() and not (
            isinstance(render, dict) and isinstance(render.get(CASE_SUMMARY_ACUTE_STAMP), str)):
        errors.append(f"final: {CASE_SUMMARY_DATA_NAME} carries no {CASE_SUMMARY_ACUTE_STAMP} — 段D step 3 stamps the "
                      "acute_findings.json it read (scripts/stamp_case_summary_sources.py); without it a later run "
                      "cannot tell a stale 段D from one that left an emergent/urgent finding out")
    ocr = patient_dir / "ocr"
    if ocr.is_dir():
        left = sorted(p.name for p in ocr.iterdir() if p.name != ".DS_Store")
        if left:
            errors.append(f"final: ocr/ still holds {len(left)} file(s) ({', '.join(left[:5])}) — a sidecar that was not "
                          "placed never reached the structured files; re-run Phase 2 before finishing")
    entries = [e for e in (_update_log_entries(patient_dir) or []) if isinstance(e, dict)]
    last_ingest = max((i for i, e in enumerate(entries) if e.get("run_mode") in INGEST_RUN_MODES), default=None)
    if last_ingest is not None and not any(
            isinstance(w, dict) and w.get("phase") == "phase2_5"
            for e in entries[last_ingest:] for w in (e.get("workers") or [])):
        errors.append("final: update_log.json records no phase2_5 worker after the last ingest run "
                      f"({entries[last_ingest].get('run_mode')} at {entries[last_ingest].get('at')}) — Phase 2.5 "
                      "(Step 11.5) must run and its worker be logged by the faithfulness_patch entry")


def _run_gate(name: str, fn, errors: list, *args, **kwargs) -> None:
    """Run one gate; a crash on malformed input (a list where a string belongs …) becomes one
    ERROR line naming the gate, and every other gate still runs and reports."""
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — any crash is a failed gate, never a lost report
        errors.append(f"{name}: crashed on malformed input — {type(exc).__name__}: {exc} "
                      "(fix the offending value's type; the other gates' findings are below)")


USAGE = ("usage: validate_structured_outputs.py <patient_dir> [--readonly] [--final]\n"
         "       validate_structured_outputs.py --generation <patient_dir>   # prints current | legacy")


def main() -> int:
    args = sys.argv[1:]
    readonly = "--readonly" in args
    want_generation = "--generation" in args
    final = "--final" in args
    args = [a for a in args if a not in ("--readonly", "--generation", "--final")]
    if len(args) != 1 or args[0].startswith("-"):
        print(USAGE, file=sys.stderr)
        return 2

    patient_dir = Path(args[0]).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    markers = generation_markers(patient_dir)
    generation = "current" if markers else "legacy"
    if want_generation:
        # SKILL.md Step 1 routes on this one predicate: current → update run (sha256 diff),
        # legacy → run_mode legacy_upgrade. Read-only; nothing else runs.
        print(generation)
        print("markers: " + ("; ".join(markers) if markers else "none"), file=sys.stderr)
        return 0

    errors: list[str] = []
    warnings: list[str] = []
    if generation == "legacy":
        warnings.append(
            "archive_generation: legacy archive (no current-contract marker: no organize_meta.json, "
            "readiness.json < 2.1, no structured file at its current version, "
            "no update_log workers[], no sidecar EXTRACTOR) — the v2.1 gates report as WARN; re-run "
            "organize to upgrade. " + LEGACY_UPGRADE_HINT
        )
    if not HAS_JSONSCHEMA:
        if generation == "current":
            # The v2.1 safety rules (linear_position → value null, flag severity/kind, treatment status
            # combinations, acute enums, the closed update_log) live in JSON Schema if/then: without
            # jsonschema they would silently pass, so the terminal gate fails closed.
            errors.append("jsonschema: not installed — `pip install 'jsonschema>=4.18'` is required for the "
                          "current-contract gate (the lightweight fallback cannot check the v2.1 schema rules)")
        else:
            warnings.append("jsonschema not installed — ran lightweight structured checks only. Install with "
                            "`pip install 'jsonschema>=4.18'` for strict schema validation.")
    g = generation
    _run_gate("structured", gate_structured, errors, patient_dir, errors, warnings, g)
    _run_gate("required_files", gate_required_current_files, errors, patient_dir, errors, warnings, g)
    _run_gate("pii_rescan", gate_pii_rescan, errors, patient_dir, errors)
    _run_gate("lab_source_shape", gate_lab_source_shape, errors, patient_dir, errors)
    _run_gate("bucket_taxonomy", gate_bucket_taxonomy, errors, patient_dir, errors, warnings, g)
    _run_gate("source_inventory", gate_source_inventory, errors, patient_dir, errors, warnings, g)
    _run_gate("input_completeness", gate_input_completeness, errors, patient_dir, errors, warnings, g)
    _run_gate("case_summary_html", gate_case_summary_html, errors, patient_dir, errors, warnings, g, final=final)
    _run_gate("agents_md", gate_agents_md, errors, patient_dir, errors, warnings, g)
    _run_gate("agents_md", gate_no_rogue_agents_md, errors, patient_dir, errors)
    _run_gate("acute_findings", gate_acute_findings, errors, patient_dir, errors, warnings, g)
    _run_gate("sidecar_header", gate_sidecar_headers, errors, patient_dir, errors, warnings, g)
    _run_gate("line_breaks", gate_sidecar_line_breaks, errors, patient_dir, errors, warnings, g)
    _run_gate("uncertainty", gate_review_flag_semantics, errors, patient_dir, errors, warnings, g)
    _run_gate("lab_pairing", gate_lab_pairing, errors, patient_dir, errors, warnings, g)
    _run_gate("page_completeness", gate_page_completeness, errors, patient_dir, errors, warnings, g)
    _run_gate("source_freshness", gate_source_freshness, errors, patient_dir, errors, warnings, g)
    _run_gate("prior_archive", gate_prior_archive_usage, errors, patient_dir, errors, warnings, g)
    _run_gate("update_log", gate_update_log, errors, patient_dir, errors, warnings, g)
    _run_gate("record_links", gate_record_links, errors, patient_dir, errors, warnings, g)
    _run_gate("profile_demographics", gate_profile_demographics, errors, patient_dir, errors, warnings, g)
    _run_gate("organize_meta", gate_organize_meta, errors, patient_dir, errors, warnings, g)
    _run_gate("ngs_completeness", gate_ngs_completeness, errors, patient_dir, warnings)
    _run_gate("update_log_freshness", gate_update_log_freshness, errors, patient_dir, warnings)
    _run_gate("untrusted_content", gate_untrusted_content, errors, patient_dir, warnings, readonly=readonly)
    if final:
        _run_gate("final", gate_final_outputs, errors, patient_dir, errors, warnings, g)

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not HAS_JSONSCHEMA:
        # legacy archive only (a current one failed closed above): say what did NOT run
        print(f"acceptance gate OK ({generation} contract, lightweight checks only — jsonschema absent, "
              f"schema rules not verified) ({patient_dir})")
        return 0
    sha = html_template_sha(patient_dir)
    print(
        f"acceptance gate OK ({generation} contract{', final' if final else ''}) — structured outputs + PII rescan + "
        f"source inventory + case-summary HTML + v2.1 gates all pass"
        + (f"; template_sha256={sha}" if sha else "") + f" ({patient_dir})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
