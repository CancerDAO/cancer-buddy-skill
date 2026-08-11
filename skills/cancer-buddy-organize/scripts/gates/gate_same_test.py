#!/usr/bin/env python3
"""G3 — 同检验判重门（确定性，零 LLM）。

同一张检验报告的两个载体（纸质拍照 vs App 截图/PDF）不构成"档案事实矛盾"。
candidate 出卡前比对确定性键，全部同时成立才改判：

- 检验编号：脱敏形态不统一（实测同批就有 `23*****017`/`ACCESSION_SUFFIX_8016`/
  `******8018`/`2301****13`/全遮蔽），因此不固定位数——取双方可见尾数的重叠区间
  比对，最小重叠 ≥3 位。candidate 散文里声称的编号是 LLM 陈述，不作输入。
- 采样时间戳与报告时间戳双双一致（同批多管秒级连号 + 编号末位相邻，任何单键
  在该场景下都会误判，见 PRD §4 G3"单键不判"）。

改判结果：
- same_test_duplicate  全键成立 → 不出 conflict 卡；若值仍不一致，标
  internal_read_discrepancy（我方读取问题，触发复读，不抛给用户）。
- possible_same_test   双时间戳一致但编号键不可用（可见位 <3）→ 保持原关系加 flag。

新图侧的编号/时间戳取自独立第二读产物（.second-read/<source_id>*.txt）。

用法: gate_same_test.py <candidates_json> <patient_dir> [--second-read <dir>] [--json <out>]
退出码: 0 = 正常（含有改判）；2 = IO 错误。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (accession_token, read_json, reported_at, sampled_at,
                         visible_accession_tail)

MIN_TAIL_OVERLAP = 3


def tails_match(tail_a, tail_b):
    if len(tail_a) < MIN_TAIL_OVERLAP or len(tail_b) < MIN_TAIL_OVERLAP:
        return None  # accession key unusable
    short, long_ = sorted((tail_a, tail_b), key=len)
    return long_.endswith(short)


def second_read_text(second_read_dir, source_id):
    chunks = []
    for path in sorted(Path(second_read_dir).glob(f"{source_id}*.txt")):
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n".join(chunks) if chunks else None


def judge(candidate, patient_dir, second_read_dir):
    target_doc = str(candidate.get("target_doc") or "")
    target_path = Path(patient_dir) / target_doc
    if not target_path.is_file():
        return None, {"reason": "target_doc_missing"}
    archive = target_path.read_text(encoding="utf-8")
    evidence = second_read_text(second_read_dir, str(candidate.get("source_id") or ""))
    if evidence is None:
        return None, {"reason": "no_independent_second_read"}
    keys = {
        "sampled_at": (sampled_at(archive), sampled_at(evidence)),
        "reported_at": (reported_at(archive), reported_at(evidence)),
    }
    ts_ok = all(a is not None and a == b for a, b in keys.values())
    tail_a = visible_accession_tail(accession_token(archive))
    tail_b = visible_accession_tail(accession_token(evidence))
    acc_ok = tails_match(tail_a, tail_b)
    detail = {"accession_tails": [tail_a, tail_b], "accession_match": acc_ok,
              "sampled_at_match": keys["sampled_at"][0] == keys["sampled_at"][1] and keys["sampled_at"][0] is not None,
              "reported_at_match": keys["reported_at"][0] == keys["reported_at"][1] and keys["reported_at"][0] is not None}
    if ts_ok and acc_ok is True:
        return "same_test_duplicate", detail
    if ts_ok and acc_ok is None:
        return "possible_same_test", detail
    return None, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates_json")
    ap.add_argument("patient_dir")
    ap.add_argument("--second-read", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    data = read_json(args.candidates_json)
    if data is None or not Path(args.patient_dir).is_dir():
        print(json.dumps({"gate": "G3_same_test", "error": "bad input"}))
        return 2
    second_read_dir = args.second_read or str(Path(args.patient_dir).resolve().parent.parent / ".second-read")
    candidates = data.get("candidates") if isinstance(data, dict) else data
    overrides = 0
    for candidate in candidates or []:
        if str(candidate.get("relation")) != "conflict":
            candidate["relation_override"] = None
            continue
        verdict, detail = judge(candidate, args.patient_dir, second_read_dir)
        candidate["relation_override"] = verdict
        candidate["same_test_keys"] = detail
        if verdict == "same_test_duplicate":
            overrides += 1
            old_value, new_value = candidate.get("old_value"), candidate.get("new_value")
            candidate["internal_read_discrepancy"] = (
                old_value not in (None, "") and new_value not in (None, "") and str(old_value) != str(new_value))
    result = {"gate": "G3_same_test", "pass": True, "overridden": overrides,
              "candidates": candidates or []}
    out = json.dumps(result, ensure_ascii=False, indent=1)
    print(out)
    if args.json:
        Path(args.json).write_text(out + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
