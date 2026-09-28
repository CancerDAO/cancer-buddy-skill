#!/usr/bin/env bash
# Remaining v2.1 cross-file bindings (validate_structured_outputs):
#   gate_record_links        — timeline conflict_group has ≥ 2 events (O-07);
#                              treatment_lines medication_refs resolve (O-05)
#   gate_profile_demographics — profile.json demographics shape + equality with the
#                              authoritative patient_summary (O-08)
#   gate_update_log          — update_log.schema.json v1; redispatched workers logged (O-09)
#   gate_source_inventory    — sha256 vs the original on disk; duplicate uploads (O-07)
# Positive control = clean synthetic archive; each negative mutates one thing.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib

tmp = Path(sys.argv[2])
passed = failed = 0
n = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def g(gate, mutate=None):
    global n
    n += 1
    return synlib.gate(gate, synlib.make(tmp / f"l{n}", mutate))


# ---- positive controls
for gate in ("gate_record_links", "gate_profile_demographics", "gate_update_log", "gate_source_inventory",
             "gate_input_completeness"):
    errs, _ = g(gate)
    check(f"clean archive: {gate} passes", errs == [], str(errs))

# ---- conflict_group
def lonely(doc):
    next(e for e in doc["events"] if e["event_id"] == "E-004")["conflict_group"] = None
errs, _ = g("gate_record_links", lambda d: synlib.edit_json(d, "timeline.json", lonely))
check("conflict_group with a single event → ERROR", any("conflict_group 'CG-001' has only event" in e for e in errs), str(errs))

# ---- medication_refs
errs, _ = g("gate_record_links", lambda d: synlib.edit_json(d, "treatment_lines.json",
            lambda doc: doc["episodes"][1].__setitem__("medication_refs", ["MED-404"])))
check("dangling medication_ref → ERROR", any("medication_refs 'MED-404'" in e for e in errs), str(errs))

# ---- antineoplastic orders are also treatment episodes (O-05.3)
errs, _ = g("gate_record_links", lambda d: synlib.edit_json(d, "treatment_lines.json",
            lambda doc: doc["episodes"][1].pop("medication_refs")))
check("antineoplastic medication no episode references → ERROR",
      any("antineoplastic medication MED-001" in e and "not referenced" in e for e in errs), str(errs))
errs, _ = g("gate_record_links", lambda d: (synlib.edit_json(d, "treatment_lines.json",
            lambda doc: doc["episodes"][1].pop("medication_refs")), synlib.edit_json(d, "comorbidities.json",
            lambda doc: doc["medications"][0].__setitem__("order_role", "supportive"))))
check("a supportive medication needs no episode link", errs == [], str(errs))
errs, _ = g("gate_record_links", lambda d: (synlib.edit_json(d, "treatment_lines.json",
            lambda doc: doc["episodes"][1].pop("medication_refs")), synlib.edit_json(d, "comorbidities.json",
            lambda doc: doc["medications"][0].pop("medication_id"))))
check("antineoplastic medication without medication_id → ERROR", any("has no medication_id" in e for e in errs), str(errs))

# ---- profile.latest_status = snapshot of the ongoing episode (phase2 §5.7; SMTB current_status row)
def latest(fn):
    return lambda d: synlib.edit_json(d, "profile.json", lambda doc: fn(doc["latest_status"]))


errs, _ = g("gate_record_links", latest(lambda ls: ls.__setitem__("regimen", "示例方案A")))
check("latest_status names a stopped episode's regimen → ERROR",
      any("latest_status.regimen '示例方案A' is not the regimen of any ongoing" in e for e in errs), str(errs))
errs, _ = g("gate_record_links", latest(lambda ls: ls.__setitem__("as_of", "2030-01-05")))
check("latest_status.as_of ≠ the ongoing episode's status_as_of → ERROR",
      any("latest_status.as_of '2030-01-05' ≠ status_as_of" in e for e in errs), str(errs))
errs, _ = g("gate_record_links", latest(lambda ls: ls.update({"regimen": None, "as_of": None})))
check("latest_status.regimen null while an episode is ongoing → ERROR",
      any("latest_status.regimen is null although" in e for e in errs), str(errs))
errs, _ = g("gate_record_links", lambda d: (latest(lambda ls: ls.update({"regimen": None, "as_of": None}))(d),
            synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].update(
                {"status": "stopped", "status_as_of": None})),
            synlib.edit_json(d, "profile.json", lambda doc: doc["summary"].__setitem__("current_regimen", None))))
check("no ongoing episode, latest_status.regimen and summary.current_regimen null passes", errs == [], str(errs))
errs, _ = g("gate_record_links", latest(lambda ls: ls.__setitem__("regimen", "示例方案 B")))
check("whitespace-only difference in the regimen string passes", errs == [], str(errs))

# ---- profile demographics (O-08)
def prof(fn):
    return lambda d: synlib.edit_json(d, "profile.json", lambda doc: fn(doc["demographics"]))
errs, _ = g("gate_profile_demographics", lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc.pop("demographics")))
check("current archive without profile.demographics → ERROR", any("no demographics block" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm.__setitem__("age_as_of", None)))
check("age without age_as_of → ERROR", any("age_as_of" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm.__setitem__("age", 61)))
check("profile age ≠ patient_summary → ERROR", any("patient_summary is authoritative" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm.__setitem__("performance_status_verbatim",
            [{"text": "ECOG 1", "as_of": "2030-01-10", "scale_label": "ECOG", "source_ref": synlib.SIDE_OUTPATIENT + "#L21"}])))
check("PS converted to ECOG in the copy (≠ summary) → ERROR", any("performance_status_verbatim ≠ patient_summary" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm["performance_status_verbatim"][0].__setitem__("scale_label", "ecog")))
check("PS scale label outside the pinned set → ERROR", any("scale_label must be one of" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm["performance_status_verbatim"][0].__setitem__("text", "PS=0")))
check("PS text not on the line its source_ref cites → ERROR", any("is not the source wording" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm.pop("provenance_layer")))
check("demographics without provenance_layer → ERROR", any("provenance_layer must be one of" in e for e in errs), str(errs))
errs, _ = g("gate_profile_demographics", prof(lambda dm: dm.__setitem__("source_refs", [])))
check("filled demographics with empty source_refs → ERROR", any("source_refs is empty" in e for e in errs), str(errs))
legacy = synlib.make_legacy(tmp / "legacy")
errs, warns = synlib.gate("gate_profile_demographics", legacy)
check("legacy archive without demographics → WARN only", errs == [] and any("no demographics block" in w for w in warns))

# ---- update_log (O-09)
def ul(fn):
    return lambda d: synlib.edit_json(d, "update_log.json", lambda doc: fn(doc["entries"][0]))
errs, _ = g("gate_update_log", lambda d: (d / "update_log.json").unlink())
check("current archive without update_log.json → ERROR", any("update_log.json: missing" in e for e in errs), str(errs))
errs, _ = g("gate_update_log", ul(lambda e: e["degradations"][0].__setitem__("redispatched_as", ["p1w-s9-99"])))
check("redispatch to a worker that never ran → ERROR", any("redispatched as 'p1w-s9-99'" in e for e in errs), str(errs))
errs, _ = g("gate_update_log", ul(lambda e: e.pop("inputs")))
check("entry without input hashes → ERROR (schema)", any("update_log.json: schema violation" in e for e in errs), str(errs))
errs, warns = synlib.gate("gate_update_log", legacy)
check("legacy update_log shape → WARN only", errs == [] and any("legacy shape" in w for w in warns), str(errs))
# the entry shape is closed: the retired orchestrator-written fields are rejected (SKILL.md Step 4,
# phase2 §8), while a worker's relevance_disposition entry (phase2 §12) and a conversation-only
# entry with empty workers[]/inputs[] are valid
errs, _ = g("gate_update_log", ul(lambda e: e.update({"case_summary_stale": True,
            "relevance": [{"action": "held", "item_ref": "99_无关文件/uncertain/x.md"}]})))
check("orchestrator-written relevance[] / case_summary_stale → ERROR with the relevance_disposition hint",
      any("Additional properties" in e for e in errs) and any("run_mode: relevance_disposition" in e for e in errs), str(errs))
def disposition(doc):
    last = doc["entries"][0]
    doc["entries"].append({"at": "2030-01-21T10:00:00Z", "run_mode": "relevance_disposition",
        "workers": [{"worker_id": "p2w-disp-01", "phase": "phase2", "slice_id": None, "status": "done", "files": []}],
        "inputs": list(last["inputs"]), "added": [], "removed": [],
        "degradations": [], "note": "hold 99_无关文件/uncertain/item-1（用户：先留着）caregiver"})
    doc["entries"].append({"at": "2030-01-22T10:00:00Z", "run_mode": "conversation_incremental",
                           "workers": [], "inputs": [], "note": "conversation note archived"})
dd = synlib.make(tmp / "ulog_modes", lambda d: synlib.edit_json(d, "update_log.json", disposition))
rc, errs, warns = synlib.validate(dd)
check("relevance_disposition + conversation-only entries validate", rc == 0, str(errs[:3]))
check("an inputs: [] entry does not trip the input-hash freshness WARN", not any("update_log_freshness" in w for w in warns), str(warns))
errs, _ = g("gate_update_log", lambda d: (d / "update_log.json").write_text("{not json", encoding="utf-8"))
check("unparseable update_log.json → ERROR", any("update_log.json: not parseable JSON" in e for e in errs), str(errs))
errs, _ = g("gate_update_log", ul(lambda e: e["workers"].append(
    {"worker_id": "Orchestrator", "phase": "phase2", "slice_id": None, "status": "done", "files": []})))
check("case-variant reserved worker id (schema is case-sensitive) → ERROR", any("'Orchestrator' is reserved" in e for e in errs), str(errs))
errs, _ = g("gate_update_log", ul(lambda e: e.__setitem__("degradations", [])))
check("timeout worker with no degradations[] record → ERROR (and its redispatch unlogged)",
      any("'p1-s0-1' ended timeout but no degradations[] entry" in e for e in errs), str(errs))
errs, _ = g("gate_update_log", ul(lambda e: next(w for w in e["workers"] if w["phase"] == "phase2").__setitem__("status", "killed")))
check("killed worker with no degradations[] record → ERROR", any("'p2-1' ended killed" in e for e in errs), str(errs))

# ---- source_inventory hash integrity (O-07)
def with_raw(content):
    def fn(d):
        (d / "raw").mkdir(exist_ok=True)
        (d / "raw" / "s001.jpg").write_bytes(content)
    return fn
import hashlib
from make_syn_current import RAW
errs, _ = g("gate_source_inventory", with_raw(RAW["s001"]))
check("original on disk matching the recorded sha256 passes", errs == [], str(errs))
errs, _ = g("gate_source_inventory", with_raw(b"a different original"))
check("original on disk ≠ recorded sha256 → ERROR", any("sha256 does not match the original" in e for e in errs), str(errs))
def dup(doc):
    doc["files"][1]["sha256"] = doc["files"][0]["sha256"]
errs, _ = g("gate_source_inventory", lambda d: synlib.edit_json(d, "source_inventory.json", dup))
check("two source_ids with one sha256 → ERROR (record the copy as skipped)", any("duplicate_sha256" in e for e in errs), str(errs))
errs, _ = g("gate_source_inventory", lambda d: (with_raw(RAW["s001"])(d), synlib.edit_json(
    d, "source_inventory.json", lambda doc: doc["files"][0].__setitem__("size_bytes", len(RAW["s001"]) + 1))))
check("only size_bytes ≠ the original → ERROR", errs and all("size_bytes" in e and "does not match the original" in e for e in errs), str(errs))

# ---- input completeness (O-07): nothing supplied is silently dropped
def raw_file(rel, content):
    def fn(d):
        p = d / "raw" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return fn
errs, _ = g("gate_input_completeness", lambda d: (raw_file("s001.jpg", RAW["s001"])(d), raw_file("_extract/s001.ocr.txt", b"x")(d),
            raw_file(".DS_Store", b"junk")(d), raw_file("sub/__MACOSX/._s001.jpg", b"junk")(d)))
check("inventoried original + raw/_* infrastructure + OS junk → pass", errs == [], str(errs))
errs, _ = g("gate_input_completeness", raw_file("s099.jpg", b"an original nobody recorded"))
check("an original under raw/ in neither files[] nor skipped_inputs[] → ERROR",
      any("input_completeness: 1 original(s) under raw/" in e and "raw/s099.jpg" in e for e in errs), str(errs))
from make_syn_current import DS_STORE
errs, _ = g("gate_input_completeness", raw_file("s099.bin", DS_STORE))
check("an original recorded in skipped_inputs[] (by sha256) passes", errs == [], str(errs))
errs, _ = g("gate_input_completeness", ul(lambda e: e["inputs"].append({"source_id": "s077", "sha256": "ef" * 32})))
check("a logged input in neither files[] nor skipped_inputs[] → ERROR",
      any("latest update_log entry are in neither" in e and "s077" in e for e in errs), str(errs))
leg_raw = synlib.make(tmp / "legacy_raw", lambda d: (synlib.downgrade_to_legacy(d), raw_file("s099.jpg", b"unrecorded")(d)))
errs, warns = synlib.gate("gate_input_completeness", leg_raw)
check("legacy archive: unaccounted original → WARN only", errs == [] and any("input_completeness" in w for w in warns), str(errs))

print(f"organize-v21-links: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
