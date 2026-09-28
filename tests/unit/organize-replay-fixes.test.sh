#!/usr/bin/env bash
# Validator guards added after the LLM replays of Phase 2 (CHANGELOG [Unreleased] 回放修复, synthetic only):
#   C1  `## 不确定字段` layout vocabulary (+ shadow_stain_fold); kind legibility only for layout none
#   C2  field_class vocabulary (+ diagnosis_text / regimen_connector / cycle_number); candidates only
#       for drug_name / ihc_marker / ln_station, each from its own lexicon
#   C3  a `high` candidate needs a COMPLETE reading at distance 0 (a partial `10R[?]` cannot) and
#       every other reading within one edit
#   C10 one line numbering: a sidecar of this contract holds no form feed / splitlines-only break
#   D1  run_mode legacy_upgrade re-transcribes everything (scoped like full); a Phase-2-only
#       rewrite of a legacy archive keeps its versions and stays a legacy WARN
#   D8  a PS statement that cites only the prior-archive digest is provenance_layer prior_archive
#   D9  digest marks agree (source_kind ↔ 既往档案摘录 sub-bucket ↔ SOURCE header); header-less
#       digest = legacy WARN
#   B3/B7 profile.latest_status.status_basis = the ongoing episode's; as_of null only for the
#       undated self-report form
#   D1  partial-upgrade trap: a v1 ledger with no full / legacy_upgrade run over header-less
#       sidecars (legacy archive: WARN; current archive with NO sidecar of this contract: ERROR)
#   anchor gap: a review flag of category anchor_coverage_gap is kind other / severity red
#   D8/C6 the full validator accepts a digest PS item as prior_archive (profile = summary) and
#       per-channel current_source_values
# Each negative mutates ONE thing of the clean synthetic archive; the clean copy is the control.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib

tmp = Path(sys.argv[2])
passed = failed = 0
n = 0
OP, CT, DG = synlib.SIDE_OUTPATIENT, synlib.SIDE_CT, synlib.SIDE_DIGEST


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def mk(mutate=None):
    global n
    n += 1
    return synlib.make(tmp / f"r{n}", mutate)


def run(gate, mutate=None):
    return synlib.gate(gate, mk(mutate))


def op_text(*pairs):
    def fn(d):
        def edit(t):
            for old, new in pairs:
                assert old in t, old
                t = t.replace(old, new, 1)
            return t
        synlib.edit_text(d, OP, edit)
    return fn


def flag0(fn):
    return lambda d: synlib.edit_json(d, "readiness.json", lambda doc: fn(doc["review_flags"][0]))


lex = tmp / "lexicons"
lex.mkdir()
(lex / "ihc_markers.txt").write_text("CK19\nCK20\nCD20\n", encoding="utf-8")
(lex / "ln_stations.txt").write_text("10R\n10Ri\n10L\n10Rs\n", encoding="utf-8")
(lex / "oncology_drugs.txt").write_text("示例药A\n示例药B\n", encoding="utf-8")
os.environ["CB_ORGANIZE_LEXICON_DIR"] = str(lex)


def entry(field_class="other", reads=("晚", "晚"), cands=None):
    """Rewrite U-001 of the outpatient sidecar: its class, the two channel readings, candidates."""
    pairs = [("  field_class: stage", f"  field_class: {field_class}"),
             ('text: "晚", confidence: 0.41', f'text: {json.dumps(reads[0], ensure_ascii=False)}, confidence: 0.41'),
             ('{channel: text_layer, text: "晚"', '{channel: text_layer, text: ' + json.dumps(reads[1], ensure_ascii=False))]
    if cands:
        pairs.append(("  candidates: []", "  candidates:\n" + "".join(f"    - {c}\n" for c in cands).rstrip("\n")))
    return op_text(*pairs)


G = "gate_review_flag_semantics"
sys.path.insert(0, sys.argv[1] + "/skills/cancer-buddy-organize/scripts")
import lexicon_candidates as lc


def mech(field_class, reads):
    """The mechanical candidate list (phase1 §5 rules 1-5, scripts/lexicon_candidates.py) as flow items."""
    return ["{text: %s, lexicon: %s, confidence: %s}" % (json.dumps(c["text"], ensure_ascii=False), c["lexicon"],
                                                         c["confidence"])
            for c in lc.for_field_class(field_class, list(reads), lex)]

# ---- positive control
errs, _ = run(G)
check("clean archive: review-flag semantics pass", errs == [], str(errs))

# ---- C1 layout vocabulary + legibility ⇔ layout none
errs, _ = run(G, op_text(("  layout: none", "  layout: shadow_stain_fold")))
check("C1 layout shadow_stain_fold accepted by the entry vocabulary",
      not any("layout 'shadow_stain_fold' is not one of" in e for e in errs), str(errs))
check("C1 …but the legibility flag citing it → ERROR (a layout anomaly is kind artifact)",
      any("kind legibility but its uncertain entry U-001 records layout shadow_stain_fold" in e for e in errs), str(errs))
errs, _ = run(G, lambda d: (op_text(("  layout: none", "  layout: shadow_stain_fold"))(d),
                            flag0(lambda f: f.__setitem__("kind", "artifact"))(d)))
check("C1 the same entry under a kind artifact flag passes", errs == [], str(errs))
errs, _ = run(G, lambda d: (op_text(("  layout: none", "  layout: strikethrough"))(d),
                            flag0(lambda f: f.__setitem__("kind", "artifact"))(d)))
check("C1 strikethrough under artifact passes", errs == [], str(errs))
errs, _ = run(G, op_text(("  layout: none", "  layout: shadow")))
check("C1 layout outside the vocabulary → ERROR", any("layout 'shadow' is not one of" in e for e in errs), str(errs))
errs, _ = run(G, op_text(("  layout: none", "  layout: none (page curvature)")))
check("C1 layout with free text appended → ERROR", any("is not one of none | strikethrough" in e for e in errs), str(errs))
errs, _ = run(G, op_text(("layout_intent: null", "layout_intent: erased")))
check("C1 layout_intent outside null|deleted|amended → ERROR", any("layout_intent 'erased'" in e for e in errs), str(errs))

# ---- C2 field_class vocabulary + which classes get candidates
for fc in ("diagnosis_text", "regimen_connector", "cycle_number", "date", "other"):
    errs, _ = run(G, entry(field_class=fc))
    check(f"C2 field_class {fc} (no candidates) passes", errs == [], str(errs))
errs, _ = run(G, entry(field_class="regimen connector"))
check("C2 field_class outside the vocabulary → ERROR", any("field_class 'regimen connector' is not one of" in e for e in errs), str(errs))
errs, _ = run(G, entry(field_class="diagnosis_text", reads=("CK2O", "CK20"),
                       cands=['{text: "CK20", lexicon: ihc_markers, confidence: high}']))
check("C2 candidates on a diagnosis_text entry → ERROR (only lexicon classes get candidates)",
      any("field_class diagnosis_text gets no candidates" in e for e in errs), str(errs))
errs, _ = run(G, entry(field_class="other", reads=("CK2O", "CK20"),
                       cands=['{text: "CK20", lexicon: ihc_markers, confidence: high}']))
check("C2 candidates on an other entry → ERROR", any("field_class other gets no candidates" in e for e in errs), str(errs))
errs, _ = run(G, entry(field_class="ihc_marker", reads=("CK2O", "CK20"), cands=mech("ihc_marker", ("CK2O", "CK20"))))
check("C2 ihc_marker candidates (the mechanical list from ihc_markers) pass", errs == [], str(errs))
errs, _ = run(G, entry(field_class="drug_name", reads=("CK2O", "CK20"),
                       cands=['{text: "CK20", lexicon: ihc_markers, confidence: high}']))
check("C2 drug_name candidate drawn from the ihc_markers lexicon → ERROR",
      any("field_class drug_name draws from oncology_drugs" in e for e in errs), str(errs))

# ---- C3 a `high` candidate rests on a complete reading at distance 0
errs, _ = run(G, entry(field_class="ln_station", reads=("10R[?]", "10R?"),
                       cands=['{text: "10R", lexicon: ln_stations, confidence: high}']))
check("C3 high candidate whose readings are both partial (10R[?] / 10R?) → ERROR",
      any("candidate '10R' is marked high but the reading(s)" in e and "resolved only part" in e for e in errs), str(errs))
errs, _ = run(G, entry(field_class="ln_station", reads=("10R[?]", "10R?"), cands=mech("ln_station", ("10R[?]", "10R?"))))
check("C3 the same partial readings with their (low) mechanical candidates pass", errs == [], str(errs))
errs, _ = run(G, entry(field_class="ln_station", reads=("10Ri", "10Rs"), cands=mech("ln_station", ("10Ri", "10Rs"))))
check("C3 high candidate equal to a complete reading, other reading 1 edit away, passes",
      errs == [] and "confidence: high" in mech("ln_station", ("10Ri", "10Rs"))[0], str(errs))
errs, _ = run(G, entry(field_class="ln_station", reads=("10Ri", "10R?"),
                       cands=['{text: "10Ri", lexicon: ln_stations, confidence: high}',
                              '{text: "10R", lexicon: ln_stations, confidence: low}',
                              '{text: "10Rs", lexicon: ln_stations, confidence: low}']))
check("C3 rule 5: a partial reading (10R?) caps every candidate at medium — high → ERROR",
      any("are not the mechanical list" in e and "10Ri=medium" in e for e in errs), str(errs))
errs, _ = run(G, entry(field_class="ln_station", reads=("10Ri", "10L?"),
                       cands=['{text: "10Ri", lexicon: ln_stations, confidence: high}']))
check("C3 high candidate with another reading 2 edits away → ERROR",
      any("is more than one edit away" in e for e in errs), str(errs))
errs, _ = run(G, entry(field_class="ln_station", reads=("No.10Ri组", "10Ri"), cands=mech("ln_station", ("No.10Ri组", "10Ri"))))
check("C3 rule-1 normalisation (No. / 组 stripped, case folded) counts as distance 0",
      errs == [] and mech("ln_station", ("No.10Ri组", "10Ri"))[0].startswith('{text: "10Ri"') and "high" in mech("ln_station", ("No.10Ri组", "10Ri"))[0], str(errs))
errs, _ = run(G, entry(field_class="ln_station", reads=("10Ri", "10Ri"),
                       cands=['{text: "10Ri", lexicon: ln_stations, confidence: 0.9}']))
check("C3 numeric candidate confidence → ERROR", any("confidence 0.9 must be high | medium | low" in e for e in errs), str(errs))
errs, _ = run(G, lambda d: (entry(field_class="ln_station", reads=("10Ri", "10Ri"),
                                  cands=mech("ln_station", ("10Ri",)))(d),
                            synlib.edit_text(d, OP, lambda t: t.replace('{channel: text_layer, text: "10Ri"',
                                                                        '{channel: text_layer, text: null', 1))))
check("C3 a channel that read nothing (text null) is not a reading", errs == [], str(errs))

# ---- anchor gap = kind other / severity red (phase2 §6.1, anchor-contract.md §5)
def anchor_gap(severity, kind="other"):
    return lambda d: synlib.edit_json(d, "readiness.json", lambda doc: doc["review_flags"][2].update(
        {"category": "anchor_coverage_gap", "severity": severity, "kind": kind}))


errs, _ = run(G, anchor_gap("red"))
check("anchor_coverage_gap flag other / red passes", errs == [], str(errs))
errs, _ = run(G, anchor_gap("yellow"))
check("anchor_coverage_gap flag with severity yellow → ERROR",
      any("RF-003 category anchor_coverage_gap has severity 'yellow'" in e for e in errs), str(errs))
errs, _ = run(G, anchor_gap("red", kind="completeness"))
check("anchor_coverage_gap flag with kind completeness → ERROR",
      any("RF-003 category anchor_coverage_gap has kind 'completeness'" in e for e in errs), str(errs))
errs, warns = synlib.gate(G, mk(anchor_gap("yellow")), generation="legacy")
check("legacy archive: a yellow anchor gap is a WARN, not an ERROR",
      errs == [] and any("anchor_coverage_gap has severity 'yellow'" in w for w in warns), str(errs + warns))

# ---- C10 one line numbering (form feeds)
LB = "gate_sidecar_line_breaks"
errs, warns = run(LB)
check("C10 clean archive: no line-break findings", errs == [] and not any("line_breaks" in w for w in warns), str(errs + warns))
errs, _ = run(LB, lambda d: synlib.edit_text(d, CT, lambda t: t.replace("\n肝实质未见", "\f肝实质未见", 1)))
check("C10 a form feed in a sidecar of this contract → ERROR", any(CT in e and "1 form feed" in e for e in errs), str(errs))
errs, _ = run(LB, lambda d: (d / CT).write_bytes((d / CT).read_bytes().replace("\n肝实质".encode(), "\r肝实质".encode(), 1)))
check("C10 a lone CR → ERROR", any(CT in e for e in errs), str(errs))
errs, _ = run(LB, lambda d: (d / CT).write_bytes((d / CT).read_bytes().replace(b"\n", b"\r\n")))
check("C10 CRLF line ends count the same for both tools → no ERROR", errs == [], str(errs))
d = mk(lambda d: synlib.edit_text(d, CT, lambda t: t.replace("\n肝实质未见", "\f肝实质未见", 1)))
rc, errs, _ = synlib.validate(d)
check("C10 the full validator fails on it", rc == 1 and any(e.startswith("line_breaks:") for e in errs), str(errs[:3]))
legacy = synlib.make(tmp / "c10_legacy", lambda d: (synlib.downgrade_to_legacy(d),
                     synlib.edit_text(d, CT, lambda t: t.replace("\n肝实质未见", "\f肝实质未见", 1))))
errs, warns = synlib.gate(LB, legacy)
check("C10 legacy archive: a form feed is one WARN, never an ERROR",
      errs == [] and sum("legacy archive: line_breaks" in w for w in warns) == 1, str(errs + warns))

# ---- D1 legacy_upgrade scopes every sidecar; a Phase-2-only rewrite of a legacy archive stays WARN
LEG = "05_影像/CT/2029-12-01_胸部CT_示例医院.md"


def carried(run_mode):
    def fn(d):
        (d / LEG).write_text("SOURCE: raw/s009.jpg\nFILE_ID: f009\nREAD_MODE: deterministic_ocr\n\n"
                             "# 旧版转写（合成夹具）\n\n腹部超声：肝左叶囊肿。\n\n## PII\n\n- 无\n", encoding="utf-8")
        def inv(doc):
            row = json.loads(json.dumps(next(r for r in doc["files"] if r["sidecar_path"] == CT)))
            row.update({"file_id": "f009", "source_id": "s009", "original_path": "s009.jpg", "raw_path": "raw/s009.jpg",
                        "bucket_path": LEG, "sidecar_path": LEG, "sha256": "cd" * 32, "size_bytes": 10,
                        "page_label": None, "second_read_channel": "none", "independent_reread": False,
                        "high_risk_review_status": "needs_human_review", "read_mode": "deterministic_ocr"})
            doc["files"].append(row)
        synlib.edit_json(d, "source_inventory.json", inv)
        synlib.edit_json(d, "update_log.json", lambda doc: doc["entries"][0].__setitem__("run_mode", run_mode))
    return fn


errs, warns = run("gate_sidecar_headers", carried("incremental"))
check("D1 incremental run: the untouched old sidecar is carried over (WARN, no ERROR)",
      not any(LEG in e for e in errs) and any("carried-over sidecar(s)" in w and "legacy_upgrade" in w for w in warns),
      str(errs + warns))
errs, _ = run("gate_sidecar_headers", carried("legacy_upgrade"))
check("D1 run_mode legacy_upgrade re-transcribes everything → the old header ERRORs",
      any(LEG in e and "EXTRACTOR missing" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", carried("full"))
check("D1 run_mode full still scopes every sidecar", any(LEG in e for e in errs), str(errs))


def phase2_only_rewrite(d):
    """Legacy archive + a Phase 2 worker that rewrote it WITHOUT the upgrade, as phase2 §4.0/§8 say:
    versions kept at the legacy numbers, the legacy ledger left as it is (no v1 entry), no
    organize_meta.json — it writes no current-contract marker. It DOES write acute_findings.json
    (a safety surface on every pass, not a marker), with timeline_event_id null."""
    synlib.downgrade_to_legacy(d)
    synlib.write_legacy_acute(d)


def v1_ledger(d):
    """…the same rewrite, but appending a current-shape ledger entry (workers[]) — a marker of this
    contract, which a Phase-2-only run on a legacy archive must not write (phase2 §8)."""
    synlib.save(d, "update_log.json", {"schema_version": "1", "entries": [
        {"at": "2030-01-20T09:00:00Z", "run_mode": "incremental",
         "workers": [{"worker_id": "p2-1", "phase": "phase2", "slice_id": None, "status": "done", "files": []}],
         "inputs": [], "added": [], "removed": [], "degradations": [], "note": "phase-2-only rewrite"}]})


d = synlib.make(tmp / "p2only", phase2_only_rewrite)
rc, errs, warns = synlib.validate(d)
check("D2 Phase-2-only rewrite keeping legacy versions and ledger → rc 0 (legacy WARN path)", rc == 0, str(errs[:3]))
check("D2 …the legacy WARN names legacy_upgrade as the way to upgrade",
      any(w.startswith("archive_generation: legacy archive") and "legacy_upgrade" in w for w in warns), str(warns[:2]))
d = synlib.make(tmp / "p2only_v1", lambda d: (phase2_only_rewrite(d), v1_ledger(d)))
rc, errs, _ = synlib.validate(d)
check("D2 the same rewrite appending a v1 ledger entry with workers[] → current marker → mixed-version ERROR",
      rc == 1 and any(e.startswith("mixed-version archive:") and "legacy_upgrade" in e for e in errs), str(errs[:3]))
d = synlib.make(tmp / "partial", lambda d: (synlib.downgrade_to_legacy(d), synlib.save(
    d, "readiness.json", synlib.fixture_doc("readiness.json"))))
rc, errs, _ = synlib.validate(d)
check("D1 partial upgrade (readiness 2.1, the rest legacy) → mixed-version ERROR naming legacy_upgrade",
      rc == 1 and any(e.startswith("mixed-version archive: labs.json") and "legacy_upgrade" in e for e in errs), str(errs[:3]))

# ---- D1 partial-upgrade trap: a v1 ledger with no full / legacy_upgrade run over header-less sidecars
# (SKILL.md Step 1 would take the ledger as an upgrade and never run legacy_upgrade)
UL = "gate_update_log"
TRAP = "records no full / legacy_upgrade run"


def rewrite_with(mode=None, extractor_on=None):
    def fn(d):
        phase2_only_rewrite(d)
        v1_ledger(d)
        if mode:
            synlib.edit_json(d, "update_log.json", lambda doc: doc["entries"][0].__setitem__("run_mode", mode))
        if extractor_on:
            synlib.edit_text(d, extractor_on, lambda t: re.sub(r"^(FILE_ID: .*\n)", r"\1EXTRACTOR: p2-1\n", t, count=1, flags=re.M))
    return fn


# a v1 ledger with workers[] is a current-contract marker (generation_markers), so the trap — no sidecar
# re-transcribed under this contract — is an ERROR: the ledger's claim cannot stand
errs, warns = synlib.gate(UL, mk(rewrite_with()))
check("D1 v1 ledger with only an incremental entry + all sidecars header-less → one ERROR naming legacy_upgrade",
      sum(TRAP in e for e in errs) == 1 and any(TRAP in e and "run run_mode legacy_upgrade" in e for e in errs),
      str(errs + warns))
errs, warns = synlib.gate(UL, mk(rewrite_with()), generation="legacy")
check("D1 …on an archive judged legacy the same trap is one WARN",
      errs == [] and sum(TRAP in w for w in warns) == 1, str(errs + warns))
errs, warns = synlib.gate(UL, mk(rewrite_with(mode="legacy_upgrade")))
check("D1 the same ledger with a legacy_upgrade entry → no partial-upgrade message",
      not any(TRAP in m for m in errs + warns), str(errs + warns))
errs, warns = synlib.gate(UL, mk(rewrite_with(mode="full")))
check("D1 …or with a full entry → no partial-upgrade message", not any(TRAP in m for m in errs + warns), str(errs + warns))
errs, warns = synlib.gate(UL, mk(rewrite_with(extractor_on=CT)), generation="legacy")
check("D1 legacy archive: one sidecar re-transcribed, the rest header-less → still the WARN",
      errs == [] and any(TRAP in w and "5/6" in w for w in warns), str(errs + warns))


def all_bare_current(d):
    for rel in (OP, CT, synlib.SIDE_LAB, DG, synlib.SIDE_SELF, synlib.SIDE_ORDER):
        synlib.edit_text(d, rel, lambda t: re.sub(r"^EXTRACTOR: .*\n", "", t, count=1, flags=re.M))
    synlib.edit_json(d, "update_log.json", lambda doc: doc["entries"][0].__setitem__("run_mode", "incremental"))


errs, warns = synlib.gate(UL, mk(all_bare_current))
check("D1 current-contract archive, no full / legacy_upgrade run, NO sidecar written under this contract → ERROR",
      any(TRAP in e and "6/6" in e for e in errs), str(errs + warns))
errs, warns = synlib.gate(UL, mk(lambda d: synlib.edit_json(d, "update_log.json", lambda doc: doc["entries"][0].__setitem__("run_mode", "incremental"))))
check("D1 current archive, incremental-only ledger, every sidecar headed by this contract → no message",
      not any(TRAP in m for m in errs + warns), str(errs + warns))
errs, warns = synlib.gate(UL, mk(carried("incremental")))
check("D1 current archive with ONE carried-over header-less sidecar → no partial-upgrade message (the carried-over WARN covers it)",
      not any(TRAP in m for m in errs + warns), str(errs + warns))

# ---- D8 PS statement from the digest = prior_archive
PA = "gate_prior_archive_usage"


def ps_item(fn):
    def mut(d):
        for name in ("patient_summary.json", "profile.json"):
            synlib.edit_json(d, name, lambda doc: fn(doc["demographics"]["performance_status_verbatim"]))
    return mut


dg_ps = {"text": "ECOG 2", "as_of": None, "scale_label": "ECOG", "source_ref": DG + "#L15"}
errs, _ = run(PA, ps_item(lambda l: l.append(dict(dg_ps))))
check("D8 PS item citing only the digest without provenance_layer → ERROR",
      any("performance_status_verbatim[1] cites only the prior-archive digest" in e for e in errs), str(errs))
errs, _ = run(PA, ps_item(lambda l: l.append(dict(dg_ps, provenance_layer="prior_archive"))))
check("D8 the same item as provenance_layer prior_archive passes", errs == [], str(errs))
errs, _ = run(PA, ps_item(lambda l: l.append(dict(dg_ps, provenance_layer="source_reported"))))
check("D8 the same item labelled source_reported → ERROR",
      any("sourced only from the prior-archive digest" in e for e in errs), str(errs))
errs, _ = run(PA, ps_item(lambda l: l[0].__setitem__("provenance_layer", "prior_archive")))
check("D8 a current PS item labelled prior_archive (cites no digest) → ERROR",
      any("cites no prior_archive_digest source" in e for e in errs), str(errs))
errs, _ = run("gate_profile_demographics", ps_item(lambda l: l[0].__setitem__("provenance_layer", "archive")))
check("D8 PS item provenance_layer outside the enum → ERROR", any("provenance_layer must be one of" in e for e in errs), str(errs))

# ---- D9 digest marks agree
OTHER = "03_病程与叙事文书/其他/2029-06-01_既往档案摘录.md"


def move_digest(d, new_rel=OTHER):
    (d / new_rel).parent.mkdir(parents=True, exist_ok=True)
    (d / DG).rename(d / new_rel)
    (d / DG).parent.rmdir()
    for name in ("timeline.json", "treatment_lines.json", "molecular.json", "source_inventory.json"):
        p = d / name
        p.write_text(p.read_text(encoding="utf-8").replace(DG, new_rel), encoding="utf-8")


errs, warns = run(PA)
check("D9 clean archive: digest marks agree", errs == [] and not any("prior_archive" in w for w in warns), str(errs + warns))
errs, _ = run(PA, move_digest)
check("D9 source_kind digest row filed outside 既往档案摘录 → ERROR",
      any(OTHER in e and "filed outside 03_病程与叙事文书/既往档案摘录" in e for e in errs), str(errs))
errs, _ = run(PA, lambda d: synlib.edit_json(d, "source_inventory.json", lambda doc: next(
    r for r in doc["files"] if r["sidecar_path"] == DG).__setitem__("source_kind", "upload")))
check("D9 a non-digest row in the digest sub-bucket → ERROR",
      any("sits in the prior-archive digest sub-bucket but its source_inventory source_kind is 'upload'" in e for e in errs), str(errs))


def misfiled_header_only(d):
    move_digest(d)
    synlib.edit_json(d, "source_inventory.json", lambda doc: next(
        r for r in doc["files"] if r["sidecar_path"] == OTHER).__setitem__("source_kind", "upload"))


errs, _ = run(PA, misfiled_header_only)
check("D9 SOURCE prior_archive_digest sidecar filed elsewhere without a digest row → ERROR",
      any(OTHER in e and "(SOURCE prior_archive_digest) filed outside" in e for e in errs), str(errs))
errs, warns = synlib.gate(PA, synlib.make_legacy(tmp / "d9_legacy"))
check("D9 legacy archive (digest under 其他 with its SOURCE header) → WARN, not ERROR",
      errs == [] and any("legacy archive: prior_archive:" in w and "(SOURCE prior_archive_digest) filed outside" in w
                         for w in warns), str(errs + warns))
errs, warns = run(PA, lambda d: synlib.edit_text(d, DG, lambda t: t.split("\n\n", 1)[1]))
check("D9 header-less digest in the digest bucket → one legacy-digest WARN (not an ERROR here)",
      errs == [] and sum("carry no pinned header" in w and "legacy_upgrade" in w for w in warns) == 1, str(errs + warns))
errs, _ = run(PA, lambda d: synlib.edit_text(d, DG, lambda t: t.replace("SOURCE: prior_archive_digest", "SOURCE: discharge_summary", 1)))
check("D9 digest whose header SOURCE is another document type → ERROR",
      any("filed as a prior-archive digest but its header SOURCE is 'discharge_summary'" in e for e in errs), str(errs))

# ---- B3/B7 latest_status ↔ the ongoing episode
RL = "gate_record_links"
errs, _ = run(RL)
check("B7 clean archive: latest_status.status_basis = the episode's (clinician_note_current)", errs == [], str(errs))
errs, _ = run(RL, lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["latest_status"].__setitem__(
    "status_basis", "administration_record")))
check("B7 latest_status.status_basis ≠ the ongoing episode's → ERROR",
      any("latest_status.status_basis 'administration_record' ≠ status_basis" in e for e in errs), str(errs))
errs, _ = run(RL, lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["latest_status"].pop("status_basis")))
check("B7 status_basis is optional", errs == [], str(errs))


def undated(latest_basis="patient_reported", drop_basis=False):
    def fn(d):
        # the family statement is the episode's source: its wording is printed in the (undated) note it cites
        synlib.edit_text(d, synlib.SIDE_SELF, lambda t: t.replace("外院检查提示肝转移。", "外院检查提示肝转移。示例方案B现在还在打，每三周一次。", 1))
        self_ref = synlib.load(d, "timeline.json")["events"][1]["source_refs"][0]
        synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].update(
            {"status_basis": "patient_reported", "status_basis_text": "示例方案B现在还在打，每三周一次", "status_as_of": None,
             "status_as_of_precision": "undated_self_report", "provenance_layer": "caregiver_reported",
             "source_refs": doc["episodes"][1]["source_refs"] + [self_ref]}))
        def ls(doc):
            doc["latest_status"].update({"as_of": None, "status_basis": latest_basis})
            if drop_basis:
                doc["latest_status"].pop("status_basis")
            # phase2 §5.7: the summary keeps the family statement's marker (its block stays source_reported)
            doc["summary"]["current_regimen"] = "家属自述：示例方案B"
        synlib.edit_json(d, "profile.json", ls)
        # patient_summary.current_status mirrors the same undated statement (as_of is nullable there)
        synlib.edit_json(d, "patient_summary.json", lambda doc: doc["current_status"].update(
            {"as_of": None, "provenance_layer": "patient_reported"}))
    return fn


errs, _ = run(RL, undated())
check("B3 undated self-report episode + latest_status as_of null + basis patient_reported passes", errs == [], str(errs))
errs, _ = run(RL, undated(drop_basis=True))
check("B3 latest_status as_of null without status_basis → ERROR",
      any("latest_status.as_of is null — only the undated self-report form" in e for e in errs), str(errs))
errs, _ = run(RL, lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["latest_status"].update(
    {"as_of": None, "status_basis": "patient_reported"})))
check("B3 latest_status as_of null while the ongoing episode is dated → ERROR",
      any("latest_status.as_of None ≠ status_as_of" in e for e in errs), str(errs))
d = mk(undated())
rc, errs, _ = synlib.validate(d)
check("B3 the undated self-report archive passes the full validator", rc == 0, str(errs[:3]))

errs, _ = run(RL, lambda d: synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].__setitem__(
    "status_basis", "order_or_indication_only")))
check("B7 latest_status.status_basis clinician_note_current while the episode says order_or_indication_only → ERROR",
      any("latest_status.status_basis 'clinician_note_current' ≠ status_basis of the ongoing episode EP-002 "
          "('order_or_indication_only')" in e for e in errs), str(errs))

# ---- D8 / C6 end to end: both validators accept the optional fields and the profile copy still
# equals patient_summary (validate-profile-schema.sh reads profile.json + readiness.json)
import subprocess
PROFILE_SH = str(synlib.REPO / "scripts" / "validate-profile-schema.sh")


def both(mutate):
    d = mk(mutate)
    rc, errs, _ = synlib.validate(d)
    prof = subprocess.run(["bash", PROFILE_SH, str(d)], capture_output=True, text=True)
    return rc, errs, prof.returncode, prof.stdout + prof.stderr


def digest_ps_line(d):
    # the digest's blank line 15 becomes the PS statement (no other line number moves)
    synlib.edit_text(d, DG, lambda t: t.replace("）\n\n既往整理档案", "）\n既往档案记载体能状态：ECOG 2。\n既往整理档案", 1))


rc, errs, prc, pout = both(lambda d: (digest_ps_line(d), ps_item(lambda l: l.append(dict(dg_ps, provenance_layer="prior_archive")))(d)))
check("D8 digest PS item provenance_layer prior_archive: full validator rc 0 and validate-profile-schema.sh pass",
      rc == 0 and prc == 0, str(errs[:3]) + pout[-300:])
rc, errs, _, _ = both(lambda d: (digest_ps_line(d), synlib.edit_json(d, "profile.json", lambda doc: doc["demographics"][
    "performance_status_verbatim"].append(dict(dg_ps, provenance_layer="prior_archive")))))
check("D8 the item only in profile.json (not patient_summary) → equality ERROR",
      rc == 1 and any("performance_status_verbatim ≠ patient_summary" in e for e in errs), str(errs[:3]))
rc, errs, prc, pout = both(flag0(lambda f: f["current_source_values"][0].__setitem__("channel", "text_layer")))
check("C6 current_source_values[].channel: full validator rc 0 and validate-profile-schema.sh pass",
      rc == 0 and prc == 0, str(errs[:3]) + pout[-300:])
rc, errs, _, _ = both(flag0(lambda f: f["current_source_values"][0].__setitem__("channel", "ocr")))
check("C6 a channel outside the pinned vocabulary → schema ERROR", rc == 1, str(errs[:3]))

print(f"organize-replay-fixes: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
