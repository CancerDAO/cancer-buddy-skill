#!/usr/bin/env python3
"""Backfill case-summary lab rows without clinical grading.

The transform copies dated values from labs.json. Badge text comes only from the
reporting laboratory's own report_flag/critical_flag on the latest result. It
never compares a value with a range, invents H/L, or assigns severity.
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


def _panel_to_row(panel: dict) -> dict | None:
    analyte = panel.get("analyte")
    if not analyte:
        return None
    values = [item for item in (panel.get("values") or []) if isinstance(item, dict)]
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

    if not data.get("lab_trends"):
        data["lab_trends"] = source_rows
        return len(source_rows)

    # Existing display rows may keep their selected series, but badges are
    # re-grounded to the source result. Unknown rows receive no badge.
    for row in data.get("lab_trends") or []:
        if not isinstance(row, dict):
            continue
        source = by_name.get(str(row.get("lab_name") or ""))
        row["status_class"] = source.get("status_class", "") if source else ""
        row["status_label"] = source.get("status_label", "") if source else ""
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
