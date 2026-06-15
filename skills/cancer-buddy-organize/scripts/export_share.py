#!/usr/bin/env python3
"""Safe-share export of a finished organize patient_dir (US-011).

A patient who wants to hand their organized archive to a doctor / second-opinion
service / family member needs a copy that ships ZERO raw identity — but the
organize design deliberately keeps every uploaded original **verbatim** in
`raw/`, never pixel-redacted (see references/bucket-taxonomy.md §4-§5: the only
desensitization of the archived data is the text masking in the `.md` sidecars,
plus the decade-band coarse-graining in the patient-facing 段D HTML). The raw
images still carry the patient's name, IDs, hospital headers, barcodes —
unredacted by design.

So the safe-share path is **exclusion, not redaction**: we never try to pixel-
redact `raw/` (lossy, unverifiable, and not what raw/ is for). We ship only the
text-masked surfaces (buckets' `.md` sidecars + the structured JSONs + the
coarse-grained HTML) and leave the verbatim originals behind entirely. To make
that safe we FIRST run the deterministic acceptance gate
(`validate_structured_outputs.py`) — which includes the PII residue rescan of the
sidecars AND the delivered-surface scan (INDEX.md / source_inventory.json /
dotfiles / 病情简要总结.html). If that gate fails, a name/email/path leak could
ship, so we ABORT and export nothing. Only a clean run is exportable.

What is EXCLUDED from the export (never copied to <dest>):
  - raw/                      verbatim un-redacted originals — the whole point of
                              exclusion-not-redaction
  - .DS_Store                 macOS Finder cruft (any depth)
  - empty ocr/                Phase-1 staging dir, should already be drained+gone;
                              an empty leftover is dropped (a non-empty ocr/ means
                              the run is unfinished — the gate above would already
                              have flagged stranded sidecars / inventory mismatch)
  - .case_summary_data.json   hidden 段D render intermediate (build artifact, never
                              a Q&A source — SKILL.md patient-dir file map)
  - .rename_plan.json         Phase-2 dotfile: bucketing plan (provenance only)
  - .phase1_sources.json      Phase-1 dotfile: slice→source map (provenance only)
  - .identity_denylist.json   the patient-identity deny-list seed — must NEVER ship
                              (it literally lists identity tokens)

Everything else is copied: the 14 buckets + 99_ quarantine, INDEX.md / AGENTS.md /
profile.json / readiness.json / the 6+ structured JSONs / timeline.* / case_text.md /
review_summary.md / review_flags.md / missing_items.json / source_inventory.json /
update_log.json / 病情简要总结.html (the current root summary, PII-gated).
(case_summary_versions/ dated snapshots are EXCLUDED — see EXCLUDE_TOPLEVEL: they are
local-only history and are not re-scanned by the gate, so they never ship.)

Usage:
    python3 scripts/export_share.py <patient_dir> --out <dest_dir>

Exit codes:
    0  — export written to <dest_dir>
    1  — acceptance gate failed (nothing exported) OR copy error
    2  — bad invocation
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Make the sibling acceptance gate importable (it lives next to us).
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Top-level entries excluded entirely (raw/ vault + hidden render/provenance dotfiles).
EXCLUDE_TOPLEVEL = {
    "raw",
    ".case_summary_data.json",
    ".rename_plan.json",
    ".phase1_sources.json",
    ".identity_denylist.json",
    # Dated immutable patient-facing snapshots accumulate across runs and old ones
    # are never re-rendered or re-scanned, so a snapshot written before a PII-gate
    # upgrade could carry PII the current gate would catch. The gate only scans the
    # CURRENT root 病情简要总结.html, so shipping unscanned snapshots would falsify
    # the "no PII ships" guarantee. Version history is a LOCAL archival concern —
    # the export ships only the current, scanned root summary.
    "case_summary_versions",
}

# Names dropped at ANY depth during the copy.
EXCLUDE_ANY_DEPTH = {".DS_Store"}


def _run_acceptance_gate(patient_dir: Path) -> bool:
    """Run validate_structured_outputs.py on patient_dir. Return True iff it passes.

    Prefer importing it as a sibling module (one process, no subprocess cost / PATH
    surprises); fall back to a subprocess if import is unavailable. Either way the
    PASS condition is the gate's own exit/return code == 0.
    """
    try:
        import validate_structured_outputs as gate  # sibling module
    except Exception:
        gate = None

    if gate is not None and hasattr(gate, "main"):
        # gate.main() reads sys.argv, so set it for the call and restore after.
        saved_argv = sys.argv
        try:
            sys.argv = ["validate_structured_outputs.py", str(patient_dir)]
            rc = gate.main()
        finally:
            sys.argv = saved_argv
        return rc == 0

    # Fallback: run it as a subprocess.
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_structured_outputs.py"), str(patient_dir)]
    )
    return proc.returncode == 0


def _is_empty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and not any(path.iterdir())
    except OSError:
        return False


def _ignore_factory(included: list[str], excluded: list[str], patient_dir: Path):
    """shutil.copytree ignore callback: drop EXCLUDE_ANY_DEPTH names + empty ocr/,
    recording what was kept vs skipped for the summary."""

    def _ignore(src_dir: str, names: list[str]) -> set[str]:
        src_path = Path(src_dir)
        skip: set[str] = set()
        for name in names:
            child = src_path / name
            if name in EXCLUDE_ANY_DEPTH:
                skip.add(name)
                continue
            # Top-level raw/ + render/provenance dotfiles: skip DURING copy so the
            # verbatim un-redacted originals are NEVER written to <dest>, not even
            # transiently (copytree DOES invoke ignore for the root dir).
            if src_path == patient_dir and name in EXCLUDE_TOPLEVEL:
                skip.add(name)
                excluded.append(name + "/" if child.is_dir() else name)
                continue
            # Drop an empty ocr/ staging leftover (only at the patient-dir root).
            if name == "ocr" and src_path == patient_dir and _is_empty_dir(child):
                skip.add(name)
                excluded.append("ocr/ (empty staging leftover)")
                continue
        # Record top-level inclusions for the summary (only at the root level).
        if src_path == patient_dir:
            for name in sorted(names):
                if name in skip or name in EXCLUDE_TOPLEVEL:
                    continue
                child = src_path / name
                included.append(name + "/" if child.is_dir() else name)
        return skip

    return _ignore


def export_share(patient_dir: Path, dest_dir: Path) -> int:
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    # (a) FIRST gate — never ship a dir that can leak PII / paths.
    print(f"[export_share] running acceptance gate on {patient_dir} ...")
    if not _run_acceptance_gate(patient_dir):
        print(
            "ERROR: acceptance gate FAILED — refusing to export (a PII / path leak "
            "could ship). Fix the gate findings above and re-run.",
            file=sys.stderr,
        )
        return 1

    if dest_dir.exists():
        print(
            f"ERROR: destination already exists: {dest_dir} — choose a fresh --out path",
            file=sys.stderr,
        )
        return 1

    # (b) copy, excluding raw/ + render/provenance dotfiles at the top level, and
    # .DS_Store / empty ocr/ at any depth.
    included: list[str] = []
    excluded: list[str] = []
    ignore = _ignore_factory(included, excluded, patient_dir)

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Copy the patient_dir into dest_dir, then prune the excluded top-level
        # entries. (copytree's ignore can't see top-level names against patient_dir
        # the same way for the synthetic root, so we prune them explicitly.)
        shutil.copytree(patient_dir, dest_dir, ignore=ignore, symlinks=False)
    except Exception as e:
        print(f"ERROR: copy failed: {e}", file=sys.stderr)
        # leave no partial export behind
        shutil.rmtree(dest_dir, ignore_errors=True)
        return 1

    # Prune the explicit top-level exclusions that may have been copied.
    for name in sorted(EXCLUDE_TOPLEVEL):
        target = dest_dir / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            excluded.append(f"{name}/")
        elif target.exists():
            try:
                target.unlink()
                excluded.append(name)
            except OSError:
                pass

    # (c) summary.
    print(f"\n[export_share] safe-share export written to: {dest_dir}")
    print(f"  INCLUDED ({len(included)} top-level entries):")
    for name in included:
        print(f"    + {name}")
    print("  EXCLUDED (never shipped):")
    print("    - raw/ (verbatim un-redacted originals — exclusion, not redaction)")
    for name in sorted(set(excluded)):
        if name.rstrip("/") == "raw":
            continue
        print(f"    - {name}")
    print(
        "    - .case_summary_data.json / .rename_plan.json / .phase1_sources.json / "
        ".identity_denylist.json (hidden render/provenance/identity dotfiles)"
    )
    print("    - .DS_Store (any depth)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safe-share export of a finished organize patient_dir "
        "(excludes raw/ + render/provenance dotfiles; aborts if the acceptance "
        "gate fails so no PII/path leak ships)."
    )
    parser.add_argument("patient_dir", help="absolute path to the patient directory")
    parser.add_argument(
        "--out", required=True, dest="out", help="destination directory (must not already exist)"
    )
    args = parser.parse_args()

    patient_dir = Path(args.patient_dir).resolve()
    dest_dir = Path(args.out).resolve()
    return export_share(patient_dir, dest_dir)


if __name__ == "__main__":
    sys.exit(main())
