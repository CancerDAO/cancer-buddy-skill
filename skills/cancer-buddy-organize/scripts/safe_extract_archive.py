#!/usr/bin/env python3
"""Safely extract ZIP or TAR-family archives into a fresh private directory.

Rejects absolute/traversal paths, links, devices, encrypted ZIP members, duplicate
normalized paths, oversized members, excessive file counts, and decompression
bombs. Extracted directories are mode 0700 and files 0600.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tarfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath


class UnsafeArchive(ValueError):
    pass


def safe_relative(name: str) -> Path:
    if "\x00" in name:
        raise UnsafeArchive("member path contains NUL")
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise UnsafeArchive(f"unsafe member path: {name!r}")
    if p.parts and p.parts[0].endswith(":"):
        raise UnsafeArchive(f"drive-qualified member path: {name!r}")
    if len(normalized) > 1024 or any(len(part) > 240 for part in p.parts):
        raise UnsafeArchive(f"member path too long: {name!r}")
    return Path(*p.parts)


def collision_key(path: Path) -> str:
    return unicodedata.normalize("NFKC", path.as_posix()).casefold()


def ensure_fresh_private_dir(out: Path) -> None:
    if out.exists():
        raise UnsafeArchive(f"output already exists: {out}")
    out.mkdir(parents=True, mode=0o700)
    os.chmod(out, 0o700)


def secure_parent(path: Path, root: Path) -> None:
    current = path.parent
    missing: list[Path] = []
    while current != root and not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        os.chmod(directory, 0o700)


def validate_budget(count: int, total: int, size: int, args) -> None:
    if count > args.max_files:
        raise UnsafeArchive(f"too many files: {count} > {args.max_files}")
    if size > args.max_file_bytes:
        raise UnsafeArchive(f"member too large: {size} > {args.max_file_bytes}")
    if total > args.max_total_bytes:
        raise UnsafeArchive(f"archive expands too large: {total} > {args.max_total_bytes}")


def zip_plan(archive: Path, args):
    plan = []
    seen: set[str] = set()
    count = total = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            rel = safe_relative(info.filename.rstrip("/")) if info.filename.rstrip("/") else None
            if rel is None:
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise UnsafeArchive(f"symlink member rejected: {info.filename}")
            if info.flag_bits & 0x1:
                raise UnsafeArchive(f"encrypted ZIP member rejected: {info.filename}")
            key = collision_key(rel)
            if key in seen:
                raise UnsafeArchive(f"duplicate normalized path: {info.filename}")
            seen.add(key)
            if info.is_dir():
                plan.append((info, rel, True))
                continue
            count += 1
            total += info.file_size
            validate_budget(count, total, info.file_size, args)
            compressed = max(info.compress_size, 1)
            if info.file_size / compressed > args.max_ratio:
                raise UnsafeArchive(f"suspicious compression ratio: {info.filename}")
            plan.append((info, rel, False))
        return plan


def tar_plan(archive: Path, args):
    plan = []
    seen: set[str] = set()
    count = total = 0
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            rel = safe_relative(member.name.rstrip("/")) if member.name.rstrip("/") else None
            if rel is None:
                continue
            if not (member.isfile() or member.isdir()):
                raise UnsafeArchive(f"link/device/special member rejected: {member.name}")
            key = collision_key(rel)
            if key in seen:
                raise UnsafeArchive(f"duplicate normalized path: {member.name}")
            seen.add(key)
            if member.isdir():
                plan.append((member.name, rel, True))
                continue
            count += 1
            total += member.size
            validate_budget(count, total, member.size, args)
            plan.append((member.name, rel, False))
        return plan


def copy_limited(src, dest: Path, expected: int, max_bytes: int) -> None:
    written = 0
    with dest.open("xb") as out:
        os.chmod(dest, 0o600)
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes or written > expected:
                raise UnsafeArchive(f"member exceeded declared size: {dest.name}")
            out.write(chunk)
    if written != expected:
        raise UnsafeArchive(f"member size mismatch: {dest.name}")


def extract_zip(archive: Path, out: Path, plan, args) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info, rel, is_dir in plan:
            dest = out / rel
            secure_parent(dest, out)
            if is_dir:
                dest.mkdir(exist_ok=True, mode=0o700)
                os.chmod(dest, 0o700)
            else:
                with zf.open(info, "r") as src:
                    copy_limited(src, dest, info.file_size, args.max_file_bytes)


def extract_tar(archive: Path, out: Path, plan, args) -> None:
    with tarfile.open(archive, "r:*") as tf:
        members = {m.name: m for m in tf.getmembers()}
        for name, rel, is_dir in plan:
            member = members[name]
            dest = out / rel
            secure_parent(dest, out)
            if is_dir:
                dest.mkdir(exist_ok=True, mode=0o700)
                os.chmod(dest, 0o700)
            else:
                src = tf.extractfile(member)
                if src is None:
                    raise UnsafeArchive(f"cannot read member: {name}")
                with src:
                    copy_limited(src, dest, member.size, args.max_file_bytes)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-files", type=int, default=5000)
    ap.add_argument("--max-total-bytes", type=int, default=2 * 1024**3)
    ap.add_argument("--max-file-bytes", type=int, default=512 * 1024**2)
    ap.add_argument("--max-ratio", type=float, default=200.0)
    args = ap.parse_args()
    archive = Path(args.archive).resolve()
    out = Path(args.out).resolve()
    if not archive.is_file():
        print(f"ERROR: archive not found: {archive}", file=sys.stderr)
        return 2
    try:
        if zipfile.is_zipfile(archive):
            plan = zip_plan(archive, args)
            kind = "zip"
        elif tarfile.is_tarfile(archive):
            plan = tar_plan(archive, args)
            kind = "tar"
        else:
            raise UnsafeArchive("unsupported archive; provide ZIP/TAR/TGZ or unpack RAR/7z yourself")
        ensure_fresh_private_dir(out)
        if kind == "zip":
            extract_zip(archive, out, plan, args)
        else:
            extract_tar(archive, out, plan, args)
    except (OSError, zipfile.BadZipFile, tarfile.TarError, UnsafeArchive) as exc:
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    files = sum(1 for _, _, is_dir in plan if not is_dir)
    print(f"safe_extract: kind={kind} files={files} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
