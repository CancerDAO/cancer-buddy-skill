#!/usr/bin/env bash
# tests/unit/pathsafe.test.sh — organize v3 fix spec A9, scripts/_pathsafe.py.
#
# Several organize scripts take an identifier straight out of *model output* — a
# `source_id` the transcriber minted, a `run_id`, a `--source` flag an operator pasted
# from a log — and three lines later join it onto a filesystem path:
#
#     raw/transcript/<source_id>/page-NNN.md
#     raw/_provenance/<run_id>/pages.json
#     raw/adapter_views/<source_id>/page-NNN.png
#
# The model that produced that value spent its whole context reading patient-uploaded
# pages, so the value is untrusted BY CONSTRUCTION. A `source_id` of `../../.ssh` turns
# every one of those joins into a write outside the patient directory, and the archive
# that was supposed to be a sealed vault becomes a write primitive.
#
# A9 requires TWO defences and they do not subsume one another:
#
#   safe_component()  a WHITELIST on the string. Whitelist, not blacklist, because the
#                     blacklist of "dangerous" path characters is open-ended — U+FF0F
#                     FULLWIDTH SOLIDUS that NFKC-folds to `/`, U+202E RIGHT-TO-LEFT
#                     OVERRIDE that makes `gpj.exe` render as `exe.jpg`, U+200B zero
#                     width space that makes two different ids look identical in a diff,
#                     NUL, a bare `..`. Enumerating what is ALLOWED is finite; the check
#                     must also ACCEPT CJK, because Chinese filenames are the norm here
#                     and a rule that rejects 血常规报告 would be turned off within a day.
#
#   contained()       a check on the RESULT, after os.path.realpath. This catches the one
#                     thing a whitelist structurally cannot see: a SYMLINK in the middle
#                     of an otherwise blameless relative path. Every component of
#                     `raw/adapter_views/s001/page-001.png` passes the whitelist even when
#                     `adapter_views` is a symlink to /tmp.
#
# So this file exercises both, each with a positive and a negative arm. A validator that
# only ever rejects is as useless as one that only ever accepts: the CJK and 64-char
# accept arms are what stop the whitelist from being "fixed" by loosening it later.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# Drive safe_component() out-of-process so the EXIT CODE is a real assertion, not a
# Python truthiness check: a caller that swallows PathSafetyError is the failure mode
# this whole module exists to prevent.
#   exit 0 = accepted, exit 1 = PathSafetyError, exit 3 = wrong exception type
run_component() {  # <python-repr-of-the-string>
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF' 2>&1
import ast, importlib, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
ps = importlib.import_module("_pathsafe")
value = ast.literal_eval(sys.argv[2])
try:
    got = ps.safe_component(value, "source_id")
except ps.PathSafetyError as exc:
    print(exc)
    sys.exit(1)
except Exception as exc:            # noqa: BLE001 — a non-PathSafetyError is its own bug
    print(f"WRONG EXCEPTION {type(exc).__name__}: {exc}")
    sys.exit(3)
assert got == value, "safe_component must return the value UNCHANGED, never a repair"
print(got)
sys.exit(0)
PYEOF
)"
  rc=$?
  set -e
}

# ===========================================================================
# A. NEGATIVE — safe_component() rejects every path-traversal / spoofing primitive
# ===========================================================================
echo "=== A. safe_component rejects (fix spec A9 whitelist) ==="

# <python repr> <label> <substring the message must contain>
reject() {
  run_component "$1"
  if [ "$rc" -eq 1 ]; then
    ok "rejects $2"
  elif [ "$rc" -eq 3 ]; then
    no "$2 — raised the wrong exception type: $out"
    return
  else
    no "$2 — ACCEPTED (rc=$rc, returned $out); this value would become a directory name"
    return
  fi
  if [ -n "${3:-}" ]; then
    echo "$out" | grep -q "$3" \
      && ok "…and the message says WHICH class tripped ($3)" \
      || no "$2 — message does not name the class '$3': $out"
  fi
}

reject "'..'"        "'..' — the parent-directory token"        "relative-path token"
reject "'.'"         "'.' — the current-directory token"        "relative-path token"
reject "'a/b'"       "a string containing '/'"                  "path separator"
reject "'a\\\\b'"    "a string containing a backslash"          "path separator"
reject "'a​b'"  "U+200B ZERO WIDTH SPACE"                  "zero-width"
reject "'a‮b'"  "U+202E RIGHT-TO-LEFT OVERRIDE"            "bidirectional-override"
reject "'a／b'"  "U+FF0F FULLWIDTH SOLIDUS (NFKC-folds to '/')" "fullwidth"
X64="$(printf 'x%.0s' {1..64})"
reject "'${X64}x'"   "a 65-character string (one over the cap)"  "65 characters long"
reject "''"          "the empty string"                          "empty"
reject "'a\x00b'"    "a NUL control character"                   "control/format"
reject "'a\nb'"      "an embedded newline"                       "control/format"

# NOT A SANITIZER: the module's own contract is that a rejected value is never repaired
# into a different-but-legal one, because a repaired id makes the manifest disagree with
# the model output it claims to record.
grep -q "NOT A SANITIZER" "$ORG/scripts/_pathsafe.py" \
  && ok "module states it REJECTS rather than repairs (a repaired id is a different id)" \
  || no "the reject-don't-repair contract is not stated in _pathsafe.py"

# ===========================================================================
# B. POSITIVE — the whitelist must not be so tight it gets switched off
# ===========================================================================
echo "=== B. safe_component accepts ==="

accept() {  # <python repr> <label>
  run_component "$1"
  [ "$rc" -eq 0 ] && ok "accepts $2" \
    || no "$2 — REJECTED (rc=$rc): $out"
}

accept "'s001'"        "plain ASCII 's001'"
accept "'s-001'"       "a hyphenated id"
accept "'s_001'"       "an underscored id"
accept "'PT-A1B2_3'"   "the mixed hyphen/underscore/digit form ids actually take"
accept "'${X64}'"      "a 64-character string (exactly at the cap)"
accept "'血常规报告'"   "CJK '血常规报告' — Chinese filenames are the norm in this archive"
accept "'病理报告-f39306d5'" "a minted CJK id: sanitize(stem)+'-'+sha256[:8] (A8)"

# ===========================================================================
# C. contained() — the defence the whitelist structurally cannot provide
# ===========================================================================
echo "=== C. contained(path, root) with a REAL symlink on disk ==="

root="$tmp/patient"
mkdir -p "$root/raw/adapter_views" "$tmp/elsewhere"
echo "not the patient's" > "$tmp/elsewhere/secret.txt"
# every component of raw/adapter_views/escape/page-001.png is whitelist-clean; the escape
# is invisible to any string rule and only realpath can see it.
ln -s "$tmp/elsewhere" "$root/raw/adapter_views/escape"

set +e
out="$(python3 - "$ORG" "$root" "$tmp" <<'PYEOF' 2>&1
import importlib, os, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
ps = importlib.import_module("_pathsafe")
root, base = sys.argv[2], sys.argv[3]

escaped = os.path.join(root, "raw", "adapter_views", "escape", "page-001.png")
inside = os.path.join(root, "raw", "adapter_views", "s001", "page-001.png")

# every component of the escaping path passes the whitelist — that is the whole point
for part in ("raw", "adapter_views", "escape"):
    ps.safe_component(part, "component")

assert ps.contained(escaped, root) is False, "symlinked escape reported as contained"
assert ps.contained(inside, root) is True, "an ordinary path inside root was refused"
assert ps.contained(root, root) is True, "root itself must count as contained"
assert ps.contained(base, root) is False, "the parent of root must not count as contained"

try:
    ps.require_contained(escaped, root, "page image")
except ps.PathSafetyError as exc:
    msg = str(exc)
else:
    raise AssertionError("require_contained accepted a symlink escape")

assert "refusing to write" in msg, msg
print("MSG:" + msg)
PYEOF
)"
rc=$?
set -e

[ "$rc" -eq 0 ] && ok "contained() refuses a symlink that escapes root, accepts a path inside it" \
  || no "contained()/require_contained behaved wrongly: $out"
echo "$out" | grep -q "resolves outside" \
  && ok "…require_contained says the path resolves OUTSIDE the root it was given" \
  || no "refusal does not state the containment violation: $out"

# The realpath check must also be what stops a multi-component relative path (--source
# targets arrive as `raw/incoming/x.pdf`, not as single components).
set +e
out="$(python3 - "$ORG" "$root" <<'PYEOF' 2>&1
import importlib, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
ps = importlib.import_module("_pathsafe")
root = sys.argv[2]

good = ps.safe_relpath("raw/adapter_views/s001/page-001.png", root, "source path")
assert str(good).startswith(root), good

for bad in ("../escape.pdf", "/etc/passwd", "raw/../../escape.pdf",
            "raw/adapter_views/escape/page-001.png"):
    try:
        ps.safe_relpath(bad, root, "source path")
    except ps.PathSafetyError:
        continue
    raise AssertionError(f"safe_relpath accepted {bad!r}")
print("ok")
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "safe_relpath: accepts a legal relative target, refuses '..', absolute, and symlinked ones" \
  || no "safe_relpath arm failed: $out"

# ===========================================================================
# D. the two rules are deliberately DIFFERENT blast radii
# ===========================================================================
echo "=== D. safe_component vs safe_filename_token ==="

# `prompt_version` (3.0) and `model_id` (claude-opus-4.1) are joined into a cache
# FILENAME and legitimately contain dots; source_id/run_id become whole DIRECTORY names
# and must not. One exception to the no-dot rule is all a traversal needs, so A9 keeps
# them as two functions rather than one relaxed one.
set +e
out="$(python3 - "$ORG" <<'PYEOF' 2>&1
import importlib, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
ps = importlib.import_module("_pathsafe")

assert ps.safe_filename_token("3.0") == "3.0"
assert ps.safe_filename_token("claude-opus-4.1") == "claude-opus-4.1"

# but the dotted form is NOT a legal directory component
for dotted in ("3.0", "claude-opus-4.1"):
    try:
        ps.safe_component(dotted, "source_id")
    except ps.PathSafetyError:
        pass
    else:
        raise AssertionError(f"safe_component accepted the dotted token {dotted!r}")

# and the relaxed rule still refuses the traversal primitives
for bad in ("..", ".", ".hidden", "a..b", "a/b", "a\\b", "‮.md"):
    try:
        ps.safe_filename_token(bad, "model_id")
    except ps.PathSafetyError:
        continue
    raise AssertionError(f"safe_filename_token accepted {bad!r}")
print("ok")
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "dots allowed inside a filename TOKEN, never in a directory COMPONENT, '..' in neither" \
  || no "the two-rule split is not holding: $out"

# sanitize_component is the ONLY repairing function, and only for ids we mint ourselves
# (A8). It must keep CJK, or every Chinese filename folds onto the same 'src'.
set +e
out="$(python3 - "$ORG" <<'PYEOF' 2>&1
import importlib, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
ps = importlib.import_module("_pathsafe")
assert ps.sanitize_component("血常规报告") == "血常规报告"
assert ps.sanitize_component("病理报告") == "病理报告"
assert ps.sanitize_component("血常规报告") != ps.sanitize_component("病理报告")
assert ps.sanitize_component("...") == "src"
assert ps.sanitize_component("") == "src"
assert ps.sanitize_component("../../etc/passwd") not in (".", "..")
assert "/" not in ps.sanitize_component("../../etc/passwd")
print("ok")
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "sanitize_component keeps CJK distinct and folds only the unusable to 'src' (A8)" \
  || no "sanitize_component collapses names it must keep apart: $out"

# ---------------------------------------------------------------------------
echo
echo "== pathsafe: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
