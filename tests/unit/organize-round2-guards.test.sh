#!/usr/bin/env bash
# Guards added after the second review / replay round (all data synthetic). Each negative mutates ONE
# thing in the clean synthetic archive and expects the named gate to fire; the unmutated archive (or the
# documented form) is the positive control.
#   L1  labs: a candidate_value only with a non-confirming method (linear_position / llm_row_read)
#   L2  labs: native_table / table_parser records need a born-digital channel; llm_row_read keeps value null
#   T1  treatment_lines: undated self-report ⇒ provenance patient_reported / caregiver_reported (schema test)
#   H1  molecular: hla_typing[].report_date is the typing report's own date
#   A1  acute: provenance source_reported only; never cites a prior-archive digest
#   A2  acute: prior_date_stated is printed in the cited report
#   A3  acute: escalation only along a class's own route (pneumonitis + 新发 stays urgent)
#   F1  review flags: foreign_language_paraphrase one per sidecar, other / yellow
#   F2  review flags: legacy_value_unsupported only on a legacy archive
#   Z1  --final: closing products (incl. timeline.md, case_text.md), the render's acute_findings_sha256 stamp,
#       empty ocr/, a phase2_5 worker after the last ingest run, template sha echoed
#   C2  a patient/caregiver self-report vs one original is conflict / yellow
#   P1  patient_code is upper-case hex (schemas)
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, subprocess, sys
from pathlib import Path
repo, tmp = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(repo / "tests/fixtures/organize-regress"))
import synlib
import validate_structured_outputs as vso

passed = failed = 0
n = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def run(gate, mutate=None, **kw):
    global n
    n += 1
    return synlib.gate(gate, synlib.make(tmp / f"g{n}", mutate), **kw)


def lab0(fn):
    return lambda d: synlib.edit_json(d, "labs.json", lambda doc: fn(doc["panels"][0]["values"][0]))


def af(fn):
    return lambda d: synlib.edit_json(d, "acute_findings.json", lambda doc: fn(doc["findings"][0]))


LAB = synlib.SIDE_LAB
CT = synlib.SIDE_CT

# ---- L1 labs schema: candidate_value ⇒ a non-confirming method --------------------------------------------
doc = synlib.fixture_doc("labs.json")
check("L1 positive: the fixture's linear_position candidates validate", synlib.schema_errors("labs.schema.json", doc) == [])
v = doc["panels"][0]["values"][0]
v["pairing_method"] = "bbox"
check("L1 bbox row carrying a candidate_value → schema rejects it",
      any("pairing_method" in e for e in synlib.schema_errors("labs.schema.json", doc)), str(synlib.schema_errors("labs.schema.json", doc)))
v.update({"candidate_value": None, "value": "3.46", "pairing_confidence": "high"})
check("L1 bbox row with a value and no candidate → accepted", synlib.schema_errors("labs.schema.json", doc) == [])
v.update({"pairing_method": "llm_row_read", "value": None, "candidate_value": "3.46", "pairing_confidence": "low"})
check("L1 llm_row_read candidate (value null, confidence low) → accepted", synlib.schema_errors("labs.schema.json", doc) == [])
v.update({"value": "3.46"})
check("L1 llm_row_read with a value → rejected", bool(synlib.schema_errors("labs.schema.json", doc)))
v.update({"value": None, "pairing_confidence": "high"})
check("L1 llm_row_read at confidence high → rejected", bool(synlib.schema_errors("labs.schema.json", doc)))


# ---- L2 lab pairing record ↔ sidecar channels ----------------------------------------------------------
def native_record(d, method="native_table", value="3.46", cand=None):
    rec = {"input": None, "pairing_method": method, "pairs": [
        {"item": "甲胎蛋白（AFP）", "raw_value": "3.46", "value": value, "candidate_value": cand, "pairing_method": method}]}
    synlib.edit_text(d, LAB, lambda t: t.split("## 列配对")[0] + "## 列配对\n\n```json\n"
                     + json.dumps(rec, ensure_ascii=False) + "\n```\n\n## PII\n\n- 无\n")
    synlib.edit_json(d, "labs.json", lambda doc: doc.__setitem__("panels", [{
        "analyte": "甲胎蛋白（AFP）", "normalized_analyte": None, "values": [dict(
            doc["panels"][0]["values"][0], value=value, candidate_value=cand, raw_value="3.46", pairing_method=method,
            pairing_confidence="high" if cand is None else "low", pairing_note=None)]}]))


errs, _ = run("gate_lab_pairing", lambda d: native_record(d))
check("L2 native_table record on a sidecar read by OCR (no text_layer / table_parser channel) → ERROR",
      any("claims native_table" in e for e in errs), str(errs[:3]))
errs, _ = run("gate_lab_pairing", lambda d: (native_record(d), synlib.edit_text(d, LAB, lambda t: t.replace(
    "SECOND_READ_CHANNEL: none", "SECOND_READ_CHANNEL: table_parser", 1))))
check("L2 native_table record with a table_parser channel in the header → no channel error",
      not any("claims native_table" in e for e in errs), str(errs[:3]))
errs, _ = run("gate_lab_pairing", lambda d: native_record(d, "llm_row_read", None, "3.46"))
check("L2 llm_row_read on a sidecar with no llm_vision channel → ERROR",
      any("names no llm_vision channel" in e for e in errs), str(errs[:3]))
errs, _ = run("gate_lab_pairing", lambda d: (native_record(d, "llm_row_read", None, "3.46"), synlib.edit_text(
    d, LAB, lambda t: t.replace("SECOND_READ_CHANNEL: none", "SECOND_READ_CHANNEL: llm_vision", 1))))
check("L2 llm_row_read with an llm_vision channel, value null + the legibility/yellow flag → OK", errs == [], str(errs[:3]))
errs, _ = run("gate_lab_pairing", lambda d: (native_record(d, "llm_row_read", None, "3.46"), synlib.edit_text(
    d, LAB, lambda t: t.replace("SECOND_READ_CHANNEL: none", "SECOND_READ_CHANNEL: llm_vision", 1)),
    synlib.edit_json(d, "readiness.json", lambda doc: doc.__setitem__(
        "review_flags", [f for f in doc["review_flags"] if f["id"] != "RF-004"]))))
check("L2 llm_row_read candidates without the legibility/yellow flag → ERROR",
      any("legibility / severity yellow" in e for e in errs), str(errs[:3]))

# ---- H1 HLA report_date -----------------------------------------------------------------------------
def hla(fn):
    return lambda d: synlib.edit_json(d, "molecular.json", lambda doc: fn(doc["hla_typing"][0]))


errs, _ = run("gate_record_links", hla(lambda h: h.__setitem__("report_date", "2029-06-01")))
check("H1 report_date = the cited digest's filename date → OK", errs == [], str(errs))
errs, _ = run("gate_record_links", hla(lambda h: h.__setitem__("report_date", "2029-02-14")))
check("H1 report_date printed nowhere in the cited report → ERROR", any("hla_typing[0] report_date" in e for e in errs), str(errs))
errs, _ = run("gate_record_links", hla(lambda h: h.__setitem__("report_date", None)))
check("H1 report_date null → OK (optional)", errs == [], str(errs))
doc = synlib.fixture_doc("molecular.json")
doc["hla_typing"][0]["report_date"] = "2029/06/01"
check("H1 report_date must be YYYY-MM-DD (schema)", bool(synlib.schema_errors("molecular.schema.json", doc)))

# ---- A1 acute provenance / digest -------------------------------------------------------------------
errs, _ = run("gate_acute_findings", af(lambda f: f.__setitem__("provenance_layer", "prior_archive")))
check("A1 acute finding with provenance prior_archive → ERROR", any("provenance_layer 'prior_archive'" in e for e in errs), str(errs))
errs, _ = run("gate_acute_findings", af(lambda f: f.__setitem__("provenance_layer", "caregiver_reported")))
check("A1 acute finding from a caregiver statement → ERROR", any("provenance_layer 'caregiver_reported'" in e for e in errs), str(errs))
DG = synlib.SIDE_DIGEST


def digest_finding(d):
    lines = (d / DG).read_text(encoding="utf-8").splitlines()
    n_ = next(i for i, l in enumerate(lines, start=1) if "示例方案A" in l)
    synlib.edit_json(d, "acute_findings.json", lambda doc: doc["findings"][0].update(
        {"source_ref": f"{DG}#L{n_}", "verbatim_text": "曾接受示例方案A", "exam_date": None, "report_date": None}))


errs, _ = run("gate_acute_findings", digest_finding)
check("A1 acute finding citing the prior-archive digest → ERROR", any("cites the prior-archive digest" in e for e in errs), str(errs))
errs, _ = run("gate_acute_findings")
check("A1 positive: the fixture's source_reported CT finding passes", errs == [], str(errs))

# ---- A2 prior_date_stated ---------------------------------------------------------------------------
def cvp(**kw):
    return af(lambda f: f["change_vs_prior"].update(kw))


def print_compare(d):
    synlib.edit_text(d, CT, lambda t: t.replace("检查日期：2030-01-12", "检查日期：2030-01-12 对比：2029-12-20 胸部CT", 1))


errs, _ = run("gate_acute_findings", cvp(prior_date_stated="2029-12-20"))
check("A2 prior_date_stated the report does not print → ERROR", any("prior_date_stated '2029-12-20'" in e for e in errs), str(errs))
errs, _ = run("gate_acute_findings", lambda d: (print_compare(d), cvp(prior_date_stated="2029-12-20")(d)))
check("A2 prior_date_stated printed on another line of the same report → OK", errs == [], str(errs))


# ---- A3 escalation routes ---------------------------------------------------------------------------
def ct_add(extra):
    return lambda d: synlib.edit_text(d, CT, lambda t: t.replace("肝实质未见明确占位。", "肝实质未见明确占位。" + extra, 1))


def reroute(cls, acuity, basis, text, verbatim):
    def fn(d):
        lines = (d / CT).read_text(encoding="utf-8").splitlines()
        n_ = next(i for i, l in enumerate(lines, start=1) if verbatim in l)
        synlib.edit_json(d, "acute_findings.json", lambda doc: doc["findings"][0].update(
            {"finding_class": cls, "acuity": acuity, "acuity_basis": basis, "acuity_basis_text": text,
             "verbatim_text": verbatim, "source_ref": f"{CT}#L{n_}", "label": verbatim}))
    return fn


PN = "双肺新发间质性改变"
errs, _ = run("gate_acute_findings", lambda d: (ct_add(PN + "。")(d),
              reroute("pneumonitis_ild_suspected", "emergent", "source_wording_escalation", PN, PN)(d)))
check("A3 pneumonitis + 新发 escalated to emergent → ERROR (no escalation route)",
      any("has no escalation in the fixed table" in e for e in errs), str(errs))
errs, _ = run("gate_acute_findings", lambda d: (ct_add(PN + "。")(d),
              reroute("pneumonitis_ild_suspected", "urgent", "class_default", None, PN)(d)))
check("A3 pneumonitis + 新发 kept at class_default urgent → OK", errs == [], str(errs))
OB = "左肺下叶远端新发阻塞性肺炎"
errs, _ = run("gate_acute_findings", lambda d: (ct_add(OB + "。")(d),
              reroute("other_source_flagged", "urgent", "source_wording_escalation", OB, OB)(d)))
check("A3 secondary obstructive change + 新发 → urgent OK", errs == [], str(errs))
errs, _ = run("gate_acute_findings", lambda d: (ct_add(OB + "。")(d),
              reroute("other_source_flagged", "emergent", "source_wording_escalation", OB, OB)(d)))
check("A3 other_source_flagged escalated past its route (emergent) → ERROR", any("to urgent" in e for e in errs), str(errs))
EF = "右侧胸膜腔新发少量积液"
errs, _ = run("gate_acute_findings", lambda d: (ct_add(EF + "。")(d),
              reroute("other_source_flagged", "urgent", "source_wording_escalation", EF, EF)(d)))
check("A3 新发 raising a non-obstructive other_source_flagged finding → ERROR",
      any("secondary obstructive change" in e for e in errs), str(errs))
SQ = "肝右叶低密度灶，建议尽快增强扫描"
errs, _ = run("gate_acute_findings", lambda d: (ct_add(SQ + "。")(d),
              reroute("other_source_flagged", "urgent", "source_wording_escalation", "建议尽快增强扫描", SQ)(d)))
check("A3 other_source_flagged + 尽快 → urgent OK (any finding)", errs == [], str(errs))
MA = "右肺动脉主干骑跨型充盈缺损"
errs, _ = run("gate_acute_findings", lambda d: (ct_add(MA + "。")(d),
              reroute("thrombus_embolism", "emergent", "source_wording_escalation", MA, MA)(d)))
check("A3 thrombus + 骑跨 → emergent OK", errs == [], str(errs))


# ---- F1 / F2 review-flag categories -----------------------------------------------------------------
def add_flag(**kw):
    base = {"id": "RF-090", "category": "foreign_language_paraphrase", "affected_field": "acute_findings.AF-001",
            "current_source_values": [{"value": "转述", "source_ref": f"{CT}#L16"}],
            "issue": "外文报告只有中文转述，需要按原文语言重新转写。", "resolution_status": "unresolved",
            "severity": "yellow", "kind": "other"}
    base.update(kw)
    return lambda d: synlib.edit_json(d, "readiness.json", lambda doc: doc["review_flags"].append(base))


G = "gate_review_flag_semantics"
errs, _ = run(G, add_flag())
check("F1 one foreign_language_paraphrase flag (other / yellow) → OK", errs == [], str(errs[:3]))
errs, _ = run(G, lambda d: (add_flag()(d), add_flag(id="RF-091", affected_field="timeline.E-005")(d)))
check("F1 two paraphrase flags on the same sidecar → ERROR (one per sidecar)",
      any("foreign_language_paraphrase flags" in e for e in errs), str(errs[:3]))
errs, _ = run(G, add_flag(severity="red"))
check("F1 paraphrase flag graded red → ERROR", any("is kind other / severity yellow" in e for e in errs), str(errs[:3]))
errs, _ = run(G, add_flag(category="legacy_value_unsupported", affected_field="demographics.sex"))
check("F2 legacy_value_unsupported on a current archive → ERROR", any("exists only on a legacy archive" in e for e in errs), str(errs[:3]))
leg = synlib.make_legacy(tmp / "f2_legacy")
synlib.edit_json(leg, "readiness.json", lambda doc: doc["review_flags"].append({
    "id": "RF-090", "category": "legacy_value_unsupported", "affected_field": "demographics.sex",
    "current_source_values": [{"value": "（旧结构化文件）", "source_ref": f"{CT}#L3"}],
    "issue": "旧档案结构化文件里有该值，本次 sidecar 中没有对应原文；保留并待核对。",
    "resolution_status": "unresolved", "severity": "yellow", "kind": "other"}))
errs, warns = synlib.gate(G, leg)
check("F2 legacy_value_unsupported (other / yellow) on a legacy archive → no ERROR",
      errs == [] and not any("exists only on a legacy archive" in w for w in warns), str(errs + warns)[:300])

# ---- Z1 --final -------------------------------------------------------------------------------------
VALIDATOR = repo / "skills/cancer-buddy-organize/scripts/validate_structured_outputs.py"
I18N = {"html_lang": "zh-CN", "doc_title": "病情简要总结", "disclaimer": "来源型资料摘要，不作诊断、疗效或治疗判断",
        "report_date_label": "报告日期", "sec_identity": "患者标识", "lbl_sex_age": "性别 / 年龄", "lbl_hwbmi": "身高 / 体重 / BMI",
        "lbl_ecog": "ECOG（仅医生原文）", "sec_summary": "资料概要", "sec_stage": "报告中的分期字符串", "sec_trend": "数值记录",
        "sec_lesions": "影像报告描述", "sec_molecular": "分子报告原文", "sec_labs": "实验室报告结果", "sec_treatment": "治疗记录",
        "sec_path": "治疗路径（本工具不生成）", "sec_caveats": "数据说明", "delta_title": "自上次摘要的数据变化", "delta_vs": "对比",
        "delta_none": "与上次摘要相比，已展示字段无变化", "trend_none": "暂无两次可比的来源数据", "val_male": "男", "val_female": "女",
        "val_pending": "资料中未找到", "val_to_start": "来源未写明", "footer_doc": "病情简要总结"}


def finish(d, p25=True, ocr_left=False, drop=None, stamp=True):
    org = repo / "skills/cancer-buddy-organize"
    data = {"i18n": I18N, "fallbacks": {"__default__": "资料缺失"}, "one_line_condition": "示例肿瘤（合成夹具）",
            "report_date": "2030-01-20",
            "case_summary_narrative": vso.ACUTE_SUMMARY_LEAD + "左肺上叶舌段肺动脉分支充盈缺损（肺栓塞可能）（2030-01-12）。其后是资料概要。",
            "trend_charts": [], "lab_trends": [], "lesions": [], "molecular_rows": [], "treatment_lines": [], "caveats": []}
    (d / ".case_summary_data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if stamp:  # 段D step 3: the render records the acute_findings.json it read
        subprocess.run([sys.executable, str(org / "scripts/stamp_case_summary_sources.py"), str(d)], check=True,
                       capture_output=True)
    subprocess.run([sys.executable, str(org / "scripts/render_html_template.py"), "--template",
                    str(org / "references/templates/case-summary.template.html"), "--data", str(d / ".case_summary_data.json"),
                    "--out", str(d / "病情简要总结.html")], check=True, capture_output=True)
    (d / "INDEX.md").write_text("# patient_code: PT-5A1F0C\n", encoding="utf-8")
    (d / "review_summary.md").write_text("# 核对摘要（合成夹具）\n", encoding="utf-8")
    subprocess.run([sys.executable, str(org / "scripts/write_organize_meta.py"), str(d), "--pii-layer1", "pii-1",
                    "--generated-at", "2030-01-20T10:00:00Z"], check=True, capture_output=True)
    if p25:
        synlib.edit_json(d, "update_log.json", lambda doc: doc["entries"].append({
            "at": "2030-01-20T10:00:00Z", "run_mode": "faithfulness_patch",
            "workers": [{"worker_id": "p25-1", "phase": "phase2_5", "slice_id": None, "status": "done", "files": []},
                        {"worker_id": "p2-2", "phase": "phase2", "slice_id": None, "status": "done", "files": []}],
            "inputs": doc["entries"][-1]["inputs"], "added": [], "removed": [], "degradations": [],
            "note": "Phase 2.5 found every checked value faithful; nothing rewritten"}))
    if ocr_left:
        (d / "ocr").mkdir(exist_ok=True)
        (d / "ocr" / "s009.md").write_text("SOURCE: lab_report\n", encoding="utf-8")
    if drop:
        (d / drop).unlink()


def final(d):
    p = subprocess.run([sys.executable, str(VALIDATOR), str(d), "--final"], capture_output=True, text=True)
    return p.returncode, p.stdout, [l[7:] for l in p.stderr.splitlines() if l.startswith("ERROR: ")]


d = synlib.make(tmp / "z_ok", finish)
rc, out, errs = final(d)
check("Z1 finished synthetic archive → --final OK", rc == 0, str(errs[:3]))
sha = vso.html_template_sha(d)
check("Z1 …the OK line echoes the HTML's template_sha256", bool(sha) and f"template_sha256={sha}" in out and ", final" in out, out)
rc, _, errs = final(synlib.make(tmp / "z_no_p25", lambda d: finish(d, p25=False)))
check("Z1 no phase2_5 worker after the last ingest run → ERROR", rc == 1 and any("no phase2_5 worker" in e for e in errs), str(errs[:3]))
rc, _, errs = final(synlib.make(tmp / "z_ocr", lambda d: finish(d, ocr_left=True)))
check("Z1 a sidecar left in ocr/ → ERROR", rc == 1 and any("ocr/ still holds" in e for e in errs), str(errs[:3]))
for name in ("review_summary.md", "INDEX.md", "organize_meta.json", "病情简要总结.html", "timeline.md", "case_text.md"):
    rc, _, errs = final(synlib.make(tmp / f"z_drop_{abs(hash(name))}", lambda d, name=name: finish(d, drop=name)))
    check(f"Z1 {name} missing → ERROR under --final", rc == 1 and any(f"final: {name} missing" in e for e in errs), str(errs[:3]))
rc, _, errs = final(synlib.make(tmp / "z_nostamp", lambda d: finish(d, stamp=False)))
check("Z1 render data without acute_findings_sha256 → ERROR under --final",
      rc == 1 and any("carries no acute_findings_sha256" in e for e in errs), str(errs[:3]))
p = subprocess.run([sys.executable, str(VALIDATOR), str(synlib.make(tmp / "z_nofinal", lambda d: finish(d, p25=False)))],
                   capture_output=True, text=True)
check("Z1 without --final (Phase 2 §9) the closing products are not required", p.returncode == 0, p.stderr[-300:])
leg = synlib.make_legacy(tmp / "z_legacy")
p = subprocess.run([sys.executable, str(VALIDATOR), str(leg), "--final"], capture_output=True, text=True)
check("Z1 legacy archive + --final → WARN, rc 0 (a Phase-2-only pass writes no organize_meta.json)",
      p.returncode == 0 and "final: legacy archive" in p.stderr, p.stderr[-300:])

# ---- C2 a self-report vs one original is conflict / yellow (phase2 §6.1, §2.4) ----------------------
def rf002(fn):
    return lambda d: synlib.edit_json(d, "readiness.json", lambda doc: fn(next(f for f in doc["review_flags"] if f["id"] == "RF-002")))


SELF_MSG = "is a self-report vs one original"
errs, _ = run("gate_review_flag_semantics")
check("C2 fixture: family statement vs CT graded yellow → no self-report ERROR (positive)", not any(SELF_MSG in e for e in errs), str(errs[:3]))
errs, _ = run("gate_review_flag_semantics", rf002(lambda f: f.__setitem__("severity", "red")))
check("C2 the same flag graded red → ERROR", any(SELF_MSG in e and "RF-002" in e for e in errs), str(errs[:3]))
errs, _ = run("gate_review_flag_semantics", rf002(lambda f: (f.__setitem__("severity", "red"),
                                                                f["current_source_values"][0].__setitem__("source_ref", "conversation:2030-01-19T08:30:00+08:00"))))
check("C2 a 段C conversation: statement vs the CT graded red → ERROR", any(SELF_MSG in e for e in errs), str(errs[:3]))
two_orig = synlib.fixture_doc("readiness.json")["review_flags"][2]["current_source_values"][0]["source_ref"]
errs, _ = run("gate_review_flag_semantics", rf002(lambda f: (f.__setitem__("severity", "red"),
                                                                f["current_source_values"][0].__setitem__("source_ref", two_orig))))
check("C2 two originals that disagree may be red (no self-report involved) → no self-report ERROR",
      not any(SELF_MSG in e for e in errs), str(errs[:3]))

# ---- P1 patient_code case ---------------------------------------------------------------------------
doc = synlib.fixture_doc("labs.json")
check("P1 upper-case hex patient_code accepted", synlib.schema_errors("labs.schema.json", doc) == [])
doc["patient_code"] = "PT-5a1f0c"
check("P1 lower-case hex patient_code rejected (SKILL Step 2 pins .upper())", bool(synlib.schema_errors("labs.schema.json", doc)))

print(f"organize-round2-guards: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
