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
import json, os, re, sys

root = sys.argv[1]
errors = []
def fail(message): errors.append(message)
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
if os.path.exists(rpath):
    r = load("readiness.json")
    if isinstance(r, dict):
        if r.get("schema_version") != "2": fail("readiness.schema_version must be '2'")
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
            allowed_resolution = {"unresolved", "resolved_by_corrected_source", "resolved_by_clinician_attestation", "resolved_administratively"}
            for index, item in enumerate(flags):
                if not isinstance(item, dict):
                    fail(f"review_flags[{index}] must be object"); continue
                for key in required:
                    if key not in item: fail(f"review_flags[{index}] missing {key}")
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

if errors:
    for error in errors: print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)
print("profile schema OK")
PY
