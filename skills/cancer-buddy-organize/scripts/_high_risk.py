#!/usr/bin/env python3
"""_high_risk.py — the ONE authority that decides whether a field label is high-risk.

WHY THIS FILE EXISTS (fix spec B1)
    Two places need the same answer to "must this field be independently re-read?":

      * `plan_second_read.py`  builds the 段 1.5 queue from it (the NUMERATOR's input);
      * `validate_structured_outputs.py` reconciles `high_risk_fields[]` against it
        (the DENOMINATOR: a row that declares fewer high-risk fields than the page's
        own frontmatter implies is an ERROR, not a smaller workload).

    While each script carried its own word list they drifted, and the drift was
    invisible: the planner queued a field the validator did not require, or — worse —
    the validator accepted a manifest that had quietly dropped `WBC` because its own
    copy of the list only knew 「白细胞计数」. A denominator that each consumer can
    redefine is not a denominator.

WHY A WORD LIST IS THE RIGHT INSTRUMENT HERE
    Elsewhere in this skill, judgment belongs in a prompt, never in a keyword table.
    This is the documented exception, and the reason is structural rather than stylistic:
    the question is not "what does this field mean" (judgment) but "which cells are in
    the set that MUST be checked" (a coverage denominator). A model that computes its own
    denominator can shrink it to zero and report 100% coverage. Missing a keyword here
    costs one extra second read; the self-reported `high_risk[]`, the `uncertain[]` arm
    and the cross-channel `discrepancy[]` arm all still run alongside it.

    Consequently this table is deliberately OVER-inclusive at the margins. `PD-L1`
    classifying as `response_wording` (because of the `pd` token) is a correct outcome:
    an extra re-read is the cheap error.

CONTRACT
    classify_label(label) -> str | None   the high-risk CLASS, or None
    is_high_risk(label)   -> bool
    HIGH_RISK_CLASSES     -> tuple[str, ...]  the 9 general + 4 oncology classes

    Source of truth for the class list and what each covers:
    `references/high-risk-fields.md` §1.1 (general 9) and §1.2 (oncology pack, 4).
"""
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "HIGH_RISK_CLASSES",
    "GENERAL_CLASSES",
    "ONCOLOGY_CLASSES",
    "classify_label",
    "is_high_risk",
    "classify_high_risk",
    "BARCODE_HINTS",
]

# §1.1 — always in force, any disease domain, any modality.
GENERAL_CLASSES = (
    "identifier", "date", "drug_name", "dose", "frequency",
    "lab_value", "unit", "reference_range", "accession",
)
# §1.2 — the oncology pack. FOUR classes: `response_wording` is one of them (the verbatim
# CR/PR/SD/PD string a report prints), which is why high-risk-fields.md says 4, not 3.
ONCOLOGY_CLASSES = ("stage", "variant", "vaf", "response_wording")

HIGH_RISK_CLASSES = GENERAL_CLASSES + ONCOLOGY_CLASSES

# --------------------------------------------------------------------------- #
# Matching, in two flavours, because one flavour cannot serve both faces.
#
#   SUBSTRING  — CJK terms and long unambiguous Latin words. CJK has no word boundary, so
#                「白细胞计数」 inside 「白细胞计数(WBC)」 has to match as a substring.
#
#   TOKEN      — short Latin abbreviations (WBC / HGB / PLT / CEA / PT / CR …). These MUST
#                NOT be substring-matched: `ref` is a substring of `report`, `ca` of
#                `calcium` and of `accession`, `pt` of `patient`. A three-letter substring
#                arm turns the table into noise. Tokens are compared against the label's
#                alphanumeric tokens AND against its fully squashed form, so `CA19-9`,
#                `CA 19-9` and `CA19_9` all reach `ca199`.
# --------------------------------------------------------------------------- #

_SUBSTRING: dict[str, tuple[str, ...]] = {
    "accession": ("检验号", "标本号", "样本号", "条码", "条形码", "报告编号", "报告号",
                  "病理号", "申请单号", "送检号",
                  "accession", "specimen", "barcode", "sample id", "sample no"),
    "identifier": ("姓名", "住院号", "门诊号", "病案号", "就诊卡", "身份证", "患者编号",
                   "床号", "病历号", "医保号",
                   "patient id", "patient_id", "patient name", "medical record"),
    "reference_range": ("参考", "范围", "区间", "上限", "下限", "正常值",
                        "reference", "range", "normal value"),
    "unit": ("单位", "10^9", "10*9", "g/l", "ng/ml", "u/l", "mmol", "umol", "μ",
             "mg/dl", "iu/l", "pg/ml"),
    "date": ("日期", "时间", "入院", "出院", "采集", "报告日", "手术日", "给药",
             "date", "collected", "reported", "admission", "discharge", "sampling"),
    "vaf": ("丰度", "等位基因频率", "突变频率", "allele frequency", "变异频率"),
    # NOTE (fix spec C1): bare "c." / "p." are NOT in this list. They used to be, and
    # they turned every dotted Latin abbreviation into a variant: `W.B.C.` ends in `c.`
    # and `C.E.A` contains `c.`, so two of the most common lab labels in the corpus
    # classified as `variant` and never reached the haematology/tumour-marker arm. HGVS
    # prefixes are matched by _CLASS_RE["variant"] instead, which requires the coordinate
    # that actually follows a real `c.`/`p.`.
    "variant": ("突变", "变异", "融合", "基因", "拷贝数", "扩增", "缺失", "重排",
                "hgvs", "variant", "mutation", "fusion", "gene",
                "amplification", "rearrangement"),
    "stage": ("分期", "tnm", "ajcc", "figo", "stage", "分级", "grade"),
    "response_wording": ("评效", "疗效", "完全缓解", "部分缓解", "疾病稳定", "疾病进展",
                         "缓解", "进展", "response", "recist"),
    "dose": ("剂量", "用量", "mg/m", "g/m", "dose", "dosage", "dosing",
             "单次量", "累积量", "投与量", "给药量", "总量"),
    "frequency": ("频次", "频率", "每日", "每周", "隔日", "每疗程", "周期", "睡前",
                  "frequency", "schedule", "interval"),
    "drug_name": ("药物", "药品", "方案", "用药", "化疗", "靶向", "免疫", "通用名",
                  "商品名", "替尼", "单抗", "紫杉", "他赛", "嘧啶", "drug", "regimen",
                  "medication"),
    # The CJK analyte arm mirrors the Latin abbreviation arm below it: a Chinese lab
    # report prints 「血清钠」 where an English one prints `Na`, and a denominator that
    # knows one face but not the other is a denominator with a language hole in it.
    "lab_value": ("检验", "检测", "结果", "数值", "计数", "浓度", "指标", "值",
                  "血红蛋白", "白细胞", "红细胞", "血小板", "中性粒", "淋巴细胞",
                  # Regional/orthographic faces of the two commonest CBC analytes.
                  # 「白血球」/「血色素」 are the Taiwanese/older-mainland prints of
                  # 「白细胞」/「血红蛋白」; `leukocyte`/`h(a)emoglobin` are the spelled-out
                  # Latin faces that the short-token arm (`wbc`, `hgb`) cannot reach.
                  "白血球", "血色素", "leukocyte", "hemoglobin", "haemoglobin",
                  "单核", "嗜酸", "嗜碱", "网织",
                  "转氨酶", "胆红素", "白蛋白", "球蛋白", "总蛋白",
                  "肌酐", "尿素", "尿酸", "血糖", "糖化",
                  "钾", "钠", "氯", "钙", "镁", "磷", "铁蛋白",
                  "淀粉酶", "脂肪酶", "乳酸", "胆固醇", "甘油三酯",
                  "凝血", "纤维蛋白", "二聚体", "降钙素原", "反应蛋白", "血沉",
                  "癌胚抗原", "甲胎蛋白", "糖类抗原", "抗原", "抗体", "激素",
                  "肌钙蛋白", "利钠肽",
                  "value", "result", "count", "level", "titer", "titre"),
}

_TOKEN: dict[str, tuple[str, ...]] = {
    "accession": ("accession", "specimen", "barcode", "labno", "labid", "reportno"),
    "identifier": ("mrn", "name", "id", "idcard", "nhi", "upi"),
    "reference_range": ("ref", "refrange", "range", "reference", "normalrange", "ri"),
    "unit": ("unit", "units", "uom"),
    "date": ("date", "dob", "dos", "datetime"),
    "vaf": ("vaf", "af", "maf", "vf"),
    "variant": ("hgvs", "cnv", "snv", "indel", "tmb", "msi", "hrd", "her2", "egfr",
                "kras", "nras", "braf", "alk", "ros1", "ret", "met", "pik3ca", "tp53",
                "brca1", "brca2", "ntrk", "fgfr", "idh1", "idh2", "kit", "pdgfra"),
    "stage": ("ct", "cn", "cm", "pt", "pn", "pm", "ypt", "ypn", "ypm", "tnm", "ajcc",
              "figo", "stage"),
    "response_wording": ("cr", "pr", "sd", "pd", "recist", "orr", "dcr", "ncr", "pmr"),
    "dose": ("dose", "dosage", "mg", "mgm2", "gm2", "auc", "bsa"),
    "frequency": ("qd", "bid", "tid", "qid", "qw", "q2w", "q3w", "q4w", "q3d", "qod",
                  "prn", "qhs", "q6h", "q8h", "q12h"),  # `hs` alone is ambiguous (hs-cTnT = high-sensitivity assay); bedtime dosing is written qhs / 睡前
    "drug_name": ("drug", "regimen", "medication", "rx"),
    # The clinical-chemistry / haematology / tumour-marker abbreviations. This arm is what
    # B1 adds: a run whose frontmatter says `WBC` rather than 「白细胞计数」 used to
    # classify to None on every row, so the denominator was empty and the reconciliation
    # gate had nothing to compare against.
    "lab_value": (
        # haematology
        "wbc", "rbc", "hgb", "hb", "hct", "plt", "mcv", "mch", "mchc", "rdw", "mpv",
        "neut", "neu", "lymph", "lym", "mono", "eos", "baso", "anc", "retic",
        # chemistry / liver / renal
        "alt", "ast", "alp", "ggt", "ldh", "tbil", "dbil", "ibil", "tp", "alb", "glb",
        "ag", "bun", "urea", "crea", "scr", "egfr2", "ua", "glu", "hba1c", "chol",
        "tg", "hdl", "ldl", "ck", "ckmb", "amy", "lps", "tsh", "ft3", "ft4",
        # electrolytes
        "na", "cl", "ca", "mg2", "p", "k",
        # inflammation / coagulation / cardiac
        "crp", "hscrp", "esr", "pct", "il6", "aptt", "inr", "fib", "dd", "ddimer",
        "tnt", "tni", "ctni", "ctnt", "hstni", "hstnt", "bnp", "ntprobnp", "fdp",
        # tumour markers
        "cea", "afp", "psa", "fpsa", "ca125", "ca153", "ca199", "ca242", "ca724",
        "ca50", "cyfra211", "cyfra", "nse", "scc", "he4", "proGRP", "progrp", "b2mg",
        "hcg", "bhcg", "tpsa", "sccag",
    ),
}

# Class evaluation order. Deterministic and load-bearing: `WBC ref` must land in
# `reference_range` (it is the printed interval, and mis-reading it inverts the bounds)
# rather than `lab_value`, so the narrower classes are asked first and `lab_value` — whose
# 「值」/`value`/`result` substrings are the broadest in the table — is asked last.
# `dose` is asked BEFORE `date` (fix spec C1). 「给药」 is in the date list because
# 「给药日期」/「给药时间」 are dates; but 「给药剂量」 is a DOSE, and with `date` first the
# 「给药」 substring swallowed it — the single most safety-critical field class in the
# table was being filed as a date. Asking `dose` first restores 「给药剂量」 → dose while
# leaving 「给药日期」 → date untouched (it carries no dose keyword).
_ORDER = (
    "accession", "identifier", "reference_range", "unit",
    "vaf", "variant", "stage", "response_wording",
    "dose", "date", "frequency", "drug_name", "lab_value",
)

BARCODE_HINTS = ("条码", "条形码", "barcode", "qr")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SQUASH_RE = re.compile(r"[^a-z0-9]+")

# Invisible characters that OCR and copy-paste from hospital PDFs sprinkle through
# labels. They carry no glyph, so a human proof-reading 「剂​量」 sees 「剂量」 and a
# substring table sees neither. Stripping them is not cosmetic: a zero-width space
# between 「剂」 and 「量」 silently emptied the high-risk denominator for that page.
#   U+200B ZERO WIDTH SPACE      U+200C ZERO WIDTH NON-JOINER
#   U+200D ZERO WIDTH JOINER     U+FEFF ZERO WIDTH NO-BREAK SPACE / BOM
#   U+2060 WORD JOINER           U+00AD SOFT HYPHEN
#   U+200E/U+200F LRM/RLM        U+202A..U+202E bidi embedding/override
#   U+2066..U+2069 bidi isolates
_ZERO_WIDTH = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060, 0x00AD, 0x200E, 0x200F]
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A)),
    None,
)


def _normalize(text: str) -> str:
    """NFKC-fold, strip zero-width/bidi marks, lowercase, collapse whitespace.

    NFKC is what makes the fullwidth face reachable: a scanner that emits 「Ｗ Ｂ Ｃ」
    (U+FF37 U+FF22 U+FF23) or 「Ｄｏｓｅ」 is printing the same label as `WBC` / `Dose`,
    but byte-wise they share nothing, so every fullwidth page classified to None and
    dropped out of the denominator entirely. NFKC also folds 「（」→`(`, 「－」→`-`,
    U+00B5 MICRO SIGN → U+03BC GREEK SMALL MU, and ligatures — all faces this table
    would otherwise need a second spelling for.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return " ".join(folded.lower().split())


# Both tables are normalized at import with the SAME function the probe goes through.
# Normalizing one side only is the classic half-fix: NFKC turns a probe's U+00B5 into
# U+03BC while a table entry typed as U+00B5 stays put, and the two never meet.
_SUBSTRING = {k: tuple(_normalize(w) for w in v) for k, v in _SUBSTRING.items()}
_TOKEN = {k: tuple(_normalize(w) for w in v) for k, v in _TOKEN.items()}

# Shape-matched classes — the cases a word list structurally cannot express.
_CLASS_RE: dict[str, re.Pattern[str]] = {
    # HGVS coordinate prefixes. A real `c.`/`p.` is followed by a position (`c.2573T>G`,
    # `p.*757`) or, for protein changes, a one-to-three-letter residue then a position
    # (`p.L858R`, `p.Leu858Arg`). Requiring what follows is what keeps `W.B.C.` and
    # `C.E.A` — which end in / contain a bare `c.` — out of the variant class.
    "variant": re.compile(r"(?<![a-z0-9])[cp]\.\s*(?:[\d*]|[a-z]{1,3}\d)"),
    # TNM printed as one run-together string: `cT3N1M0`, `ypT2`, `T4`, `cTX`. There is no
    # word to look for — the class lives in the shape — and a mis-read digit here moves
    # the patient a whole stage. Anchored at the start of the label (fix spec C1
    # `^[cyp]*T[0-4X]`), which is where a TNM string is printed; anchoring is also what
    # keeps the thyroid analytes out, since `FT3`/`FT4`/`TT4` never start with the `T`.
    # `TP53` / `TSH` / `TG` / `cTnI` do not match either: the character after the `T`
    # must be a stage digit or `X`, and `[cyp]*` cannot consume the `T` itself.
    "stage": re.compile(r"^[cyp]*t[0-4x]"),
}


def _faces(label: str) -> tuple[str, frozenset[str], str]:
    """(substring face, token set, squashed face) — all NFKC-folded and lowercase."""
    probe = _normalize(label)
    tokens = frozenset(_TOKEN_RE.findall(probe))
    squashed = _SQUASH_RE.sub("", probe)
    return probe, tokens, squashed


def classify_label(label: object) -> str | None:
    """Return the high-risk CLASS this label falls in, or None if it is not high-risk.

    Deterministic, total, and side-effect free: the same label always yields the same
    class, in every consumer, for every run. That property is the point — the validator
    recomputes this set from the archive's own frontmatter and compares it with what the
    manifest claims, and a comparison against a non-deterministic function proves nothing.
    """
    if not isinstance(label, str):
        return None
    probe, tokens, squashed = _faces(label)
    if not probe:
        return None
    for cls in _ORDER:
        for word in _SUBSTRING.get(cls, ()):
            if word in probe:
                return cls
        shape = _CLASS_RE.get(cls)
        if shape is not None and shape.search(probe):
            return cls
        toks = _TOKEN.get(cls, ())
        if toks:
            lowered = tuple(t.lower() for t in toks)
            if tokens.intersection(lowered) or (squashed and squashed in lowered):
                return cls
    return None


def is_high_risk(label: object) -> bool:
    """True when this label is in the high-risk denominator."""
    return classify_label(label) is not None


# Historical name used by plan_second_read.py before this module existed. Kept so an
# out-of-tree caller does not break; new code calls classify_label.
classify_high_risk = classify_label
