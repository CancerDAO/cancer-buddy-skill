#!/usr/bin/env python3
"""update_log_append.py — append one entry to <patient_dir>/update_log.json with its hash-chain link
(phase2 §8; ORG-P1-09).

Each appended entry gets `prev_sha256` = sha256 of the previous entry's canonical JSON (keys sorted, no
whitespace, UTF-8) — or null for the first entry of a new ledger. validate_structured_outputs.py re-computes the
chain: an entry edited after a later one was appended (a kill rewritten as `retried`, a degradation deleted)
breaks the link. A model cannot hash reliably, so Phase 2 writes its entry to a file and appends it through this
script instead of editing update_log.json by hand.

CLI:
    update_log_append.py <patient_dir> --entry <entry.json | -> [--patient-code PT-…]   (- = read the entry from stdin)
    update_log_append.py <patient_dir> --check          # verify the chain; prints the first break
Exit: 0 ok; 1 --check found a break; 2 bad invocation / unreadable ledger / not a v1 ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

NAME = "update_log.json"


def canonical(entry: dict) -> bytes:
    return json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def entry_sha(entry: dict) -> str:
    return hashlib.sha256(canonical(entry)).hexdigest()


def chain_problems(entries: list) -> list[str]:
    """Breaks of the prev_sha256 chain. The chain starts at the first entry that carries the key (older
    ledgers had none); from there on every entry must carry it and match its predecessor."""
    out: list[str] = []
    started = False
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        if "prev_sha256" not in e:
            if started:
                out.append(f"entries[{i}] ({e.get('run_mode')} at {e.get('at')}) has no prev_sha256 although an earlier "
                           "entry started the chain — append through scripts/update_log_append.py")
            continue
        started = True
        want = entry_sha(entries[i - 1]) if i > 0 and isinstance(entries[i - 1], dict) else None
        if e["prev_sha256"] != want:
            out.append(f"entries[{i}] ({e.get('run_mode')} at {e.get('at')}) prev_sha256 does not match entries[{i - 1}] — "
                       "an earlier entry was edited after this one was appended")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("patient_dir")
    ap.add_argument("--entry", help="JSON file holding ONE update_log entry (without prev_sha256)")
    ap.add_argument("--patient-code")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    pd = Path(a.patient_dir)
    path = pd / NAME
    if not pd.is_dir():
        print(json.dumps({"error": f"{pd} is not a directory"}), file=sys.stderr)
        return 2
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(json.dumps({"error": f"{NAME} is not parseable JSON: {e}"}), file=sys.stderr)
            return 2
        if not isinstance(doc, dict) or doc.get("schema_version") != "1" or not isinstance(doc.get("entries"), list):
            print(json.dumps({"error": f"{NAME} is not a schema_version \"1\" ledger — move a legacy ledger aside first "
                                       "(phase2 §8)"}), file=sys.stderr)
            return 2
    else:
        doc = {"schema_version": "1", "entries": []}
        if a.patient_code:
            doc["patient_code"] = a.patient_code
    if a.check:
        probs = chain_problems(doc["entries"])
        print(json.dumps({"entries": len(doc["entries"]), "chain_ok": not probs, "problems": probs}, ensure_ascii=False))
        return 1 if probs else 0
    if not a.entry:
        print(json.dumps({"error": "pass --entry <file> or --check"}), file=sys.stderr)
        return 2
    try:
        entry = json.loads(sys.stdin.read() if a.entry == "-" else Path(a.entry).read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"error": f"--entry is not parseable JSON: {e}"}), file=sys.stderr)
        return 2
    if not isinstance(entry, dict):
        print(json.dumps({"error": "--entry must hold one JSON object"}), file=sys.stderr)
        return 2
    entry.pop("prev_sha256", None)
    entries = doc["entries"]
    entry["prev_sha256"] = entry_sha(entries[-1]) if entries else None
    entries.append(entry)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"appended": len(entries) - 1, "prev_sha256": entry["prev_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
