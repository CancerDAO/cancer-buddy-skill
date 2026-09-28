#!/usr/bin/env bash
# Local git pre-push hook: refuse to push a commit whose NEW content or message holds a phrase from the
# maintainer's PRIVATE real-record phrase list (the list lint 14 reads; kept outside the tracked tree).
#
# Lint 14 checks the working tree. This hook checks history: every commit the push would publish (not
# yet on any remote-tracking ref) — each blob it adds or changes and its message. A phrase that one commit
# adds and a later commit removes is still refused, because both commits would reach the public remote.
# Output names the commit, the file and line, and the phrase's line number in the list — never the phrase.
#
# Install (per clone; hooks are not versioned):
#   cp tests/eval/hooks/pre-push-real-phrases.sh "$(git rev-parse --git-common-dir)/hooks/pre-push"
#   chmod +x "$(git rev-parse --git-common-dir)/hooks/pre-push"
#   cp <your private list> "$(git rev-parse --git-common-dir)/info/real-phrases.txt"; chmod 600 …
# The list is CB_REAL_PHRASES_FILE when set, else <git-common-dir>/info/real-phrases.txt (never pushed).
# No list → the push is refused (fail closed); `git push --no-verify` is the explicit bypass.
set -uo pipefail
list="${CB_REAL_PHRASES_FILE:-$(git rev-parse --git-common-dir 2>/dev/null)/info/real-phrases.txt}"
if [ ! -f "$list" ]; then
  echo "pre-push: no private phrase list at $list — refusing to push (set CB_REAL_PHRASES_FILE, install the" >&2
  echo "pre-push: list there, or bypass deliberately with git push --no-verify)" >&2
  exit 1
fi
CB_PREPUSH_UPDATES="$(cat)" python3 - "$list" <<'PY'
import os
import re
import subprocess
import sys
import unicodedata

ZERO = "0" * 40


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def git(*args: str, raw: bool = False):
    out = subprocess.run(["git", *args], capture_output=True, check=True).stdout
    return out if raw else out.decode("utf-8", "replace")


phrases = []
with open(sys.argv[1], encoding="utf-8") as fh:
    for i, line in enumerate(fh, start=1):
        t = line.strip()
        if t and not t.startswith("#") and len(norm(t)) >= 4:
            phrases.append((i, norm(t)))
if not phrases:
    print("pre-push: the phrase list holds no phrase of 4+ characters — refusing to push", file=sys.stderr)
    sys.exit(1)

updates = [l.split() for l in os.environ.get("CB_PREPUSH_UPDATES", "").splitlines() if l.strip()]
commits: list[str] = []
for parts in updates:
    if len(parts) != 4:
        continue
    _local_ref, local_sha, _remote_ref, remote_sha = parts
    if local_sha == ZERO:  # deleting a remote branch publishes nothing
        continue
    try:
        if remote_sha != ZERO:
            git("cat-file", "-e", remote_sha + "^{commit}")
            rng = git("rev-list", f"{remote_sha}..{local_sha}")
        else:
            raise subprocess.CalledProcessError(1, "new ref")
    except subprocess.CalledProcessError:
        rng = git("rev-list", local_sha, "--not", "--remotes")
    commits += [c for c in rng.split() if c not in commits]

hits = 0


def scan(text: str, where) -> None:
    global hits
    whole = norm(text)
    lines = None
    for idx, ph in phrases:
        if ph in whole:
            if lines is None:
                lines = text.splitlines()
            n = next((k for k, l in enumerate(lines, start=1) if ph in norm(l)), None)
            print(f"pre-push: {where(n)} contains phrase #{idx} of the private list", file=sys.stderr)
            hits += 1


for c in commits:
    short = c[:10]
    scan(git("log", "-1", "--format=%B", c), lambda n, s=short: f"{s} commit message:{n or '?'}")
    out = git("diff-tree", "-r", "--root", "--no-commit-id", "-z", "--diff-filter=d", c, raw=True)
    fields = out.split(b"\0")
    k = 0
    while k < len(fields) - 1:
        meta = fields[k].decode("utf-8", "replace")
        if not meta.startswith(":"):
            k += 1
            continue
        _m1, _m2, _old, new_blob, status = meta[1:].split(" ")
        npaths = 2 if status[:1] in ("R", "C") else 1
        path = fields[k + npaths].decode("utf-8", "replace")
        k += 1 + npaths
        if new_blob == ZERO:
            continue
        try:
            text = git("cat-file", "blob", new_blob, raw=True).decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary
        scan(text, lambda n, s=short, p=path: f"{s} {p}:{n or '(spans lines)'}")

if hits:
    print(f"pre-push: {hits} hit(s) in {len(commits)} unpublished commit(s) — rewrite those commits with invented "
          "text before pushing (a later fix does not remove a phrase from history)", file=sys.stderr)
    sys.exit(1)
print(f"pre-push: real-phrase check OK ({len(commits)} commit(s), {len(phrases)} phrase(s))", file=sys.stderr)
PY
