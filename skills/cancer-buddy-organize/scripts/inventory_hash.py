#!/usr/bin/env python3
"""inventory_hash.py — sha256 / size / page count for every input, plus the skip ledger (O-07).

Feeds source_inventory.json v2.1 (`files[].sha256 / size_bytes / page_count` and the
top-level `skipped_inputs[]`) and update_log.json `entries[].inputs[]`. Deterministic,
read-only on the input tree, no network.

Privacy: the JSON on stdout NEVER contains an original upload name or path. Every
input gets a de-identified handle — `in-NNN` for ingested files, `skip-NNN` for
skipped ones — in a stable order (sorted relative path). The handle → original
relative path mapping is written ONLY when `--mapping-out FILE` is given, and that
file belongs inside the access-controlled raw/ vault (raw/_FILENAME_MAPPING.md or a
sibling), never in a delivered surface.

When the scanned directory IS a patient archive's de-identified vault (its basename is
`raw`), the PINNED organize infrastructure entries (is_vault_infra: `_extract/`,
`_identity_denylist/`, `_legacy_<ts>/`, `_FILENAME_MAPPING.md`, `_SIDECAR_MAP.md`,
`_INPUT_HANDLES_<ts>.json`) are not inputs and are ignored — any other entry is an input,
even one whose de-identified name happens to start with `_` — and each row additionally
carries `raw_path` (`raw/<relative path>` — vault names are already de-identified handles).

Symbolic links are never followed (their target may sit outside the vault): each one is a
skipped input with reason `symlink`, its sha256 taken over the link text, not the target.

Skip reasons (pinned, source_inventory.schema.json skipped_inputs[].reason):
  ds_store              .DS_Store / Thumbs.db / desktop.ini
  macosx                anything under __MACOSX/ or an AppleDouble `._*` file
  empty                 zero-byte file
  duplicate_sha256      byte-identical to an earlier input (the first one is kept)
  archive_container     .zip/.rar/.7z/.tar/.tgz/.tar.gz/.tar.bz2/.tar.xz container (its members are ingested
                        separately); a single compressed file (.nii.gz, .vcf.gz, .gz …) is an input
  symlink               a symbolic link (never followed)
  user_excluded         matched an --exclude glob
  quarantined_irrelevant  matched a --quarantined glob (段E relevance quarantine)
Unsupported or corrupt formats are NOT skipped: they are ingested as stub sidecars
([INGESTION_BLOCKED]) — "never silently sample or drop".

page_count: images = 1 (multi-frame TIFF → null), PDF = pypdf page count when pypdf is
importable, else a `/Type /Page` object count; anything else null.

CLI:
    inventory_hash.py <input> [<input> ...] [--exclude GLOB]... [--quarantined GLOB]...
                      [--mapping-out FILE]
Each <input> is a directory (walked recursively, as above) or a single file (one row) —
e.g. a Phase-1 worker's own file list, or the earlier archive's source_inventory.json
when a digest's version is pinned by hash. Rows are sorted by (input position, relative
path); the handles are assigned in that order. With one directory the output is exactly
the directory report. Duplicate detection spans all inputs.
Exit: 0 ok; 2 bad invocation (an input that is neither a file nor a directory).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".gif", ".webp"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".tgz", ".tbz2", ".txz"}
# a compressed TAR is a container; a bare .gz / .bz2 / .xz compresses ONE file (.nii.gz, .vcf.gz)
ARCHIVE_SUFFIX_PAIRS = (".tar.gz", ".tar.bz2", ".tar.xz")
# organize's own entries inside raw/ — pinned names only (the vault's other `_…` entries are inputs)
VAULT_INFRA_NAMES = frozenset({"_extract", "_identity_denylist", "_FILENAME_MAPPING.md", "_SIDECAR_MAP.md", "_dispatch_log.jsonl"})
VAULT_INFRA_PATTERNS = (re.compile(r"^_legacy_[0-9A-Za-z_-]+$"), re.compile(r"^_INPUT_HANDLES_[0-9A-Za-z_-]+\.json$"))
DS_STORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![s])")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def page_count(path: Path) -> int | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return 1
    if ext in (".tif", ".tiff"):
        return None
    if ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            return len(PdfReader(str(path)).pages) or None
        except Exception:
            pass
        try:
            n = len(_PDF_PAGE_RE.findall(path.read_bytes()))
            return n or None
        except OSError:
            return None
    return None


def is_vault_infra(rel: str) -> bool:
    """True for a raw/-relative path under one of organize's pinned infrastructure entries."""
    first = rel.split("/", 1)[0]
    return first in VAULT_INFRA_NAMES or any(p.match(first) for p in VAULT_INFRA_PATTERNS)


def is_archive_container(name: str) -> bool:
    low = name.lower()
    return Path(low).suffix in ARCHIVE_EXT or low.endswith(ARCHIVE_SUFFIX_PAIRS)


def symlink_digest(path: Path) -> tuple[str, int]:
    """(sha256, size) of a symlink's own text — the target is never read."""
    target = os.readlink(path).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(target).hexdigest(), len(target)


def _walk(root: Path) -> list[Path]:
    """Every file AND symlink under `root`, never descending through a symlinked directory."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        d = Path(dirpath)
        for name in dirnames:
            if (d / name).is_symlink():
                out.append(d / name)
        out.extend(d / name for name in filenames)
    return sorted(out)


def _matches(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(Path(rel).name, g) for g in globs)


def _candidates(inputs: list[Path]) -> list[tuple[Path, str, bool]]:
    """(path, relative label, from a vault dir) for every input file, in handle order."""
    multi = len(inputs) > 1
    out: list[tuple[Path, str, bool]] = []
    for k, root in enumerate(inputs, start=1):
        prefix = f"{k:02d}/" if multi else ""
        if root.is_file():
            out.append((root, prefix + root.name, False))
            continue
        is_vault = root.name == "raw"
        for p in _walk(root):
            rel = p.relative_to(root).as_posix()
            if is_vault and is_vault_infra(rel):
                continue
            out.append((p, prefix + rel, is_vault))
    return out


def scan(inputs, exclude: list[str] | None = None,
         quarantined: list[str] | None = None) -> tuple[dict, dict]:
    """Return (report, mapping). mapping = {handle: original relative path}.

    `inputs` is one path or a list of paths; each is a directory or a single file."""
    roots = [Path(x) for x in inputs] if isinstance(inputs, (list, tuple)) else [Path(inputs)]
    exclude = exclude or []
    quarantined = quarantined or []
    files: list[dict] = []
    skipped: list[dict] = []
    mapping: dict[str, str] = {}
    seen_sha: dict[str, str] = {}
    duplicate_of: dict[str, str] = {}
    n_in = n_skip = 0
    for p, label, is_vault in _candidates(roots):
        rel = label.split("/", 1)[1] if len(roots) > 1 else label
        if p.is_symlink():
            digest, size = symlink_digest(p)
            n_skip += 1
            handle = f"skip-{n_skip:03d}"
            skipped.append({"input_ref": handle, "reason": "symlink", "sha256": digest, "size_bytes": size})
            mapping[handle] = label
            continue
        size = p.stat().st_size
        reason = None
        if p.name in DS_STORE_NAMES:
            reason = "ds_store"
        elif "__MACOSX" in rel.split("/") or p.name.startswith("._"):
            reason = "macosx"
        elif _matches(rel, exclude):
            reason = "user_excluded"
        elif _matches(rel, quarantined):
            reason = "quarantined_irrelevant"
        elif size == 0:
            reason = "empty"
        elif is_archive_container(p.name):
            reason = "archive_container"
        digest = sha256_file(p)
        if reason is None and digest in seen_sha:
            reason = "duplicate_sha256"
        if reason:
            n_skip += 1
            handle = f"skip-{n_skip:03d}"
            # exactly the four source_inventory skipped_inputs[] keys (closed schema)
            skipped.append({"input_ref": handle, "reason": reason, "sha256": digest, "size_bytes": size})
            if reason == "duplicate_sha256":
                duplicate_of[handle] = seen_sha[digest]
        else:
            n_in += 1
            handle = f"in-{n_in:03d}"
            seen_sha[digest] = handle
            row = {"input_ref": handle, "sha256": digest, "size_bytes": size,
                   "page_count": page_count(p), "ext": p.suffix.lower() or None}
            if is_vault:
                row["raw_path"] = f"raw/{rel}"
            files.append(row)
        mapping[handle] = label
    report = {
        "tool": "inventory_hash",
        "version": "1",
        "vault_mode": any(r.is_dir() and r.name == "raw" for r in roots),
        "files": files,
        "skipped_inputs": skipped,
        "duplicate_of": duplicate_of,
        "counts": {"inputs_seen": len(files) + len(skipped), "ingest": len(files),
                   "skipped": len(skipped),
                   "by_reason": {r: sum(1 for s in skipped if s["reason"] == r)
                                 for r in sorted({s["reason"] for s in skipped})}},
    }
    return report, mapping


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="sha256/size/page_count of every input + skipped_inputs ledger (de-identified handles).")
    ap.add_argument("inputs", nargs="+", metavar="input", help="directory or file (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="glob of inputs the user excluded")
    ap.add_argument("--quarantined", action="append", default=[], help="glob of inputs quarantined as irrelevant (段E)")
    ap.add_argument("--mapping-out", default=None,
                    help="write {handle: original relative path} JSON here — keep it inside raw/, never in a delivered surface")
    args = ap.parse_args(argv)
    roots = [Path(x) for x in args.inputs]
    for root in roots:
        if root.is_symlink() or not (root.is_dir() or root.is_file()):
            print(f"ERROR: {root} is neither a directory nor a file", file=sys.stderr)
            return 2
    report, mapping = scan(roots, args.exclude, args.quarantined)
    if args.mapping_out:
        Path(args.mapping_out).write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
