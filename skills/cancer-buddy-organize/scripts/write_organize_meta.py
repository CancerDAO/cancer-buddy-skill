#!/usr/bin/env python3
"""write_organize_meta.py — stamp which organize build produced a patient archive.

Writes <patient_dir>/organize_meta.json (schema: references/schemas/organize_meta.schema.json):

    {"skill": "cancer-buddy-organize", "skill_version": ..., "skill_commit": ...,
     "skill_dirty": ..., "skill_fingerprint": "sha256:…", "generated_at": "…Z"}

  * skill_version  — `version:` from SKILL.md frontmatter (top-level or under
                     `metadata:`), else the `version` of the nearest
                     .claude-plugin/plugin.json above the skill, else null.
  * skill_commit   — `.skill_source.json` ({repo, commit, dirty, synced_at}) next to
                     SKILL.md when present (an installed copy records the commit it was
                     synced from); otherwise `git rev-parse HEAD` of the checkout holding
                     this skill, with skill_dirty = uncommitted changes under the skill
                     dir — but ONLY when that checkout tracks this SKILL.md (`git ls-files
                     --error-unmatch SKILL.md`): a copy that merely sits inside some other
                     repository (a dotfiles-managed ~/.agents, say) would otherwise report
                     the outer repository's HEAD; else null.
  * skill_fingerprint — sha256 over SKILL.md + references/** + scripts/** (sorted
                     relative path + NUL + bytes; __pycache__ / *.pyc excluded), so two
                     installs can be compared even without git.

  * pii_layer1_scan — `{worker_id, clean: true}` of the semantic PII scan (pii-rescan-prompt.md)
                     that returned clean=true in SKILL.md Step 12.5 (`--pii-layer1 <worker_id>`);
                     DoD 3 on disk. The terminal validator requires it on a current archive; the
                     script only records a CLEAN scan (a scan with findings is not finished).

SMTB's `runlog.py init` reads skill_commit into its manifest (organize_commit).
Called once in the organize wrap-up step, BEFORE the terminal validator (its presence
marks the archive as current-contract, so the validator enforces the v2.1 gates).

CLI:
    write_organize_meta.py <patient_dir> --pii-layer1 <worker_id> [--skill-dir DIR]
                           [--generated-at ISO] [--print]
Exit: 0 written; 2 bad invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FINGERPRINT_PARTS = ("SKILL.md", "references", "scripts")
_VERSION_RE = re.compile(r"^\s*version\s*:\s*[\"']?([^\"'\s#]+)", re.MULTILINE)
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def skill_version(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        m = _VERSION_RE.search(_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace")))
        if m:
            return m.group(1)
    for parent in [skill_dir, *skill_dir.parents]:
        plugin = parent / ".claude-plugin" / "plugin.json"
        if plugin.is_file():
            try:
                v = json.loads(plugin.read_text(encoding="utf-8")).get("version")
            except Exception:
                v = None
            return v if isinstance(v, str) and v else None
    return None


def _git(skill_dir: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(skill_dir), *args], capture_output=True,
                              text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def skill_commit(skill_dir: Path) -> tuple[str | None, bool | None]:
    src = skill_dir / ".skill_source.json"
    if src.is_file():
        try:
            doc = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            doc = {}
        commit = doc.get("commit") if isinstance(doc, dict) else None
        if isinstance(commit, str) and _COMMIT_RE.match(commit):
            dirty = doc.get("dirty")
            return commit, dirty if isinstance(dirty, bool) else None
    # Only a checkout that TRACKS this SKILL.md describes this skill's build.
    if _git(skill_dir, "ls-files", "--error-unmatch", "--", "SKILL.md") is None:
        return None, None
    head = _git(skill_dir, "rev-parse", "HEAD")
    if head and _COMMIT_RE.match(head):
        status = _git(skill_dir, "status", "--porcelain", "--", ".")
        return head, (bool(status) if status is not None else None)
    return None, None


def skill_fingerprint(skill_dir: Path) -> str:
    files: list[Path] = []
    for part in FINGERPRINT_PARTS:
        p = skill_dir / part
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(f for f in p.rglob("*") if f.is_file())
    h = hashlib.sha256()
    for f in sorted(files, key=lambda x: x.relative_to(skill_dir).as_posix()):
        rel = f.relative_to(skill_dir).as_posix()
        if "__pycache__" in rel.split("/") or rel.endswith(".pyc"):
            continue
        h.update(rel.encode("utf-8") + b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


_WORKER_ID_RE = re.compile(r"^(?!(orchestrator|main|manual|host|self|user)$)(?!.*[0-9]{11})[A-Za-z][A-Za-z0-9_.:-]{1,63}$")


def build_meta(skill_dir: Path, generated_at: str | None = None, pii_layer1: str | None = None) -> dict:
    commit, dirty = skill_commit(skill_dir)
    meta = {
        "skill": "cancer-buddy-organize",
        "skill_version": skill_version(skill_dir),
        "skill_commit": commit,
        "skill_dirty": dirty,
        "skill_fingerprint": skill_fingerprint(skill_dir),
        "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if pii_layer1 is not None:
        meta["pii_layer1_scan"] = {"worker_id": pii_layer1, "clean": True}
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write <patient_dir>/organize_meta.json (skill build provenance).")
    ap.add_argument("patient_dir")
    ap.add_argument("--skill-dir", default=str(SKILL_DIR), help="skill directory to describe (default: this script's skill)")
    ap.add_argument("--generated-at", default=None, help="override generated_at (ISO 8601, for tests)")
    ap.add_argument("--print", action="store_true", help="print the JSON instead of writing it")
    ap.add_argument("--pii-layer1", default=None, metavar="WORKER_ID",
                    help="worker id of the pii-rescan-prompt.md subagent that returned clean=true (Step 12.5)")
    args = ap.parse_args(argv)
    if args.pii_layer1 is not None and not _WORKER_ID_RE.match(args.pii_layer1):
        print(f"ERROR: --pii-layer1 {args.pii_layer1!r} is not a worker id (the orchestrator's reserved "
              "names and 11-digit runs are refused)", file=sys.stderr)
        return 2
    pdir = Path(args.patient_dir)
    skill_dir = Path(args.skill_dir)
    if not args.print and not pdir.is_dir():
        print(f"ERROR: {pdir} is not a directory", file=sys.stderr)
        return 2
    if not (skill_dir / "SKILL.md").is_file():
        print(f"ERROR: {skill_dir} has no SKILL.md", file=sys.stderr)
        return 2
    meta = build_meta(skill_dir, args.generated_at, args.pii_layer1)
    text = json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    if args.print:
        sys.stdout.write(text)
        return 0
    (pdir / "organize_meta.json").write_text(text, encoding="utf-8")
    print(f"organize_meta.json written (commit={meta['skill_commit']}, version={meta['skill_version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
