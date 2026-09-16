#!/usr/bin/env python3
"""merge_fields.py — 段 2 field collector: one candidate ledger, grouped by clinical_class.

WHAT THIS IS
    The deterministic half of 段 2. Every page that 段 1 transcribed carries a
    `fields: [{label, value, unit?, span}]` block in its frontmatter. This script reads
    those blocks from the MASKED copies, groups them by `clinical_class`, and writes one
    file:

        raw/_provenance/<run_id>/field_candidates.json

    Each 段 2 projection worker then reads only its own group. A `labs` worker never sees
    the molecular pages, so it cannot invent a lab value out of a variant table, and its
    context is a fraction of the archive.

WHY A SCRIPT AND NOT A WORKER (fix spec A19)
    Collecting `fields[]` is transcription of a transcription: the value is already a
    string on the page, its `span` already points at a bbox in raw/, and there is no
    judgement left to apply. Having a model re-read the sidecars to gather them costs a
    subagent per group and introduces a step at which a value can change without anything
    noticing. The LLM's job in 段 2 is PROJECTION — deciding that this page's 白细胞计数
    belongs in labs.json as WBC with this unit — and projection is exactly what a script
    cannot do. Splitting the two means the numbers a worker projects are the numbers the
    page carries, byte for byte, and `gate_field_provenance` can prove it afterwards.

IT READS THE MASKED COPY, NOT THE VERBATIM ONE
    `ocr/<sid>/page-NNN.md` (or the page's bucket location after 段 2 moved it), never
    `raw/transcript/`. The verbatim vault is for deterministic scripts and authorised
    humans; a candidate ledger is an intermediate that 段 2 workers read, so it must be
    built from the same masked surface they are allowed to see. A field whose value was
    shape-masked arrives as `[PII_MASKED]` and is recorded as such — a masked identifier
    is a fact about the page, not a gap to be filled in from somewhere else.

WHAT IT DOES NOT DO
    It does not normalize, convert units, parse dates, deduplicate across pages or decide
    which of two conflicting readings is right. Every one of those is a projection
    decision. The ledger is candidates, in page order, with their provenance attached.

USAGE
    merge_fields.py <patient_dir> --run-id <id> [--from-transcript]

Exit codes:
    0  a ledger was written (an empty ledger is valid — a text-only archive has no pages)
    1  the run manifest is missing/unreadable, or a page's masked copy could not be read
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

import _pathsafe  # noqa: E402
import ingest_transcripts as ing  # noqa: E402

# fix spec A22 — the 段 2 worker groups, keyed on clinical_class and nothing else. The
# bucket path is where a document was FILED; clinical_class is what it CONTAINS, and a
# discharge summary filed under 03_ can carry the only molecular result in the archive.
CLASS_GROUPS: dict[str, str] = {
    "lab": "labs",
    "molecular": "molecular_pathology",
    "pathology": "molecular_pathology",
    "narrative": "timeline_narrative",
    "imaging": "timeline_narrative",
    "admin": "open_fields_filing",
    "unknown": "open_fields_filing",
}


def group_for(clinical_class: str, kind: str = "known") -> str:
    """Which 段 2 worker owns this page."""
    if kind == "novel":
        # Novel material has no pinned projection target by definition, so it lands with
        # the open-field filer regardless of what class it looks like.
        return "open_fields_filing"
    return CLASS_GROUPS.get(clinical_class, "open_fields_filing")


def collect(patient_dir: Path, run_id: str, from_transcript: bool) -> tuple[int, dict]:
    prov = patient_dir / "raw" / "_provenance" / run_id
    _pathsafe.require_contained(prov, patient_dir, "provenance dir")
    man_path = prov / "transcribe-manifest.json"
    if not man_path.is_file():
        print(f"ERROR: no transcribe-manifest.json for run {run_id}", file=sys.stderr)
        return 1, {}
    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unreadable manifest: {exc}", file=sys.stderr)
        return 1, {}

    groups: dict[str, list[dict]] = {g: [] for g in sorted(set(CLASS_GROUPS.values()))}
    problems: list[dict] = []
    pages_read = 0

    for rec in manifest.get("pages", []) or []:
        if rec.get("status") != "ok":
            continue
        sid, page = rec.get("source_id"), rec.get("page")
        rel = rec.get("transcript_path") if from_transcript else rec.get("masked_path")
        if not isinstance(rel, str):
            problems.append({"source_id": sid, "page": page,
                             "issue": "manifest row has no masked_path"})
            continue
        try:
            path = _pathsafe.safe_relpath(rel, patient_dir, "page path")
        except _pathsafe.PathSafetyError as exc:
            problems.append({"source_id": sid, "page": page, "issue": str(exc)})
            continue
        if not path.is_file():
            # 段 2 may already have moved the masked copy into its bucket; the manifest's
            # `masked_path` then points at where it WAS. That is a real state, and it is
            # reported rather than guessed at — searching the archive for a file with the
            # right name is how a page from another source gets read as this one.
            problems.append({"source_id": sid, "page": page,
                             "issue": f"page copy not found at {rel} (already filed by 段 2?)"})
            continue
        try:
            fm, _body, err = ing.parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            problems.append({"source_id": sid, "page": page, "issue": f"unreadable: {exc}"})
            continue
        if fm is None:
            problems.append({"source_id": sid, "page": page, "issue": f"frontmatter: {err}"})
            continue
        pages_read += 1

        clinical_class = rec.get("clinical_class") or fm.get("clinical_class") or "unknown"
        kind = "novel" if str(rec.get("doc_kind", "")).startswith("novel:") else "known"
        group = group_for(clinical_class, kind)
        high_risk = {x for x in (fm.get("high_risk") or []) if isinstance(x, str)}
        uncertain = {x for x in (fm.get("uncertain") or []) if isinstance(x, str)}

        for f in fm.get("fields", []) or []:
            if not isinstance(f, dict):
                continue
            label = f.get("label")
            if not isinstance(label, str):
                continue
            span = f.get("span") if isinstance(f.get("span"), dict) else {}
            groups[group].append({
                "source_id": sid,
                "page": page,
                "doc_kind": rec.get("doc_kind"),
                "clinical_class": clinical_class,
                "label": label,
                # Verbatim, unnormalized. gate_field_provenance later requires every
                # labs.json raw_value to appear HERE, so any cleanup applied at this step
                # would break the very binding it exists to support.
                "value": f.get("value"),
                "unit": f.get("unit"),
                "open_ref": {"source_id": sid, "page": page, "bbox": span.get("bbox")},
                "high_risk": label in high_risk,
                "uncertain": label in uncertain,
            })

    doc = {
        "schema": "organize_field_candidates_v1",
        "run_id": run_id,
        "read_from": "raw/transcript/" if from_transcript else "ocr/ (masked)",
        "group_key": "clinical_class",
        "counts": {
            "pages_read": pages_read,
            "fields_total": sum(len(v) for v in groups.values()),
            **{f"fields_{g}": len(v) for g, v in sorted(groups.items())},
            "problems": len(problems),
        },
        "rule": (
            "Candidates only. Nothing here is normalized, deduplicated or adjudicated — "
            "that is 段 2's projection work. Each group is read by ONE worker: a labs "
            "worker never sees molecular pages, so it cannot source a lab value from a "
            "variant table. `value` is verbatim from the page's frontmatter, which is what "
            "lets gate_field_provenance bind every projected raw_value back to a page."
        ),
        "groups": {g: v for g, v in sorted(groups.items())},
        "problems": problems,
    }
    out = prov / "field_candidates.json"
    _pathsafe.require_contained(out, patient_dir, "field candidates")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return (1 if problems else 0), doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="merge_fields.py",
        description="段 2 field collector: group transcribed fields[] by clinical_class "
                    "into raw/_provenance/<run>/field_candidates.json (no LLM).",
    )
    ap.add_argument("patient_dir")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--from-transcript", action="store_true",
                    help="read the VERBATIM pages instead of the masked copies. For "
                         "deterministic auditing only — the ledger it produces must not be "
                         "handed to a 段 2 worker, which may only read masked surfaces")
    args = ap.parse_args(argv)

    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2
    try:
        _pathsafe.safe_component(args.run_id, "--run-id")
    except _pathsafe.PathSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    code, doc = collect(patient_dir, args.run_id, args.from_transcript)
    if not doc:
        return code
    c = doc["counts"]
    print(
        f"[merge_fields] run={args.run_id} pages={c['pages_read']} fields={c['fields_total']} "
        f"(labs={c['fields_labs']} molecular_pathology={c['fields_molecular_pathology']} "
        f"timeline_narrative={c['fields_timeline_narrative']} "
        f"open_fields_filing={c['fields_open_fields_filing']}) problems={c['problems']}"
    )
    print(f"[merge_fields] ledger: raw/_provenance/{args.run_id}/field_candidates.json")
    for pr in doc["problems"][:10]:
        print(f"  WARN {pr.get('source_id')} p{pr.get('page')}: {pr.get('issue')}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
