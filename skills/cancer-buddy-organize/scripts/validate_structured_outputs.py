#!/usr/bin/env python3
"""Total acceptance gate for a finished organize run.

This script is the single deterministic门 the orchestrator runs after Phase 2 (and
after 段D HTML generation) to decide "is this patient_dir actually done?". It does
NOT make any medical or content judgement — every check here is a *form/безопасность*
invariant that is fixed regardless of which patient was processed. The LLM still
owns ingestion / narrative / classification; this gate only verifies the deterministic
products line up.

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

  [2b] Numeric integrity (gate_numeric_integrity) — deterministic, no medical
      judgement: labs flag ↔ reference_range consistency (an out-of-range value
      with flag=null is blocked) + dropped-abnormal (a cited sidecar abnormal row
      whose value is absent from labs.json is blocked). Semantic faithfulness
      (column-shift etc.) is the separate Phase-2.5 faithfulness sub-skill's job.

  [3] Source inventory:
      source_inventory.json MUST exist and every content unit must have a
      text-masked MD sidecar plus a raw_path back to its verbatim original in raw/.
      Originals in raw/ are kept verbatim and are never pixel-redacted — there is no
      image-level source-redaction gate (the former segment B is removed). Sources
      cited by formal outputs must be persist:true with a co-located .md sidecar
      in its bucket (the original itself lives once in raw/, never copied into a bucket).

  [3b] Bucket-taxonomy enforcement (gate_bucket_taxonomy, CB-P0-1) —
      deterministic, no medical judgement: every top-level `NN_` domain dir and
      every typed sub-bucket one level down MUST be a pinned slug (zh OR en) from
      references/bucket_taxonomy.json (mirror of bucket-taxonomy.md §1.1/§1.1a).
      Non-pinned dirs (a classifier echoing an incoming source-folder name, an
      off-taxonomy domain) are collected as violations and FAIL, each printed
      with the pinned slug expected for its NN prefix.

  [3c] NGS completeness floor (gate_ngs_completeness, CB-P0-2) — deterministic
      WARN (never a hard FAIL, so a report legitimately lacking a germline/PGx
      chapter is not false-blocked): if an NGS source exists but molecular.json's
      variants / germline / pharmacogenomics arrays are empty, warn that the
      report may have been collapsed to its front-page P/LP summary.

  [4] Case-summary HTML shape (validate_case_summary_html.py):
      If 病情简要总结.html exists, it must pass the shape+provenance invariants
      against references/templates/case-summary.template.html — including the
      template_sha provenance proving it was machine-rendered (not hand-written).

Usage:
    python3 scripts/validate_structured_outputs.py <patient_dir>

Exit codes:
    0  — all present artifacts pass every gate (missing optional artifacts are OK)
    1  — at least one gate failure
    2  — bad invocation
"""
from __future__ import annotations

import json
import os
import re
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
# The renderer (SKILL.md Step 12 `--out`) writes this exact name, so this gate's
# literal stays in lock-step with the producer — do not localize one without the other.
CASE_SUMMARY_HTML_NAME = "病情简要总结.html"
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


def validate_one(patient_dir: Path, fname: str, schema_name: str, errors: list):
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


def validate_doc_schema(fname: str, data, schema_name: str, errors: list) -> None:
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
        for err in Draft202012Validator(schema).iter_errors(data):
            loc = ".".join(str(p) for p in err.absolute_path) or "$"
            errors.append(f"{fname}: schema violation at {loc}: {err.message}")
    except Exception as e:
        errors.append(f"{fname}: schema load failed for {schema_name}: {e}")


def gate_structured(patient_dir: Path, errors: list) -> None:
    for fname, schema_name in STRUCTURED_FILES.items():
        validate_one(patient_dir, fname, schema_name, errors)


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
            errors.append(f"pii_rescan(delivered): {name} {loc} [{pii_type}] {snippet!r}")
    if delivered_total:
        errors.append(
            f"pii_rescan(delivered): {delivered_total} PII leak(s) in shipped index/"
            "provenance/HTML artifacts — relativize paths / strip name-bearing basenames / "
            "coarse-grain the HTML so no identity, account, or absolute local path ships"
        )


# --------------------------------------------------------------------------- #
# [2b] numeric integrity (US-002) — deterministic, NO medical judgement
#
# This gate makes ZERO clinical decisions: it never invents a threshold, never
# carries a disease/drug keyword table. It only checks two FORM invariants that
# are true regardless of patient:
#   (a) flag ↔ reference_range consistency: a numeric lab value that sits outside
#       its OWN stated reference_range must carry the matching H/L flag. An
#       out-of-range value with flag=null is "an abnormal value silently marked
#       normal" — the column-shift / mis-extraction failure mode (a falsely
#       reassuring tumor-marker downtrend). Block.
#   (b) dropped-abnormal: a cited sidecar table row that carries an abnormal
#       marker (↑/↓/H/L) for an analyte symbol that labs.json tracks, whose
#       number is absent from that panel's values[], is a dropped abnormal value.
#       Conservative (exact uppercase analyte-symbol match) to avoid false blocks
#       on garbled OCR; semantic coverage is the US-003 faithfulness sub-skill's job.
# --------------------------------------------------------------------------- #
_RANGE_BAND = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–—~～]\s*([0-9]+(?:\.[0-9]+)?)\s*$")
_RANGE_LE = re.compile(r"^\s*[<≤]\s*([0-9]+(?:\.[0-9]+)?)\s*$")
_RANGE_GE = re.compile(r"^\s*[>≥]\s*([0-9]+(?:\.[0-9]+)?)\s*$")
_EPS = 1e-9


def _parse_range(rng):
    """Return (low, high) floats (or None for an open side); None if unparseable."""
    if not isinstance(rng, str):
        return None
    m = _RANGE_BAND.match(rng)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    m = _RANGE_LE.match(rng)
    if m:
        return (None, float(m.group(1)))
    m = _RANGE_GE.match(rng)
    if m:
        return (float(m.group(1)), None)
    return None


def gate_numeric_integrity(patient_dir: Path, errors: list) -> None:
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

    # (a) flag ↔ reference_range
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        analyte = panel.get("analyte", "<?>")
        band = _parse_range(panel.get("reference_range"))
        if not band:
            continue
        low, high = band
        for v in panel.get("values", []) or []:
            if not isinstance(v, dict):
                continue
            val = v.get("value")
            if not isinstance(val, (int, float)):
                continue  # string/null values carry no numeric invariant
            flag = v.get("flag")
            date = v.get("date", "?")
            if high is not None and val > high + _EPS and flag not in ("H", "HH"):
                errors.append(
                    f"numeric_integrity: labs '{analyte}' {date} value {val} > reference "
                    f"high {high} but flag={flag!r} (abnormal value silently marked normal)"
                )
            if low is not None and val < low - _EPS and flag not in ("L", "LL"):
                errors.append(
                    f"numeric_integrity: labs '{analyte}' {date} value {val} < reference "
                    f"low {low} but flag={flag!r} (abnormal value silently marked normal)"
                )

    # (b) dropped-abnormal (conservative) — scan each cited sidecar for abnormal
    # rows whose analyte symbol labs.json tracks but whose number is missing.
    symbol_re = re.compile(r"\b([A-Z][A-Z0-9]{1,8}(?:-[0-9]{1,3})?)\b")
    abnormal_marker = re.compile(r"[↑↓]|\bH\b|\bL\b|\bHH\b|\bLL\b")
    num_re = re.compile(r"(?<![\d.])([0-9]+(?:\.[0-9]+)?)(?![\d.])")
    # index: symbol -> set of numeric values present in labs.json for that symbol
    present: dict[str, set[float]] = {}
    cited: set[str] = set()
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        for sym in symbol_re.findall((panel.get("analyte") or "").upper()):
            present.setdefault(sym, set())
            for v in panel.get("values", []) or []:
                if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
                    present[sym].add(float(v["value"]))
                for r in (v.get("source_refs") or []) if isinstance(v, dict) else []:
                    rel = _anchor_sidecar_path(r)
                    if rel:
                        cited.add(rel)
    if not present:
        return
    for rel in sorted(cited):
        sc = patient_dir / rel
        if not sc.is_file():
            continue
        try:
            for ln, line in enumerate(sc.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not abnormal_marker.search(line):
                    continue
                syms = [s for s in symbol_re.findall(line) if s in present]
                if not syms:
                    continue
                nums = [float(x) for x in num_re.findall(line)]
                for sym in syms:
                    missing = [n for n in nums if n not in present[sym] and n > 0]
                    # require the number to look like a result (not a tiny index/row id)
                    missing = [n for n in missing if n >= 1.0]
                    if missing:
                        errors.append(
                            f"numeric_integrity: dropped-abnormal — sidecar {rel} L{ln} shows "
                            f"abnormal '{sym}' with value(s) {missing} absent from labs.json "
                            f"panel for {sym}"
                        )
                        break
        except Exception:
            continue


# --------------------------------------------------------------------------- #
# [3] source inventory (raw/ deep-link; originals kept verbatim)
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

        # raw_path must deep-link back to the verbatim original under raw/.
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
# [3b] bucket-taxonomy enforcement (CB-P0-1) — deterministic, NO medical
# judgement. The Phase-2 classifier is instructed to re-file every source onto
# the pinned v3 taxonomy (bucket-taxonomy.md §1.1 / §1.1a) and to NEVER echo an
# incoming source-folder name. Real runs still drifted (patient 023 echoed
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
    for s in tax.get("universal_fallback_sub_buckets", []):
        fallback_subs.update((s["zh"], s["en"]))

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
                    f"'{nn}_' is not a pinned domain number — valid domains are 01_..14_ "
                    "(see bucket_taxonomy.json); re-file its contents onto the correct "
                    "clinical domain"
                )
            errors.append(
                f"bucket_taxonomy: top-level dir '{name}' is not a pinned domain slug; {expect}"
            )


# --------------------------------------------------------------------------- #
# [3c] NGS completeness floor (CB-P0-2) — deterministic WARN, NO medical
# judgement. NGS/genomic PDFs were being summarized down to their front-page
# P/LP list, dropping the full somatic variant table, the germline VUS section,
# and the pharmacogenomics chapter (DPYD/UGT1A1/…). If an NGS source exists
# (a sidecar under 06_分子与组学/NGS报告 or an NGS entry in source_inventory.json)
# but molecular.json's variants / germline / pharmacogenomics arrays are empty,
# that is the "collapsed to the summary" failure mode. This is a WARN (not a
# hard FAIL) because a report can legitimately lack a germline or PGx chapter —
# a FAIL would false-block those archives. WARNs are printed but do not change
# the exit code.
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
            "full variant table (one row/variant + VAF), the germline section (INCLUDING "
            "VUS), and the pharmacogenomics chapter (DPYD/UGT1A1/…) were transcribed, not "
            "collapsed to the report's front-page P/LP summary"
        )


# --------------------------------------------------------------------------- #
# [3d] update_log edit-trail freshness (CB-P2-1) — deterministic WARN, NO
# medical judgement. update_log.json is written ONLY by the Phase-2 LLM step; a
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
    if profile_mtime > update_log_mtime + _EPS:
        warnings.append(
            "update_log_freshness: profile.json edited outside the organize flow "
            "— no changelog entry; re-run organize or append an update_log entry."
        )


# --------------------------------------------------------------------------- #
# [4] case-summary HTML shape + provenance
# --------------------------------------------------------------------------- #
def gate_case_summary_html(patient_dir: Path, errors: list) -> None:
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
def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_structured_outputs.py <patient_dir>", file=sys.stderr)
        return 2

    patient_dir = Path(sys.argv[1]).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    gate_structured(patient_dir, errors)
    gate_pii_rescan(patient_dir, errors)
    gate_numeric_integrity(patient_dir, errors)
    gate_bucket_taxonomy(patient_dir, errors)
    gate_source_inventory(patient_dir, errors)
    gate_case_summary_html(patient_dir, errors)
    gate_ngs_completeness(patient_dir, warnings)
    gate_update_log_freshness(patient_dir, warnings)

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if not HAS_JSONSCHEMA:
        print(
            "WARN: jsonschema not installed — ran lightweight structured checks only. "
            "Install with `pip install 'jsonschema>=4.18'` for strict "
            "schema validation.",
            file=sys.stderr,
        )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(
        f"acceptance gate OK — structured outputs + PII rescan + source inventory "
        f"+ case-summary HTML all pass ({patient_dir})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
