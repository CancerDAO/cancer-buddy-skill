#!/usr/bin/env python3
"""Resolve the three reference-library layers and report what is registered.

Layers (see `references/reference-library.md`):

  L3  <patient_dir>/library/        patient-specific, user supplied
  L2  $CANCER_BUDDY_GUIDELINES or ~/CancerDAO/library/   cross-patient, user supplied
  L1  <skill>/references/library/   product-curated structured fact lists

This script only resolves roots, reads `index.json`, and enforces the path
boundary. It does not read entry contents, does not rank, and does not decide
what an answer may rely on -- that is `library_verify.py` plus the presentation
rules in `references/reference-library.md`.

`trust_tier` is assigned by LAYER POSITION here and nowhere else. An index file
cannot declare its own tier; the schema forbids the key and this module never
reads one.

The path-boundary logic (`resolve_entry_path`) is lifted from the existing
implementation in `export_share.py:82-110` (reject absolute paths, `.`, `..`,
symlinks, resolved paths that escape the root, non-regular files) so both
call sites enforce the same rule instead of two divergent ones.

Usage:
  python3 library_resolve.py [--patient-dir DIR] [--indent 2]
  python3 library_resolve.py --layer L2      # restrict to one layer
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

INDEX_FILENAME = "index.json"

# Assigned by position, never by self-declaration.
LAYER_TRUST_TIER = {"L1": "curated", "L2": "user_supplied", "L3": "user_supplied"}

DEFAULT_L2_ROOT = "~/CancerDAO/library"
L2_ENV_VAR = "CANCER_BUDDY_GUIDELINES"
L1_ENV_VAR = "CANCER_BUDDY_L1_LIBRARY"

CANONICAL_CATEGORIES = ("guidelines", "literature", "education", "datasets", "other")

# Bookkeeping files that live in a library root but are never library entries.
HOUSEKEEPING_NAMES = {
    INDEX_FILENAME,
    "update_log.json",
    "verified_entries.json",
    "README.md",
}
FORBIDDEN_ANY_DEPTH = {".DS_Store", "_FILENAME_MAPPING.md"}


class LibraryPathError(ValueError):
    """An index entry names a path that is not safely inside its library root."""


def resolve_entry_path(root: Path, raw_rel: str) -> Path:
    """Return the real path of one index entry, or raise LibraryPathError.

    Mirrors `export_share.py:82-110`.
    """
    if not isinstance(raw_rel, str) or not raw_rel.strip():
        raise LibraryPathError("entry `file` must be a non-empty string")

    rel = Path(raw_rel)
    if rel.is_absolute() or rel == Path(".") or ".." in rel.parts:
        raise LibraryPathError(f"unsafe library path: {raw_rel}")
    if not rel.parts:
        raise LibraryPathError(f"unsafe library path: {raw_rel}")
    if any(part in FORBIDDEN_ANY_DEPTH for part in rel.parts):
        raise LibraryPathError(f"forbidden library path: {raw_rel}")
    if rel.name in HOUSEKEEPING_NAMES:
        raise LibraryPathError(f"housekeeping file cannot be an entry: {raw_rel}")

    root = root.resolve()
    candidate = root / rel
    if candidate.is_symlink():
        raise LibraryPathError(f"symbolic links are not usable as sources: {raw_rel}")
    src = candidate.resolve()
    try:
        src.relative_to(root)
    except ValueError as exc:
        raise LibraryPathError(f"entry escapes library root: {raw_rel}") from exc
    if not src.exists():
        raise LibraryPathError(f"entry file does not exist: {raw_rel}")
    if not src.is_file():
        raise LibraryPathError(f"entry must name one regular file: {raw_rel}")
    if src.stat().st_nlink > 1:
        raise LibraryPathError(f"hard-linked file is not usable as a source: {raw_rel}")
    return src


def read_index(root: Path) -> tuple[list[dict], list[str]]:
    """Return (entries, errors). A missing index.json is not an error."""
    errors: list[str] = []
    index_path = root / INDEX_FILENAME
    if not index_path.exists():
        return [], errors
    if index_path.is_symlink():
        return [], [f"{INDEX_FILENAME} is a symbolic link; refusing to read it"]
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"{INDEX_FILENAME} is unreadable or not valid JSON: {exc}"]

    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict):
        raw_entries = payload.get("entries")
        if raw_entries is None and isinstance(payload.get("datasets"), list):
            # Legacy prototype shape kept readable so an early hand-made index
            # is not silently dropped; the canonical key is `entries`.
            raw_entries = payload["datasets"]
            errors.append(
                "index.json uses the legacy `datasets` key; rename it to `entries`"
            )
        if raw_entries is None:
            return [], [f"{INDEX_FILENAME} has no `entries` array"]
    else:
        return [], [f"{INDEX_FILENAME} must be an object with an `entries` array"]

    if not isinstance(raw_entries, list):
        return [], [f"{INDEX_FILENAME} `entries` must be an array"]

    entries = []
    for pos, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            errors.append(f"entries[{pos}] is not an object")
            continue
        entries.append(item)
    return entries, errors


def scan_files(root: Path) -> tuple[list[str], list[str]]:
    """Return (relative file paths, symlink paths) under root, excluding housekeeping."""
    files: list[str] = []
    symlinks: list[str] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(dirnames):
            if (here / name).is_symlink():
                symlinks.append((here / name).relative_to(root).as_posix())
        for name in sorted(filenames):
            if name.startswith(".") or name in FORBIDDEN_ANY_DEPTH:
                continue
            path = here / name
            rel = path.relative_to(root).as_posix()
            if rel in HOUSEKEEPING_NAMES or name in HOUSEKEEPING_NAMES:
                continue
            if path.is_symlink():
                symlinks.append(rel)
                continue
            files.append(rel)
    # A symlinked directory is never descended into by os.walk(followlinks=False),
    # so nothing under it can become a registered entry either.
    return files, symlinks


def _repo_root() -> Path:
    # <repo>/skills/cancer-buddy-organize/scripts/library_resolve.py
    return Path(__file__).resolve().parents[3]


def l1_root() -> Path:
    override = os.environ.get(L1_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    repo = _repo_root()
    candidates = [
        repo / "skills" / "cancer-buddy" / "references" / "library",
        Path(__file__).resolve().parents[1] / "references" / "library",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def l2_root() -> Path:
    override = os.environ.get(L2_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path(DEFAULT_L2_ROOT).expanduser()


def l3_root(patient_dir: Path | None) -> Path | None:
    if patient_dir is None:
        return None
    return Path(patient_dir).expanduser() / "library"


def describe_layer(layer: str, root: Path | None) -> dict:
    info: dict = {
        "layer": layer,
        "trust_tier": LAYER_TRUST_TIER[layer],
        "root": str(root) if root is not None else None,
        "exists": False,
        "index_exists": False,
        "entry_count": 0,
        "registered_files": [],
        "orphan_files": [],
        "unsafe_entries": [],
        "symlinks": [],
        "errors": [],
    }
    if root is None:
        info["errors"].append("layer not configured (no patient directory supplied)")
        return info
    if not root.is_dir():
        return info

    resolved_root = root.resolve()
    info["root"] = str(resolved_root)
    info["exists"] = True
    info["index_exists"] = (resolved_root / INDEX_FILENAME).is_file()

    entries, index_errors = read_index(resolved_root)
    info["errors"].extend(index_errors)
    info["entry_count"] = len(entries)

    registered: set[str] = set()
    for pos, entry in enumerate(entries):
        raw_rel = entry.get("file")
        try:
            real = resolve_entry_path(resolved_root, raw_rel if isinstance(raw_rel, str) else "")
        except LibraryPathError as exc:
            info["unsafe_entries"].append(
                {"index": pos, "file": raw_rel, "reason": str(exc)}
            )
            continue
        rel = real.relative_to(resolved_root).as_posix()
        registered.add(rel)
    info["registered_files"] = sorted(registered)

    files, symlinks = scan_files(resolved_root)
    info["symlinks"] = symlinks
    info["orphan_files"] = [rel for rel in files if rel not in registered]
    return info


def resolve_layers(patient_dir: Path | None, layers: list[str]) -> dict:
    roots = {"L3": l3_root(patient_dir), "L2": l2_root(), "L1": l1_root()}
    described = [describe_layer(name, roots[name]) for name in layers]
    return {
        "search_order": layers,
        "layers": described,
        "orphan_total": sum(len(item["orphan_files"]) for item in described),
        "unsafe_entry_total": sum(len(item["unsafe_entries"]) for item in described),
        "error_total": sum(len(item["errors"]) for item in described),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--patient-dir", type=Path, default=None)
    parser.add_argument(
        "--layer",
        action="append",
        choices=["L1", "L2", "L3"],
        help="restrict output to these layers (default: L3, L2, L1 in search order)",
    )
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    order = ["L3", "L2", "L1"]
    layers = [name for name in order if not args.layer or name in args.layer]
    result = resolve_layers(args.patient_dir, layers)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=args.indent)
    sys.stdout.write("\n")
    # Unsafe entries are a hard signal: an index is pointing outside its root.
    return 1 if result["unsafe_entry_total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
