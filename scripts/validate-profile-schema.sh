#!/usr/bin/env bash
# Validate profile.json plus compatibility readiness.json/role.json when present.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <patient_dir>" >&2
  exit 2
fi
DIR="$1"
[[ -d "$DIR" ]] || { echo "ERROR: directory $DIR does not exist" >&2; exit 1; }
[[ -f "$DIR/profile.json" ]] || { echo "ERROR: $DIR/profile.json missing" >&2; exit 1; }

python3 - "$DIR" <<'PY'
import json, os, re, sys, unicodedata

root = sys.argv[1]
errors = []
warns = []
def fail(message): errors.append(message)
def warn(message): warns.append(message)
ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PS_SCALES = {"PS", "ECOG", "KPS", "Zubrod", "unlabeled"}
PROVENANCE_LAYERS = {"source_reported", "patient_reported", "caregiver_reported", "system_normalized", "prior_archive"}
# treatment_lines.schema.json episodes[].status_basis — latest_status copies the ongoing episode's
STATUS_BASIS = {"administration_record", "clinician_note_current", "order_or_indication_only", "patient_reported",
                "dates_only", "none"}
LINE_ANCHOR = re.compile(r"#L(\d+)(?:-L(\d+))?$")
def norm(text): return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
def line_binding(ref, text):
    """None when every segment of text (elisions ……) is on the cited line(s); else a reason."""
    m = LINE_ANCHOR.search(ref)
    if not m: return f"{ref!r} carries no #L<n> line anchor"
    target = os.path.join(root, ref.split("#", 1)[0])
    if not os.path.isfile(target): return f"{ref!r} does not resolve"
    with open(target, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    a = int(m.group(1)); b = int(m.group(2) or a)
    if a < 1 or b < a or b > len(lines): return f"{ref!r} points outside the file"
    block = norm("".join(lines[a - 1:b]))
    for seg in re.split(r"\.{3,}", unicodedata.normalize("NFKC", text)):
        if norm(seg) and norm(seg) not in block: return f"text not found on {ref}"
    return None
READINESS_CURRENT = "2.1"
READINESS_LEGACY = {"2"}  # read leniently (WARN), see validate_structured_outputs.LEGACY_SCHEMA_VERSIONS
def load(name):
    try:
        with open(os.path.join(root, name), encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        fail(f"{name} unparseable: {exc}")
        return None

p = load("profile.json")
if isinstance(p, dict):
    for key in ("schema", "patient_code", "summary"):
        if key not in p: fail(f"missing required field: {key}")
    if p.get("schema") != "cancer_buddy_profile_v3":
        fail("schema must be 'cancer_buddy_profile_v3'")
    code = p.get("patient_code")
    if not isinstance(code, str) or not re.fullmatch(r"PT-[A-F0-9]+(?:_\d+)?", code):
        fail(f"invalid patient_code: {code!r}")
    summary = p.get("summary")
    if not isinstance(summary, dict):
        fail("summary must be an object")
    else:
        # Missing clinical fields are valid unknowns; if present, they must not
        # be container values.
        for key in ("primary", "histology", "stage"):
            if key in summary and summary[key] is not None and not isinstance(summary[key], str):
                fail(f"summary.{key} must be string or null")
    latest = p.get("latest_status")
    if latest is not None and not isinstance(latest, dict):
        fail("latest_status must be object or null")
    elif isinstance(latest, dict) and latest.get("ecog") is not None:
        ecog = latest["ecog"]
        if isinstance(ecog, bool) or not isinstance(ecog, int) or not 0 <= ecog <= 5:
            fail("latest_status.ecog must be clinician-reported integer 0-5 or null")
    if p.get("disclosure_state") not in (None, "full", "partial", "suppressed", "unknown"):
        fail(f"invalid disclosure_state: {p.get('disclosure_state')!r}")

rpath = os.path.join(root, "readiness.json")
r = load("readiness.json") if os.path.exists(rpath) else None
# Same archive-generation rule as validate_structured_outputs.archive_generation():
# current = readiness.json at 2.1 OR an organize_meta.json written by the organize run.
current = (isinstance(r, dict) and r.get("schema_version") == READINESS_CURRENT) \
    or os.path.isfile(os.path.join(root, "organize_meta.json"))

# profile.latest_status (phase2 §5.7): the ongoing episode's regimen + its status_as_of (+ the
# optional status_basis, B7), or null. SMTB reads {regimen, as_of, status_basis} as a
# current-status row, so the shape is pinned on a current archive (legacy: WARN). The binding to
# the ongoing treatment_lines.json episode is validate_structured_outputs.gate_record_links.
if isinstance(p, dict) and isinstance(p.get("latest_status"), dict):
    ls = p["latest_status"]
    if ls.get("regimen") is not None and not (isinstance(ls["regimen"], str) and ls["regimen"].strip()):
        (fail if current else warn)("latest_status.regimen must be a non-empty string or null")
    if ls.get("as_of") is not None and not (isinstance(ls["as_of"], str) and ISO_DAY.match(ls["as_of"])):
        (fail if current else warn)("latest_status.as_of must be YYYY-MM-DD or null (the ongoing episode's status_as_of)")
    if ls.get("status_basis") is not None and ls["status_basis"] not in STATUS_BASIS:
        (fail if current else warn)(f"latest_status.status_basis must be one of {sorted(STATUS_BASIS)} or null "
                                    "(the ongoing episode's status_basis, copied — it says what the snapshot rests on)")
    if isinstance(ls.get("regimen"), str) and ls["regimen"].strip() and ls.get("as_of") is None \
            and ls.get("status_basis") != "patient_reported":
        (fail if current else warn)("latest_status.as_of is required whenever latest_status.regimen is set "
                                    "(null only for an undated family/patient statement: status_basis patient_reported)")

# profile.demographics (O-08): sex / age / age_as_of / performance_status_verbatim.
# Required on a current-contract archive (readiness 2.1); a legacy archive only WARNs.
# patient_summary.json is authoritative — the profile block is its copy.
if isinstance(p, dict):
    demo = p.get("demographics")
    if demo is None:
        (fail if current else warn)("profile.demographics missing (sex / age / age_as_of / performance_status_verbatim)")
    elif not isinstance(demo, dict):
        fail("profile.demographics must be an object")
    else:
        if demo.get("sex") is not None and not isinstance(demo["sex"], str):
            fail("profile.demographics.sex must be string or null")
        age = demo.get("age")
        if age is not None and (isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 130):
            fail("profile.demographics.age must be an integer 0-130 or null")
        if age is not None and not (isinstance(demo.get("age_as_of"), str) and ISO_DAY.match(demo["age_as_of"])):
            fail("profile.demographics.age_as_of (YYYY-MM-DD) required whenever age is present")
        ps = demo.get("performance_status_verbatim", [])
        if not isinstance(ps, list):
            fail("profile.demographics.performance_status_verbatim must be an array"); ps = []
        for i, item in enumerate(ps):
            if not isinstance(item, dict):
                fail(f"performance_status_verbatim[{i}] must be object"); continue
            if not isinstance(item.get("text"), str) or not item["text"].strip():
                fail(f"performance_status_verbatim[{i}].text must be the verbatim wording")
            if item.get("as_of") is not None and not (isinstance(item["as_of"], str) and ISO_DAY.match(item["as_of"])):
                fail(f"performance_status_verbatim[{i}].as_of must be YYYY-MM-DD or null")
            if item.get("scale_label") not in PS_SCALES:
                fail(f"performance_status_verbatim[{i}].scale_label must be one of {sorted(PS_SCALES)} (never converted)")
            if "provenance_layer" in item and item["provenance_layer"] not in PROVENANCE_LAYERS:
                fail(f"performance_status_verbatim[{i}].provenance_layer must be one of {sorted(PROVENANCE_LAYERS)} (optional)")
            if not isinstance(item.get("source_ref"), str):
                fail(f"performance_status_verbatim[{i}].source_ref must be a string anchor")
            elif isinstance(item.get("text"), str) and not item["source_ref"].startswith("conversation:"):
                why = line_binding(item["source_ref"], item["text"])
                if why: fail(f"performance_status_verbatim[{i}].text is not the source wording: {why}")
        if demo.get("provenance_layer") not in PROVENANCE_LAYERS:
            (fail if current else warn)(f"profile.demographics.provenance_layer must be one of {sorted(PROVENANCE_LAYERS)}")
        refs = demo.get("source_refs")
        if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs):
            (fail if current else warn)("profile.demographics.source_refs must be an array of anchors")
        elif not refs and (demo.get("sex") is not None or age is not None or ps):
            (fail if current else warn)("profile.demographics.source_refs is empty although sex / age / PS are filled")
        spath = os.path.join(root, "patient_summary.json")
        if os.path.exists(spath):
            ps_doc = load("patient_summary.json")
            sd = ps_doc.get("demographics") if isinstance(ps_doc, dict) else None
            if isinstance(sd, dict):
                for key in ("sex", "age", "age_as_of", "performance_status_verbatim"):
                    if key in sd and demo.get(key, [] if key == "performance_status_verbatim" else None) != sd.get(key):
                        fail(f"profile.demographics.{key} differs from patient_summary.demographics (authoritative)")

if isinstance(r, dict):
    sv = r.get("schema_version")
    if sv not in READINESS_LEGACY and sv != READINESS_CURRENT:
        fail(f"readiness.schema_version must be '{READINESS_CURRENT}' (legacy '2' is read with a warning)")
    elif sv in READINESS_LEGACY and current:
        fail(f"mixed-version archive: readiness.schema_version {sv!r} but organize_meta.json marks the archive "
             f"current-contract (requires '{READINESS_CURRENT}')")
    elif sv in READINESS_LEGACY:
        warn(f"readiness.schema_version {sv!r} is legacy — severity/kind and recency fields are not enforced; re-run organize")
    if current:
        for key in ("latest_source_date", "days_since_latest", "as_of_run_date"):
            if key not in r: fail(f"readiness.{key} is required (v2.1)")
        if r.get("as_of_run_date") is not None and not (isinstance(r.get("as_of_run_date"), str) and ISO_DAY.match(r["as_of_run_date"])):
            fail("readiness.as_of_run_date must be YYYY-MM-DD")
        days = r.get("days_since_latest")
        if days is not None and (isinstance(days, bool) or not isinstance(days, int) or days < 0):
            fail("readiness.days_since_latest must be a non-negative integer or null")
        if isinstance(days, int) and days > 14:
            if not any(isinstance(w, str) and (f"{days} 天" in w or f"{days}天" in w) for w in r.get("warnings") or []):
                fail(f"readiness: {days} days since the newest source (> 14) needs a warnings[] line stating the day count")
    for forbidden in ("grade", "coverage_band", "blocking_gaps"):
        if forbidden in r: fail(f"readiness.{forbidden} is retired")
    coverage = r.get("documentation_coverage")
    if coverage is not None:
        if not isinstance(coverage, dict):
            fail("documentation_coverage must be object")
        else:
            allowed = {"present", "not_in_archive", "unknown", "requested_by_clinician", "patient_declined_to_add"}
            for domain, status in coverage.items():
                if status not in allowed: fail(f"invalid documentation_coverage[{domain!r}]: {status!r}")
    flags = r.get("review_flags", [])
    if not isinstance(flags, list):
        fail("review_flags must be array")
    else:
        required = ("id", "category", "affected_field", "current_source_values", "issue", "resolution_status")
        if current:
            required = required + ("severity", "kind")
        allowed_resolution = {"unresolved", "resolved_by_corrected_source", "resolved_by_clinician_attestation", "resolved_administratively"}
        allowed_severity = {"red", "yellow", "info"}
        allowed_kind = {"legibility", "artifact", "document_intent", "conflict", "completeness", "other"}
        for index, item in enumerate(flags):
            if not isinstance(item, dict):
                fail(f"review_flags[{index}] must be object"); continue
            for key in required:
                if key not in item: fail(f"review_flags[{index}] missing {key}")
            if "severity" in item and item["severity"] not in allowed_severity:
                fail(f"review_flags[{index}] invalid severity {item['severity']!r} (extraction-uncertainty grade, not clinical)")
            if "kind" in item and item["kind"] not in allowed_kind:
                fail(f"review_flags[{index}] invalid kind {item['kind']!r}")
            if "current_source_values" in item and not isinstance(item["current_source_values"], list):
                fail(f"review_flags[{index}].current_source_values must be array")
            if item.get("resolution_status") not in allowed_resolution:
                fail(f"review_flags[{index}] invalid resolution_status")
            if "suggested_value" in item or "user_confirmed" in item:
                fail(f"review_flags[{index}] contains retired model/patient adjudication field")

role_path = os.path.join(root, "role.json")
if os.path.exists(role_path):
    role = load("role.json")
    if isinstance(role, dict) and role.get("active_role") not in ("patient", "caregiver", "family"):
        fail(f"invalid role.json.active_role: {role.get('active_role')!r}")

for w in warns: print(f"WARN: {w}", file=sys.stderr)
if errors:
    for error in errors: print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)
print("profile schema OK")
PY
