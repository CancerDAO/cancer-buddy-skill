#!/usr/bin/env python3
"""Validate the no-static-marker-mapping trend policy."""
import argparse
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markers", required=True)
    parser.add_argument("--slugs", help="retained for backward-compatible invocation; unused")
    args = parser.parse_args()
    text = Path(args.markers).read_text(encoding="utf-8")
    errors = []

    required = {
        "no cancer-type auto-selection": r"does not maintain a cancer-type table|Do not place.*by cancer type|不.*按癌种",
        "method/unit compatibility": r"same analyte/method|compatible units|方法.*单位",
        "source anchoring": r"source anchor|来源.*锚",
        "no efficacy inference": r"Do not infer response|no efficacy interpretation|不.*疗效",
        "patient or clinician trigger": r"user requests|clinician-authored plan|用户.*请求|医生.*计划",
    }
    for label, pattern in required.items():
        if not re.search(pattern, text, re.I | re.S):
            errors.append(f"missing policy: {label}")

    for line_no, line in enumerate(text.splitlines(), 1):
        cells = [cell.strip().lower() for cell in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and "slug" in cells and any(
            token in cells for token in ("marker", "primary", "tumor marker", "标志物", "癌种")
        ):
            errors.append(f"L{line_no}: static cancer-type/marker mapping table is forbidden")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("OK: source-grounded, no-static-marker-mapping policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
