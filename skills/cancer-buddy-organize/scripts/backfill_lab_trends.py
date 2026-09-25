#!/usr/bin/env python3
"""Backfill case-summary lab rows without clinical grading.

The transform copies dated values from labs.json. Badge text comes only from the
reporting laboratory's own report_flag/critical_flag on the latest result. It
never compares a value with a range, invents H/L, or assigns severity.

A result whose column binding was not confirmed (labs v2.1 pairing_method
`linear_position` = position-paired candidate, `none` = pairing refused, or any row that
carries a candidate_value) is never displayed: its raw string is not bound to this
analyte, so showing it would present a candidate as the patient's value. This holds for
rows 段D already wrote too: an existing lab_trends row whose analyte has no confirmed
result, or whose newest result is unconfirmed, gets its current_value cleared (the
series is kept; compute_sparklines.py --labs rejects any series point or numeric
current_value that is not a confirmed value).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _latest(values: list[dict]) -> dict:
    return sorted(values, key=lambda item: str(item.get("date") or ""))[-1] if values else {}


def _source_badge(result: dict) -> tuple[str, str]:
    critical = result.get("critical_flag")
    report = result.get("report_flag")
    if critical not in (None, ""):
        return "critical", str(critical)
    if report not in (None, ""):
        return "", str(report)
    return "", ""


UNCONFIRMED_PAIRING = ("linear_position", "none")


def is_unconfirmed(result: dict) -> bool:
    """A result whose value-to-analyte binding is only a candidate (or was refused)."""
    return result.get("pairing_method") in UNCONFIRMED_PAIRING or result.get("candidate_value") is not None


def _panel_to_row(panel: dict) -> dict | None:
    analyte = panel.get("analyte")
    if not analyte:
        return None
    all_values = [item for item in (panel.get("values") or []) if isinstance(item, dict)]
    values = [item for item in all_values if not is_unconfirmed(item)]
    if all_values and not values:
        return None  # only unconfirmed candidates: nothing may be displayed for this analyte
    values.sort(key=lambda item: str(item.get("date") or ""))
    series = [
        {"t": str(item["date"]), "v": item["value"]}
        for item in values
        if item.get("date") is not None and item.get("value") is not None
    ]
    latest = _latest(values)
    displayed = latest.get("raw_value")
    if displayed in (None, ""):
        displayed = latest.get("value")
    status_class, status_label = _source_badge(latest)
    return {
        "lab_name": str(analyte),
        "series": series,
        "current_value": "" if displayed is None else str(displayed),
        "unit": "" if latest.get("unit") is None else str(latest.get("unit")),
        "status_class": status_class,
        "status_label": status_label,
    }


def backfill(data: dict, labs: dict) -> int:
    panels = [item for item in (labs.get("panels") or []) if isinstance(item, dict)] if isinstance(labs, dict) else []
    source_rows = [row for row in (_panel_to_row(panel) for panel in panels) if row]
    by_name = {row["lab_name"]: row for row in source_rows}
    # analytes whose newest result is unconfirmed (or that have no confirmed result at all)
    unconfirmed_latest: set[str] = set()
    for panel in panels:
        vals = [v for v in (panel.get("values") or []) if isinstance(v, dict)]
        if panel.get("analyte") and vals and is_unconfirmed(_latest(vals)):
            unconfirmed_latest.add(str(panel["analyte"]))

    if not data.get("lab_trends"):
        data["lab_trends"] = source_rows
        return len(source_rows)

    # Existing display rows may keep their selected series, but badges are
    # re-grounded to the source result. Unknown rows receive no badge.
    for row in data.get("lab_trends") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("lab_name") or "")
        source = by_name.get(name)
        row["status_class"] = source.get("status_class", "") if source else ""
        row["status_label"] = source.get("status_label", "") if source else ""
        # A position-paired candidate must never surface as the displayed value: if the
        # newest result for this analyte is unconfirmed, show the latest CONFIRMED value
        # (or nothing when there is none). Rows naming no labs.json analyte are left to
        # the compute_sparklines --labs anti-fabrication gate.
        if name in unconfirmed_latest:
            row["current_value"] = source["current_value"] if source else ""
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill lab trends from source-reported lab results")
    parser.add_argument("--data", required=True)
    parser.add_argument("--labs", required=True)
    parser.add_argument("--profile", help="accepted for backward-compatible CLI use")
    parser.add_argument("--out")
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        labs = json.loads(Path(args.labs).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: cannot read input JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict) or not isinstance(labs, dict):
        print("ERROR: input roots must be JSON objects", file=sys.stderr)
        return 2

    count = backfill(data, labs)
    out = Path(args.out or args.data)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"lab_trends source-only backfill -> {out} ({count} row(s) added)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
