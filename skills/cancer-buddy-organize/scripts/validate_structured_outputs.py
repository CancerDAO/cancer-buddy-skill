#!/usr/bin/env python3
"""Validate the structured-JSON outputs produced by Phase 2 synthesis.

Targets:
  patient_summary.json
  timeline.json
  molecular.json
  treatment_lines.json
  labs.json
  comorbidities.json
  missing_items.json

For each present file, validates against references/schemas/<name>.schema.json
(Draft 2020-12, via jsonschema>=4.18). Also verifies every source_refs[] anchor
resolves to an existing markdown file under <patient_dir>/.

If `jsonschema` is not installed, falls back to a lighter check: JSON parses,
required top-level keys present, source_refs entries match the anchor regex,
anchors resolve.

Usage:
    python3 scripts/validate_structured_outputs.py <patient_dir>

Exit codes:
    0  — all present files valid (missing files are not errors)
    1  — at least one validation failure
    2  — bad invocation
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "references" / "schemas"

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

try:
    from jsonschema import Draft202012Validator  # type: ignore

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


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


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_structured_outputs.py <patient_dir>", file=sys.stderr)
        return 2

    patient_dir = Path(sys.argv[1]).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    errors: list[str] = []
    for fname, schema_name in STRUCTURED_FILES.items():
        validate_one(patient_dir, fname, schema_name, errors)

    if not HAS_JSONSCHEMA:
        print(
            "WARN: jsonschema not installed — ran lightweight checks only. "
            "Install with `pip install 'jsonschema>=4.18'` for strict validation.",
            file=sys.stderr,
        )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"structured outputs OK (validated against {SCHEMA_DIR})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
