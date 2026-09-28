#!/usr/bin/env bash
# tests/eval/hooks/pre-push-real-phrases.sh (local pre-push hook): every commit a push would publish —
# its added/changed blobs and its message — is checked against the private phrase list; a phrase that
# one commit adds and a later commit removes is still refused; commits already on a remote-tracking ref
# are not rescanned; the output never echoes the phrase. Every phrase below is invented for this test.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/tests/eval/hooks/pre-push-real-phrases.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); }
bad() { fail=$((fail+1)); echo "FAIL: $1" >&2; }
Z=0000000000000000000000000000000000000000

r="$tmp/repo"; mkdir -p "$r"
g() { git -C "$r" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false "$@"; }
g init -q -b main
printf '合成正文\n' > "$r/a.md"; g add a.md; g commit -qm "base"
base=$(g rev-parse HEAD)
g update-ref refs/remotes/origin/main "$base"          # base is already published
printf '# 私有清单（测试用，全部虚构）\n虚构短语 壬癸子丑寅\n' > "$tmp/list.txt"

hook() {  # stdin line(s) → rc; output in $out
  out="$(cd "$r" && printf '%s\n' "$@" | CB_REAL_PHRASES_FILE="$tmp/list.txt" bash "$HOOK" 2>&1)"
}

# positive: a clean new commit on a new branch → exit 0
printf '合成正文\n第二行\n' > "$r/a.md"; g commit -qam "clean change"
clean=$(g rev-parse HEAD)
hook "refs/heads/main $clean refs/heads/main $base"; [ $? -eq 0 ] && ok || bad "clean commit → exit 0: $out"
(cd "$r" && printf 'refs/heads/f %s refs/heads/f %s\n' "$clean" "$Z" | CB_REAL_PHRASES_FILE="$tmp/list.txt" bash "$HOOK" >/dev/null 2>&1) \
  && ok || bad "clean new branch → exit 0"

# negative: commit A adds the phrase, commit B removes it — the push still publishes A → exit 1
printf '合成正文\n这里写着虚构短语壬癸子丑寅。\n' > "$r/b.md"; g add b.md; g commit -qm "add"
a_sha=$(g rev-parse HEAD)
printf '合成正文\n' > "$r/b.md"; g commit -qam "remove"
b_sha=$(g rev-parse HEAD)
hook "refs/heads/main $b_sha refs/heads/main $base"; rc=$?
[ $rc -eq 1 ] && ok || bad "phrase added then removed within the pushed range → exit 1 ($rc)"
echo "$out" | grep -q "${a_sha:0:10} b.md:2 contains phrase #2" && ok || bad "hit names commit, file:line and list index: $out"
echo "$out" | grep -q "壬癸子丑寅" && bad "the phrase itself must never be printed" || ok
hook "refs/heads/topic $b_sha refs/heads/topic $Z"; [ $? -eq 1 ] && ok || bad "same range on a new remote branch → exit 1"

# positive: once A is published (on a remote-tracking ref), pushing only what follows it → exit 0
g update-ref refs/remotes/origin/main "$a_sha"
hook "refs/heads/main $b_sha refs/heads/main $a_sha"; [ $? -eq 0 ] && ok || bad "published history is not rescanned: $out"

# negative: the phrase only in a commit message → exit 1
g commit -q --allow-empty -m "说明：虚构短语壬癸子丑寅"
m_sha=$(g rev-parse HEAD)
hook "refs/heads/main $m_sha refs/heads/main $b_sha"; [ $? -eq 1 ] && echo "$out" | grep -q "commit message" && ok \
  || bad "phrase in a commit message → exit 1: $out"

# deleting a remote branch publishes nothing → exit 0
hook "(delete) $Z refs/heads/old $b_sha"; [ $? -eq 0 ] && ok || bad "branch deletion → exit 0: $out"

# no list → refused (fail closed)
out="$(cd "$r" && printf 'refs/heads/main %s refs/heads/main %s\n' "$clean" "$base" | CB_REAL_PHRASES_FILE="$tmp/none.txt" bash "$HOOK" 2>&1)"
[ $? -eq 1 ] && ok || bad "missing list → exit 1"
# default list location: <git-common-dir>/info/real-phrases.txt
cp "$tmp/list.txt" "$r/.git/info/real-phrases.txt"
out="$(cd "$r" && printf 'refs/heads/main %s refs/heads/main %s\n' "$b_sha" "$base" | env -u CB_REAL_PHRASES_FILE bash "$HOOK" 2>&1)"
[ $? -eq 1 ] && ok || bad "default list in .git/info is used: $out"

echo "pre-push-real-phrases: $pass passed, $fail failed"
[ $fail -eq 0 ]
