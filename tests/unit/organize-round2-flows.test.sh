#!/usr/bin/env bash
# Flows the second review found under-specified, pinned where they touch structure (all data synthetic):
#   G   gap_asks.json: the ask-once ledger has one writer (scripts/record_gap_ask.py) and a schema
#   S   upload reconciliation 替换: the superseded sidecar stays in place, the relation is
#       source_inventory.files[].superseded_by (a move to _superseded_/ breaks anchors → the gate fails)
#   R   段E restore / reclassify without re-synthesis → the recency gate fails; re-synthesized → OK
#   C   段C / legacy_upgrade conversation events must have the current timeline shape
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, shutil, subprocess, sys
from pathlib import Path
repo, tmp = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "tests/fixtures/organize-regress"))
import synlib

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


GA = repo / "skills/cancer-buddy-organize/scripts/record_gap_ask.py"


def ga(d, *args):
    p = subprocess.run([sys.executable, str(GA), str(d), *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


# ---- G ask-once ledger ------------------------------------------------------------------------------
d = synlib.make(tmp / "g")
K = "2030-01-10|03_病程与叙事文书/门诊病历|示例医院|2"
rc, out = ga(d, "check", "--item-key", K, "--today", "2030-01-20")
check("G first check → allowed", rc == 0 and out == "allowed", out)
rc, out = ga(d, "ask", "--item-key", K, "--category", "门诊病历（2030-01-10，共 2 页）", "--trigger", "step_11_4",
             "--today", "2030-01-20")
check("G ask records the invitation", rc == 0 and (d / "gap_asks.json").is_file(), out)
rc, out = ga(d, "ask", "--item-key", K, "--category", "x", "--trigger", "step_11_4", "--today", "2030-01-25")
check("G the same item within 30 days → refused, nothing written", rc == 3 and "re-offer only after 30 days" in out
      and len(json.loads((d / "gap_asks.json").read_text())["items"][0]["asked_at"]) == 1, out)
rc, out = ga(d, "ask", "--item-key", K, "--category", "x", "--trigger", "visit_prep", "--today", "2030-03-01")
check("G a pending item may be offered once more after 30 days", rc == 0, out)
rc, out = ga(d, "check", "--item-key", K, "--today", "2030-06-01")
check("G never more than two invitations", rc == 3 and "at most 2" in out, out)
K2 = "病理报告"
ga(d, "ask", "--item-key", K2, "--category", "病理报告", "--trigger", "step_11_4", "--today", "2030-01-20")
rc, out = ga(d, "status", "--item-key", K2, "--status", "declined", "--today", "2030-01-21")
rc, out = ga(d, "check", "--item-key", K2, "--today", "2031-01-01")
check("G a declined item is never offered again", rc == 3 and "declined" in out, out)
rc, all_errs, _ = synlib.validate(d)
check("G the script's ledger validates against gap_asks.schema.json (whole validator rc 0)", rc == 0, str(all_errs[:3]))
synlib.edit_json(d, "gap_asks.json", lambda doc: doc["items"][0].__setitem__("priority", "P0"))
rc, all_errs, _ = synlib.validate(d)
check("G a hand-edited ledger with a clinical priority field → schema ERROR",
      rc == 1 and any(e.startswith("gap_asks.json: schema violation") for e in all_errs), str(all_errs[:3]))

# ---- S upload reconciliation 替换 ---------------------------------------------------------------------
LAB = synlib.SIDE_LAB


def supersede(d, target="f003"):
    synlib.edit_json(d, "source_inventory.json", lambda doc: next(
        r for r in doc["files"] if r["file_id"] == "f002").__setitem__("superseded_by", target))


errs, _ = synlib.gate("gate_source_inventory", synlib.make(tmp / "s_ok", supersede))
check("S superseded_by naming another inventory row → OK (old sidecar stays in place)", errs == [], str(errs[:3]))
errs, _ = synlib.gate("gate_source_inventory", synlib.make(tmp / "s_bad", lambda d: supersede(d, "f099")))
check("S superseded_by naming no row → ERROR", any("superseded_by 'f099'" in e for e in errs), str(errs[:3]))


def move_to_superseded(d):
    old = d / LAB
    dst = d / "_superseded_20300121T000000" / LAB
    dst.parent.mkdir(parents=True)
    shutil.move(str(old), str(dst))


rc, all_errs, _ = synlib.validate(synlib.make(tmp / "s_move", move_to_superseded))
check("S moving the replaced sidecar out of its bucket (the old wording) breaks anchors → gate FAIL",
      rc == 1 and any("not found" in e for e in all_errs), str(all_errs[:3]))

# ---- R restore without re-synthesis ------------------------------------------------------------------
NEW = "07_检验/肿瘤标志物/2030-01-18_肿瘤标志物_示例医院.md"


def restore_only(d):
    # a quarantined, later-dated report moved back into its clinical bucket (段E restore) — and nothing else
    src = (d / LAB).read_text(encoding="utf-8").replace("FILE_ID: s003", "FILE_ID: s007", 1)
    (d / NEW).write_text(src, encoding="utf-8")


errs, _ = synlib.gate("gate_source_freshness", synlib.make(tmp / "r_bad", restore_only))
check("R restore that skips the re-synthesis (§12) → recency ERROR (readiness still names the older latest date)",
      any("latest_source_date" in e for e in errs), str(errs[:3]))
errs, _ = synlib.gate("gate_source_freshness", synlib.make(tmp / "r_ok", lambda d: (restore_only(d), synlib.edit_json(
    d, "readiness.json", lambda doc: doc.update({"latest_source_date": "2030-01-18", "days_since_latest": 2})))))
check("R …with readiness re-synthesized (§12 → §6.2) the recency gate passes", errs == [], str(errs[:3]))

# ---- C conversation events in the current timeline shape --------------------------------------------
LEGACY_CONV = {"event_id": "E-020", "date": "2030-01-19", "date_precision": "day", "category": "symptom_report",
               "title": "家属对话：近两天食欲差", "detail": None, "institution": None,
               "provenance_layer": "caregiver_reported", "verification_status": "unverified",
               "supersedes_event_id": None, "source_refs": ["conversation:2030-01-19T10:00:00Z"],
               "speaker_role": "caregiver", "reported_at": "2030-01-19T10:00:00Z"}
doc = synlib.fixture_doc("timeline.json")
doc["events"].append(dict(LEGACY_CONV))
errs = synlib.schema_errors("timeline.schema.json", doc)
check("C a legacy/段C conversation event copied verbatim (extra keys, no conflict_group / acute_finding_id) → rejected",
      any("conflict_group" in e for e in errs) and any("speaker_role" in e for e in errs), str(errs[:3]))
norm = {k: v for k, v in LEGACY_CONV.items() if k not in ("speaker_role", "reported_at")}
norm.update({"detail": "陈述者：照护者", "conflict_group": None, "acute_finding_id": None})
doc = synlib.fixture_doc("timeline.json")
doc["events"].append(norm)
check("C normalized (speaker in detail, conflict_group / acute_finding_id null) → accepted",
      synlib.schema_errors("timeline.schema.json", doc) == [], str(synlib.schema_errors("timeline.schema.json", doc)[:3]))

# ---- L legacy recency: a Phase-2-only pass writes the recency block; the legacy branch reads it -----------
import source_freshness as sf


def legacy_recency(latest, days, as_of="2030-02-20", warn=True):
    def fn(d):
        synlib.downgrade_to_legacy(d)
        def up(doc):
            doc.update({"latest_source_date": latest, "days_since_latest": days, "as_of_run_date": as_of,
                        "generated_at": "2030-02-19T20:00:00Z"})
            if warn:
                doc["warnings"] = [sf.stale_warning(latest, days)]
        synlib.edit_json(d, "readiness.json", up)
    return fn


errs, warns = synlib.gate("gate_source_freshness", synlib.make(tmp / "l_ok", legacy_recency("2030-01-15", 36)))
check("L legacy archive with a correct recency block (as_of_run_date, stale sentence) → no recency WARN",
      errs == [] and not any("source_freshness" in w for w in warns), str(errs + warns))
errs, warns = synlib.gate("gate_source_freshness", synlib.make(tmp / "l_bad", legacy_recency("2030-01-12", 39)))
check("L legacy archive whose recency block disagrees with the sidecars → WARN naming both",
      errs == [] and any("readiness says '2030-01-12'" in w for w in warns), str(errs + warns))
errs, warns = synlib.gate("gate_source_freshness", synlib.make(tmp / "l_nowarn", legacy_recency("2030-01-15", 36, warn=False)))
check("L legacy archive, stale, block present but no stale sentence → WARN",
      any("lacks the stale-source sentence" in w for w in warns), str(errs + warns))

# ---- N the legacy patient_summary note names only the anchors that are really missing ------------------
def ps_anchors(d):
    synlib.downgrade_to_legacy(d)
    synlib.edit_json(d, "patient_summary.json", lambda doc: doc["demographics"].update(
        {"age_as_of": "2030-01-10", "age_observations": []}))


rc, _, warns = synlib.validate(synlib.make(tmp / "n_ps", ps_anchors))
note = next((w for w in warns if w.startswith("legacy_schema: patient_summary.json")), "")
check("N legacy note lists the missing anchors but not the ones the pass already wrote",
      "birth_year" in note and "age_as_of" not in note, note)

print(f"organize-round2-flows: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
