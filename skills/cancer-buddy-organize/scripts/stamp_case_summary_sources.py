#!/usr/bin/env python3
"""stamp_case_summary_sources.py — record which acute_findings.json a 段D render read.

Writes `acute_findings_sha256` into <patient_dir>/.case_summary_data.json: the sha256 of
<patient_dir>/acute_findings.json as it is now (null when that file does not exist). The 段D
worker runs it right before render_html_template.py (case-summary-html-prompt.md 段D 管线 step 3).

Why: the 段D narrative's first sentence must name every emergent/urgent finding. A later run
(incremental, upload reconciliation, restore) can add a finding without re-rendering 段D — the
re-render waits for the case-summary freshness question (SKILL.md). validate_structured_outputs.py
tells those two apart with this stamp: stamp == current file and a finding is missing → the
render read it and left it out (ERROR); stamp ≠ current file → the render predates the change
(WARN "段D stale"). Deterministic, zero medical logic.

CLI:
    stamp_case_summary_sources.py <patient_dir>
Exit: 0 stamped; 2 bad invocation / .case_summary_data.json missing or not a JSON object.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DATA_NAME = ".case_summary_data.json"
ACUTE_NAME = "acute_findings.json"
STAMP_KEY = "acute_findings_sha256"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0].startswith("-"):
        print("usage: stamp_case_summary_sources.py <patient_dir>", file=sys.stderr)
        return 2
    patient_dir = Path(argv[0])
    data_path = patient_dir / DATA_NAME
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {DATA_NAME} unreadable: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print(f"ERROR: {DATA_NAME} is not a JSON object", file=sys.stderr)
        return 2
    acute = patient_dir / ACUTE_NAME
    data[STAMP_KEY] = file_sha256(acute) if acute.is_file() else None
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{STAMP_KEY}={data[STAMP_KEY]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
