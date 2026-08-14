#!/usr/bin/env python3
"""Small helpers for the stable-ID high-risk review index.

The v2 file is keyed by a content ID (``file_id`` when available, otherwise the
lite profile's 1:1 ``source_id``).  ``sidecar_path`` is audit metadata only: a
review must continue to resolve after the sidecar moves from ``ocr/`` into its
final bucket.
"""

from __future__ import annotations

import json
from pathlib import Path


FULL_PASS = "passed_independent_reread"
NEEDS_REVIEW = "needs_human_review"
NOT_APPLICABLE = "not_applicable"


def load_review_records(path: Path) -> dict[str, dict]:
    """Load v2 records, returning an empty index for absent/malformed input.

    A narrow v1 reader is kept for existing archives and conformance fixtures.
    New writes must use ``high_risk_review_v2`` and stable IDs.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}

    sources = data.get("sources")
    if data.get("schema") == "high_risk_review_v2" and isinstance(sources, dict):
        return {str(key): value for key, value in sources.items() if isinstance(value, dict)}

    # Read-only compatibility for v1 path-keyed value overrides.  These records
    # deliberately cannot confer a file-level full pass because v1 never proved
    # that every high-risk field was covered.
    values = data.get("values")
    if data.get("schema") == "high_risk_review_v1" and isinstance(values, dict):
        return {
            str(path_key): {
                "sidecar_path": str(path_key),
                "status": NEEDS_REVIEW,
                "values": value_map,
                "legacy_path_key": True,
            }
            for path_key, value_map in values.items()
            if isinstance(value_map, dict)
        }
    return {}


def find_review_record(
    records: dict[str, dict], file_id: str, source_id: str, sidecar_path: str | None = None
) -> dict | None:
    """Resolve by stable ID; use a path only for read-only v1 compatibility."""
    def matches(record: dict) -> bool:
        if record.get("legacy_path_key"):
            return False
        record_source = str(record.get("source_id") or "")
        record_file = str(record.get("file_id") or "")
        return (record_source == source_id
                and (not record_file or record_file == file_id))

    for stable_id in (file_id, source_id):
        record = records.get(stable_id)
        if isinstance(record, dict) and matches(record):
            return record

    # During a file_id rollout, accept a v2 record keyed by file_id but carrying
    # the matching source_id.  This keeps the lookup stable without path joins.
    for record in records.values():
        if not isinstance(record, dict) or not matches(record):
            continue
        return record

    if sidecar_path:
        legacy = records.get(sidecar_path)
        if isinstance(legacy, dict) and legacy.get("legacy_path_key"):
            return legacy
    return None


def inventory_review_status(record: dict | None) -> str:
    """Map only an explicit v2 document-level status into the inventory.

    ``not_applicable`` means the deterministic high-risk filter found no field
    that required an independent reread.  A missing/partial/legacy record stays
    fail-closed as ``needs_human_review``.
    """
    if isinstance(record, dict) and not record.get("legacy_path_key"):
        if record.get("status") == FULL_PASS:
            return FULL_PASS
        if record.get("status") == NOT_APPLICABLE:
            return NOT_APPLICABLE
    return NEEDS_REVIEW


def verified_values(record: dict | None) -> dict:
    values = record.get("values") if isinstance(record, dict) else None
    return values if isinstance(values, dict) else {}
