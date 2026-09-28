#!/usr/bin/env bash
# tests/eval/lint/14-real-phrase-denylist.sh: a phrase from a PRIVATE list (kept outside the repo,
# CB_REAL_PHRASES_FILE) found in a scanned file fails the lint, and the failure output names the
# file, line and list index — never the phrase. Every phrase below is invented for this test.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LINT="$REPO_ROOT/tests/eval/lint/14-real-phrase-denylist.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); }
bad() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

mkdir -p "$tmp/scan/sub"
printf '合成正文第一行\n这里写着虚构短语甲乙丙丁戊，\n结束\n' > "$tmp/scan/sub/a.md"
printf '无关内容\n' > "$tmp/scan/b.md"
printf '# 私有清单（测试用，全部虚构）\n虚构短语 甲乙丙丁戊\n' > "$tmp/list_hit.txt"
printf '另一个不存在的虚构短语己庚辛\n' > "$tmp/list_miss.txt"
printf '# only comments\n甲乙\n' > "$tmp/list_short.txt"

# unset → SKIP, exit 0 (CI has no private list)
out="$(env -u CB_REAL_PHRASES_FILE bash "$LINT" 2>&1)"; rc=$?
[ $rc -eq 0 ] && echo "$out" | grep -q "SKIP" && ok || bad "unset list → SKIP exit 0 ($rc)"

# negative: a listed phrase (re-spaced in the list) is present → exit 1, phrase never echoed
out="$(CB_REAL_PHRASES_FILE="$tmp/list_hit.txt" CB_DENYLIST_ROOT="$tmp/scan" bash "$LINT" 2>&1)"; rc=$?
[ $rc -eq 1 ] && ok || bad "listed phrase present → exit 1 ($rc)"
echo "$out" | grep -q "sub/a.md:2 contains phrase #2" && ok || bad "hit names file:line and list index: $out"
echo "$out" | grep -q "甲乙丙丁戊" && bad "the phrase itself must never be printed" || ok

# positive: none of the listed phrases present → exit 0
out="$(CB_REAL_PHRASES_FILE="$tmp/list_miss.txt" CB_DENYLIST_ROOT="$tmp/scan" bash "$LINT" 2>&1)"; rc=$?
[ $rc -eq 0 ] && echo "$out" | grep -q "real-phrase-denylist OK" && ok || bad "no listed phrase → exit 0 ($rc): $out"

# a list with no usable (4+ character) phrase is refused rather than silently passing
out="$(CB_REAL_PHRASES_FILE="$tmp/list_short.txt" CB_DENYLIST_ROOT="$tmp/scan" bash "$LINT" 2>&1)"; rc=$?
[ $rc -eq 1 ] && ok || bad "empty/short list → exit 1 ($rc)"

# a missing list file is an error, not a skip
out="$(CB_REAL_PHRASES_FILE="$tmp/nope.txt" bash "$LINT" 2>&1)"; rc=$?
[ $rc -eq 1 ] && ok || bad "missing list file → exit 1 ($rc)"

echo "real-phrase-denylist: $pass passed, $fail failed"
[ $fail -eq 0 ]
