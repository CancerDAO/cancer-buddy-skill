#!/usr/bin/env bash
# Legacy-archive leniency (schemas/README.md version policy): an archive written under the pre-v2.1 contract
# (readiness/timeline/labs/… "2", patient_summary "2", source_inventory_v2 — the shape
# every d84b7eb-era archive has) must VALIDATE with WARNs, never FAIL merely for its
# schema versions. The relax path (LEGACY_SCHEMA_VERSIONS / _relax_schema_for_legacy)
# must actually be invoked — the earlier e112821 version defined it and never called
# it, and popped the version property so additionalProperties:false rejected it.
# The leniency is narrow: closed shapes, types and enums still apply.
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
import validate_structured_outputs as v

tmp = Path(sys.argv[2])
passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


# 1. whole legacy archive → rc 0, legacy WARNs, relax path used for every bumped file
legacy = synlib.make_legacy(tmp / "legacy")
rc, errs, warns = synlib.validate(legacy)
check("legacy archive validates (rc 0)", rc == 0, f"rc={rc} errors={errs[:3]}")
check("archive flagged as legacy generation", any(w.startswith("archive_generation: legacy archive") for w in warns))
for f in ("patient_summary.json", "readiness.json", "timeline.json", "labs.json", "comorbidities.json",
          "treatment_lines.json", "missing_items.json", "molecular.json", "source_inventory.json"):
    check(f"legacy WARN (relax path invoked) for {f}", any(w.startswith("legacy_schema: " + f) for w in warns))
check("patient_summary v2 WARN names the missing time anchors",
      any("pre-time-anchor" in w for w in warns))
# the new v2.1 gates report as WARN on a legacy archive, never as ERROR
for needle in ("acute_findings.json: missing", "carry no EXTRACTOR", "bare [OCR_UNCERTAIN]",
               "page_completeness:", "profile_demographics:"):
    check(f"v2.1 gate '{needle}' is a legacy WARN", any(needle in w for w in warns))
    check(f"v2.1 gate '{needle}' is not an ERROR", not any(needle in e for e in errs))

# 2. the relax is narrow: a legacy doc with an unknown key still FAILS
def add_unknown(d):
    synlib.edit_json(d, "labs.json", lambda doc: doc["panels"][0]["values"][0].__setitem__("guess", 1))
bad = synlib.make(tmp / "legacy_bad", lambda d: (synlib.downgrade_to_legacy(d), add_unknown(d)))
rc, errs, _ = synlib.validate(bad)
check("legacy doc with an unknown key still ERRORs", rc == 1 and any("labs.json: schema violation" in e for e in errs), str(errs[:2]))

# 3. an unknown version (neither current nor registered legacy) FAILS
unk = synlib.make(tmp / "legacy_unknown", lambda d: (synlib.downgrade_to_legacy(d),
      synlib.edit_json(d, "timeline.json", lambda doc: doc.__setitem__("schema_version", "1"))))
rc, errs, _ = synlib.validate(unk)
check("unregistered version '1' ERRORs", any("timeline.json: schema violation at schema_version" in e for e in errs), str(errs[:2]))

# 4. relax helper: version const swapped (not removed), only named required fields dropped
schema = synlib.json.loads((synlib.SCHEMAS / "readiness.schema.json").read_text(encoding="utf-8"))
relaxed, note = v.schema_for_document("readiness.json", schema, {"schema_version": "2"})
check("relaxed readiness keeps schema_version as a const", relaxed["properties"]["schema_version"] == {"const": "2"})
check("relaxed readiness drops severity/kind only", set(schema["properties"]["review_flags"]["items"]["required"])
      - set(relaxed["properties"]["review_flags"]["items"]["required"]) == {"severity", "kind"})
check("relaxed readiness still closed", relaxed["additionalProperties"] is False)
check("current version gets the strict schema and no note",
      v.schema_for_document("readiness.json", schema, {"schema_version": "2.1"}) == (schema, None))

# 5. Mixed versions. Leniency is for a WHOLLY legacy archive only: inside a current-contract
#    archive (readiness 2.1 / organize_meta.json) a structured file written at an old version
#    is an ERROR and is held to the strict schema — otherwise a run could write "2" and skip
#    every v2.1 required field (pairing_method, status/status_basis, administration_setting …).
ps21 = synlib.make(tmp / "ps21", lambda d: synlib.edit_json(d, "patient_summary.json",
       lambda doc: (doc.__setitem__("schema_version", "2.1"), doc["demographics"].pop("performance_status_verbatim"))))
rc, errs, warns = synlib.validate(ps21)
check("patient_summary 2.1 in a current archive → mixed-version ERROR",
      rc == 1 and any(e.startswith("mixed-version archive: patient_summary.json is schema_version '2.1'") for e in errs),
      str(errs[:2]))
check("…validated strictly (the missing PS verbatim is reported too)",
      any("patient_summary.json: schema violation" in e and "performance_status_verbatim" in e for e in errs), str(errs[:4]))
check("…and not downgraded to a WARN", not any("legacy_schema: patient_summary.json" in w for w in warns))
ps22 = synlib.make(tmp / "ps22", lambda d: synlib.edit_json(d, "patient_summary.json",
       lambda doc: doc["demographics"].pop("performance_status_verbatim")))
rc, errs, _ = synlib.validate(ps22)
check("patient_summary 2.2 without PS verbatim ERRORs", rc == 1 and any("performance_status_verbatim" in e for e in errs))


def labs_v2_confirmed(d):
    # v1-shaped bypass: labs rewritten as "2", the v2.1 pairing fields dropped and the
    # position-paired candidates promoted into value
    def fn(doc):
        doc["schema_version"] = "2"
        for p in doc["panels"]:
            for val in p["values"]:
                val["value"] = float(val.pop("candidate_value"))
                for k in ("pairing_method", "pairing_confidence", "pairing_note"):
                    val.pop(k, None)
    synlib.edit_json(d, "labs.json", fn)
mixed = synlib.make(tmp / "mixed_labs", labs_v2_confirmed)
rc, errs, warns = synlib.validate(mixed)
check("current archive + labs '2' with candidates promoted to value → rc 1", rc == 1, str(errs[:3]))
check("…named as a mixed-version archive", any("mixed-version archive: labs.json is schema_version '2'" in e for e in errs))
check("…and the missing pairing_method is reported", any("labs.json: schema violation" in e and "pairing_method" in e for e in errs))
inv_old = synlib.make(tmp / "mixed_inv", lambda d: synlib.edit_json(d, "source_inventory.json",
                      lambda doc: doc.__setitem__("schema", "source_inventory_v2")))
rc, errs, _ = synlib.validate(inv_old)
check("current archive + source_inventory_v2 → mixed-version ERROR",
      rc == 1 and any("mixed-version archive: source_inventory.json is schema 'source_inventory_v2'" in e for e in errs), str(errs[:3]))
# the same patient_summary "2.1" inside a wholly legacy archive stays a WARN
def ps21_doc():
    doc = synlib.fixture_doc("patient_summary.json")
    doc["schema_version"] = "2.1"
    doc["demographics"].pop("performance_status_verbatim")
    return doc
leg21 = synlib.make(tmp / "legacy_ps21", lambda d: (synlib.downgrade_to_legacy(d),
                    synlib.save(d, "patient_summary.json", ps21_doc())))
rc, errs, warns = synlib.validate(leg21)
check("legacy archive + patient_summary 2.1 → WARN, rc 0",
      rc == 0 and any(w.startswith("legacy_schema: patient_summary.json") for w in warns), str(errs[:3]))

# 6. the same new-gate condition that WARNs on legacy FAILS on a current archive
cur = synlib.make(tmp / "current_no_acute", lambda d: (d / "acute_findings.json").unlink())
rc, errs, _ = synlib.validate(cur)
check("current archive without acute_findings.json ERRORs", rc == 1 and any("acute_findings.json: missing" in e for e in errs))

# 7. organize_meta.json alone marks an archive current (a writer that wrote readiness "2")
meta = synlib.make(tmp / "meta_marks_current", lambda d: (synlib.downgrade_to_legacy(d),
       synlib.save(d, "organize_meta.json", {"skill": "cancer-buddy-organize", "skill_version": None,
            "skill_commit": None, "skill_dirty": None, "skill_fingerprint": "sha256:" + "0" * 64,
            "generated_at": "2030-01-20T09:00:00Z"})))
check("organize_meta.json ⇒ current generation", v.archive_generation(meta) == "current")
rc, errs, _ = synlib.validate(meta)
check("…so the v2.1 gates FAIL there", rc == 1 and any("acute_findings.json: missing" in e for e in errs))

print(f"legacy-schema-read: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
