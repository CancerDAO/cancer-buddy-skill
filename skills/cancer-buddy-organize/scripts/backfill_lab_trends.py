#!/usr/bin/env python3
"""Deterministic floor for 段D `lab_trends` (stdlib only, ZERO medical judgement).

The 段D producer (an LLM subagent) is *supposed* to select which labs to surface as
trend rows and describe them. But an LLM can leave `lab_trends: []` even when the
patient has rich lab data — and then the patient-facing summary shows "资料缺失"
where a trend table belongs. That is a correctness failure, not a style nit.

This helper is the SAFETY NET: **only when `lab_trends` is empty AND `labs.json`
has panels**, it builds one row per panel straight from the structured data —
name = analyte, series = the panel's dated values, current_value = the latest,
status from the latest value's `flag` (or a range compare when flag is absent).
It is a pure data transform (no "is this lab important?" keyword list) — it simply
surfaces everything the record already has rather than leaving the section blank.

If the producer already populated `lab_trends`, this is a NO-OP (the LLM's
condition-aware selection + wording wins). Run it BEFORE compute_sparklines so the
backfilled rows get their sparkline geometry too.

status_label is localized from a tiny zh/en table; for any other locale it falls
back to the English word (the LLM path produces a properly localized label — this
floor only needs to be correct, not eloquent).

CLI:
    python3 backfill_lab_trends.py --data .case_summary_data.json --labs labs.json [--profile profile.json]

Exit codes:
    0  — data written (backfilled, or left unchanged if already populated / no panels)
    2  — bad invocation / unreadable --data
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_STATUS_LABELS = {
    "zh": {"normal": "正常", "low": "偏低", "high": "偏高", "abnormal": "异常", "severe": "严重", "": ""},
    "en": {"normal": "Normal", "low": "Low", "high": "High", "abnormal": "Abnormal", "severe": "Severe", "": ""},
}


def _to_float(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _status_from_flag(flag):
    """Map a lab flag to a status_class. Conservative: only the well-known flags."""
    if not flag or not isinstance(flag, str):
        return None
    f = flag.strip().upper()
    if f in ("HH", "LL", "CRIT", "CRITICAL", "PANIC"):
        return "severe"
    if f in ("H", "HIGH", "+"):
        return "high"
    if f in ("L", "LOW", "-"):
        return "low"
    if f in ("A", "ABN", "ABNORMAL", "*"):
        return "abnormal"
    return None


def _status_from_range(value, ref_range):
    """When no flag: compare numeric value to a 'lo-hi' reference range."""
    fv = _to_float(value)
    if fv is None or not isinstance(ref_range, str):
        return ""
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*[-~–]\s*(-?\d+(?:\.\d+)?)\s*$", ref_range.strip())
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if fv < lo:
            return "low"
        if fv > hi:
            return "high"
        return "normal"
    m = re.match(r"\s*[<≤]\s*(-?\d+(?:\.\d+)?)\s*$", ref_range.strip())
    if m:
        return "high" if fv > float(m.group(1)) else "normal"
    m = re.match(r"\s*[>≥]\s*(-?\d+(?:\.\d+)?)\s*$", ref_range.strip())
    if m:
        return "low" if fv < float(m.group(1)) else "normal"
    return ""


def _panel_to_row(panel, labels):
    analyte = panel.get("analyte")
    if not analyte:
        return None
    values = [v for v in (panel.get("values") or []) if isinstance(v, dict)]
    # sort by date when present (ISO strings sort lexicographically)
    values.sort(key=lambda v: str(v.get("date") or ""))
    series = []
    for v in values:
        d = v.get("date")
        val = v.get("value")
        if d is not None and val is not None:
            series.append({"t": str(d), "v": val})
    latest = values[-1] if values else {}
    current_value = latest.get("value")
    status_class = _status_from_flag(latest.get("flag"))
    if status_class is None:
        status_class = _status_from_range(current_value, panel.get("reference_range"))
    return {
        "lab_name": str(analyte),
        "series": series,
        "current_value": "" if current_value is None else str(current_value),
        "unit": str(panel.get("unit") or ""),
        "status_class": status_class or "",
        "status_label": labels.get(status_class or "", ""),
    }


def backfill(data: dict, labs: dict, locale: str) -> int:
    """Fill data['lab_trends'] from labs['panels'] iff currently empty. Returns
    the number of rows added (0 = no-op)."""
    if data.get("lab_trends"):
        return 0  # producer already populated — respect the LLM's selection
    panels = labs.get("panels") if isinstance(labs, dict) else None
    if not panels:
        return 0
    labels = _STATUS_LABELS.get((locale or "").split("-")[0].lower(), _STATUS_LABELS["en"])
    rows = [r for r in (_panel_to_row(p, labels) for p in panels if isinstance(p, dict)) if r]
    if rows:
        data["lab_trends"] = rows
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministically backfill 段D lab_trends from labs.json when the producer left it empty.")
    ap.add_argument("--data", required=True, help="case_summary_data.json (modified in place unless --out)")
    ap.add_argument("--labs", required=True, help="labs.json (labs.schema.json, panels[])")
    ap.add_argument("--profile", help="profile.json (for locale of status labels)")
    ap.add_argument("--out", help="output path (default: overwrite --data)")
    args = ap.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot read/parse --data: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("ERROR: --data root must be a JSON object", file=sys.stderr)
        return 2

    try:
        labs = json.loads(Path(args.labs).read_text(encoding="utf-8"))
    except Exception:
        labs = {}

    locale = "en"
    if args.profile:
        try:
            locale = json.loads(Path(args.profile).read_text(encoding="utf-8")).get("locale") or "en"
        except Exception:
            pass

    n = backfill(data, labs, locale)
    out = args.out or args.data
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"lab_trends backfill → {out} ({'no-op (already populated / no panels)' if n == 0 else str(n) + ' row(s) from labs.json'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
