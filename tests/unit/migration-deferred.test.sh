#!/usr/bin/env bash
# tests/unit/migration-deferred.test.sh — organize v3→v4, fix spec B5 + B6.
#
# A migration is the one run that produces an archive NOBODY READ. migrate_v3_to_v4.py
# opens no page, calls no model, and touches no patient text — it rewrites metadata in
# place. That is what makes it safe, and it is also what makes its output a uniquely
# dangerous shape: a scheme-4 archive, passing every v4 gate, carrying two claims it
# cannot back up.
#
#   B5 — the semantic PII pass never ran. The v4 surface list (fix spec A17) is wider
#        than the one the archive was last scanned against, and the migration re-scanned
#        nothing, so the honest verdict is `pii_semantic: "deferred"`. Deferral is legal
#        here for the same reason it is legal for a text-only increment: the alternative
#        is that no pre-v4 archive can be migrated without first re-running organize over
#        the patient's whole history. What it must never buy is SILENCE. An update_log
#        entry is machine state that no human surface renders; a readiness review_flag is
#        what reaches the QC list and AGENTS.md. Write the first without the second and
#        the debt is indistinguishable from a pass nobody ran — permanently, because the
#        only record of it owing anything is a file people read when something is already
#        wrong.
#
#   B6 — the v3 `model_vision_*` rows have no transcript, and never will. v3 kept no
#        verbatim per-page transcription on disk, so `transcript_path` (required in v4 for
#        model-read sources) cannot be honestly synthesized and cannot be re-derived
#        without a new run. The row is therefore WAIVED — `legacy_transcript_unavailable:
#        true` exempts it from the schema requirement and from gate_transcripts. A waiver
#        with no price is an amnesty, so this one is paid for in the coverage number: the
#        source is counted in `projection_coverage.summary.unreadable_sources` and the
#        archive must carry a `coverage_gap` / `internal_qc` review flag. "Nothing can
#        ever re-read this page" is exactly the fact a coverage figure exists to surface,
#        and a migration that hid it would make an unverifiable source look identical to
#        a verified one on the only surface anybody reads.
#
# So both halves of this file assert the same shape from both directions: the paired
# artifact makes the archive PASS, and deleting just the visible half of the pair makes
# it FAIL. Only the positive arm would pass on a validator that never checked; only the
# negative arm would pass on a validator that rejects everything. The pairing is the
# mechanism, so the pairing is what is pinned.
#
# Section E pins idempotence. The first thing anyone does with a migration that printed
# a wall of warnings is run it again, usually on the only copy. NOTE ON update_log.json:
# its entries carry `started_at` from datetime.now(), so byte-identity across two runs is
# only achievable if the second run WRITES NOTHING. That is exactly the claim being
# tested — migrate() short-circuits on an already-scheme-4 archive (and, under --force,
# on one that needs no field filled) before append_update_log() is reached — so the
# sha256 comparison below is a strictly stronger assertion than any timestamp-insensitive
# diff would be, and it is paired with a count of the migration entries so a failure says
# which of the two things went wrong.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"
MIGRATE="$ORG/scripts/migrate_v3_to_v4.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

jget() {  # <file> <python expr over `d`>
  python3 -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
print($2)" "$1" 2>/dev/null
}

# --------------------------------------------------------------------------- #
# A scheme-3 archive with BOTH populations, because the two are checked by different
# gates and a fixture with only one of them cannot exercise B6 at all:
#   s1  native_text, 03_ (narrative)  — an ordinary row the migration simply fills in
#   s2  model_vision_primary, 05_ (imaging), NO transcript — the row B6 is about
# `doc_type` is present on both: it is what a REAL v3 archive carries, and the v4
# inventory schema is additionalProperties:false, so a fixture that omitted it would
# steer around the rename instead of testing it.
# --------------------------------------------------------------------------- #
mk_v3() {  # <dir>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/05_影像/CT" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  printf 'SOURCE: ct-report | CONFIDENCE: medium\n胸部CT示例描述。\n' \
    > "$d/05_影像/CT/2026-02-10_胸部CT.md"
  : > "$d/raw/incoming/upload-001.txt"
  : > "$d/raw/incoming/upload-002.pdf"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","patient_dir":".",
  "generated_at":"2026-01-02T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "doc_type":"出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable",
   "adapter":"text_payload","persist":true},
  {"file_id":"f2","source_id":"s2","original_path":"upload-002.pdf",
   "raw_path":"raw/incoming/upload-002.pdf","page_range":"1-1",
   "sidecar_path":"05_影像/CT/2026-02-10_胸部CT.md",
   "bucket_path":"05_影像/CT",
   "doc_type":"CT报告",
   "modality":"image","read_mode":"model_vision_primary",
   "extractor_provenance":{"engine":"vision-v3","version":"3.0","raw_output_ref":null,
                           "llm_role":"primary_transcription"},
   "high_risk_review_status":"not_applicable",
   "adapter":"pdf_pages","persist":true} ]}
EOF
  cat > "$d/readiness.json" <<'EOF'
{"patient_code":"PT-A1B2","schema_version":"2",
 "documentation_coverage":{"pathology_report":"not_in_archive"},
 "review_flags":[]}
EOF
  cat > "$d/profile.json" <<'EOF'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1B2",
 "summary":{"one_line_condition":"示例：结肠腺癌术后"}}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

run_val() {  # <dir> -> sets vrc; stderr in $tmp/val.err
  python3 "$VAL" "$1" >"$tmp/val.out" 2>"$tmp/val.err"
  vrc=$?
}

# Mutate the migrated archive, then re-validate. Every negative arm below is "the
# migration's own output, minus exactly one thing".
edit_json() {  # <file> <python body operating on `d`>
  python3 - "$1" "$2" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
exec(sys.argv[2])
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PYEOF
}

# ===========================================================================
# A. POSITIVE — the migration's own output passes the FULL validator
# ===========================================================================
echo "=== A. what migrate_v3_to_v4.py produces is acceptable as it stands ==="

GOLD="$tmp/migrated"
mk_v3 "$GOLD"
python3 "$MIGRATE" "$GOLD" --run-id migrate-test >"$tmp/mig.out" 2>&1
mig_rc=$?
[ "$mig_rc" -eq 0 ] && ok "migrate_v3_to_v4.py exits 0 on a scheme-3 archive with a model-vision row" \
  || no "migration exited $mig_rc: $(cat "$tmp/mig.out")"

run_val "$GOLD"
[ "$vrc" -eq 0 ] \
  && ok "the migrated archive passes the FULL validator → exit 0 (deferral + waiver are legal AS WRITTEN)" \
  || no "the migrator's own output cannot pass the validator, rc=$vrc: $(grep '^ERROR' "$tmp/val.err")"

# exit 0 must not be quiet. A deferral the operator is never told about is the failure
# mode B5 exists to prevent, and a WARN is the only thing standing between "legal" and
# "invisible".
grep -q '^WARN: pii_semantic_deferred' "$tmp/val.err" \
  && ok "…and it WARNs: the deferral is legal, and still announced on every run" \
  || no "the deferred semantic PII pass produced no WARN — legal became invisible"
grep '^WARN: pii_semantic_deferred' "$tmp/val.err" | grep -q 'before the next full run, any image increment, or any export' \
  && ok "…naming the boundary the debt must be paid by (before the next full run / image increment / export)" \
  || no "the deferral WARN does not say when the debt comes due"

# ===========================================================================
# B. B5 — deferred travels with its readiness flag, or it does not travel
# ===========================================================================
echo "=== B. pii_semantic: deferred, paired with a flag humans read ==="

[ "$(jget "$GOLD/update_log.json" \
      "next(r['pii_semantic'] for r in d['runs'] if r['run_mode']=='migration')")" = "deferred" ] \
  && ok "the migration run records pii_semantic: deferred (it read no page characters, so it claims nothing)" \
  || no "the migration run claims a PII state it could not have established"
[ "$(jget "$GOLD/readiness.json" \
      "sum(1 for f in d['review_flags'] if f.get('category')=='pii_semantic_deferred')")" = "1" ] \
  && ok "…and readiness.json carries exactly one pii_semantic_deferred review flag" \
  || no "the deferral has no paired readiness flag: $(jget "$GOLD/readiness.json" "[f.get('category') for f in d['review_flags']]")"
[ "$(jget "$GOLD/readiness.json" \
      "next(f['audience'] for f in d['review_flags'] if f['category']=='pii_semantic_deferred')")" \
  = "internal_qc" ] \
  && ok "…audience internal_qc — 「the PII pass has not been re-run」 is a processing fact, never a question for a doctor" \
  || no "the deferral flag is addressed to the wrong audience"
[ "$(jget "$GOLD/update_log.json" \
      "next(r.get('readiness_flag_id') for r in d['runs'] if r['run_mode']=='migration')")" \
  = "$(jget "$GOLD/readiness.json" \
      "next(f['id'] for f in d['review_flags'] if f['category']=='pii_semantic_deferred')")" ] \
  && ok "…and the two halves name each other by id, so the pair is machine-traceable, not merely co-present" \
  || no "the update_log entry and the readiness flag are not linked by id"

# NEGATIVE: the flag is the visible half. Delete it and the archive must fail — the
# update_log entry alone is a debt recorded where nobody looks.
D="$tmp/no_pii_flag"
cp -R "$GOLD" "$D"
edit_json "$D/readiness.json" \
  "d['review_flags']=[f for f in d['review_flags'] if f.get('category')!='pii_semantic_deferred']"
run_val "$D"
[ "$vrc" -ne 0 ] \
  && ok "deleting the pii_semantic_deferred flag → ERROR (a deferral nobody can see is an unrun pass)" \
  || no "the archive passed with a deferred PII state and no review flag at all"
grep -q 'carries no review_flag with category=pii_semantic_deferred' "$tmp/val.err" \
  && ok "…named for the missing pairing, not for some downstream symptom" \
  || no "wrong reason: $(grep '^ERROR' "$tmp/val.err" | head -1)"
grep -q 'indistinguishable from a pass nobody ran' "$tmp/val.err" \
  && ok "…and the ERROR states WHY visibility is the requirement" \
  || no "the ERROR does not explain why the flag is load-bearing"

# NEGATIVE, the other boundary: `deferred` is not a universal excuse. B5 widened the
# legal set to {incremental, migration} — and to exactly those two. Relabel this very run
# as `full` and the same deferral must be rejected, or the widening would have been an
# opening.
D="$tmp/deferred_on_full"
cp -R "$GOLD" "$D"
edit_json "$D/update_log.json" \
  "[r.__setitem__('run_mode','full') for r in d['runs'] if r.get('run_mode')=='migration']"
run_val "$D"
[ "$vrc" -ne 0 ] \
  && ok "the same deferral on a run_mode=full run → ERROR (migration is an exemption, not a precedent)" \
  || no "pii_semantic=deferred was accepted on a full run"
grep -q "deferral is legal only for \['incremental', 'migration'\]" "$tmp/val.err" \
  && ok "…against the closed two-value set, printed so drift is greppable" \
  || no "the legal run_mode set is not named: $(grep '^ERROR' "$tmp/val.err" | head -1)"

# ===========================================================================
# C. B6 — the legacy model-vision row: waived, but COUNTED
# ===========================================================================
echo "=== C. legacy_transcript_unavailable buys silence about the transcript, not about the coverage ==="

[ "$(jget "$GOLD/source_inventory.json" \
      "next(r.get('legacy_transcript_unavailable') for r in d['files'] if r['source_id']=='s2')")" \
  = "True" ] \
  && ok "the v3 model_vision_primary row is migrated with legacy_transcript_unavailable: true" \
  || no "the model-vision row carries no waiver: $(jget "$GOLD/source_inventory.json" "[r.get('legacy_transcript_unavailable') for r in d['files']]")"
[ "$(jget "$GOLD/source_inventory.json" \
      "next(r.get('legacy_transcript_unavailable','ABSENT') for r in d['files'] if r['source_id']=='s1')")" \
  = "ABSENT" ] \
  && ok "…and the native_text row does NOT get one (the waiver is narrow, not a blanket)" \
  || no "the waiver was applied to a row that never needed it"
[ "$(jget "$GOLD/readiness.json" "d['projection_coverage']['summary']['unreadable_sources']")" = "1" ] \
  && ok "…the waived source is counted in projection_coverage.summary.unreadable_sources" \
  || no "the unverifiable source is not counted as unreadable: summary=$(jget "$GOLD/readiness.json" "d['projection_coverage']['summary']")"
[ "$(jget "$GOLD/readiness.json" \
      "sum(1 for f in d['review_flags'] if f.get('category')=='coverage_gap')")" = "1" ] \
  && ok "…and carries exactly one coverage_gap review flag" \
  || no "no coverage_gap flag was written for the waived source"
[ "$(jget "$GOLD/readiness.json" \
      "next(f['audience'] for f in d['review_flags'] if f['category']=='coverage_gap')")" \
  = "internal_qc" ] \
  && ok "…audience internal_qc" || no "the coverage_gap flag is addressed to the wrong audience"
jget "$GOLD/readiness.json" \
  "next(str(f.get('current_source_values')) for f in d['review_flags'] if f['category']=='coverage_gap')" \
  | grep -q 's2' \
  && ok "…and it names the source (s2), so the gap is actionable rather than a headcount" \
  || no "the coverage_gap flag does not say WHICH source cannot be re-read"

# NEGATIVE 1: delete the coverage_gap flag. The waiver is still on the row and the count
# is still right — and that must not be enough, because the count lives in a JSON summary
# and the flag is what reaches a human review surface.
D="$tmp/no_gap_flag"
cp -R "$GOLD" "$D"
edit_json "$D/readiness.json" \
  "d['review_flags']=[f for f in d['review_flags'] if f.get('category')!='coverage_gap']"
run_val "$D"
[ "$vrc" -ne 0 ] \
  && ok "deleting the coverage_gap flag → ERROR (the waiver is not free)" \
  || no "an archive with an unverifiable source and no coverage_gap flag passed"
grep -q 'no review_flag has category=coverage_gap' "$tmp/val.err" \
  && ok "…named for the missing flag" || no "wrong reason: $(grep '^ERROR' "$tmp/val.err" | head -1)"
grep -q 'can never be re-read, re-sampled or independently verified' "$tmp/val.err" \
  && ok "…and the ERROR spells out what the archive would otherwise forget" \
  || no "the ERROR does not state the fact the flag exists to preserve"

# NEGATIVE 2: leave the flag, lie about the number. `unreadable_sources: 0` is the shape
# a coverage figure takes when it is measuring the wrong set — it reads downstream as
# "nothing is missing" on the one surface that renders a number instead of a flag.
D="$tmp/miscounted"
cp -R "$GOLD" "$D"
edit_json "$D/readiness.json" "d['projection_coverage']['summary']['unreadable_sources']=0"
run_val "$D"
[ "$vrc" -ne 0 ] \
  && ok "under-counting unreadable_sources → ERROR (the waived row must be IN the number, not just in a flag)" \
  || no "the summary was allowed to disagree with the rows it summarises"
grep -q 'unreadable_sources is 0 but the data says 1' "$tmp/val.err" \
  && ok "…reconciled against the inventory, with both numbers printed" \
  || no "the count is not reconciled: $(grep '^ERROR' "$tmp/val.err" | head -1)"

# NEGATIVE 3: the waiver itself is what buys the transcript exemption. Strip it and the
# row goes back to owing a transcript_path it cannot produce — which is the whole reason
# B6 had to be written down rather than left as "gate_transcripts is lenient about old
# rows".
D="$tmp/no_waiver"
cp -R "$GOLD" "$D"
edit_json "$D/source_inventory.json" \
  "[r.pop('legacy_transcript_unavailable',None) for r in d['files']]"
run_val "$D"
[ "$vrc" -ne 0 ] && ok "removing the waiver → ERROR (the exemption is the flag, not the read_mode)" \
  || no "a model_vision row with no transcript and no waiver passed"
grep -q "transcripts: s2: read_mode='model_vision_primary' but no transcript_path" "$tmp/val.err" \
  && ok "…gate_transcripts demands the transcript back the moment the waiver is gone" \
  || no "gate_transcripts stayed silent without the waiver: $(grep '^ERROR' "$tmp/val.err" | head -1)"
grep -q "'transcript_path' is a required property" "$tmp/val.err" \
  && ok "…and the schema if/then demands it too (two independent enforcers, not one)" \
  || no "the schema did not require transcript_path without the waiver"

# NEGATIVE 4: truthiness. `"true"` is what a hand-edit or a loose serializer produces,
# and a waiver that accepts a non-empty string is a waiver anybody can spell their way
# into on a row the migration never touched.
D="$tmp/string_waiver"
cp -R "$GOLD" "$D"
edit_json "$D/source_inventory.json" \
  "[r.__setitem__('legacy_transcript_unavailable','true') for r in d['files'] if r.get('legacy_transcript_unavailable') is True]"
run_val "$D"
[ "$vrc" -ne 0 ] \
  && ok "legacy_transcript_unavailable: \"true\" (a string) → ERROR, never waived by truthiness" \
  || no "a stringy waiver bought the transcript exemption"
grep -q "legacy_transcript_unavailable: 'true' is not of type 'boolean'" "$tmp/val.err" \
  && ok "…rejected at the type, so the waiver cannot be spelled into existence" \
  || no "the non-boolean waiver was not type-checked: $(grep '^ERROR' "$tmp/val.err" | head -1)"

# ===========================================================================
# D. the two pairings are INDEPENDENT
# ===========================================================================
echo "=== D. one flag does not cover for the other ==="

# Both flags are category-checked by different gates, and both are internal_qc, so a
# validator that merely counted internal_qc flags would pass either deletion. Deleting
# each while the other remains is what proves the two checks are separate.
D="$tmp/only_gap"
cp -R "$GOLD" "$D"
edit_json "$D/readiness.json" \
  "d['review_flags']=[f for f in d['review_flags'] if f.get('category')!='pii_semantic_deferred']"
run_val "$D"
grep -q 'carries no review_flag with category=pii_semantic_deferred' "$tmp/val.err" \
  && ok "the surviving coverage_gap flag does NOT satisfy the PII pairing" \
  || no "a coverage_gap flag was accepted in place of the pii_semantic_deferred one"

D="$tmp/only_pii"
cp -R "$GOLD" "$D"
edit_json "$D/readiness.json" \
  "d['review_flags']=[f for f in d['review_flags'] if f.get('category')!='coverage_gap']"
run_val "$D"
grep -q 'no review_flag has category=coverage_gap' "$tmp/val.err" \
  && ok "…and the surviving pii_semantic_deferred flag does NOT satisfy the coverage pairing" \
  || no "a pii_semantic_deferred flag was accepted in place of the coverage_gap one"

# ===========================================================================
# E. idempotence — running it twice changes nothing, byte for byte
# ===========================================================================
echo "=== E. a second run is a no-op (see the update_log timestamp note in the header) ==="

snap() { (cd "$1" && find . -type f | LC_ALL=C sort | xargs shasum -a 256); }

IDEM="$tmp/idem"
mk_v3 "$IDEM"
python3 "$MIGRATE" "$IDEM" --run-id migrate-first >/dev/null 2>&1
snap "$IDEM" > "$tmp/run1.sha"
sha_inv_1=$(shasum -a 256 "$IDEM/source_inventory.json" | cut -d' ' -f1)
sha_rd_1=$(shasum -a 256 "$IDEM/readiness.json" | cut -d' ' -f1)
sha_log_1=$(shasum -a 256 "$IDEM/update_log.json" | cut -d' ' -f1)

# Second run, deliberately with a DIFFERENT run id: a scheduled or scripted re-run is
# exactly how a daily cron would call it, and a per-call run id is the thing that would
# defeat a naive "same arguments produce the same output" idempotence.
python3 "$MIGRATE" "$IDEM" --run-id migrate-second >"$tmp/idem2.out" 2>&1
[ $? -eq 0 ] && ok "a second migration on the same directory exits 0 (idempotent, not an error)" \
  || no "the second run failed: $(cat "$tmp/idem2.out")"
[ "$(shasum -a 256 "$IDEM/source_inventory.json" | cut -d' ' -f1)" = "$sha_inv_1" ] \
  && ok "source_inventory.json is sha256-identical after the second run" \
  || no "source_inventory.json changed on a re-run"
[ "$(shasum -a 256 "$IDEM/readiness.json" | cut -d' ' -f1)" = "$sha_rd_1" ] \
  && ok "readiness.json is sha256-identical (flags are keyed on a stable id, so they never stack)" \
  || no "readiness.json changed on a re-run — a flag was probably duplicated"
[ "$(shasum -a 256 "$IDEM/update_log.json" | cut -d' ' -f1)" = "$sha_log_1" ] \
  && ok "update_log.json is sha256-identical — which, given started_at=now(), can only mean it was not rewritten" \
  || no "update_log.json was rewritten on a re-run (a second migration entry, or a fresh timestamp)"
[ "$(jget "$IDEM/update_log.json" "sum(1 for r in d['runs'] if r.get('run_mode')=='migration')")" = "1" ] \
  && ok "…and runs[] still holds exactly ONE migration entry" \
  || no "the re-run appended a second migration entry"
[ "$(jget "$IDEM/readiness.json" "len(d['review_flags'])")" = "2" ] \
  && ok "…and readiness still holds exactly the two flags (pii_semantic_deferred + coverage_gap)" \
  || no "the flag list grew: $(jget "$IDEM/readiness.json" "[f.get('category') for f in d['review_flags']]")"

# --force is the flag that COMPLETES a partial v4 archive, so it is the one that could
# plausibly re-derive fields that are already there. On a complete archive it must be as
# inert as the plain re-run above.
python3 "$MIGRATE" "$IDEM" --force --run-id migrate-third >"$tmp/idem3.out" 2>&1
[ $? -eq 0 ] && ok "--force on an already-complete archive exits 0" \
  || no "--force failed on a complete archive: $(cat "$tmp/idem3.out")"
snap "$IDEM" > "$tmp/run3.sha"
diff -q "$tmp/run1.sha" "$tmp/run3.sha" >/dev/null \
  && ok "…and EVERY file in the tree is byte-identical to the first run (--force fills what is missing, never what is present)" \
  || no "--force rewrote a complete archive: $(diff "$tmp/run1.sha" "$tmp/run3.sha")"
grep -q 'nothing to do' "$tmp/idem3.out" \
  && ok "…and it says so, rather than reporting a migration it did not perform" \
  || no "--force did not report a no-op: $(cat "$tmp/idem3.out")"

run_val "$IDEM"
[ "$vrc" -eq 0 ] \
  && ok "the thrice-migrated archive still passes the full validator → exit 0" \
  || no "the archive degraded across re-runs, rc=$vrc: $(grep '^ERROR' "$tmp/val.err" | head -2)"

# ---------------------------------------------------------------------------
echo
echo "== migration-deferred: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
