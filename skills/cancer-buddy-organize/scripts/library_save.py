#!/usr/bin/env python3
"""Execute the "save this one for me" action into a reference library.

Given a source file the user already holds legally, this script:

  1. picks the destination root -- `--scope global` (L2) or `--scope patient` (L3)
  2. decides `patient_scope`; anything patient-identifying is refused for L2
  3. refuses to write into any git working tree (L1 is maintained by us and
     never receives user files)
  4. copies the file under the chosen category directory
  5. appends the `index.json` entry and an `update_log.json` record

It does not confirm anything with the user -- the calling skill must run the
confirm-gate diff card first (`references/confirm-gate.md`). Metadata this
script cannot know (version, publication date) must be supplied; a missing
`--version`/`--date` produces an entry that `library_verify.py` will reject, so
the flags are required rather than silently defaulted.

Usage:
  python3 library_save.py --src ~/Downloads/guide.pdf --scope global \
      --title "..." --publisher "..." --version "2026.v3" --date 2026-01-15
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import library_resolve as lib  # noqa: E402

CATEGORIES = ("guidelines", "literature", "education", "datasets", "other")

# Publishers whose terms commonly forbid redistribution. Detection only sets a
# conservative default and tells the user; it never grants `allowed`.
RESTRICTED_PUBLISHER_RE = re.compile(
    r"(NCCN|CSCO|ESMO|ASCO|UpToDate|Elsevier|Springer|Wiley|中国临床肿瘤学会|人民卫生出版社)",
    re.IGNORECASE,
)

PATIENT_MARKER_RE = re.compile(
    r"(住院号|门诊号|病案号|病历号|就诊卡号|患者姓名|出院小结|入院记录|检验报告|"
    r"病理报告|影像报告|(?<!\d)[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d))"
)


class SaveError(Exception):
    pass


def _git_worktree_root(path: Path) -> Path | None:
    """Return the nearest ancestor containing `.git`, or None."""
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _assert_writable_destination(root: Path) -> None:
    """L1 is ours; user files never land in a repository working tree."""
    probe = root if root.exists() else root.parent
    probe = probe.resolve() if probe.exists() else probe
    repo = _git_worktree_root(probe)
    if repo is not None:
        raise SaveError(
            f"refusing to write into the git working tree at {repo}: the bundled "
            "L1 library is product-maintained and never receives user files; "
            "use --scope global (L2) or --scope patient (L3)"
        )
    skill_repo = lib._repo_root()
    try:
        probe.relative_to(skill_repo)
    except ValueError:
        return
    raise SaveError(f"refusing to write inside the skill repository at {skill_repo}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_patient_specific(src: Path, title: str, notes: str) -> list[str]:
    hits: list[str] = []
    blob = "\n".join([src.name, title or "", notes or ""])
    if PATIENT_MARKER_RE.search(blob):
        hits.append("filename/title")
    if src.suffix.lower() in {".md", ".txt", ".json", ".jsonl", ".csv", ".html", ".htm"}:
        try:
            body = src.read_text(encoding="utf-8", errors="ignore")[:200_000]
        except OSError:
            body = ""
        if PATIENT_MARKER_RE.search(body):
            hits.append("file content")
    return hits


def _load_index(index_path: Path) -> dict:
    if not index_path.is_file():
        return {"schema_version": 1, "entries": []}
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SaveError(f"existing index.json is unreadable: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise SaveError("existing index.json is not an object with an `entries` array")
    return payload


def save(args: argparse.Namespace) -> dict:
    src = Path(args.src).expanduser()
    if src.is_symlink():
        raise SaveError(f"source is a symbolic link: {src}")
    if not src.is_file():
        raise SaveError(f"source is not a regular file: {src}")

    if args.scope == "patient":
        if args.patient_dir is None:
            raise SaveError("--scope patient requires --patient-dir")
        patient_dir = Path(args.patient_dir).expanduser()
        if not patient_dir.is_dir():
            raise SaveError(f"patient directory does not exist: {patient_dir}")
        root = lib.l3_root(patient_dir)
        layer = "L3"
    else:
        root = lib.l2_root()
        layer = "L2"
    assert root is not None

    _assert_writable_destination(root)

    detected = _looks_patient_specific(src, args.title, args.notes or "")
    patient_scope = args.patient_scope
    if detected and patient_scope != "patient_specific":
        patient_scope = "patient_specific"
    if patient_scope == "patient_specific" and layer == "L2":
        raise SaveError(
            "this file looks patient-identifying ("
            + ", ".join(detected or ["declared patient_specific"])
            + ") and the global library is shared across patient records; "
            "save it with --scope patient --patient-dir <patient_dir>"
        )

    redistribution = args.redistribution
    notices: list[str] = []
    if redistribution is None:
        if RESTRICTED_PUBLISHER_RE.search(f"{args.publisher} {args.title} {src.name}"):
            redistribution = "restricted"
            notices.append(
                "publisher matched a commonly licence-restricted list; recorded as "
                "`restricted`, so this entry can be read locally but never leaves the "
                "machine (no export package, no second-opinion package)"
            )
        else:
            redistribution = "unknown"
            notices.append(
                "redistribution not declared; recorded as `unknown`, which is treated "
                "as not exportable until the user states the licence"
            )

    dest_name = args.dest_name or src.name
    if "/" in dest_name or dest_name.startswith("."):
        raise SaveError(f"invalid --dest-name: {dest_name}")
    rel = f"{args.category}/{dest_name}"

    dest_dir = root / args.category
    dest = dest_dir / dest_name
    if dest.exists() and not args.force:
        raise SaveError(f"destination already exists (use --force to replace): {dest}")

    index_path = root / lib.INDEX_FILENAME
    payload = _load_index(index_path)
    if any(entry.get("file") == rel for entry in payload["entries"]) and not args.force:
        raise SaveError(f"index.json already registers {rel} (use --force to replace)")

    entry = {
        "file": rel,
        "title": args.title,
        "publisher": args.publisher,
        "version": args.version,
        "date": args.date,
        "retrieved_at": args.retrieved_at or dt.date.today().isoformat(),
        "lang": args.lang,
        "redistribution": redistribution,
        "patient_scope": patient_scope,
    }
    for key, value in (
        ("jurisdiction", args.jurisdiction),
        ("license", args.license),
        ("notes", args.notes),
        ("expires_at", args.expires_at),
    ):
        if value:
            entry[key] = value
    if args.cancer_type:
        entry["cancer_types"] = list(args.cancer_type)

    result = {
        "layer": layer,
        "trust_tier": lib.LAYER_TRUST_TIER[layer],
        "root": str(root),
        "destination": str(dest),
        "entry": entry,
        "notices": notices,
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        return result

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    entry["sha256"] = _sha256(dest)
    result["entry"] = entry

    payload["entries"] = [e for e in payload["entries"] if e.get("file") != rel]
    payload["entries"].append(entry)
    payload.setdefault("schema_version", 1)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log_path = root / "update_log.json"
    try:
        log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.is_file() else []
    except (OSError, ValueError):
        log = []
    if not isinstance(log, list):
        log = []
    log.append(
        {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "action": "library_save",
            "layer": layer,
            "file": rel,
            "title": args.title,
            "redistribution": redistribution,
            "patient_scope": patient_scope,
            "source_basename": src.name,
        }
    )
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["update_log"] = str(log_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True)
    parser.add_argument("--scope", required=True, choices=["global", "patient"])
    parser.add_argument("--patient-dir", default=None)
    parser.add_argument("--category", default="other", choices=list(CATEGORIES))
    parser.add_argument("--title", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", required=True, help="publication date of this version")
    parser.add_argument("--retrieved-at", default=None, help="defaults to today")
    parser.add_argument("--lang", default="zh")
    parser.add_argument("--redistribution", default=None, choices=["allowed", "restricted", "unknown"])
    parser.add_argument("--patient-scope", default="general", choices=["general", "patient_specific"])
    parser.add_argument("--jurisdiction", default=None)
    parser.add_argument("--license", default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--expires-at", default=None)
    parser.add_argument("--cancer-type", action="append", default=None)
    parser.add_argument("--dest-name", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = save(args)
    except SaveError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    for notice in result["notices"]:
        print(f"NOTE {notice}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
