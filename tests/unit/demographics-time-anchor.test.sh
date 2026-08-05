#!/usr/bin/env bash
# demographics time-anchor gate (patient_summary schema v2.1)
#
# Root cause this guards: age was modelled as a bare scalar next to `sex`, so two
# reports from different years stating different ages landed in one slot, were read
# as a cross-source contradiction, and got stuck `disputed` forever (a state only a
# formal amendment can clear — which an age can never obtain).
#
# The structural half of the fix is deterministically testable and asserted here:
# every point-in-time demographic must carry its own `_as_of` source date, and the
# age series must be preserved. The judgement half (§2.1 of
# organizer-prompt-phase2-synthesis.md — natural ageing is NOT a conflict) is
# prompt-level; it is covered by tests/eval/scenarios/cancer-buddy-organize.md org-05.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCHEMA="$ROOT/skills/cancer-buddy-organize/references/schemas/patient_summary.schema.json"

if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2
  exit 0
fi

python3 - "$SCHEMA" <<'PY'
import copy, json, sys
import jsonschema

schema = json.load(open(sys.argv[1]))
validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

BASE = {
    "patient_code": "PT-A1B2",
    "schema_version": "2.1",
    "generated_at": "2026-08-05T00:00:00Z",
    "demographics": {
        "sex": "女",
        "sex_normalized": "female",
        "age": 55,
        "age_as_of": "2026-03-11",
        "age_observations": [
            {"value": 52, "as_of": "2023-04-02", "source_ref": "04_诊断与分期/a.md"},
            {"value": 55, "as_of": "2026-03-11", "source_ref": "04_诊断与分期/b.md"},
        ],
        "birth_year": 1970,
        "height_cm": 162,
        "height_cm_as_of": "2023-04-02",
        "weight_kg": 58.5,
        "weight_kg_as_of": "2026-03-11",
        "ecog": 1,
        "ecog_as_of": "2026-03-11",
        "function_description": None,
        "provenance_layer": "source_reported",
        "verification_status": "unverified",
        "source_refs": ["04_诊断与分期/b.md"],
    },
    "diagnosis": {
        "primary": None, "histology": None, "icd10": None, "diagnosed_at": None, "stage": None,
        "metastasis_sites": [],
        "provenance_layer": "source_reported", "verification_status": "unverified", "source_refs": [],
    },
    "current_status": {
        "regimen": None, "response": None, "ecog": None, "as_of": None,
        "provenance_layer": "source_reported", "verification_status": "unverified", "source_refs": [],
    },
}

passed = failed = 0


def case(label, expected, mutate):
    """expected: 'pass' = document must validate, 'fail' = schema must reject it."""
    global passed, failed
    doc = copy.deepcopy(BASE)
    mutate(doc)
    try:
        validator.validate(doc)
        got = "pass"
    except jsonschema.ValidationError:
        got = "fail"
    if got == expected:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} expected={expected} got={got}", file=sys.stderr)


def demo(doc):
    return doc["demographics"]


# 1. The reported bug's shape: three years apart, two different ages, one archive.
#    Must be a VALID document — the series is expressible, so nothing forces the
#    synthesizer to collapse it into a single self-contradicting slot.
case("cross-year age series is representable", "pass", lambda d: None)

# 2. Every point-in-time field's anchor is required (nullable, but must be present).
for field in ("age_as_of", "height_cm_as_of", "weight_kg_as_of", "ecog_as_of",
              "age_observations", "birth_year"):
    case(f"missing {field} rejected", "fail",
         lambda d, f=field: demo(d).pop(f))

# 3. An age observation without its own date is meaningless — reject.
case("age_observation without as_of rejected", "fail",
     lambda d: demo(d).__setitem__("age_observations",
                                   [{"value": 52, "source_ref": "04_诊断与分期/a.md"}]))

# 4. Full DOB must not be smuggled back in (additionalProperties:false is the floor).
case("date_of_birth field rejected", "fail",
     lambda d: demo(d).__setitem__("date_of_birth", "1970-05-14"))

# 5. birth_year stays a coarse year, never a date.
case("birth_year as date string rejected", "fail",
     lambda d: demo(d).__setitem__("birth_year", "1970-05-14"))
case("birth_year null when undeterminable", "pass",
     lambda d: demo(d).__setitem__("birth_year", None))

# 6. No age stated in any source is legitimate — null everything, do not invent one.
case("no age stated anywhere", "pass",
     lambda d: demo(d).update({"age": None, "age_as_of": None,
                               "age_observations": [], "birth_year": None}))

# 7. age_basis is opt-in and enum-locked (周岁/虚岁 only when the source says so).
case("age_basis nominal_years accepted", "pass",
     lambda d: demo(d)["age_observations"][0].__setitem__("age_basis", "nominal_years"))
case("invented age_basis rejected", "fail",
     lambda d: demo(d)["age_observations"][0].__setitem__("age_basis", "lunar"))

# 8. A pre-fix v2 archive must no longer validate: it carries no time anchors, so it
#    has to be re-organized rather than silently read as if current.
case("pre-fix schema_version 2 rejected", "fail",
     lambda d: d.__setitem__("schema_version", "2"))

# 9. Ages stay integers as the source stated them — no recomputed fractional age.
case("fractional age rejected", "fail",
     lambda d: demo(d)["age_observations"][0].__setitem__("value", 52.7))

# 10. An out-of-range birth_year is a transcription error, not a fact.
case("birth_year 1750 rejected", "fail",
     lambda d: demo(d).__setitem__("birth_year", 1750))

print(f"demographics-time-anchor: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
