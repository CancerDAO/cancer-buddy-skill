#!/usr/bin/env python3
"""Create a purpose-limited export from an organized patient directory.

This helper is not an authorization system and does not prove anonymity. The
calling host must authenticate the actor, verify authority, obtain the patient's
scoped confirmation, enforce expiry/revocation, and append its own audit event.

The exporter:
  * requires an explicit allowlist (`--include`) rather than copying the archive;
  * refuses `raw/`, build intermediates, identity maps, and version history;
  * runs the structural acceptance gate before copying;
  * writes a manifest describing the declared recipient, purpose, expiry,
    authorization reference, and selected paths.

Usage:
  python3 export_share.py PATIENT_DIR --out DEST \
    --include profile.json --include 04_诊断与分期/病理报告/report.md \
    --recipient "receiving-center" --purpose "second-opinion" \
    --expires-at 2026-08-01T00:00:00Z --authorization-ref consent-123
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

FORBIDDEN_TOPLEVEL = {
    "raw",
    "ocr",
    "case_summary_versions",
    ".case_summary_data.json",
    ".visit_prep_data.json",
    ".rename_plan.json",
    ".phase1_sources.json",
    ".identity_denylist.json",
    "alias_map.json",
}
FORBIDDEN_ANY_DEPTH = {".DS_Store", "_FILENAME_MAPPING.md"}


def _run_acceptance_gate(patient_dir: Path) -> bool:
    try:
        import validate_structured_outputs as gate
    except Exception:
        gate = None

    if gate is not None and hasattr(gate, "main"):
        saved_argv = sys.argv
        try:
            sys.argv = ["validate_structured_outputs.py", str(patient_dir)]
            return gate.main() == 0
        finally:
            sys.argv = saved_argv

    import subprocess

    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_structured_outputs.py"), str(patient_dir)]
    ).returncode == 0


def _parse_expiry(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--expires-at must be ISO-8601") from exc
    now = dt.datetime.now(dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    if parsed <= now:
        raise argparse.ArgumentTypeError("--expires-at must be in the future")
    return value


def _resolve_includes(patient_dir: Path, requested: list[str]) -> list[tuple[Path, Path]]:
    selected: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for raw_rel in requested:
        rel = Path(raw_rel)
        if rel.is_absolute() or rel == Path(".") or ".." in rel.parts:
            raise ValueError(f"unsafe include path: {raw_rel}")
        if not rel.parts or rel.parts[0] in FORBIDDEN_TOPLEVEL:
            raise ValueError(f"forbidden export path: {raw_rel}")
        if any(part in FORBIDDEN_ANY_DEPTH for part in rel.parts):
            raise ValueError(f"forbidden export path: {raw_rel}")

        candidate = patient_dir / rel
        if candidate.is_symlink():
            raise ValueError(f"symbolic links are not exportable: {raw_rel}")
        # A HARD link is not a symlink and resolve() does not follow it, so the
        # realpath boundary check below cannot see it. Without this,
        # `ln raw/secret.txt 14_.../x.txt` exports a raw original while the
        # manifest still claims raw_originals_included=false — the one real
        # mechanical gate making a promise it did not keep.
        if candidate.is_file() and candidate.stat().st_nlink > 1:
            raise ValueError(f"hard-linked files are not exportable: {raw_rel}")
        src = candidate.resolve()
        try:
            resolved_rel = src.relative_to(patient_dir)
        except ValueError as exc:
            raise ValueError(f"include escapes patient directory: {raw_rel}") from exc
        if not resolved_rel.parts or resolved_rel.parts[0] in FORBIDDEN_TOPLEVEL:
            raise ValueError(f"include resolves to protected path: {raw_rel}")
        if not src.exists():
            raise ValueError(f"include does not exist: {raw_rel}")
        if not src.is_file():
            raise ValueError(f"include must name one regular file: {raw_rel}")
        if src in seen:
            continue
        seen.add(src)
        selected.append((rel, src))

    return selected


def export_share(
    patient_dir: Path,
    dest_dir: Path,
    includes: list[str],
    *,
    recipient: str,
    purpose: str,
    expires_at: str,
    authorization_ref: str,
) -> int:
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2
    if dest_dir.exists():
        print(f"ERROR: destination already exists: {dest_dir}", file=sys.stderr)
        return 1
    if dest_dir == patient_dir or dest_dir.is_relative_to(patient_dir):
        print("ERROR: export destination must be outside the patient directory", file=sys.stderr)
        return 2
    if not all(value.strip() for value in (recipient, purpose, authorization_ref, expires_at)):
        print(
            "ERROR: recipient, purpose, authorization-ref and expires-at must be non-empty",
            file=sys.stderr,
        )
        return 2
    # The CLI parses/validates --expires-at, but the library entrypoint is what the
    # unit tests (and any programmatic caller) use — re-validate here so a future
    # expiry can never be skipped by calling export_share() directly.
    try:
        _parse_expiry(expires_at)
    except argparse.ArgumentTypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        selected = _resolve_includes(patient_dir, includes)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not selected:
        print("ERROR: at least one permitted --include is required", file=sys.stderr)
        return 2

    print(f"[export_share] running structural acceptance gate on {patient_dir} ...")
    if not _run_acceptance_gate(patient_dir):
        print("ERROR: acceptance gate failed; nothing exported", file=sys.stderr)
        return 1

    try:
        dest_dir.mkdir(parents=True, exist_ok=False)
        for rel, src in selected:
            dst = dest_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        manifest = {
            "schema": "cancer_buddy_purpose_limited_export_v1",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "recipient": recipient,
            "purpose": purpose,
            "expires_at": expires_at,
            "authorization_ref": authorization_ref,
            "included_paths": [rel.as_posix() for rel, _ in selected],
            "raw_originals_included": False,
            "notice": (
                "This is a purpose-limited, explicitly selected export. It may still contain direct "
                "or indirect identifiers and is not guaranteed de-identified or anonymous. The host "
                "must enforce authorization, expiry, revocation, and audit."
            ),
        }
        (dest_dir / "_SHARE_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print(f"ERROR: export failed: {exc}", file=sys.stderr)
        shutil.rmtree(dest_dir, ignore_errors=True)
        return 1

    print(f"[export_share] purpose-limited export written to: {dest_dir}")
    for rel, _ in selected:
        print(f"  + {rel.as_posix()}")
    print("  - raw/ and protected provenance/build files were not eligible")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a purpose-limited patient-record export")
    parser.add_argument("patient_dir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--include", action="append", required=True, help="relative path; repeatable")
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--expires-at", required=True, type=_parse_expiry)
    parser.add_argument("--authorization-ref", required=True)
    args = parser.parse_args()

    return export_share(
        Path(args.patient_dir).resolve(),
        Path(args.out).resolve(),
        args.include,
        recipient=args.recipient,
        purpose=args.purpose,
        expires_at=args.expires_at,
        authorization_ref=args.authorization_ref,
    )


if __name__ == "__main__":
    sys.exit(main())
