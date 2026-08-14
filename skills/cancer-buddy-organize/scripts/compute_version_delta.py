#!/usr/bin/env python3
"""Compute the 段D "自上次总结的变化" delta from `.case_summary_data.json`
snapshots (stdlib only, ZERO medical logic).

Each 段D (re)generation snapshots its render data to
`case_summary_versions/case_summary_data_<date>.json`. This helper diffs the
CURRENT render data against the most recent PRIOR snapshot and injects a
`version_delta` object the template renders as a highlighted "what changed since
last time" strip — the literal answer to "当前 vs 上一版对比". First-ever summary
(no prior snapshot) → `version_delta: null` → the strip is hidden (RENDER_IF).

It compares only fields already present in the render data, VERBATIM — it invents
no clinical judgement and no numbers:

  - lab_trends[] / labs[] : current_value moved (up/down/changed) per lab_name.
  - treatment_lines[]     : a line present now but absent before → "新增 <label> <regimen>".
  - ecog                  : ECOG scalar moved.

`dir` ∈ {up, down, changed, new} drives the arrow/colour; the numeric compare is a
plain float compare when both sides parse as numbers, else a string-inequality
"changed". Direction carries NO clinical meaning here (a lab going down can be good
or bad) — it is purely the arithmetic direction; the template colours it neutrally.

CLI:
    python3 compute_version_delta.py --data .case_summary_data.json --prev PREV.json
    python3 compute_version_delta.py --data .case_summary_data.json            # no --prev → version_delta:null
    python3 compute_version_delta.py --data D.json --prev P.json --out E.json

Exit codes:
    0  — delta computed (or set to null) and written
    2  — bad invocation / unreadable --data
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _to_float(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().lstrip("<>≤≥").strip()
        # keep the leading numeric run so "1.81 ng/mL" compares as 1.81
        num = ""
        for ch in s:
            if ch.isdigit() or ch in ".-+eE":
                num += ch
            else:
                break
        try:
            return float(num)
        except ValueError:
            return None
    return None


def _lab_current(row: dict):
    """Current value string for a lab row from either lab_trends or labs shape."""
    if not isinstance(row, dict):
        return None, None
    name = row.get("lab_name") or row.get("name")
    val = row.get("current_value")
    if val is None:
        val = row.get("lab_value")
    return name, val


def _lab_map(data: dict) -> dict:
    """{lab_name: current_value_str} merged over lab_trends[] then labs[]."""
    out: dict[str, object] = {}
    for key in ("lab_trends", "labs"):
        for row in data.get(key, []) or []:
            name, val = _lab_current(row)
            if name and val is not None and name not in out:
                out[name] = val
    return out


def _treatment_set(data: dict) -> dict:
    """{(label, regimen): row} keyed by the verbatim clinical strings."""
    out = {}
    for row in data.get("treatment_lines", []) or []:
        if isinstance(row, dict):
            key = (str(row.get("line_label", "")).strip(), str(row.get("line_regimen", "")).strip())
            if key != ("", ""):
                out[key] = row
    return out


def compute_delta(cur: dict, prev: dict) -> dict:
    items = []

    # labs — value moves
    cur_labs, prev_labs = _lab_map(cur), _lab_map(prev)
    for name in cur_labs:
        if name not in prev_labs:
            continue  # a brand-new lab is not a "change since last" of an existing value
        a, b = prev_labs[name], cur_labs[name]
        if str(a).strip() == str(b).strip():
            continue
        fa, fb = _to_float(a), _to_float(b)
        if fa is not None and fb is not None:
            direction = "down" if fb < fa else ("up" if fb > fa else "changed")
        else:
            direction = "changed"
        items.append({"kind": "lab", "text": f"{name} {a} → {b}", "dir": direction})

    # treatment lines — newly added
    cur_tx, prev_tx = _treatment_set(cur), _treatment_set(prev)
    for (label, regimen) in cur_tx:
        if (label, regimen) not in prev_tx:
            txt = f"新增 {label} {regimen}".strip()
            items.append({"kind": "treatment", "text": txt, "dir": "new"})

    # ecog scalar
    a, b = prev.get("ecog"), cur.get("ecog")
    if a is not None and b is not None and str(a).strip() != str(b).strip():
        fa, fb = _to_float(a), _to_float(b)
        if fa is not None and fb is not None:
            direction = "down" if fb < fa else ("up" if fb > fa else "changed")
        else:
            direction = "changed"
        items.append({"kind": "status", "text": f"ECOG {a} → {b}", "dir": direction})

    return {"prev_date": prev.get("report_date"), "items": items}


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject version_delta (自上次总结的变化) into .case_summary_data.json.")
    ap.add_argument("--data", required=True, help="current .case_summary_data.json")
    ap.add_argument("--prev", help="previous snapshot case_summary_data_<date>.json (omit → version_delta:null)")
    ap.add_argument("--out", help="output path (default: overwrite --data in place)")
    args = ap.parse_args()

    try:
        cur = json.loads(Path(args.data).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot read/parse --data: {e}", file=sys.stderr)
        return 2
    if not isinstance(cur, dict):
        print("ERROR: --data root must be a JSON object", file=sys.stderr)
        return 2

    prev = None
    if args.prev:
        try:
            prev = json.loads(Path(args.prev).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN: cannot read --prev ({e}); treating as first-ever summary", file=sys.stderr)
            prev = None

    if isinstance(prev, dict):
        delta = compute_delta(cur, prev)
        # An empty item list still means "compared, nothing changed" — render a
        # neutral note rather than hiding, so the patient knows it WAS compared.
        cur["version_delta"] = delta
        n = len(delta["items"])
    else:
        cur["version_delta"] = None
        n = 0

    out = args.out or args.data
    Path(out).write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"version_delta → {out} ({'null (first summary)' if prev is None else str(n) + ' change(s)'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
