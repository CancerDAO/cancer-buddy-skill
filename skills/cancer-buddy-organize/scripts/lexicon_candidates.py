#!/usr/bin/env python3
"""lexicon_candidates.py — the mechanical `## 不确定字段` candidate list (organizer-prompt-phase1-ocr.md §5).

Candidates for an uncertain `drug_name` / `ihc_marker` / `ln_station` field come only from the
pinned lexicons (references/lexicons/<name>.txt, one term per line) by rules 1-5 of phase1 §5 —
a pure computation, so it is a script: Phase 1 runs it and copies its output into the entry, and
validate_structured_outputs.py recomputes it and rejects any other list.

  1. normalise: NFKC + case fold, then strip a leading / trailing "No." / 组 / 站;
  2. distance: character Levenshtein (insert / delete / substitute = 1); an unresolved character in
     a reading (`?`, and ？ [?] □ U+FFFD written for it) equals nothing;
  3. admit: an entry of normalised length ≤ 3 needs distance ≤ 1 to some reading, a longer one ≤ 2;
  4. rank: smallest distance to any reading, then more readings within the admit threshold, then
     the lexicon's line order; keep the first 3;
  5. confidence: distance 0 to a COMPLETE reading and ≤ 1 to every other reading → high; distance 0
     to a complete reading → medium; else low. Any reading with an unresolved character caps
     every candidate at medium.
Rule 6 (a clear reading of the same object on another page of the slice must be among the
candidates) needs the other page, so Phase 1 applies it on top: the validator accepts exactly one
such replacement of the 3rd candidate (or an append) when it is a whole lexicon line that the
entry's cross_doc_supported refs print.

CLI:
    lexicon_candidates.py --field-class ihc_marker --reading CK2O --reading CK20 [--lexicon-dir DIR]
    (a channel that read nothing: pass no --reading for it)
Output: JSON {"field_class", "lexicon", "readings", "candidates": [{text, lexicon, confidence}]}.
Exit: 0; 2 = bad invocation (unknown field class / lexicon missing).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
LEXICON_DIR_ENV = "CB_ORGANIZE_LEXICON_DIR"  # tests point this at a synthetic lexicon dir
FIELD_CLASS_LEXICON = {"drug_name": "oncology_drugs", "ihc_marker": "ihc_markers", "ln_station": "ln_stations"}
MAX_CANDIDATES = 3
AFFIXES = ("no.", "组", "站")
# written for a character a channel could not resolve; after NFKC ？ is ?
UNRESOLVED_MARKERS = ("[?]", "?", "？", "□", "�")
_UNRESOLVED_CHARS = frozenset("?□�")


def lexicon_dir() -> Path:
    env = os.environ.get(LEXICON_DIR_ENV)
    return Path(env) if env else SKILL_ROOT / "references" / "lexicons"


def load_lexicon(name: str, directory: Path | None = None) -> list[str] | None:
    """The lexicon's lines in file order (NFKC, stripped, blanks dropped); None when missing."""
    path = (directory or lexicon_dir()) / f"{name}.txt"
    try:
        return [unicodedata.normalize("NFKC", l).strip()
                for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return None


def norm(s: str) -> str:
    """Rule 1: NFKC + case fold, then strip a leading / trailing No. / 组 / 站 (repeatedly)."""
    t = unicodedata.normalize("NFKC", s).casefold().strip().replace("[?]", "?")
    changed = True
    while changed and t:
        changed = False
        for a in AFFIXES:
            if t.startswith(a):
                t, changed = t[len(a):].strip(), True
            if t.endswith(a):
                t, changed = t[:-len(a)].strip(), True
    return t


def is_partial(reading: str) -> bool:
    return any(m in unicodedata.normalize("NFKC", reading) for m in UNRESOLVED_MARKERS)


def distance(a: str, b: str) -> int:
    """Rule 2: Levenshtein; an unresolved character (?, □, U+FFFD) equals no character."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            same = ca == cb and ca not in _UNRESOLVED_CHARS
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if same else 1)))
        prev = cur
    return prev[-1]


def confidence(entry: str, readings: list[str]) -> str:
    """Rule 5 for one lexicon entry against the (non-null) readings."""
    e = norm(entry)
    dist = [(distance(e, norm(r)), r) for r in readings]
    capped = any(is_partial(r) for r in readings)
    exact = [r for d, r in dist if d == 0 and not is_partial(r)]
    if exact and all(d <= 1 for d, _ in dist):
        level = "high"
    elif exact:
        level = "medium"
    else:
        level = "low"
    if capped and level == "high":
        level = "medium"
    return level


def compute(readings, lexicon_lines: list[str], lexicon_name: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    """Rules 1-5: the ranked candidate list for these readings (null / empty readings ignored)."""
    reads = [r for r in readings if isinstance(r, str) and r.strip()]
    if not reads:
        return []
    nreads = [norm(r) for r in reads]
    ranked = []
    for order, entry in enumerate(lexicon_lines):
        e = norm(entry)
        if not e:
            continue
        threshold = 1 if len(e) <= 3 else 2
        dists = [distance(e, r) for r in nreads]
        within = sum(1 for d in dists if d <= threshold)
        if not within:
            continue
        ranked.append((min(dists), -within, order, entry))
    ranked.sort()
    return [{"text": entry, "lexicon": lexicon_name, "confidence": confidence(entry, reads)}
            for _, _, _, entry in ranked[:limit]]


def for_field_class(field_class: str, readings, directory: Path | None = None) -> list[dict] | None:
    """Candidates for an entry of `field_class` ([] for a class without a lexicon); None = lexicon missing."""
    name = FIELD_CLASS_LEXICON.get(field_class)
    if name is None:
        return []
    lines = load_lexicon(name, directory)
    if lines is None:
        return None
    return compute(readings, lines, name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lexicon candidates for one uncertain field (phase1 §5 rules 1-5).")
    ap.add_argument("--field-class", required=True, help="drug_name | ihc_marker | ln_station (others get [])")
    ap.add_argument("--reading", action="append", default=[], help="one channel's raw reading (repeat per channel)")
    ap.add_argument("--lexicon-dir", default=None, help="override references/lexicons/")
    args = ap.parse_args(argv)
    directory = Path(args.lexicon_dir) if args.lexicon_dir else None
    cands = for_field_class(args.field_class, args.reading, directory)
    if cands is None:
        print(f"ERROR: lexicon {FIELD_CLASS_LEXICON[args.field_class]}.txt not found", file=sys.stderr)
        return 2
    print(json.dumps({"field_class": args.field_class, "lexicon": FIELD_CLASS_LEXICON.get(args.field_class),
                      "readings": args.reading, "candidates": cands}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
