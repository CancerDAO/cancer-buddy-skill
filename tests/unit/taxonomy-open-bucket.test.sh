#!/usr/bin/env bash
# tests/unit/taxonomy-open-bucket.test.sh — organize v3 / taxonomy scheme_version 4.
#
# Domain 15 (`15_未分类资料` / `15_unclassified`) is the ONLY open domain: its
# sub-bucket slug is written by a model out of the document's own — untrusted —
# text. That makes the slug a security boundary, not a naming convention. This
# suite pins both halves of the rule from bucket_taxonomy.json:
#
#   shape        open_sub_bucket_slug_regex (CJK/Latin/digits/hyphen, 2-24 chars,
#                must start alphanumeric-or-CJK) — no separators, no '..', no
#                dotfiles, no NN_ prefix, no control characters.
#   impersonation  reserved_sub_bucket_names — a slug that merely *looks* fine but
#                equals a pinned clinical slug, an infra dir or the universal
#                fallback would let an open, model-named directory re-route sources
#                past the closed-world gates that guard that name.
#
# Every case asserts the gate's EXIT CODE as well as its message: a gate checked
# only through grep keeps "passing" every negative case the day it stops collecting.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok()  { pass=$((pass+1)); echo "  ok   — $1"; }
no()  { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# run gate_bucket_taxonomy on a dir; stdout = violations, exit 1 when any.
gate() {
  set +e
  out="$(python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
v.gate_bucket_taxonomy(pathlib.Path(sys.argv[2]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# Directly exercise _open_sub_bucket_violation for slugs a filesystem cannot hold
# ('..', a name containing '/', a control character). Those are exactly the inputs
# a model could emit into a mkdir call, so they must be rejected BEFORE any dir
# exists — the on-disk scan can never see them.
slug_violation() {
  python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib, json, re
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
tax = json.loads(v.BUCKET_TAXONOMY_JSON.read_text(encoding="utf-8"))
slug_re = re.compile(tax.get("open_sub_bucket_slug_regex") or v._DEFAULT_OPEN_SLUG_RE)
reserved = v._reserved_sub_bucket_names(tax)
why = v._open_sub_bucket_violation(sys.argv[2], slug_re, reserved)
print(why if why else "")
PYEOF
}

mk() { mkdir -p "$1"; }

# ===========================================================================
# POSITIVE — a real open filing is accepted, and so is the pinned fallback.
# ===========================================================================
echo "=== A. positive: an open slug the model was allowed to write ==="

p1="$tmp/open_ok"
mk "$p1/15_未分类资料/肠道菌群检测"
: > "$p1/15_未分类资料/肠道菌群检测/report.md"
gate "$p1"
[ -z "$out" ] && ok "15_未分类资料/肠道菌群检测/ accepted (open domain, legal slug)" \
  || no "legal open slug rejected: $out"
[ "$rc" -eq 0 ] && ok "legal open slug → gate exits 0" || no "legal open slug → gate exited $rc"

# 14_ is a CLOSED domain; 其他/other is the universal fallback and stays legal there.
p2="$tmp/fallback_ok"
mk "$p2/14_患者自管补充/其他"
gate "$p2"
[ -z "$out" ] && ok "14_患者自管补充/其他 still accepted (universal fallback, closed domain)" \
  || no "universal fallback rejected under a closed domain: $out"
[ "$rc" -eq 0 ] && ok "universal fallback → gate exits 0" || no "universal fallback → gate exited $rc"

# en-locale open domain behaves identically
p3="$tmp/open_en"
mk "$p3/15_unclassified/gut-microbiome"
gate "$p3"
[ -z "$out" ] && ok "15_unclassified/gut-microbiome accepted (en locale, hyphen legal)" \
  || no "en-locale open slug rejected: $out"

# the open domain's own fallback + ASCII infra children stay legal
p4="$tmp/open_infra"
mk "$p4/15_未分类资料/其他" "$p4/15_未分类资料/high_confidence"
gate "$p4"
[ -z "$out" ] && ok "open domain still accepts 其他/ and high_confidence/" \
  || no "open domain rejected its own fallback/infra children: $out"

# ===========================================================================
# NEGATIVE — every way an untrusted slug can go wrong.
# ===========================================================================
echo "=== B. negative: shape abuse, impersonation, off-taxonomy domain ==="

# B1. `raw` — reserved even though it is an ASCII infra dir elsewhere. Under an
#     OPEN domain a directory literally named `raw` impersonates the vault.
p="$tmp/neg_raw"; mk "$p/15_未分类资料/raw"
gate "$p"
[ "$rc" -eq 1 ] && ok "15_未分类资料/raw → gate exits 1" || no "15_未分类资料/raw must exit 1, got $rc"
echo "$out" | grep -q '15_未分类资料/raw' && ok "…names the offending path" || no "does not name 15_未分类资料/raw"
echo "$out" | grep -q 'reserved' && ok "…message cites the reserved-name rule" \
  || no "message does not cite reserved names: $out"

# B2. `07_检验` — an NN_ prefix inside the open domain. The slug rules must be
#     quoted so an operator knows WHICH rule was broken.
p="$tmp/neg_nn"; mk "$p/15_未分类资料/07_检验"
gate "$p"
[ "$rc" -eq 1 ] && ok "15_未分类资料/07_检验 → gate exits 1" || no "NN_-prefixed open slug must exit 1, got $rc"
echo "$out" | grep -q 'NN_' && ok "…message names the NN_-prefix rule" || no "NN_ rule not named: $out"
echo "$out" | grep -q 'open_sub_bucket_slug_regex' \
  && ok "…message cites open_sub_bucket_slug_regex" || no "slug regex not cited: $out"

# B3. over-length slug (25 chars > the 24 max)
long="$(python3 -c 'print("a"*25)')"
p="$tmp/neg_long"; mk "$p/15_未分类资料/$long"
gate "$p"
[ "$rc" -eq 1 ] && ok "25-char open slug → gate exits 1" || no "over-length slug must exit 1, got $rc"
echo "$out" | grep -qE '25 characters long|max 24' && ok "…message states the length limit" \
  || no "length limit not stated: $out"

# B4. collides with a PINNED sub-bucket slug (血常规 belongs to 07_检验). Filing a
#     lab panel under 15_未分类资料/血常规 would make an open dir look closed-world.
p="$tmp/neg_pinned"; mk "$p/15_未分类资料/血常规"
gate "$p"
[ "$rc" -eq 1 ] && ok "15_未分类资料/血常规 (pinned slug collision) → gate exits 1" \
  || no "pinned-slug collision must exit 1, got $rc"
echo "$out" | grep -q 'reserved' && ok "…message cites the impersonation rule" \
  || no "impersonation rule not cited: $out"

# B5. dotfile namespace
p="$tmp/neg_dot"; mk "$p/15_未分类资料/.hidden"
gate "$p"
[ "$rc" -eq 1 ] && ok "15_未分类资料/.hidden → gate exits 1" || no "dotfile slug must exit 1, got $rc"

# B6. `16_xxx` at top level — 15_ is the LAST domain; 16_ is not a domain at all.
p="$tmp/neg_16"; mk "$p/16_xxx"
gate "$p"
[ "$rc" -eq 1 ] && ok "top-level 16_xxx → gate exits 1" || no "16_xxx must exit 1, got $rc"
echo "$out" | grep -q "top-level dir '16_xxx'" && ok "…flagged as an off-taxonomy top-level domain" \
  || no "16_xxx not flagged as a top-level violation: $out"
echo "$out" | grep -qE '01_\.\.15_|valid domains' && ok "…message says which domain numbers exist" \
  || no "message does not state the valid domain range: $out"

# B7. an open slug is NOT a licence for the whole tree: a non-pinned sub-bucket
#     under a CLOSED domain must still fail.
p="$tmp/neg_closed"; mk "$p/06_分子与组学/基因检测"
gate "$p"
[ "$rc" -eq 1 ] && ok "closed domain still rejects a non-pinned sub-bucket" \
  || no "closed-domain sub-bucket drift must exit 1, got $rc"
echo "$out" | grep -q 'not a pinned sub-bucket' && ok "…closed-domain message is the pinned-slug one" \
  || no "closed domain used the open-domain message: $out"

echo "=== C. negative: slugs no filesystem can hold (checked at the API) ==="

check_slug() {  # name, expected-substring, label
  local why; why="$(slug_violation "$1")"
  if [[ -z "$why" ]]; then
    no "$3 — slug '$1' was ACCEPTED"
  elif echo "$why" | grep -qF "$2"; then
    ok "$3 — rejected: $why"
  else
    no "$3 — rejected for the wrong reason: $why"
  fi
}

check_slug '..'            "path traversal"        "'..' (traversal)"
check_slug '../x'          "path traversal"        "'../x' (traversal)"
check_slug 'a/b'           "path separator"        "slug containing '/'"
check_slug 'a\b'           "path separator"        "slug containing backslash"
check_slug "$(printf 'ab\tc')" "control character" "slug containing a control character"
check_slug 'transcript'    "reserved"              "'transcript' (the verbatim vault name)"

# `_cache` and `AGENTS.md` are on the reserved list AND fail the shape rule (leading
# '_' / an embedded '.'). Which rule fires first is an implementation detail; that they
# are rejected at all is the contract, so only that is asserted.
for _name in '_cache' '_provenance' 'AGENTS.md' '.git'; do
  _why="$(slug_violation "$_name")"
  [ -n "$_why" ] && ok "'$_name' rejected ($_why)" || no "'$_name' accepted as an open slug"
done
unset _name _why

# positive at the API level too: the legal slug must produce NO violation string
why_ok="$(slug_violation '肠道菌群检测')"
[ -z "$why_ok" ] && ok "'肠道菌群检测' passes the slug API cleanly" \
  || no "legal slug rejected at the API: $why_ok"
why_ok2="$(slug_violation 'gut-microbiome')"
[ -z "$why_ok2" ] && ok "'gut-microbiome' passes the slug API cleanly" \
  || no "legal en slug rejected at the API: $why_ok2"

# ---------------------------------------------------------------------------
echo
echo "== taxonomy-open-bucket: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
