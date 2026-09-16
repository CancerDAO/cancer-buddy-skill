#!/usr/bin/env python3
"""ingest_transcripts.py — 段 1 collector: validate model page output, write both copies.

WHAT THIS IS
    The deterministic back half of the transcription path. prepare_pages.py wrote one
    self-contained packet per page; the host model answered them; this script takes
    those answers, VALIDATES them, and lands two derivatives per page:

      raw/transcript/<source_id>/page-NNN.md   verbatim, unmasked, never leaves raw/
      ocr/<source_id>/page-NNN.md              masked staging copy — 段 2 moves it into
                                               its bucket, after which ocr/ is empty

    Two copies because a single one cannot be both. The verbatim page is what makes a
    value checkable against the source without re-running a model, and it necessarily
    contains letterheads, signatures, 住院号 and barcodes. The masked copy is the only
    surface anything downstream reads. Collapsing them would either destroy the audit
    trail or route unmasked identifiers into every downstream context.

EVERY IDENTIFIER HERE IS UNTRUSTED (fix spec A9 / P0-2)
    `source_id`, `page`, `prompt_version` and `model_id` all arrive INSIDE the model's
    own frontmatter and were previously joined straight onto a path:

        raw/transcript/{sid}/page-{page:03d}.md
        raw/_cache/transcripts/{sha}.{pv}.{mid}.md

    A page whose frontmatter said `source_id: ../../../../tmp/x` wrote outside the
    patient directory, and a `prompt_version: ../../evil` did the same to the cache. The
    model producing those strings is reading patient-uploaded pages, so they are attacker-
    influenced by construction. Every one now goes through _pathsafe.safe_component, and
    every resulting path is asserted contained BEFORE the write. A rejection makes the
    page `invalid`; it never becomes a guessed-at filename.

MASKING IS FAIL-CLOSED (fix spec A7 / P0-3)
    Masking here is pii_rescan's deterministic SHAPE layer. It cannot see 姓名, 出生地,
    职业, 家属姓名 or signatures; those have no shape and remain the semantic pass's job.
    What changed is what happens when it FAILS. The previous implementation serialized
    the frontmatter to JSON, masked the text, and re-parsed — with

        except json.JSONDecodeError: masked_fm = fm

    i.e. when masking broke the JSON, the UNMASKED frontmatter was written to the
    downstream-readable copy. A masking failure silently became a masking bypass, and the
    only signal was that it did not crash. Frontmatter is now masked by walking the parsed
    structure leaf by leaf (so there is no round-trip to break, and numeric leaves like
    `住院号: 12345` are reachable at all), and ANY failure marks the page `invalid` and
    writes nothing.

VALIDATION IS THE POINT
    A page whose frontmatter does not parse, or whose bbox is outside 0-1, or whose
    clinical_class is invented, or that is not in this run's pages.json, or that was
    submitted twice, is recorded as `invalid` and the script exits 1. It is NOT silently
    dropped and NOT half-written: a page that quietly vanished between transcription and
    archive is indistinguishable from a page the patient never had.

ESCALATION
    unreadable_ratio > 0.3 or uncertain_n > 8 sets `escalate_to_agent: true` on that
    page in the manifest. The stateless single-call path is for pages a model can read;
    a page it cannot is exactly where an agent worker with tools and judgement earns its
    cost. The flag is advisory — this script never calls a model.

USAGE
    ingest_transcripts.py <patient_dir> --run-id <id> --from <dir | file.jsonl>
    ingest_transcripts.py <patient_dir> --run-id <id> --from-cache
    ingest_transcripts.py <patient_dir> --run-id <id> --apply-second-read <results.json>

    --from DIR    one file per page. Two layouts are accepted, and BOTH are cross-checked
                  against the frontmatter (fix spec C2):
                    <source_id>.page-NNN.md          the canonical dot form
                    <source_id>/page-NNN.md          the slash form; the DIRECTORY name
                                                     is the expected source_id
    --from JSONL  one object per line: {source_id, page, content} (or {path, content})
    --from-cache  re-ingest this run's cache hits from raw/_cache/transcripts/. A cached
                  page still goes through validation and re-derives its masked copy — a
                  cache stores the MODEL's answer, never the conclusion that the answer
                  was acceptable.
    --apply-second-read  fold 段 1.5 results ({source_id,page,label,channel,model_id,
                  value,agree}) back into high_risk_fields[] in the run manifest.

Exit codes:
    0  every page validated and landed
    1  at least one page was invalid, or nothing was ingested
    2  bad invocation
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _pathsafe  # noqa: E402

TEXT_LAYER_KINDS = {"born_digital", "embedded_ocr", "absent", "not_applicable"}
CLINICAL_CLASSES = {"molecular", "lab", "imaging", "pathology", "narrative", "admin", "unknown"}
REQUIRED_KEYS = (
    "source_id", "page", "text_layer_kind", "doc_kind", "clinical_class",
    "fields", "high_risk", "uncertain", "discrepancy",
    "unreadable_ratio", "needs_rotation", "prompt_version", "model_id",
)
ESCALATE_UNREADABLE_RATIO = 0.3
ESCALATE_UNCERTAIN_N = 8
MAX_PAGE_NO = 10000

_PAGE_FILE_RE = re.compile(r"^(?P<sid>.+)\.page-(?P<page>\d+)\.md$")
# The slash layout `ocr/_inbox/<source_id>/page-NNN.md`. Hosts write it because it is what
# a per-source worker naturally produces, and before fix spec C2 it parsed to (None, None):
# the filename carried no source_id, so `validate_frontmatter` was handed expect_sid=None
# and SKIPPED the cross-check entirely. A page dropped in `.../s1/` whose frontmatter said
# `source_id: s2` was accepted and filed under s2 — the one mix-up the naming convention
# exists to catch. Both layouts are now parsed, and both are cross-checked identically.
_PAGE_IN_SID_DIR_RE = re.compile(r"^page-(?P<page>\d+)\.md$")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)
# bucket_taxonomy.json open_sub_bucket_slug_regex, enforced HERE rather than three stages
# later (fix spec A33): a malformed `novel:<slug>` that reaches 段 2 becomes a directory
# name under 15_未分类资料/, and by then the page is already filed.
_NOVEL_SLUG_RE = re.compile(r"^[一-鿿A-Za-z0-9][一-鿿A-Za-z0-9-]{1,23}$")


# --------------------------------------------------------------------------- #
# frontmatter
# --------------------------------------------------------------------------- #
def parse_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """Return (frontmatter, body, error).

    The contract asks for a small, fixed YAML subset: scalars plus four keys whose
    values are JSON arrays. That subset is parsed directly rather than depending on
    PyYAML, for two reasons. It keeps the collector a stdlib-only script that runs in
    any host. And full YAML on model-written text is a liability, not a convenience:
    YAML's implicit typing turns a Norwegian gene symbol into False and an accession
    like `1:30` into a sexagesimal integer, and its anchors/merge keys are a parsing
    surface untrusted text should not get.

    DUPLICATE KEYS ARE AN ERROR (fix spec A33). `data[key] = ...` silently kept the last
    occurrence, so a page carrying `high_risk: ["住院号"]` followed by `high_risk: []`
    validated cleanly with an empty high-risk list — a one-line way to make a page's
    identifiers skip the second read entirely. There is no safe pick between two values
    for the same key, so the page is rejected.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text, "no YAML frontmatter block (--- ... ---) at the start of the page"
    block, body = m.group(1), text[m.end():]

    data: dict = {}
    key: str | None = None
    buf: list[str] = []
    depth = 0

    def flush() -> str | None:
        nonlocal key, buf
        if key is None:
            return None
        if key in data:
            return (
                f"duplicate frontmatter key {key!r}: two values for one key have no safe "
                "resolution — a second `high_risk: []` would silently erase the first"
            )
        blob = "\n".join(buf).strip()
        if blob == "":
            data[key] = None
        elif blob[0] in "[{":
            try:
                data[key] = json.loads(blob)
            except json.JSONDecodeError as exc:
                return f"key {key!r}: value is not valid JSON ({exc.msg})"
        else:
            data[key] = _scalar(blob)
        key, buf = None, []
        return None

    for raw_line in block.splitlines():
        if depth == 0 and not raw_line.startswith((" ", "\t")) and ":" in raw_line:
            err = flush()
            if err:
                return None, body, err
            k, _, v = raw_line.partition(":")
            key, buf = k.strip(), [v.strip()]
            depth = _depth_delta(v)
        else:
            buf.append(raw_line)
            depth += _depth_delta(raw_line)
        if depth < 0:
            depth = 0
    err = flush()
    if err:
        return None, body, err
    return data, body, None


def _depth_delta(s: str) -> int:
    """Bracket balance, ignoring brackets inside double-quoted strings."""
    depth, in_str, esc = 0, False, False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    return depth


def _scalar(blob: str):
    low = blob.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~", "none"):
        return None
    try:
        return int(blob)
    except ValueError:
        pass
    try:
        return float(blob)
    except ValueError:
        pass
    if len(blob) >= 2 and blob[0] == blob[-1] and blob[0] in "\"'":
        return blob[1:-1]
    return blob


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _bbox_errors(bbox, where: str) -> list[str]:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return [f"{where}: bbox must be a 4-element list [x0,y0,x1,y1]"]
    errs = []
    for i, v in enumerate(bbox):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"{where}: bbox[{i}] must be a number")
        elif not (0.0 <= float(v) <= 1.0):
            errs.append(
                f"{where}: bbox[{i}]={v} is outside 0-1. Coordinates are NORMALIZED to "
                "the rendered page so they survive a change of DPI; pixel coordinates "
                "silently become wrong the next time the page is rendered"
            )
    if not errs:
        if float(bbox[0]) > float(bbox[2]) or float(bbox[1]) > float(bbox[3]):
            errs.append(f"{where}: bbox is inverted (x0>x1 or y0>y1)")
    return errs


def validate_frontmatter(fm: dict, expect_sid: str | None, expect_page: int | None) -> list[str]:
    errs: list[str] = []
    for k in REQUIRED_KEYS:
        if k not in fm:
            errs.append(f"missing required frontmatter key: {k}")
    if errs:
        return errs

    if not isinstance(fm["source_id"], str) or not fm["source_id"].strip():
        errs.append("source_id must be a non-empty string")
    else:
        # fix spec A9 / P0-2 — this string becomes a directory name.
        try:
            _pathsafe.safe_component(fm["source_id"], "source_id")
        except _pathsafe.PathSafetyError as exc:
            errs.append(str(exc))
    if not isinstance(fm["page"], int) or isinstance(fm["page"], bool) or fm["page"] < 1:
        errs.append("page must be a positive integer")
    elif fm["page"] > MAX_PAGE_NO:
        errs.append(f"page {fm['page']} exceeds the sane maximum ({MAX_PAGE_NO})")
    if expect_sid is not None and fm.get("source_id") != expect_sid:
        errs.append(f"source_id {fm.get('source_id')!r} does not match the filename ({expect_sid!r})")
    if expect_page is not None and fm.get("page") != expect_page:
        errs.append(f"page {fm.get('page')!r} does not match the filename ({expect_page})")

    for key in ("prompt_version", "model_id"):
        # Both land in the cache filename.
        if not isinstance(fm[key], str) or not fm[key].strip():
            errs.append(f"{key} must be a non-empty string")
        else:
            try:
                _pathsafe.safe_filename_token(fm[key], key)
            except _pathsafe.PathSafetyError as exc:
                errs.append(str(exc))

    if fm["text_layer_kind"] not in TEXT_LAYER_KINDS:
        errs.append(f"text_layer_kind {fm['text_layer_kind']!r} not in {sorted(TEXT_LAYER_KINDS)}")
    if fm["clinical_class"] not in CLINICAL_CLASSES:
        errs.append(
            f"clinical_class {fm['clinical_class']!r} not in {sorted(CLINICAL_CLASSES)} — it is a "
            "closed routing enum, not a free-text label; the completeness gates key off it"
        )
    if not isinstance(fm["doc_kind"], str) or not fm["doc_kind"].strip():
        errs.append("doc_kind must be a non-empty string (a pinned type name, or novel:<slug>)")

    ratio = fm["unreadable_ratio"]
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not (0.0 <= float(ratio) <= 1.0):
        errs.append("unreadable_ratio must be a number in 0-1")
    if not isinstance(fm["needs_rotation"], bool):
        errs.append("needs_rotation must be a boolean")

    fields = fm["fields"]
    if not isinstance(fields, list):
        errs.append("fields must be a list")
    else:
        for i, f in enumerate(fields):
            if not isinstance(f, dict):
                errs.append(f"fields[{i}] must be an object")
                continue
            label = f.get("label")
            if not isinstance(label, str) or not label.strip():
                errs.append(f"fields[{i}] has no label")
            elif len(label) > 120:
                # fix spec A16: the label is copied VERBATIM (no slug fold), so the only
                # limits are length and control characters.
                errs.append(f"fields[{i}] label is {len(label)} chars (max 120)")
            elif any(ord(ch) < 32 or ord(ch) == 127 for ch in label):
                errs.append(f"fields[{i}] label contains a control character")
            if "value" not in f:
                errs.append(f"fields[{i}] ({f.get('label', '?')}) has no value")
            span = f.get("span")
            if not isinstance(span, dict):
                errs.append(
                    f"fields[{i}] ({f.get('label', '?')}) has no span — every field anchors to a "
                    "page bbox in raw/, never to a markdown line number (a line number points at "
                    "the model's own output, which is what the anchor exists to check)"
                )
                continue
            errs.extend(_bbox_errors(span.get("bbox"), f"fields[{i}] ({f.get('label', '?')})"))

    for key in ("high_risk", "uncertain"):
        if not isinstance(fm[key], list):
            errs.append(f"{key} must be a list of field labels")
        elif any(not isinstance(x, str) for x in fm[key]):
            errs.append(f"{key} must contain only field labels (strings)")

    disc = fm["discrepancy"]
    if not isinstance(disc, list):
        errs.append("discrepancy must be a list")
    else:
        for i, d in enumerate(disc):
            if not isinstance(d, dict):
                errs.append(f"discrepancy[{i}] must be an object")
            elif not all(k in d for k in ("label", "vision_value", "text_layer_value")):
                errs.append(
                    f"discrepancy[{i}] needs label + vision_value + text_layer_value — both "
                    "readings stay side by side; the disagreement is the record, and picking a "
                    "winner here would erase it"
                )
    return errs


def normalize_doc_kind(doc_kind: str, seq: int) -> tuple[str, str | None]:
    """Validate `novel:<slug>` at ingest. Returns (doc_kind, flag_note|None) (fix spec A33).

    A malformed slug is DEGRADED rather than rejected, because the page itself is fine —
    only the model's proposed directory name is not. Losing a real page over a bad slug
    would be the worse error. The degraded name is visible (`novel:unknown-NN`) and the
    note travels into the manifest so 段 2 files it and a reviewer renames it.
    """
    if not doc_kind.startswith("novel:"):
        return doc_kind, None
    slug = doc_kind[len("novel:"):]
    if _NOVEL_SLUG_RE.match(slug) and not slug.startswith(("raw", "ocr")) \
            and not re.match(r"^\d{2}_", slug):
        return doc_kind, None
    degraded = f"novel:unknown-{seq:02d}"
    return degraded, (
        f"doc_kind {doc_kind!r} has a slug that is not a legal open sub-bucket name "
        f"(^[一-鿿A-Za-z0-9][一-鿿A-Za-z0-9-]{{1,23}}$); degraded to "
        f"{degraded!r} so it cannot become a directory name nobody vetted"
    )


# --------------------------------------------------------------------------- #
# readings[].channel vocabulary (fix spec B2)
#
# SIX values, and the split between them is the whole point:
#
#   `transcribe` is the FIRST read — 段 1's multimodal transcription. It is the only
#   channel a reading can carry before 段 1.5 runs, and it is never a second channel.
#   (It was briefly written as `first_read` here while the schema said `transcribe`, so a
#   manifest and its own schema disagreed about what the first reading was called.)
#
#   The other five are the SECOND-READ channels, in the priority order of
#   references/high-risk-fields.md §2.2.
#
# `none` is deliberately NOT in either set. `none` is a statement about the ENVIRONMENT —
# "this run had no second channel available" — and it belongs on `reread_channel`, never
# on a reading. A reading is a value somebody read; there is no value read through no
# channel, so an entry `{"channel": "none", "value": ""}` asserts a second read that did
# not happen, which is exactly the claim the second-read contract exists to prevent.
# --------------------------------------------------------------------------- #
FIRST_READ_CHANNEL = "transcribe"
REREAD_CHANNELS = (
    "text_layer", "barcode", "deterministic_ocr", "alternate_vision_model", "human",
)
READING_CHANNELS = (FIRST_READ_CHANNEL,) + REREAD_CHANNELS


# --------------------------------------------------------------------------- #
# high_risk_fields[] skeleton  (fix spec A5)
# --------------------------------------------------------------------------- #
def high_risk_fields_skeleton(fm: dict) -> list[dict]:
    """One entry per high-risk label on this page, all `needs_human_review` to begin with.

    The status starts PESSIMISTIC and is only moved by evidence: `plan_second_read.py`
    settles what a born-digital text layer settles, and `--apply-second-read` folds an
    actual second channel's answer back in. Defaulting to anything else would mean a page
    that never reached 段 1.5 at all — because the run crashed, or because the planner
    was skipped — presented as if its identifiers had been independently confirmed.
    """
    fields = {f.get("label"): f for f in fm.get("fields", []) if isinstance(f, dict)}
    out: list[dict] = []
    for label in fm.get("high_risk", []) or []:
        if not isinstance(label, str):
            continue
        f = fields.get(label) or {}
        out.append({
            "label": label,
            "status": "needs_human_review",
            "reread_channel": "none",
            "readings": [{"channel": FIRST_READ_CHANNEL, "value": str(f.get("value", ""))}],
        })
    return out


# --------------------------------------------------------------------------- #
# input collection
# --------------------------------------------------------------------------- #
def split_page_path(path: Path, root: Path | None = None) -> tuple[str | None, int | None]:
    """(source_id, page) implied by a staging FILENAME — never by its content.

    Two layouts, one contract (fix spec C2). Whatever this returns is fed to
    `validate_frontmatter` as `expect_sid` / `expect_page`, so returning None is not a
    neutral act: it silences the cross-check for that page. The slash form therefore
    reads the source_id off the parent directory rather than giving up on it.

        <source_id>.page-007.md        -> ("<source_id>", 7)
        <source_id>/page-007.md        -> ("<source_id>", 7)
        page-007.md  (loose at root)   -> (None, 7)      no directory to trust
        anything else                  -> (None, None)
    """
    m = _PAGE_FILE_RE.match(path.name)
    if m:
        return m.group("sid"), int(m.group("page"))
    m = _PAGE_IN_SID_DIR_RE.match(path.name)
    if m:
        page = int(m.group("page"))
        parent = path.parent
        # A file sitting loose in the inbox root has no directory that means anything;
        # claiming the inbox's own name as the source_id would invent a cross-check.
        if root is not None:
            try:
                if parent.resolve() == root.resolve():
                    return None, page
            except OSError:
                return None, page
        name = parent.name
        return (name or None), page
    return None, None


def load_inputs(src: Path) -> list[dict]:
    """Return [{source_id?, page?, content, origin}].

    A file that is not valid UTF-8 produces an `invalid` item rather than an exception
    (fix spec A33): `read_text` used to raise UnicodeDecodeError out of the loop and take
    the entire batch with it, so one mis-encoded page meant no page in the run landed.
    """
    items: list[dict] = []
    if src.is_dir():
        for f in sorted(src.rglob("*.md")):
            sid_from_name, page_from_name = split_page_path(f, src)
            try:
                rel = str(f.relative_to(src))
            except ValueError:
                rel = f.name
            try:
                content = f.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                items.append({"source_id": None, "page": None, "content": None,
                              "origin": rel,
                              "parse_error": f"not valid UTF-8: {exc}"})
                continue
            except OSError as exc:
                items.append({"source_id": None, "page": None, "content": None,
                              "origin": rel, "parse_error": f"unreadable: {exc}"})
                continue
            items.append({
                "source_id": sid_from_name,
                "page": page_from_name,
                "content": content,
                # The RELATIVE path, not the bare name: with the slash layout two sources
                # both contain `page-001.md`, and a rejection report that says
                # `INVALID page-001.md` names neither of them.
                "origin": rel,
            })
        return items
    if src.is_file():
        try:
            raw = src.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            return [{"source_id": None, "page": None, "content": None,
                     "origin": src.name, "parse_error": f"not valid UTF-8: {exc}"}]
        for n, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                items.append({"source_id": None, "page": None, "content": None,
                              "origin": f"{src.name}:L{n}", "parse_error": "line is not JSON"})
                continue
            sid, page = obj.get("source_id"), obj.get("page")
            if (sid is None or page is None) and isinstance(obj.get("path"), str):
                # Same two layouts as the directory branch — a JSONL that carries `path`
                # instead of `source_id` must not be the loophole that skips the check.
                p_sid, p_page = split_page_path(Path(obj["path"]))
                sid, page = (sid or p_sid), (page or p_page)
            items.append({
                "source_id": sid,
                "page": int(page) if isinstance(page, int) else None,
                "content": obj.get("content"),
                "origin": f"{src.name}:L{n}",
            })
        return items
    return items


def load_from_cache(patient_dir: Path, pages_index: dict) -> list[dict]:
    """Re-ingest this run's cache hits (fix spec A33, `--from-cache`).

    A cache stores the MODEL's answer, not the conclusion that the answer was acceptable,
    so a cached page goes through exactly the same validation and re-derives its masked
    copy. Skipping the derivation on a cache hit was how a masked copy could go missing
    for a page the manifest reported as `ok`.
    """
    items: list[dict] = []
    for (sid, page), rec in sorted(pages_index.items()):
        cached_rel = rec.get("cached_path")
        if not (rec.get("cache_hit") and isinstance(cached_rel, str)):
            continue
        try:
            path = _pathsafe.safe_relpath(cached_rel, patient_dir, "cached_path")
        except _pathsafe.PathSafetyError as exc:
            items.append({"source_id": sid, "page": page, "content": None,
                          "origin": f"cache:{sid}.page-{page:03d}", "parse_error": str(exc)})
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            items.append({"source_id": sid, "page": page, "content": None,
                          "origin": f"cache:{sid}.page-{page:03d}",
                          "parse_error": f"cached page unreadable: {exc}"})
            continue
        items.append({"source_id": sid, "page": page, "content": content,
                      "origin": f"cache:{sid}.page-{page:03d}"})
    return items


# --------------------------------------------------------------------------- #
# main ingest
# --------------------------------------------------------------------------- #
def _load_pages_index(prov_dir: Path) -> tuple[dict, str | None]:
    pages_index: dict[tuple[str, int], dict] = {}
    run_prompt_version = None
    pages_json = prov_dir / "pages.json"
    if pages_json.is_file():
        try:
            pm = json.loads(pages_json.read_text(encoding="utf-8"))
            run_prompt_version = pm.get("prompt_version")
            for rec in pm.get("pages", []) or []:
                sid, page = rec.get("source_id"), rec.get("page")
                if isinstance(sid, str) and isinstance(page, int):
                    pages_index[(sid, page)] = rec
        except (OSError, json.JSONDecodeError):
            pass
    return pages_index, run_prompt_version


def ingest(patient_dir: Path, run_id: str, src: Path | None, model_id: str,
           from_cache: bool = False) -> tuple[int, dict]:
    try:
        import pii_rescan
    except Exception as exc:
        print(f"ERROR: cannot import pii_rescan (needed for the masked copy): {exc}", file=sys.stderr)
        return 2, {}

    prov_dir = patient_dir / "raw" / "_provenance" / run_id
    _pathsafe.require_contained(prov_dir, patient_dir, "provenance dir")
    prov_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = patient_dir / "raw" / "_cache" / "transcripts"

    pages_index, run_prompt_version = _load_pages_index(prov_dir)

    items = load_from_cache(patient_dir, pages_index) if from_cache else load_inputs(src)
    if not items:
        where = "the run cache" if from_cache else str(src)
        print(f"ERROR: no page output found at {where}", file=sys.stderr)
        return 1, {}

    manifest_pages: list[dict] = []
    invalid = 0
    submitted: dict[tuple[str, int], str] = {}
    novel_seq = 0

    def reject(origin: str, errors: list[str]) -> None:
        nonlocal invalid
        invalid += 1
        manifest_pages.append({"origin": origin, "status": "invalid", "errors": errors})
        for e in errors:
            print(f"INVALID {origin}: {e}", file=sys.stderr)

    for item in items:
        origin = item["origin"]
        if item.get("parse_error") or not isinstance(item.get("content"), str):
            reject(origin, [item.get("parse_error") or "no content"])
            continue

        fm, body, err = parse_frontmatter(item["content"])
        if fm is None:
            reject(origin, [err])
            continue

        errs = validate_frontmatter(fm, item.get("source_id"), item.get("page"))
        if errs:
            reject(origin, errs)
            continue

        sid = fm["source_id"]
        page = fm["page"]

        # ---- the page must be one 段 0 actually prepared (fix spec A33) -------------
        # Without this the collector accepted any well-formed page for any id, including
        # ids that never existed: a fabricated `source_id` created a transcript directory
        # and an inventory row for a document nobody uploaded.
        if pages_index and (sid, page) not in pages_index:
            reject(origin, [
                f"({sid}, page {page}) is not in raw/_provenance/{run_id}/pages.json — every "
                "ingested page must correspond to a page 段 0 prepared, or the archive gains a "
                "page the patient never uploaded"
            ])
            continue
        if (sid, page) in submitted:
            reject(origin, [
                f"({sid}, page {page}) was already submitted by {submitted[(sid, page)]!r} — two "
                "transcriptions of one page have no safe merge, and last-write-wins would make "
                "the archive depend on directory ordering"
            ])
            continue

        doc_kind, novel_note = normalize_doc_kind(fm["doc_kind"], novel_seq)
        if novel_note:
            novel_seq += 1
            fm = dict(fm)
            fm["doc_kind"] = doc_kind

        # ---- masking, fail-closed (fix spec A7 / P0-3) -----------------------------
        try:
            masked_body, body_spans = pii_rescan.mask_text(body)
            masked_fm, fm_spans = pii_rescan.mask_structure(fm)
            masked_text = (
                "---\n"
                + "\n".join(
                    f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in masked_fm.items()
                )
                + "\n---\n"
                + masked_body
            )
        except Exception as exc:
            reject(origin, [
                f"masking failed ({exc.__class__.__name__}: {exc}) — the page is recorded as "
                "invalid and NEITHER copy is written. A masking failure must never fall back "
                "to writing the unmasked text to the downstream-readable copy"
            ])
            continue

        # ---- paths, checked before any write (fix spec A9 / P0-2) ------------------
        verbatim_rel = f"raw/transcript/{sid}/page-{page:03d}.md"
        masked_rel = f"ocr/{sid}/page-{page:03d}.md"
        try:
            verbatim_path = _pathsafe.safe_relpath(verbatim_rel, patient_dir, "transcript path")
            masked_path = _pathsafe.safe_relpath(masked_rel, patient_dir, "masked path")
            _pathsafe.require_contained(verbatim_path, patient_dir / "raw" / "transcript",
                                        "transcript path")
            _pathsafe.require_contained(masked_path, patient_dir / "ocr", "masked path")
        except _pathsafe.PathSafetyError as exc:
            reject(origin, [str(exc)])
            continue

        try:
            verbatim_path.parent.mkdir(parents=True, exist_ok=True)
            verbatim_path.write_text(item["content"], encoding="utf-8")
            masked_path.parent.mkdir(parents=True, exist_ok=True)
            masked_path.write_text(masked_text, encoding="utf-8")
        except OSError as exc:
            # A half-written page is worse than a rejected one: the verbatim copy would
            # exist with no masked counterpart, and 段 2 would find nothing to file.
            for p in (verbatim_path, masked_path):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            reject(origin, [f"could not write page to disk: {exc}"])
            continue

        submitted[(sid, page)] = origin

        # content-addressed cache: keyed on the PAGE IMAGE **and its text layer**, so
        # re-running with the same prompt, model and inputs never pays for the same page
        # twice — and a changed text layer is a changed question (fix spec A1).
        cached_rel = None
        rec = pages_index.get((sid, page))
        cache_key = (rec or {}).get("cache_key")
        if not cache_key:
            sha = (rec or {}).get("image_sha256")
            tl_sha = (rec or {}).get("text_layer_sha256")
            pv = fm.get("prompt_version") or run_prompt_version
            mid = model_id or fm.get("model_id") or "unknown"
            if sha and pv:
                cache_key = f"{sha}.{(tl_sha or '')[:16]}.{pv}.{mid}"
        if cache_key:
            try:
                cache_file = _pathsafe.safe_relpath(
                    f"raw/_cache/transcripts/{cache_key}.md", patient_dir, "cache path")
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(item["content"], encoding="utf-8")
                cached_rel = cache_file.relative_to(patient_dir).as_posix()
            except (_pathsafe.PathSafetyError, OSError) as exc:
                # A cache miss is a cost, not a correctness problem — the page is landed.
                print(f"WARN {origin}: could not write the cache entry: {exc}", file=sys.stderr)

        uncertain_n = len(fm["uncertain"])
        ratio = float(fm["unreadable_ratio"])
        escalate = ratio > ESCALATE_UNREADABLE_RATIO or uncertain_n > ESCALATE_UNCERTAIN_N

        page_rec = {
            "origin": origin,
            "status": "ok",
            "source_id": sid,
            "page": page,
            "image_path": (rec or {}).get("image_path"),
            "text_layer_kind": fm["text_layer_kind"],
            "doc_kind": doc_kind,
            "clinical_class": fm["clinical_class"],
            "n_fields": len(fm["fields"]),
            "high_risk_n": len(fm["high_risk"]),
            "high_risk_fields": high_risk_fields_skeleton(fm),
            "uncertain_n": uncertain_n,
            "discrepancy_n": len(fm["discrepancy"]),
            "unreadable_ratio": ratio,
            "needs_rotation": fm["needs_rotation"],
            "cache_hit": bool((rec or {}).get("cache_hit")),
            "cached_path": cached_rel,
            "transcript_path": verbatim_rel,
            "masked_path": masked_rel,
            "transcribe_model_id": model_id or fm.get("model_id") or "unknown",
            # spans only: {kind, len}. Never the matched text — this manifest is read
            # downstream, and echoing the identifier here would undo the masking.
            # fix spec B10. A `skipped_as_timestamp` record is NOT a masked span — nothing
            # was rewritten — so it is split out rather than inflating the mask count. It
            # is still carried, under its own key: an exemption nobody can see is
            # indistinguishable from a leak nobody noticed.
            "masked_spans": [{"kind": s["kind"], "len": s["len"]}
                             for s in (body_spans + fm_spans)
                             if s["kind"] != pii_rescan.SKIPPED_AS_TIMESTAMP],
            "skipped_as_timestamp": [{"key": s.get("key", ""), "len": s["len"]}
                                     for s in (body_spans + fm_spans)
                                     if s["kind"] == pii_rescan.SKIPPED_AS_TIMESTAMP],
            "masked_findings": len(body_spans) + len(fm_spans),
            "escalate_to_agent": escalate,
            "escalate_reason": (
                f"unreadable_ratio {ratio} > {ESCALATE_UNREADABLE_RATIO}" if ratio > ESCALATE_UNREADABLE_RATIO
                else (f"uncertain_n {uncertain_n} > {ESCALATE_UNCERTAIN_N}" if escalate else None)
            ),
        }
        if novel_note:
            page_rec["review_flags"] = [{
                "category": "coverage_gap",
                "audience": "internal_qc",
                "issue": novel_note,
            }]
        manifest_pages.append(page_rec)

    ok_pages = [p for p in manifest_pages if p["status"] == "ok"]
    manifest = {
        "schema": "organize_transcribe_manifest_v1",
        "run_id": run_id,
        "model_id": model_id,
        "source": "cache" if from_cache else str(src.name if src else ""),
        "counts": {
            "pages_in": len(items),
            "pages_ok": len(ok_pages),
            "pages_invalid": invalid,
            "escalate_to_agent": sum(1 for p in ok_pages if p.get("escalate_to_agent")),
            "with_discrepancy": sum(1 for p in ok_pages if p.get("discrepancy_n")),
            "masked_findings": sum(p.get("masked_findings", 0) for p in ok_pages),
            "high_risk_fields": sum(len(p.get("high_risk_fields", [])) for p in ok_pages),
        },
        "pages": manifest_pages,
    }
    out_path = prov_dir / "transcribe-manifest.json"
    _pathsafe.require_contained(out_path, patient_dir, "transcribe manifest")
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return (1 if invalid else 0), manifest


# --------------------------------------------------------------------------- #
# --apply-second-read  (fix spec A5/A23)
# --------------------------------------------------------------------------- #
def apply_second_read(patient_dir: Path, run_id: str, results_path: Path) -> tuple[int, dict]:
    """Fold 段 1.5 channel results back into the manifest's high_risk_fields[].

    Before this existed the skeleton written at ingest was the last word: nothing in the
    pipeline could move a field from `needs_human_review` to `passed_independent_reread`,
    so either every archive shipped with every identifier unconfirmed, or somebody edited
    the JSON by hand. The adjudication rules are the ones in
    `references/organizer-prompt-second-read.md` §3, and they are deliberately strict:

      agree == false            -> needs_human_review. NOT "keep reading 1".
      values differ             -> needs_human_review, BOTH readings kept side by side.
      same model as 段 1        -> needs_human_review. Re-reading with the same weights is
                                   a tie-break; agreement proves the model is stable, not
                                   that the paper says what it says.
      values equal, channel ok  -> passed_independent_reread + reread_channel.

    There is no vote. Three channels giving two values is `needs_human_review` with all
    candidates listed, because a majority vote turns a systematic misreading — which is
    exactly what correlated models produce — into a settled fact.
    """
    prov_dir = patient_dir / "raw" / "_provenance" / run_id
    man_path = prov_dir / "transcribe-manifest.json"
    if not man_path.is_file():
        print(f"ERROR: no transcribe-manifest.json for run {run_id}", file=sys.stderr)
        return 1, {}
    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unreadable input: {exc}", file=sys.stderr)
        return 1, {}

    results = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(results, list):
        print("ERROR: --apply-second-read expects a list of "
              "{source_id,page,label,channel,model_id,value,agree} (or {results:[...]})",
              file=sys.stderr)
        return 2, {}

    by_page = {(p.get("source_id"), p.get("page")): p
               for p in manifest.get("pages", []) or [] if p.get("status") == "ok"}
    applied = passed = disputed = unmatched = 0
    rejected: list[tuple] = []

    for r in results:
        if not isinstance(r, dict):
            unmatched += 1
            continue
        sid, page, label = r.get("source_id"), r.get("page"), r.get("label")
        rec = by_page.get((sid, page))
        if rec is None:
            unmatched += 1
            continue
        entry = next((e for e in rec.get("high_risk_fields", []) if e.get("label") == label), None)
        if entry is None:
            unmatched += 1
            continue
        channel = r.get("channel")
        if channel not in REREAD_CHANNELS:
            # fix spec B2. A result that does not name one of the five second-read
            # channels is NOT folded in as `none`: `none` means "no channel was
            # available", and writing it here would record an attempted-and-failed second
            # read as an environmental limitation — the two have opposite remedies (find a
            # channel vs. fix the caller), and only one of them is visible to a human.
            rejected.append((sid, page, label, channel))
            continue
        value = "" if r.get("value") is None else str(r.get("value"))
        agree = bool(r.get("agree"))
        first = next((x.get("value") for x in entry.get("readings", [])
                      if x.get("channel") == "transcribe"), "")
        same_model = (channel == "alternate_vision_model"
                      and r.get("model_id")
                      and r.get("model_id") == rec.get("transcribe_model_id"))
        entry.setdefault("readings", []).append({"channel": channel, "value": value})
        if r.get("model_id"):
            entry["reread_model_id"] = r["model_id"]
        entry["reread_channel"] = channel
        if agree and value.strip() == str(first).strip() and not same_model:
            entry["status"] = "passed_independent_reread"
            passed += 1
        else:
            entry["status"] = "needs_human_review"
            entry["disagreement_reason"] = (
                "second read could not read the field (agree: false)" if not agree
                else ("the re-read used the SAME model as 段 1 — a tie-break, not an "
                      "independent channel" if same_model
                      else "the two channels disagree; both readings are kept, no vote is taken")
            )
            disputed += 1
        applied += 1

    for p in by_page.values():
        hrf = p.get("high_risk_fields") or []
        if not hrf:
            p["high_risk_review_status"] = "not_applicable"
        elif any(e.get("status") != "passed_independent_reread" for e in hrf):
            p["high_risk_review_status"] = "needs_human_review"
        else:
            p["high_risk_review_status"] = "passed_independent_reread"

    manifest.setdefault("counts", {})["second_read_applied"] = applied
    if rejected:
        manifest.setdefault("counts", {})["second_read_rejected_channel"] = len(rejected)
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ingest_transcripts] second read applied={applied} "
          f"passed_independent_reread={passed} needs_human_review={disputed} unmatched={unmatched} "
          f"rejected_channel={len(rejected)}")
    for sid_, page_, label_, ch_ in rejected[:10]:
        print(f"ERROR: {sid_} p{page_} {label_!r}: channel {ch_!r} is not a second-read "
              f"channel; expected one of {', '.join(REREAD_CHANNELS)} "
              f"(`none` describes the ENVIRONMENT and belongs on reread_channel, "
              f"never on a reading)", file=sys.stderr)
    return (1 if (unmatched or rejected) else 0), manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ingest_transcripts.py",
        description="段 1 collector: validate page transcriptions, write the verbatim + masked copies.",
    )
    ap.add_argument("patient_dir")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--from", dest="src", default=None,
                    help="directory of <source_id>.page-NNN.md files, or a .jsonl of {source_id,page,content}")
    ap.add_argument("--from-cache", action="store_true",
                    help="re-ingest this run's cache hits from raw/_cache/transcripts/ "
                         "(cached pages still go through validation and re-derive the masked copy)")
    ap.add_argument("--apply-second-read", dest="second_read", default=None, metavar="RESULTS.json",
                    help="fold 段 1.5 results back into high_risk_fields[] "
                         "({source_id,page,label,channel,model_id,value,agree})")
    ap.add_argument("--model-id", default="unknown", help="model id for the transcription cache key")
    args = ap.parse_args(argv)

    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(f"ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2
    try:
        _pathsafe.safe_component(args.run_id, "--run-id")
        _pathsafe.safe_filename_token(args.model_id, "--model-id")
    except _pathsafe.PathSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.second_read:
        rp = Path(args.second_read).resolve()
        if not rp.is_file():
            print(f"ERROR: --apply-second-read {rp} does not exist", file=sys.stderr)
            return 2
        code, _doc = apply_second_read(patient_dir, args.run_id, rp)
        return code

    if not args.src and not args.from_cache:
        print("ERROR: one of --from, --from-cache or --apply-second-read is required",
              file=sys.stderr)
        return 2
    src = None
    if args.src:
        src = Path(args.src).resolve()
        if not src.exists():
            print(f"ERROR: --from {src} does not exist", file=sys.stderr)
            return 2

    try:
        code, manifest = ingest(patient_dir, args.run_id, src, args.model_id, args.from_cache)
    except _pathsafe.PathSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not manifest:
        return code or 1
    c = manifest["counts"]
    print(
        f"[ingest_transcripts] run={args.run_id} in={c['pages_in']} ok={c['pages_ok']} "
        f"invalid={c['pages_invalid']} escalate={c['escalate_to_agent']} "
        f"discrepancy_pages={c['with_discrepancy']} shape_masked={c['masked_findings']} "
        f"high_risk_fields={c['high_risk_fields']}"
    )
    print(f"[ingest_transcripts] manifest: raw/_provenance/{args.run_id}/transcribe-manifest.json")
    if c["pages_invalid"]:
        print(
            "[ingest_transcripts] invalid pages were NOT written — re-transcribe them; a page "
            "that quietly vanishes is indistinguishable from a page the patient never had",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
