"""One-pass archive check. It reports; it never loops and never blocks the user.

Checks only things that are cheap and real:
  - required files exist and parse, container keys present
  - every source_ref / [[src:…]] anchor points at an existing sidecar line range
  - acute-finding verbatim text and lab raw values really appear in the cited sidecar
  - core facts (stage, driver variants, current regimen) are not dropped from the HTML summary
  - no real identity string from raw/_identity/ is left in any derived file (finish masks them first)
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
                        "addresses": "[住址]", "record_numbers": "[病案号]", "other": "[身份信息]"}
ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


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
                if len(v) >= 2:
                    merged.setdefault(k, set()).add(v)
    return merged


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
    total = 0
    for p in _derived_files(patient_dir):
        text = p.read_text(encoding="utf-8", errors="replace")
        new = text
        for value, ph in pairs:
            if value in new:
                total += new.count(value)
                new = new.replace(value, ph)
        for rx, ph in ((ID_RE, "[证件号]"), (PHONE_RE, "[电话]")):
            new, n = rx.subn(ph, new)
            total += n
        if new != text:
            if p.suffix == ".json":
                try:
                    json.loads(new)
                except ValueError:
                    continue                          # never corrupt a JSON file; check() will report it
            p.write_text(new, encoding="utf-8")
    return total


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

    # Identity leaks (after masking there should be none).
    ident = load_identity(patient_dir)
    values = [v for vs in ident.values() for v in vs]
    for p in _derived_files(patient_dir):
        text = p.read_text(encoding="utf-8", errors="replace")
        hit = [v for v in values if v in text]
        if hit:
            errors.append(f"{rel(patient_dir, p)} 里仍有真实身份信息（{len(hit)} 处）")

    return {"errors": errors, "warnings": warnings}
