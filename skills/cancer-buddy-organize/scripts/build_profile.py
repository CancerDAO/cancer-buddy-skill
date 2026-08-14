#!/usr/bin/env python3
"""Build the slim profile.json deterministically from patient_summary.json.

The patient-summary model owns only ``patient_summary.json``. This script owns
``profile.json`` and performs a fixed, source-preserving projection: it copies
diagnosis/current-status fields, unions their existing source references, and
builds a neutral label from copied values. It does not derive BMI or make a
clinical inference.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PATIENT_CODE_RE = re.compile(r"^PT-[A-F0-9]+(?:_\d+)?$")
DEFAULT_LOCALE = "zh"


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _number_or_none(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _string_list(value: object) -> list[str]:
    return _strings(value)


def _union_refs(*values: object) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _strings(value):
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def _projection_provenance(*blocks: dict[str, Any]) -> str:
    values = {
        block.get("provenance_layer")
        for block in blocks
        if isinstance(block.get("source_refs"), list) and block.get("source_refs")
    }
    values.discard(None)
    return next(iter(values)) if len(values) == 1 else "system_normalized"


def _projection_verification(*blocks: dict[str, Any]) -> str:
    values = {
        block.get("verification_status")
        for block in blocks
        if isinstance(block.get("source_refs"), list) and block.get("source_refs")
    }
    if "disputed" in values:
        return "disputed"
    if values and values == {"clinician_verified"}:
        return "clinician_verified"
    return "unverified"


def _one_line(diagnosis: dict[str, Any], current: dict[str, Any]) -> str:
    parts: list[str] = []
    for label, value in (
        ("原发部位", diagnosis.get("primary")),
        ("组织学", diagnosis.get("histology")),
        ("分期原文", diagnosis.get("stage")),
        ("方案记录", current.get("regimen")),
    ):
        if isinstance(value, str) and value.strip():
            parts.append(f"{label} {value.strip()}")
    return "来源记录：" + "；".join(parts) if parts else "资料缺失"


def _locale(summary: dict[str, Any], existing: dict[str, Any] | None, override: str | None) -> str:
    candidates = [override, summary.get("locale"), (existing or {}).get("locale"), DEFAULT_LOCALE]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return DEFAULT_LOCALE


def build_profile(
    summary: dict[str, Any], *, locale_override: str | None = None, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    patient_code = summary.get("patient_code")
    if not isinstance(patient_code, str) or not PATIENT_CODE_RE.fullmatch(patient_code):
        raise ValueError(f"invalid patient_summary.patient_code: {patient_code!r}")
    generated_at = summary.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError("patient_summary.generated_at is required for deterministic profile generation")

    demographics = summary.get("demographics")
    diagnosis = summary.get("diagnosis")
    current = summary.get("current_status")
    if not isinstance(demographics, dict):
        raise ValueError("patient_summary.demographics must be an object")
    if not isinstance(diagnosis, dict):
        raise ValueError("patient_summary.diagnosis must be an object")
    if not isinstance(current, dict):
        raise ValueError("patient_summary.current_status must be an object")

    diagnosis_refs = diagnosis.get("source_refs")
    current_refs = current.get("source_refs")
    demographics_refs = demographics.get("source_refs")
    summary_refs = _union_refs(diagnosis_refs, current_refs)
    all_refs = _union_refs(diagnosis_refs, current_refs, demographics_refs)

    profile: dict[str, Any] = {
        "schema": "cancer_buddy_profile_v3",
        "patient_code": patient_code,
        "locale": _locale(summary, existing, locale_override),
        "generated_at": generated_at,
        "privacy": {
            "pii_policy": "sidecar_text_masked; raw_originals_retained_under_raw",
            "summary_minimization_policy": "purpose_and_authorization_required",
        },
        "summary": {
            "one_line_condition": _one_line(diagnosis, current),
            "primary": diagnosis.get("primary"),
            "histology": diagnosis.get("histology"),
            "stage": diagnosis.get("stage"),
            "metastasis_sites": _string_list(diagnosis.get("metastasis_sites")),
            "current_regimen": current.get("regimen"),
            "provenance_layer": _projection_provenance(diagnosis, current),
            "verification_status": _projection_verification(diagnosis, current),
            "source_refs": summary_refs,
        },
        "latest_status": {
            "regimen": current.get("regimen"),
            "response": current.get("response"),
            "ecog": current.get("ecog"),
            "as_of": current.get("as_of"),
            "provenance_layer": current.get("provenance_layer"),
            "verification_status": current.get("verification_status"),
            "source_refs": _strings(current_refs),
        },
        "source_refs": all_refs,
    }

    alias = summary.get("alias")
    if not isinstance(alias, str) or not alias.strip():
        alias = (existing or {}).get("alias")
    if isinstance(alias, str) and alias.strip():
        profile["alias"] = alias.strip()

    height = _number_or_none(demographics.get("height_cm"))
    weight = _number_or_none(demographics.get("weight_kg"))
    if height is not None or weight is not None:
        profile["anthropometrics"] = {
            "height_cm": height,
            "height_cm_as_of": demographics.get("height_cm_as_of"),
            "weight_kg": weight,
            "weight_kg_as_of": demographics.get("weight_kg_as_of"),
            # patient_summary has no source BMI field; deriving one would make
            # source_reported provenance false. Keep the schema slot explicit.
            "bmi": None,
            "provenance_layer": demographics.get("provenance_layer"),
            "verification_status": demographics.get("verification_status"),
            "source_refs": _strings(demographics_refs),
        }

    longitudinal_ref = summary.get("longitudinal_observations_ref")
    if isinstance(longitudinal_ref, str) and longitudinal_ref:
        profile["longitudinal_observations_ref"] = longitudinal_ref
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient_dir")
    parser.add_argument("--locale", help="BCP-47 locale override; otherwise preserve existing locale, then zh")
    parser.add_argument("--out", help="output path (default: <patient_dir>/profile.json)")
    args = parser.parse_args(argv)

    patient_dir = Path(args.patient_dir)
    if not patient_dir.is_dir():
        print(f"ERROR: not a directory: {patient_dir}", file=sys.stderr)
        return 2
    try:
        summary = _read_object(patient_dir / "patient_summary.json")
        patient_code = summary.get("patient_code")
        if patient_code != patient_dir.name:
            raise ValueError(
                f"patient code mismatch: directory={patient_dir.name!r}, patient_summary={patient_code!r}"
            )
        out = Path(args.out) if args.out else patient_dir / "profile.json"
        existing = _read_object(out) if out.is_file() else None
        profile = build_profile(summary, locale_override=args.locale, existing=existing)
        out.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, "output": str(out), "patient_code": profile["patient_code"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
