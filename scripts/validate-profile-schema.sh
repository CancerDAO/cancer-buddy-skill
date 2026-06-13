#!/usr/bin/env bash
# Field-level validator for patients/<patient_code>/profile.json (cancer_buddy_profile_v3),
# plus readiness.json and role.json when present.
# Usage: validate-profile-schema.sh <patient_dir>
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <patient_dir>" >&2
  exit 2
fi
DIR="$1"

if [[ ! -d "$DIR" ]]; then
  echo "ERROR: directory $DIR does not exist" >&2
  exit 1
fi
if [[ ! -f "$DIR/profile.json" ]]; then
  echo "ERROR: $DIR/profile.json missing" >&2
  exit 1
fi

python3 - "$DIR" <<'PY'
import json, sys, re

d = sys.argv[1]
errs = []

def fail(msg): errs.append(msg)

try:
    with open(f"{d}/profile.json") as f:
        p = json.load(f)
except Exception as e:
    print(f"ERROR: profile.json not parseable: {e}", file=sys.stderr); sys.exit(1)

# --- profile.json: cancer_buddy_profile_v3 (nested) shape ---
# Authority: references/patient-profile-schema.md. Diagnosis fields live under
# summary.* (NOT the retired flat top-level diagnosis/primary_cancer); ECOG lives
# under latest_status; detailed demographics / molecular drivers / treatment lines
# live in patient_summary.json / molecular.json / treatment_lines.json and are
# validated by validate_structured_outputs.py, NOT here.
for key in ("schema", "patient_code", "summary"):
    if key not in p: fail(f"missing required field: {key}")

if "schema" in p and p["schema"] != "cancer_buddy_profile_v3":
    fail(f"schema must be 'cancer_buddy_profile_v3', got {p['schema']!r}")

if "patient_code" in p and not re.match(r"^PT-", str(p["patient_code"])):
    fail(f"invalid patient_code (must match ^PT-): {p['patient_code']}")

summary = p.get("summary")
if "summary" in p and not isinstance(summary, dict):
    fail("summary must be an object")
elif isinstance(summary, dict):
    for k in ("primary", "histology", "stage"):
        if k not in summary: fail(f"missing summary.{k}")

# ECOG moved under latest_status in v3; validate when present and non-null.
ls = p.get("latest_status", {})
if isinstance(ls, dict) and ls.get("ecog") is not None:
    if not (isinstance(ls["ecog"], int) and 0 <= ls["ecog"] <= 4):
        fail(f"invalid latest_status.ecog: {ls['ecog']} (must be int 0-4 or null)")

# disclosure_state: top-level optional, written by cancer-buddy-disclosure.
if "disclosure_state" in p and p["disclosure_state"] is not None:
    if p["disclosure_state"] not in ("full", "partial", "suppressed"):
        fail(f"invalid disclosure_state: {p['disclosure_state']}")

import os
rpath = f"{d}/readiness.json"
if os.path.exists(rpath):
    try:
        with open(rpath) as f:
            r = json.load(f)
        if "grade" in r and r["grade"] not in ("A", "B", "C", "D", "F"):
            fail(f"invalid readiness.grade: {r['grade']}")
        if "review_flags" in r:
            rf = r["review_flags"]
            if not isinstance(rf, list):
                fail(f"review_flags must be array, got {type(rf).__name__}")
            else:
                allowed_severity = ("red", "yellow", "green")
                # Full 9-category roster — authoritative in
                # organizer-prompt-phase2-synthesis.md Step 3 (table rows 1-9),
                # organize-contract.md §2.4, patient-profile-schema.md.
                allowed_category = (
                    "format_violation",
                    "cross_doc_contradiction",
                    "clinical_logic_anomaly",
                    "unverified_critical_field",
                    "value_trend_anomaly",
                    "cross_patient_name_collision",
                    "anchor_coverage_gap",
                    "relevance_uncertain",
                    "filename_content_mismatch",
                )
                required_keys = ("id", "severity", "category", "field_path",
                                 "current_value", "issue", "source_evidence",
                                 "suggested_action", "user_confirmed")
                for i, item in enumerate(rf):
                    if not isinstance(item, dict):
                        fail(f"review_flags[{i}] must be object")
                        continue
                    for k in required_keys:
                        if k not in item:
                            fail(f"review_flags[{i}] missing {k}")
                    if "severity" in item and item["severity"] not in allowed_severity:
                        fail(f"review_flags[{i}] severity {item['severity']} not in {allowed_severity}")
                    if "category" in item and item["category"] not in allowed_category:
                        fail(f"review_flags[{i}] category {item['category']} not in {allowed_category}")
                    if "source_evidence" in item and not isinstance(item["source_evidence"], list):
                        fail(f"review_flags[{i}] source_evidence must be array")
                    if "user_confirmed" in item and not isinstance(item["user_confirmed"], bool):
                        fail(f"review_flags[{i}] user_confirmed must be boolean")
    except Exception as e:
        fail(f"readiness.json unparseable: {e}")

role_path = f"{d}/role.json"
if os.path.exists(role_path):
    try:
        with open(role_path) as f:
            ro = json.load(f)
        if ro.get("active_role") not in ("patient", "caregiver", "family"):
            fail(f"invalid role.json.active_role: {ro.get('active_role')}")
    except Exception as e:
        fail(f"role.json unparseable: {e}")

if errs:
    for e in errs: print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
print("profile schema OK")
PY
