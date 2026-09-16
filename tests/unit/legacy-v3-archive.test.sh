#!/usr/bin/env bash
# tests/unit/legacy-v3-archive.test.sh — organize v3→v4, fix spec A13.
#
# v4 made `kind` and `clinical_class` required on every source_inventory row and added
# `readiness.projection_coverage`. No archive organized under v3 has any of them. So the
# new validator faces a choice on day one: fail every archive that already exists, which
# turns a schema bump into a data-loss event for the one person whose records are in it,
# or accept rows missing the fields the open-world gates read, which makes the whole
# requirement decorative. A13 takes neither. An archive that HONESTLY DECLARES itself as
# scheme 3 — `scheme_version: 3` spelled out, with readiness still at
# `schema_version: "2"` — is read against the shape it was written to, WARNed, and passed.
#
# B4 then closed the hole the first draft of A13 opened. That draft also read an OMITTED
# `scheme_version` as 3, which made the whole open-world gate set — open-domain filing,
# the clinical_class floors, per-field second-read independence, the human spot-check,
# faithfulness coverage, projection coverage, review-flag audience, field provenance and
# the high-risk denominator reconciliation — switchable off by DELETING one key from a
# JSON file. That is the cheapest bypass a gate can have and it wore the costume of
# backward compatibility. Silence is not a version: an archive that will not say which
# contract it was written to is an ERROR that names both legal answers. The grace period
# costs a declaration, and a declaration is something a reader can grep for.
#
# Three properties make that safe, and this file asserts all three.
#
# The first is that the relaxation is keyed on the archive's own EXPLICIT
# self-description and is a GRACE PERIOD, not a resting place. The WARN has to say which gates are being skipped
# and name scripts/migrate_v3_to_v4.py, because exit 0 on a legacy archive means "readable
# under the old contract", not "clean" — and the only thing standing between those two
# readings is the text of that warning.
#
# The second is that it must be PAID FOR by saying so. An archive carrying no
# `scheme_version` at all gets no relaxation and no WARN — it gets an ERROR, because a
# validator cannot check an archive against a contract nobody named, and guessing the
# lenient one is the guess that costs the patient.
#
# The third is that it is not an escape hatch a v4 archive can claim. The relaxation is
# bought by declaring scheme 3 and accepting the WARN that says the floors are off. The
# same rows with `scheme_version: 4` on top — claiming the current contract while missing
# everything the current contract requires — must ERROR. If a v4 declaration could inherit
# the v3 leniency, then every archive would simply be "whatever validates", and the gates
# A13 exists to defer would be gates nobody ever has to pass.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
VAL="$ORG/scripts/validate_structured_outputs.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# --------------------------------------------------------------------------- #
# The MINIMAL scheme-3 archive: an inventory row with no kind / clinical_class /
# text_layer_kind / transcript_path, a readiness.json at schema_version "2" with no
# projection_coverage, one bucket sidecar. $2 is the scheme_version declaration spliced
# into the inventory — the ONLY thing that differs between the positive and negative
# arms below, which is exactly the point being made.
# --------------------------------------------------------------------------- #
mk_v3() {  # <dir> <scheme_version json fragment, may be empty>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/upload-001.txt"
  cat > "$d/source_inventory.json" <<EOF
{ "schema":"source_inventory_v2",$2"patient_dir":".",
  "generated_at":"2026-01-02T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable",
   "adapter":"text_payload","persist":true} ]}
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
  # B7 — update_log.json is a REQUIRED product for EVERY archive, legacy included. A
  # scheme-3 archive is old, not exempt: the one question this file answers ("did the
  # semantic PII pass ever run, and over what?") is exactly the question a pre-v4
  # archive cannot answer any other way. Leaving it out of the legacy fixture would
  # have made this suite assert that legacy buys you out of it.
  cat > "$d/update_log.json" <<'EOF'
{"schema_version":"1","patient_code":"PT-A1B2","runs":[
  {"run_id":"run-legacy-001","run_mode":"full","started_at":"2026-01-02T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],
   "pii_semantic":"clean","faithfulness_method":"native_text_identity"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

run_val() {  # <dir> -> sets vrc, and writes stderr to $tmp/val.err
  python3 "$VAL" "$1" >"$tmp/val.out" 2>"$tmp/val.err"
  vrc=$?
}

is_legacy() {  # <dir> -> exit 0 when the validator calls this archive legacy
  python3 - "$ORG" "$1" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
sys.exit(0 if v.archive_is_legacy_v3(pathlib.Path(sys.argv[2])) else 1)
PYEOF
}

# ===========================================================================
# A. NEGATIVE — scheme_version OMITTED (B4: silence is not a version)
# ===========================================================================
echo "=== A. an archive that omits scheme_version ==="

# This fixture is byte-identical to the passing one in section B except for the five
# characters `"scheme_version":3,`. Under the first draft of A13 that made it legacy and
# it exited 0. It is the same rows, the same gaps and the same risk as a declared
# scheme 3 — the difference is entirely in whether anybody said so, and that is the
# point: the relaxation is bought by a DECLARATION, and an archive that declares nothing
# has bought nothing. Anything else means deleting one JSON key is the cheapest way to
# switch off every open-world gate in the validator at once.
D="$tmp/omitted"
mk_v3 "$D" ""
run_val "$D"
[ "$vrc" -eq 1 ] \
  && ok "a v3-shaped archive with NO scheme_version key → exit 1 (silence is not a version)" \
  || no "an undeclared archive still bought the legacy relaxation, rc=$vrc"
grep -q 'no scheme_version' "$tmp/val.err" \
  && ok "…the ERROR names the missing declaration, not the fields it could not check" \
  || no "the missing declaration is not the reported cause: $(grep '^ERROR' "$tmp/val.err")"
grep -q 'scheme_version: 4' "$tmp/val.err" \
  && ok "…and names the CURRENT declaration to write" || no "the v4 answer is not offered"
grep -q '3 for a genuine pre-v4 archive' "$tmp/val.err" \
  && ok "…and the legacy one too, so the fix is not 'guess again'" \
  || no "the legacy answer is not offered: $(grep '^ERROR' "$tmp/val.err")"
# the ERROR has to enumerate the blast radius, because "add a key" reads like a
# formality until you can see that the key was switching off nine gates
for skipped in 'clinical_class floors' 'faithfulness coverage' 'projection' \
               'review-flag audience' 'field provenance' 'denominator reconciliation'; do
  grep -q "$skipped" "$tmp/val.err" \
    && ok "…the ERROR names a gate the silence was switching off: $skipped" \
    || no "the ERROR does not disclose that '$skipped' was being skipped"
done
grep -q '^WARN: legacy_archive' "$tmp/val.err" \
  && no "an undeclared archive was still handed the legacy_archive relaxation WARN" \
  || ok "…and NO legacy_archive WARN was issued: nothing was relaxed for it"
is_legacy "$D" && no "archive_is_legacy_v3() is True for a missing scheme_version" \
  || ok "archive_is_legacy_v3() is False when the key is simply absent (B4)"

# …and the remedy really is one line: the SAME directory, declared, validates. This is
# what keeps the ERROR above from being a wall — the archive is not rejected, its
# silence is.
python3 - "$D/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["scheme_version"] = 3
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
run_val "$D"
[ "$vrc" -eq 0 ] \
  && ok "…adding `scheme_version: 3` to that very directory → exit 0 (the fix is the declaration)" \
  || no "declaring the scheme did not clear it, rc=$vrc: $(grep '^ERROR' "$tmp/val.err")"

# ===========================================================================
# B. POSITIVE — scheme_version: 3 declared explicitly
# ===========================================================================
echo "=== B. an archive that declares scheme_version: 3 ==="

D="$tmp/three"
mk_v3 "$D" '"scheme_version":3,'
run_val "$D"
[ "$vrc" -eq 0 ] && ok "scheme_version: 3 validates → exit 0" \
  || no "explicit scheme 3 failed, rc=$vrc: $(grep '^ERROR' "$tmp/val.err")"
grep -q 'migrate_v3_to_v4.py' "$tmp/val.err" \
  && ok "…and the run WARNs, naming scripts/migrate_v3_to_v4.py" || no "no migration pointer"
grep -q '^WARN: legacy_archive' "$tmp/val.err" \
  && ok "…tagged legacy_archive, so the reason is greppable" \
  || no "the archive-level WARN is not tagged legacy_archive"
grep -q 'not a clean bill of health' "$tmp/val.err" \
  && ok "…and says out loud that exit 0 here is NOT a clean bill of health" \
  || no "the WARN lets exit 0 be read as clean: $(grep legacy_archive "$tmp/val.err")"
# the WARN must enumerate what it switches off. "legacy archive" on its own reads like
# a version note; the list is what makes it read like a debt.
for skipped in 'clinical_class floors' 'faithfulness coverage' 'projection' \
               'review-flag audience' 'field provenance'; do
  grep '^WARN: legacy_archive' "$tmp/val.err" | grep -q "$skipped" \
    && ok "…the WARN names a gate it is skipping: $skipped" \
    || no "the WARN does not disclose that '$skipped' is off"
done
is_legacy "$D" && ok "archive_is_legacy_v3() is True for scheme_version: 3" \
  || no "explicit scheme 3 not detected as legacy"

# readiness.json's own legacy declaration is a SEPARATE warning with its own pointer:
# the two files version independently, so one WARN covering both would go quiet as soon
# as either was upgraded.
grep -q 'readiness.json declares schema_version 2' "$tmp/val.err" \
  && ok "readiness.json schema_version \"2\" gets its OWN WARN" \
  || no "the readiness legacy version is not warned about separately"
grep 'readiness.json declares schema_version 2' "$tmp/val.err" | grep -q 'migrate_v3_to_v4.py' \
  && ok "…which also names scripts/migrate_v3_to_v4.py" \
  || no "the readiness WARN has no remedy"
grep 'readiness.json declares schema_version 2' "$tmp/val.err" | grep -q 'audience' \
  && ok "…and says what it predates (review_flags[].audience is NOT being checked)" \
  || no "the readiness WARN does not disclose what is unchecked"

# the relaxation really is what lets it through: the same archive is missing exactly the
# things v4 requires, and under scheme 3 none of them is an error
python3 - "$D" <<'PYEOF'
import json, sys, pathlib
inv = json.loads(pathlib.Path(sys.argv[1], "source_inventory.json").read_text(encoding="utf-8"))
row = inv["files"][0]
for k in ("kind", "clinical_class", "text_layer_kind", "transcript_path"):
    assert k not in row, f"fixture is not really legacy — it carries {k}"
rd = json.loads(pathlib.Path(sys.argv[1], "readiness.json").read_text(encoding="utf-8"))
assert "projection_coverage" not in rd, "fixture already has projection_coverage"
print("fixture is genuinely pre-v4")
PYEOF
[ $? -eq 0 ] \
  && ok "the passing fixture genuinely lacks kind / clinical_class / text_layer_kind / transcript_path / projection_coverage" \
  || no "the fixture is not actually a legacy archive"

# ===========================================================================
# C. NEGATIVE — the same archive claiming scheme_version: 4
# ===========================================================================
echo "=== C. claiming v4 while missing the v4 fields ==="

D="$tmp/claims_four"
mk_v3 "$D" '"scheme_version":4,'
run_val "$D"
[ "$vrc" -eq 1 ] \
  && ok "the SAME rows declared scheme_version: 4 → exit 1 (the hatch is not claimable)" \
  || no "a v4 declaration inherited the v3 leniency, rc=$vrc"
grep -q "'kind' is a required property" "$tmp/val.err" \
  && ok "…the missing kind is reported as a required property" || no "kind not enforced"
grep -q "'clinical_class' is a required property" "$tmp/val.err" \
  && ok "…and the missing clinical_class too" || no "clinical_class not enforced"
grep -q 'projection_coverage is missing' "$tmp/val.err" \
  && ok "…and readiness.projection_coverage is demanded" || no "projection_coverage not demanded"
grep -q '^WARN: legacy_archive' "$tmp/val.err" \
  && no "an archive claiming v4 still got the legacy_archive relaxation WARN" \
  || ok "…with NO legacy_archive WARN — nothing was relaxed for it"
is_legacy "$D" && no "archive_is_legacy_v3() is True for a scheme_version: 4 archive" \
  || ok "archive_is_legacy_v3() is False for scheme_version: 4"

# ===========================================================================
# D. NEGATIVE — leniency is narrow, and cannot be bought by being broken
# ===========================================================================
echo "=== D. what the legacy branch does NOT excuse ==="

# a value that was illegal under v3 as well is still illegal
D="$tmp/bad_enum"
mk_v3 "$D" '"scheme_version":3,'
python3 - "$D/source_inventory.json" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["files"][0]["read_mode"] = "vibes"
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
run_val "$D"
[ "$vrc" -eq 1 ] && ok "a legacy archive with an off-enum read_mode still ERRORs" \
  || no "the legacy branch relaxed an enum it has no business relaxing"
grep -q "'vibes' is not one of" "$tmp/val.err" \
  && ok "…rejected against the closed read_mode enum (types/enums are never relaxed)" \
  || no "the enum violation was not reported: $(grep '^ERROR' "$tmp/val.err")"

# there is no forward-compatible scheme beyond 4
D="$tmp/five"
mk_v3 "$D" '"scheme_version":5,'
run_val "$D"
[ "$vrc" -eq 1 ] && ok "scheme_version: 5 → exit 1 (the enum is [3, 4], with no future value)" \
  || no "an unknown scheme_version was accepted"
grep -q 'is not one of \[3, 4\]' "$tmp/val.err" \
  && ok "…named against the closed scheme_version enum" || no "scheme enum not enforced"
is_legacy "$D" && no "scheme_version: 5 was treated as legacy" \
  || ok "…and it does NOT fall back into the legacy branch"

# an inventory nobody can parse must not buy leniency by being broken
D="$tmp/broken"
mk_v3 "$D" '"scheme_version":3,'
printf '{not json' > "$D/source_inventory.json"
run_val "$D"
[ "$vrc" -eq 1 ] && ok "an unparseable source_inventory.json → exit 1" \
  || no "a corrupt inventory passed"
is_legacy "$D" && no "an unparseable inventory was treated as legacy" \
  || ok "…and archive_is_legacy_v3() is False for it (broken ≠ old)"
grep -q 'not parseable JSON' "$tmp/val.err" \
  && ok "…reported as unparseable rather than as an empty archive" \
  || no "the parse failure was not reported"
grep -q 'could not run' "$tmp/val.err" \
  && ok "…and the gates that could not run SAY SO instead of reporting nothing" \
  || no "a gate that could not run stayed silent"

# ===========================================================================
# E. the split: file-level read relaxation vs archive-level gate relaxation
# ===========================================================================
echo "=== E. a v4 archive with a legacy readiness.json ==="

# A v4 archive whose readiness.json still says "2" gets a lenient READ of that one file
# — and full-strength GATES everywhere else. These are two different mechanisms and
# collapsing them would let one stale schema_version switch off the open-world floors.
mk_v4_readiness2() {  # <dir> <extra python to mutate readiness>
  local d="$1"
  rm -rf "$d"
  mkdir -p "$d/03_病程与叙事文书/出院小结" "$d/raw/incoming"
  printf 'SOURCE: discharge | CONFIDENCE: high\n出院小结正文示例。\n' \
    > "$d/03_病程与叙事文书/出院小结/2026-03-15_出院小结.md"
  : > "$d/raw/incoming/upload-001.txt"
  cat > "$d/source_inventory.json" <<'EOF'
{ "schema":"source_inventory_v2","scheme_version":4,"patient_dir":".",
  "generated_at":"2026-09-16T00:00:00Z","files":[
  {"file_id":"f1","source_id":"s1","original_path":"upload-001.txt",
   "raw_path":"raw/incoming/upload-001.txt","page_range":null,
   "kind":"known","doc_kind":"出院小结","clinical_class":"narrative",
   "text_layer_kind":"not_applicable",
   "sidecar_path":"03_病程与叙事文书/出院小结/2026-03-15_出院小结.md",
   "bucket_path":"03_病程与叙事文书/出院小结",
   "modality":"text","read_mode":"native_text",
   "extractor_provenance":{"engine":"native-text","version":"3.0","raw_output_ref":null,
                           "llm_role":"none"},
   "high_risk_review_status":"not_applicable",
   "adapter":"text_payload","persist":true} ]}
EOF
  cat > "$d/readiness.json" <<'EOF'
{"patient_code":"PT-A1B2","schema_version":"2",
 "documentation_coverage":{"pathology_report":"not_in_archive"},
 "projection_coverage":{
   "per_source":[{"source_id":"s1","unprojected_field_classes":[]}],
   "summary":{"sources_total":1,"sources_fully_projected":1,
              "novel_sources":0,"unreadable_sources":0}},
 "review_flags":[]}
EOF
  cat > "$d/profile.json" <<'EOF'
{"schema":"cancer_buddy_profile_v3","patient_code":"PT-A1B2",
 "summary":{"one_line_condition":"示例：结肠腺癌术后"}}
EOF
  cat > "$d/update_log.json" <<'EOF'
{"schema_version":"1","patient_code":"PT-A1B2","runs":[
  {"run_id":"run-001","run_mode":"full","started_at":"2026-09-16T00:00:00Z",
   "added_sources":[{"source_id":"s1","read_mode":"native_text"}],
   "pii_semantic":"clean","faithfulness_method":"native_text_identity"} ]}
EOF
  python3 "$ORG/scripts/fill_agents_md.py" "$d" >/dev/null 2>&1
}

D="$tmp/v4_readiness2"
mk_v4_readiness2 "$D"
run_val "$D"
[ "$vrc" -eq 1 ] \
  && ok "a v4 inventory over a readiness.json still saying \"2\" → exit 1 (C12: mixed is refused, not relaxed)" \
  || no "the mixed archive passed, rc=$vrc — one stale schema_version bought a v4 review surface out of checking"
grep -q 'a MIXED archive, not a legacy one' "$tmp/val.err" \
  && ok "…named as a MIXED archive rather than reported as a legacy one" \
  || no "the mixed state was not diagnosed: $(grep '^ERROR' "$tmp/val.err" | head -2)"
grep -q 'review_flags\[\].audience' "$tmp/val.err" && grep -q 'projection_coverage' "$tmp/val.err" \
  && ok "…and the message says WHAT schema 2 is missing (audience / category / projection_coverage)" \
  || no "the error does not say why schema 2 is unsafe under scheme 4"
grep -q 'migrate_v3_to_v4.py' "$tmp/val.err" && grep -q -- '--force' "$tmp/val.err" \
  && ok "…and names the exact command that resolves it (--force, per B4/C4)" \
  || no "no remediation command in the C12 error"
grep -q 'declare the whole archive scheme_version 3' "$tmp/val.err" \
  && ok "…and offers the other legal answer too: declare the archive scheme 3 if it really is one" \
  || no "the C12 error offers only one of the two legal resolutions"
grep -q '^WARN: legacy_archive' "$tmp/val.err" \
  && no "the mixed archive was ALSO waved through the archive-level legacy branch" \
  || ok "…and it is not routed into the legacy branch: a half-migrated archive is not an old one"

# NEGATIVE ARM — the same archive with readiness at "3" passes. Without this, everything
# above is satisfied by a gate that fails every v4 archive it is shown, and C12 would be
# indistinguishable from a broken fixture.
D="$tmp/v4_readiness3"
mk_v4_readiness2 "$D"
python3 - "$D/readiness.json" <<'RDEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["schema_version"] = "3"
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
RDEOF
run_val "$D"
[ "$vrc" -eq 0 ] \
  && ok "negative arm: the identical archive with readiness schema_version \"3\" → exit 0" \
  || no "the control v4 archive fails too, rc=$vrc — C12 above proves nothing: $(grep '^ERROR' "$tmp/val.err" | head -2)"
grep -q 'MIXED archive' "$tmp/val.err" \
  && no "the C12 error fires on a correctly-versioned archive" \
  || ok "…with no mixed-archive complaint: the pair (4, \"3\") is the current contract"

# …and the pair (3, "2") is still the LEGACY contract, not an error. C12 tightened one
# combination; it must not have turned every schema_version "2" into a refusal, or genuine
# pre-v4 archives become unreadable instead of migratable.
D="$tmp/v3_readiness2"
mk_v3 "$D" '"scheme_version":3,'
run_val "$D"
[ "$vrc" -eq 0 ] \
  && ok "negative arm: a genuine scheme_version 3 archive with readiness \"2\" still READS → exit 0" \
  || no "C12 made real legacy archives unreadable, rc=$vrc: $(grep '^ERROR' "$tmp/val.err" | head -2)"
grep -q 'MIXED archive' "$tmp/val.err" \
  && no "the mixed-archive ERROR fired on a consistently-versioned legacy archive" \
  || ok "…and is not called MIXED: both keys agree on 3/\"2\", which is a version, not a half-migration"

# and the archive-level gates are still armed under scheme 4 for their own reasons —
# not merely because C12 got there first. Drop projection_coverage from an archive whose
# readiness is already at "3", so the C12 ERROR is out of the way and only the coverage
# gate can speak.
D="$tmp/v4_readiness3_nocov"
mk_v4_readiness2 "$D"
python3 - "$D/readiness.json" <<'RDEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["schema_version"] = "3"
d.pop("projection_coverage", None)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
RDEOF
run_val "$D"
[ "$vrc" -eq 1 ] \
  && ok "…a v4 archive missing projection_coverage ERRORs on its own, with readiness at \"3\"" \
  || no "the coverage floor is not armed independently of C12"
grep -q 'projection_coverage is missing' "$tmp/val.err" \
  && ok "…for the right reason, named" || no "wrong reason: $(grep '^ERROR' "$tmp/val.err")"

# ===========================================================================
# F. the legacy vocabulary lives in the script, not in this test
# ===========================================================================
echo "=== F. no drift ==="

python3 - "$ORG" <<'PYEOF'
import sys, json, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
v = importlib.import_module("validate_structured_outputs")
spec = v.LEGACY_ARCHIVE_SCHEMAS
inv = spec[v.SOURCE_INVENTORY_NAME]
assert inv["version_key"] == "scheme_version", inv["version_key"]
# B4 — {3}, NOT {None, 3}. If None ever creeps back into this tuple, an archive that
# declares nothing is legacy again and every open-world gate is one deleted key away
# from off. The vocabulary IS the mechanism, so it is pinned here.
assert set(inv["legacy_values"]) == {3}, inv["legacy_values"]
assert "migrate_v3_to_v4.py" in inv["note"]
rd = spec[v.READINESS_NAME]
assert rd["version_key"] == "schema_version", rd["version_key"]
assert set(rd["legacy_values"]) == {"2"}, rd["legacy_values"]
assert "migrate_v3_to_v4.py" in rd["note"]
schema = json.loads((pathlib.Path(sys.argv[1])
                     / "references/schemas/source_inventory.schema.json")
                    .read_text(encoding="utf-8"))
assert schema["properties"]["scheme_version"]["enum"] == [3, 4], "scheme_version enum drifted"
print("legacy vocabulary OK")
PYEOF
[ $? -eq 0 ] \
  && ok "LEGACY_ARCHIVE_SCHEMAS pins {3} / {\"2\"} — absent is NOT legacy — both naming the migration script" \
  || no "the legacy version vocabulary drifted from fix spec A13"

# ---------------------------------------------------------------------------
echo
echo "== legacy-v3-archive: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
