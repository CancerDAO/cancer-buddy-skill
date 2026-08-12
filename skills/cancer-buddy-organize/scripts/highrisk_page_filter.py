#!/usr/bin/env python3
"""highrisk_page_filter.py — 定向第二读的确定性筛选（lite 绑定，零 LLM）。

扫描 ocr/（或桶内）sidecar，列出含高危内容的来源：药名/剂量/给药频次、分期串、
化验数值+单位、标识后缀。只有这些来源值得花第二次视觉读取——替代全量双读。

匹配是**召回优先**的粗筛（宁多勿漏）：漏筛的代价是误读值失去复核机会，
多筛的代价只是一次廉价的第二读。

用法: highrisk_page_filter.py <patient_dir> [--dir ocr] [--json <out>]
输出: {"high_risk": [{"source_id", "path", "hits": [...]}], "skipped": N}
"""
import argparse
import json
import re
import sys
from pathlib import Path

PATTERNS = {
    # 剂量/给药：数字+剂量单位（mg/ml/单位/次/日…）
    "dose": re.compile(r"\d+(?:\.\d+)?\s*(?:mg|g|ml|mL|μg|ug|IU|单位)(?:/(?:m2|m²|kg|次|日|d|天|周))?", re.I),
    # 化验值：数值 + 常见检验单位（允许隔一个 markdown 表格单元分隔符 `|`）
    "lab_value": re.compile(r"\d+(?:\.\d+)?\s*\|?\s*(?:U/m?l|ng/m?l|mmol/L|umol/L|μmol/L|g/L|%|×?10\^?9|10\*9)", re.I),
    # 分期串：TNM / 期
    "stage": re.compile(r"\b[cpy]{0,2}T[0-4isx][a-c]?N[0-3x][a-c]?M[01x]\b|[IVX]{1,4}\s*期", re.I),
    # 药名线索：常见抗肿瘤药后缀（粗筛）与化疗方案缩写
    "drug": re.compile(r"[一-鿿]{1,6}(?:单抗|替尼|拉唑|曲塞|铂|司他|昔布|杉醇|嘧啶|霉素)|FOLFOX|FOLFIRI|XELOX|CAPEOX", re.I),
    # 标识后缀（检验编号/病案号可见尾数）
    "identifier": re.compile(r"(?:编号|病案|条码|标本号)[^\n]{0,20}\d{3,}"),
    # 分子/变异
    "molecular": re.compile(r"\b(?:KRAS|NRAS|BRAF|EGFR|HER2|MSI|MSS|TMB|VAF|MLH1|MSH[26]|PMS2)\b", re.I),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patient_dir")
    ap.add_argument("--dir", default="ocr", help="相对 patient_dir 的 sidecar 目录（默认 ocr）")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    base = Path(args.patient_dir) / args.dir
    if not base.is_dir():
        print(json.dumps({"error": f"{base} not found"}))
        return 2
    high_risk, skipped = [], 0
    for md in sorted(base.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        hits = sorted({name for name, pat in PATTERNS.items() if pat.search(text)})
        source_id = (re.search(r"^source_id:\s*(\S+)", text, re.M) or [None, md.stem])[1]
        if hits:
            high_risk.append({"source_id": source_id,
                              "path": md.relative_to(args.patient_dir).as_posix(), "hits": hits})
        else:
            skipped += 1
    result = {"high_risk": high_risk, "skipped": skipped,
              "ratio": round(len(high_risk) / max(1, len(high_risk) + skipped), 2)}
    out = json.dumps(result, ensure_ascii=False, indent=1)
    print(out)
    if args.json:
        Path(args.json).write_text(out + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
