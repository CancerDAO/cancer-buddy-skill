"""Shared helpers for the deterministic contract gates (G1/G2/G3).

stdlib-only by contract: gates must run on any host (platform CI, CLI, sandbox)
without pip installs. No LLM calls here — gates verify model output, they never
produce it.
"""
import json
import re
import unicodedata
from pathlib import Path

REVIEW_FLAG = "needs_human_review"

# Header keys a Phase-1 sidecar may use for the report type. Order matters: first hit wins.
# 真实档案回灌发现的形态: 报告类型(s000675)/文档类型(s000674)/检验项目(s000672,同批第4处
# 串位正是靠它声明的)。"检验项目"要求冒号紧随,表格列头"| 检验项目 |"无冒号不会误命中。
REPORT_TYPE_KEYS = ("报告类型", "document_title", "document_type", "report_type",
                    "报告名称", "文档类型", "检验项目")


def canon(text):
    """NFKC-normalize and strip everything except CJK + ASCII alphanumerics, lowercased.

    This is deliberately aggressive: type matching must survive full/half width,
    color markers like （黄）, spacing and punctuation differences.
    """
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return "".join(ch for ch in text if ch.isalnum() or "一" <= ch <= "鿿")


def strip_annotations(value):
    """Cut trailing sidecar annotations: source_span/engine/confidence parentheticals."""
    value = re.split(r"[（(]\s*source_span", value)[0]
    value = re.split(r"[；;]\s*(?:engine|confidence|review_status)", value)[0]
    # leading color markers e.g. （黄）/(紫) are kept — canon() removes the parens anyway.
    return value.strip()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def load_alias_groups(refs_dir):
    data = read_json(Path(refs_dir) / "report-type-aliases.json") or {}
    groups = []
    for group in data.get("groups", []):
        keywords = [canon(k) for k in group.get("keywords", []) if canon(k)]
        if keywords:
            groups.append({"id": str(group.get("id", "")), "keywords": keywords})
    return groups


def alias_group_ids(text_canon, groups):
    return {g["id"] for g in groups if any(k in text_canon for k in g["keywords"])}


# Words that name the *container*, not the report type. A declaration made only of
# these (e.g. `document_type: laboratory_report_image`) is no type claim at all —
# verified against real data where treating them as types produced false violations.
GENERIC_TYPE_WORDS = (
    "laboratory", "report", "image", "medical", "document", "clinical", "record",
    "file", "scan", "photo", "page", "检验报告单", "检验报告", "报告单", "报告",
    "记录单", "记录", "单据", "影像", "照片", "图片", "化验单", "检查单", "检验单",
)


def is_generic_type(value):
    残 = canon(value)
    for word in GENERIC_TYPE_WORDS:
        残 = 残.replace(canon(word), "")
    return len(残) == 0


def report_type_from_sidecar(text):
    """Extract the report-type declaration from a sidecar markdown body, or None.

    Scans every declaration line and returns the first non-generic one; a file
    whose only declarations are generic container words has made no type claim.
    """
    for line in text.splitlines()[:120]:
        for key in REPORT_TYPE_KEYS:
            m = re.search(rf"{re.escape(key)}\s*[:：]\s*(.+)", line)
            if m:
                value = strip_annotations(m.group(1))
                # drop generic wrapper words that precede the actual type
                value = re.sub(r"^检验报告单\s*[／/|，,]?\s*", "", value)
                if canon(value) and not is_generic_type(value):
                    return value
    return None


def claimed_type_from_filename(name):
    """`2023-01-05_凝血功能筛查_北京肿瘤医院_来源s000675.md` → `凝血功能筛查` (or None)."""
    m = re.match(r"^(?:\d{4}-\d{2}-\d{2}|unknown-date)_([^_]+)_", name)
    return m.group(1) if m else None


def numeric_token(value):
    """First numeric token of a value string ('67.90 U/ml' → '67.90'), or None."""
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(value or ""))
    return m.group(0) if m else None


def value_locatable(value, haystack):
    """Verbatim-locate a candidate value in text; returns the matching lines.

    Numeric values get digit boundaries so 67.2 can never match inside 167.28.
    Any residue beyond the number (unit, date rest, qualifier) must also appear
    on the line when at least one line carries it — '67.90 U/ml' prefers lines
    that contain both 67.90 and U/ml. Non-numeric values match canon-substring.
    """
    raw = str(value or "")
    number = numeric_token(raw)
    if number is None:
        needle = canon(raw)
        return [l for l in haystack.splitlines() if needle and needle in canon(l)] if needle else []
    pattern = re.compile(rf"(?<![0-9.]){re.escape(number)}(?![0-9])")
    lines = [l for l in haystack.splitlines() if pattern.search(unicodedata.normalize("NFKC", l))]
    residue = canon(re.sub(re.escape(number), "", raw, count=1))
    if residue:
        with_residue = [l for l in lines if residue in canon(l)]
        if with_residue:
            lines = with_residue
    return lines


def visible_accession_tail(token):
    """Trailing visible digit run of a (possibly redacted) accession token.

    Redaction shapes are NOT uniform across sidecars (observed in one batch:
    `23*****017`, `ACCESSION_SUFFIX_8016`, `******8018`, `2301****13`, fully
    masked). We therefore never assume a fixed width — just take the trailing
    digits that are actually visible.
    """
    m = re.search(r"(\d+)\s*$", str(token or "").strip().strip("]`）)"))
    return m.group(1) if m else ""


def find_labeled(text, labels, pattern):
    """First regex match following any of the given labels in text, or None."""
    for line in text.splitlines():
        norm = unicodedata.normalize("NFKC", line)
        for label in labels:
            idx = norm.find(label)
            if idx >= 0:
                m = re.search(pattern, norm[idx + len(label):])
                if m:
                    return m.group(0)
    return None


def accession_token(text):
    for line in text.splitlines():
        norm = unicodedata.normalize("NFKC", line)
        m = re.search(r"检验编号[^:：]*[:：]\s*([^\s|，,；;（(]+)", norm)
        if m:
            return m.group(1)
        m = re.search(r"ACCESSION[_A-Z]*[:：\s]*([0-9*]+)", norm)
        if m:
            return m.group(1)
    return None


TS_PATTERN = r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"


def sampled_at(text):
    return find_labeled(text, ("采样时间", "采集时间", "collected_at"), TS_PATTERN)


def reported_at(text):
    return find_labeled(text, ("报告时间", "reported_at"), TS_PATTERN)
