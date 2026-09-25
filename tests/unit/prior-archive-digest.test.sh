#!/usr/bin/env bash
# O-06 prior-archive digest layer.
#   source_inventory: a source_kind=prior_archive_digest row passes with digest_of and a
#   null raw_path, and fails without digest_of / with a placeholder raw pointer (the
#   shape an earlier run faked). Facts restated only from the digest carry
#   provenance_layer prior_archive; a prior_archive fact cites the digest; the digest
#   never feeds current status (gate_prior_archive_usage). Synthetic archive only.
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
DG = synlib.SIDE_DIGEST


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def make(mutate=None):
    global n
    n += 1
    return synlib.make(tmp / f"p{n}", mutate)


def digest_row(fn):
    return lambda d: synlib.edit_json(d, "source_inventory.json",
                                      lambda doc: fn(next(r for r in doc["files"] if r["source_kind"] == "prior_archive_digest")))


# ---- inventory row
d = make()
errs, _ = synlib.gate("gate_source_inventory", d)
check("digest row with digest_of + null raw_path passes", errs == [], str(errs))
d = make(digest_row(lambda r: r.pop("digest_of")))
errs, _ = synlib.gate("gate_source_inventory", d)
check("digest row without digest_of → ERROR", any("requires digest_of" in e for e in errs), str(errs))
d = make(digest_row(lambda r: r.__setitem__("raw_path", "raw/ingest/prior_archive_pointer.txt")))
errs, _ = synlib.gate("gate_source_inventory", d)
check("digest row with a placeholder raw pointer → ERROR", any("raw_path must be null" in e for e in errs), str(errs))
d = make(digest_row(lambda r: r.__setitem__("source_kind", "upload")))
errs, _ = synlib.gate("gate_source_inventory", d)
check("the same row as an upload (null raw_path) → ERROR", any("raw_path must point under raw/" in e for e in errs), str(errs))

# ---- usage of digest facts
def ep(fn):
    return lambda d: synlib.edit_json(d, "treatment_lines.json", lambda doc: fn(doc["episodes"][0]))
d = make()
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("clean archive: digest facts are prior_archive and history-only", errs == [], str(errs))
d = make(ep(lambda e: e.__setitem__("provenance_layer", "source_reported")))
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("digest-only fact labelled source_reported → ERROR", any("sourced only from the prior-archive digest" in e for e in errs), str(errs))
d = make(lambda d: synlib.edit_json(d, "timeline.json", lambda doc: next(
    e for e in doc["events"] if e["event_id"] == "E-003").__setitem__("provenance_layer", "prior_archive")))
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("prior_archive fact that cites no digest → ERROR", any("cites no prior_archive_digest source" in e for e in errs), str(errs))
d = make(lambda d: synlib.edit_json(d, "patient_summary.json", lambda doc: doc["current_status"]["source_refs"].append(DG + "#L15")))
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("digest cited by patient_summary.current_status → ERROR", any("current_status cites the prior-archive digest" in e for e in errs), str(errs))
d = make(lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["latest_status"]["source_refs"].append(DG + "#L15")))
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("digest cited by profile.latest_status → ERROR", any("latest_status cites the prior-archive digest" in e for e in errs), str(errs))
d = make(ep(lambda e: e.update({"status": "ongoing", "status_basis": "clinician_note_current",
                                "status_basis_text": "x", "status_as_of": "2029-06-01"})))
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("ongoing episode resting on the digest → ERROR", any("never establishes current therapy" in e for e in errs), str(errs))
d = make(lambda d: synlib.edit_json(d, "comorbidities.json", lambda doc: doc["medications"][0].update(
    {"use_status": "active_confirmed", "source_refs": [DG + "#L15"], "provenance_layer": "prior_archive"})))
errs, _ = synlib.gate("gate_prior_archive_usage", d)
check("active medication resting on the digest → ERROR", any("history only" in e for e in errs), str(errs))

# ---- the whole clean archive still validates (positive control through main)
rc, errs, _ = synlib.validate(make())
check("clean archive with a digest passes the full validator", rc == 0, str(errs[:3]))

print(f"prior-archive-digest: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
