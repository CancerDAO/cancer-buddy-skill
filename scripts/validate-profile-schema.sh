#!/usr/bin/env bash
# Field-level validator for patients/<patient_code>/profile.json (and readiness.json).
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
import json, sys, os
from datetime import datetime

d = sys.argv[1]
errs = []

def fail(msg): errs.append(msg)

try:
    with open(f"{d}/profile.json") as f:
        p = json.load(f)
except Exception as e:
    print(f"ERROR: profile.json not parseable: {e}", file=sys.stderr); sys.exit(1)

if not isinstance(p, dict):
    print(f"ERROR: profile.json must be a JSON object, got {type(p).__name__}", file=sys.stderr); sys.exit(1)

for key in ("schema_version", "patient_code", "diagnosis"):
    if key not in p:
        fail(f"missing required field: {key}")
    elif p[key] is None:
        fail(f"required field {key} must not be null")

if "diagnosis" in p and p["diagnosis"] is not None:
    if not isinstance(p["diagnosis"], dict):
        fail(f"diagnosis must be an object, got {type(p['diagnosis']).__name__}")
    else:
        for k in ("primary_site", "histology", "stage"):
            if k not in p["diagnosis"]:
                fail(f"missing diagnosis.{k}")
            elif p["diagnosis"][k] is None:
                fail(f"diagnosis.{k} must not be null")

basics = p.get("basics")
if basics is None:
    basics = {}
elif not isinstance(basics, dict):
    fail(f"basics must be an object, got {type(basics).__name__}")
    basics = {}
if "ecog" in basics and basics["ecog"] is not None:
    if not (isinstance(basics["ecog"], int) and 0 <= basics["ecog"] <= 4):
        fail(f"invalid basics.ecog: {basics['ecog']} (must be 0-4)")

if "sex" in basics and basics["sex"] is not None and basics["sex"] not in ("M", "F"):
    fail(f"invalid basics.sex: {basics['sex']}")

if "disclosure_state" in p and p["disclosure_state"] is not None:
    if p["disclosure_state"] not in ("full", "partial", "suppressed"):
        fail(f"invalid disclosure_state: {p['disclosure_state']}")

if "acp_status" in p and p["acp_status"] is not None:
    if p["acp_status"] not in ("none", "discussed", "documented", "legally_filed"):
        fail(f"invalid acp_status: {p['acp_status']}")

if "surveillance_schedule_anchor" in p and p["surveillance_schedule_anchor"]:
    try:
        datetime.strptime(p["surveillance_schedule_anchor"], "%Y-%m-%d")
    except ValueError:
        fail(f"invalid surveillance_schedule_anchor date: {p['surveillance_schedule_anchor']}")

th = p.get("treatment_history")
if th is not None and not isinstance(th, list):
    fail(f"treatment_history must be an array, got {type(th).__name__}")
if isinstance(th, list):
    last_start = None
    last_line = None
    for i, t in enumerate(th):
        if not isinstance(t, dict): continue
        if t.get("line") is not None and last_line is not None and t["line"] < last_line:
            fail(f"treatment_history[{i}] line {t['line']} < previous line {last_line}")
        if t.get("line") is not None: last_line = t["line"]
        if t.get("start"):
            try:
                s = datetime.strptime(t["start"], "%Y-%m-%d")
                if last_start is not None and s < last_start:
                    fail(f"treatment_history[{i}] start {t['start']} before previous")
                last_start = s
            except ValueError:
                fail(f"treatment_history[{i}] invalid start date: {t['start']}")

rpath = f"{d}/readiness.json"
if os.path.exists(rpath):
    try:
        with open(rpath) as f:
            r = json.load(f)
        if not isinstance(r, dict):
            fail(f"readiness.json must be a JSON object, got {type(r).__name__}")
            r = {}
        if r.get("grade") is not None and r["grade"] not in ("A", "B", "C", "D", "F"):
            fail(f"invalid readiness.grade: {r['grade']}")
        if r.get("review_flags") is not None:
            rf = r["review_flags"]
            if not isinstance(rf, list):
                fail(f"review_flags must be array, got {type(rf).__name__}")
            else:
                allowed_severity = ("red", "yellow", "green")
                allowed_category = (
                    "format_violation",
                    "cross_doc_contradiction",
                    "clinical_logic_anomaly",
                    "unverified_critical_field",
                    "value_trend_anomaly",
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
        if not isinstance(ro, dict):
            fail(f"role.json must be a JSON object, got {type(ro).__name__}")
        elif ro.get("active_role") not in ("patient", "caregiver", "family"):
            fail(f"invalid role.json.active_role: {ro.get('active_role')}")
    except Exception as e:
        fail(f"role.json unparseable: {e}")

if errs:
    for e in errs: print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
print("profile schema OK")
PY
