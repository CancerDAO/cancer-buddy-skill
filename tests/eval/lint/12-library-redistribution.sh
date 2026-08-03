#!/usr/bin/env bash
# Cross-cutting — reference-library redistribution safety.
#
# Static, fully automatable. Two failure modes this repo can ship by accident,
# neither of which any other lint sees:
#
#   A. L1 (`skills/cancer-buddy/references/library/`) travels with the repo.
#      Every byte in it is redistributed to every install, every fork and the
#      public GitHub mirror. So an L1 index entry may only ever be
#      `redistribution: allowed`. `restricted` means "we hold a licensed copy,
#      it may not be handed on" — that belongs in L2/L3 (the user's own disk),
#      never in git. `unknown` is the same risk with the label filed off, and a
#      missing field is `unknown` written in invisible ink. All three fail.
#
#   B. The L2 example manifest is a *template*. Shipping it with concrete
#      restricted-publisher paths (`nccn/…`, `csco/…`) reads as "these files
#      come with the skill" and nudges the user to name real licensed packs in
#      a file that lives in a public repo. The example must teach the field
#      structure with neutral placeholders and nothing else. The structure
#      itself is asserted too, so "neutralize" cannot degrade into "gut".
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

L1_INDEX="$SKILLS_DIR/cancer-buddy/references/library/index.json"
EXAMPLE="$SKILLS_DIR/cancer-buddy-education/references/guideline-pack.example.json"

# ---------------------------------------------------------------------------
# A. L1 index: allowed-only. Conditional — L1 may legitimately not exist yet.
# ---------------------------------------------------------------------------
if [[ -f "$L1_INDEX" ]]; then
  # A1. every declared redistribution value must be exactly "allowed".
  while IFS= read -r val; do
    [[ -z "$val" ]] && continue
    if [[ "$val" != "allowed" ]]; then
      fail "L1 index.json declares redistribution \"$val\" — L1 ships with the repo, only \"allowed\" may live there (move it to L2/L3)"
    fi
  done < <(grep -oE '"redistribution"[[:space:]]*:[[:space:]]*"[^"]*"' "$L1_INDEX" \
            | sed 's/.*"\([^"]*\)"$/\1/' || true)

  # A2. a missing field is `unknown` in disguise — every entry must declare it.
  n_entries=$(grep -cE '"(file|dataset)"[[:space:]]*:' "$L1_INDEX" || true)
  n_redis=$(grep -cE '"redistribution"[[:space:]]*:' "$L1_INDEX" || true)
  if (( n_entries > n_redis )); then
    fail "L1 index.json: $n_entries entr(ies) but only $n_redis redistribution declaration(s) — an undeclared entry is \"unknown\" and may not ship in L1"
  fi
fi

# ---------------------------------------------------------------------------
# B. L2 example manifest: neutral placeholders, structure intact.
# ---------------------------------------------------------------------------
if [[ ! -f "$EXAMPLE" ]]; then
  fail "guideline-pack.example.json is missing — the L2 manifest template is part of the contract"
else
  # B1. no concrete restricted-publisher paths in `file` values.
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if printf '%s' "$path" | grep -qiE '(^|/)(nccn|csco|asco|esmo|nice)/'; then
      fail "guideline-pack.example.json: file \"$path\" names a specific restricted publisher — use a neutral placeholder (e.g. example-publisher/example-guideline-2026.pdf)"
    fi
  done < <(grep -oE '"file"[[:space:]]*:[[:space:]]*"[^"]*"' "$EXAMPLE" \
            | sed 's/.*"\([^"]*\)"$/\1/' || true)

  # B2. the example must still teach the full field structure.
  for field in file publisher title version date jurisdiction cancer_types license; do
    grep -qE "\"$field\"[[:space:]]*:" "$EXAMPLE" \
      || fail "guideline-pack.example.json: lost the \"$field\" field — the template must keep the full structure"
  done

  # B3. a template with no entries teaches nothing.
  n_ex=$(grep -cE '"file"[[:space:]]*:' "$EXAMPLE" || true)
  (( n_ex >= 1 )) || fail "guideline-pack.example.json: no example entry left"
fi

summarize "library-redistribution"
