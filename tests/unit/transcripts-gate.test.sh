#!/usr/bin/env bash
# tests/unit/transcripts-gate.test.sh — organize v3, gate_transcripts + Q8 containment.
#
# `raw/transcript/<source_id>/page-NNN.md` is the VERBATIM, UNMASKED page
# transcription. It lives under raw/ so it inherits the vault's access control, and
# three things must stay true:
#
#   1. a declared transcript_path exists on disk — a promise is not a record, and a
#      transcript that is only claimed breaks the whole faithfulness chain;
#   2. the MASKED bucket sidecar derived from it carries no unmasked PII shapes —
#      the transcript is the only place unmasked text may exist, the sidecar is the
#      only surface anything downstream reads;
#   3. nothing outside raw/ mentions `raw/transcript/` except the two registries
#      whose job is to record it. Handing a downstream reader the path is an
#      invitation to open it, which routes the unmasked page around the access control.
#
# Q8 is asserted alongside, and fix spec A15 narrowed it to what it actually forbids:
# DERIVING a formal fact from the open projection. A derivation shows up in exactly two
# places — a `source_refs`/anchor pointing at `extracted_fields.json`, or a chart
# declaring it as a data source — and both are ERRORs. Prose is NOT one of them: the
# previous version failed any formal file whose bytes contained the string anywhere,
# which caught the breach and also caught a reviewer's note explaining that a value was
# deliberately NOT taken from the open store. Punishing the sentence that documents the
# rule teaches producers to stop writing it, so this file now pins BOTH directions.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

run_gate() {  # <gate_fn> <patient_dir>
  set +e
  out="$(python3 - "$ORG" "$1" "$2" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
errs = []
getattr(v, sys.argv[2])(pathlib.Path(sys.argv[3]), errs)
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  rc=$?
  set -e
}

# a full v3 inventory row for a transcribed pixel page
write_inv() {  # <dir> <sidecar> <transcript_path-or-empty>
  local tp=""
  [ -n "${3:-}" ] && tp="\"transcript_path\":\"$3\","
  cat > "$1/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.pdf",
   "raw_path":"raw/incoming/upload-001.pdf","page_range":null,
   "kind":"known","doc_kind":"检验报告","clinical_class":"lab",
   "text_layer_kind":"absent",$tp
   "sidecar_path":"$2","bucket_path":"$(dirname "$2")",
   "modality":"text","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"host-vision","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"needs_human_review","adapter":"pdf_pages","persist":true} ]}
EOF
}

scaffold() {  # <dir>
  mkdir -p "$1/07_检验/血常规" "$1/raw/incoming" "$1/raw/transcript/s1"
  : > "$1/raw/incoming/upload-001.pdf"
  cat > "$1/07_检验/血常规/2026-03-15_血常规.md" <<'EOF'
SOURCE: lab | CONFIDENCE: medium
ORIGINAL: raw/incoming/upload-001.pdf
| 项目 | 结果 | 参考 |
| 白细胞计数 | 3.21 | 3.50-9.50 |
EOF
}

# ===========================================================================
# A. a declared transcript must exist
# ===========================================================================
echo "=== A. transcript_path declared but absent ==="

d="$tmp/absent"
scaffold "$d"
write_inv "$d" "07_检验/血常规/2026-03-15_血常规.md" "raw/transcript/s1/page-001.md"
run_gate gate_transcripts "$d"
[ "$rc" -eq 1 ] && ok "declared-but-missing transcript → exit 1" \
  || no "missing transcript must block, got rc=$rc"
echo "$out" | grep -q 'transcript_path not found on disk' \
  && ok "…error names the missing path" || no "wrong reason: $out"
echo "$out" | grep -q 'faithfulness chain' \
  && ok "…error states what the absence breaks" || no "consequence not stated: $out"

# POSITIVE — same archive with the transcript actually written
cat > "$d/raw/transcript/s1/page-001.md" <<'EOF'
---
source_id: s1
page: 1
---
# 全文
白细胞计数 3.21 10^9/L
联系电话 13800000000
EOF
run_gate gate_transcripts "$d"
[ "$rc" -eq 0 ] && ok "transcript present + masked sidecar clean → exit 0" \
  || no "valid transcript archive blocked: $out"

# a transcript_path that does not live under raw/transcript/ is rejected outright
d2="$tmp/wrong_prefix"
scaffold "$d2"
mkdir -p "$d2/ocr/s1"
: > "$d2/ocr/s1/page-001.md"
write_inv "$d2" "07_检验/血常规/2026-03-15_血常规.md" "ocr/s1/page-001.md"
run_gate gate_transcripts "$d2"
[ "$rc" -eq 1 ] && ok "transcript_path outside raw/transcript/ → exit 1" \
  || no "off-vault transcript_path accepted, rc=$rc"
echo "$out" | grep -q 'must live under raw/transcript/' \
  && ok "…error states the vault location rule" || no "wrong reason: $out"

# ===========================================================================
# B. the masked sidecar must actually be masked
# ===========================================================================
echo "=== B. unmasked PII shape in the bucket sidecar ==="

d="$tmp/leaky_sidecar"
scaffold "$d"
cat > "$d/raw/transcript/s1/page-001.md" <<'EOF'
---
source_id: s1
page: 1
---
# 全文
白细胞计数 3.21 10^9/L
EOF
# an unmasked phone shape left in the DERIVED, downstream-readable surface
cat >> "$d/07_检验/血常规/2026-03-15_血常规.md" <<'EOF'
联系电话：13800000000
EOF
write_inv "$d" "07_检验/血常规/2026-03-15_血常规.md" "raw/transcript/s1/page-001.md"
run_gate gate_transcripts "$d"
[ "$rc" -eq 1 ] && ok "unmasked phone shape in the masked sidecar → exit 1" \
  || no "unmasked PII in a derived sidecar accepted, rc=$rc"
echo "$out" | grep -q 'unmasked PII shape' && ok "…error names the leak" || no "wrong reason: $out"
echo "$out" | grep -q 'PII_MASKED' \
  && ok "…error states the remedy (mask to [PII_MASKED], clinical characters untouched)" \
  || no "remedy not stated: $out"

# ===========================================================================
# C. containment — nothing downstream may name the vault
# ===========================================================================
echo "=== C. raw/transcript/ containment ==="

d="$tmp/leak_path"
scaffold "$d"
cat > "$d/raw/transcript/s1/page-001.md" <<'EOF'
---
source_id: s1
page: 1
---
# 全文
白细胞计数 3.21 10^9/L
EOF
write_inv "$d" "07_检验/血常规/2026-03-15_血常规.md" "raw/transcript/s1/page-001.md"

# C1. a formal JSON handing a downstream reader the vault path
cat > "$d/timeline.json" <<'EOF'
{ "patient_code":"PT-TR1","schema_version":"1","events":[
  {"date":"2026-03-15","event":"血常规","note":"逐字版见 raw/transcript/s1/page-001.md",
   "source_refs":["07_检验/血常规/2026-03-15_血常规.md"]} ]}
EOF
run_gate gate_transcripts "$d"
[ "$rc" -eq 1 ] && ok "timeline.json naming raw/transcript/ → exit 1" \
  || no "vault path leaked into a formal JSON and was accepted, rc=$rc"
echo "$out" | grep -q 'must never be reachable from a downstream-readable surface' \
  && ok "…error states the containment rule" || no "wrong reason: $out"
echo "$out" | grep -q 'source_inventory.json' \
  && ok "…error names the registries that ARE allowed to record it" \
  || no "allowed registries not named: $out"
rm -f "$d/timeline.json"

# C2. an AGENTS.md / markdown surface is scanned too
cat > "$d/AGENTS.md" <<'EOF'
# Patient archive pointer
Verbatim pages: raw/transcript/s1/
EOF
run_gate gate_transcripts "$d"
[ "$rc" -eq 1 ] && ok "AGENTS.md naming raw/transcript/ → exit 1" \
  || no "vault path in AGENTS.md accepted, rc=$rc"
rm -f "$d/AGENTS.md"

# C3. POSITIVE — source_inventory.json is exactly the registry allowed to record it
run_gate gate_transcripts "$d"
[ "$rc" -eq 0 ] && ok "source_inventory.json may record transcript_path (it is the registry)" \
  || no "the registry itself was flagged: $out"

# C4. files INSIDE raw/ may self-reference
cat > "$d/raw/transcript/s1/page-002.md" <<'EOF'
continued from raw/transcript/s1/page-001.md
EOF
run_gate gate_transcripts "$d"
[ "$rc" -eq 0 ] && ok "self-reference inside raw/ is fine (already behind the access control)" \
  || no "raw/-internal self-reference flagged: $out"

# ===========================================================================
# D. Q8 — extracted_fields.json is not a legal source library
# ===========================================================================
echo "=== D. Q8: no formal output may cite extracted_fields ==="

d="$tmp/q8"
scaffold "$d"
cat > "$d/raw/transcript/s1/page-001.md" <<'EOF'
---
source_id: s1
page: 1
---
# 全文
白细胞计数 3.21
EOF
write_inv "$d" "07_检验/血常规/2026-03-15_血常规.md" "raw/transcript/s1/page-001.md"
# D1 NEGATIVE — the breach as it actually happens: a source_ref pointing at the open store
cat > "$d/labs.json" <<'EOF'
{ "patient_code":"PT-00Q8","schema_version":"2","panels":[
  {"analyte":"双歧杆菌属相对丰度","values":[
    {"date":"2026-03-15","value":4.7,"raw_value":"4.7","unit":"%",
     "reference_range":"2.0-8.0%","report_flag":null,"critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "source_refs":["extracted_fields.json#entries/3"]}]} ]}
EOF
run_gate gate_extracted_fields "$d"
[ "$rc" -eq 1 ] && ok "labs.json whose source_refs cite extracted_fields.json → exit 1 (Q8)" \
  || no "Q8 containment breach accepted, rc=$rc"
echo "$out" | grep -q 'NOT a legal' && ok "…error states extracted_fields is not a source library" \
  || no "wrong reason: $out"
echo "$out" | grep -q 'Q8' && ok "…error cites the decision it enforces" || no "Q8 not cited: $out"
echo "$out" | grep -q 'source_refs' \
  && ok "…error names the citation that carries the derivation" || no "the offending ref is not located: $out"

# D1b NEGATIVE — the other derivation shape: a chart wired to the open store
cat > "$d/.case_summary_data.json" <<'EOF'
{"charts":[{"title":"菌群趋势","data_source":"extracted_fields.json","series":[]}]}
EOF
run_gate gate_extracted_fields "$d"
[ "$rc" -eq 1 ] && ok "a chart declaring extracted_fields.json as its data source → exit 1" \
  || no "a chart fed from the open projection was accepted, rc=$rc"
echo "$out" | grep -q 'never feeds a chart' \
  && ok "…error states an open field has no trend line" || no "chart rationale absent: $out"
rm -f "$d/.case_summary_data.json"

# D1c POSITIVE (fix spec A15) — PROSE naming the file is NOT a breach. This is the
# regression arm: the sentence below documents the rule being enforced, and a gate that
# fails it is teaching producers to delete their own audit trail.
cat > "$d/labs.json" <<'EOF'
{ "patient_code":"PT-00Q8","schema_version":"2","panels":[
  {"analyte":"双歧杆菌属相对丰度","values":[
    {"date":"2026-03-15","value":4.7,"raw_value":"4.7","unit":"%",
     "reference_range":"2.0-8.0%","report_flag":null,"critical_flag":null,
     "provenance_layer":"source_reported","verification_status":"unverified",
     "note":"值取自该源 sidecar 原文，未采用 extracted_fields.json 中的开放读数（Q8）",
     "source_refs":["07_检验/血常规/2026-03-15_血常规.md"]}]} ]}
EOF
run_gate gate_extracted_fields "$d"
[ "$rc" -eq 0 ] && ok "a prose note MENTIONING extracted_fields.json → exit 0 (A15: only citations bind)" \
  || no "prose was punished as a containment breach: $out"

# the check fires whether or not the file exists — a formal output citing a store
# that is not even there is the same breach
[ ! -f "$d/extracted_fields.json" ] \
  && ok "…and it fired with no extracted_fields.json on disk at all" \
  || no "fixture unexpectedly has an extracted_fields.json"

# POSITIVE — and with no mention at all, obviously silent
python3 - "$d/labs.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["panels"][0]["values"][0].pop("note", None)
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF
run_gate gate_extracted_fields "$d"
[ "$rc" -eq 0 ] && ok "labs.json with no extracted_fields reference → exit 0" \
  || no "clean archive still flagged by the Q8 check: $out"

# D2 — the markdown surface obeys the same split: an ANCHOR into the open store is a
# breach, a sentence naming it is not (Q7/Q8 are about what a fact RESTS on).
printf -- '# 时间线\n\n- 2026-03-15 菌群丰度 4.7%% [[src:extracted_fields.json]]\n' > "$d/timeline.md"
run_gate gate_extracted_fields "$d"
[ "$rc" -eq 1 ] && ok "[[src:extracted_fields.json]] in timeline.md → exit 1" \
  || no "a narrative anchor into the open projection was accepted, rc=$rc"
printf -- '# 时间线\n\n- 2026-03-15 菌群丰度 4.7%%（开放读数见 extracted_fields.json，未作为本行来源）\n' > "$d/timeline.md"
run_gate gate_extracted_fields "$d"
[ "$rc" -eq 0 ] && ok "the same file merely NAMING it in prose → exit 0" \
  || no "prose in a markdown surface was punished: $out"
rm -f "$d/timeline.md"

# ---------------------------------------------------------------------------
echo
echo "== transcripts-gate: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
