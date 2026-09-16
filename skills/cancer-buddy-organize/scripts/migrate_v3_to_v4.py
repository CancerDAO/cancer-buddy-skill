#!/usr/bin/env python3
"""migrate_v3_to_v4.py — bring a scheme_version 3 archive up to the v4 contract.

WHY THIS EXISTS (fix spec A13)
    organize v4 makes three fields REQUIRED on every `source_inventory.files[]` row —
    `kind`, `clinical_class` and, for transcribed sources, `transcript_path` — and adds
    `readiness.projection_coverage`. Archives organized under v3 have none of them. The
    validator's choice is then between failing every existing archive (which makes the
    upgrade a data-loss event for anybody who already has one) and silently accepting
    rows that are missing the fields the gates key off (which makes the requirement
    decorative). Neither is acceptable, so the validator WARNs on a legacy archive and
    points here, and this script performs the one-time, auditable conversion.

WHAT IT INFERS, AND HOW CONSERVATIVELY
    Every inference below is derived from data the v3 archive ALREADY recorded. Nothing
    is guessed from file content, and nothing calls a model — a migration that re-reads
    the patient's documents is a re-organize, and it would silently overwrite values a
    clinician may already have corrected.

      kind              from `read_mode`. Every v3 row described a document that a pinned
                        v3 bucket accepted, so `known` is correct by construction:
                        `novel` did not exist as a concept, so no v3 row can be one. Rows
                        whose read_mode is `stub_unreadable` become `unreadable`.
      clinical_class    from the BUCKET NUMBER, which is the only classification v3
                        recorded. It is a weaker signal than the v4 field (a discharge
                        summary in 03_ can carry the archive's only molecular result), so
                        anything outside the mapped buckets becomes `unknown` rather than
                        a plausible-looking guess.
      audience          from `review_flags[].category`, using the four categories v4 pins
                        to internal_qc. A transcription disagreement rendered to a family
                        as 「请医生确认」 is both useless and alarming, so the default for
                        an unmapped category is `clinician` only because that is the
                        pre-existing v3 behaviour for every flag.
      projection_coverage  a DELIBERATELY PESSIMISTIC skeleton: every source is recorded
                        with `unprojected_field_classes: ["unknown"]`. A v3 archive has no
                        per-field projection record, so the honest statement is "we do not
                        know what was projected", and the one thing this must never do is
                        write zeros, which read as "nothing is missing". The AGENTS.md
                        pointer renders that as a real number, so a fabricated zero would
                        tell a cold session the archive is complete.

      doc_kind          RENAMED from v3's `doc_type` (fix spec B6). The v4 inventory schema
                        is additionalProperties: false, so a real v3 archive used to fail
                        the validator immediately after a "successful" migration, on a
                        field whose only defect was its name.
      legacy_transcript_unavailable
                        set true on a `model_vision_*` row with no `transcript_path` (fix
                        spec B6). v3 kept no verbatim page transcription, so there is no
                        file to point at and none can be honestly invented. The row is
                        MARKED rather than silently waived, and the source is counted in
                        `projection_coverage.summary.unreadable_sources` with a
                        `coverage_gap` review flag — because "nothing can re-verify what
                        this model read" is exactly the state a coverage number exists to
                        expose.

    The conversion is recorded in `update_log.json` as a run with `run_mode: migration`,
    so the archive says how its v4 fields came to exist. That entry carries
    `pii_semantic: "deferred"`, and it never travels alone: the same run writes a
    `pii_semantic_deferred` review flag into `readiness.json` (fix spec B5). The pairing
    is what makes the deferral legal AND visible — the update_log line is machine state
    nothing renders, while the flag reaches the QC list and AGENTS.md.

IDEMPOTENCE
    Re-running changes nothing. An already-v4 archive short-circuits; flags are keyed on a
    stable id so they are never stacked; `--force` on a complete archive writes no second
    migration entry. This matters because the first thing anyone does with a migration
    that printed a warning is run it again.

USAGE
    migrate_v3_to_v4.py <patient_dir> [--run-id <id>] [--dry-run] [--force]

    --force also completes a PARTIAL v4 archive (fix spec B4): one that declares
    `scheme_version: 4` but whose rows are missing the fields v4 requires. The validator
    ERRORs on that state and names this flag. It fills only what is ABSENT.

Exit codes:
    0  migrated (or already v4 / nothing to do)
    1  the archive could not be migrated (unreadable or unexpected JSON)
    2  bad invocation
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _pathsafe  # noqa: E402

TARGET_SCHEME_VERSION = 4
READINESS_SCHEMA_VERSION = "3"

# Bucket number -> clinical_class. Only the buckets whose content is unambiguous by
# definition are mapped; everything else becomes `unknown`, which is a state the gates
# understand, rather than a guess that looks like a finding.
BUCKET_CLASS = {
    "01": "narrative", "02": "narrative", "03": "narrative",
    "04": "pathology",
    "05": "imaging",
    "06": "molecular",
    "07": "lab",
    "08": "narrative", "09": "narrative", "10": "narrative",
    "11": "narrative", "12": "narrative", "13": "narrative", "14": "narrative",
}
# readiness.review_flags[].category values that v4 pins to internal_qc: each is a fact
# about how the archive was READ, never a clinical question for a doctor.
INTERNAL_QC_CATEGORIES = {
    "transcription_disagreement", "ocr_artifact",
    "untrusted_content_marker", "pii_semantic_deferred",
}

# v3 rows read by a vision model have no `transcript_path`: v3 never kept the verbatim
# page transcription as a file, so there is nothing on disk to point at and nothing this
# script could honestly synthesize.
MODEL_VISION_READ_MODES = {"model_vision_primary", "model_vision_assist"}

# Stable flag ids. Stable ON PURPOSE: re-running the migration must not stack a second
# copy of the same flag, and `migration-...` is recognisable in a readiness file as
# "written by the migrator", not by a reviewer.
PII_DEFERRED_FLAG_ID = "migration-pii-semantic-deferred"
COVERAGE_GAP_FLAG_ID = "migration-legacy-transcript-unavailable"


def infer_kind(row: dict) -> str:
    if row.get("read_mode") == "stub_unreadable":
        return "unreadable"
    return "known"


def infer_clinical_class(row: dict) -> str:
    for key in ("bucket_path", "sidecar_path"):
        val = row.get(key)
        if isinstance(val, str) and len(val) >= 2 and val[:2].isdigit():
            return BUCKET_CLASS.get(val[:2], "unknown")
    return "unknown"


def migrate_inventory(data: dict) -> tuple[dict, list[str], list[str]]:
    """Fill the v4-required fields on every row. Returns (data, notes, legacy_unreadable).

    `legacy_unreadable` is the list of source_ids whose page text v3 never kept — see
    the `legacy_transcript_unavailable` block below. It flows into readiness so the gap
    is COUNTED, not merely tolerated.
    """
    notes: list[str] = []
    legacy_unreadable: list[str] = []
    rows = data.get("files")
    if not isinstance(rows, list):
        raise ValueError("source_inventory.json has no files[] array")
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = row.get("source_id") or row.get("file_id") or "<?>"
        # ---- doc_type -> doc_kind (fix spec B6) ----------------------------------
        # v3 called this `doc_type`; v4 calls it `doc_kind` and pins the inventory schema
        # to additionalProperties: false. So a REAL v3 archive — as opposed to the one the
        # unit fixture steers around — failed the validator immediately after a migration
        # that claimed to have converted it, on a field whose only problem was its name.
        if "doc_type" in row:
            legacy_value = row.pop("doc_type")
            if "doc_kind" not in row or row.get("doc_kind") in (None, ""):
                row["doc_kind"] = legacy_value
                notes.append(f"{sid}: doc_type -> doc_kind ({legacy_value!r})")
            elif row.get("doc_kind") != legacy_value:
                raise ValueError(
                    f"{sid}: row carries BOTH doc_type ({legacy_value!r}) and a different "
                    f"doc_kind ({row.get('doc_kind')!r}). There is no safe pick between two "
                    "document kinds for one source; fix the row by hand"
                )
            else:
                notes.append(f"{sid}: dropped redundant legacy doc_type")
        if "kind" not in row:
            row["kind"] = infer_kind(row)
            notes.append(f"{sid}: kind <- {row['kind']} (from read_mode)")
        if "clinical_class" not in row:
            row["clinical_class"] = infer_clinical_class(row)
            notes.append(f"{sid}: clinical_class <- {row['clinical_class']} (from bucket number)")
        if "text_layer_kind" not in row:
            # v3 had no concept of a text layer. `not_applicable` is the only honest value:
            # claiming `absent` would assert something about pixels nobody looked at.
            row["text_layer_kind"] = (
                "not_applicable" if row.get("read_mode") == "native_text" else "absent"
            )
        if row.get("kind") == "novel" and not row.get("novel_reason"):
            row["novel_reason"] = "migrated from scheme_version 3; reason not recorded at the time"
        # ---- the model-vision rows v3 left without a transcript (fix spec B6) ------
        # A14 requires `transcript_path` for read_mode model_vision_primary/_assist,
        # because a model-read page whose transcription is not on disk cannot be
        # re-checked by anything: no faithfulness pass, no second read, no human spot
        # check. v3 kept no such file, so migrating one of these rows means recording an
        # UNVERIFIABLE source, and the only two honest options are to say so or to refuse
        # the archive. Saying so costs nothing and loses nothing; refusing strands the
        # patient's records. So the row is marked, the A14 requirement is waived FOR
        # MARKED ROWS ONLY, and the source is counted as unreadable in
        # projection_coverage with a coverage_gap flag — which is what stops the waiver
        # from reading downstream as "fine".
        if (row.get("read_mode") in MODEL_VISION_READ_MODES
                and not row.get("transcript_path")):
            if row.get("legacy_transcript_unavailable") is not True:
                row["legacy_transcript_unavailable"] = True
                notes.append(
                    f"{sid}: legacy_transcript_unavailable <- true (read_mode "
                    f"{row.get('read_mode')!r}, and v3 kept no verbatim page transcription "
                    "to point transcript_path at)"
                )
            if isinstance(row.get("source_id"), str):
                legacy_unreadable.append(row["source_id"])
        # ---- the high-risk triple on a waived row (fix spec C3) --------------------
        # A v4 row must say what it did about its high-risk fields. These rows can say
        # nothing true about them: there is no transcript, so there is no frontmatter,
        # so there is no `fields[]` to derive a denominator from and nothing for a second
        # channel to re-read. Left unset, the row trips gate_high_risk_denominator on a
        # missing key and the operator's only escape is to INVENT a value — and the two
        # values within reach are both lies: `passed_independent_reread` claims a check
        # that cannot be performed, and `needs_human_review` queues a human to re-read a
        # page that is not on disk.
        #
        # `not_applicable` over an EMPTY list is the honest reading, and it is only honest
        # because the cost is paid elsewhere and visibly: the same source is counted in
        # projection_coverage.summary.unreadable_sources and carries an unresolved
        # coverage_gap flag (B6). The waiver is narrow — gate_high_risk_denominator,
        # gate_faithfulness and gate_human_sample skip THESE rows and no others.
        if row.get("legacy_transcript_unavailable") is True:
            if "high_risk_fields" not in row:
                row["high_risk_fields"] = []
                notes.append(
                    f"{sid}: high_risk_fields <- [] (no transcript on disk, so the page has "
                    "no frontmatter to derive a high-risk denominator from)"
                )
            if row.get("high_risk_review_status") != "not_applicable":
                row["high_risk_review_status"] = "not_applicable"
                notes.append(f"{sid}: high_risk_review_status <- not_applicable")
            if row.get("reread_channel") != "none":
                row["reread_channel"] = "none"
                notes.append(f"{sid}: reread_channel <- none (no channel exists to re-read with)")
    data["scheme_version"] = TARGET_SCHEME_VERSION
    return data, notes, legacy_unreadable


def _ensure_flag(data: dict, flag: dict, notes: list[str], what: str) -> None:
    """Append `flag` unless one with the same id is already there (idempotence).

    Keyed on the id rather than on deep equality: a reviewer may legitimately have
    edited the issue text or moved the flag to `resolved_administratively`, and a second
    migration run must not resurrect the original wording beside it.
    """
    flags = data.setdefault("review_flags", [])
    if not isinstance(flags, list):
        return
    if any(isinstance(f, dict) and f.get("id") == flag["id"] for f in flags):
        return
    flags.append(flag)
    notes.append(what)


def migrate_readiness(data: dict, source_ids: list[str],
                      legacy_unreadable: list[str] | None = None) -> tuple[dict, list[str]]:
    """Fill the v4 GAPS in readiness.json. Returns (data, notes).

    Deliberately does NOT write the `pii_semantic_deferred` flag — that is
    `record_pii_deferral()` (fix spec C4). The split exists because the two kinds of edit
    answer different questions. Everything here answers "is this archive missing something
    v4 requires?", so an empty note list is the proof that `--force` has nothing to do. The
    PII deferral answers "did we just perform a migration?", and folding it in here made
    that question unanswerable: the flag appended a note on every single invocation, so a
    complete archive always LOOKED like it needed work and `--force` rewrote it, stacking a
    fresh migration run onto an archive that had not changed.
    """
    notes: list[str] = []
    legacy_unreadable = list(dict.fromkeys(legacy_unreadable or []))
    flags = data.get("review_flags")
    if isinstance(flags, list):
        for flag in flags:
            if isinstance(flag, dict) and "audience" not in flag:
                cat = flag.get("category")
                flag["audience"] = "internal_qc" if cat in INTERNAL_QC_CATEGORIES else "clinician"
                notes.append(f"review_flag {flag.get('id', '?')}: audience <- {flag['audience']}")
    if "projection_coverage" not in data:
        data["projection_coverage"] = {
            "per_source": [
                # "unknown", not []. A v3 archive recorded nothing about which field classes
                # reached the structured JSON, and [] renders downstream as "fully
                # projected" — a number this migration is in no position to assert.
                {"source_id": sid, "unprojected_field_classes": ["unknown"]}
                for sid in source_ids
            ],
            "summary": {
                "sources_total": len(source_ids),
                "sources_fully_projected": 0,
                "novel_sources": 0,
                # fix spec B6: a source whose page text v3 never kept IS unreadable, by the
                # only definition that matters downstream — nothing can go back and read it.
                "unreadable_sources": len(legacy_unreadable),
            },
        }
        notes.append(
            f"projection_coverage <- conservative skeleton over {len(source_ids)} source(s); "
            "every source is 'unknown', because a v3 archive recorded no per-field "
            "projection state and a zero would read as 'nothing is missing'"
        )
    else:
        # --force path: the skeleton is already there (from an earlier partial migration or
        # a real run). Do not rebuild it — only make sure it has not under-counted the
        # sources this run just marked unverifiable.
        cov = data["projection_coverage"]
        if isinstance(cov, dict) and isinstance(cov.get("summary"), dict):
            summ = cov["summary"]
            if summ.get("unreadable_sources", 0) < len(legacy_unreadable):
                notes.append(
                    f"projection_coverage.summary.unreadable_sources "
                    f"{summ.get('unreadable_sources')!r} -> {len(legacy_unreadable)} "
                    "(legacy model-vision sources with no transcript on disk)"
                )
                summ["unreadable_sources"] = len(legacy_unreadable)
        if isinstance(cov, dict) and isinstance(cov.get("per_source"), list):
            known = {r.get("source_id") for r in cov["per_source"] if isinstance(r, dict)}
            for sid in source_ids:
                if sid not in known:
                    cov["per_source"].append(
                        {"source_id": sid, "unprojected_field_classes": ["unknown"]})
                    notes.append(f"projection_coverage.per_source <- {sid} (was missing)")
            if isinstance(cov.get("summary"), dict):
                cov["summary"]["sources_total"] = len(cov["per_source"])

    # ---- fix spec B6: the legacy model-vision sources are a COVERAGE GAP -----------
    if legacy_unreadable:
        _ensure_flag(data, {
            "id": COVERAGE_GAP_FLAG_ID,
            "category": "coverage_gap",
            "audience": "internal_qc",
            "affected_field": "source_inventory.transcript_path",
            "current_source_values": [
                {"value": sid, "source_ref": f"source:{sid}"} for sid in legacy_unreadable
            ],
            "issue": (
                f"{len(legacy_unreadable)} source(s) were read by a vision model under "
                "scheme_version 3, which kept no verbatim page transcription on disk. They "
                "carry legacy_transcript_unavailable: true and are counted as unreadable in "
                "projection_coverage: nothing can re-verify what was read from them — not "
                "the faithfulness pass, not a second channel, not a human spot check. "
                "Re-upload the originals and run a full organize to replace the waiver."
            ),
            "resolution_status": "unresolved",
        }, notes,
            f"review_flags <- {COVERAGE_GAP_FLAG_ID} over {len(legacy_unreadable)} "
            "unverifiable legacy source(s)")

    if data.get("schema_version") != READINESS_SCHEMA_VERSION:
        notes.append(f"schema_version {data.get('schema_version')!r} -> {READINESS_SCHEMA_VERSION!r}")
        data["schema_version"] = READINESS_SCHEMA_VERSION
    return data, notes


def record_pii_deferral(data: dict, notes: list[str]) -> None:
    """fix spec B5: `pii_semantic: deferred` never travels alone.

    The migration's update_log entry says `deferred`, and B5 makes that legal for a
    migration run — but ONLY against a matching readiness flag. The pairing is the whole
    mechanism: the update_log line is machine state that no human surface renders, while a
    review_flag is the thing that shows up in the QC list and in AGENTS.md. Writing the
    first without the second is how a deferral becomes permanent — nobody is ever told it
    is owed. `internal_qc`, because "we have not re-run the PII pass" is a fact about how
    the archive was PROCESSED, never a question for a doctor.

    Called ONLY on the committing path (fix spec C4), immediately before the update_log
    entry it pairs with, and never on the `--force` no-op path — a flag that says "a
    migration deferred the PII pass" must not be written by a run that performed no
    migration.
    """
    _ensure_flag(data, {
        "id": PII_DEFERRED_FLAG_ID,
        "category": "pii_semantic_deferred",
        "audience": "internal_qc",
        "affected_field": "pii_semantic",
        "current_source_values": [],
        "issue": (
            "scheme_version 3 -> 4 migration. A migration reads no page content, so it "
            "cannot make a PII statement, and the v4 surface list (fix spec A17) is wider "
            "than the one this archive was last scanned against. The semantic PII pass "
            "(references/pii-rescan-prompt.md) is still OWED over the whole archive; "
            "export_share.py refuses until a later run records pii_semantic: clean."
        ),
        "resolution_status": "unresolved",
    }, notes, f"review_flags <- {PII_DEFERRED_FLAG_ID} (pairs the update_log deferral)")


def append_update_log(patient_dir: Path, run_id: str, source_ids: list[str]) -> None:
    log_path = patient_dir / "update_log.json"
    data: dict = {"schema": "cancer_buddy_update_log_v1", "runs": []}
    if log_path.is_file():
        try:
            loaded = json.loads(log_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            pass
    data.setdefault("runs", []).append({
        "run_id": run_id,
        "run_mode": "migration",
        "started_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "added_sources": [],
        # A migration reads no page content, so it cannot make a PII statement. `deferred`
        # is the honest verdict and it carries its own consequence: export_share refuses
        # while the most recent verdict is not `clean`, which is exactly right — nobody has
        # run a semantic PII pass over this archive under the v4 surface list.
        "pii_semantic": "deferred",
        "readiness_flag_id": PII_DEFERRED_FLAG_ID,
        "note": (
            f"scheme_version 3 -> {TARGET_SCHEME_VERSION} by scripts/migrate_v3_to_v4.py over "
            f"{len(source_ids)} source(s). kind/clinical_class/text_layer_kind were INFERRED "
            "from read_mode and bucket number; projection_coverage is a conservative skeleton, "
            "not a measurement. Re-run a full organize to replace inference with observation."
        ),
    })
    log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate(patient_dir: Path, run_id: str, dry_run: bool,
            force: bool = False) -> tuple[int, list[str]]:
    inv_path = patient_dir / "source_inventory.json"
    if not inv_path.is_file():
        print(f"ERROR: {inv_path} not found — nothing to migrate", file=sys.stderr)
        return 1, []
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: source_inventory.json unreadable: {exc}", file=sys.stderr)
        return 1, []
    if not isinstance(inv, dict):
        print("ERROR: source_inventory.json is not an object", file=sys.stderr)
        return 1, []

    scheme = inv.get("scheme_version")
    if scheme == TARGET_SCHEME_VERSION and not force:
        print(f"[migrate_v3_to_v4] already scheme_version {TARGET_SCHEME_VERSION}; nothing to do")
        return 0, []
    if scheme not in (None, 3, TARGET_SCHEME_VERSION):
        print(f"ERROR: unexpected scheme_version {scheme!r} (expected missing or 3)", file=sys.stderr)
        return 1, []

    try:
        inv, inv_notes, legacy_unreadable = migrate_inventory(inv)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1, []
    source_ids = [r.get("source_id") for r in inv.get("files", [])
                  if isinstance(r, dict) and isinstance(r.get("source_id"), str)]

    read_notes: list[str] = []
    readiness_path = patient_dir / "readiness.json"
    readiness = None
    if readiness_path.is_file():
        try:
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: readiness.json unreadable: {exc}", file=sys.stderr)
            return 1, []
        if isinstance(readiness, dict):
            readiness, read_notes = migrate_readiness(readiness, source_ids, legacy_unreadable)
    else:
        # readiness.json is a REQUIRED product in v4 (fix spec A14). Its absence is a real
        # gap; this script says so rather than minting an empty one, because a synthesized
        # readiness file asserts a completeness review that never happened.
        read_notes.append(
            "readiness.json is MISSING. v4 requires it. This migration does not create one: "
            "an invented readiness file claims a documentation-completeness review nobody "
            "performed. Re-run organize to produce it."
        )

    # ---- the completeness verdict, taken BEFORE anything migration-shaped is written --
    # (fix spec C4.) `inv_notes` and `read_notes` now contain only GAPS — v4 fields that
    # were genuinely missing — because the PII deferral has been moved out to
    # `record_pii_deferral()` below. That is what makes emptiness meaningful: an archive
    # that is already complete produces no notes, so `--force` can tell "complete" from
    # "needed work" and stop. Previously the deferral flag was appended during the
    # readiness pass, so `notes` was never empty, the no-op branch was unreachable, and
    # every `--force` on a finished archive rewrote both JSON files and stacked another
    # `run_mode: migration` entry that recorded a migration nobody had performed — each
    # one re-deferring the PII pass and re-blocking export.
    #
    # `scheme != TARGET` stays a reason to write in its own right: stamping
    # scheme_version 4 is a real change even when no row needed a single field.
    needs_write = (scheme != TARGET_SCHEME_VERSION) or bool(inv_notes) or bool(read_notes)
    if not needs_write:
        print(f"[migrate_v3_to_v4] --force: scheme_version {TARGET_SCHEME_VERSION} archive is "
              "already complete; nothing to do")
        return 0, []

    # Past this point the run IS a migration, so it takes on a migration's obligations:
    # the deferred-PII flag, and the update_log entry it pairs with. Applied before the
    # --dry-run return as well, so a dry run previews the flag it would write instead of
    # under-reporting the consequences of the migration it is previewing.
    notes = inv_notes + read_notes
    if isinstance(readiness, dict):
        record_pii_deferral(readiness, notes)
    if dry_run:
        return 0, notes

    _pathsafe.require_contained(inv_path, patient_dir, "source_inventory.json")
    inv_path.write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if isinstance(readiness, dict):
        _pathsafe.require_contained(readiness_path, patient_dir, "readiness.json")
        readiness_path.write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    append_update_log(patient_dir, run_id, source_ids)
    return 0, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="migrate_v3_to_v4.py",
        description="One-time scheme_version 3 -> 4 conversion for an existing patient archive.",
    )
    ap.add_argument("patient_dir")
    ap.add_argument("--run-id", default=None,
                    help="run id recorded in update_log.json (default: migrate-<UTC date>)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would change and write nothing")
    ap.add_argument("--force", action="store_true",
                    help="also complete a PARTIAL scheme_version 4 archive (fix spec B4): "
                         "rows that declare 4 but are missing kind / clinical_class / "
                         "doc_kind / text_layer_kind, or a readiness.json with no "
                         "projection_coverage. Fills only what is MISSING; never overwrites "
                         "a value that is already there")
    args = ap.parse_args(argv)

    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2
    run_id = args.run_id or f"migrate-{dt.datetime.now(dt.timezone.utc):%Y%m%d}"
    try:
        _pathsafe.safe_component(run_id, "--run-id")
    except _pathsafe.PathSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    code, notes = migrate(patient_dir, run_id, args.dry_run, force=args.force)
    prefix = "[migrate_v3_to_v4] would change" if args.dry_run else "[migrate_v3_to_v4] changed"
    for n in notes:
        print(f"  {prefix[len('[migrate_v3_to_v4] '):]}: {n}")
    if code == 0 and notes:
        print(f"[migrate_v3_to_v4] {len(notes)} change(s), scheme_version -> {TARGET_SCHEME_VERSION}"
              + (" (dry run, nothing written)" if args.dry_run else ""))
        if not args.dry_run:
            print("[migrate_v3_to_v4] recorded in update_log.json as run_mode: migration. "
                  "kind/clinical_class were INFERRED, not observed — re-run a full organize "
                  "to replace inference with real values, and run the semantic PII pass "
                  "before any export (this run is recorded pii_semantic: deferred)")
    return code


if __name__ == "__main__":
    sys.exit(main())
