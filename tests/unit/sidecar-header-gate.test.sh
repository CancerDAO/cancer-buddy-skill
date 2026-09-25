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

# ---- independent reread
errs, _ = run("gate_sidecar_headers", hdr(OP, "SECOND_READ_CHANNEL", "llm_vision"))
check("llm_vision second read with INDEPENDENT_REREAD true → ERROR",
      any("must be false when a read channel is llm_vision" in e for e in errs), str(errs))
errs, _ = run("gate_sidecar_headers", hdr(OP, "PRIMARY_CHANNEL", "llm_vision"))
check("llm_vision primary read with INDEPENDENT_REREAD true → ERROR",
      any("llm_vision" in e for e in errs), str(errs))
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

# ---- legacy archive: the missing-EXTRACTOR condition is one WARN, never an ERROR
legacy = synlib.make_legacy(tmp / "legacy")
errs, warns = synlib.gate("gate_sidecar_headers", legacy)
check("legacy: no ERROR", errs == [], str(errs))
check("legacy: one EXTRACTOR WARN", sum("carry no EXTRACTOR" in w for w in warns) == 1, str(warns))

print(f"sidecar-header-gate: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
