#!/usr/bin/env python3
"""
record_namer.py — canonical filename generator for organized patient records.

Contract:
    Input  : --plan-from <path>  (JSON array of OCR sidecar records, see below)
    Output : JSON rename plan on stdout

Each input record (one per file in patient_dir):
    {
      "original_path": "<absolute path to physical file in 11 bucket dir>",
      "ocr_sidecar":   "<absolute path to ocr/<basename>.md, or null>",
      "ocr_text":      "<full OCR sidecar text content, or null if no OCR>",
      "bucket":        "<e.g. 02_诊断与分期>",
      "subbucket":     "<e.g. 病理报告>, optional",
      "default_org":   "<optional task-context org name fallback>"
    }

Output JSON:
    {
      "patient_dir_rename": {
        "cancer_label": "<extracted, normalized — see CANCER_VOCAB below>",
        "first_dx_yyyymm": "YYYY-MM",
        "hash4": "<4-hex>",
        "proposed": "<cancer_label>_<YYYY-MM>_<hash4>",
        "fallback_used": true/false,
        "reason_if_fallback": "<...>"
      },
      "file_renames": [
        {
          "original_path": "...",
          "new_basename": "<YYYY-MM-DD>_<doc_type>_<机构>.<ext>",
          "new_path":     "<absolute path with new basename>",
          "extracted": {
            "date": "YYYY-MM-DD | UNKNOWN-DATE",
            "doc_type": "...",
            "org": "... | unknown-org",
            "page": null | 1 | 2 | ...
          },
          "collision_suffix": null | "_2",
          "sidecar_rename": null | {"old": "...", "new": "..."},
          "audit": {
            "date_source": "ocr_body | filename | mtime | none",
            "org_source": "ocr_body | filename | task_default | unknown",
            "doc_type_source": "ocr_body | subbucket | bucket | default"
          }
        }
      ],
      "ref_backfill": {
        "manifest_old_to_new": {"old/basename.ext": "new/basename.ext", ...},
        "sidecar_old_to_new":  {"ocr/old.md": "ocr/new.md", ...}
      },
      "warnings": ["...", ...]
    }

Spec sources:
    - feishu PRD: https://pcnsvomh0o8a.feishu.cn/wiki/NT7UwtrVli6io6kSRImcqBJhnfg
      § "文件命名规则: 日期_类型_机构 例: 2025-10-08_出院小结_中山六院.pdf"
      § "机构字段提取优先级: 报告正文 → 文件元信息/文件名 → 任务上下文 → unknown-org"
    - patient_dir 命名 (用户 2026-05-18 选项): <cancer>_<YYYY-MM>_<hash4>

Reads no network. Pure stdlib. Safe to run offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


CANCER_VOCAB = {
    "宫颈癌": ["宫颈癌", "宫颈鳞癌", "宫颈腺癌", "宫颈鳞状", "cervical cancer", "cervical carcinoma", "cervix cancer"],
    "乳腺癌": ["乳腺癌", "乳腺浸润", "breast cancer", "breast carcinoma"],
    "肺腺癌": ["肺腺癌", "肺腺鳞", "lung adenocarcinoma", "adenocarcinoma of lung"],
    "肺鳞癌": ["肺鳞癌", "肺鳞状", "lung squamous", "squamous cell carcinoma of lung"],
    "肺癌": ["肺癌", "lung cancer", "lung carcinoma", "NSCLC", "SCLC", "非小细胞肺", "小细胞肺"],
    "结直肠癌": ["结直肠癌", "结肠癌", "直肠癌", "colorectal", "colon cancer", "rectal cancer", "CRC"],
    "胃癌": ["胃癌", "胃腺癌", "gastric cancer", "stomach cancer"],
    "肝癌": ["肝癌", "肝细胞癌", "hepatocellular", "HCC", "liver cancer"],
    "胰腺癌": ["胰腺癌", "pancreatic cancer", "pancreatic adenocarcinoma"],
    "食管癌": ["食管癌", "食道癌", "esophageal cancer"],
    "前列腺癌": ["前列腺癌", "prostate cancer"],
    "卵巢癌": ["卵巢癌", "ovarian cancer"],
    "子宫内膜癌": ["子宫内膜癌", "endometrial cancer"],
    "甲状腺癌": ["甲状腺癌", "甲状腺乳头", "thyroid cancer"],
    "鼻咽癌": ["鼻咽癌", "nasopharyngeal", "NPC"],
    "淋巴瘤": ["淋巴瘤", "lymphoma", "DLBCL"],
    "白血病": ["白血病", "leukemia", "AML", "ALL", "CML", "CLL"],
    "黑色素瘤": ["黑色素瘤", "melanoma"],
    "脑胶质瘤": ["胶质瘤", "胶质母细胞", "glioma", "GBM"],
    "肾癌": ["肾癌", "肾细胞癌", "renal cell", "RCC"],
    "膀胱癌": ["膀胱癌", "bladder cancer"],
    "骨肉瘤": ["骨肉瘤", "osteosarcoma"],
}


DOC_TYPE_PATTERNS = [
    ("病理报告", [r"病理报告", r"病理诊断", r"pathology report", r"免疫组化", r"IHC"]),
    ("基因检测", [r"基因检测", r"NGS", r"WES", r"分子病理", r"genomic profiling", r"PD-L1\s*CPS", r"靶向检测"]),
    ("CT", [r"\bCT(?:扫描|平扫|增强)?\b", r"computed tomography"]),
    ("MRI", [r"\bMRI\b", r"磁共振", r"MR\b"]),
    ("PET-CT", [r"PET[-/ ]?CT", r"PET[-/ ]?MR"]),
    ("超声", [r"超声(?:报告)?", r"彩超", r"ultrasound", r"\bUS\b"]),
    ("X线", [r"\bX[-\s]?线\b", r"DR\b", r"胸片"]),
    ("出院小结", [r"出院小结", r"出院记录", r"discharge summary"]),
    ("入院记录", [r"入院记录", r"admission note"]),
    ("门诊病历", [r"门诊病历", r"门诊记录", r"outpatient"]),
    ("手术记录", [r"手术记录", r"术后小结", r"operation note", r"surgical report"]),
    ("化疗记录", [r"化疗记录", r"化疗医嘱", r"chemo(?:therapy)? record"]),
    ("放疗记录", [r"放疗记录", r"放疗计划", r"radiotherapy"]),
    ("血常规", [r"血常规", r"全血细胞", r"CBC\b"]),
    ("血生化", [r"血生化", r"生化全套", r"肝功能", r"肾功能", r"电解质"]),
    ("肿瘤标志物", [r"肿瘤标志物", r"CEA", r"CA[\s-]?125", r"CA[\s-]?199", r"AFP", r"PSA"]),
    ("尿常规", [r"尿常规", r"urinalysis"]),
    ("免疫指标", [r"免疫(?:指标|功能)", r"流式细胞"]),
    ("处方", [r"处方", r"prescription", r"医嘱"]),
    ("会诊意见", [r"会诊(?:意见|记录)", r"MTB", r"MDT"]),
    ("身份证明", [r"身份证", r"医保卡", r"ID card"]),
    ("知情同意", [r"知情同意"]),
]


ORG_HINTS = [
    r"([一-龥]{2,15}医院)",
    r"([一-龥]{2,15}医学中心)",
    r"([一-龥]{2,15}肿瘤(?:防治)?(?:研究)?中心)",
    r"([一-龥]{2,15}(?:大学)?(?:附属)?第?[一二三四五六七八九十]+医院)",
    r"(中山[一二三四五六七八九十]院)",
    r"(华西医院)",
    r"(协和医院)",
    r"(湘雅医院)",
    r"(瑞金医院)",
    r"(华大基因)",
    r"(燃石医学)",
    r"(吉因加)",
    r"(泛生子)",
]


ILLEGAL_FS_CHARS = re.compile(r'[/\\<>:"|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    s = ILLEGAL_FS_CHARS.sub("-", name).strip().strip(".")
    s = re.sub(r"\s+", "_", s)
    return s[:120] if len(s) > 120 else s


def extract_date(text: str | None, fallback_mtime: float | None = None) -> tuple[str, str]:
    """Return (YYYY-MM-DD or 'UNKNOWN-DATE', source: 'ocr_body'|'filename'|'mtime'|'none')."""
    if not text:
        if fallback_mtime:
            d = datetime.fromtimestamp(fallback_mtime).strftime("%Y-%m-%d")
            return d, "mtime"
        return "UNKNOWN-DATE", "none"
    patterns = [
        (r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", "ocr_body"),
        (r"(\d{4})(\d{2})(\d{2})", "ocr_body"),
    ]
    candidates = []
    for pat, src in patterns:
        for m in re.finditer(pat, text):
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2000 <= y <= datetime.now().year + 1 and 1 <= mo <= 12 and 1 <= d <= 31:
                    candidates.append((datetime(y, mo, d), src))
            except (ValueError, IndexError):
                continue
    if candidates:
        candidates.sort(key=lambda x: x[0])
        chosen = candidates[0]
        return chosen[0].strftime("%Y-%m-%d"), chosen[1]
    if fallback_mtime:
        return datetime.fromtimestamp(fallback_mtime).strftime("%Y-%m-%d"), "mtime"
    return "UNKNOWN-DATE", "none"


def extract_doc_type(text: str | None, subbucket: str | None, bucket: str) -> tuple[str, str]:
    """Return (doc_type, source: 'ocr_body'|'subbucket'|'bucket'|'default')."""
    if text:
        for canonical, patterns in DOC_TYPE_PATTERNS:
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return canonical, "ocr_body"
    if subbucket:
        return safe_name(subbucket), "subbucket"
    bucket_clean = re.sub(r"^\d+_", "", bucket)
    return safe_name(bucket_clean), "bucket"


def extract_org(text: str | None, filename: str | None, default_org: str | None) -> tuple[str, str]:
    """Return (org, source: 'ocr_body'|'filename'|'task_default'|'unknown'). Priority per PRD."""
    if text:
        for pat in ORG_HINTS:
            m = re.search(pat, text)
            if m:
                return safe_name(m.group(1)), "ocr_body"
    if filename:
        for pat in ORG_HINTS:
            m = re.search(pat, filename)
            if m:
                return safe_name(m.group(1)), "filename"
    if default_org:
        return safe_name(default_org), "task_default"
    return "unknown-org", "unknown"


def extract_page(text: str | None, filename: str | None) -> int | None:
    if text:
        m = re.search(r"第\s*(\d+)\s*[/\\]\s*\d+\s*页", text) or re.search(r"page\s+(\d+)\s+of\s+\d+", text, re.I)
        if m:
            return int(m.group(1))
    if filename:
        m = re.search(r"[_-]p(?:age)?[_-]?(\d+)", filename, re.I) or re.search(r"[_-](\d+)of\d+", filename, re.I)
        if m:
            return int(m.group(1))
    return None


def extract_cancer(text: str | None) -> str | None:
    if not text:
        return None
    for canonical, aliases in CANCER_VOCAB.items():
        for alias in aliases:
            if re.search(re.escape(alias), text, re.IGNORECASE):
                return canonical
    return None


def short_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:4]


def derive_patient_dir(records: list[dict], current_dir: str) -> dict:
    cancer_label = None
    first_dx_date = None
    for r in records:
        c = extract_cancer(r.get("ocr_text", ""))
        if c and not cancer_label:
            cancer_label = c
        d_str, _ = extract_date(r.get("ocr_text", ""), None)
        if d_str != "UNKNOWN-DATE":
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d")
                if first_dx_date is None or d < first_dx_date:
                    first_dx_date = d
            except ValueError:
                continue
    hash4 = short_hash(current_dir + ":" + (cancer_label or "") + ":" + (first_dx_date.isoformat() if first_dx_date else ""))
    if cancer_label and first_dx_date:
        return {
            "cancer_label": cancer_label,
            "first_dx_yyyymm": first_dx_date.strftime("%Y-%m"),
            "hash4": hash4,
            "proposed": f"{cancer_label}_{first_dx_date.strftime('%Y-%m')}_{hash4}",
            "fallback_used": False,
            "reason_if_fallback": None,
        }
    return {
        "cancer_label": cancer_label,
        "first_dx_yyyymm": first_dx_date.strftime("%Y-%m") if first_dx_date else None,
        "hash4": hash4,
        "proposed": f"PT-{hash4}{hashlib.sha256(current_dir.encode()).hexdigest()[:6]}",
        "fallback_used": True,
        "reason_if_fallback": (
            "OCR did not yield a recognizable cancer type" if not cancer_label
            else "OCR did not yield any parseable date"
        ),
    }


def build_rename_plan(records: list[dict], current_dir: str) -> dict:
    patient = derive_patient_dir(records, current_dir)
    file_renames = []
    used_basenames: dict[str, int] = {}
    manifest_map: dict[str, str] = {}
    sidecar_map: dict[str, str] = {}
    warnings: list[str] = []

    for r in records:
        op = r["original_path"]
        original_basename = os.path.basename(op)
        ext = os.path.splitext(original_basename)[1].lstrip(".").lower() or "bin"
        mtime = None
        try:
            mtime = os.path.getmtime(op)
        except OSError:
            warnings.append(f"cannot stat {op}; mtime fallback unavailable")
        date_str, date_src = extract_date(r.get("ocr_text"), mtime)
        doc_type, doc_src = extract_doc_type(r.get("ocr_text"), r.get("subbucket"), r.get("bucket", ""))
        org, org_src = extract_org(r.get("ocr_text"), original_basename, r.get("default_org"))
        page = extract_page(r.get("ocr_text"), original_basename)
        parts = [date_str, doc_type, org]
        if page is not None:
            parts.append(f"p{page}")
        candidate = "_".join(parts) + "." + ext
        candidate = safe_name(candidate)
        collision_suffix = None
        if candidate in used_basenames:
            used_basenames[candidate] += 1
            stem, dot, e = candidate.rpartition(".")
            collision_suffix = f"_{used_basenames[candidate]}"
            candidate = f"{stem}{collision_suffix}.{e}"
        else:
            used_basenames[candidate] = 1
        new_path = os.path.join(os.path.dirname(op), candidate)
        manifest_map[original_basename] = candidate
        sidecar_rename = None
        if r.get("ocr_sidecar"):
            sc_old = os.path.basename(r["ocr_sidecar"])
            stem = os.path.splitext(original_basename)[0]
            new_stem = os.path.splitext(candidate)[0]
            sc_new = sc_old.replace(stem, new_stem) if stem in sc_old else new_stem + ".md"
            sidecar_rename = {"old": r["ocr_sidecar"], "new": os.path.join(os.path.dirname(r["ocr_sidecar"]), sc_new)}
            sidecar_map[sc_old] = sc_new
        file_renames.append({
            "original_path": op,
            "new_basename": candidate,
            "new_path": new_path,
            "extracted": {"date": date_str, "doc_type": doc_type, "org": org, "page": page},
            "collision_suffix": collision_suffix,
            "sidecar_rename": sidecar_rename,
            "audit": {"date_source": date_src, "org_source": org_src, "doc_type_source": doc_src},
        })

    return {
        "patient_dir_rename": patient,
        "file_renames": file_renames,
        "ref_backfill": {
            "manifest_old_to_new": manifest_map,
            "sidecar_old_to_new": sidecar_map,
        },
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan-from", required=True, help="path to JSON array of OCR sidecar records")
    ap.add_argument("--current-dir", required=True, help="absolute path to current patient_dir (used for hash seed)")
    ap.add_argument("--dry-run", action="store_true", help="print plan, do not write")
    args = ap.parse_args()
    records = json.loads(Path(args.plan_from).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        print(json.dumps({"error": "input must be a JSON array"}), file=sys.stderr)
        return 1
    plan = build_rename_plan(records, args.current_dir)
    json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
