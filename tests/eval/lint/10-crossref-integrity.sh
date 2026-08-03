#!/usr/bin/env bash
# Cross-cutting — cross-file reference integrity.
#
# Static, fully automatable. A cross-file pointer is a load-bearing part of the
# safety contract: `organize/SKILL.md` tells the reader that the full citation
# spec lives in the router's 「来源引用」节 and then stops explaining. If that
# section does not exist, the contract silently has a hole — and nothing else
# catches it, because prose pointers are invisible to every other lint.
#
# Two assertions:
#   A. Section pointers resolve. Two written forms are recognized:
#        `X.md` …「Y」节        (quoted section name, 节 suffix)
#        `X.md` → Y             (arrow; a non-ASCII target is a section name,
#                                a pure-ASCII one is a file handoff and skipped)
#      For each: X must exist on disk AND X must carry a heading matching Y.
#   B. Relative markdown links resolve. Every `](path)` target that is not a
#      URL / mailto / bare anchor must exist on disk (anchor suffix stripped).
#
# Scope. Everything under the repo is scanned, but violations are reported in
# two tiers, because a broken pointer means different things in different files:
#   * BINDING  (skills/, references/, scripts/, tests/, root README/INSTALL/…)
#     — these are instructions a model will actually follow at answer time. A
#     dangling pointer here is a real hole → FAIL.
#   * ADVISORY (CHANGELOG.md, docs/, tasks/) — historical and design records. A
#     changelog entry naming a file that was later deleted was true when
#     written, and a PRD quoting `X.md`「Y」节 as metasyntax is describing this
#     very lint. Reported as WARN, not counted, so the gate stays meaningful
#     instead of being permanently red on history.
# Fenced code blocks are skipped everywhere: they hold illustrative snippets and
# dependency diagrams that quote broken pointers on purpose. A pointer only
# binds when written as prose.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0
warns=0

cd "$REPO_ROOT"

# All markdown, minus VCS/vendor noise.
MD_FILES=()
while IFS= read -r _p; do
  [[ -n "$_p" ]] && MD_FILES+=("$_p")
done < <(find . -type f -name '*.md' \
  -not -path './.git/*' \
  -not -path './node_modules/*' \
  | sed 's|^\./||' | sort)
unset _p

TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT

# report <source_file> <msg> — FAIL on the binding surface, WARN on records.
report() {
  case "$1" in
    CHANGELOG.md|docs/*|tasks/*) warns=$((warns+1)); echo "WARN: $2" >&2 ;;
    *) fail "$2" ;;
  esac
}

# ere_escape <string> — make a section name literal inside an ERE.
ere_escape() {
  printf '%s' "$1" | sed 's/[][\.*^$(){}?+|\\]/\\&/g'
}

# resolve_ref <referencing_file> <ref_path> — echo on-disk path, or fail.
resolve_ref() {
  local from_dir cand
  from_dir="$(dirname "$1")"
  for cand in "$from_dir/$2" "$2"; do
    if [[ -e "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

# check_section <file> <lineno> <ref_path> <section>
check_section() {
  local src="$1" lno="$2" ref="$3" sec="$4" target esc
  if ! target="$(resolve_ref "$src" "$ref")"; then
    report "$src" "$src:$lno: points at 「${sec}」 in \`$ref\` — that file does not exist"
    return
  fi
  esc="$(ere_escape "$sec")"
  if ! grep -qE "^#+ .*${esc}" "$target"; then
    report "$src" "$src:$lno: \`$ref\` has no heading matching 「${sec}」 (dangling section pointer)"
  fi
}

for f in "${MD_FILES[@]}"; do
  # prose = lines outside ``` fences, prefixed "lineno<TAB>".
  awk '
    /^[[:space:]]*```/ { fence = !fence; next }
    !fence { printf "%d\t%s\n", NR, $0 }
  ' "$f" > "$TMPD/prose"

  # -------------------------------------------------------------------------
  # A1. `X.md` …「Y」节 — the .md path nearest the quoted name wins.
  # Candidate lines are pre-filtered with a cheap pattern; the expensive
  # extraction then runs on a handful of lines instead of the whole repo.
  # -------------------------------------------------------------------------
  while IFS=$'\t' read -r lno line; do
    [[ -z "${line:-}" ]] && continue
    while IFS= read -r m; do
      [[ -z "$m" ]] && continue
      sec="${m##*「}"; sec="${sec%%」*}"
      ref="$(printf '%s' "${m%%「*}" | grep -oE '[A-Za-z0-9_./-]+\.md' | tail -1 || true)"
      [[ -z "$ref" ]] && continue
      check_section "$f" "$lno" "$ref" "$sec"
    done < <(printf '%s' "$line" | grep -oE '[A-Za-z0-9_./-]+\.md[^「]{0,40}「[^」]+」节' || true)
  done < <(grep -E '\.md[^「]{0,40}「[^」]+」节' "$TMPD/prose" || true)

  # -------------------------------------------------------------------------
  # A2. `X.md` → Y
  # -------------------------------------------------------------------------
  while IFS=$'\t' read -r lno line; do
    [[ -z "${line:-}" ]] && continue
    while IFS= read -r m; do
      [[ -z "$m" ]] && continue
      ref="$(printf '%s' "${m%%→*}" | grep -oE '[A-Za-z0-9_./-]+\.md' | tail -1 || true)"
      [[ -z "$ref" ]] && continue
      sec="${m#*→}"
      sec="$(printf '%s' "$sec" | sed 's/^[[:space:]`]*//; s/[[:space:]`]*$//')"
      sec="${sec#「}"; sec="${sec%」}"
      [[ -z "$sec" ]] && continue
      # pure-ASCII target = file/identifier handoff, not a section pointer
      [[ "$sec" =~ ^[A-Za-z0-9_./+-]+$ ]] && continue
      check_section "$f" "$lno" "$ref" "$sec"
    done < <(printf '%s' "$line" | grep -oE '`[A-Za-z0-9_./-]+\.md`[[:space:]]*→[[:space:]]*`?[^ ，。；、）)|]+' || true)
  done < <(grep -F '→' "$TMPD/prose" || true)

  # -------------------------------------------------------------------------
  # B. relative markdown links resolve
  # -------------------------------------------------------------------------
  while IFS=$'\t' read -r lno line; do
    [[ -z "${line:-}" ]] && continue
    while IFS= read -r m; do
      [[ -z "$m" ]] && continue
      tgt="${m#](}"; tgt="${tgt%)}"
      tgt="${tgt%%#*}"          # strip anchor
      tgt="${tgt%% *}"          # strip link title
      [[ -z "$tgt" ]] && continue
      case "$tgt" in
        http://*|https://*|mailto:*|tel:*|\#*|/*|\$*|\<*|*'{{'*|*'<'*) continue ;;
      esac
      resolve_ref "$f" "$tgt" >/dev/null \
        || report "$f" "$f:$lno: relative link target \`$tgt\` does not exist"
    done < <(printf '%s' "$line" | grep -oE '\]\([^)]+\)' || true)
  done < <(grep -F '](' "$TMPD/prose" || true)
done

(( warns > 0 )) && echo "$warns advisory warning(s) in CHANGELOG/docs/tasks (not counted)" >&2
summarize "crossref-integrity"
