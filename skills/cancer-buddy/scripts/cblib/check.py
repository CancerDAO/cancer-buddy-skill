"""One-pass archive check. It reports; it never loops and never blocks the user.

Checks only things that are cheap and real:
  - required files exist and parse, container keys present
  - every source_ref / [[src:…]] anchor points at an existing sidecar line range
  - acute-finding verbatim text and lab raw values really appear in the cited sidecar
  - core facts (stage, driver variants, current regimen) are not dropped from the HTML summary
  - no real identity string from raw/_identity/ is left in any derived file or file name (finish masks first)
  - dates bind to the transcript: an acute finding / timeline event dated by the report date, not the exam date
  - every imaging report is summarised in imaging_findings.json, line by labelled FINDINGS line
  - facts never cite a secondary (hand-compiled) source; lab flags use the fixed vocabulary
"""
import datetime as _dt
import json
import re
from pathlib import Path

from .common import load_json, write_json, read_frontmatter, iter_sidecars, rel, today

REQUIRED = {
    "profile.json": None,
    "patient_summary.json": "diagnosis",
    "acute_findings.json": "findings",
    "imaging_findings.json": "studies",
    "labs.json": "panels",
    "molecular.json": "variants",
    "treatment_lines.json": "episodes",
    "timeline.json": "events",
    "comorbidities.json": "medications",
    "readiness.json": "review_flags",
    "missing_items.json": "document_gaps",
    "source_inventory.json": "files",
}
REQUIRED_MD = ["case_text.md", "timeline.md", "review_summary.md"]
REF_RE = re.compile(r"^(?P<path>[^#\s]+\.md)(?:#L(?P<a>\d+)(?:-L?(?P<b>\d+))?)?$")
ANCHOR_RE = re.compile(r"\[\[src:([^\]\s]+)\]\]")
IDENTITY_PLACEHOLDER = {"names": "[姓名]", "id_numbers": "[证件号]", "phones": "[电话]",
                        "addresses": "[住址]", "record_numbers": "[病案号]", "order_numbers": "[单号]",
                        "dates_of_birth": "[出生日期]", "clinician_names": "[医生]", "other": "[身份信息]"}
# Pattern backstops. Letters count as edges: a hex digest is not an ID number.
ID_RE = re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])")
PHONE_RE = re.compile(r"(?<![0-9A-Za-z])1[3-9]\d{9}(?![0-9A-Za-z])")
_DATE = r"(?:\d{1,4}[./\-年]\s?\d{1,2}[./\-月]\s?\d{1,4}日?|\d{1,2}\.?\s+[A-Za-z]{3,9}\.?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})"
DOB_RE = re.compile(r"(?i)((?:\bDOB|\bD\.O\.B\.|date\s+of\s+birth|birth\s*date|\bborn|\bgeb\.|geburtsdatum|出生日期|出生年月|生日)"
                    r"[\s*:：/|]*(?:gender[\s*:：/|]*)?)" + _DATE)
URL_ID_RE = re.compile(r"(?i)\b(eorderid|orderid|accession|mrn|patientid)=([^\s&)\]|>…]+)")
NO_MASK_KEYS = {"sha256", "inputs_digest"}          # machine hashes: never rewrite
LAB_FLAGS = {"high", "low", "normal", "critical_high", "critical_low", "abnormal"}


def _norm(s: str) -> str:
    return re.sub(r"[\s　,，:：;；]+", "", str(s or ""))


# --- refs --------------------------------------------------------------------------

def _walk_refs(obj, where=""):
    """Yield (json_path, ref_string, row) for every source_ref(s) value."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("source_refs", "source_ref"):
                refs = v if isinstance(v, list) else [v]
                for r in refs:
                    if isinstance(r, str) and r:
                        yield f"{where}.{k}", r, obj
            else:
                yield from _walk_refs(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_refs(v, f"{where}[{i}]")


class _Lines:
    def __init__(self, patient_dir: Path):
        self.dir = patient_dir
        self.cache = {}

    def get(self, relpath):
        if relpath not in self.cache:
            p = self.dir / relpath
            self.cache[relpath] = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else None
        return self.cache[relpath]

    def resolve(self, ref: str):
        """Return (text of cited lines, error or None)."""
        if ref.startswith("conversation:"):
            return None, None
        m = REF_RE.match(ref)
        if not m:
            return None, f"引用格式不对：{ref}"
        lines = self.get(m.group("path"))
        if lines is None:
            return None, f"引用的转写稿不存在：{ref}"
        if not m.group("a"):
            return "\n".join(lines), None
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        if a < 1 or b < a or b > len(lines):
            return None, f"引用行号超出范围（文件共 {len(lines)} 行）：{ref}"
        lo, hi = max(0, a - 3), min(len(lines), b + 2)          # small tolerance around the range
        return "\n".join(lines[lo:hi]), None


# --- identity --------------------------------------------------------------------

def load_identity(patient_dir: Path) -> dict:
    merged = {}
    files = list((patient_dir / "raw" / "_identity").glob("*.json"))
    legacy = patient_dir / "raw" / "_identity.json"
    if legacy.exists():
        files.append(legacy)
    for f in files:
        data = load_json(f) or {}
        for k, vals in data.items():
            for v in vals if isinstance(vals, list) else [vals]:
                v = str(v or "").strip()
                if _usable_identity(v):
                    merged.setdefault(k, set()).add(v)
    return merged


def _id_checksum_ok(s: str) -> bool:
    """GB 11643 check digit, so an 18-digit run in a report number is not taken for an ID card."""
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    total = sum(int(c) * k for c, k in zip(s[:17], w))
    return "10X98765432"[total % 11] == s[17].upper()


def _mask_text(text: str, pairs) -> tuple:
    total = 0
    for rx, ph in pairs:
        text, n = rx.subn(ph, text)
        total += n
    hits = []
    text = ID_RE.sub(lambda m: (hits.append(1), "[证件号]")[1] if _id_checksum_ok(m.group(0)) else m.group(0), text)
    total += len(hits)
    text, n2 = PHONE_RE.subn("[电话]", text)
    text, n3 = DOB_RE.subn(lambda m: m.group(1) + "[出生日期]", text)
    text, n4 = URL_ID_RE.subn(lambda m: f"{m.group(1)}=[单号]", text)
    return text, total + n2 + n3 + n4


def _mask_json(obj, pairs, key=None):
    if key in NO_MASK_KEYS:
        return obj, 0
    if isinstance(obj, str):
        return _mask_text(obj, pairs)
    if isinstance(obj, list):
        out, n = [], 0
        for v in obj:
            v, k = _mask_json(v, pairs)
            out.append(v)
            n += k
        return out, n
    if isinstance(obj, dict):
        out, n = {}, 0
        for k, v in obj.items():
            v, c = _mask_json(v, pairs, k)
            out[k] = v
            n += c
        return out, n
    return obj, 0


def _usable_identity(v: str) -> bool:
    """Drop values that cannot identify anyone but would hit clinical text: "0000", "XX", "123"."""
    core = re.sub(r"[\s\-_/.:]", "", v)
    if len(core) < 2 or len(set(core.lower())) == 1:
        return False
    if core.isalpha() and core.isascii() and len(core) <= 2:   # "AT", "MD": initials/codes collide with words
        return False
    return not (core.isdigit() and len(core) < 5)


def _identity_re(value: str):
    """Match a whole identity token: an ASCII letter/digit edge must not touch another one.
    Stops a short record number such as "0000" matching inside ENST00000404276.6 or a longer number;
    CJK edges stay unbounded because Chinese text has no word separators."""
    pat = re.escape(value)
    if re.match(r"[A-Za-z0-9]", value[0]):
        pat = r"(?<![A-Za-z0-9])" + pat
    if re.match(r"[A-Za-z0-9]", value[-1]):
        pat += r"(?![A-Za-z0-9])"
    return re.compile(pat, re.IGNORECASE if len(value) >= 4 else 0)


def _derived_files(patient_dir: Path):
    out = list(iter_sidecars(patient_dir))
    for p in sorted(patient_dir.glob("*")):
        if p.is_file() and p.suffix in (".json", ".md", ".html"):
            out.append(p)
    for sub in ("case_summary_versions", "charts", "reports", ".work"):
        d = patient_dir / sub
        if d.exists():
            out += [p for p in d.rglob("*") if p.is_file() and p.suffix in (".json", ".md", ".html")
                    and "tasks" not in p.parts and "pages" not in p.parts]
    return out


def mask_identity(patient_dir) -> int:
    """Replace every known identity string (longest first) in derived files. Returns count replaced."""
    patient_dir = Path(patient_dir)
    ident = load_identity(patient_dir)
    pairs = sorted(((v, IDENTITY_PLACEHOLDER.get(k, "[身份信息]")) for k, vs in ident.items() for v in vs),
                   key=lambda x: -len(x[0]))
    pairs = [(_identity_re(v), ph) for v, ph in pairs]
    total = 0
    for p in _derived_files(patient_dir):
        text = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix == ".json":
            try:
                obj = json.loads(text)
            except ValueError:
                continue                              # never corrupt a JSON file; check() will report it
            obj, n = _mask_json(obj, pairs)
            if n:
                total += n
                p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            continue
        new, n = _mask_text(text, pairs)
        if new != text:
            total += n
            p.write_text(new, encoding="utf-8")
    return total


def mask_name(patient_dir, name: str) -> str:
    """Identity values out of a file name part (institution fields sometimes carry a physician's name)."""
    ident = load_identity(Path(patient_dir))
    for v in sorted((v for vs in ident.values() for v in vs), key=len, reverse=True):
        name = _identity_re(v).sub("", name)
    return name


_FINDINGS_START = re.compile(r"(?i)^\W*(findings|检查所见|影像所见|所见)\W*$")
_FINDINGS_END = re.compile(r"(?i)^\W*(impression|assessment|summary|plain-language|note from|conclusion|result|"
                           r"beurteilung|ergebnis|zusammenfassung|诊断意见|影像诊断|印象|结论|"
                           r"ordering provider|reading physician|study date)\b")
_LABELLED = re.compile(r"^\W{0,3}[A-Za-zÄÖÜäöü][A-Za-zÄÖÜäöü /,&\-]{1,40}:\s*\S")


def _findings_lines(text_lines) -> list:
    """Line numbers of 'Organ: description' lines inside a FINDINGS block (structure, not content)."""
    out, inside = [], False
    for i, line in enumerate(text_lines, 1):
        t = line.strip().strip("*#").strip()
        if _FINDINGS_START.match(t):
            inside = True
            continue
        if inside and _FINDINGS_END.match(t):
            inside = False
            continue
        if inside and _LABELLED.match(t):
            out.append(i)
    return out


def dob_flag(patient_dir) -> None:
    """Birth dates are masked before synthesis sees them, so the script flags differing written forms."""
    patient_dir = Path(patient_dir)
    forms = load_identity(patient_dir).get("dates_of_birth") or set()
    path = patient_dir / "readiness.json"
    r = load_json(path) or {}
    flags = [f for f in r.get("review_flags") or [] if f.get("id") != "RF-DOB"]
    if len(forms) > 1:
        flags.append({"id": "RF-DOB", "kind": "conflict", "severity": "yellow", "affected_field": "demographics.date_of_birth",
                      "values": [], "resolution_status": "unresolved",
                      "issue": f"不同报告上的出生日期有 {len(forms)} 种写法，日/月顺序可能不一致，请对照证件核对"
                               "（具体写法只记在本机受控的 raw/_identity/ 里）。"})
    r["review_flags"] = flags
    write_json(path, r)


# --- freshness ----------------------------------------------------------------------

STALE_DAYS = 14


def freshness(patient_dir) -> None:
    """Latest document date and its age are computed here, not by the model."""
    patient_dir = Path(patient_dir)
    dates = []
    for p in iter_sidecars(patient_dir):
        meta, _ = read_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        d = (meta.get("doc_date") or "")[:10]
        if meta.get("read") != "conversation" and not rel(patient_dir, p).startswith("99_") and re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            dates.append(d)
    path = patient_dir / "readiness.json"
    r = load_json(path) or {}
    r.setdefault("review_flags", [])
    r["warnings"] = [w for w in r.get("warnings") or [] if not str(w).startswith("本档案最新一份资料")]
    r["as_of_run_date"] = today()
    if dates:
        latest = max(dates)
        days = (_dt.date.fromisoformat(today()) - _dt.date.fromisoformat(latest)).days
        r["latest_source_date"], r["days_since_latest"] = latest, days
        if days > STALE_DAYS:
            r["warnings"].append(f"本档案最新一份资料的日期是 {latest}，距今 {days} 天。之后如果做过新的检查或看过门诊，请补充进来。")
    else:
        r["latest_source_date"], r["days_since_latest"] = None, None
    write_json(path, r)


# --- check ------------------------------------------------------------------------------

def check(patient_dir) -> dict:
    patient_dir = Path(patient_dir)
    errors, warnings = [], []
    data = {}
    for name, key in REQUIRED.items():
        p = patient_dir / name
        if not p.exists():
            errors.append(f"缺少 {name}")
            continue
        try:
            data[name] = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            errors.append(f"{name} 不是合法 JSON：{e}")
            continue
        if key and key not in data[name]:
            errors.append(f"{name} 缺少顶层键 {key}")
    for name in REQUIRED_MD:
        if not (patient_dir / name).exists():
            errors.append(f"缺少 {name}")

    prof = data.get("profile.json") or {}
    if prof and prof.get("patient_code") != patient_dir.name:
        errors.append(f"profile.json 的 patient_code（{prof.get('patient_code')}）与目录名不一致")
    if prof and not prof.get("locale"):
        warnings.append("profile.json 没有 locale")

    lines = _Lines(patient_dir)
    for name, obj in data.items():
        if name == "source_inventory.json":
            continue
        for where, ref, _ in _walk_refs(obj):
            _, err = lines.resolve(ref)
            if err:
                errors.append(f"{name}{where}: {err}")
    for name in ("case_text.md", "timeline.md"):
        p = patient_dir / name
        if p.exists():
            for ref in ANCHOR_RE.findall(p.read_text(encoding="utf-8")):
                _, err = lines.resolve(ref)
                if err:
                    errors.append(f"{name}: {err}")

    # Acute findings: the words must be the report's own words.
    for i, f in enumerate((data.get("acute_findings.json") or {}).get("findings") or []):
        if f.get("verbatim_is_translation"):
            continue
        text, err = lines.resolve(f.get("source_ref") or "")
        if err or not f.get("source_ref"):
            continue                                  # already reported above / missing ref
        if text is not None and _norm(f.get("verbatim_text")) not in _norm(text):
            errors.append(f"acute_findings.json findings[{i}]: 原文“{f.get('verbatim_text')}”不在 {f.get('source_ref')} 里；"
                          "要么照抄原句，要么标 verbatim_is_translation")

    # Lab values: every recorded number must be traceable.
    for panel in (data.get("labs.json") or {}).get("panels") or []:
        for v in panel.get("values") or []:
            shown = v.get("raw_value") if v.get("raw_value") not in (None, "") else v.get("value")
            if shown in (None, ""):
                continue
            refs = [r for r in v.get("source_refs") or [] if not r.startswith("conversation:")]
            texts = [t for t, _ in (lines.resolve(r) for r in refs) if t is not None]
            if texts and not any(_norm(shown) in _norm(t) for t in texts):
                errors.append(f"labs.json {panel.get('analyte')} {v.get('date')}: 数值 {shown} 不在所引用的行里（{', '.join(refs)}）")

    # Lab flags: one fixed vocabulary, so "high/low" is machine-readable (the verbatim stays in report_flag).
    for panel in (data.get("labs.json") or {}).get("panels") or []:
        for v in panel.get("values") or []:
            f = v.get("flag_normalized")
            if f is not None and f not in LAB_FLAGS:
                errors.append(f"labs.json {panel.get('analyte')} {v.get('date')}: flag_normalized “{f}” 不在 {sorted(LAB_FLAGS)} 里")

    metas = {}
    for sp in iter_sidecars(patient_dir):
        metas[rel(patient_dir, sp)] = read_frontmatter(sp.read_text(encoding="utf-8", errors="replace"))[0]

    def cited_meta(ref):
        m = REF_RE.match(ref or "")
        return metas.get(m.group("path")) if m else None

    # Dates: an exam is dated by when it was done, not when the report was signed.
    for i, f in enumerate((data.get("acute_findings.json") or {}).get("findings") or []):
        m = cited_meta(f.get("source_ref"))
        if m and m.get("exam_date") and f.get("exam_date") != m["exam_date"]:
            errors.append(f"acute_findings.json findings[{i}]: exam_date 应为检查日 {m['exam_date']}"
                          f"（转写稿 exam_date），现为 {f.get('exam_date')}")
    for i, ev in enumerate((data.get("timeline.json") or {}).get("events") or []):
        ms = [cited_meta(r) for r in ev.get("source_refs") or []]
        ms = [m for m in ms if m]
        if ms and all(m.get("exam_date") and m.get("doc_date") and m["exam_date"] != m["doc_date"]
                      and ev.get("date") == m["doc_date"] for m in ms):
            errors.append(f"timeline.json events[{i}]: 日期 {ev.get('date')} 是报告日，检查日是 {ms[0]['exam_date']}")

    # Secondary material (hand-made lists, summaries) may point at gaps, never back a fact.
    secondary = {k for k, m in metas.items() if str(m.get("evidence") or "").lower() == "secondary"}
    if secondary:
        for name, obj in data.items():
            if name in ("source_inventory.json", "missing_items.json"):
                continue
            for where, ref, _ in _walk_refs(obj):
                m = REF_RE.match(ref)
                if m and m.group("path") in secondary:
                    errors.append(f"{name}{where}: 引用了二手整理材料 {m.group('path')}；它只能用来列缺失资料，不能作为事实出处")
        for name in ("case_text.md", "timeline.md"):
            q = patient_dir / name
            if q.exists():
                for ref in ANCHOR_RE.findall(q.read_text(encoding="utf-8")):
                    m = REF_RE.match(ref)
                    if m and m.group("path") in secondary:
                        errors.append(f"{name}: 引用了二手整理材料 {m.group('path')}")

    # Imaging: every report summarised; every labelled FINDINGS line (organ system) covered by a cited range.
    covered = {}
    for st in (data.get("imaging_findings.json") or {}).get("studies") or []:
        refs = list(st.get("source_refs") or [])
        for fnd in st.get("findings") or []:
            refs += fnd.get("source_refs") or ([fnd["source_ref"]] if fnd.get("source_ref") else [])
        for r in refs:
            m = REF_RE.match(r or "")
            if m:
                a = int(m.group("a") or 1)
                b = int(m.group("b") or m.group("a") or 10 ** 6)
                covered.setdefault(m.group("path"), []).append((a, b))
    if "imaging_findings.json" in data:
        for path, m in metas.items():
            if not path.startswith("05_") or str(m.get("evidence") or "").lower() == "secondary":
                continue
            if path not in covered:
                errors.append(f"imaging_findings.json 没有收录影像报告 {path}")
                continue
            for ln in _findings_lines(lines.get(path) or []):
                if not any(a <= ln <= b for a, b in covered[path]):
                    errors.append(f"imaging_findings.json 漏了 {path}#L{ln} 这一行所见（{(lines.get(path) or [''])[ln - 1][:40]}）")

    # Every source should have produced a transcript.
    for f in (data.get("source_inventory.json") or {}).get("files") or []:
        if f.get("kind") == "unsupported":
            warnings.append(f"{f['source_id']}（{f.get('raw_path')}）格式无法读取，原件已保存在 raw/")
        elif not f.get("sidecar_paths") and not f.get("discarded") and f.get("contract") == "v2":
            warnings.append(f"{f['source_id']} 还没有转写稿")

    # Core facts must survive into the patient-facing summary.
    html_path = patient_dir / "病情简要总结.html"
    if html_path.exists():
        html = _norm(html_path.read_text(encoding="utf-8"))
        ps = data.get("patient_summary.json") or {}
        must = []
        stage = (ps.get("diagnosis") or {}).get("stage")
        if isinstance(stage, str) and stage:
            must.append(("分期", stage))
        for var in ((data.get("molecular.json") or {}).get("variants") or [])[:10]:
            if var.get("gene"):
                must.append(("基因", var["gene"]))
        regimen = ((prof.get("latest_status") or {}).get("regimen"))
        if isinstance(regimen, str) and regimen:
            must.append(("当前方案", regimen))
        import html as _html
        for label, value in must:
            # An uncertain read renders as prose around the literal, so check each piece on its own.
            pieces = [p for p in re.split(r"\{\?([^|}]*)(?:\|[^}]*)?\}", value) if _norm(p)]
            lost = [p for p in pieces if _norm(_html.escape(p)) not in html and _norm(p) not in html]
            if lost:
                errors.append(f"病情简要总结.html 丢了{label}：{value}")

    # Identity leaks (after masking there should be none), in contents and in file names.
    ident = load_identity(patient_dir)
    patterns = [_identity_re(v) for vs in ident.values() for v in vs]
    for p in _derived_files(patient_dir):
        text = p.read_text(encoding="utf-8", errors="replace")
        hit = [rx for rx in patterns if rx.search(text)]
        if hit:
            errors.append(f"{rel(patient_dir, p)} 里仍有真实身份信息（{len(hit)} 处）")
        if any(rx.search(rel(patient_dir, p)) for rx in patterns):
            errors.append(f"文件名里有真实身份信息：{rel(patient_dir, p)}")

    # Hashes are bookkeeping; a rewritten digest breaks provenance.
    for f in (data.get("source_inventory.json") or {}).get("files") or []:
        if f.get("sha256") and not re.fullmatch(r"[0-9a-f]{64}", str(f["sha256"])):
            errors.append(f"source_inventory.json {f.get('source_id')}: sha256 不是 64 位十六进制（{f['sha256']}）")

    return {"errors": errors, "warnings": warnings}
