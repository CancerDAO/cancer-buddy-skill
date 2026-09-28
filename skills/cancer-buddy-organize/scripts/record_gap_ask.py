#!/usr/bin/env python3
"""record_gap_ask.py — the ask-once ledger for "would you like to add this existing document?" invitations.

`<patient_dir>/gap_asks.json` (references/schemas/gap_asks.schema.json) records every concrete invitation
the orchestrator makes under SKILL.md Step 11.4 / references/gap-followup.md, so the same existing
document is not asked for again and again. It never assigns clinical priority or recommends a test.
This script is the ledger's only writer (it is on the orchestrator's allow-list, SKILL.md invariant 3):
the orchestrator makes the invitation in conversation and records it here — it never hand-edits the file.

Pinned rules (gap-followup.md「只问一次」):
  * one invitation per item_key per session day;
  * a `declined` item is never offered again (only the user may raise it);
  * a `provided` item is closed;
  * a `pending` item may be offered again at most once more, and only ≥ REASK_AFTER_DAYS days after
    its last invitation (MAX_ASKS invitations in total).

Usage:
  record_gap_ask.py <patient_dir> check  --item-key K [--today YYYY-MM-DD]
        exit 0 + "allowed" → you may make the invitation; exit 3 + the reason → do not ask
  record_gap_ask.py <patient_dir> ask    --item-key K --category "<document category>" --trigger <step>
        [--today YYYY-MM-DD]   (runs `check` first; exit 3 without writing when not allowed)
  record_gap_ask.py <patient_dir> status --item-key K --status provided|declined [--today YYYY-MM-DD]
item_key = the missing_items.json document_gaps[] group_key when it has one, else its document_category.
Exit: 0 ok · 2 bad invocation · 3 not allowed (nothing written).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

LEDGER = "gap_asks.json"
REASK_AFTER_DAYS = 30
MAX_ASKS = 2
_PT_RE = re.compile(r"^PT-[A-F0-9]+(_\d+)?$")


def _today(arg: str | None) -> str:
    if arg:
        dt.date.fromisoformat(arg)
        return arg
    return dt.date.today().isoformat()


def load(patient_dir: Path) -> dict:
    p = patient_dir / LEDGER
    if p.is_file():
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
            raise SystemExit(f"{LEDGER}: not a ledger ({{schema_version, items[]}})")
        return doc
    code = patient_dir.name if _PT_RE.match(patient_dir.name) else None
    return {"schema_version": "1", **({"patient_code": code} if code else {}), "items": []}


def save(patient_dir: Path, doc: dict) -> None:
    (patient_dir / LEDGER).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find(doc: dict, key: str) -> dict | None:
    return next((it for it in doc["items"] if isinstance(it, dict) and it.get("item_key") == key), None)


def refusal(doc: dict, key: str, today: str) -> str | None:
    it = find(doc, key)
    if it is None:
        return None
    if it.get("status") == "declined":
        return "declined — never offered again (only the user may raise it)"
    if it.get("status") == "provided":
        return "provided — closed"
    asks = it.get("asked_at") or []
    if len(asks) >= MAX_ASKS:
        return f"already offered {len(asks)} time(s) (at most {MAX_ASKS})"
    if asks:
        last = dt.date.fromisoformat(asks[-1][:10])
        if (dt.date.fromisoformat(today) - last).days < REASK_AFTER_DAYS:
            return f"last offered {asks[-1][:10]} — re-offer only after {REASK_AFTER_DAYS} days"
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Ask-once ledger for existing-document invitations (gap_asks.json).")
    ap.add_argument("patient_dir")
    ap.add_argument("action", choices=("check", "ask", "status"))
    ap.add_argument("--item-key", required=True)
    ap.add_argument("--category")
    ap.add_argument("--trigger")
    ap.add_argument("--status", choices=("provided", "declined"))
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    pd = Path(a.patient_dir)
    if not pd.is_dir():
        print(f"not a directory: {pd}", file=sys.stderr)
        return 2
    try:
        today = _today(a.today)
    except ValueError:
        print("--today must be YYYY-MM-DD", file=sys.stderr)
        return 2
    doc = load(pd)
    if a.action == "check":
        why = refusal(doc, a.item_key, today)
        print("allowed" if why is None else f"not allowed: {why}")
        return 0 if why is None else 3
    if a.action == "ask":
        if not a.category or not a.trigger:
            print("ask needs --category and --trigger", file=sys.stderr)
            return 2
        why = refusal(doc, a.item_key, today)
        if why is not None:
            print(f"not allowed: {why}")
            return 3
        it = find(doc, a.item_key)
        if it is None:
            it = {"item_key": a.item_key, "document_category": a.category, "asked_at": [], "surfaced_at_trigger": a.trigger,
                  "status": "pending", "status_at": today}
            doc["items"].append(it)
        it["asked_at"].append(today)
        it["surfaced_at_trigger"] = a.trigger
        save(pd, doc)
        print(f"recorded: {a.item_key} offered {len(it['asked_at'])} time(s)")
        return 0
    if not a.status:
        print("status needs --status provided|declined", file=sys.stderr)
        return 2
    it = find(doc, a.item_key)
    if it is None:
        print(f"no invitation recorded for {a.item_key}", file=sys.stderr)
        return 3
    it["status"], it["status_at"] = a.status, today
    save(pd, doc)
    print(f"recorded: {a.item_key} {a.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
