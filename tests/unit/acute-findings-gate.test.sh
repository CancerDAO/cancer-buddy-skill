#!/usr/bin/env bash
# O-02 acute / incidental findings gate (validate_structured_outputs.gate_acute_findings).
#
# acute_findings.json is always written; every finding ↔ exactly one timeline event
# with category acute_finding; source_ref carries a line anchor whose line holds the
# verbatim text (elisions written as ……); acuity follows the fixed finding_class table
# (references/acute-findings.md §3) — the model never triages. Positive control = the clean synthetic
# archive; each negative mutates one thing. All data synthetic.
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


def run(mutate=None):
    global n
    n += 1
    d = synlib.make(tmp / f"a{n}", mutate)
    return d, synlib.gate("gate_acute_findings", d)


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def af(fn):
    return lambda d: synlib.edit_json(d, "acute_findings.json", lambda doc: fn(doc["findings"][0]))


def tl(fn):
    return lambda d: synlib.edit_json(d, "timeline.json", fn)


# positive control
d, (errs, warns) = run()
check("clean archive: no acute_findings errors", errs == [], str(errs))
rc, all_errs, _ = synlib.validate(d)
check("clean archive passes the whole validator", rc == 0, str(all_errs[:3]))

# presence
d, (errs, _) = run(lambda d: (d / "acute_findings.json").unlink())
check("missing file on a current archive → ERROR", any("acute_findings.json: missing" in e for e in errs))
d, (errs, _) = run(lambda d: synlib.edit_json(d, "acute_findings.json", lambda doc: doc.__setitem__("findings", []))
                   or synlib.edit_json(d, "timeline.json", lambda doc: doc.__setitem__(
                       "events", [e for e in doc["events"] if e["category"] != "acute_finding"])))
check("findings: [] with no acute timeline event passes", errs == [], str(errs))

# timeline binding both ways
d, (errs, _) = run(af(lambda f: f.__setitem__("timeline_event_id", "E-999")))
check("finding → missing timeline event → ERROR", any("has no timeline.json event" in e for e in errs), str(errs))
d, (errs, _) = run(tl(lambda doc: next(e for e in doc["events"] if e["event_id"] == "E-005").__setitem__("category", "imaging")))
check("finding → event not categorised acute_finding → ERROR", any("must have category acute_finding" in e for e in errs), str(errs))


def orphan_event(doc):
    doc["events"].append({"event_id": "E-099", "date": "2030-01-12", "date_precision": "day",
                          "category": "acute_finding", "title": "孤立事件", "detail": None, "institution": None,
                          "provenance_layer": "source_reported", "verification_status": "unverified",
                          "supersedes_event_id": None, "conflict_group": None, "acute_finding_id": "AF-009",
                          "source_refs": [synlib.SIDE_CT + "#L17"]})
d, (errs, _) = run(tl(orphan_event))
check("acute timeline event without a finding → ERROR", any("does not contain" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: synlib.edit_json(d, "acute_findings.json", lambda doc: doc["findings"].append(dict(doc["findings"][0]))))
check("duplicate finding_id → ERROR", any("duplicate finding_id" in e for e in errs), str(errs))

# line anchor + verbatim binding
d, (errs, _) = run(af(lambda f: f.__setitem__("source_ref", synlib.SIDE_CT + "#L999")))
check("line anchor outside the sidecar → ERROR", any("points outside the file" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__("source_ref", synlib.SIDE_CT + "#L16")))
check("anchor on the wrong line (verbatim absent) → ERROR", any("verbatim text not found" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__("verbatim_text", "右侧颈内静脉充盈缺损")))
check("paraphrased verbatim text → ERROR", any("verbatim text not found" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__("verbatim_text", "考虑肺栓塞可能，请结合临床。")))
check("exact substring (no elision) passes", errs == [], str(errs))

# acuity table (references/acute-findings.md §3)
d, (errs, _) = run(af(lambda f: f.__setitem__("acuity", "incidental")))
check("class_default thrombus not urgent → ERROR", any("means urgent" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.update({"acuity": "urgent", "acuity_basis": "source_wording_escalation",
                                          "acuity_basis_text": "请结合临床"})))
check("escalation that does not raise the default → ERROR", any("must raise" in e for e in errs), str(errs))
# The source wording behind an adjustment must be ON THE CITED LINE(S) (acute-findings.md §4;
# §4/§4.1): it is quoted from the finding's source_ref range — or acuity_basis_ref, another line of the
# same report — and holds one of that adjustment's pinned words. The positives write the wording into
# the CT impression line (the anchored one: verbatim_text keeps its segments, every other anchor its
# line number); the negatives quote wording the report does not contain, wording from another line,
# wording without a pinned word, or only an ellipsis.
IMP_END = "请结合临床。"


def ct_imp_says(extra):
    return lambda d: synlib.edit_text(d, synlib.SIDE_CT, lambda t: t.replace(IMP_END, "请结合临床" + extra + "。", 1))


def ct_find_says(extra):  # the findings line — NOT the line AF-001 cites
    return lambda d: synlib.edit_text(d, synlib.SIDE_CT, lambda t: t.replace("其余肺动脉显影良好。", "其余肺动脉显影良好" + extra + "。", 1))


def ct_line(d, needle):
    for i, line in enumerate((d / synlib.SIDE_CT).read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return f"{synlib.SIDE_CT}#L{i}"
    raise KeyError(needle)


d, (errs, _) = run(lambda d: (ct_imp_says("，呈骑跨状")(d), af(lambda f: f.update(
    {"acuity": "emergent", "acuity_basis": "source_wording_escalation", "acuity_basis_text": "骑跨"}))(d)))
check("escalation urgent → emergent quoting the cited line passes", errs == [], str(errs))
d, (errs, _) = run(af(lambda f: f.update({"acuity": "emergent", "acuity_basis": "source_wording_escalation",
                                          "acuity_basis_text": "骑跨"})))
check("escalation wording absent from the report → ERROR",
      any("acuity_basis source_wording_escalation" in e and "not found" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__("finding_class", "perforation_free_air")))
check("class change without acuity change → ERROR (perforation defaults emergent)", any("means emergent" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: (ct_imp_says("，与前片比较无变化，考虑陈旧性")(d), af(lambda f: f.update(
    {"acuity": "incidental", "acuity_basis": "source_wording_chronic",
     "acuity_basis_text": "与前片比较无变化……陈旧性"}))(d)))
check("chronic + unchanged wording quoted from the cited line (with elision) → incidental passes", errs == [], str(errs))
# v1-shaped failure: a pulmonary-embolism finding demoted to incidental on wording the
# report never used — it would drop out of every urgent path downstream.
d, (errs, _) = run(af(lambda f: f.update({"acuity": "incidental", "acuity_basis": "source_wording_chronic",
                                          "acuity_basis_text": "陈旧性，较前无变化"})))
check("invented chronic wording → ERROR (no demotion without the report's words)",
      any("acuity_basis source_wording_chronic" in e and "not found" in e for e in errs), str(errs))
# I-01 (acute-findings.md §4.1): 「较前无显著变化」 is printed on the cited line but is NOT chronic wording
d, (errs, _) = run(lambda d: (ct_imp_says("，较前无显著变化")(d), af(lambda f: f.update(
    {"acuity": "incidental", "acuity_basis": "source_wording_chronic", "acuity_basis_text": "较前无显著变化"}))(d)))
check("「较前无显著变化」 alone quoted as chronic wording → ERROR (no pinned chronic word)",
      any("holds none of the pinned words" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.update({"acuity": "incidental", "acuity_basis": "source_wording_chronic",
                                          "acuity_basis_text": "肺动脉"})))
check("an unrelated quoted word from the cited line as chronic wording → ERROR",
      any("holds none of the pinned words" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: (ct_imp_says("，考虑陈旧性")(d), af(lambda f: f.update(
    {"acuity": "incidental", "acuity_basis": "source_wording_chronic", "acuity_basis_text": "陈旧性"}))(d)))
check("thrombus demoted on 陈旧 without an unchanged comparison → ERROR (§3: 陈旧/慢性 AND 较前无变化)",
      any("old AND unchanged" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: (ct_imp_says("，陈旧性，与前片比较无变化")(d), af(lambda f: f.update(
    {"finding_class": "obstruction", "acuity": "incidental", "acuity_basis": "source_wording_chronic",
     "acuity_basis_text": "陈旧性，与前片比较无变化"}))(d)))
check("chronic demotion of a class whose §3 row has none (obstruction) → ERROR",
      any("has no chronic adjustment" in e for e in errs), str(errs))
# wording on ANOTHER line of the report: bound only through acuity_basis_ref
d, (errs, _) = run(lambda d: (ct_find_says("，与前片比较无变化，考虑陈旧性")(d), af(lambda f: f.update(
    {"acuity": "incidental", "acuity_basis": "source_wording_chronic",
     "acuity_basis_text": "与前片比较无变化……陈旧性"}))(d)))
check("chronic wording on another line of the report, no acuity_basis_ref → ERROR",
      any("acuity_basis source_wording_chronic" in e and "not found" in e for e in errs), str(errs))


def demote_via_ref(d):
    ct_find_says("，与前片比较无变化，考虑陈旧性")(d)
    ref = ct_line(d, "其余肺动脉显影良好")
    af(lambda f: f.update({"acuity": "incidental", "acuity_basis": "source_wording_chronic",
                           "acuity_basis_text": "与前片比较无变化……陈旧性", "acuity_basis_ref": ref}))(d)


d, (errs, _) = run(demote_via_ref)
check("…the same wording named by acuity_basis_ref (same report) passes", errs == [], str(errs))
d, (errs, _) = run(lambda d: (demote_via_ref(d), af(lambda f: f.__setitem__(
    "acuity_basis_ref", synlib.SIDE_OUTPATIENT + "#L15"))(d)))
check("acuity_basis_ref into another sidecar → ERROR", any("is not in the report" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: (ct_imp_says("（危急值）")(d), af(lambda f: f.update(
    {"acuity": "emergent", "acuity_basis": "source_critical_flag", "acuity_basis_text": "危急值"}))(d)))
check("critical flag printed on the cited line → emergent passes", errs == [], str(errs))
d, (errs, _) = run(af(lambda f: f.update({"acuity": "emergent", "acuity_basis": "source_critical_flag",
                                          "acuity_basis_text": "危急值"})))
check("critical flag the report does not print → ERROR",
      any("source_critical_flag" in e and "not found" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.update({"finding_class": "clinical_correlation_requested", "acuity": "incidental"})))
check("clinical_correlation_requested defaults incidental", errs == [], str(errs))

# an ellipsis-only quote binds nothing (every "segment is in the source" check passes vacuously)
for label, mut in (
        ("verbatim_text '……'", af(lambda f: f.__setitem__("verbatim_text", "……"))),
        ("verbatim_text '...'", af(lambda f: f.__setitem__("verbatim_text", "..."))),
        ("acuity_basis_text '……' demoting the embolism", af(lambda f: f.update(
            {"acuity": "incidental", "acuity_basis": "source_wording_chronic", "acuity_basis_text": "……"}))),
        ("change_vs_prior.verbatim '……'", af(lambda f: f.__setitem__(
            "change_vs_prior", {"verbatim": "……", "direction": "resolved", "prior_date_stated": None})))):
    d, (errs, _) = run(mut)
    check(f"{label} → ERROR", any("holds no source words" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__("verbatim_text", "……左肺上叶舌段肺动脉分支充盈缺损……")))
check("a legitimate '……'-elided quote still passes", errs == [], str(errs))

# change_vs_prior.verbatim is the report's own comparison wording, on the cited line(s) (§2.2)
d, (errs, _) = run(lambda d: (ct_imp_says("，较前增多")(d), af(lambda f: f.__setitem__(
    "change_vs_prior", {"verbatim": "较前增多", "direction": "increased", "prior_date_stated": None}))(d)))
check("change_vs_prior quoted from the cited line passes", errs == [], str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__(
    "change_vs_prior", {"verbatim": "较前明显增多", "direction": "increased", "prior_date_stated": "2029-12-01"})))
check("invented change_vs_prior wording → ERROR", any("change_vs_prior increased" in e and "not found" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: (ct_find_says("，较前增多")(d), af(lambda f: f.__setitem__(
    "change_vs_prior", {"verbatim": "较前增多", "direction": "increased", "prior_date_stated": None}))(d)))
check("comparison wording from another line (not the finding's) → ERROR",
      any("change_vs_prior increased" in e and "not found" in e for e in errs), str(errs))

# O-02.2: exam_date / report_date come from the report
d, (errs, _) = run(af(lambda f: f.__setitem__("exam_date", "2030-01-02")))
check("exam_date that is neither the report's filename date nor printed in it → ERROR",
      any("exam_date '2030-01-02'" in e for e in errs), str(errs))
d, (errs, _) = run(lambda d: (synlib.edit_text(d, synlib.SIDE_CT, lambda t: t.replace(
    "检查日期：2030-01-12", "检查日期：2030-01-12 报告日期：2030年1月13日", 1)),
    af(lambda f: f.__setitem__("report_date", "2030-01-13"))(d)))
check("report_date printed in the report as 2030年1月13日 passes", errs == [], str(errs))

# legacy archive: the same absence is a WARN
legacy = synlib.make_legacy(tmp / "legacy")
errs, warns = synlib.gate("gate_acute_findings", legacy)
check("legacy archive: missing file → WARN not ERROR", errs == [] and any("acute_findings.json: missing" in w for w in warns))

# ---- acute_findings.json is a SAFETY surface written on every pass — a Phase-2-only pass on a legacy
#      archive included — so it is not a current-contract marker; on a legacy archive its own schema and
#      source bindings are still ERRORs, only the timeline linkage is not required.
import json
import validate_structured_outputs as vso


def legacy_with_acute(tag, fn=None):
    """Legacy archive + the acute_findings.json a Phase-2-only pass writes (timeline_event_id null)."""
    return synlib.make(tmp / tag, lambda d: (synlib.downgrade_to_legacy(d), synlib.write_legacy_acute(d, fn)))


lg = legacy_with_acute("legacy_acute")
check("R1 legacy archive + acute_findings.json → still legacy (not a current-contract marker)",
      vso.archive_generation(lg) == "legacy" and not any("acute" in m for m in vso.generation_markers(lg)),
      str(vso.generation_markers(lg)))
errs, warns = synlib.gate("gate_acute_findings", lg)
check("R1 legacy + valid acute file with timeline_event_id null and no acute event → no error",
      errs == [] and not any("acute_findings.json: missing" in w for w in warns), str(errs + warns))
rc, all_errs, all_warns = synlib.validate(lg)
check("R1 …the whole validator stays on the legacy path (rc 0)", rc == 0, str(all_errs[:3]))
lg = legacy_with_acute("legacy_acute_bad_quote", lambda f: f.__setitem__("verbatim_text", "右侧颈内静脉充盈缺损"))
errs, _ = synlib.gate("gate_acute_findings", lg)
check("R1 legacy archive: a quote not on the cited line is an ERROR (not a legacy WARN)",
      any("verbatim text not found" in e for e in errs), str(errs))
lg = legacy_with_acute("legacy_acute_bad_table", lambda f: f.__setitem__("acuity", "incidental"))
errs, _ = synlib.gate("gate_acute_findings", lg)
check("R1 legacy archive: the fixed acuity table is enforced (ERROR)", any("means urgent" in e for e in errs), str(errs))
lg = legacy_with_acute("legacy_acute_bad_schema", lambda f: f.__setitem__("acuity", "severe"))
rc, all_errs, _ = synlib.validate(lg)
check("R1 legacy archive: acute_findings.json schema violation → ERROR (it has no legacy version)",
      rc == 1 and any(e.startswith("acute_findings.json: schema violation") for e in all_errs), str(all_errs[:3]))
lg = legacy_with_acute("legacy_acute_dangling", lambda f: f.__setitem__("timeline_event_id", "E-099"))
errs, _ = synlib.gate("gate_acute_findings", lg)
check("R1 legacy archive: a non-null timeline_event_id must still resolve", any("E-099" in e for e in errs), str(errs))
d, (errs, _) = run(af(lambda f: f.__setitem__("timeline_event_id", None)))
check("R1 current archive: timeline_event_id null → ERROR (the event is required there)",
      any("has no timeline.json event" in e for e in errs), str(errs))

# ---- the 段D narrative lead. A render that predates emergent/urgent findings (stale / unstamped, or an HTML
# with no render data) makes the re-render mandatory; until then Phase 2's pinned stale notice must stand in
# review_summary.md AND readiness.json warnings[] naming the missing findings — ERROR without it (legacy
# archives too), WARN with it; --final ERRORs on any stale lead; a fresh render that omits a finding is an ERROR.
import subprocess
STAMP = [sys.executable, str(synlib.SCRIPTS / "stamp_case_summary_sources.py")]
LEAD = vso.ACUTE_SUMMARY_LEAD + "左肺上叶舌段肺动脉分支充盈缺损（肺栓塞可能）（2030-01-12）。其后是病情概要。"
AF1_LABEL = "左肺上叶舌段肺动脉分支充盈缺损（肺栓塞可能）"
AF2_LABEL = "肝实质未见明确占位"


I18N_KEYS = ("html_lang", "doc_title", "disclaimer", "report_date_label", "sec_identity", "lbl_sex_age", "lbl_hwbmi",
             "lbl_ecog", "sec_summary", "sec_stage", "sec_trend", "sec_lesions", "sec_molecular", "sec_labs",
             "sec_treatment", "sec_path", "sec_caveats", "delta_title", "delta_vs", "delta_none", "trend_none",
             "val_male", "val_female", "val_pending", "val_to_start", "footer_doc")


def render(narrative, stamp=True, caveats=None):
    def fn(d):
        synlib.save(d, ".case_summary_data.json", {
            "i18n": {k: "x" for k in I18N_KEYS}, "fallbacks": {"__default__": "资料缺失"}, "report_date": "2030-01-20",
            "one_line_condition": "示例肿瘤（合成夹具）", "case_summary_narrative": narrative, "trend_charts": [],
            "lab_trends": [], "lesions": [], "molecular_rows": [], "treatment_lines": [],
            "caveats": [{"caveat_text": c} for c in (caveats or [])]})
        if stamp:
            subprocess.run(STAMP + [str(d)], check=True, capture_output=True)
    return fn


def notice(labels, review=True, readiness=True):
    """Phase 2's pinned stale notice (phase2 §7) naming `labels`, in review_summary.md and/or readiness warnings."""
    line = vso.CASE_SUMMARY_STALE_NOTICE + "；".join(f"{lb}（2030-01-12）" for lb in labels) + "。"
    def fn(d):
        if review:
            (d / "review_summary.md").write_text(line + "\n\n资料时效：示例。\n", encoding="utf-8")
        if readiness:
            synlib.edit_json(d, "readiness.json", lambda doc: doc.setdefault("warnings", []).append(line))
    return fn


def ref_of(d, rel, needle):
    lines = (d / rel).read_text(encoding="utf-8").splitlines()
    return f"{rel}#L{next(i for i, l in enumerate(lines, start=1) if needle in l)}"


def later_urgent(d):
    """An incremental run registers a second urgent finding (same CT report) after 段D rendered."""
    synlib.edit_text(d, synlib.SIDE_CT, lambda s: s.replace("肝实质未见明确占位。", "肝实质未见明确占位，尽快。"))
    def fn(doc):
        f2 = dict(doc["findings"][0])
        f2.update({"finding_id": "AF-002", "timeline_event_id": "E-099", "label": AF2_LABEL,
                   "finding_class": "other_source_flagged", "acuity": "urgent", "acuity_basis": "source_wording_escalation",
                   "acuity_basis_text": "尽快", "verbatim_text": "肝实质未见明确占位，尽快",
                   "source_ref": ref_of(d, synlib.SIDE_CT, "肝实质未见明确占位，尽快")})
        doc["findings"].append(f2)
    synlib.edit_json(d, "acute_findings.json", fn)
    def tl(doc):
        e = dict(next(e for e in doc["events"] if e["category"] == "acute_finding"))
        e.update({"event_id": "E-099", "acute_finding_id": "AF-002"})
        doc["events"].append(e)
    synlib.edit_json(d, "timeline.json", tl)


def incremental_entry(d):
    synlib.edit_json(d, "update_log.json", lambda doc: doc["entries"].append(dict(
        doc["entries"][-1], at="2030-01-20T12:00:00Z", run_mode="incremental", added=[], removed=[], degradations=[],
        note="incremental run: one new report")))


def both(*fns):
    return lambda d: [f(d) for f in fns]


def gate(d, final=False):
    e, w = [], []
    vso.gate_case_summary_html(d, e, w, final=final)
    keep = ("case_summary_narrative", "caveats quote", "段D stale", vso.CASE_SUMMARY_HTML_NAME)
    return [x for x in e if any(k in x for k in keep)], [x for x in w if any(k in x for k in keep)]


lg = legacy_with_acute("legacy_stale_summary")
render("病情概要。", stamp=False)(lg)
e2, w2 = gate(lg)
check("R1 legacy archive: 段D narrative without the urgent lead and no stale notice → ERROR (a safety surface: "
      "legacy archives too)", any("stale notice" in e and "AF-001" in e for e in e2), str(e2 + w2))
notice([AF1_LABEL])(lg)
e2, w2 = gate(lg)
check("R1 legacy archive: …with the stale notice in review_summary.md and readiness warnings → WARN only",
      not e2 and any("legacy archive" in w and "段D stale" in w for w in w2), str(e2 + w2))
rc, all_errs, _ = synlib.validate(lg)
check("R1 legacy archive with the notice: the whole validator stays rc 0", rc == 0, str(all_errs[:3]))
lg = legacy_with_acute("legacy_fresh_omits")
render("病情概要。")(lg)
e2, _ = gate(lg)
check("R1 legacy archive: a FRESH render (re-rendered on the legacy archive) that omits the finding → ERROR",
      any("this render read the current acute_findings.json" in e for e in e2), str(e2))

cur = synlib.make(tmp / "s1_unstamped", render("病情概要。", stamp=False))
e2, w2 = gate(cur)
check("S1 unstamped render + missing lead, no stale notice → ERROR naming both missing places",
      any("review_summary.md and readiness.json warnings[]" in e for e in e2), str(e2 + w2))
cur = synlib.make(tmp / "s1_unstamped_notice", both(render("病情概要。", stamp=False), notice([AF1_LABEL])))
e2, w2 = gate(cur)
check("S1 unstamped render + missing lead + stale notice in both places → WARN 段D stale, no ERROR "
      "(Phase 2 §9 stays passable)", not e2 and any("段D stale (unstamped" in w for w in w2), str(e2 + w2))
e2, _ = gate(cur, final=True)
check("S1 unstamped render + missing lead at --final → ERROR even with the notice (the re-render is mandatory)",
      any("terminal gate" in e for e in e2), str(e2))
cur = synlib.make(tmp / "s1_notice_review_only", both(render("病情概要。", stamp=False), notice([AF1_LABEL], readiness=False)))
e2, _ = gate(cur)
check("S1 stale notice only in review_summary.md → ERROR naming readiness.json warnings[]",
      any("missing from readiness.json warnings[]" in e for e in e2), str(e2))
cur = synlib.make(tmp / "s1_notice_readiness_only", both(render("病情概要。", stamp=False), notice([AF1_LABEL], review=False)))
e2, _ = gate(cur)
check("S1 stale notice only in readiness warnings → ERROR naming review_summary.md",
      any("missing from review_summary.md" in e for e in e2), str(e2))
cur = synlib.make(tmp / "s1_notice_wrong_label", both(render("病情概要。", stamp=False), notice(["别的所见"])))
e2, _ = gate(cur)
check("S1 stale notice that does not name the missing finding → ERROR", any("stale notice" in e for e in e2), str(e2))
cur = synlib.make(tmp / "s1_fresh_omits", render("病情概要。"))
e2, w2 = gate(cur)
check("S1 fresh render (stamp = current acute_findings.json) that omits the urgent finding → ERROR",
      any("this render read the current acute_findings.json" in e for e in e2), str(e2 + w2))
cur = synlib.make(tmp / "s1_fresh_ok", render(LEAD))
check("S1 fresh render that leads with the urgent finding → no message (positive)", gate(cur) == ([], []), str(gate(cur)))
check("S1 …and the same at --final", gate(cur, final=True) == ([], []), str(gate(cur, final=True)))
st = synlib.make(tmp / "s1_stale_full", lambda d: (render(LEAD)(d), later_urgent(d)))
e2, w2 = gate(st)
check("S1 stale render (a later run added AF-002), no stale notice → ERROR naming AF-002",
      any("AF-002" in e and "stale notice" in e for e in e2), str(e2 + w2))
st = synlib.make(tmp / "s1_stale_notice", lambda d: (render(LEAD)(d), later_urgent(d), notice([AF2_LABEL])(d)))
e2, w2 = gate(st)
check("S1 stale render + a notice naming AF-002 only (AF-001 is already in the lead) → WARN naming AF-002, no ERROR",
      not e2 and any("AF-002" in w and "段D stale (stale" in w for w in w2), str(e2 + w2))
e2, _ = gate(st, final=True)
check("S1 stale render at --final after a full run → ERROR", any("terminal gate" in e for e in e2), str(e2))
st = synlib.make(tmp / "s1_stale_incr", lambda d: (render(LEAD)(d), later_urgent(d), incremental_entry(d),
                                                   notice([AF2_LABEL])(d)))
e2, w2 = gate(st, final=True)
check("S1 stale render at --final after an incremental run → ERROR (new urgent finding: re-render is mandatory, "
      "never left to the freshness question)", any("terminal gate" in e and "AF-002" in e for e in e2), str(e2 + w2))
st2 = synlib.make(tmp / "s1_stale_restore", lambda d: (render(LEAD)(d), later_urgent(d), synlib.edit_json(
    d, "update_log.json", lambda doc: doc["entries"].append(dict(
        doc["entries"][-1], at="2030-01-20T12:00:00Z", run_mode="relevance_disposition", added=[], removed=[],
        degradations=[], note="restore: one quarantined report")))))
e2, w2 = gate(st2, final=True)
check("S1 stale render at --final after a Step 14 restore → ERROR (back to Step 12 before Step 17)",
      any("terminal gate" in e for e in e2), str(e2 + w2))
rc, all_errs, all_warns = synlib.validate(st)
check("S1 whole validator (Phase 2 §9 form) on the incremental archive with the notice: rc 0, stale lead a WARN",
      rc == 0 and any("段D stale" in w for w in all_warns), str(all_errs[:3]))
st3 = synlib.make(tmp / "s1_stale_incr_nonotice", lambda d: (render(LEAD)(d), later_urgent(d), incremental_entry(d)))
rc, all_errs, _ = synlib.validate(st3)
check("S1 whole validator on the same archive WITHOUT the notice → rc 1", rc == 1 and any("stale notice" in e for e in all_errs),
      str(all_errs[:3]))
# an older 段D that left only the HTML: nothing shows it carries the finding
html_only = synlib.make(tmp / "s1_html_only", lambda d: (d / vso.CASE_SUMMARY_HTML_NAME).write_text(
    "<!doctype html><title>x</title>", encoding="utf-8"))
e = []
vso.gate_case_summary_html(html_only, e, [])
check("S1 病情简要总结.html without .case_summary_data.json + an urgent finding + no notice → ERROR",
      any("stale notice" in x and "unverifiable" in x for x in e), str(e))
notice([AF1_LABEL])(html_only)
e, w = [], []
vso.gate_case_summary_html(html_only, e, w)
check("S1 …with the notice → no stale ERROR (WARN)", not any("stale notice" in x for x in e)
      and any("段D stale (unverifiable" in x for x in w), str(e + w))

# ---- TL: a finding quoted from a Chinese rendering of a foreign-language report (verbatim_is_translation,
# acute-findings.md §2.4) is never presented as the report's own words: the 段D lead is neutral (报告写到, not
# 报告原文写到), the translated item carries 中文转述 in its date parentheses, and a caveat quoting it starts
# 中文转述，非报告原句：. Routing is the lead's: fresh → ERROR, stale → notice / WARN, --final → ERROR; an incidental
# translated finding's caveat is ERROR on a fresh render, WARN on a stale one.
AF1_VERBATIM = "左肺上叶舌段肺动脉分支充盈缺损……请结合临床"
OLD_LEAD = "资料中有报告原文写到需要尽快告知治疗团队的发现：" + AF1_LABEL + "（2030-01-12）。其后是病情概要。"
MARKED = vso.ACUTE_SUMMARY_LEAD + AF1_LABEL + "（2030-01-12，中文转述）。其后是病情概要。"
CAV_ORIG = f"报告原文：{AF1_VERBATIM}（2030-01-12，胸部CT报告）——请尽快告知治疗团队"
CAV_TR = f"报告（外文）中文转述，非报告原句：{AF1_VERBATIM}（2030-01-12，胸部CT报告）——请尽快告知治疗团队"


def translated(acuity=None, dateless=False):
    def fn(d):
        def g(doc):
            f = doc["findings"][0]
            f["verbatim_is_translation"] = True
            if acuity:
                f["acuity"] = acuity
            if dateless:
                f["exam_date"] = f["report_date"] = None
        synlib.edit_json(d, "acute_findings.json", g)
    return fn


check("TL the pinned lead is neutral: no 报告原文 in it", "原文" not in vso.ACUTE_SUMMARY_LEAD, vso.ACUTE_SUMMARY_LEAD)
cur = synlib.make(tmp / "tl_old_lead", render(OLD_LEAD))
e2, _ = gate(cur)
check("TL fresh render still leading 「资料中有报告原文写到…」 → ERROR (the lead no longer claims 原文)",
      any("must start" in e and vso.ACUTE_SUMMARY_LEAD in e for e in e2), str(e2))
cur = synlib.make(tmp / "tl_unmarked", both(translated(), render(LEAD)))
e2, _ = gate(cur)
check("TL fresh render naming a translated finding without 中文转述 → ERROR",
      any("AF-001" in e and "without 「中文转述」" in e for e in e2), str(e2))
cur = synlib.make(tmp / "tl_ok", both(translated(), render(MARKED, caveats=[CAV_TR])))
check("TL fresh render: 「<label>（<日期>，中文转述）」 + caveat 「中文转述，非报告原句：…」 → no message (positive)",
      gate(cur) == ([], []), str(gate(cur)))
check("TL …and the same at --final", gate(cur, final=True) == ([], []), str(gate(cur, final=True)))
cur = synlib.make(tmp / "tl_dateless", both(translated(dateless=True),
                                            render(vso.ACUTE_SUMMARY_LEAD + AF1_LABEL + "（中文转述）。其后是病情概要。")))
check("TL a translated finding with no date written 「<label>（中文转述）」 → no message (positive)",
      gate(cur) == ([], []), str(gate(cur)))
cur = synlib.make(tmp / "tl_cav_orig", both(translated(), render(MARKED, caveats=[CAV_ORIG])))
e2, _ = gate(cur)
check("TL fresh render whose caveat introduces the translated quote as 「报告原文：」 → ERROR",
      any("caveats quote AF-001" in e for e in e2), str(e2))
cur = synlib.make(tmp / "tl_cav_both", both(translated(), render(MARKED, caveats=[CAV_TR + "；" + CAV_ORIG])))
e2, _ = gate(cur)
check("TL a caveat carrying the labelled translation AND the same quote as 「报告原文：」 → ERROR",
      any("caveats quote AF-001" in e for e in e2), str(e2))
cur = synlib.make(tmp / "tl_orig_ok", render(LEAD, caveats=[CAV_ORIG]))
check("TL an untranslated finding quoted 「报告原文：…」 → no message (positive: only a rendering is barred)",
      gate(cur) == ([], []), str(gate(cur)))
st = synlib.make(tmp / "tl_mark_other", lambda d: (later_urgent(d), translated()(d), render(
    vso.ACUTE_SUMMARY_LEAD + AF1_LABEL + "（2030-01-12）；" + AF2_LABEL + "（2030-01-12，中文转述）。其后是病情概要。")(d)))
e2, _ = gate(st)
check("TL the 中文转述 mark on another item, not on the translated finding's → ERROR naming AF-001",
      any("AF-001" in e and "without 「中文转述」" in e for e in e2) and not any("AF-002" in e for e in e2), str(e2))
cur = synlib.make(tmp / "tl_stale", both(translated(), render(LEAD, stamp=False)))
e2, w2 = gate(cur)
check("TL unstamped render naming the translated finding unmarked, no stale notice → ERROR (stale notice)",
      any("stale notice" in e and "AF-001" in e for e in e2), str(e2 + w2))
notice([AF1_LABEL])(cur)
e2, w2 = gate(cur)
check("TL …with the stale notice naming it → WARN only (Phase 2 §9 stays passable)",
      not e2 and any("段D stale (unstamped" in w and "AF-001" in w for w in w2), str(e2 + w2))
e2, _ = gate(cur, final=True)
check("TL …at --final → ERROR (the mandatory re-render writes it marked)", any("terminal gate" in e for e in e2), str(e2))
cur = synlib.make(tmp / "tl_inc_fresh", both(translated(acuity="incidental"), render("病情概要。", caveats=[CAV_ORIG])))
e2, w2 = gate(cur)
check("TL incidental translated finding quoted 「报告原文：」 in a fresh render → ERROR",
      any("caveats quote AF-001" in e for e in e2), str(e2 + w2))
cur = synlib.make(tmp / "tl_inc_stale", both(translated(acuity="incidental"), render("病情概要。", stamp=False, caveats=[CAV_ORIG])))
e2, w2 = gate(cur)
check("TL …in a stale (unstamped) render → WARN, not ERROR (an incidental change does not force the re-render)",
      not e2 and any("caveats quote AF-001" in w for w in w2), str(e2 + w2))
cur = synlib.make(tmp / "tl_inc_ok", both(translated(acuity="incidental"), render("病情概要。", caveats=[CAV_TR])))
check("TL incidental translated finding quoted 「中文转述，非报告原句：」 → no message (positive)",
      gate(cur) == ([], []), str(gate(cur)))

# ---- stamp_case_summary_sources.py
d = synlib.make(tmp / "stamp_ok", render("x", stamp=False))
r = subprocess.run(STAMP + [str(d)], capture_output=True, text=True)
got = json.loads((d / ".case_summary_data.json").read_text(encoding="utf-8")).get("acute_findings_sha256")
check("stamp script writes the sha256 of acute_findings.json", r.returncode == 0 and got == vso._sha256_path(d / "acute_findings.json"),
      r.stderr)
(d / "acute_findings.json").unlink()
subprocess.run(STAMP + [str(d)], check=True, capture_output=True)
check("stamp script writes null when acute_findings.json is absent",
      json.loads((d / ".case_summary_data.json").read_text(encoding="utf-8")).get("acute_findings_sha256", "x") is None)
d = synlib.make(tmp / "stamp_nodata")
r = subprocess.run(STAMP + [str(d)], capture_output=True, text=True)
check("stamp script without .case_summary_data.json → exit 2", r.returncode == 2, str(r.returncode))
bad = {"case_summary_narrative": "x", "acute_findings_sha256": "abc"}
check("schema rejects a stamp that is not 64 hex", bool(synlib.schema_errors("case_summary_data.schema.json", bad)))

print(f"acute-findings-gate: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
