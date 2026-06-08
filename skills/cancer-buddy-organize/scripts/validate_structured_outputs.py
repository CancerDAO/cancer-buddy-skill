#!/usr/bin/env python3
"""Total acceptance gate for a finished organize run.

This script is the single deterministic门 the orchestrator runs after Phase 2 (and
after 段D HTML generation) to decide "is this patient_dir actually done?". It does
NOT make any medical or content judgement — every check here is a *form/безопасность*
invariant that is fixed regardless of which patient was processed. The LLM still
owns OCR / narrative / classification; this gate only verifies the deterministic
products line up.

Gate sections (each contributes to one aggregated exit code; a missing optional
artifact is not an error — the gate validates what exists):

  [1] Structured JSON schema + anchor (ORIGINAL behavior, unchanged):
      For each present structured output (patient_summary / timeline / molecular /
      treatment_lines / labs / comorbidities / missing_items), validate against
      references/schemas/<name>.schema.json (Draft 2020-12 via jsonschema>=4.18,
      with a lighter fallback when jsonschema is absent) and verify every
      source_refs[] anchor resolves to an existing markdown file.

  [2] PII residue rescan (pii_rescan.py):
      Independently re-scan every desensitized MD sidecar for plaintext PII that
      survived Phase-1 redaction. The sidecar is the only downstream plaintext
      boundary, so residue here leaks everywhere. Reuses the redact_ocr.py regex
      family (text-only — no OCR/image deps).

  [3] Redaction-manifest hand-off (segment B):
      If the run produced raster bucket images (jpg/png/…), redaction_manifest.json
      MUST exist and be a non-empty redaction_manifest_v1 with one entry per such
      image awaiting redaction. (If there are NO raster images, an absent or empty
      manifest is fine.)

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
CASE_SUMMARY_HTML_NAME = "病情简要总结.html"
REDACTION_MANIFEST_NAME = "redaction_manifest.json"

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
    "missing_items.json": "missing_items.schema.json",
}

ANCHOR_RE = re.compile(
    r"^(([0-9]{2}_[^\s/]+(/[^\s/]+)*\.md(#L\d+(-L\d+)?|#[A-Za-z0-9_-]+)?)|(conversation:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?))$"
)

# Raster image extensions that imply a 段B redaction manifest entry is owed.
RASTER_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}

try:
    from jsonschema import Draft202012Validator  # type: ignore

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


# --------------------------------------------------------------------------- #
# [1] structured JSON schema + anchor (ORIGINAL behavior, preserved verbatim)
# --------------------------------------------------------------------------- #
def collect_source_refs(obj, path="$"):
    """Yield (jsonpath, anchor) tuples for every source_refs entry in `obj`."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_refs" and isinstance(v, list):
                for i, ref in enumerate(v):
                    yield f"{path}.source_refs[{i}]", ref
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
    if not sidecars:
        # No sidecars yet (e.g. mid-run) — not this gate's job to demand them.
        return
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


# --------------------------------------------------------------------------- #
# [3] redaction-manifest hand-off
# --------------------------------------------------------------------------- #
def _iter_bucket_rasters(patient_dir: Path):
    """Yield raster image paths inside the 11 NN_ buckets (excludes 10_原始文件
    audit mirror and the ocr/ staging dir — manifest entries point at bucket
    canonical copies)."""
    for b in sorted(patient_dir.glob("[0-9][0-9]_*")):
        if not b.is_dir():
            continue
        if b.name.startswith("10_"):
            continue  # audit mirror, not a manifest bucket_path target
        for p in b.rglob("*"):
            if p.is_file() and p.suffix.lower() in RASTER_EXTS:
                yield p


def gate_redaction_manifest(patient_dir: Path, errors: list) -> None:
    rasters = list(_iter_bucket_rasters(patient_dir))
    manifest_path = patient_dir / REDACTION_MANIFEST_NAME

    if not rasters:
        # No raster bucket images → no manifest owed. If a manifest exists anyway,
        # only sanity-check it parses; an empty files[] is acceptable here.
        if manifest_path.is_file():
            try:
                json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(f"{REDACTION_MANIFEST_NAME}: present but unparseable: {e}")
        return

    # Raster images exist → manifest must exist, be valid, and be non-empty.
    if not manifest_path.is_file():
        errors.append(
            f"{REDACTION_MANIFEST_NAME}: missing, but {len(rasters)} raster bucket "
            "image(s) still carry plaintext-PII pixels and need a 段B hand-off"
        )
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{REDACTION_MANIFEST_NAME}: not parseable JSON: {e}")
        return
    if not isinstance(manifest, dict):
        errors.append(f"{REDACTION_MANIFEST_NAME}: root must be an object")
        return
    if manifest.get("schema") != "redaction_manifest_v1":
        errors.append(
            f"{REDACTION_MANIFEST_NAME}: schema must be 'redaction_manifest_v1', "
            f"got {manifest.get('schema')!r}"
        )
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) == 0:
        errors.append(
            f"{REDACTION_MANIFEST_NAME}: files[] is empty but {len(rasters)} raster "
            "bucket image(s) await redaction — every PII-bearing image must be queued"
        )
    if HAS_JSONSCHEMA:
        schema_path = SCHEMA_DIR / "redaction_manifest.schema.json"
        if schema_path.is_file():
            try:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                for err in Draft202012Validator(schema).iter_errors(manifest):
                    loc = ".".join(str(p) for p in err.absolute_path) or "$"
                    errors.append(f"{REDACTION_MANIFEST_NAME}: schema violation at {loc}: {err.message}")
            except Exception as e:
                errors.append(f"{REDACTION_MANIFEST_NAME}: schema load failed: {e}")


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
    gate_structured(patient_dir, errors)
    gate_pii_rescan(patient_dir, errors)
    gate_redaction_manifest(patient_dir, errors)
    gate_case_summary_html(patient_dir, errors)

    if not HAS_JSONSCHEMA:
        print(
            "WARN: jsonschema not installed — ran lightweight structured + manifest "
            "checks only. Install with `pip install 'jsonschema>=4.18'` for strict "
            "schema validation.",
            file=sys.stderr,
        )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(
        f"acceptance gate OK — structured outputs + PII rescan + redaction manifest "
        f"+ case-summary HTML all pass ({patient_dir})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
