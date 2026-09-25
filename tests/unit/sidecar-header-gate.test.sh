#!/usr/bin/env bash
# O-01 / O-09 sidecar header + uncertainty gates.
#   gate_sidecar_headers      — pinned header block; EXTRACTOR ∈ update_log workers[]
#                               (the orchestrator never writes sidecars); an llm_vision
#                               reread is never INDEPENDENT_REREAD: true; header ↔
#                               source_inventory agreement (worker, reread, channel, sha256).
#   gate_review_flag_semantics — kind document_intent only with an independent reread;
#                               uncertain_ids / cross_doc_supported refs resolve;
#                               [OCR_UNCERTAIN:U-nnn] ↔ `## 不确定字段` entries (before ## PII).
# Positive control = clean synthetic archive. All data synthetic.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib

tmp = Path(sys.argv[2])
passed = failed = 0
n = 0
OP, CT = synlib.SIDE_OUTPATIENT, synlib.SIDE_CT


def run(gate, mutate=None):
    global n
    n += 1
    d = synlib.make(tmp / f"h{n}", mutate)
    return synlib.gate(gate, d)


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def hdr(rel, key, value):
    """Set (value str), or delete (value None), one header line of a sidecar."""
    def fn(text):
        lines = text.splitlines()
        out = []
        for line in lines:
            if line.startswith(key + ":"):
                if value is None:
                    continue
                line = f"{key}: {value}"
            out.append(line)
        return "\n".join(out) + "\n"
    return lambda d: synlib.edit_text(d, rel, fn)


def inv_row(rel, fn):
    return lambda d: synlib.edit_json(d, "source_inventory.json",
                                      lambda doc: fn(next(r for r in doc["files"] if r["sidecar_path"] == rel)))


# ---- positive control
errs, _ = run("gate_sidecar_headers")
check("clean archive: sidecar headers pass", errs == [], str(errs))
errs, _ = run("gate_review_flag_semantics")
check("clean archive: review-flag semantics pass", errs == [], str(errs))

# ---- EXTRACTOR
errs, _ = run("gate_sidecar_headers", hdr(OP, "EXTRACTOR", None))
check("missing EXTRACTOR → ERROR", any("EXTRACTOR missing" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(OP, "EXTRACTOR", "p1w-ghost-99"))
check("EXTRACTOR not in update_log workers → ERROR", any("is not a worker in update_log.json" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(OP, "EXTRACTOR", "Orchestrator"))
check("EXTRACTOR = orchestrator (any case) → ERROR", any("is the orchestrator" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_json(d, "update_log.json",
              lambda doc: doc["entries"][0].__setitem__("workers", [])))
check("update_log without workers → ERROR", any("lists no workers" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", inv_row(OP, lambda r: r["extractor_provenance"].__setitem__("worker_id", "p2-1")))
check("header EXTRACTOR ≠ inventory worker_id → ERROR", any("≠ source_inventory worker_id" in e for e in errs), str(errs))

# ---- independent reread (phase1 §2.3: an engine read is independent of the model's transcription; the
# model re-reading its own image is not)
errs, _ = run("gate_sidecar_headers", hdr(OP, "SECOND_READ_CHANNEL", "llm_vision"))
check("llm_vision SECOND read with INDEPENDENT_REREAD true → ERROR",
      any("must be false when the second read channel is llm_vision" in e for e in errs), str(errs))
ORD = synlib.SIDE_ORDER
errs, _ = run("gate_sidecar_headers")
check("llm_vision PRIMARY + apple_vision second read + true (the pixel-page fixture) passes",
      not any(ORD in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(OP, "PRIMARY_CHANNEL", "llm_vision")(d),
              hdr(OP, "SECOND_READ_CHANNEL", "deterministic_ocr:apple_vision")(d), hdr(OP, "READ_MODE", "model_vision_primary")(d),
              inv_row(OP, lambda r: r.update({"second_read_channel": "deterministic_ocr:apple_vision",
                                              "read_mode": "model_vision_primary"}))(d)))
check("llm_vision primary read + engine second read + true (no table on a legacy-shaped body) passes the header gate",
      errs == [], str(errs))


def order_rows(new_state, rows=None):
    """Rewrite the 一致 cell of the pixel-page fixture's second-read table rows (all rows, or the given 1-based rows)."""
    def fn(text):
        out, k = [], 0
        for line in text.splitlines():
            if line.startswith("| ") and line.rstrip().endswith(("| 是 |", "| 否 |", "| 无信号 |")) and not line.startswith("| 字段"):
                k += 1
                if rows is None or k in rows:
                    line = line.rsplit("|", 2)[0] + f"| {new_state} |"
            out.append(line)
        return "\n".join(out) + "\n"
    return lambda d: synlib.edit_text(d, ORD, fn)


errs, _ = run("gate_sidecar_headers", order_rows("无信号"))
check("true while every second-read row is 无信号 → ERROR (the engine read nothing: single-channel)",
      any(ORD in e and "every row of the second-read table is 无信号" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (order_rows("无信号")(d), hdr(ORD, "INDEPENDENT_REREAD", "false")(d),
              inv_row(ORD, lambda r: r.update({"independent_reread": False}))(d)))
check("every row 无信号 and INDEPENDENT_REREAD false passes", not any(ORD in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(ORD, "INDEPENDENT_REREAD", "false")(d),
              inv_row(ORD, lambda r: r.update({"independent_reread": False, "high_risk_review_status": "needs_human_review"}))(d)))
check("signal rows present but INDEPENDENT_REREAD false → ERROR (an under-claimed engine read)",
      any(ORD in e and "INDEPENDENT_REREAD false although the engine second read" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(ORD, "PRIMARY_CHANNEL", "deterministic_ocr:tesseract"))
check("READ_MODE model_vision_primary with a non-llm primary → ERROR",
      any(ORD in e and "READ_MODE model_vision_primary is a pixel page" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(ORD, "READ_MODE", "hybrid_verified")(d),
              inv_row(ORD, lambda r: r.update({"read_mode": "hybrid_verified"}))(d)))
check("PRIMARY llm_vision with READ_MODE hybrid_verified → ERROR", any(ORD in e and "PRIMARY_CHANNEL llm_vision with READ_MODE" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(ORD, "CONFIDENCE", "high"))
check("CONFIDENCE high with a 无信号 row → ERROR", any(ORD in e and "row(s) are 无信号" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (order_rows("是")(d), hdr(ORD, "CONFIDENCE", "medium")(d)))
check("independent, every row 是, CONFIDENCE medium → ERROR (→ high)", any(ORD in e and "no 无信号 row → high" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(synlib.SIDE_SELF, "CONFIDENCE", "high"))
check("born-digital native_text CONFIDENCE high → ERROR (fixed medium)", any("born-digital text layer" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers")
check("born-digital text layer + SECOND none + not_applicable (the self-note fixture) passes",
      not any(synlib.SIDE_SELF in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "SECOND_READ_CHANNEL", "deterministic_ocr:tesseract"))
check("two OCR engines (same channel category) marked independent → ERROR",
      any("both reads use channel 'deterministic_ocr'" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(OP, "INDEPENDENT_REREAD", "yes"))
check("INDEPENDENT_REREAD not true/false → ERROR", any("must be true or false" in e for e in errs), str(errs))
# (READ_MODE follows: hybrid_verified is reserved for an agreeing independent reread, so an honest
#  llm_vision reread is model_vision_assist in the header AND the inventory row)
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(OP, "SECOND_READ_CHANNEL", "llm_vision")(d),
              hdr(OP, "INDEPENDENT_REREAD", "false")(d), hdr(OP, "READ_MODE", "model_vision_assist")(d),
              inv_row(OP, lambda r: r.update({"second_read_channel": "llm_vision", "independent_reread": False,
                                              "high_risk_review_status": "needs_human_review",
                                              "read_mode": "model_vision_assist"}))(d)))
check("llm_vision reread honestly marked false passes", errs == [], str(errs))
errs, _ = run("gate_sidecar_headers", inv_row(OP, lambda r: r.update({"independent_reread": False,
              "high_risk_review_status": "needs_human_review"})))
check("header INDEPENDENT_REREAD ≠ inventory → ERROR", any("≠ source_inventory independent_reread" in e for e in errs), str(errs))

# ---- pinned header shape
errs, _ = run("gate_sidecar_headers", hdr(OP, "PAGE_LABEL", None))
check("missing pinned key → ERROR", any("missing pinned header key(s) PAGE_LABEL" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, OP, lambda t: "PATIENT_PHONE: x\n" + t))
check("header block not starting with a known key → no header → ERROR", any("no header block" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, OP, lambda t: t.replace("MODALITY: text", "MODALITY: text\nCONTACT: x", 1)))
check("unknown key inside the header block → ERROR (block is PII-exempt)", any("unknown header key(s) CONTACT" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(OP, "SHA256", "0" * 64))
check("SHA256 header ≠ inventory sha256 → ERROR", any("SHA256 header ≠ source_inventory sha256" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "SHA256", "n/a"))
check("SHA256 placeholder on an upload sidecar → ERROR", any("SHA256 'n/a' is not the 64-char" in e for e in errs), str(errs))
# a digest has no uploaded original: SHA256 is pinned to exactly `none` (phase1 §12)
errs, _ = run("gate_sidecar_headers")
check("digest sidecar SHA256: none (the fixture) passes", not any(synlib.SIDE_DIGEST in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(synlib.SIDE_DIGEST, "SHA256", "n/a"))
check("digest sidecar SHA256 placeholder n/a → ERROR", any("prior-archive digest SHA256 'n/a' must be exactly `none`" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(synlib.SIDE_DIGEST, "SHA256", "ab" * 32))
check("digest sidecar with a 64-hex SHA256 (e.g. of the summarised archive) → ERROR naming the digest",
      any(synlib.SIDE_DIGEST in e and "must be exactly `none`" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(synlib.SIDE_DIGEST, "SHA256", "None"))
check("digest sidecar SHA256 'None' (not the pinned spelling) → ERROR", any("SHA256 'None' must be exactly" in e for e in errs), str(errs))
n += 1
errs, warns = synlib.gate("gate_sidecar_headers", synlib.make(tmp / f"h{n}", hdr(synlib.SIDE_DIGEST, "SHA256", "ab" * 32)),
                          generation="legacy")
check("legacy archive: a hashed digest header is not an ERROR (legacy WARN path only)", errs == [], str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "SECOND_READ_CHANNEL", "text_layer"))
check("only SECOND_READ_CHANNEL ≠ inventory → ERROR", errs and all("SECOND_READ_CHANNEL 'text_layer' ≠ source_inventory" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "SECOND_READ_CHANNEL", "none"))
check("INDEPENDENT_REREAD true with second channel none → ERROR", any("without a second read channel" in e for e in errs), str(errs))

# ---- scope: a carried-over sidecar of an update-type run (not rewritten by this contract's
# workers) is one WARN; the same sidecar handed to a worker, or in a full run, is held to the header.
LEG = "05_影像/CT/2029-12-01_胸部CT_示例医院.md"


def carried(d, run_mode="incremental", in_workers=False):
    (d / LEG).write_text("SOURCE: raw/s009.jpg\nFILE_ID: f009\nREAD_MODE: deterministic_ocr\n\n"
                         "# 旧版转写（合成夹具）\n\n腹部超声：肝左叶[OCR_UNCERTAIN]囊肿。\n\n## PII\n\n- 无\n", encoding="utf-8")
    def inv(doc):
        row = json.loads(json.dumps(next(r for r in doc["files"] if r["sidecar_path"] == CT)))
        row.update({"file_id": "f009", "source_id": "s009", "original_path": "s009.jpg", "raw_path": "raw/s009.jpg",
                    "bucket_path": LEG, "sidecar_path": LEG, "sha256": "cd" * 32, "size_bytes": 10,
                    "page_label": None, "second_read_channel": "none", "independent_reread": False,
                    "high_risk_review_status": "needs_human_review", "read_mode": "deterministic_ocr"})
        row["extractor_provenance"]["worker_id"] = "legacy-import"
        doc["files"].append(row)
    synlib.edit_json(d, "source_inventory.json", inv)
    def ulog(doc):
        doc["entries"][0]["run_mode"] = run_mode
        if in_workers:
            doc["entries"][0]["workers"][1]["files"].append("s009")
    synlib.edit_json(d, "update_log.json", ulog)


n += 1
dd = synlib.make(tmp / f"h{n}", carried)
rc, errs, warns = synlib.validate(dd)
check("carried-over legacy sidecar in an incremental current archive → rc 0", rc == 0, str(errs[:3]))
check("…reported as one carried-over WARN", sum("carried-over sidecar(s)" in w for w in warns) == 1, str(warns))
check("…its bare [OCR_UNCERTAIN] is a WARN, not an ERROR", any("in carried-over sidecars" in w for w in warns))
errs, _ = run("gate_sidecar_headers", lambda d: carried(d, in_workers=True))
check("the same sidecar listed in a worker's files → header ERRORs", any(LEG in e and "EXTRACTOR missing" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: carried(d, in_workers=True))
check("…and its bare [OCR_UNCERTAIN] ERRORs", any(LEG in e and "bare [OCR_UNCERTAIN]" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: carried(d, run_mode="full"))
check("a full run re-transcribes everything → header ERRORs", any(LEG in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (carried(d), synlib.save(d, "update_log.json", {
    "schema_version": "1", "entries": [{"at": "2030-01-20T09:00:00Z", "run_mode": "incremental", "note": "no workers"}]})))
check("no current-shape ledger entry (no workers[]) → nothing counts as carried over → header ERRORs",
      any(LEG in e and "EXTRACTOR missing" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, OP, lambda t: re.sub(r"^EXTRACTOR: .*\n", "", t, flags=re.M)))
check("a sidecar of this run that dropped its EXTRACTOR is still an ERROR (source handed to a worker)",
      any("EXTRACTOR missing" in e for e in errs), str(errs))

# ---- document_intent needs two agreeing independent reads (O-01 item 2)
def intent(d, rel=OP):
    synlib.edit_json(d, "readiness.json", lambda doc: doc["review_flags"][0].update(
        {"kind": "document_intent", "current_source_values": [{"value": "x", "source_ref": rel + "#L20"}]}))


def op_text(old, new):
    return lambda d: synlib.edit_text(d, OP, lambda t: t.replace(old, new, 1))


deleted = op_text("layout_intent: null", "layout_intent: deleted")
errs, _ = run("gate_review_flag_semantics", lambda d: (intent(d, OP), deleted(d)))
check("document_intent: layout_intent deleted + two agreeing non-llm reads (apple_vision / text_layer) passes",
      errs == [], str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: intent(d, OP))
check("document_intent whose entry records no layout_intent → ERROR (downgrade to artifact)",
      any("none of its uncertain_ids (U-001)" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: (intent(d, OP), deleted(d), synlib.edit_json(
    d, "readiness.json", lambda doc: doc["review_flags"][0].pop("uncertain_ids"))))
check("document_intent without uncertain_ids → ERROR", any("names no uncertain_ids" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: (intent(d, OP), deleted(d),
              op_text('{channel: text_layer, text: "晚"', '{channel: text_layer, text: "早"')(d)))
check("document_intent whose two reads disagree → ERROR",
      any("do not show two agreeing reads" in e for e in errs) and any("none of its uncertain_ids" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: (intent(d, OP), deleted(d),
              op_text("{channel: text_layer,", '{channel: "llm_vision",')(d)))
check("document_intent resting on an llm_vision read → ERROR",
      any("none of its uncertain_ids" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: intent(d, synlib.SIDE_LAB))
check("document_intent on a sidecar without independent reread → ERROR (downgrade to artifact)",
      any("downgrade to artifact" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_json(d, "readiness.json",
              lambda doc: doc["review_flags"][0].update({"kind": "document_intent", "current_source_values": []})))
check("document_intent citing no sidecar → ERROR", any("cites no sidecar" in e for e in errs), str(errs))

# ---- `## 不确定字段` entry: line holds the token; candidates are whole lexicon lines (O-01 item 3)
line_now = re.search(r"  line: \d+", (synlib.SRC / OP).read_text(encoding="utf-8")).group(0)
errs, _ = run("gate_review_flag_semantics", op_text(line_now, "  line: 3"))
check("entry line that does not carry its token → ERROR", any("line 3 does not carry [OCR_UNCERTAIN:U-001]" in e for e in errs), str(errs))
lex = tmp / "lexicons"
lex.mkdir()
(lex / "ihc_markers.txt").write_text("CK19\nCK20\nCD20\n", encoding="utf-8")
os.environ["CB_ORGANIZE_LEXICON_DIR"] = str(lex)


def cands(line, fc="ihc_marker", reads=("CK2O", "CK20")):
    """Give U-001 lexicon candidates. The entry is turned into a rule-consistent ihc_marker
    reading (C2: only drug_name / ihc_marker / ln_station get candidates; C3: a `high`
    candidate needs a complete reading at distance 0), so each case isolates the lexicon check."""
    def fn(d):
        synlib.edit_text(d, OP, lambda t: t.replace("  field_class: stage", f"  field_class: {fc}", 1)
                         .replace('text: "晚", confidence: 0.41', f'text: "{reads[0]}", confidence: 0.41', 1)
                         .replace('{channel: text_layer, text: "晚"', f'{{channel: text_layer, text: "{reads[1]}"', 1)
                         .replace("  candidates: []", "  candidates:\n    " + line, 1))
    return fn


# the mechanical list for readings CK2O / CK20 over this lexicon (phase1 §5 rules 1-5)
MECH = ('- {text: "CK20", lexicon: ihc_markers, confidence: high}\n'
        '    - {text: "CD20", lexicon: ihc_markers, confidence: low}\n'
        '    - {text: "CK19", lexicon: ihc_markers, confidence: low}')
errs, _ = run("gate_review_flag_semantics", cands(MECH))
check("candidates that are the mechanical list of whole lexicon lines pass", errs == [], str(errs))
errs, _ = run("gate_review_flag_semantics", cands('- {text: "CK20", lexicon: ihc_markers, confidence: high}'))
check("a hand-picked subset of the mechanical list → ERROR (candidates are script output)",
      any("are not the mechanical list" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", cands('- {text: "CK2O", lexicon: ihc_markers, confidence: high}'))
check("candidate that is not a lexicon line (a free correction) → ERROR",
      any("candidate 'CK2O' is not a whole line of lexicon 'ihc_markers'" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", cands('- {text: "CK20", lexicon: my_guesses, confidence: high}'))
check("candidate from an unknown lexicon → ERROR", any("lexicon 'my_guesses' is not a references/lexicons" in e for e in errs), str(errs))
os.environ["CB_ORGANIZE_LEXICON_DIR"] = str(tmp / "no-such-dir")
errs, warns = run("gate_review_flag_semantics", cands('- {text: "CK2O", lexicon: ihc_markers, confidence: high}'))
check("lexicon dir absent → candidates reported unverified (WARN), not an ERROR",
      errs == [] and any("not verified" in w for w in warns), str(errs) + str(warns))
os.environ.pop("CB_ORGANIZE_LEXICON_DIR")

# ---- uncertain_ids / cross_doc_supported
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_json(d, "readiness.json",
              lambda doc: doc["review_flags"][0].__setitem__("uncertain_ids", ["U-077"])))
check("uncertain_id without a token in the cited sidecar → ERROR", any("uncertain_id U-077" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_json(d, "readiness.json",
              lambda doc: doc["review_flags"][0].__setitem__("cross_doc_supported",
                  {"status": "supported", "refs": ["04_诊断与分期/病理报告/不存在.md#L3"]})))
check("cross_doc_supported ref that does not resolve → ERROR", any("does not resolve" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_json(d, "readiness.json",
              lambda doc: doc["review_flags"][0].__setitem__("cross_doc_supported",
                  {"status": "supported", "refs": ["ocr/s002.md#L20"]})))
check("cross_doc_supported ref that is not a bucket anchor (Phase-1 ocr/ path) → ERROR",
      any("is not a bucket anchor" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_json(d, "readiness.json",
              lambda doc: doc["review_flags"][0].__setitem__("cross_doc_supported",
                  {"status": "supported", "refs": [synlib.SIDE_CT + "#L20"]})))
check("cross_doc_supported ref that resolves passes", errs == [], str(errs))

# ---- [OCR_UNCERTAIN] bookkeeping inside the sidecar
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_text(d, OP, lambda t: t.replace("[OCR_UNCERTAIN:U-001]", "[OCR_UNCERTAIN]")))
check("bare [OCR_UNCERTAIN] (no id, no readings) → ERROR", any("bare [OCR_UNCERTAIN]" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_text(d, OP, lambda t: t.replace("- id: U-001", "- id: U-002")))
check("token without a `## 不确定字段` entry → ERROR", any("has no `## 不确定字段` entry" in e for e in errs), str(errs))
def block_after_pii(t):
    head, block = t.split("## 不确定字段", 1)
    block, pii = block.split("## PII", 1)
    return head + "## PII" + pii + "\n## 不确定字段" + block
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_text(d, OP, block_after_pii))
check("`## 不确定字段` after `## PII` → ERROR", any("sits after `## PII`" in e for e in errs), str(errs))

errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_text(d, OP, lambda t: t.replace("  readings:", "  reads:")))
check("`## 不确定字段` entry without readings → ERROR", any("has no readings" in e for e in errs), str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: synlib.edit_text(d, OP, lambda t: t.replace("layout_intent: null", "layout_intent: deleted")))
check("layout_intent deleted on an independently reread sidecar passes", errs == [], str(errs))
errs, _ = run("gate_review_flag_semantics", lambda d: (synlib.edit_text(d, OP, lambda t: t.replace("layout_intent: null", "layout_intent: deleted")),
              hdr(OP, "INDEPENDENT_REREAD", "false")(d)))
check("layout_intent deleted without an independent reread → ERROR", any("layout_intent deleted/amended" in e for e in errs), str(errs))

# ---- exactly the 12 pinned keys, once each, in the pinned order (phase1 §3)
LAB, DIG = synlib.SIDE_LAB, synlib.SIDE_DIGEST


def swap_lines(rel, a, b):
    def fn(text):
        lines = text.splitlines()
        i = next(k for k, l in enumerate(lines) if l.startswith(a + ":"))
        j = next(k for k, l in enumerate(lines) if l.startswith(b + ":"))
        lines[i], lines[j] = lines[j], lines[i]
        return "\n".join(lines) + "\n"
    return lambda d: synlib.edit_text(d, rel, fn)


def body_only(text):
    return text.split("\n\n", 1)[1]


errs, _ = run("gate_sidecar_headers", swap_lines(CT, "SOURCE", "FILE_ID"))
check("keys out of the pinned order → ERROR", any("out of the pinned order" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, lambda t: t.replace("EXTRACTOR: p1-s002-1\n", "EXTRACTOR: p1-s002-1\nEXTRACTOR: p1-s002-1\n", 1)))
check("duplicate key → ERROR", any("duplicate header key(s) EXTRACTOR" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, lambda t: t.replace("MODALITY: text\n", "MODALITY: text\nADAPTER_PROVENANCE: sips\n", 1)))
check("legacy key inside a current header → ERROR", any("ADAPTER_PROVENANCE are not part of the pinned" in e for e in errs), str(errs))
# v1 shapes the gate must reject on a current-contract sidecar (synthetic re-creations)
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, lambda t: "# source_id: s002\n# read_mode: ocr\n\n" + body_only(t)))
check("v1 lowercase `# source_id:` comment header → no header block ERROR", any(CT in e and "no header block" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, body_only))
check("v1 headerless sidecar → no header block ERROR", any(CT in e and "no header block" in e for e in errs), str(errs))

# ---- pinned header values
errs, _ = run("gate_sidecar_headers", hdr(CT, "SOURCE", "raw/s002.jpg"))
check("SOURCE is a path, not a document type → ERROR", any("SOURCE 'raw/s002.jpg' is not a pinned document type" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(synlib.SIDE_SELF, "PRIMARY_CHANNEL", "native_text"))
check("PRIMARY_CHANNEL native_text (a read mode, not a channel) → ERROR", any("PRIMARY_CHANNEL 'native_text' is not a pinned channel" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "PRIMARY_CHANNEL", "deterministic_ocr"))
check("deterministic_ocr without an engine → ERROR", any("PRIMARY_CHANNEL 'deterministic_ocr' is not a pinned" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(CT, "PRIMARY_CHANNEL", "deterministic_ocr:tesseract")(d),
              inv_row(CT, lambda r: r["extractor_provenance"].__setitem__("engine", "tesseract"))(d)))
check("another OCR engine name passes", errs == [], str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(CT, "INDEPENDENT_REREAD", "false")(d), hdr(CT, "CONFIDENCE", "medium")(d),
              inv_row(CT, lambda r: r.update({"independent_reread": False, "high_risk_review_status": "needs_human_review"}))(d)))
check("different categories, neither llm_vision, marked false → ERROR",
      any("INDEPENDENT_REREAD false although the reads use different channel categories" in e for e in errs), str(errs))

errs, _ = run("gate_sidecar_headers", lambda d: (hdr(CT, "INDEPENDENT_REREAD", "false")(d), hdr(CT, "SECOND_READ_CHANNEL", "llm_vision")(d),
              hdr(CT, "CONFIDENCE", "medium")(d),
              inv_row(CT, lambda r: r.update({"second_read_channel": "llm_vision", "independent_reread": False,
                                              "high_risk_review_status": "needs_human_review"}))(d)))
check("READ_MODE hybrid_verified without an independent reread → ERROR",
      any("READ_MODE hybrid_verified is reserved" in e for e in errs), str(errs))

# ---- CONFIDENCE is rule-derived
errs, _ = run("gate_sidecar_headers", hdr(CT, "CONFIDENCE", "0.90"))
check("numeric CONFIDENCE → ERROR", any("CONFIDENCE '0.90' must be low | medium | high" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(OP, "CONFIDENCE", "medium"))
check("uncertain fields with CONFIDENCE medium → ERROR", any("carries uncertain fields → low" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "CONFIDENCE", "medium"))
check("independent reread, no uncertain field, CONFIDENCE medium → ERROR", any("CONFIDENCE medium with INDEPENDENT_REREAD true" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(LAB, "CONFIDENCE", "high"))
check("CONFIDENCE high without an independent reread → ERROR", any("CONFIDENCE high requires INDEPENDENT_REREAD true" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, LAB, lambda t: t.replace("\n\n", "\n\n[INGESTION_BLOCKED: timeout]\n\n", 1)))
check("stub with CONFIDENCE medium → ERROR", any("is an [INGESTION_BLOCKED] stub → low" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "CONFIDENCE", "low"))
check("independent reread written low (handwriting) passes", errs == [], str(errs))

# ---- header ↔ inventory row
errs, _ = run("gate_sidecar_headers", hdr(CT, "FILE_ID", "f002"))
check("FILE_ID ≠ inventory source_id → ERROR", any("FILE_ID 'f002' ≠ source_inventory source_id 's002'" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "READ_MODE", "deterministic_ocr"))
check("READ_MODE ≠ inventory → ERROR", any("READ_MODE 'deterministic_ocr' ≠ source_inventory read_mode" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "ADAPTER", "temp_raster"))
check("ADAPTER ≠ inventory → ERROR", any("ADAPTER 'temp_raster' ≠ source_inventory adapter" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "MODALITY", "image"))
check("MODALITY ≠ inventory → ERROR", any("MODALITY 'image' ≠ source_inventory modality" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(LAB, "PAGE_LABEL", "第1页，共1页"))
check("PAGE_LABEL printed but inventory page_label null → ERROR", any("PAGE_LABEL '第1页，共1页' ≠ source_inventory page_label None" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "PAGE_LABEL", "none"))
check("PAGE_LABEL none but inventory holds a label → ERROR", any("PAGE_LABEL 'none' ≠ source_inventory page_label" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", lambda d: (hdr(LAB, "PAGE_LABEL", "第1页，共1页")(d),
              inv_row(LAB, lambda r: r.__setitem__("page_label", "第1页，共1页"))(d)))
check("same label in header and inventory passes", errs == [], str(errs))
errs, _ = run("gate_sidecar_headers", hdr(DIG, "SOURCE", "discharge_summary"))
check("digest row whose SOURCE is not prior_archive_digest → ERROR", any("source_kind is 'prior_archive_digest'" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(DIG, "PRIMARY_CHANNEL", "text_layer"))
check("digest not read from prior_archive_sidecar → ERROR", any("reads PRIMARY_CHANNEL prior_archive_sidecar" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(CT, "SOURCE", "prior_archive_digest"))
check("upload row claiming SOURCE prior_archive_digest → ERROR", any("source_kind is 'upload'" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(synlib.SIDE_SELF, "PRIMARY_CHANNEL", "prior_archive_sidecar"))
check("upload read from prior_archive_sidecar → ERROR", any("prior_archive_sidecar is the digest channel only" in e for e in errs), str(errs))

# ---- gate_second_read (phase1 §4 G / §5): the table, tokens and readings are the script's
SR = "gate_second_read"
errs, warns = run(SR)
check("clean archive: second-read gate passes", errs == [], str(errs))
errs, _ = run(SR, lambda d: synlib.edit_text(d, ORD, lambda t: t.replace("卡铂 300 mg", "卡铂 30 mg", 1)))
check("body edited after the second read → body_sha256 ERROR", any(ORD in e and "body_sha256" in e for e in errs), str(errs))
errs, _ = run(SR, lambda d: synlib.edit_text(d, ORD, lambda t: re.sub(r"^\| number \|.*\n", "", t, count=1, flags=re.M)))
check("a derived span dropped from the table → ERROR", any(ORD in e and "not the recomputed second read" in e for e in errs), str(errs))
errs, _ = run(SR, order_rows("是", rows={5}))
check("a 无信号 row relabelled 是 → ERROR", any(ORD in e and "not the recomputed second read" in e for e in errs), str(errs))
errs, _ = run(SR, lambda d: synlib.edit_text(d, ORD, lambda t: t.replace("| 111期 |", "| III期 |", 1)))
check("a second-channel reading that is not the engine's string → ERROR", any(ORD in e and "not the engine's own string" in e for e in errs), str(errs))
errs, _ = run(SR, lambda d: synlib.edit_text(d, ORD, lambda t: t.replace("开立日期：2030-01-08", "开立日期：2030-01-08[OCR_UNCERTAIN:U-001]", 1)))
check("a token on an agree span → ERROR", any(ORD in e and "sits on no conflict" in e for e in errs), str(errs))
errs, _ = run(SR, lambda d: synlib.edit_text(d, ORD, lambda t: t.split("## 高风险字段复读")[0] + "## PII\n\n- 无\n"))
check("a pixel page (model_vision_primary) without the script's block → ERROR", any(ORD in e and "without a `## 高风险字段复读` block" in e for e in errs), str(errs))
errs, _ = run(SR, lambda d: synlib.edit_text(d, "raw/_extract/s006.apple_vision.json", lambda t: t.replace('"分期:111期"', '"分期:III期"', 1)))
check("engine output edited after the second read → ERROR", any(ORD in e and "changed after the second read" in e for e in errs), str(errs))
n += 1
errs, warns = synlib.gate(SR, synlib.make(tmp / f"h{n}", with_raw=False))
check("a copy without raw/: body hash checked, the rest one WARN (no ERROR)",
      errs == [] and any("checked by body_sha256 only" in w for w in warns), str(errs) + str(warns))
n += 1
errs, warns = synlib.gate(SR, synlib.make(tmp / f"h{n}", lambda d: synlib.edit_text(d, ORD, lambda t: t.replace("卡铂 300 mg", "卡铂 30 mg", 1)), with_raw=False))
check("…and a body edit is still caught there", any("body_sha256" in e for e in errs), str(errs))

# ---- phase1 §6: the one born-digital second read — an engine read of a layout-anomaly region backing a document
# intent. The family-note fixture (text_layer / native_text) gets its identity check, then a struck-through phrase.
SELF = synlib.SIDE_SELF
SELF_STEM = Path(SELF).stem


def born_digital_intent(region=True, intent="deleted", engine_text="外院检查提示肝转移"):
    def fn(d):
        import subprocess as sp
        layer = d / "raw" / "_extract" / f"{SELF_STEM}.text_layer.txt"
        layer.parent.mkdir(parents=True, exist_ok=True)
        layer.write_text("家属自述：2029-11 外院检查提示肝转移。\n", encoding="utf-8")
        p = sp.run([sys.executable, str(synlib.SCRIPTS / "second_read_align.py"), "--apply", str(d / SELF),
                    "--patient-dir", str(d), "--text-layer", str(layer)], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        lines = (d / SELF).read_text(encoding="utf-8").splitlines()
        ln = next(i for i, l in enumerate(lines, 1) if "肝转移" in l)
        def edit(text):
            text = text.replace("提示肝转移。", "提示肝转移[OCR_UNCERTAIN:U-001]。", 1)
            text = text.replace("SECOND_READ_CHANNEL: none", "SECOND_READ_CHANNEL: deterministic_ocr:apple_vision", 1)
            text = text.replace("INDEPENDENT_REREAD: false", "INDEPENDENT_REREAD: true", 1)
            text = text.replace("CONFIDENCE: medium", "CONFIDENCE: low", 1)
            entry = ("## 不确定字段\n\n- id: U-001\n  line: %d\n  field_class: diagnosis_text\n  readings:\n"
                     "    - {channel: text_layer, text: \"肝转移\", confidence: null}\n"
                     "    - {channel: \"deterministic_ocr:apple_vision\", text: \"肝转移\", confidence: 0.9}\n"
                     "  candidates: []\n  cross_doc_supported: {status: none, refs: []}\n  layout: strikethrough\n"
                     "  layout_intent: %s\n\n" % (ln, intent))
            return text.replace("## PII", entry + "## PII", 1)
        synlib.edit_text(d, SELF, edit)
        inv_row(SELF, lambda r: r.update({"second_read_channel": "deterministic_ocr:apple_vision", "independent_reread": True}))(d)
        synlib.edit_json(d, "readiness.json", lambda doc: doc["review_flags"].append(
            {"id": "RF-009", "category": "extraction_fidelity", "affected_field": "timeline.liver",
             "current_source_values": [{"value": "肝转移", "source_ref": f"{SELF}#L{ln}"}],
             "issue": "文本层与区域引擎读都显示“肝转移”被划去。", "resolution_status": "unresolved",
             "severity": "yellow", "kind": "document_intent", "uncertain_ids": ["U-001"]}))
        if region:
            (d / "raw" / "_extract" / f"{SELF_STEM}.region.json").write_text(json.dumps({
                "tool": "run_ocr_engine", "version": "1", "engine": "apple_vision", "channel": "deterministic_ocr:apple_vision",
                "pages": [{"page": 1, "lines": [{"text": engine_text, "confidence": 0.9}]}]}, ensure_ascii=False), encoding="utf-8")
    return fn


for gate_name in ("gate_sidecar_headers", "gate_second_read", "gate_review_flag_semantics"):
    errs, _ = run(gate_name, born_digital_intent())
    check(f"born-digital document intent backed by a region engine read passes {gate_name}",
          not any(SELF in e for e in errs), str([e for e in errs if SELF in e]))
errs, _ = run("gate_second_read", born_digital_intent(region=False))
check("…without the region engine output → ERROR", any(SELF in e and "without its region engine read" in e for e in errs), str(errs))
errs, _ = run("gate_second_read", born_digital_intent(intent="null"))
check("…with no document-intent entry → ERROR (the engine read exists only to back one)",
      any(SELF in e and "exists only to back a document intent" in e for e in errs), str(errs))
errs, _ = run("gate_second_read", born_digital_intent(engine_text="外院检查提示肺转移"))
check("…when the entry's engine reading is not in the region output → ERROR",
      any(SELF in e and "exists only to back a document intent" in e for e in errs), str(errs))

# ---- legacy archive: the missing-EXTRACTOR condition is one WARN, never an ERROR
legacy = synlib.make_legacy(tmp / "legacy")
errs, warns = synlib.gate("gate_sidecar_headers", legacy)
check("legacy: no ERROR", errs == [], str(errs))
check("legacy: one EXTRACTOR WARN", sum("carry no EXTRACTOR" in w for w in warns) == 1, str(warns))

print(f"sidecar-header-gate: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
