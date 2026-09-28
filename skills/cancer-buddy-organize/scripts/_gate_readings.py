"""_gate_readings.py — ORG-P1-02 bindings of the validator (phase2 §3, §5.7).

A token masks only its own span: a text field (diagnosis primary / histology / stage, an episode's regimen)
whose reading is uncertain keeps its literal + its OWN `[OCR_UNCERTAIN:U-nnn]` token and lists the other
readings in `alt_readings[]` — never a null that a token elsewhere on the line caused, never a reading promoted
into the value. Checked mechanically:

  ERROR  an alt_readings item whose field is null (blanked instead of literal + token), whose field does not carry
         the item's token, whose token is not on the line its source_ref cites, or whose field is not a text field
         of that block;
  ERROR  profile.summary.one_line_condition leaves out diagnosis.primary (a non-null primary must appear, token-free;
         a null primary is written 诊断资料缺失 / 资料缺失);
  WARN   diagnosis.primary set without diagnosis_basis (the source ladder is judged in phase2 §5.7);
  WARN   a sidecar's second-read table read a diagnosis consistently (diagnosis_text 是) while diagnosis.primary is null;
  WARN   a stage / diagnosis read consistently in a sidecar appears in no structured field (readiness completeness hint);
  ERROR  an acute finding quoting a damaged text-layer run (the sidecar's `## 文本层字形异常` block) without the recomputed
         verbatim_text_search (acute-findings.md §2.5).

The source ladder itself (pathology > discharge/clinic > order/imaging indication > NGS clinical box > self-report) is
judgment and lives in the phase2 prompt, not here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TOKEN_RE = re.compile(r"\[OCR_UNCERTAIN:(U-\d{3,})\]")
ALT_FIELDS = {"diagnosis": ("primary", "histology", "stage"), "episode": ("regimen",)}
MISSING_DIAGNOSIS = "资料缺失"


def _strip(s: str) -> str:
    return TOKEN_RE.sub("", s).strip()


def _cited_lines(patient_dir: Path, ref: str) -> list[str]:
    path, _, frag = (ref or "").partition("#")
    p = patient_dir / path
    if not path or not p.is_file():
        return []
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    m = re.match(r"L(\d+)(?:-L(\d+))?$", frag)
    if not m:
        return lines
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    return lines[a - 1:b]


def alt_reading_problems(patient_dir: Path, block: dict, kind: str, where: str) -> list[str]:
    out = []
    items = block.get("alt_readings")
    if not isinstance(items, list):
        return out
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        field, uid, ref = it.get("field"), it.get("uncertain_id"), it.get("source_ref")
        tag = f"{where}.alt_readings[{i}]"
        if field not in ALT_FIELDS[kind]:
            out.append(f"{tag}: field {field!r} is not a text field of this block ({' / '.join(ALT_FIELDS[kind])})")
            continue
        value = block.get(field)
        if value is None:
            out.append(f"{tag}: {where}.{field} is null although {uid} marks it uncertain — a token masks only its own "
                       "span: the text field keeps its literal + that token (phase2 §3), it is never blanked")
            continue
        if not isinstance(value, str) or f"[OCR_UNCERTAIN:{uid}]" not in value:
            out.append(f"{tag}: {where}.{field} {value!r} does not carry its own token [OCR_UNCERTAIN:{uid}] "
                       "(literal + token; the alternative stays in alt_readings)")
        lines = _cited_lines(patient_dir, ref) if isinstance(ref, str) else []
        if not any(f"[OCR_UNCERTAIN:{uid}]" in l for l in lines):
            out.append(f"{tag}: source_ref {ref!r} does not cite the line holding [OCR_UNCERTAIN:{uid}]")
    return out


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _structured_text(patient_dir: Path) -> str:
    parts = []
    for name in ("patient_summary.json", "timeline.json", "treatment_lines.json", "molecular.json", "profile.json",
                 "acute_findings.json", "comorbidities.json"):
        p = patient_dir / name
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


_GLYPH_LINE_RE = re.compile(r"^- L(\d+)：文本层「(.+?)」；看图读作「(.+?)」")


def glyph_pairs(text: str) -> list[tuple[str, str]]:
    """(damaged run, by-eye reading) pairs of a sidecar's `## 文本层字形异常` block (phase1 §4 D)."""
    m = re.search(r"^## 文本层字形异常\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return []
    return [(g.group(2), g.group(3)) for g in (_GLYPH_LINE_RE.match(l.strip()) for l in m.group(1).splitlines()) if g]


def acute_search_problems(patient_dir: Path) -> list[str]:
    """acute-findings.md §2.5: verbatim_text keeps the damaged text layer; verbatim_text_search is it with every listed
    damaged run replaced by the by-eye reading — recomputed here."""
    out = []
    doc = _load(patient_dir / "acute_findings.json")
    for f in (doc or {}).get("findings") or [] if isinstance(doc, dict) else []:
        if not isinstance(f, dict) or not isinstance(f.get("verbatim_text"), str):
            continue
        rel = str(f.get("source_ref") or "").split("#", 1)[0]
        sc = patient_dir / rel
        pairs = glyph_pairs(sc.read_text(encoding="utf-8", errors="replace")) if rel and sc.is_file() else []
        hits = [(bad, good) for bad, good in pairs if bad in f["verbatim_text"]]
        want = f["verbatim_text"]
        for bad, good in hits:
            want = want.replace(bad, good)
        got = f.get("verbatim_text_search")
        fid = f.get("finding_id")
        if hits and got is None:
            out.append(f"acute_findings {fid}: verbatim_text holds the damaged text-layer run {hits[0][0]!r} listed in "
                       f"{rel}'s `## 文本层字形异常` block — add verbatim_text_search {want!r} (acute-findings.md §2.5)")
        elif got is not None and got != want:
            out.append(f"acute_findings {fid}: verbatim_text_search {got!r} is not verbatim_text with the listed damaged "
                       f"runs replaced ({want!r})")
    return out


def gate_readings(patient_dir: Path, errors: list, warnings: list | None = None,
                  generation: str | None = None) -> None:
    import validate_structured_outputs as vso
    add = vso._router(errors, warnings, vso._generation(patient_dir, generation))
    warn = (lambda m: warnings.append(m)) if warnings is not None else (lambda m: None)
    ps = _load(patient_dir / "patient_summary.json")
    diag = ps.get("diagnosis") if isinstance(ps, dict) and isinstance(ps.get("diagnosis"), dict) else None
    if diag is not None:
        for p in alt_reading_problems(patient_dir, diag, "diagnosis", "patient_summary.diagnosis"):
            add(f"readings: {p}")
        primary = diag.get("primary")
        if isinstance(primary, str) and primary.strip() and not diag.get("diagnosis_basis"):
            warn("readings: patient_summary.diagnosis.primary is set without diagnosis_basis — name the rung of the "
                 "source ladder it was taken from (phase2 §5.7)")
        prof = _load(patient_dir / "profile.json")
        summ = prof.get("summary") if isinstance(prof, dict) and isinstance(prof.get("summary"), dict) else None
        if summ is not None and "one_line_condition" in summ:
            olc = summ.get("one_line_condition")
            olc_s = _strip(olc) if isinstance(olc, str) else ""
            if isinstance(primary, str) and _strip(primary):
                if _strip(primary) not in olc_s:
                    add(f"readings: profile.summary.one_line_condition {olc!r} leaves out diagnosis.primary "
                        f"{_strip(primary)!r} — the one-line condition always carries the primary diagnosis (phase2 §5.7)")
            elif MISSING_DIAGNOSIS not in olc_s:
                add(f"readings: diagnosis.primary is null but profile.summary.one_line_condition {olc!r} does not say "
                    "诊断资料缺失 (phase2 §5.7)")
    for p in acute_search_problems(patient_dir):
        add(f"readings: {p}")
    tl = _load(patient_dir / "treatment_lines.json")
    for k, ep in enumerate((tl or {}).get("episodes") or [] if isinstance(tl, dict) else []):
        if isinstance(ep, dict):
            for p in alt_reading_problems(patient_dir, ep, "episode", f"treatment_lines.episodes[{k}]"):
                add(f"readings: {p}")
    # completeness hints from the second-read tables (advisory)
    import _gate_second_read as gsr
    structured = _structured_text(patient_dir)
    diag_agree = []
    missing = []
    for sc in vso._bucket_sidecars(patient_dir):
        sec = gsr.table_of(sc.read_text(encoding="utf-8", errors="replace"))
        for r in (sec or {}).get("rows") or []:
            if r.get("state") != "是" or r.get("field_class") not in ("stage", "diagnosis_text"):
                continue
            rel = sc.relative_to(patient_dir).as_posix()
            if r["field_class"] == "diagnosis_text":
                diag_agree.append(f"{rel}#L{r['line']}")
            if r["model"] not in structured:
                missing.append(f"{r['field_class']} {r['model']!r} ({rel}#L{r['line']})")
    if diag_agree and diag is not None and not (isinstance(diag.get("primary"), str) and diag["primary"].strip()):
        warn(f"readings: a diagnosis was read consistently by both channels ({diag_agree[0]}"
             + (f" and {len(diag_agree) - 1} more" if len(diag_agree) > 1 else "")
             + ") but patient_summary.diagnosis.primary is null — apply the source ladder (phase2 §5.7)")
    if missing:
        warn(f"readings: completeness — {len(missing)} stage / diagnosis reading(s) that both channels agree on appear in "
             f"no structured field: {'; '.join(missing[:3])}" + (" …" if len(missing) > 3 else ""))
