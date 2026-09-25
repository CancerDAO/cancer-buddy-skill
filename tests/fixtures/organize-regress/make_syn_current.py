#!/usr/bin/env python3
"""Generate the synthetic current-contract (v2.1 / v2.2) organize archive fixture.

EVERYTHING HERE IS INVENTED: patient code, dates (2029-2030), the institution
("示例医院"), regimen / drug names ("示例方案A/B", "示例药B"), lab values (the §3.2
variant-A numbers of the O-03 column-pairing shape) and every sentence. No real
record, name, hospital or identifier is used. The public repo ships synthetic data only.

The archive exercises every v2.1 gate on its positive side: pinned sidecar headers
with EXTRACTOR ∈ update_log workers (a timed-out slice worker whose files were redispatched
as single-file workers p1-<source_id>-1, each listing exactly its one source), an llm-free
independent reread, one acute finding ↔ one timeline event, a recorded missing page with its
completeness / red flag, position-paired lab CANDIDATES (value null) whose sidecar carries the
`## 列配对` record pair_lab_columns.py prints for raw/_extract/s003.lab1.txt (EXTRACT_FILES —
written into the test copy's raw/ by synlib.make, since the repository ignores raw/) and a
legibility / yellow flag, an uncertain stage (field_class stage, no cross-document support →
red flag), an ongoing episode with its basis, a conflict_group pair, a prior-archive digest
(written by a Phase 1 digest worker, phase1_digest) used for history only, HLA typing (bare
locus letters), PS verbatim, one episode per regimen with its cycle label,
profile.latest_status carrying the episode's status_basis.

Usage:
    python3 make_syn_current.py [--out DIR]     # default: ./syn-current/src
Tests copy the committed src/ and then run fill_agents_md.py on the copy (AGENTS.md
is generated at test time because its template belongs to the prompt package).
tests/integration/organize-regress.sh re-runs this generator and fails on drift.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "skills" / "cancer-buddy-organize" / "scripts"))
import pair_lab_columns  # noqa: E402 — the fixture's lab record IS the script's output
PT = "PT-5A1F0C"
GEN_AT = "2030-01-20T09:00:00Z"
AS_OF = "2030-01-20"
INST = "示例医院"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# Stand-ins for the raw uploads. They are never written (a fixture has no raw/);
# only their hashes / sizes are recorded, exactly as inventory_hash.py would.
RAW = {
    "s001": b"synthetic-upload-s001-outpatient-page-1",
    "s002": b"synthetic-upload-s002-chest-ct",
    "s003": b"synthetic-upload-s003-tumour-markers",
    "s005": b"synthetic-upload-s005-family-note",
}
DS_STORE = b"synthetic-ds-store"


def header(src, fid, worker, primary, second, indep, read_mode, sha256, page_label, modality="text",
           confidence="medium", adapter="none"):
    """The pinned 12-key block (organizer-prompt-phase1-ocr.md §3): SOURCE is the document
    type, FILE_ID the original's source_id, CONFIDENCE rule-derived (low / medium / high)."""
    return "\n".join([
        f"SOURCE: {src}",
        f"FILE_ID: {fid}",
        f"EXTRACTOR: {worker}",
        f"PRIMARY_CHANNEL: {primary}",
        f"SECOND_READ_CHANNEL: {second}",
        f"INDEPENDENT_REREAD: {'true' if indep else 'false'}",
        f"READ_MODE: {read_mode}",
        f"ADAPTER: {adapter}",
        f"CONFIDENCE: {confidence}",
        f"SHA256: {sha256}",
        f"PAGE_LABEL: {page_label}",
        f"MODALITY: {modality}",
    ])


SIDE_OUTPATIENT = "03_病程与叙事文书/门诊病历/2030-01-10_门诊病历_示例医院_s001.md"
SIDE_CT = "05_影像/CT/2030-01-12_胸部CT_示例医院.md"
SIDE_LAB = "07_检验/肿瘤标志物/2030-01-15_肿瘤标志物_示例医院.md"
SIDE_DIGEST = "03_病程与叙事文书/既往档案摘录/2029-06-01_既往档案摘录.md"
SIDE_SELF = "14_患者自管补充/患者补充/undated_家属自述.md"
# Phase 1 workers: one slice worker timed out, its four files went to single-file workers (SKILL.md Step 4)
W_SLICE = "p1-s0-1"
W = {sid: f"p1-{sid}-1" for sid in ("s001", "s002", "s003", "s005")}
W_DIGEST = "p1digest-1"
W_P2 = "p2-1"
LAB_INPUT = "raw/_extract/s003.lab1.txt"

LAB_LINEAR = """肿瘤标志物检测（合成夹具）
报告日期：2030/01/15
检验项目
甲胎蛋白（AFP）
胃泌素释放肽前体
（ProGRP）
神经元特异性烯醇化酶（NSE）
人附睾蛋白
4（HE4）
鳞状上皮细胞癌抗原
（SCC）
糖类抗原15-3（CA15-3）
铁蛋白（FER）
糖类抗原50（CA50）
结果
3.46
118.2个
21.73
个
单位
ng/ml
pg/ml
ng/ml
96.5
参考范围
0~7
0~65
0~16.3
pmol/L
0.8
0~140
ng/ml
12.40
U/ml
0~1.5
ng/ml
402.6小
13~150
7.9
0~25"""

# raw/_extract files the `## 列配对` record names (the repository ignores raw/, so synlib.make writes
# them into each test copy; the committed src/ has no raw/ and the validator then checks the record
# only — one WARN).
EXTRACT_FILES = {LAB_INPUT: LAB_LINEAR + "\n"}
LAB_PAIRING = pair_lab_columns.pair(pair_lab_columns.columns_from_text(LAB_LINEAR))
LAB_RECORD = {"input": LAB_INPUT, **{k: LAB_PAIRING[k] for k in (
    "tool", "version", "status", "refused_reason", "pairing_method", "pairing_confidence", "counts",
    "column_decisions", "pairs")}}

SIDECARS = {
    SIDE_OUTPATIENT: header("outpatient_note", "s001", W["s001"], "deterministic_ocr:apple_vision",
                            "text_layer", True, "hybrid_verified", sha(RAW["s001"]), "第1页，共2页",
                            confidence="low") + """

# 版面重建

示例医院 门诊病历（合成夹具）
病区：日间治疗中心
就诊日期：2030-01-10
年龄：60岁
现病史：合成示例患者，本次为示例方案B第2周期，今日入日间治疗中心给药。
一般状况：PS 1分。
诊断：1. 示例肿瘤（[OCR_UNCERTAIN:U-001]期）
处理：示例药B 100 mg 静滴 配 5%葡萄糖注射液 250 ml。

## 不确定字段

- id: U-001
  line: 10
  field_class: stage
  readings:
    - {channel: "deterministic_ocr:apple_vision", text: "晚", confidence: 0.41}
    - {channel: text_layer, text: "晚", confidence: null}
  candidates: []
  cross_doc_supported: {status: none, refs: []}
  layout: none
  layout_intent: null

## PII

- 无
""",
    SIDE_CT: header("imaging_report", "s002", W["s002"], "deterministic_ocr:apple_vision",
                    "human", True, "hybrid_verified", sha(RAW["s002"]), "第1页 共1页",
                    confidence="high") + """

# 版面重建

示例医院 胸部CT报告（合成夹具）
检查日期：2030-01-12
影像所见：左肺上叶舌段肺动脉分支内见低密度充盈缺损，其余肺动脉显影良好。
肝实质未见明确占位。
印象：左肺上叶舌段肺动脉分支充盈缺损，考虑肺栓塞可能，请结合临床。

## PII

- 无
""",
    SIDE_LAB: header("lab_report", "s003", W["s003"], "deterministic_ocr:apple_vision",
                     "none", False, "deterministic_ocr", sha(RAW["s003"]), "none") + """

# 线性 OCR 原文（按列输出，无坐标；数值仅为按位置配对的候选）

""" + LAB_LINEAR + """

## 列配对

```json
""" + json.dumps(LAB_RECORD, ensure_ascii=False, indent=2) + """
```

## PII

- 无
""",
    SIDE_DIGEST: header("prior_archive_digest", "prior-20290601", W_DIGEST, "prior_archive_sidecar",
                        "none", False, "prior_archive_digest", "none", "none") + """

# 既往整理档案摘录（合成夹具；原件不在本次资料中）

既往整理档案（2029-06-01 生成）记载：2029-03 起曾接受示例方案A，共 4 程。
既往档案记载 HLA 分型：HLA-A*02:01。

## PII

- 无
""",
    SIDE_SELF: header("patient_supplement", "s005", W["s005"], "text_layer", "none", False,
                      "native_text", sha(RAW["s005"]), "none") + """

# 家属自述（合成夹具）

家属自述：2029-11 外院检查提示肝转移。

## PII

- 无
""",
}


def line_of(rel: str, needle: str) -> int:
    for i, line in enumerate(SIDECARS[rel].splitlines(), start=1):
        if needle in line:
            return i
    raise KeyError(f"{needle!r} not in {rel}")


def ref(rel: str, needle: str) -> str:
    return f"{rel}#L{line_of(rel, needle)}"


def build() -> dict[str, str]:
    out: dict[str, str] = dict(SIDECARS)
    # the U-001 block records the body line of its token
    out[SIDE_OUTPATIENT] = out[SIDE_OUTPATIENT].replace(
        "  line: 10", f"  line: {line_of(SIDE_OUTPATIENT, '[OCR_UNCERTAIN:U-001]')}")
    SIDECARS[SIDE_OUTPATIENT] = out[SIDE_OUTPATIENT]

    r_age = ref(SIDE_OUTPATIENT, "年龄：60岁")
    r_ps = ref(SIDE_OUTPATIENT, "PS 1分")
    r_now = ref(SIDE_OUTPATIENT, "本次为示例方案B第2周期")
    r_rx = ref(SIDE_OUTPATIENT, "示例药B 100 mg")
    r_dept = ref(SIDE_OUTPATIENT, "病区：日间治疗中心")
    r_dx = ref(SIDE_OUTPATIENT, "诊断：1. 示例肿瘤")
    r_ct_imp = ref(SIDE_CT, "印象：左肺上叶舌段肺动脉分支充盈缺损")
    r_ct_find = ref(SIDE_CT, "影像所见：")
    r_ct_perit = ref(SIDE_CT, "肝实质未见明确占位")
    lab_first = line_of(SIDE_LAB, '检验项目')
    lab_last = lab_first + len(LAB_LINEAR.splitlines()) - 1 - LAB_LINEAR.splitlines().index('检验项目')
    r_lab = f"{SIDE_LAB}#L{lab_first}-L{lab_last}"
    r_digest_tx = ref(SIDE_DIGEST, "示例方案A，共 4 程")
    r_digest_hla = ref(SIDE_DIGEST, "HLA-A*02:01")
    r_self = ref(SIDE_SELF, "外院检查提示肝转移")

    def j(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

    ps_verbatim = [{"text": "PS 1分", "as_of": "2030-01-10", "scale_label": "PS", "source_ref": r_ps}]

    # phase2 §0/§7: timeline.md and case_text.md are written on every build (the terminal gate requires both)
    out["timeline.md"] = (
        "# 时间线（合成夹具）\n\n"
        f"- 2030-01-10 门诊：本次为示例方案B第2周期 [[src:{r_now}]]\n"
        f"- 2030-01-12 胸部CT：左肺上叶舌段肺动脉分支充盈缺损 [[src:{r_ct_imp}]]\n"
        f"- 未注明日期 家属自述：外院检查提示肝转移（与 2030-01-12 CT 原文并列保留）[[src:{r_self}]]\n")
    out["case_text.md"] = (
        "# 病历文本（合成夹具）\n\n"
        f"诊断：1. 示例肿瘤 [[src:{r_dx}]]\n\n"
        f"2030-01-12 胸部CT 印象：左肺上叶舌段肺动脉分支充盈缺损 [[src:{r_ct_imp}]]\n")

    out["patient_summary.json"] = j({
        "patient_code": PT, "schema_version": "2.2", "generated_at": GEN_AT,
        "demographics": {
            "sex": None, "sex_normalized": None, "age": 60, "age_as_of": "2030-01-10",
            "age_observations": [{"value": 60, "as_of": "2030-01-10", "source_ref": r_age}],
            "birth_year": None, "height_cm": None, "height_cm_as_of": None,
            "weight_kg": None, "weight_kg_as_of": None, "ecog": None, "ecog_as_of": None,
            "function_description": None, "performance_status_verbatim": ps_verbatim,
            "provenance_layer": "source_reported", "verification_status": "unverified",
            "source_refs": [r_age, r_ps],
        },
        "diagnosis": {
            "primary": "示例肿瘤", "histology": None, "icd10": None, "diagnosed_at": None,
            "stage": None, "metastasis_sites": [], "provenance_layer": "source_reported",
            "verification_status": "unverified", "source_refs": [r_dx],
        },
        "current_status": {
            "regimen": "示例方案B", "response": None, "ecog": None, "as_of": "2030-01-10",
            "provenance_layer": "source_reported", "verification_status": "unverified",
            "source_refs": [r_now],
        },
    })
    out["profile.json"] = j({
        "schema": "cancer_buddy_profile_v3", "patient_code": PT, "locale": "zh",
        "generated_at": GEN_AT,
        "summary": {"one_line_condition": "示例肿瘤（合成夹具），在用示例方案B", "primary": "示例肿瘤",
                    "histology": None, "stage": None, "provenance_layer": "source_reported",
                    "verification_status": "unverified", "source_refs": [r_dx]},
        "latest_status": {"regimen": "示例方案B", "response": None, "ecog": None,
                          "as_of": "2030-01-10", "status_basis": "clinician_note_current", "source_refs": [r_now]},
        "demographics": {"sex": None, "age": 60, "age_as_of": "2030-01-10",
                         "performance_status_verbatim": ps_verbatim,
                         "provenance_layer": "source_reported", "source_refs": [r_age, r_ps]},
        "source_refs": [r_dx, r_now],
    })
    out["timeline.json"] = j({
        "patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT,
        "events": [
            {"event_id": "E-001", "date": "2029-03", "date_precision": "month", "category": "systemic_therapy",
             "title": "既往示例方案A（来自既往档案摘录）", "detail": None, "institution": None,
             "provenance_layer": "prior_archive", "verification_status": "unverified",
             "supersedes_event_id": None, "conflict_group": None, "acute_finding_id": None,
             "source_refs": [r_digest_tx]},
            {"event_id": "E-002", "date": "2029-11", "date_precision": "month", "category": "diagnosis",
             "title": "家属自述：外院检查提示肝转移", "detail": None, "institution": None,
             "provenance_layer": "caregiver_reported", "verification_status": "unverified",
             "supersedes_event_id": None, "conflict_group": "CG-001", "acute_finding_id": None,
             "source_refs": [r_self]},
            {"event_id": "E-003", "date": "2030-01-10", "date_precision": "day", "category": "systemic_therapy",
             "title": "示例方案B 第2周期（日间治疗中心）", "detail": None, "institution": INST,
             "provenance_layer": "source_reported", "verification_status": "unverified",
             "supersedes_event_id": None, "conflict_group": None, "acute_finding_id": None,
             "source_refs": [r_now]},
            {"event_id": "E-004", "date": "2030-01-12", "date_precision": "day", "category": "imaging",
             "title": "胸部CT：肝实质未见明确占位", "detail": None, "institution": INST,
             "provenance_layer": "source_reported", "verification_status": "unverified",
             "supersedes_event_id": None, "conflict_group": "CG-001", "acute_finding_id": None,
             "source_refs": [r_ct_perit]},
            {"event_id": "E-005", "date": "2030-01-12", "date_precision": "day", "category": "acute_finding",
             "title": "左肺上叶舌段肺动脉分支充盈缺损（肺栓塞可能）", "detail": None, "institution": INST,
             "provenance_layer": "source_reported", "verification_status": "unverified",
             "supersedes_event_id": None, "conflict_group": None, "acute_finding_id": "AF-001",
             "source_refs": [r_ct_imp]},
            {"event_id": "E-006", "date": "2030-01-15", "date_precision": "day", "category": "lab",
             "title": "肿瘤标志物（按位置配对的候选值，待核原件）", "detail": None, "institution": INST,
             "provenance_layer": "source_reported", "verification_status": "unverified",
             "supersedes_event_id": None, "conflict_group": None, "acute_finding_id": None,
             "source_refs": [r_lab]},
        ],
    })
    out["acute_findings.json"] = j({
        "patient_code": PT, "schema_version": "1", "generated_at": GEN_AT,
        "findings": [{
            "finding_id": "AF-001", "finding_class": "thrombus_embolism",
            "label": "左肺上叶舌段肺动脉分支充盈缺损（肺栓塞可能）",
            "verbatim_text": "左肺上叶舌段肺动脉分支充盈缺损……请结合临床",
            "exam_date": "2030-01-12", "report_date": "2030-01-12", "source_ref": r_ct_imp,
            "acuity": "urgent", "acuity_basis": "class_default", "acuity_basis_text": None,
            "change_vs_prior": {"verbatim": None, "direction": "not_stated", "prior_date_stated": None},
            "timeline_event_id": "E-005", "provenance_layer": "source_reported",
            "verification_status": "unverified",
        }],
    })
    out["treatment_lines.json"] = j({
        "patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT,
        "episodes": [
            {"episode_id": "EP-001", "sequence_index": 0, "documented_line_label": None,
             "phase_or_intent_source": None, "regimen": "示例方案A", "started_at": None, "ended_at": None,
             "clinician_reported_response": None, "reason_for_change_source": None,
             "provenance_layer": "prior_archive", "verification_status": "unverified",
             "source_refs": [r_digest_tx], "status": "stopped", "status_basis": "dates_only",
             "status_basis_text": "2029-03 起曾接受示例方案A，共 4 程", "status_as_of": None, "line_number": None},
            {"episode_id": "EP-002", "sequence_index": 1, "documented_line_label": None, "cycle_label_verbatim": "第2周期",
             "phase_or_intent_source": None, "regimen": "示例方案B", "started_at": None, "ended_at": None,
             "clinician_reported_response": None, "reason_for_change_source": None,
             "provenance_layer": "source_reported", "verification_status": "unverified",
             "source_refs": [r_now, r_rx], "status": "ongoing", "status_basis": "clinician_note_current",
             "status_basis_text": "本次为示例方案B第2周期，今日入日间治疗中心给药", "status_as_of": "2030-01-10",
             "line_number": None, "medication_refs": ["MED-001"]},
        ],
    })
    out["comorbidities.json"] = j({
        "patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT,
        "conditions": [],
        "medications": [{
            "name": "示例药B", "normalized_name": None, "dose": "100 mg", "frequency": None, "route": "静滴",
            "indication_source": None, "use_status": "unknown", "as_of": "2030-01-10",
            "medication_id": "MED-001", "administration_setting": "day_ward",
            "setting_basis": "病区：日间治疗中心", "order_role": "antineoplastic",
            "provenance_layer": "source_reported", "verification_status": "unverified",
            "source_refs": [r_rx, r_dept],
        }],
        "allergies": [],
    })
    panels = []
    for pr in LAB_PAIRING["pairs"]:  # phase2 §5.1: copied from the `## 列配对` record, field by field
        panels.append({"analyte": pr["item"], "normalized_analyte": None, "values": [{
            "date": "2030-01-15", "date_kind": "reported", "value": pr["value"], "raw_value": pr["raw_value"],
            "unit": pr["unit"], "reference_range": pr["reference_range"], "report_flag": None, "critical_flag": None,
            "provenance_layer": "source_reported", "verification_status": "unverified",
            "source_refs": [r_lab], "candidate_value": pr["candidate_value"], "pairing_method": pr["pairing_method"],
            "pairing_confidence": pr["pairing_confidence"], "pairing_note": pr["pairing_note"],
        }]})
    out["labs.json"] = j({"patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT, "panels": panels})
    out["molecular.json"] = j({
        "patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT,
        "reports": [], "variants": [], "ihc": [], "msi_results": [], "mmr_results": [],
        "hla_typing": [{"locus": "A", "allele": "A*02:01", "resolution": "2-field", "method": None,
                        "provenance_layer": "prior_archive", "verification_status": "unverified",
                        "source_refs": [r_digest_hla]}],
    })
    group_key = f"2030-01-10|03_病程与叙事文书/门诊病历|{INST}|2"
    out["missing_items.json"] = j({
        "patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT,
        "inventory_mode": "existing_document_inventory_only", "cancer_type": None,
        "document_gaps": [{
            "document_category": "门诊病历（2030-01-10，共 2 页）", "gap_type": "missing_pages",
            "reason_for_artifact": "同一份文书标注共 2 页，档案中缺第 2 页；补齐后可完整转录该次记录。",
            "severity": "red", "group_key": group_key, "pages_present": [1], "pages_missing": [2],
            "page_total": 2,
        }],
        "disclaimer": "Document inventory only; not a test or treatment recommendation.",
    })
    out["readiness.json"] = j({
        "patient_code": PT, "schema_version": "2.1", "generated_at": GEN_AT,
        "documentation_coverage": {"pathology_documents": "not_in_archive", "imaging_reports": "present"},
        "warnings": [],
        "latest_source_date": "2030-01-15", "days_since_latest": 5, "as_of_run_date": AS_OF,
        "review_flags": [
            {"id": "RF-001", "category": "extraction_fidelity", "affected_field": "diagnosis.stage",
             "current_source_values": [{"value": "[OCR_UNCERTAIN:U-001]", "source_ref": r_dx}],
             "issue": "分期用字未能确定，两个读取通道一致读作「晚」但置信度低，他页没有清楚读法；不作为分期依据。",
             "resolution_status": "unresolved", "severity": "red", "kind": "legibility",
             "cross_doc_supported": {"status": "none", "refs": []}, "uncertain_ids": ["U-001"]},
            {"id": "RF-002", "category": "cross_source_conflict", "affected_field": "timeline.liver",
             "current_source_values": [{"value": "外院检查提示肝转移（家属自述）", "source_ref": r_self},
                                       {"value": "肝实质未见明确占位", "source_ref": r_ct_perit}],
             "issue": "家属自述与 2030-01-12 CT 原文不一致，并列保留（conflict_group CG-001）。",
             "resolution_status": "unresolved", "severity": "yellow", "kind": "conflict"},
            {"id": "RF-003", "category": "missing_pages", "affected_field": "03_门诊病历 2030-01-10",
             "current_source_values": [{"value": "第1页，共2页", "source_ref": r_now}],
             "issue": "该次门诊病历缺第 2 页。", "resolution_status": "unresolved",
             "severity": "red", "kind": "completeness"},
            {"id": "RF-004", "category": "lab_column_pairing", "affected_field": "labs.肿瘤标志物",
             "current_source_values": [{"value": "项目 8 / 数值 8 / 单位 7 / 参考范围 7（按位置配对的候选值）",
                                        "source_ref": r_lab}],
             "issue": "检验表为线性文字（无坐标），数值按位置配对为候选值，未核实；单位、参考范围列计数不等未配对。",
             "resolution_status": "unresolved", "severity": "yellow", "kind": "legibility"},
        ],
    })
    worker_files = ["s001", "s002", "s003", "s005"]
    out["update_log.json"] = j({
        "schema_version": "1", "patient_code": PT,
        "entries": [{
            "at": GEN_AT, "run_mode": "full",
            "workers": [
                {"worker_id": W_SLICE, "phase": "phase1", "slice_id": "s0", "status": "timeout",
                 "files": worker_files},
                *[{"worker_id": W[s], "phase": "phase1_retry", "slice_id": None, "status": "done",
                   "files": [s]} for s in worker_files],
                {"worker_id": W_DIGEST, "phase": "phase1_digest", "slice_id": None, "status": "done",
                 "files": ["prior-20290601"]},
                {"worker_id": W_P2, "phase": "phase2", "slice_id": None, "status": "done",
                 "files": []},
            ],
            "inputs": [{"source_id": s, "sha256": sha(RAW[s])} for s in worker_files],
            "added": worker_files, "removed": [],
            "degradations": [{"worker_id": W_SLICE, "reason": "timeout",
                              "redispatched_as": [W[s] for s in worker_files]}],
            "note": None,
        }],
    })

    def row(fid, sid, raw, sidecar, modality, read_mode, worker, second, indep, hr_status, page_label,
            engine="apple_vision", adapter="none"):
        return {
            "file_id": fid, "source_id": sid, "original_path": raw.split("/")[-1] if raw else sid,
            "raw_path": raw, "page_range": None, "bucket_path": sidecar, "sidecar_path": sidecar,
            "modality": modality, "read_mode": read_mode,
            "extractor_provenance": {"engine": engine, "version": None, "raw_output_ref": None,
                                     "llm_role": "none", "worker_id": worker},
            "high_risk_review_status": hr_status, "adapter": adapter, "persist": True,
            "sha256": sha(RAW[sid]) if sid in RAW else None,
            "size_bytes": len(RAW[sid]) if sid in RAW else None,
            "page_count": 1 if raw and raw.endswith(".jpg") else None,
            "page_label": page_label, "source_kind": "upload",
            "second_read_channel": second, "independent_reread": indep,
        }

    digest_row = row("f004", "prior-20290601", None, SIDE_DIGEST, "text", "prior_archive_digest",
                     W_DIGEST, "none", False, "needs_human_review", None, engine="prior_archive_digest")
    digest_row["source_kind"] = "prior_archive_digest"
    digest_row["digest_of"] = {"archive_ref": "PT-5A1F0C@2029-06-01", "archive_generated_at": "2029-06-01",
                               "sidecar_refs": ["03_病程与叙事文书/出院小结/2029-05-20_出院小结.md"]}
    out["source_inventory.json"] = j({
        "schema": "source_inventory_v2.1", "patient_dir": ".", "generated_at": GEN_AT,
        "files": [
            row("f001", "s001", "raw/s001.jpg", SIDE_OUTPATIENT, "text", "hybrid_verified", W["s001"],
                "text_layer", True, "passed_independent_reread", "第1页，共2页"),
            row("f002", "s002", "raw/s002.jpg", SIDE_CT, "text", "hybrid_verified", W["s002"],
                "human", True, "passed_independent_reread", "第1页 共1页"),
            row("f003", "s003", "raw/s003.jpg", SIDE_LAB, "text", "deterministic_ocr", W["s003"],
                "none", False, "needs_human_review", None),
            digest_row,
            row("f005", "s005", "raw/s005.txt", SIDE_SELF, "text", "native_text", W["s005"],
                "none", False, "not_applicable", None, engine="plaintext"),
        ],
        "skipped_inputs": [{"input_ref": "skip-001", "reason": "ds_store", "sha256": sha(DS_STORE),
                            "size_bytes": len(DS_STORE)}],
    })
    return out


def write(out_dir: Path) -> list[str]:
    files = build()
    written = []
    for rel, text in sorted(files.items()):
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        written.append(rel)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE / "syn-current" / "src"))
    args = ap.parse_args()
    for rel in write(Path(args.out)):
        print(rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
