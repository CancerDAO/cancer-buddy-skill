#!/usr/bin/env python3
"""Verify a reference-library layer and emit the only entry list an answer may use.

Checks performed per layer:

  1. manifest/filesystem reconciliation, both directions
     - entry listed but file missing            -> entry invalid
     - file present but not listed              -> orphan (never a source)
  2. staleness / expiry
     - `date` or `version` missing or placeholder    -> entry invalid
     - `expires_at` in the past                      -> entry invalid
     - `retrieved_at` older than --max-age-days      -> entry invalid (stale)
  3. size limits: entry count and total registered bytes
  4. schema validation against library_index.schema.json
     (jsonschema when installed, built-in fallback otherwise -- see WARNINGS)
  5. L2 patient-scope gate: a `general` entry whose metadata or text content
     looks patient-identifying is reported so it can be moved to L3

Deliberately NOT implemented: content/manifest consistency sampling (e.g.
"PDF page 1 text must contain the declared publisher"). Rejected by the founder,
see `docs/prd/reference-library-and-instruction-layer.md` §5.7 -- scanned
documents have no text layer and cover pages are often a single image, so the
false-rejection rate would keep legitimate material out of the library. The real
defence is positional: L2/L3 are `user_supplied` and never settle a
time-sensitive assertion on their own.

`trust_tier` comes from the layer, never from the file. An index that declares
its own `trust_tier` fails schema validation.

Usage:
  python3 library_verify.py --patient-dir DIR --out verified_entries.json
  python3 library_verify.py --layer L1
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import library_resolve as lib  # noqa: E402

SCHEMA_PATH = SCRIPT_DIR.parent / "references" / "schemas" / "library_index.schema.json"

DEFAULT_MAX_ENTRIES = 500
DEFAULT_MAX_TOTAL_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB
DEFAULT_MAX_AGE_DAYS = 730  # two years since the user obtained the file

# Values that look filled in but carry no verifiable content. `_RE` matches the
# whole field; `_MARKER_RE` matches anywhere, and is kept narrow so that a real
# title containing e.g. "unknown primary" is not rejected.
PLACEHOLDER_RE = re.compile(
    r"(待填|待补|待确认|待定|未知|unknown|tbd|todo|n/?a|xxx+|-{2,}|\?+)", re.IGNORECASE
)
PLACEHOLDER_MARKER_RE = re.compile(r"(待填|待补|待确认|待定|<[^>]*>|\bTBD\b|\bTODO\b)", re.IGNORECASE)

# Text-ish files whose contents we are willing to sample for the L2 scope gate.
TEXT_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".html", ".htm"}
PII_SAMPLE_BYTES = 200_000

PII_PATTERNS = [
    ("id_card", re.compile(r"(?<!\d)[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")),
    ("medical_record_no", re.compile(r"(住院号|门诊号|病案号|病历号|就诊卡号|医保号)\s*[:：]?\s*\S+")),
    ("patient_name_field", re.compile(r"(患者姓名|姓\s*名|受检者)\s*[:：]\s*[一-鿿]{2,4}")),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
]


def _parse_date(value: str) -> dt.date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# schema validation
# --------------------------------------------------------------------------

def _load_schema() -> dict | None:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fallback_validate(payload: dict, schema: dict) -> list[str]:
    """Required-fields + enum + additionalProperties check without jsonschema."""
    errors: list[str] = []
    entry_schema = schema.get("$defs", {}).get("entry", {})
    required = entry_schema.get("required", [])
    allowed = set(entry_schema.get("properties", {}).keys())
    enums = {
        name: spec["enum"]
        for name, spec in entry_schema.get("properties", {}).items()
        if "enum" in spec
    }

    top_allowed = set(schema.get("properties", {}).keys())
    for key in payload:
        if key not in top_allowed:
            errors.append(f"index.json: unexpected top-level key `{key}`")
    if "entries" not in payload:
        errors.append("index.json: missing required key `entries`")

    for pos, entry in enumerate(payload.get("entries", []) or []):
        if not isinstance(entry, dict):
            errors.append(f"entries[{pos}]: not an object")
            continue
        for field in required:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"entries[{pos}]: missing or empty required field `{field}`")
        for key in entry:
            if key not in allowed:
                extra = (
                    " (trust_tier is assigned by layer position and cannot be declared)"
                    if key == "trust_tier"
                    else ""
                )
                errors.append(f"entries[{pos}]: unexpected field `{key}`{extra}")
        for field, choices in enums.items():
            if field in entry and entry[field] not in choices:
                errors.append(
                    f"entries[{pos}]: `{field}` must be one of {choices}, got {entry[field]!r}"
                )
    return errors


def validate_schema(payload: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    schema = _load_schema()
    if schema is None:
        return [], [f"schema not readable at {SCHEMA_PATH}; schema validation skipped"]

    if importlib.util.find_spec("jsonschema") is None:
        return _fallback_validate(payload, schema), [
            "jsonschema is not installed; using the built-in required/enum/"
            "additionalProperties fallback (format and pattern rules are not enforced)"
        ]

    import jsonschema  # type: ignore

    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in err.path) or "<root>"
        errors.append(f"{location}: {err.message}")
    return errors, []


# --------------------------------------------------------------------------
# scope gate
# --------------------------------------------------------------------------

def scan_patient_identifiers(entry: dict, real_path: Path | None) -> list[str]:
    hits: list[str] = []
    haystacks = [str(entry.get("title", "")), str(entry.get("notes", "")), str(entry.get("file", ""))]
    if real_path is not None and real_path.suffix.lower() in TEXT_SUFFIXES:
        try:
            haystacks.append(real_path.read_text(encoding="utf-8", errors="ignore")[:PII_SAMPLE_BYTES])
        except OSError:
            pass
    blob = "\n".join(haystacks)
    for name, pattern in PII_PATTERNS:
        if pattern.search(blob):
            hits.append(name)
    return hits


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

def verify_layer(
    layer: str,
    root: Path | None,
    *,
    max_entries: int,
    max_total_bytes: int,
    max_age_days: int,
    today: dt.date,
) -> dict:
    report: dict = {
        "layer": layer,
        "trust_tier": lib.LAYER_TRUST_TIER[layer],
        "root": str(root) if root is not None else None,
        "exists": False,
        "verified_entries": [],
        "rejected_entries": [],
        "orphan_files": [],
        "scope_violations": [],
        "errors": [],
        "warnings": [],
    }
    if root is None or not Path(root).is_dir():
        return report

    resolved = Path(root).resolve()
    report["root"] = str(resolved)
    report["exists"] = True

    index_path = resolved / lib.INDEX_FILENAME
    if not index_path.is_file():
        report["errors"].append("index.json is missing; no file in this layer can be a source")
        files, _symlinks = lib.scan_files(resolved)
        report["orphan_files"] = files
        return report
    if index_path.is_symlink():
        report["errors"].append(
            "index.json is a symbolic link; refusing to read it (the manifest must "
            "live inside the library root it describes)"
        )
        files, _symlinks = lib.scan_files(resolved)
        report["orphan_files"] = files
        return report

    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report["errors"].append(f"index.json unreadable or invalid JSON: {exc}")
        return report
    if not isinstance(payload, dict):
        report["errors"].append("index.json must be an object with an `entries` array")
        return report

    schema_errors, schema_warnings = validate_schema(payload)
    report["errors"].extend(f"schema: {msg}" for msg in schema_errors)
    report["warnings"].extend(schema_warnings)

    entries, index_errors = lib.read_index(resolved)
    report["warnings"].extend(index_errors)

    if len(entries) > max_entries:
        report["errors"].append(
            f"entry count {len(entries)} exceeds --max-entries {max_entries}"
        )
        return report

    registered: set[str] = set()
    total_bytes = 0

    for pos, entry in enumerate(entries):
        rejections: list[str] = []
        real: Path | None = None
        raw_file = entry.get("file")
        try:
            real = lib.resolve_entry_path(resolved, raw_file if isinstance(raw_file, str) else "")
        except lib.LibraryPathError as exc:
            rejections.append(str(exc))

        for field in ("version", "date", "retrieved_at", "title", "publisher", "lang"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                rejections.append(f"missing required field `{field}`")
            elif PLACEHOLDER_RE.fullmatch(value.strip()) or PLACEHOLDER_MARKER_RE.search(value):
                rejections.append(f"field `{field}` is a placeholder: {value!r}")

        if entry.get("redistribution") not in ("allowed", "restricted", "unknown"):
            rejections.append("`redistribution` must be allowed|restricted|unknown")
        if entry.get("patient_scope") not in ("general", "patient_specific"):
            rejections.append("`patient_scope` must be general|patient_specific")

        published = _parse_date(str(entry.get("date", "")))
        if published is None:
            rejections.append("`date` is not a parseable date")
        elif published > today:
            rejections.append(f"`date` {published} is in the future")

        obtained = _parse_date(str(entry.get("retrieved_at", "")))
        if obtained is None:
            rejections.append("`retrieved_at` is not a parseable date")
        else:
            age = (today - obtained).days
            if age > max_age_days:
                rejections.append(
                    f"stale: retrieved {age} days ago, limit is {max_age_days}"
                )

        expires = entry.get("expires_at")
        if isinstance(expires, str) and expires.strip():
            deadline = _parse_date(expires)
            if deadline is None:
                rejections.append("`expires_at` is not a parseable date")
            elif deadline < today:
                rejections.append(f"expired on {deadline}")

        if layer == "L1" and entry.get("redistribution") != "allowed":
            rejections.append(
                "L1 ships with the repository and accepts `redistribution: allowed` only"
            )
        if layer == "L2" and entry.get("patient_scope") != "general":
            rejections.append("L2 is cross-patient and accepts `patient_scope: general` only")

        if layer == "L2" and entry.get("patient_scope") == "general":
            hits = scan_patient_identifiers(entry, real)
            if hits:
                report["scope_violations"].append(
                    {
                        "index": pos,
                        "file": raw_file,
                        "matched": hits,
                        "action": "move this entry into the patient's L3 library (<patient_dir>/library/)",
                    }
                )
                rejections.append(
                    "patient-identifying content in a cross-patient (L2) entry: "
                    + ", ".join(hits)
                )

        if rejections:
            report["rejected_entries"].append(
                {"index": pos, "file": raw_file, "reasons": rejections}
            )
            continue

        assert real is not None
        rel = real.relative_to(resolved).as_posix()
        registered.add(rel)
        total_bytes += real.stat().st_size

        verified = dict(entry)
        verified.pop("trust_tier", None)
        verified["file"] = rel
        verified["layer"] = layer
        verified["trust_tier"] = lib.LAYER_TRUST_TIER[layer]
        verified["bytes"] = real.stat().st_size
        report["verified_entries"].append(verified)

    if total_bytes > max_total_bytes:
        report["errors"].append(
            f"registered bytes {total_bytes} exceed --max-total-bytes {max_total_bytes}"
        )
        report["verified_entries"] = []

    files, symlinks = lib.scan_files(resolved)
    report["orphan_files"] = [rel for rel in files if rel not in registered]
    if symlinks:
        report["warnings"].append(
            f"{len(symlinks)} symbolic link(s) ignored: {', '.join(symlinks[:5])}"
        )
    report["total_bytes"] = total_bytes
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--patient-dir", type=Path, default=None)
    parser.add_argument("--layer", action="append", choices=["L1", "L2", "L3"])
    parser.add_argument("--out", type=Path, default=None, help="write verified_entries.json here")
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--today", type=str, default=None, help="override today's date (tests)")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    today = _parse_date(args.today) if args.today else dt.date.today()
    if today is None:
        parser.error("--today must be an ISO date")

    order = ["L3", "L2", "L1"]
    layers = [name for name in order if not args.layer or name in args.layer]
    roots = {
        "L3": lib.l3_root(args.patient_dir),
        "L2": lib.l2_root(),
        "L1": lib.l1_root(),
    }

    reports = [
        verify_layer(
            name,
            roots[name],
            max_entries=args.max_entries,
            max_total_bytes=args.max_total_bytes,
            max_age_days=args.max_age_days,
            today=today,
        )
        for name in layers
    ]

    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "search_order": layers,
        "layers": reports,
        "verified_total": sum(len(r["verified_entries"]) for r in reports),
        "rejected_total": sum(len(r["rejected_entries"]) for r in reports),
        "orphan_total": sum(len(r["orphan_files"]) for r in reports),
        "scope_violation_total": sum(len(r["scope_violations"]) for r in reports),
        "error_total": sum(len(r["errors"]) for r in reports),
    }

    text = json.dumps(result, ensure_ascii=False, indent=args.indent)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)

    for report in reports:
        for message in report["warnings"]:
            print(f"WARN [{report['layer']}] {message}", file=sys.stderr)
        for message in report["errors"]:
            print(f"ERROR [{report['layer']}] {message}", file=sys.stderr)
        for item in report["scope_violations"]:
            print(
                f"ERROR [{report['layer']}] patient-identifying content in a general entry: "
                f"{item['file']} ({', '.join(item['matched'])}) -> {item['action']}",
                file=sys.stderr,
            )

    if result["error_total"] or result["scope_violation_total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
