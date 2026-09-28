#!/usr/bin/env bash
# organize contract v2.1 schemas — positive + negative case for every new field.
#
# BASE = the clean synthetic archive (tests/fixtures/organize-regress/syn-current/src,
# all data invented). Each case deep-copies one document, changes ONE thing and asserts
# the schema accepts (positive) or rejects (negative) it. Schema level only; the
# cross-file bindings are covered by the gate tests.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi

python3 - "$REPO_ROOT" <<'PY'
import copy, sys
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib

passed = failed = 0
SCHEMA = {
    "readiness.json": "readiness.schema.json", "source_inventory.json": "source_inventory.schema.json",
    "comorbidities.json": "comorbidities.schema.json", "labs.json": "labs.schema.json",
    "treatment_lines.json": "treatment_lines.schema.json", "timeline.json": "timeline.schema.json",
    "missing_items.json": "missing_items.schema.json", "molecular.json": "molecular.schema.json",
    "patient_summary.json": "patient_summary.schema.json", "acute_findings.json": "acute_findings.schema.json",
    "update_log.json": "update_log.schema.json",
}


def case(label, fname, expected, mutate=None):
    global passed, failed
    doc = synlib.fixture_doc(fname)
    if mutate:
        mutate(doc)
    errs = synlib.schema_errors(SCHEMA[fname], doc)
    got = "fail" if errs else "pass"
    if got == expected:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: [{fname}] {label}: expected {expected}, got {got} {errs[:2]}", file=sys.stderr)


def flag(d, i=0): return d["review_flags"][i]
def row(d, i=0): return d["files"][i]
def med(d): return d["medications"][0]
def val(d, i=0): return d["panels"][i]["values"][0]
def ep(d, i=1): return d["episodes"][i]
def ev(d, eid): return next(e for e in d["events"] if e["event_id"] == eid)
def gap(d): return d["document_gaps"][0]
def af(d): return d["findings"][0]
def entry(d): return d["entries"][0]

# ---- positive controls: every fixture document validates
for fname in SCHEMA:
    case("clean fixture validates", fname, "pass")

# ---- readiness v2.1 (O-01 severity/kind, O-04 recency)
case("schema_version 2 rejected by the strict schema (legacy read is the validator's job)", "readiness.json", "fail",
     lambda d: d.__setitem__("schema_version", "2"))
case("flag without severity rejected", "readiness.json", "fail", lambda d: flag(d).pop("severity"))
case("flag without kind rejected", "readiness.json", "fail", lambda d: flag(d).pop("kind"))
case("clinical-style severity 'green' rejected", "readiness.json", "fail", lambda d: flag(d).__setitem__("severity", "green"))
case("unknown kind rejected", "readiness.json", "fail", lambda d: flag(d).__setitem__("kind", "strikethrough"))
for k in ("legibility", "artifact", "document_intent", "conflict", "completeness", "other"):
    case(f"kind {k} accepted", "readiness.json", "pass", lambda d, k=k: flag(d).__setitem__("kind", k))
case("cross_doc_supported supported without refs rejected", "readiness.json", "fail",
     lambda d: flag(d).__setitem__("cross_doc_supported", {"status": "supported", "refs": []}))
case("cross_doc_supported bad status rejected", "readiness.json", "fail",
     lambda d: flag(d).__setitem__("cross_doc_supported", {"status": "maybe", "refs": []}))
case("uncertain_ids must be U-nnn", "readiness.json", "fail", lambda d: flag(d).__setitem__("uncertain_ids", ["CgA"]))
# C6: current_source_values[] items may name their read channel (several readings of one line)
def csv(d): return flag(d)["current_source_values"][0]
for ch in ("llm_vision", "deterministic_ocr:apple_vision", "text_layer", "none", None):
    case(f"current_source_values channel {ch!r} accepted", "readiness.json", "pass", lambda d, ch=ch: csv(d).__setitem__("channel", ch))
for ch in ("deterministic_ocr", "OCR+模型", "vision"):
    case(f"current_source_values channel {ch!r} rejected", "readiness.json", "fail", lambda d, ch=ch: csv(d).__setitem__("channel", ch))
case("a channel that read nothing: value null + channel", "readiness.json", "pass",
     lambda d: flag(d)["current_source_values"].append({"value": None, "source_ref": csv(d)["source_ref"], "channel": "text_layer"}))
case("current_source_values other extra key still rejected", "readiness.json", "fail", lambda d: csv(d).__setitem__("reader", "x"))
case("suggested_value still forbidden", "readiness.json", "fail", lambda d: flag(d).__setitem__("suggested_value", "CgA"))
for k in ("latest_source_date", "days_since_latest", "as_of_run_date"):
    case(f"missing {k} rejected", "readiness.json", "fail", lambda d, k=k: d.pop(k))
case("no dated source: latest null + days null accepted", "readiness.json", "pass",
     lambda d: d.update({"latest_source_date": None, "days_since_latest": None}))
case("latest null with a day count rejected", "readiness.json", "fail",
     lambda d: d.update({"latest_source_date": None, "days_since_latest": 3}))
case("latest date with null day count rejected", "readiness.json", "fail", lambda d: d.update({"days_since_latest": None}))
case("as_of_run_date must be YYYY-MM-DD", "readiness.json", "fail", lambda d: d.update({"as_of_run_date": "2030/01/20"}))
case("negative day count rejected", "readiness.json", "fail", lambda d: d.update({"days_since_latest": -1}))

# ---- source_inventory v2.1 (O-01 reread channel, O-06 digest, O-07 hashes/skips, O-09 worker)
case("legacy schema id rejected by strict schema", "source_inventory.json", "fail",
     lambda d: d.__setitem__("schema", "source_inventory_v2"))
case("missing skipped_inputs rejected", "source_inventory.json", "fail", lambda d: d.pop("skipped_inputs"))
for k in ("sha256", "size_bytes", "page_count", "page_label", "source_kind", "second_read_channel", "independent_reread"):
    case(f"file row without {k} rejected", "source_inventory.json", "fail", lambda d, k=k: row(d).pop(k))
case("sha256 must be 64 lower-case hex", "source_inventory.json", "fail", lambda d: row(d).__setitem__("sha256", "ABC"))
case("upload row with null sha256 rejected", "source_inventory.json", "fail", lambda d: row(d).__setitem__("sha256", None))
case("page_count 0 rejected", "source_inventory.json", "fail", lambda d: row(d).__setitem__("page_count", 0))
case("worker_id required", "source_inventory.json", "fail", lambda d: row(d)["extractor_provenance"].pop("worker_id"))
case("orchestrator worker_id rejected", "source_inventory.json", "fail",
     lambda d: row(d)["extractor_provenance"].__setitem__("worker_id", "orchestrator"))
case("llm_vision reread marked independent rejected", "source_inventory.json", "fail",
     lambda d: row(d).update({"second_read_channel": "llm_vision", "independent_reread": True}))
case("llm_vision reread marked not independent accepted", "source_inventory.json", "pass",
     lambda d: row(d).update({"second_read_channel": "llm_vision", "independent_reread": False,
                              "high_risk_review_status": "needs_human_review"}))
case("passed_independent_reread with a non-independent reread rejected", "source_inventory.json", "fail",
     lambda d: row(d).update({"independent_reread": False}))
case("second_read_channel outside the pinned categories rejected", "source_inventory.json", "fail",
     lambda d: row(d).__setitem__("second_read_channel", "OCR+模型"))
case("second_read_channel deterministic_ocr without an engine rejected", "source_inventory.json", "fail",
     lambda d: row(d).__setitem__("second_read_channel", "deterministic_ocr"))
case("second_read_channel deterministic_ocr:<engine> accepted", "source_inventory.json", "pass",
     lambda d: row(d).__setitem__("second_read_channel", "deterministic_ocr:tesseract"))
case("upload row with null raw_path rejected", "source_inventory.json", "fail", lambda d: row(d).__setitem__("raw_path", None))
case("prior_archive_digest row with digest_of + null raw_path accepted", "source_inventory.json", "pass")
case("prior_archive_digest row without digest_of rejected", "source_inventory.json", "fail", lambda d: row(d, 3).pop("digest_of"))
case("prior_archive_digest row with a placeholder raw_path rejected", "source_inventory.json", "fail",
     lambda d: row(d, 3).__setitem__("raw_path", "raw/ingest/prior_archive_pointer.txt"))
case("prior_archive_digest row with a format adapter rejected", "source_inventory.json", "fail",
     lambda d: row(d, 3).__setitem__("adapter", "pdf_pages"))
case("digest_of archive_ref as absolute path rejected", "source_inventory.json", "fail",
     lambda d: row(d, 3)["digest_of"].__setitem__("archive_ref", "/Users/someone/archive"))
case("digest_of without sidecar_refs rejected", "source_inventory.json", "fail",
     lambda d: row(d, 3)["digest_of"].__setitem__("sidecar_refs", []))
case("unknown source_kind rejected", "source_inventory.json", "fail", lambda d: row(d).__setitem__("source_kind", "email"))
case("skip reason outside the pinned enum rejected", "source_inventory.json", "fail",
     lambda d: d["skipped_inputs"][0].__setitem__("reason", "unreadable"))
case("skip input_ref as an original upload name rejected", "source_inventory.json", "fail",
     lambda d: d["skipped_inputs"][0].__setitem__("input_ref", "张测试-报告.pdf"))
case("skip input_ref carrying an 11-digit run rejected", "source_inventory.json", "fail",
     lambda d: d["skipped_inputs"][0].__setitem__("input_ref", "mmexport16950000000.jpg"))
case("skip row extra key rejected (closed shape)", "source_inventory.json", "fail",
     lambda d: d["skipped_inputs"][0].__setitem__("original_name", "x.jpg"))
for r in ("ds_store", "macosx", "empty", "duplicate_sha256", "archive_container", "user_excluded", "quarantined_irrelevant"):
    case(f"skip reason {r} accepted", "source_inventory.json", "pass",
         lambda d, r=r: d["skipped_inputs"][0].__setitem__("reason", r))

# ---- comorbidities v2.1 (O-05)
case("medication without administration_setting rejected", "comorbidities.json", "fail", lambda d: med(d).pop("administration_setting"))
case("medication without setting_basis key rejected", "comorbidities.json", "fail", lambda d: med(d).pop("setting_basis"))
case("administration_setting outside enum rejected", "comorbidities.json", "fail",
     lambda d: med(d).__setitem__("administration_setting", "outpatient"))
case("day_ward with null setting_basis rejected", "comorbidities.json", "fail", lambda d: med(d).__setitem__("setting_basis", None))
case("unknown setting with null basis accepted", "comorbidities.json", "pass",
     lambda d: med(d).update({"administration_setting": "unknown", "setting_basis": None}))
case("bad order_role rejected", "comorbidities.json", "fail", lambda d: med(d).__setitem__("order_role", "chemo"))
case("order_role optional", "comorbidities.json", "pass", lambda d: med(d).pop("order_role"))
case("prior_archive provenance accepted", "comorbidities.json", "pass", lambda d: med(d).__setitem__("provenance_layer", "prior_archive"))

# ---- labs v2.1 (O-03)
case("value without pairing_method rejected", "labs.json", "fail", lambda d: val(d).pop("pairing_method"))
case("linear_position with a confirmed value rejected", "labs.json", "fail", lambda d: val(d).__setitem__("value", 2.1))
case("linear_position without candidate_value rejected", "labs.json", "fail", lambda d: val(d).pop("candidate_value"))
case("linear_position with null candidate rejected", "labs.json", "fail", lambda d: val(d).__setitem__("candidate_value", None))
case("linear_position without confidence rejected", "labs.json", "fail", lambda d: val(d).__setitem__("pairing_confidence", None))
case("refused pairing (none) with a candidate rejected", "labs.json", "fail",
     lambda d: val(d).update({"pairing_method": "none", "pairing_confidence": None}))
case("refused pairing (none) with nulls accepted", "labs.json", "pass",
     lambda d: val(d).update({"pairing_method": "none", "candidate_value": None, "pairing_confidence": None}))
case("native_table confirmed value accepted", "labs.json", "pass",
     lambda d: val(d).update({"pairing_method": "native_table", "value": 2.1, "candidate_value": None,
                              "pairing_confidence": "high"}))
case("confirmed value and candidate together rejected", "labs.json", "fail",
     lambda d: val(d).update({"pairing_method": "bbox", "value": 2.1}))
case("bad pairing_method rejected", "labs.json", "fail", lambda d: val(d).__setitem__("pairing_method", "guess"))

# ---- treatment_lines v2.1 (S-02/O-05 source)
case("episode without status rejected", "treatment_lines.json", "fail", lambda d: ep(d).pop("status"))
case("episode without status_basis rejected", "treatment_lines.json", "fail", lambda d: ep(d).pop("status_basis"))
case("bad status rejected", "treatment_lines.json", "fail", lambda d: ep(d).__setitem__("status", "active"))
case("bad status_basis rejected", "treatment_lines.json", "fail", lambda d: ep(d).__setitem__("status_basis", "imaging"))
case("ongoing without status_as_of rejected", "treatment_lines.json", "fail", lambda d: ep(d).__setitem__("status_as_of", None))
case("ongoing with basis none rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).update({"status_basis": "none", "status_basis_text": None}))
case("clinician-note basis without verbatim text rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).__setitem__("status_basis_text", None))
case("patient_reported basis ongoing accepted (D1=B)", "treatment_lines.json", "pass",
     lambda d: ep(d).update({"status_basis": "patient_reported", "status_basis_text": "家属说一直在用"}))
case("basis none must be status unknown", "treatment_lines.json", "fail",
     lambda d: ep(d, 0).update({"status": "stopped", "status_basis": "none"}))
case("line_number 0 rejected", "treatment_lines.json", "fail", lambda d: ep(d).__setitem__("line_number", 0))
case("status_as_of must be a day", "treatment_lines.json", "fail", lambda d: ep(d).__setitem__("status_as_of", "2030-01"))
# B1: a cycle is not a line — one episode per regimen, the cycle wording kept verbatim
case("cycle_label_verbatim accepted (fixture: 第2周期)", "treatment_lines.json", "pass")
case("cycle_label_verbatim optional", "treatment_lines.json", "pass", lambda d: ep(d).pop("cycle_label_verbatim"))
case("cycle_label_verbatim null accepted", "treatment_lines.json", "pass", lambda d: ep(d).__setitem__("cycle_label_verbatim", None))
case("empty cycle_label_verbatim rejected", "treatment_lines.json", "fail", lambda d: ep(d).__setitem__("cycle_label_verbatim", ""))
case("numeric cycle_label_verbatim rejected (verbatim wording, not a count)", "treatment_lines.json", "fail",
     lambda d: ep(d).__setitem__("cycle_label_verbatim", 3))
# B3: an undated family statement of ongoing therapy — the ONLY ongoing form with status_as_of null
UNDATED = {"status": "ongoing", "status_basis": "patient_reported", "status_basis_text": "示例方案B现在还在打，每三周一次",
           "status_as_of": None, "status_as_of_precision": "undated_self_report", "provenance_layer": "caregiver_reported"}
case("undated self-report: ongoing + patient_reported + null date + precision accepted", "treatment_lines.json", "pass",
     lambda d: ep(d).update(UNDATED))
case("undated past-tense self-report (status unknown) accepted", "treatment_lines.json", "pass",
     lambda d: (ep(d).update(UNDATED), ep(d).__setitem__("status", "unknown")))
case("undated self-report of a stopped course accepted", "treatment_lines.json", "pass",
     lambda d: (ep(d).update(UNDATED), ep(d).__setitem__("status", "stopped")))
case("undated self-report said by the patient (provenance patient_reported) accepted", "treatment_lines.json", "pass",
     lambda d: (ep(d).update(UNDATED), ep(d).__setitem__("provenance_layer", "patient_reported")))
case("undated self-report left at provenance source_reported rejected (a family statement is not a record)",
     "treatment_lines.json", "fail", lambda d: (ep(d).update(UNDATED), ep(d).__setitem__("provenance_layer", "source_reported")))
case("ongoing + patient_reported + null date WITHOUT the precision marker rejected", "treatment_lines.json", "fail",
     lambda d: (ep(d).update(UNDATED), ep(d).pop("status_as_of_precision")))
case("ongoing + null date + precision but a clinician basis rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).update(dict(UNDATED, status_basis="clinician_note_current")))
case("ongoing + null date + precision but an order/indication basis rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).update(dict(UNDATED, status_basis="order_or_indication_only")))
case("undated_self_report with a date rejected (the marker means there is none)", "treatment_lines.json", "fail",
     lambda d: ep(d).update(dict(UNDATED, status_as_of="2030-01-10")))
case("undated_self_report on a clinician-note episode rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).__setitem__("status_as_of_precision", "undated_self_report"))
case("undated_self_report without a status_as_of key rejected", "treatment_lines.json", "fail",
     lambda d: (ep(d).update(UNDATED), ep(d).pop("status_as_of")))
case("precision day with a date accepted", "treatment_lines.json", "pass", lambda d: ep(d).__setitem__("status_as_of_precision", "day"))
case("precision day with a null date rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).update({"status_as_of_precision": "day", "status_as_of": None, "status": "stopped"}))
case("precision outside the enum rejected", "treatment_lines.json", "fail",
     lambda d: ep(d).__setitem__("status_as_of_precision", "month"))
case("stopped patient report without a date needs no marker", "treatment_lines.json", "pass",
     lambda d: ep(d).update({"status": "stopped", "status_basis": "patient_reported", "status_basis_text": "已经停药",
                             "status_as_of": None}))

# ---- timeline v2.1 (O-02 acute link, O-07 conflict_group)
case("event without conflict_group key rejected", "timeline.json", "fail", lambda d: ev(d, "E-003").pop("conflict_group"))
case("event without acute_finding_id key rejected", "timeline.json", "fail", lambda d: ev(d, "E-003").pop("acute_finding_id"))
case("acute_finding event without an id rejected", "timeline.json", "fail", lambda d: ev(d, "E-005").__setitem__("acute_finding_id", None))
case("unknown category rejected", "timeline.json", "fail", lambda d: ev(d, "E-003").__setitem__("category", "emergency"))
case("empty conflict_group string rejected", "timeline.json", "fail", lambda d: ev(d, "E-003").__setitem__("conflict_group", ""))

# ---- missing_items v2.1 (O-04)
case("gap without severity rejected", "missing_items.json", "fail", lambda d: gap(d).pop("severity"))
for k in ("group_key", "pages_present", "pages_missing", "page_total"):
    case(f"missing_pages gap without {k} rejected", "missing_items.json", "fail", lambda d, k=k: gap(d).pop(k))
case("missing_pages gap with empty pages_missing rejected", "missing_items.json", "fail", lambda d: gap(d).__setitem__("pages_missing", []))
case("missing_pages gap not red rejected", "missing_items.json", "fail", lambda d: gap(d).__setitem__("severity", "yellow"))
case("not_in_archive gap without page fields accepted", "missing_items.json", "pass",
     lambda d: d.__setitem__("document_gaps", [{"document_category": "病理报告", "gap_type": "not_in_archive",
                                                 "reason_for_artifact": "x", "severity": "yellow"}]))

# ---- molecular v2.1 (hla_typing)
case("missing hla_typing rejected", "molecular.json", "fail", lambda d: d.pop("hla_typing"))
case("empty hla_typing accepted", "molecular.json", "pass", lambda d: d.__setitem__("hla_typing", []))
case("HLA row without allele rejected", "molecular.json", "fail", lambda d: d["hla_typing"][0].pop("allele"))
case("HLA row extra key rejected", "molecular.json", "fail", lambda d: d["hla_typing"][0].__setitem__("restriction", "x"))
# D7: bare locus letters; zygosity-only typing = allele null + verbatim zygosity
def hla(d): return d["hla_typing"][0]
for loc in ("A", "B", "C", "DRB1", "DQB1", "DPB1"):
    case(f"bare locus {loc} accepted", "molecular.json", "pass", lambda d, loc=loc: hla(d).__setitem__("locus", loc))
for loc in ("HLA-A", "hla-a", "A*02", "HLA A", ""):
    case(f"locus {loc!r} rejected (bare letters only)", "molecular.json", "fail", lambda d, loc=loc: hla(d).__setitem__("locus", loc))
case("zygosity-only typing: allele null + zygosity 杂合 accepted", "molecular.json", "pass",
     lambda d: hla(d).update({"allele": None, "zygosity": "杂合", "resolution": None}))
case("allele null without zygosity rejected", "molecular.json", "fail", lambda d: hla(d).__setitem__("allele", None))
case("allele null with zygosity null rejected", "molecular.json", "fail", lambda d: hla(d).update({"allele": None, "zygosity": None}))
case("allele null with empty zygosity rejected", "molecular.json", "fail", lambda d: hla(d).update({"allele": None, "zygosity": ""}))
case("allele + zygosity together accepted", "molecular.json", "pass", lambda d: hla(d).__setitem__("zygosity", "纯合"))
case("empty allele string rejected", "molecular.json", "fail", lambda d: hla(d).__setitem__("allele", ""))

# ---- patient_summary v2.2 (PS verbatim)
case("2.1 rejected by strict 2.2 schema", "patient_summary.json", "fail", lambda d: d.__setitem__("schema_version", "2.1"))
case("PS verbatim missing rejected", "patient_summary.json", "fail", lambda d: d["demographics"].pop("performance_status_verbatim"))
case("PS scale label invented rejected", "patient_summary.json", "fail",
     lambda d: d["demographics"]["performance_status_verbatim"][0].__setitem__("scale_label", "ECOG(converted)"))
# D8: optional per-item provenance_layer (a digest ECOG statement is prior_archive, history only)
def ps(d): return d["demographics"]["performance_status_verbatim"][0]
case("PS item provenance_layer optional (fixture has none)", "patient_summary.json", "pass")
case("PS item provenance_layer prior_archive accepted", "patient_summary.json", "pass",
     lambda d: ps(d).__setitem__("provenance_layer", "prior_archive"))
case("PS item provenance_layer outside the enum rejected", "patient_summary.json", "fail",
     lambda d: ps(d).__setitem__("provenance_layer", "archive"))

# ---- prior_archive provenance in all 7 schemas
case("prior_archive in labs", "labs.json", "pass", lambda d: val(d).__setitem__("provenance_layer", "prior_archive"))
case("prior_archive in timeline", "timeline.json", "pass", lambda d: ev(d, "E-003").__setitem__("provenance_layer", "prior_archive"))
case("prior_archive in treatment_lines", "treatment_lines.json", "pass", lambda d: ep(d, 0).__setitem__("provenance_layer", "prior_archive"))
case("prior_archive in molecular", "molecular.json", "pass")
case("prior_archive in patient_summary", "patient_summary.json", "pass",
     lambda d: d["diagnosis"].__setitem__("provenance_layer", "prior_archive"))
case("bogus provenance rejected", "labs.json", "fail", lambda d: val(d).__setitem__("provenance_layer", "archive"))
import json
lo = {"schema_version": "longitudinal_observations_v2", "patient_code": "PT-5A1F0C", "observations": [
    {"obs_type": "lab", "metric": "x", "value": 1, "timestamp": "2029-01-01T00:00:00Z",
     "source_ref": synlib.SIDE_DIGEST + "#L15", "provenance_layer": "prior_archive", "verification_status": "unverified"}]}
errs = synlib.schema_errors("longitudinal_observations.schema.json", lo)
if errs: failed += 1; print(f"FAIL: prior_archive in longitudinal_observations {errs}", file=sys.stderr)
else: passed += 1

# ---- acute_findings v1 (O-02)
case("unknown finding_class rejected", "acute_findings.json", "fail", lambda d: af(d).__setitem__("finding_class", "pe"))
case("acuity outside enum rejected", "acute_findings.json", "fail", lambda d: af(d).__setitem__("acuity", "critical"))
case("source_ref without a line anchor rejected", "acute_findings.json", "fail",
     lambda d: af(d).__setitem__("source_ref", synlib.SIDE_CT))
case("non-default basis without verbatim basis text rejected", "acute_findings.json", "fail",
     lambda d: af(d).update({"acuity_basis": "source_wording_escalation", "acuity": "emergent"}))
case("critical flag basis must be emergent", "acute_findings.json", "fail",
     lambda d: af(d).update({"acuity_basis": "source_critical_flag", "acuity_basis_text": "危急值"}))
case("chronic wording basis must be incidental", "acute_findings.json", "fail",
     lambda d: af(d).update({"acuity_basis": "source_wording_chronic", "acuity_basis_text": "陈旧"}))
case("direction without verbatim comparison wording rejected", "acute_findings.json", "fail",
     lambda d: af(d)["change_vs_prior"].__setitem__("direction", "increased"))
case("direction 'progression' (summarised) rejected", "acute_findings.json", "fail",
     lambda d: af(d)["change_vs_prior"].update({"direction": "progression", "verbatim": "较前增多"}))
case("missing timeline_event_id rejected", "acute_findings.json", "fail", lambda d: af(d).pop("timeline_event_id"))
case("empty findings list accepted (always written)", "acute_findings.json", "pass", lambda d: d.__setitem__("findings", []))
case("finding_id pattern AF-nnn", "acute_findings.json", "fail", lambda d: af(d).__setitem__("finding_id", "F1"))

# ---- update_log v1 (O-09)
case("worker status outside enum rejected", "update_log.json", "fail", lambda d: entry(d)["workers"][0].__setitem__("status", "stalled"))
case("orchestrator as a worker rejected", "update_log.json", "fail", lambda d: entry(d)["workers"][0].__setitem__("worker_id", "orchestrator"))
case("entry without workers rejected", "update_log.json", "fail", lambda d: entry(d).pop("workers"))
case("entry without inputs rejected", "update_log.json", "fail", lambda d: entry(d).pop("inputs"))
case("input sha256 malformed rejected", "update_log.json", "fail", lambda d: entry(d)["inputs"][0].__setitem__("sha256", "x"))
case("degradation without redispatched_as rejected", "update_log.json", "fail", lambda d: entry(d)["degradations"][0].pop("redispatched_as"))
case("run_mode legacy_upgrade accepted", "update_log.json", "pass", lambda d: entry(d).__setitem__("run_mode", "legacy_upgrade"))
case("legacy hashless entry shape rejected", "update_log.json", "fail",
     lambda d: d.__setitem__("entries", [{"at": "2030-01-20T09:00:00Z", "run_mode": "full", "phase": "phase2"}]))

print(f"organize-schema-v21: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
