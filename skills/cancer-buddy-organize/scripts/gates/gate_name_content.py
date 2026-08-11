#!/usr/bin/env python3
"""G1 — 文件名↔sidecar 报告类型一致性门（确定性，零 LLM）。

背景：Phase-2 单次大批量归档曾把同批检验单的名字错位分配（内容是肿瘤标志5项的
sidecar 被命名"凝血功能筛查"入了凝血桶）。本门在落盘/交付前逐文件校验：
桶内文件名声称的报告类型，必须能在该 sidecar 自己的报告类型原文中找到
（归一化子串或别名组交集，别名表 references/report-type-aliases.json）。

判定：
- violation  文件名类型与 sidecar 报告类型确定性不匹配 → 不得以当前名落盘
- unknown    sidecar 无可解析的报告类型字段 → 不拦，记入 readiness flags
- ok         匹配

用法: gate_name_content.py <patient_dir> [--refs <references_dir>] [--json <out>]
退出码: 0 = 无 violation；1 = 有 violation；2 = 用法/IO 错误。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (alias_group_ids, canon, claimed_type_from_filename,
                         load_alias_groups, report_type_from_sidecar)

BUCKET_RE = re.compile(r"^\d{2}_")
PENDING_RE = re.compile(r"待归类资料|unclassified_record")


def types_match(claimed, sidecar_type, groups):
    c, s = canon(claimed), canon(sidecar_type)
    if not c or not s:
        return False
    if c in s or s in c:
        return True
    return bool(alias_group_ids(c, groups) & alias_group_ids(s, groups))


def run(patient_dir, refs_dir):
    patient_dir = Path(patient_dir)
    groups = load_alias_groups(refs_dir)
    result = {"gate": "G1_name_content", "pass": True, "checked": 0,
              "violations": [], "unknown": []}
    for bucket in sorted(p for p in patient_dir.iterdir() if p.is_dir() and BUCKET_RE.match(p.name)):
        for md in sorted(bucket.rglob("*.md")):
            rel = md.relative_to(patient_dir).as_posix()
            if PENDING_RE.search(md.name):
                continue  # already awaiting classification — not a naming claim
            claimed = claimed_type_from_filename(md.name)
            if not claimed:
                continue  # filename makes no report-type claim (INDEX, notes, …)
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            sidecar_type = report_type_from_sidecar(text)
            result["checked"] += 1
            if sidecar_type is None:
                result["unknown"].append({"path": rel, "claimed": claimed})
            elif not types_match(claimed, sidecar_type, groups):
                result["violations"].append(
                    {"path": rel, "claimed": claimed, "sidecar_says": sidecar_type})
    result["pass"] = not result["violations"]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patient_dir")
    ap.add_argument("--refs", default=None, help="references dir (default: ../references relative to this script)")
    ap.add_argument("--json", default=None, help="also write result JSON to this path")
    args = ap.parse_args()
    refs = args.refs or str(Path(__file__).resolve().parent.parent.parent / "references")
    if not Path(args.patient_dir).is_dir():
        print(json.dumps({"gate": "G1_name_content", "error": "patient_dir not found"}))
        return 2
    result = run(args.patient_dir, refs)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    print(out)
    if args.json:
        Path(args.json).write_text(out + "\n", encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
