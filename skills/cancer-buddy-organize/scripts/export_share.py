#!/usr/bin/env python3
"""Create a purpose-limited export from an organized patient directory.

This helper is not an authorization system and does not prove anonymity. The
calling host must authenticate the actor, verify authority, obtain the patient's
scoped confirmation, enforce expiry/revocation, and append its own audit event.

The exporter:
  * requires an explicit allowlist (`--include`) rather than copying the archive;
  * refuses `raw/`, build intermediates, identity maps, and version history.
    `raw/transcript/` (the verbatim, UNMASKED per-page transcription) and
    `raw/_cache/` (cached model transcription output, equally unmasked) are named
    explicitly: they are the highest-value plaintext in the archive and an export
    is precisely the boundary they must never cross;
  * excludes `15_未分类资料/` (the open archive) BY DEFAULT even though its `.md`
    sidecars are masked like any other. Open-world material is by definition the
    material nobody classified, so its relevance to a declared purpose has not been
    established; shipping it by reflex would widen a purpose-limited export into a
    dump. `--include-unclassified` turns it on as a deliberate, recorded act;
  * runs the structural acceptance gate before copying;
  * writes a manifest describing the declared recipient, purpose, expiry,
    authorization reference, and selected paths.

Usage:
  python3 export_share.py PATIENT_DIR --out DEST \
    --include profile.json --include 04_诊断与分期/病理报告/report.md \
    --recipient "receiving-center" --purpose "second-opinion" \
    --expires-at 2026-08-01T00:00:00Z --authorization-ref consent-123

  # opt in to the open archive (masked .md only), when the purpose genuinely needs it:
  python3 export_share.py PATIENT_DIR --out DEST --include-unclassified \
    --include 15_未分类资料/肠道菌群/report.md ...
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _pathsafe  # noqa: E402

FORBIDDEN_TOPLEVEL = {
    "raw",
    "ocr",
    "case_summary_versions",
    ".case_summary_data.json",
    ".visit_prep_data.json",
    # Retired in v4 (fix spec A17): these two 段 1 build intermediates are no longer
    # produced, and the PII scan surfaces dropped them. They stay on the REFUSAL list
    # anyway — a denylist entry for a file that should not exist costs nothing, and an
    # archive carried over from v3 still has them on disk.
    ".rename_plan.json",
    ".phase1_sources.json",
    ".identity_denylist.json",
    "alias_map.json",
}
FORBIDDEN_ANY_DEPTH = {".DS_Store", "_FILENAME_MAPPING.md"}
# Named explicitly even though `raw` already blocks them at the top level: these two
# hold UNMASKED character truth (the verbatim page transcription and the model-output
# cache). A future refactor that loosens the `raw` rule must still trip over these,
# and the operator deserves an error that says what it actually refused.
FORBIDDEN_PATH_PREFIXES = {
    "raw/transcript/": (
        "verbatim per-page transcription (unmasked source text; it lives under raw/ so it "
        "inherits the vault's access control and is never exportable)"
    ),
    "raw/_cache/": (
        "cached model transcription output (unmasked; a cache is not a deliverable)"
    ),
}
# The open archive. Masked like any other sidecar, but excluded unless asked for.
OPEN_DOMAIN_PREFIX = "15_"

# Every membership test below is done on a CASEFOLDED string (fix spec P0-5). macOS APFS
# and Windows NTFS are case-INSENSITIVE by default, so `RAW/transcript/s001/page-001.md`
# and `Raw/_cache/x.md` open exactly the file the allowlist exists to refuse while
# matching none of its literal prefixes. The refusal must be decided on the same
# equivalence the filesystem uses, or the check is decorative on two of three platforms.
#
# casefold() rather than lower(): lower() leaves ﬁ (U+FB01) and ẞ alone, and a
# case-insensitive filesystem does not.
_FORBIDDEN_TOPLEVEL_CF = {x.casefold() for x in FORBIDDEN_TOPLEVEL}
_FORBIDDEN_ANY_DEPTH_CF = {x.casefold() for x in FORBIDDEN_ANY_DEPTH}
_FORBIDDEN_PREFIXES_CF = {k.casefold(): (k, v) for k, v in FORBIDDEN_PATH_PREFIXES.items()}
_OPEN_DOMAIN_PREFIX_CF = OPEN_DOMAIN_PREFIX.casefold()


def _true_spelling(patient_dir: Path, rel: Path) -> Path | None:
    """The path as the FILESYSTEM spells it, or None if it does not exist.

    Casefolding the requested string closes the direct bypass, but a second one remains:
    on a case-insensitive filesystem the requested spelling and the real spelling can
    differ in ways no string rule anticipates, and everything downstream (the manifest,
    the copied filename, a later re-scan keyed on the path) would then record a name that
    is not the file's name. Walking the real directory entries and matching case-
    insensitively returns the on-disk spelling, which is then re-checked against every
    rule. A path that exists under a different spelling is judged as what it IS.
    """
    current = patient_dir
    parts: list[str] = []
    for want in rel.parts:
        try:
            entries = os.listdir(current)
        except OSError:
            return None
        match = next((e for e in entries if e == want), None)
        if match is None:
            match = next((e for e in entries if e.casefold() == want.casefold()), None)
        if match is None:
            return None
        parts.append(match)
        current = current / match
    return Path(*parts)


def _forbidden_reason(rel: Path) -> str | None:
    """Every allowlist rule, applied to ONE spelling of a relative path."""
    posix_cf = rel.as_posix().casefold()
    for prefix_cf, (prefix, why) in _FORBIDDEN_PREFIXES_CF.items():
        if posix_cf.startswith(prefix_cf):
            return f"{prefix} is {why}"
    if not rel.parts or rel.parts[0].casefold() in _FORBIDDEN_TOPLEVEL_CF:
        return f"{rel.parts[0] if rel.parts else rel!s} is not exportable"
    if any(part.casefold() in _FORBIDDEN_ANY_DEPTH_CF for part in rel.parts):
        return "the path contains a protected filename"
    return None


def _run_acceptance_gate(patient_dir: Path) -> bool:
    try:
        import validate_structured_outputs as gate
    except Exception:
        gate = None

    if gate is not None and hasattr(gate, "main"):
        saved_argv = sys.argv
        try:
            sys.argv = ["validate_structured_outputs.py", str(patient_dir)]
            return gate.main() == 0
        finally:
            sys.argv = saved_argv

    import subprocess

    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_structured_outputs.py"), str(patient_dir)]
    ).returncode == 0


def _parse_expiry(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--expires-at must be ISO-8601") from exc
    now = dt.datetime.now(dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    if parsed <= now:
        raise argparse.ArgumentTypeError("--expires-at must be in the future")
    return value


def _resolve_includes(
    patient_dir: Path, requested: list[str], include_unclassified: bool = False
) -> list[tuple[Path, Path]]:
    selected: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for raw_rel in requested:
        rel = Path(raw_rel)
        if rel.is_absolute() or rel == Path(".") or ".." in rel.parts:
            raise ValueError(f"unsafe include path: {raw_rel}")

        # Judge BOTH spellings: the one that was asked for, and the one the filesystem
        # actually has. On a case-insensitive volume they can differ, and the rule must
        # hold for whichever one is used later (fix spec P0-5).
        spellings = [rel]
        real_rel = _true_spelling(patient_dir, rel)
        if real_rel is not None and real_rel != rel:
            spellings.append(real_rel)

        for candidate_rel in spellings:
            why = _forbidden_reason(candidate_rel)
            if why:
                extra = ""
                if candidate_rel != rel:
                    extra = (f" (requested as {raw_rel!r}, but the filesystem spells it "
                             f"{candidate_rel.as_posix()!r}; a case-insensitive volume opens "
                             "the same file either way)")
                raise ValueError(f"forbidden export path: {raw_rel} — {why}{extra}")

            if candidate_rel.parts[0].casefold().startswith(_OPEN_DOMAIN_PREFIX_CF):
                if candidate_rel.suffix.casefold() != ".md":
                    raise ValueError(
                        f"forbidden export path: {raw_rel} — only the masked .md sidecar under "
                        f"{candidate_rel.parts[0]}/ is ever exportable; originals stay in raw/"
                    )
                if not include_unclassified:
                    raise ValueError(
                        f"unclassified-archive path excluded by default: {raw_rel} — "
                        f"{candidate_rel.parts[0]}/ holds material no pinned domain fit, so its "
                        "relevance to this export's declared purpose is unestablished. Pass "
                        "--include-unclassified to ship it deliberately"
                    )

        candidate = patient_dir / rel
        if candidate.is_symlink():
            raise ValueError(f"symbolic links are not exportable: {raw_rel}")
        # A HARD link is not a symlink and resolve() does not follow it, so the
        # realpath boundary check below cannot see it. Without this,
        # `ln raw/secret.txt 14_.../x.txt` exports a raw original while the
        # manifest still claims raw_originals_included=false — the one real
        # mechanical gate making a promise it did not keep.
        if candidate.is_file() and candidate.stat().st_nlink > 1:
            raise ValueError(f"hard-linked files are not exportable: {raw_rel}")
        src = candidate.resolve()
        if not _pathsafe.contained(src, patient_dir):
            raise ValueError(f"include escapes patient directory: {raw_rel}")
        try:
            resolved_rel = src.relative_to(patient_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"include escapes patient directory: {raw_rel}") from exc
        # The post-resolve spelling is the authoritative one — a symlink-free path that
        # resolved into raw/ under any casing is refused here even if the requested
        # string looked innocent.
        why = _forbidden_reason(resolved_rel)
        if why:
            raise ValueError(f"include resolves to protected path: {raw_rel} — {why}")
        if not src.exists():
            raise ValueError(f"include does not exist: {raw_rel}")
        if not src.is_file():
            raise ValueError(f"include must name one regular file: {raw_rel}")
        if src in seen:
            continue
        seen.add(src)
        selected.append((rel, src))

    return selected


# fix spec B7 — which runs count as a "same-class" PII verdict.
#
# A `full` run and an increment that brought in PIXEL pages are the runs whose content the
# semantic pass has to cover. A `conversation_incremental` (chat text the patient typed)
# and a `migration` (which reads no page content at all) are not: neither one can look at
# a scanned discharge summary, so neither one's `clean` is evidence about that summary.
#
# This distinction is the entire fix. The previous check kept only the LAST verdict of any
# kind, so `full → deferred` followed by a two-line conversation increment recording
# `clean` exported an archive whose images nobody had ever semantically scanned — and the
# chat increment is the cheapest run in the system to produce.
_HEAVY_READ_MODES_EXCLUDED = {"native_text"}


def _run_is_anchor(run: dict) -> bool:
    """A `full` run, or an increment that added a source that is not native_text.

    These are the runs that set the clock: everything from the most recent one onward is
    what the current archive's PII state actually rests on.
    """
    if run.get("run_mode") == "full":
        return True
    for src in run.get("added_sources") or []:
        if not isinstance(src, dict):
            return True          # unparseable provenance is treated as the heavy case
        if src.get("read_mode") not in _HEAVY_READ_MODES_EXCLUDED:
            return True
    return False


def _debt_is_heavy(run: dict) -> bool:
    """A deferral that only a full / image run can pay off.

    `migration` is heavy even though it adds no sources, and deliberately so: a migration
    declares that NOTHING in the archive has been scanned under the v4 surface list, so the
    debt it records is archive-wide. Letting a later conversation increment clear it would
    turn the migration's honest "nobody has looked" into "somebody looked".
    """
    return _run_is_anchor(run) or run.get("run_mode") == "migration"


def _pii_deferred_blocks_export(patient_dir: Path) -> str | None:
    """Refuse the export when a `pii_semantic` debt has not been paid by a same-class run.

    `deferred` is an audited shortcut for a text-only increment: the semantic PII pass is
    postponed to the next full run. It is NOT a state an export may ship from, and the
    aggregate acceptance gate is the wrong place to enforce that on its own — a gate can
    be satisfied by a later unrelated run, and export is a one-way boundary with a
    different risk profile (the data leaves the vault and no later pass can reach it).

    So this check is INDEPENDENT and deliberately duplicated. It works in three steps
    (fix spec A6 as amended by B7):

      1. ANCHOR. Find the most recent run that is a `full` or that added a non-native_text
         source. Everything before it describes an archive state that has since been
         superseded; everything from the anchor ONWARD is the state being exported.
      2. DEBTS. From the anchor (inclusive), every run whose `pii_semantic` is `deferred`
         or `failed` records a debt, classed heavy or light.
      3. PAYMENT. A later `clean` pays a debt only if it is at least the debt's class. A
         light (conversation / text-only) `clean` can never pay a heavy debt.

    A MISSING OR MALFORMED update_log.json is now a REFUSAL, not a pass (B7). The previous
    `return None` meant that deleting one file — or writing `"runs": {}` — bought an
    unconditional export, which made every rule above advisory. An archive that cannot say
    what was done to it cannot be cleared to leave the vault.

    The same reasoning closes the two remaining ways to say nothing and be believed:
    `"runs": []` (a well-formed log with no history) and a run that omits `pii_semantic`
    (a well-formed run with no verdict). Both used to fall through to `return None`.
    """
    log = patient_dir / "update_log.json"
    if not log.is_file():
        return (
            "update_log.json is missing. It is the only place the archive records whether "
            "the semantic PII pass ever ran, so without it there is no evidence the export "
            "is clean — and an absent file must never read as an absent problem"
        )
    try:
        data = json.loads(log.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"update_log.json could not be read ({exc.__class__.__name__}: {exc})"
    runs = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        return (
            "update_log.json has no runs[] array — the archive cannot say which run "
            "produced it, or whether that run's semantic PII pass was ever performed"
        )
    runs = [r for r in runs if isinstance(r, dict)]

    # ---- an EMPTY runs[] is not a clean archive ---------------------------------
    # `"runs": []` passed every check below by having nothing to check: the anchor scan
    # found no anchor, the debt loop iterated zero times, and the function returned None —
    # i.e. cleared for export. That is the same bypass the missing-file branch above
    # closes, one line further in, and it is CHEAPER to reach: `{"runs": []}` is a
    # well-formed file that satisfies the schema, so nothing else in the pipeline objects.
    # An archive with no recorded run has never had a semantic PII pass, by definition.
    if not runs:
        return (
            "update_log.json records no runs (no runs recorded). An archive with an empty "
            "runs[] has never recorded a semantic PII pass — there is no run that could "
            "have performed one — so there is no evidence this export is clean. Run "
            "organize and record the run before exporting"
        )

    # ---- every run must STATE its PII verdict ------------------------------------
    # fix spec A6 makes this check independent of the aggregate gate, and independence is
    # worth nothing if a missing key reads as a pass. `run.get("pii_semantic")` returned
    # None for a run that simply omitted the field, and None matches neither the
    # deferred/failed arm nor the clean arm — so the run recorded no debt AND paid none,
    # and an archive could be exported on the strength of a run that said nothing at all
    # about PII. Silence is the one verdict this boundary must never accept: `deferred`
    # blocks the export, `failed` blocks it, and the absence of the key must not be the
    # only way to get past both.
    missing = [str(r.get("run_id") or f"#{i}") for i, r in enumerate(runs)
               if "pii_semantic" not in r]
    if missing:
        return (
            f"update_log.json run(s) {', '.join(missing)} carry no `pii_semantic` key. "
            "Every run must state its semantic-PII verdict (clean | deferred | failed); a "
            "run that omits it asserts nothing, and an export must not be cleared by a "
            "run that said nothing. Record the verdict, or re-run the pass "
            "(references/pii-rescan-prompt.md) and record `clean`"
        )

    anchor = 0
    for i, run in enumerate(runs):
        if _run_is_anchor(run):
            anchor = i

    heavy_debt: tuple | None = None
    light_debt: tuple | None = None
    for run in runs[anchor:]:
        verdict = run.get("pii_semantic")
        if verdict in ("deferred", "failed"):
            record = (verdict, run.get("run_id"), run.get("run_mode"))
            if _debt_is_heavy(run):
                heavy_debt = record
            else:
                light_debt = record
        elif verdict == "clean":
            light_debt = None
            if _run_is_anchor(run):
                heavy_debt = None

    debt = heavy_debt or light_debt
    if debt:
        state, run_id, mode = debt
        scope = ("a full / image run" if debt is heavy_debt
                 else "a later run")
        return (
            f"run {run_id!r} (run_mode={mode!r}) recorded pii_semantic: {state}, and no "
            f"subsequent {scope} has recorded `clean` for it. The semantic PII pass is "
            "fail-closed and an export is one-way: run the pass "
            "(references/pii-rescan-prompt.md) and record `pii_semantic: clean` on a run "
            "of at least the same class before exporting. A conversation-only or migration "
            "`clean` cannot clear a full/image deferral — neither of those runs reads a page"
        )
    return None


def export_share(
    patient_dir: Path,
    dest_dir: Path,
    includes: list[str],
    *,
    recipient: str,
    purpose: str,
    expires_at: str,
    authorization_ref: str,
    include_unclassified: bool = False,
) -> int:
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2
    if dest_dir.exists():
        print(f"ERROR: destination already exists: {dest_dir}", file=sys.stderr)
        return 1
    if dest_dir == patient_dir or dest_dir.is_relative_to(patient_dir):
        print("ERROR: export destination must be outside the patient directory", file=sys.stderr)
        return 2
    if not all(value.strip() for value in (recipient, purpose, authorization_ref, expires_at)):
        print(
            "ERROR: recipient, purpose, authorization-ref and expires-at must be non-empty",
            file=sys.stderr,
        )
        return 2
    # The CLI parses/validates --expires-at, but the library entrypoint is what the
    # unit tests (and any programmatic caller) use — re-validate here so a future
    # expiry can never be skipped by calling export_share() directly.
    try:
        _parse_expiry(expires_at)
    except argparse.ArgumentTypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        selected = _resolve_includes(patient_dir, includes, include_unclassified)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not selected:
        print("ERROR: at least one permitted --include is required", file=sys.stderr)
        return 2

    # fix spec A6 — checked BEFORE the acceptance gate, and independently of it.
    blocked = _pii_deferred_blocks_export(patient_dir)
    if blocked:
        print(f"ERROR: export refused — {blocked}", file=sys.stderr)
        return 1

    print(f"[export_share] running structural acceptance gate on {patient_dir} ...")
    if not _run_acceptance_gate(patient_dir):
        print("ERROR: acceptance gate failed; nothing exported", file=sys.stderr)
        return 1

    try:
        dest_dir.mkdir(parents=True, exist_ok=False)
        for rel, src in selected:
            dst = dest_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        manifest = {
            "schema": "cancer_buddy_purpose_limited_export_v1",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "recipient": recipient,
            "purpose": purpose,
            "expires_at": expires_at,
            "authorization_ref": authorization_ref,
            "included_paths": [rel.as_posix() for rel, _ in selected],
            "raw_originals_included": False,
            "verbatim_transcripts_included": False,
            "unclassified_archive_opted_in": bool(include_unclassified),
            "notice": (
                "This is a purpose-limited, explicitly selected export. It may still contain direct "
                "or indirect identifiers and is not guaranteed de-identified or anonymous. The host "
                "must enforce authorization, expiry, revocation, and audit."
            ),
        }
        (dest_dir / "_SHARE_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print(f"ERROR: export failed: {exc}", file=sys.stderr)
        shutil.rmtree(dest_dir, ignore_errors=True)
        return 1

    print(f"[export_share] purpose-limited export written to: {dest_dir}")
    for rel, _ in selected:
        print(f"  + {rel.as_posix()}")
    print("  - raw/ (incl. raw/transcript/ verbatim text and raw/_cache/) and protected "
          "provenance/build files were not eligible")
    if not include_unclassified:
        print("  - 15_未分类资料/ excluded by default (pass --include-unclassified to ship it)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a purpose-limited patient-record export")
    parser.add_argument("patient_dir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--include", action="append", required=True, help="relative path; repeatable")
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--expires-at", required=True, type=_parse_expiry)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument(
        "--include-unclassified",
        action="store_true",
        help=(
            "allow masked .md sidecars under 15_未分类资料/ (the open archive) to be included. "
            "Off by default: open-world material is what nobody classified, so its fit to the "
            "declared purpose has not been established. raw/transcript/ and raw/_cache/ stay "
            "refused regardless of this flag."
        ),
    )
    args = parser.parse_args()

    return export_share(
        Path(args.patient_dir).resolve(),
        Path(args.out).resolve(),
        args.include,
        recipient=args.recipient,
        purpose=args.purpose,
        expires_at=args.expires_at,
        authorization_ref=args.authorization_ref,
        include_unclassified=args.include_unclassified,
    )


if __name__ == "__main__":
    sys.exit(main())
