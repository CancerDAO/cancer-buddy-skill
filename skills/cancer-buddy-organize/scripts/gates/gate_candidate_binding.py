#!/usr/bin/env python3
"""G2 — 对账候选值-源绑定门（确定性，零 LLM）。

冲突/替换卡上的每个数值出示给患者之前，必须证明它真的来自声称的来源：

- old_value：能在 target_doc sidecar 逐字定位（数字带边界，67.2 永不匹配进 167.28），
  **且**该值不带 needs_human_review 复核标记（未经独立复读的档案值不得充当
  "档案现有事实"；P8 复读通过后可经 high_risk_review.json 升级）。
- new_value：能在新图的独立第二次读取产物（.second-read/<source_id>*.txt，由平台
  与 round-1 判定隔离生成：native text / tesseract / 隔离转录调用）中逐字定位。

任一失败 → binding = "value_unverified"：UI 必须渲染「数值待核对」+ 附原图，
禁止渲染成确定语气二选一。无 new_value/old_value 的候选（纯 supersede）不适用。

用法: gate_candidate_binding.py <candidates_json> <patient_dir> [--second-read <dir>] [--json <out>]
stdout: 原 candidates 逐条追加 binding / binding_reasons 后的 JSON。
退出码: 0 = 全部 verified/not_applicable；1 = 存在 value_unverified；2 = IO 错误。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import REVIEW_FLAG, numeric_token, read_json, value_locatable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from high_risk_review import find_review_record, load_review_records, verified_values

VERIFIED_STATES = ("double_read", "verified_by_second_read", "clinician_verified")


def inventory_entry(patient_dir, target_doc):
    inventory = read_json(Path(patient_dir) / "source_inventory.json") or {}
    for row in inventory.get("files", []) if isinstance(inventory, dict) else []:
        if not isinstance(row, dict):
            continue
        # v2 bucket_path is a directory. Only sidecar_path identifies a file;
        # accept an old full-file bucket_path solely for archive compatibility.
        if target_doc in (str(row.get("sidecar_path") or ""),
                          str(row.get("bucket_path") or "")):
            return row
    return None


def sidecar_source_id(patient_dir, target_doc):
    try:
        text = (Path(patient_dir) / target_doc).read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^source_id:\s*(\S+)", text, re.M)
    return match.group(1) if match else None


def review_overrides(patient_dir, target_doc):
    """Return value-level overrides via stable ID, never a current path join."""
    entry = inventory_entry(patient_dir, target_doc) or {}
    source_id = str(entry.get("source_id") or sidecar_source_id(patient_dir, target_doc) or "")
    file_id = str(entry.get("file_id") or source_id)
    records = load_review_records(Path(patient_dir) / "high_risk_review.json")
    record = find_review_record(records, file_id, source_id, target_doc)
    return verified_values(record)


def inventory_status(patient_dir, target_doc):
    row = inventory_entry(patient_dir, target_doc)
    return str(row.get("high_risk_review_status") or "") if row else ""


def old_value_flagged(lines, full_text, patient_dir, target_doc, value):
    """value 所在行带 needs_human_review，或行内无状态但文件级复核状态为待核。"""
    overrides = review_overrides(patient_dir, target_doc)
    # P8(verifySidecarHighRisk)以表格单元的裸数字作 key("67.61"),candidate 的 old_value
    # 通常带单位("67.61 U/ml")——两种 key 都试,否则复读升级永远打不通(同事 review 实锤)。
    keys = [str(value)]
    bare = numeric_token(value)
    if bare and bare not in keys:
        keys.append(bare)
    if any(str(overrides.get(key, "")) in VERIFIED_STATES for key in keys):
        return False
    value_lines_flagged = [l for l in lines if REVIEW_FLAG in l]
    if value_lines_flagged and len(value_lines_flagged) == len(lines):
        return True  # every occurrence of the value sits on a flagged row
    if any(state in l for l in lines for state in VERIFIED_STATES):
        return False
    if REVIEW_FLAG in full_text:
        return True  # file-level review marker and no per-line clearance
    if inventory_status(patient_dir, target_doc) == REVIEW_FLAG:
        return True
    return False


def second_read_text(second_read_dir, source_id):
    if not source_id or not second_read_dir:
        return None
    chunks = []
    base = Path(second_read_dir)
    for path in sorted(base.glob(f"{source_id}*.txt")):
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n".join(chunks) if chunks else None


def check_candidate(candidate, patient_dir, second_read_dir):
    reasons = []
    old_value = candidate.get("old_value")
    new_value = candidate.get("new_value")
    if old_value in (None, "") and new_value in (None, ""):
        return "not_applicable", reasons
    target_doc = str(candidate.get("target_doc") or "")
    if old_value not in (None, ""):
        target_path = Path(patient_dir) / target_doc
        if not target_path.is_file():
            reasons.append("target_doc_missing")
        else:
            text = target_path.read_text(encoding="utf-8")
            lines = value_locatable(old_value, text)
            if not lines:
                reasons.append("old_value_not_located_in_target_doc")
            elif old_value_flagged(lines, text, patient_dir, target_doc, old_value):
                reasons.append("old_value_needs_human_review")
    if new_value not in (None, ""):
        evidence = second_read_text(second_read_dir, str(candidate.get("source_id") or ""))
        if evidence is None:
            reasons.append("no_independent_second_read")
        elif not value_locatable(new_value, evidence):
            reasons.append("new_value_not_reproduced_by_second_read")
    return ("verified" if not reasons else "value_unverified"), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates_json")
    ap.add_argument("patient_dir")
    ap.add_argument("--second-read", default=None,
                    help="independent second-read evidence dir (default: <patient_dir>/../../.second-read)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    data = read_json(args.candidates_json)
    if data is None or not Path(args.patient_dir).is_dir():
        print(json.dumps({"gate": "G2_candidate_binding", "error": "bad input"}))
        return 2
    second_read_dir = args.second_read or str(Path(args.patient_dir).resolve().parent.parent / ".second-read")
    candidates = data.get("candidates") if isinstance(data, dict) else data
    unverified = 0
    for candidate in candidates or []:
        binding, reasons = check_candidate(candidate, args.patient_dir, second_read_dir)
        candidate["binding"] = binding
        candidate["binding_reasons"] = reasons
        unverified += binding == "value_unverified"
    result = {"gate": "G2_candidate_binding", "pass": unverified == 0,
              "unverified": unverified, "candidates": candidates or []}
    out = json.dumps(result, ensure_ascii=False, indent=1)
    print(out)
    if args.json:
        Path(args.json).write_text(out + "\n", encoding="utf-8")
    return 0 if unverified == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
