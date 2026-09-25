#!/usr/bin/env bash
# 14 — no real-record phrase in the public repository.
#
# This repository is public and ships synthetic data only (tests/fixtures/organize-regress/README.md).
# A maintainer who has worked with real archives keeps a private phrase list OUTSIDE the repository
# (one phrase per line, `#` comments allowed) and points CB_REAL_PHRASES_FILE at it; this lint then
# fails when any tracked text under skills/, references/, tests/ or the root docs contains one of
# those phrases (compared after NFKC and with all whitespace removed, so a re-wrapped copy still
# matches). The output names only the file, the line and the phrase's line number in the list —
# never the phrase itself, so a CI log cannot leak it.
#
# Unset CB_REAL_PHRASES_FILE → SKIP (exit 0): CI has no real phrases, and none may be committed.
# CB_DENYLIST_ROOT (tests only) scans another directory instead of the repository.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
echo "-- 14 real-phrase denylist --"
if [ -z "${CB_REAL_PHRASES_FILE:-}" ]; then
  echo "SKIP: CB_REAL_PHRASES_FILE unset (keep the phrase list outside the repository)"
  exit 0
fi
if [ ! -f "$CB_REAL_PHRASES_FILE" ]; then
  echo "FAIL: CB_REAL_PHRASES_FILE is set but is not a readable file" >&2
  exit 1
fi
python3 - "$CB_REAL_PHRASES_FILE" "${CB_DENYLIST_ROOT:-$REPO_ROOT}" "${CB_DENYLIST_ROOT:+scan-dir}" <<'PY'
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

phrases_file, root, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


phrases = []
for i, line in enumerate(phrases_file.read_text(encoding="utf-8").splitlines(), start=1):
    t = line.strip()
    if t and not t.startswith("#"):
        n = norm(t)
        if len(n) >= 4:  # shorter strings match generic text; the list must hold distinctive phrases
            phrases.append((i, n))
if not phrases:
    print("FAIL: the phrase list holds no phrase of 4+ characters", file=sys.stderr)
    sys.exit(1)

if mode == "scan-dir":
    files = [p for p in root.rglob("*") if p.is_file()]
else:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "skills", "references", "tests",
                          "README.md", "README_EN.md", "CHANGELOG.md", "CONTRIBUTING.md"],
                         capture_output=True, text=True, check=True).stdout
    files = [root / f for f in out.split("\0") if f]
hits = 0
for f in files:
    try:
        text = f.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    lines = text.splitlines()
    whole = norm(text)
    for idx, ph in phrases:
        if ph not in whole:
            continue
        where = next((n for n, l in enumerate(lines, start=1) if ph in norm(l)), None)
        rel = f.relative_to(root).as_posix()
        print(f"FAIL: {rel}:{where or '(spans lines)'} contains phrase #{idx} of the private list", file=sys.stderr)
        hits += 1
if hits:
    print(f"real-phrase-denylist: {hits} hit(s) — replace them with invented text", file=sys.stderr)
    sys.exit(1)
print(f"real-phrase-denylist OK ({len(phrases)} phrase(s), {len(files)} file(s))")
PY
