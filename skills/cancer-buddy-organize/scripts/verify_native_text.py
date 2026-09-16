#!/usr/bin/env python3
"""verify_native_text.py — faithfulness_method: native_text_identity.

WHAT THIS IS
    The cheap, exact faithfulness check for sources whose text was never guessed at: a
    .txt / .csv / native .docx payload read byte-for-byte. For those, "is the sidecar
    faithful to the source?" is not a judgement call and needs no model — the sidecar
    must be the source, character for character, except where PII was masked.

WHY IT EXISTS
    The general faithfulness pass re-reads pages with a model, which is the right tool
    for a scanned page and completely the wrong one for a 14-line text file: it costs
    subagents and minutes to re-derive something a byte comparison settles exactly. That
    mismatch is what turned a trivial text-only increment into a 30-minute, 4-worker run.
    This script is the short circuit, and it is STRICTER than what it replaces, not
    weaker: a model re-read agrees "close enough", byte identity does not.

THE MASK-AWARE COMPARISON
    A masked sidecar is not byte-identical to its source — that is the point of masking.
    So the sidecar body is split on [PII_MASKED] and the remaining segments must appear
    in the source IN ORDER, with the first anchored at the start and the last at the end
    (unless the sidecar begins/ends with a mask). That is precisely "identical except
    inside masked spans": text cannot be added, dropped, reordered or reworded anywhere
    outside a mask, and a mask can only ever stand for a contiguous run of source
    characters. Trying to compare raw bytes directly would fail on every masked file;
    comparing loosely (normalized, fuzzy) would not be identity at all.

    Only line endings (CRLF → LF) and a trailing newline are normalized, because those
    are artifacts of how a file was written, not of what it says. Whitespace, spelling,
    spacing inside numbers and every clinical character are compared exactly.

    A mask is BOUNDED, and that bound is what makes the check honest. Each [PII_MASKED]
    may stand for at most MAX_MASK_SPAN characters and may not span a newline — an
    identifier is one short run on one line. Without that bound a mask at the end of the
    sidecar would stand for "the entire rest of the file", and deleting every remaining
    line would pass as faithful. It is the one place a naive segment match silently
    inverts into the opposite of the guarantee it claims.

SCOPE
    ONLY for rows with read_mode `native_text`. A source that went through OCR or a model
    is NOT eligible: there its sidecar is genuinely a derivation, and asserting byte
    identity would either always fail or, worse, invite someone to make it pass by
    copying the derivation back over the source.

WRITES
    raw/_provenance/<run_id>/faithfulness-<source_id>.json

USAGE
    verify_native_text.py <patient_dir> <source_id> [--run-id <id>]

Exit codes:
    0  identical (modulo masked spans)
    1  NOT identical, or the source/sidecar could not be compared
    2  bad invocation
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

FAITHFULNESS_METHOD = "native_text_identity"
# A masked span stands for ONE identifier on ONE line. Generous enough for a long
# account path or an email; far too small to hide a dropped paragraph.
MAX_MASK_SPAN = 128


def _norm(text: str) -> str:
    """Normalize the ARTEFACTS of how a file was written, and nothing else (fix spec A35).

    Four classes of difference are not differences in what the document SAYS, and each one
    has produced a false NOT-IDENTICAL verdict on a faithful sidecar:

      BOM             a UTF-8 BOM on the source and not on the sidecar (or the reverse)
                      made the two files differ at offset 0, so the report pointed at line
                      1 of a file whose line 1 was correct.
      line endings    CRLF / lone CR, already handled.
      exotic breaks   U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR, U+0085 NEL,
                      \v, \f. A .docx text payload emits these; they are line breaks, and
                      comparing one against `\n` fails on every such file.
      trailing space  whitespace at end of line, which an editor strips and a writer does
                      not.

    Everything else — interior whitespace, spelling, spacing inside a number, every
    clinical character — is compared EXACTLY. This function is deliberately short: each
    line added to it removes a class of difference the check was supposed to catch, so the
    report states the normalisation it applied (`normalization` in the JSON) rather than
    leaving the reader to guess how loose "identical" was.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    text = (text.replace("\r\n", "\n").replace("\r", "\n")
                .replace("\u2028", "\n").replace("\u2029", "\n")
                .replace("\x85", "\n").replace("\v", "\n").replace("\f", "\n"))
    return "\n".join(line.rstrip(" \t") for line in text.split("\n"))


NORMALIZATION_NOTE = (
    "Normalized before comparison: UTF-8 BOM, CRLF/CR/U+2028/U+2029/U+0085/VT/FF line "
    "breaks, per-line trailing spaces and tabs, and a trailing newline. Nothing else: "
    "interior whitespace, spelling, spacing inside numbers and every clinical character "
    "are compared exactly."
)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def compare(source_text: str, sidecar_body: str, mask_token: str) -> tuple[bool, list[str]]:
    """Return (identical, diff_lines). See THE MASK-AWARE COMPARISON above."""
    src = _norm(source_text).rstrip("\n")
    side = _norm(sidecar_body).rstrip("\n")
    diffs: list[str] = []

    if mask_token not in side:
        if src == side:
            return True, diffs
        common = 0
        for a, b in zip(src, side):
            if a != b:
                break
            common += 1
        diffs.append(
            f"first difference at source line {_line_of(src, common)} (offset {common}): "
            f"source has {src[common:common + 60]!r}, sidecar has {side[common:common + 60]!r}"
        )
        return False, diffs

    segments = side.split(mask_token)
    pos = 0
    for i, seg in enumerate(segments):
        if i == 0:
            if seg and not src.startswith(seg):
                common = 0
                for a, b in zip(src, seg):
                    if a != b:
                        break
                    common += 1
                diffs.append(
                    f"first difference at source line {_line_of(src, common)} (offset {common}): "
                    f"source has {src[common:common + 60]!r}, sidecar has {seg[common:common + 60]!r}"
                )
                return False, diffs
            pos = len(seg)
            continue

        # The gap between `pos` and the next match is what this mask stands for. It must
        # look like ONE identifier: bounded length, no newline.
        if seg == "":
            # adjacent masks, or a mask at the very end — the remaining source must still
            # fit inside one masked span
            gap = src[pos:]
            if i == len(segments) - 1:
                if len(gap) > MAX_MASK_SPAN or "\n" in gap:
                    diffs.append(
                        f"the trailing [PII_MASKED] would have to stand for {len(gap)} source "
                        f"character(s)"
                        + (" spanning a line break" if "\n" in gap else "")
                        + f" (source line {_line_of(src, pos)} onward) — a mask covers one "
                        f"identifier on one line (max {MAX_MASK_SPAN} chars), so this is dropped "
                        f"source content, not redaction: {gap[:80]!r}"
                    )
                    return False, diffs
                pos = len(src)
            continue

        search_from = pos
        matched = False
        while True:
            found = src.find(seg, search_from)
            if found < 0:
                diffs.append(
                    f"sidecar text not found in the source after line {_line_of(src, pos)}: "
                    f"{seg[:80]!r}"
                )
                return False, diffs
            gap = src[pos:found]
            if len(gap) <= MAX_MASK_SPAN and "\n" not in gap:
                pos = found + len(seg)
                matched = True
                break
            search_from = found + 1
        if not matched:  # pragma: no cover - the loop only exits via break/return
            return False, diffs

    if not side.endswith(mask_token):
        if pos != len(src):
            tail = src[pos:]
            diffs.append(
                f"source has {len(tail)} unaccounted character(s) after the sidecar's last "
                f"segment (from source line {_line_of(src, pos)}) — the sidecar is missing "
                f"source content: {tail[:80]!r}"
            )
            return False, diffs
    return True, diffs


def verify(patient_dir: Path, source_id: str, run_id: str) -> tuple[int, dict]:
    try:
        import pii_rescan
    except Exception as exc:
        print(f"ERROR: cannot import pii_rescan (needed for the mask token): {exc}", file=sys.stderr)
        return 2, {}
    import _pathsafe

    # fix spec A9 / P1-1: source_id and run_id both land in a written path
    # (raw/_provenance/<run_id>/faithfulness-<source_id>.json) and both arrive from
    # outside. `--run-id ../../..` used to retarget the report anywhere on the host.
    try:
        _pathsafe.safe_component(source_id, "source_id")
        _pathsafe.safe_component(run_id, "--run-id")
    except _pathsafe.PathSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2, {}

    inv_path = patient_dir / "source_inventory.json"
    if not inv_path.is_file():
        print("ERROR: source_inventory.json not found", file=sys.stderr)
        return 1, {}
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: source_inventory.json unreadable: {exc}", file=sys.stderr)
        return 1, {}

    rows = [
        e for e in (inv.get("files") or [])
        if isinstance(e, dict) and e.get("source_id") == source_id
    ]
    if not rows:
        print(f"ERROR: no inventory row for source_id {source_id!r}", file=sys.stderr)
        return 1, {}

    results: list[dict] = []
    identical_all = True
    for row in rows:
        file_id = row.get("file_id", "<?>")
        raw_rel = row.get("raw_path")
        side_rel = row.get("sidecar_path")
        read_mode = row.get("read_mode")

        entry = {
            "file_id": file_id,
            "raw_path": raw_rel,
            "sidecar_path": side_rel,
            "read_mode": read_mode,
            "identical": False,
            "diff_lines": [],
        }
        if read_mode != "native_text":
            entry["diff_lines"] = [
                f"read_mode is {read_mode!r}, not 'native_text' — byte identity does not apply "
                "to a source whose characters were derived by OCR or a model; use the "
                "vision_second_read / sampled_reread faithfulness path instead"
            ]
            entry["skipped"] = True
            results.append(entry)
            identical_all = False
            continue

        # Both paths come from the inventory, which a model wrote. Resolve them against
        # the patient dir and refuse anything that leaves it, rather than reading whatever
        # `../../../etc/passwd` names.
        raw_path = side_path = None
        try:
            if isinstance(raw_rel, str):
                raw_path = _pathsafe.safe_relpath(raw_rel, patient_dir, "raw_path")
            if isinstance(side_rel, str):
                side_path = _pathsafe.safe_relpath(side_rel, patient_dir, "sidecar_path")
        except _pathsafe.PathSafetyError as exc:
            entry["diff_lines"] = [str(exc)]
            results.append(entry)
            identical_all = False
            continue
        if raw_path is None or not raw_path.is_file():
            entry["diff_lines"] = [f"raw source not found: {raw_rel}"]
            results.append(entry)
            identical_all = False
            continue
        if side_path is None or not side_path.is_file():
            entry["diff_lines"] = [f"sidecar not found: {side_rel}"]
            results.append(entry)
            identical_all = False
            continue
        try:
            source_text = raw_path.read_text(encoding="utf-8")
            sidecar_text = side_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            entry["diff_lines"] = [f"unreadable as UTF-8 text: {exc}"]
            results.append(entry)
            identical_all = False
            continue

        # ONE definition of "what is scaffold", shared with the PII gate (fix spec A24):
        # a divergence here means the gate and the faithfulness check disagree about which
        # bytes are content, and a byte nobody agrees on is a byte nobody checks.
        body = pii_rescan.strip_scaffold(sidecar_text)
        ok, diffs = compare(source_text, body, pii_rescan.MASK_TOKEN)
        entry["identical"] = ok
        entry["diff_lines"] = diffs
        entry["masked_spans"] = body.count(pii_rescan.MASK_TOKEN)
        results.append(entry)
        identical_all = identical_all and ok

    doc = {
        "schema": "organize_faithfulness_v1",
        "faithfulness_method": FAITHFULNESS_METHOD,
        "source_id": source_id,
        "run_id": run_id,
        "identical": identical_all,
        "diff_lines": [d for r in results for d in r.get("diff_lines", [])],
        "content_units": results,
        "normalization": NORMALIZATION_NOTE,
        # fix spec A35. A byte-identity pass is a FAITHFULNESS fact, not a second read: the
        # characters were never guessed at, so there was no reading to confirm. Writing
        # `passed_independent_reread` on the strength of it would claim an independent
        # channel confirmed a value that no channel ever read. The inventory row for a pure
        # text source therefore carries `high_risk_review_status: not_applicable`, and this
        # report is what records the faithfulness method independently.
        "inventory_high_risk_review_status": "not_applicable",
        "inventory_reread_channel": "none",
        "status_note": (
            "native_text_identity is a faithfulness method, NOT an independent second read. "
            "The inventory row for these sources must read high_risk_review_status: "
            "not_applicable — never passed_independent_reread, which asserts that a second "
            "channel re-read a value that in this path was never read at all."
        ),
        "note": (
            "Byte identity between the source and its sidecar, modulo masked spans. "
            + NORMALIZATION_NOTE
            + " A pass means the sidecar added, dropped and reworded nothing outside a "
            "[PII_MASKED] span."
        ),
    }
    out_dir = patient_dir / "raw" / "_provenance" / run_id
    _pathsafe.require_contained(out_dir, patient_dir, "provenance dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"faithfulness-{source_id}.json"
    _pathsafe.require_contained(out_path, patient_dir, "faithfulness report")
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return (0 if identical_all else 1), doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="verify_native_text.py",
        description="Byte-identity faithfulness check for native_text sources (modulo PII masks).",
    )
    ap.add_argument("patient_dir")
    ap.add_argument("source_id")
    ap.add_argument("--run-id", default="adhoc",
                    help="provenance run id the report is filed under (default: adhoc)")
    args = ap.parse_args(argv)

    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    code, doc = verify(patient_dir, args.source_id, args.run_id)
    if not doc:
        return code
    rel = f"raw/_provenance/{args.run_id}/faithfulness-{args.source_id}.json"
    if doc["identical"]:
        print(f"[verify_native_text] {args.source_id}: IDENTICAL (native_text_identity) → {rel}")
    else:
        print(f"[verify_native_text] {args.source_id}: NOT IDENTICAL → {rel}", file=sys.stderr)
        for d in doc["diff_lines"][:10]:
            print(f"  - {d}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
