#!/usr/bin/env bash
# Dimension 6 — Never self-assess efficacy / treatment response.
#
# cancer-buddy MUST NOT judge, derive, or synthesize a treatment-response
# conclusion (RECIST CR/PR/SD/PD, 部分缓解/完全缓解/进展, "病灶缩小 X%").
# Response assessment is a clinician act. The system may only reproduce a
# response category the SOURCE stated verbatim (with citation); descriptive
# imaging (缩小/减轻) stays descriptive and is NEVER converted to a category.
#
# Real failure this guards against: a radiologist "病灶缩小/减轻" was
# synthesized into best_response=PR, propagated to 7 deliverables, and the
# education handbook then bolted on the RECIST definition "病灶缩小超过 30%"
# as if it were the patient's own measurement.
#
# Like the other lints this checks the *guardrail wiring* (static); the actual
# "did a generated report self-assess efficacy" is a runtime property → LLM-judge
# scenarios. Static assertions:
#   A. safety-guardrails.md carries the no-efficacy-self-assessment P0 rule.
#   B. organize Phase-2 synthesis prompt has the verbatim-only response rule
#      (best_response/response null when the source only has descriptive imaging).
#   C. Phase-2.5 faithfulness worker covers response labels, not just numbers.
#   D. treatment_lines schema documents best_response as source-stated-only.
#   E. case-summary + education prompts forbid the RECIST-definition gloss.
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0

SG="$REFS_DIR/safety-guardrails.md"
SYN="$SKILLS_DIR/cancer-buddy-organize/references/organizer-prompt-phase2-synthesis.md"
F25="$SKILLS_DIR/cancer-buddy-organize/references/organizer-prompt-phase2_5-faithfulness.md"
TLS="$SKILLS_DIR/cancer-buddy-organize/references/schemas/treatment_lines.schema.json"
CS="$SKILLS_DIR/cancer-buddy-organize/references/case-summary-html-prompt.md"
HB="$SKILLS_DIR/cancer-buddy-education/references/handbook-template.md"

# A. shared guardrail carries the P0 no-self-assess-efficacy rule.
[[ -f "$SG" ]] || fail "safety-guardrails.md not found"
if [[ -f "$SG" ]]; then
  grep -qiE '疗效|response is a clinician' "$SG" \
    || fail "safety-guardrails.md: no-efficacy-self-assessment rule absent"
  grep -qiE '缩小.*(PR|类别)|绝不.*(合成|推导).*疗效|描述性发现' "$SG" \
    || fail "safety-guardrails.md: descriptive-finding-is-not-a-response-category rule absent"
fi

# B. Phase-2 synthesis: verbatim-only response, null when only descriptive imaging.
[[ -f "$SYN" ]] || fail "phase2-synthesis prompt not found"
if [[ -f "$SYN" ]]; then
  grep -qiE 'best_response|latest_status\.response|响应类别' "$SYN" \
    || fail "phase2-synthesis: response verbatim-only rule absent"
  grep -qiE '绝不.*(合成|转写)|verbatim-only.*response|描述性影像' "$SYN" \
    || fail "phase2-synthesis: does not forbid synthesizing a response from descriptive imaging"
fi

# C. Phase-2.5 faithfulness covers response labels (not only numeric).
[[ -f "$F25" ]] || fail "phase2.5 faithfulness prompt not found"
if [[ -f "$F25" ]]; then
  grep -qiE 'best_response|response.*label|响应.*label|synthesized response' "$F25" \
    || fail "phase2.5: faithfulness check does not cover response/efficacy labels"
fi

# D. treatment_lines schema documents best_response as source-stated-only.
[[ -f "$TLS" ]] || fail "treatment_lines.schema.json not found"
if [[ -f "$TLS" ]]; then
  grep -qiE '逐字|source-stated|绝不.*合成|clinician' "$TLS" \
    || fail "treatment_lines schema: best_response lacks source-stated-only description"
fi

# E. case-summary + education forbid the RECIST-definition gloss.
[[ -f "$CS" ]] || fail "case-summary-html-prompt.md not found"
[[ -f "$CS" ]] && { grep -qiE '疗效红线|缩小超过 30%|定义式' "$CS" \
  || fail "case-summary: RECIST-definition-gloss ban absent"; }
[[ -f "$HB" ]] || fail "handbook-template.md not found"
[[ -f "$HB" ]] && { grep -qiE '疗效红线|不自行判疗效|缩小超过 30%' "$HB" \
  || fail "handbook: no-efficacy-self-assessment note absent"; }

summarize "no-efficacy-judgment"
