#!/usr/bin/env python3
"""plan_second_read.py — 段 1.5 planner: who gets read twice, through which channel.

WHAT THIS IS
    A deterministic planner. It reads the run's transcription manifest and the verbatim
    page frontmatter, decides which fields still owe an INDEPENDENT second read, resolves
    the ones a channel already resolved for free, and emits one batched packet per page.
    It calls no model and reads no pixels.

WHAT TRIGGERS A SECOND READ
    fixed high-risk list  ∪  self-reported uncertain  ∪  vision/text-layer discrepancy
    ∪  numeric-level conflict with the deterministic OCR appendix.

    The union matters, and the FIXED LIST is the main term, not the model's self-report.
    The places a model slips — a dropped decimal point, a swapped unit, an HGVS c./p.
    shift, VAF as % vs fraction, a dose with one zero too many — are places it reads
    *fluently* and reports no doubt at all. So the list is also applied DETERMINISTICALLY
    to every field label on the page (fix spec A11): a page that self-reported
    `high_risk: []` used to contribute nothing to the second read AND nothing to the human
    spot-check pool, which meant a model could zero out its own audit by omission. The
    classification lives in `scripts/_high_risk.py` (fix spec B1) — ONE table, shared with
    `validate_structured_outputs.py`, so the set this planner queues and the set the
    validator requires cannot drift apart. It is a DENOMINATOR (which fields must be
    checked), not a judgement about what a field means, which is why a word list is the
    right tool for it, and why it knows both faces of every analyte: 「白细胞计数」 and
    `WBC` are the same cell.

WHY A BORN-DIGITAL PAGE OFTEN COSTS NOTHING
    On a born-digital page the embedded text layer is a genuinely independent channel —
    different modality, produced by the application that made the PDF, not by any model.
    If the field's value is present in that text layer, the second read is already done:
    the field is recorded as `passed_independent_reread` via `reread_channel: text_layer`
    and never enters a packet. This is where most of the second-read budget disappears.

    "Present", though, has to mean present as a VALUE (fix spec A10 / P0-4). The previous
    test was `value.strip() in text_layer` — a raw substring match. `112` is a substring
    of `1123`, of `0.112`, and of the date `2026-01-12` with the separators stripped; a
    WBC misread as `112` on a page whose text layer contains the reference range `1123`
    was therefore declared independently confirmed and removed from the plan. The match is
    now numeric-token-aware and boundary-anchored, short bare numbers cannot settle at
    all, and a page that resolves suspiciously much is flagged rather than trusted.

INDEPENDENCE IS THE WHOLE POINT
    channel_preference never proposes "ask the same model again". Re-prompting one model
    on one image is a tie-break, not a channel: its errors are correlated with itself, so
    agreement proves consistency, not correctness. Options are a different modality (text
    layer / barcode / parseable deterministic OCR), a different model, or a human — and
    `human` always terminates the list, because "no channel was available" must resolve
    to a person, never to accepting a single read.

    The list only offers channels the HOST ACTUALLY HAS (`--available-channels`), and
    `barcode` only when the page's frontmatter shows a barcode field. An offer the run
    cannot take is worse than no offer: the plan looks satisfiable, nobody notices the
    first three preferences are fiction, and the fields quietly stay at one reading.

WRITES
    raw/_provenance/<run_id>/second-read-plan.json
    raw/_provenance/<run_id>/human_sample_plan.json   (the script's half of the spot-check;
                                                       a human writes human_sample_result.json)

USAGE
    plan_second_read.py <patient_dir> --run-id <id> [--sample-rate 0.05] [--min-sample 3]
                        [--available-channels text_layer,alternate_vision_model,human]

Exit codes:
    0  a plan was written (an empty plan is a valid, good outcome)
    1  the run manifest is missing/unreadable, or a page in it could not be considered
    2  bad invocation
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _pathsafe  # noqa: E402
import ingest_transcripts as ing  # frontmatter parser, shared so both agree on the shape

DEFAULT_SAMPLE_RATE = 0.05
DEFAULT_MIN_SAMPLE = 3
# Below this the OCR appendix is "no signal" — not a disagreement. See the tri-state note.
OCR_PARSEABLE_MIN_CHARS = 40
# A `-` only reads as a SIGN when nothing numeric precedes it. Without the lookbehind,
# `2026-03-15` tokenizes to ["2026", "-03", "-15"] and the date can never be matched
# against a text layer that contains it verbatim, because `-03` occurs there only with a
# digit immediately before it. A hyphen between two digits is a separator, not a minus.
_NUM_RE = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?")
# A bare number shorter than this cannot resolve a field by being "found in the text
# layer": on a dense report every 1-2 digit run appears somewhere, so a match carries no
# information. Longer numbers, and anything non-numeric, are matched on boundaries.
MIN_SETTLE_DIGITS = 3
# A page where nearly everything resolved for free is usually a page where the matcher is
# too loose, not a page that is unusually clean. Recorded, never acted on automatically.
SUSPICIOUS_SETTLE_RATIO = 0.8

ALL_CHANNELS = ("text_layer", "barcode", "deterministic_ocr", "alternate_vision_model", "human")
DEFAULT_AVAILABLE = ("text_layer", "barcode", "deterministic_ocr", "alternate_vision_model", "human")

# ---------------------------------------------------------------------------
# The high-risk DENOMINATOR now lives in ONE place: scripts/_high_risk.py (fix spec B1).
#
# This module used to carry its own 12-key keyword table, and
# validate_structured_outputs.py carried a second one. They drifted, and the drift was
# invisible in exactly the direction that matters: neither copy knew the Latin lab
# abbreviations, so a page whose frontmatter says `WBC` / `HGB` / `PLT` / `CEA` produced
# an EMPTY derived set here — the planner queued nothing, the validator required nothing,
# and a Chinese-hospital archive exported in English abbreviations passed every gate with
# zero high-risk fields checked. A denominator each consumer re-implements is not a
# denominator; it is two opinions.
#
# `classify_label` is deterministic and total, which is what lets the validator recompute
# the same set from the archive's own frontmatter and compare it with what the manifest
# claims. See _high_risk.py for why a word list is the correct instrument for THIS
# question and only this one.
# ---------------------------------------------------------------------------
from _high_risk import (  # noqa: E402
    BARCODE_HINTS,
    HIGH_RISK_CLASSES,  # noqa: F401  (re-exported: callers read the class list from here)
    classify_label,
)

# Historical name, kept so the call sites below (and any out-of-tree caller) read the same.
classify_high_risk = classify_label


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------
def _numeric_tokens(text: str) -> list[str]:
    probe = text.replace(",", "").replace("，", "")
    probe = probe.translate(str.maketrans("０１２３４５６７８９．－", "0123456789.-"))
    return _NUM_RE.findall(probe)


def _norm_numeric_text(text: str) -> str:
    probe = text.replace(",", "").replace("，", "")
    return probe.translate(str.maketrans("０１２３４５６７８９．－", "0123456789.-"))


def _token_present(token: str, haystack: str) -> bool:
    """True when `token` occurs in `haystack` bounded by NON-DIGIT characters.

    This is the fix for P0-4. A digit-run must not be allowed to match inside a longer
    digit-run: `112` inside `1123`, `0.112` or `20260112` is a coincidence of decimal
    representation, and treating it as confirmation of a laboratory value is how a
    misread WBC gets certified by the very check meant to catch it.
    """
    for m in re.finditer(re.escape(token), haystack):
        before = haystack[m.start() - 1] if m.start() else ""
        after = haystack[m.end()] if m.end() < len(haystack) else ""
        if before.isdigit() or after.isdigit():
            continue
        # `==`, not `in`: `"" in "."` is True, so an `in` test silently rejected every
        # token that ended at the end of the string — including the last field on a page.
        if before == "." or after == ".":
            # `1.12` vs `1.123`: a decimal point on either side means the number
            # continues, so this is not the same value.
            continue
        return True
    return False


def resolved_by_text_layer(value: str, text_layer: str) -> bool:
    """Can the born-digital text layer stand in for an independent second read?

    Numeric fields: every numeric token in the value must appear in the text layer as a
    whole number (boundary-anchored), and a lone number shorter than MIN_SETTLE_DIGITS
    cannot resolve anything.

    Non-numeric fields: whole-token containment, so `EGFR` does not resolve `EGFRvIII`.
    """
    val = (value or "").strip()
    if not val:
        return False
    hay = _norm_numeric_text(text_layer)
    tokens = _numeric_tokens(val)
    if tokens:
        digits_only = re.fullmatch(r"-?\d+", val.strip()) is not None
        if digits_only and len(val.strip().lstrip("-")) < MIN_SETTLE_DIGITS:
            return False
        return all(_token_present(t, hay) for t in tokens)
    probe = re.escape(val)
    return re.search(rf"(?<![0-9A-Za-z_]){probe}(?![0-9A-Za-z_])", text_layer) is not None


def _near_miss(a: str, b: str) -> bool:
    """True when two numeric strings differ by one plausible OCR slip.

    Deliberately narrow: a single digit substitution/insertion/deletion, or the same
    digits with the decimal point somewhere else (12.4 vs 1.24 vs 124). Anything looser
    would fire on every unrelated number on the page and the trigger would be worthless.
    """
    if a == b:
        return False
    if a.replace(".", "") == b.replace(".", ""):
        return True  # decimal point moved — the classic, and the most dangerous, slip
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(long)):
        if long[:i] + long[i + 1:] == short:
            return True
    return False


def _channel_preference(text_layer_kind: str, has_ocr_appendix: bool,
                        has_barcode: bool, available: set[str]) -> list[str]:
    """Channels this run can ACTUALLY use, cheapest first (fix spec A10).

    Two changes from the version that listed everything unconditionally. `barcode` is only
    offered when the page's own frontmatter shows a barcode-bearing field — it used to be
    emitted first for every page with no evidence whatsoever that a barcode existed, which
    put an unreachable channel at the top of the preference list on every pixel page. And
    the whole list is intersected with what the host declares it has, so the plan describes
    a reachable route rather than an aspiration.
    """
    ordered: list[str] = []
    if text_layer_kind in ("born_digital", "embedded_ocr"):
        # born_digital: the text layer is truth. embedded_ocr: it is somebody else's OCR,
        # so it is a second CHANNEL — useful for cross-checking, never authoritative.
        ordered.append("text_layer")
    if has_barcode:
        ordered.append("barcode")
    if has_ocr_appendix:
        ordered.append("deterministic_ocr")
    ordered.append("alternate_vision_model")
    channels = [c for c in ordered if c in available]
    # `human` always terminates the list and is never omitted: "no channel was available"
    # resolves to a person, never to accepting a single read.
    channels.append("human")
    return channels


def _load_frontmatter(path: Path, patient_dir: Path) -> tuple[dict | None, str | None]:
    """Parse a page's frontmatter. The error string is PRODUCT-SAFE.

    An OSError's text quotes the absolute path it was handed, and this string is written
    into second-read-plan.json — a product. No product in this archive may carry a host
    filesystem path: it leaks the OS username and where the vault lives on disk. The
    patient-relative path carries all the diagnostic value and none of that.
    """
    try:
        rel = path.relative_to(patient_dir).as_posix()
    except ValueError:
        rel = path.name
    try:
        fm, _body, err = ing.parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"transcript unreadable at {rel}: {exc.__class__.__name__} (errno {exc.errno})"
    except UnicodeDecodeError:
        return None, f"transcript at {rel} is not valid UTF-8"
    return (None, err) if err else (fm, None)


def _patient_code(patient_dir: Path) -> str:
    try:
        data = json.loads((patient_dir / "profile.json").read_text(encoding="utf-8"))
        code = data.get("patient_code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return patient_dir.name


def plan(patient_dir: Path, run_id: str, sample_rate: float, min_sample: int,
         available: set[str]) -> tuple[int, dict]:
    prov = patient_dir / "raw" / "_provenance" / run_id
    _pathsafe.require_contained(prov, patient_dir, "provenance dir")
    manifest_path = prov / "transcribe-manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: no transcribe-manifest.json for run {run_id}", file=sys.stderr)
        return 1, {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unreadable manifest: {exc}", file=sys.stderr)
        return 1, {}

    packets: list[dict] = []
    resolved: list[dict] = []
    high_risk_pool: list[dict] = []
    warnings: list[dict] = []
    pages_considered = 0
    manifest_ok_pages = sum(1 for p in manifest.get("pages", []) or []
                            if p.get("status") == "ok")

    for page_rec in manifest.get("pages", []) or []:
        if page_rec.get("status") != "ok":
            continue
        sid = page_rec.get("source_id")
        page = page_rec.get("page")
        tpath = page_rec.get("transcript_path")
        if not (isinstance(sid, str) and isinstance(page, int) and isinstance(tpath, str)):
            warnings.append({"source_id": sid, "page": page,
                             "issue": "manifest row lacks source_id/page/transcript_path"})
            continue
        try:
            abs_tpath = _pathsafe.safe_relpath(tpath, patient_dir, "transcript_path")
        except _pathsafe.PathSafetyError as exc:
            warnings.append({"source_id": sid, "page": page, "issue": str(exc)})
            continue
        fm, fm_err = _load_frontmatter(abs_tpath, patient_dir)
        if fm is None:
            # fix spec P1-3: an unreadable transcript used to `continue` silently, so the
            # page contributed no high-risk fields to the plan AND none to the spot-check
            # pool — a missing file quietly became a clean page.
            warnings.append({"source_id": sid, "page": page,
                             "issue": f"transcript could not be read ({fm_err}); the page's "
                                      "high-risk fields cannot be planned or sampled"})
            continue
        pages_considered += 1

        kind = fm.get("text_layer_kind") or page_rec.get("text_layer_kind") or "absent"
        image_path = page_rec.get("image_path")

        views = patient_dir / "raw" / "adapter_views" / sid
        text_layer_file = views / f"page-{page:03d}.txt"
        ocr_file = views / f"page-{page:03d}.ocr.txt"
        text_layer = text_layer_file.read_text(encoding="utf-8", errors="replace") \
            if text_layer_file.is_file() else ""
        ocr_text = ocr_file.read_text(encoding="utf-8", errors="replace") if ocr_file.is_file() else ""
        ocr_parseable = len(ocr_text.strip()) >= OCR_PARSEABLE_MIN_CHARS and bool(_numeric_tokens(ocr_text))
        ocr_tokens = _numeric_tokens(ocr_text) if ocr_parseable else []

        fields = {f.get("label"): f for f in fm.get("fields", []) if isinstance(f, dict)}
        self_reported = [x for x in fm.get("high_risk", []) if isinstance(x, str)]
        uncertain = [x for x in fm.get("uncertain", []) if isinstance(x, str)]
        discrepancy = [d.get("label") for d in fm.get("discrepancy", []) if isinstance(d, dict)]

        # fix spec A11 — the denominator is computed, not accepted.
        derived: list[str] = []
        classes: dict[str, str] = {}
        for label in fields:
            cls = classify_high_risk(label)
            if cls:
                classes[label] = cls
                if label not in self_reported:
                    derived.append(label)
        high_risk = list(dict.fromkeys(self_reported + derived))
        if derived:
            warnings.append({
                "source_id": sid, "page": page, "kind": "high_risk_completed",
                "issue": f"{len(derived)} field(s) matched references/high-risk-fields.md but were "
                         f"not in the page's own high_risk[]: {derived[:8]}",
            })

        has_barcode = any(any(h in str(lbl).lower() for h in BARCODE_HINTS) for lbl in fields)

        # ∪ OCR numeric near-miss conflicts
        ocr_conflicts: list[str] = []
        if ocr_parseable:
            for label in high_risk:
                f = fields.get(label)
                if not isinstance(f, dict):
                    continue
                vals = _numeric_tokens(str(f.get("value", "")))
                if not vals:
                    continue
                v = vals[0]
                if v in ocr_tokens:
                    continue  # agreement — a confidence bonus, not a trigger
                if any(_near_miss(v, t) for t in ocr_tokens):
                    ocr_conflicts.append(label)
                # no near miss => OCR simply did not see this field => NO SIGNAL

        candidates: list[str] = []
        for label in high_risk + uncertain + [d for d in discrepancy if d] + ocr_conflicts:
            if label and label not in candidates:
                candidates.append(label)

        needed: list[dict] = []
        resolved_here = 0
        for label in candidates:
            f = fields.get(label)
            value = "" if f is None else str(f.get("value", ""))
            bbox = ((f or {}).get("span") or {}).get("bbox")
            trigger = []
            if label in high_risk:
                trigger.append("high_risk")
            if label in uncertain:
                trigger.append("uncertain")
            if label in discrepancy:
                trigger.append("discrepancy")
            if label in ocr_conflicts:
                trigger.append("ocr_numeric_conflict")

            # A discrepancy is, by definition, the text layer already disagreeing — it can
            # never be resolved BY the text layer.
            if (
                kind == "born_digital"
                and "text_layer" in available
                and label not in discrepancy
                and resolved_by_text_layer(value, text_layer)
            ):
                resolved.append({
                    "source_id": sid, "page": page, "label": label, "value": value,
                    "status": "passed_independent_reread",
                    "reread_channel": "text_layer",
                    "note": "value found in the born-digital text layer as a bounded token — an "
                            "independent modality, so no model call is owed",
                })
                resolved_here += 1
                if label in high_risk:
                    # Resolved by a channel, but still eligible for the human spot-check:
                    # the sample must be drawn from ALL high-risk fields, or it only ever
                    # audits the fields the pipeline already found hard.
                    high_risk_pool.append({
                        "source_id": sid, "page": page, "label": label,
                        "transcript_value": value, "bbox": bbox,
                        "high_risk_class": classes.get(label),
                    })
                continue

            needed.append({"label": label, "trigger": trigger, "bbox": bbox})
            if label in high_risk:
                high_risk_pool.append({
                    "source_id": sid, "page": page, "label": label,
                    "transcript_value": value, "bbox": bbox,
                    "high_risk_class": classes.get(label),
                })

        if candidates and resolved_here / len(candidates) > SUSPICIOUS_SETTLE_RATIO:
            warnings.append({
                "source_id": sid, "page": page, "kind": "suspicious_settle_ratio",
                "issue": f"{resolved_here}/{len(candidates)} fields resolved against the text "
                         "layer on one page. A page that resolves nearly everything is more often "
                         "a matcher that is too loose than a page that is unusually clean — "
                         "spot-check this page's values against raw/ before trusting the count",
            })

        if needed:
            channels = _channel_preference(kind, bool(ocr_text.strip()), has_barcode, available)
            packets.append({
                # The packet shape is the one in references/organizer-prompt-second-read.md §1:
                # whole-page image + a list of {label, trigger, bbox}, and NOT 段 1's values —
                # showing the model the first reading contaminates the second one.
                "source_id": sid,
                "page": page,
                "image": image_path,
                "channel": channels[0],
                "channel_preference": channels,
                "text_layer_kind": kind,
                "fields_to_verify": needed,
                "rule": (
                    "Read these fields again through `channel`. Re-prompting the same model on "
                    "the same image is a tie-break only and must not set "
                    "passed_independent_reread. Disagreement → needs_human_review with both "
                    "readings recorded side by side; never vote."
                ),
            })

    # fix spec A11: silently considering fewer pages than the manifest has is how a
    # coverage number gets its denominator quietly reduced.
    coverage_error = pages_considered < manifest_ok_pages
    if coverage_error:
        print(
            f"ERROR: considered {pages_considered} of {manifest_ok_pages} ok pages in the run "
            "manifest. Every ok page must be plannable; the unconsidered ones are listed in "
            "the plan's `warnings[]`. A second-read plan built over a silently smaller "
            "denominator reports coverage it does not have",
            file=sys.stderr,
        )

    # ---- deterministic human spot-check sample ---------------------------------
    seen = set()
    pool = []
    for item in high_risk_pool:
        key = (item["source_id"], item["page"], item["label"])
        if key not in seen:
            seen.add(key)
            pool.append(item)
    target = max(min_sample, math.ceil(sample_rate * len(pool))) if pool else 0
    target = min(target, len(pool))
    # fix spec A36: the seed is the PATIENT and the FIELD SET, never the run id. Keying on
    # the run id made the sample re-rollable — a run that failed its spot-check could be
    # re-run under a new id to draw different fields until it passed.
    seed_material = _patient_code(patient_dir) + "|" + "|".join(
        sorted(f"{i['source_id']}#{i['page']}#{i['label']}" for i in pool)
    )
    seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    sample = sorted(
        random.Random(seed).sample(pool, target) if target else [],
        key=lambda s: (s["source_id"], s["page"], s["label"]),
    )

    plan_doc = {
        "schema": "organize_second_read_plan_v1",
        "run_id": run_id,
        "available_channels": sorted(available),
        "counts": {
            "pages_considered": pages_considered,
            "pages_in_manifest_ok": manifest_ok_pages,
            "pages_in_plan": len(packets),
            "fields_to_reread": sum(len(p["fields_to_verify"]) for p in packets),
            "fields_passed_via_text_layer": len(resolved),
            "high_risk_fields_total": len(pool),
            "warnings": len(warnings),
        },
        "independence_rule": (
            "A second read counts only through an INDEPENDENT channel: a different modality "
            "(born-digital text layer / barcode / parseable deterministic OCR), a different "
            "model, or a human. The same model on the same image is a tie-break, not a channel."
        ),
        "packets": packets,
        # fix spec A23: a field that a channel confirmed is recorded with the SAME vocabulary
        # the inventory uses — status + reread_channel. The old `settled` / `settled_via`
        # wording named a third, undefined state that no schema had, and that read to a human
        # like "this value is final" when it means "one independent channel agreed once".
        "passed_independent_reread": resolved,
        "warnings": warnings,
    }
    out_plan = prov / "second-read-plan.json"
    _pathsafe.require_contained(out_plan, patient_dir, "second-read plan")
    out_plan.write_text(json.dumps(plan_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sample_doc = {
        "schema": "organize_human_sample_plan_v1",
        "run_id": run_id,
        "rule": (
            f"max({min_sample}, {sample_rate:.0%} of high-risk fields) per patient. The sample is "
            "seeded from the patient code and the SET OF HIGH-RISK FIELDS — never the run id — so "
            "the same archive always yields the same sample and a failed spot-check cannot be "
            "re-rolled by starting a new run. Open the ORIGINAL in raw/ (not the transcript, not "
            "the sidecar) and compare each value character by character, then record the verdicts "
            f"in raw/_provenance/{run_id}/human_sample_result.json "
            "({run_id, performed_by, performed_at, verdicts:[{source_id,page,label,"
            "verdict: match|mismatch|unreadable, note?}]}). Two mismatches mark the whole run "
            "needs_human_review and it is not deliverable."
        ),
        "high_risk_fields_total": len(pool),
        "sample_size": len(sample),
        "sample": [
            {"source_id": s["source_id"], "page": s["page"], "label": s["label"],
             "bbox": s.get("bbox"), "transcript_value": s.get("transcript_value")}
            for s in sample
        ],
    }
    out_sample = prov / "human_sample_plan.json"
    _pathsafe.require_contained(out_sample, patient_dir, "human sample plan")
    out_sample.write_text(json.dumps(sample_doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return (1 if coverage_error else 0), plan_doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="plan_second_read.py",
        description="段 1.5 planner: batch the fields that still owe a channel-independent second read.",
    )
    ap.add_argument("patient_dir")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sample-rate", type=float, default=DEFAULT_SAMPLE_RATE,
                    help="human spot-check fraction of high-risk fields (default 0.05)")
    ap.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE,
                    help="minimum human spot-check size per patient (default 3)")
    ap.add_argument("--available-channels", default=",".join(DEFAULT_AVAILABLE),
                    help="comma-separated channels the HOST can actually reach "
                         f"(any of: {', '.join(ALL_CHANNELS)}). `human` is always appended: "
                         "'no channel available' resolves to a person, never to one reading")
    args = ap.parse_args(argv)

    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2
    if not (0.0 <= args.sample_rate <= 1.0) or args.min_sample < 0:
        print("ERROR: --sample-rate must be 0-1 and --min-sample non-negative", file=sys.stderr)
        return 2
    try:
        _pathsafe.safe_component(args.run_id, "--run-id")
    except _pathsafe.PathSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    available = {c.strip() for c in args.available_channels.split(",") if c.strip()}
    unknown = available - set(ALL_CHANNELS)
    if unknown:
        print(f"ERROR: unknown channel(s) {sorted(unknown)}; allowed: {list(ALL_CHANNELS)}",
              file=sys.stderr)
        return 2
    available.add("human")

    code, doc = plan(patient_dir, args.run_id, args.sample_rate, args.min_sample, available)
    if not doc:
        return code
    c = doc["counts"]
    print(
        f"[plan_second_read] run={args.run_id} pages={c['pages_considered']}/{c['pages_in_manifest_ok']} "
        f"packets={c['pages_in_plan']} fields_to_reread={c['fields_to_reread']} "
        f"passed_via_text_layer={c['fields_passed_via_text_layer']} "
        f"high_risk_total={c['high_risk_fields_total']} warnings={c['warnings']}"
    )
    print(f"[plan_second_read] plan: raw/_provenance/{args.run_id}/second-read-plan.json")
    print(f"[plan_second_read] human spot-check: raw/_provenance/{args.run_id}/human_sample_plan.json")
    return code


if __name__ == "__main__":
    sys.exit(main())
