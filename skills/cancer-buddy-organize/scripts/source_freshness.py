#!/usr/bin/env python3
"""source_freshness.py — how old is the newest source document in the archive? (O-04)

Computes the three readiness.json v2.1 recency fields:
    latest_source_date  — latest report/exam date among the dated source documents;
    days_since_latest   — as_of_run_date − latest_source_date, in days;
    as_of_run_date      — the run date the recency is measured against.
More than THRESHOLD_DAYS (14) days → stale: readiness.warnings[] must carry a line
stating the day count, and the downstream time statement must say it too. Exactly 14
days is NOT stale (iteration doc: "超过 14 天时告警").

Which documents count (deterministic, no medical judgement):
  * every sidecar `NN_…/…/YYYY-MM-DD_….md` under a clinical bucket — the filename date
    prefix is the document's own report/exam date (bucket naming convention);
  * EXCLUDED: 14_患者自管补充 (patient supplements carry no report date of their own),
    99_ quarantine, conversation_notes, prior-archive digests (sub-bucket
    既往档案摘录 / prior-archive-digest, or inventory rows with
    source_kind=prior_archive_digest) and any date after as_of (reported, not used).
Upload / file-modification times are never used.

as_of: --as-of YYYY-MM-DD, else readiness.json `as_of_run_date`, else the date part
of readiness.json `generated_at`, else today's LOCAL date. as_of_run_date is the local
calendar date of the run; update_log entries[].at are UTC ISO timestamps, so the validator
accepts an as_of_run_date within ±1 day of a logged run.

The stale warning has ONE wording, STALE_WARNING_TEMPLATE: Phase 2 copies the script's
`warning` verbatim into readiness.warnings[], and every prompt that quotes it quotes this
template (tests/unit/source-freshness.test.sh pins it).

CLI:
    source_freshness.py <patient_dir> [--as-of YYYY-MM-DD] [--json]
Exit: 0 = computed (stale or not — this is a reporter); 2 = bad invocation.
Importable: compute(patient_dir, as_of=None) -> dict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

THRESHOLD_DAYS = 14
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
_BUCKET_RE = re.compile(r"^\d{2}_")
EXCLUDED_TOP_PREFIXES = ("14_", "99_")
DIGEST_SUB_BUCKETS = ("既往档案摘录", "prior-archive-digest")


def _parse_date(s) -> date | None:
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _digest_sidecars(patient_dir: Path) -> set[str]:
    inv = patient_dir / "source_inventory.json"
    out: set[str] = set()
    if not inv.is_file():
        return out
    try:
        doc = json.loads(inv.read_text(encoding="utf-8"))
    except Exception:
        return out
    for row in doc.get("files", []) if isinstance(doc, dict) else []:
        if isinstance(row, dict) and row.get("source_kind") == "prior_archive_digest" \
                and isinstance(row.get("sidecar_path"), str):
            out.add(row["sidecar_path"])
    return out


def default_as_of(patient_dir: Path) -> tuple[date, str]:
    r = patient_dir / "readiness.json"
    if r.is_file():
        try:
            doc = json.loads(r.read_text(encoding="utf-8"))
        except Exception:
            doc = None
        if isinstance(doc, dict):
            d = _parse_date(doc.get("as_of_run_date"))
            if d:
                return d, "readiness.as_of_run_date"
            d = _parse_date(doc.get("generated_at"))
            if d:
                return d, "readiness.generated_at"
    return date.today(), "today_local"


# The single canonical stale-source sentence ({latest} = YYYY-MM-DD, {days} = integer day count).
STALE_WARNING_TEMPLATE = ("本档案最新一份资料的日期为 {latest}，距本次整理已 {days} 天；"
                          "请确认此后是否有新的检查报告或病历，时效说明需写明这一天数。")


def stale_warning(latest: str, days: int) -> str:
    return STALE_WARNING_TEMPLATE.format(latest=latest, days=days)


def compute(patient_dir: Path | str, as_of: str | date | None = None) -> dict:
    patient_dir = Path(patient_dir)
    if as_of is None:
        as_of_d, as_of_src = default_as_of(patient_dir)
    else:
        as_of_d = as_of if isinstance(as_of, date) else _parse_date(as_of)
        if as_of_d is None:
            raise ValueError(f"--as-of must be YYYY-MM-DD, got {as_of!r}")
        as_of_src = "argument"
    digests = _digest_sidecars(patient_dir)
    considered: list[tuple[date, str]] = []
    excluded = {"patient_supplement_or_quarantine": 0, "prior_archive_digest": 0,
                "undated": 0, "after_as_of": []}
    for top in sorted(patient_dir.iterdir()) if patient_dir.is_dir() else []:
        if not top.is_dir() or not _BUCKET_RE.match(top.name):
            continue
        skip_top = top.name.startswith(EXCLUDED_TOP_PREFIXES)
        for p in sorted(top.rglob("*.md")):
            rel = p.relative_to(patient_dir).as_posix()
            if "conversation_notes" in p.parts:
                continue
            if skip_top:
                excluded["patient_supplement_or_quarantine"] += 1
                continue
            if rel in digests or any(part in DIGEST_SUB_BUCKETS for part in p.parts):
                excluded["prior_archive_digest"] += 1
                continue
            m = _DATE_PREFIX_RE.match(p.name)
            d = _parse_date(m.group(1)) if m else None
            if d is None:
                excluded["undated"] += 1
                continue
            if d > as_of_d:
                excluded["after_as_of"].append(rel)
                continue
            considered.append((d, rel))
    latest = max(considered)[0] if considered else None
    latest_ref = max(considered)[1] if considered else None
    days = (as_of_d - latest).days if latest else None
    stale = bool(days is not None and days > THRESHOLD_DAYS)
    return {
        "tool": "source_freshness",
        "version": "1",
        "latest_source_date": latest.isoformat() if latest else None,
        "latest_source_ref": latest_ref,
        "days_since_latest": days,
        "as_of_run_date": as_of_d.isoformat(),
        "as_of_source": as_of_src,
        "threshold_days": THRESHOLD_DAYS,
        "stale": stale,
        "warning": stale_warning(latest.isoformat(), days) if stale else None,
        "sources_considered": len(considered),
        "excluded": excluded,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compute latest_source_date / days_since_latest for readiness.json.")
    ap.add_argument("patient_dir")
    ap.add_argument("--as-of", default=None, help="run date YYYY-MM-DD, the LOCAL date of the run (default: readiness.json as_of_run_date / generated_at, else today's local date)")
    ap.add_argument("--json", action="store_true", help="JSON only (no stderr summary)")
    args = ap.parse_args(argv)
    pdir = Path(args.patient_dir)
    if not pdir.is_dir():
        print(f"ERROR: {pdir} is not a directory", file=sys.stderr)
        return 2
    try:
        rep = compute(pdir, args.as_of)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if not args.json:
        print(f"SOURCE_FRESHNESS: latest={rep['latest_source_date']} as_of={rep['as_of_run_date']} "
              f"days={rep['days_since_latest']} stale={rep['stale']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
