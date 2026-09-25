#!/usr/bin/env bash
# The independent review's findings on the organize gate (schemas/README.md, O-01..O-09, CHANGELOG [Unreleased]):
# every guard added for them fails without it (negative) and passes the clean archive (positive).
# All data synthetic — the clean archive is tests/fixtures/organize-regress/syn-current, each
# negative mutates one thing.
#   generation markers · required current files · jsonschema fail-closed · crash-safe gates ·
#   AGENTS.md from an earlier template · orphan sidecars · `## PII` last · body page labels ·
#   EXTRACTOR phase/files · single-file redispatch · handle-only input_ref / PT- archive_ref ·
#   every uncertainty token flagged · §6.1 severity rows · one field per flag · §1.3 entry keys ·
#   cross_doc_supported shape · reading channels · rule-6 candidates · status_basis_text /
#   setting_basis bound to sources · missing-page flags + pages_present · uneven copies ·
#   lab `## 列配对` binding + recomputation · bucket depth / originals / raw sub-buckets ·
#   vault infra names / symlinks / .nii.gz · per-worker identity deny lists · PS ellipsis.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, os, re, subprocess, sys
from pathlib import Path
repo, tmp = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, repo + "/tests/fixtures/organize-regress")
import synlib
import make_syn_current as msc

SCRIPTS = Path(repo) / "skills" / "cancer-buddy-organize" / "scripts"
VALIDATOR = SCRIPTS / "validate_structured_outputs.py"
OP, CT, LAB, SELF, DG = synlib.SIDE_OUTPATIENT, synlib.SIDE_CT, synlib.SIDE_LAB, synlib.SIDE_SELF, synlib.SIDE_DIGEST
passed = failed = 0
n = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {str(detail)[:600]}", file=sys.stderr)


def mk(mutate=None, **kw):
    global n
    n += 1
    return synlib.make(tmp / f"r{n}", mutate, **kw)


def run(gate, mutate=None, **kw):
    return synlib.gate(gate, mk(mutate), **kw)


def full(mutate=None, **kw):
    return synlib.validate(mk(mutate, **kw))


def full_after(post):
    """Build the archive (AGENTS.md needs profile.json), THEN mutate, then validate."""
    d = mk()
    post(d)
    return synlib.validate(d)


def flags(fn):
    return lambda d: synlib.edit_json(d, "readiness.json", lambda doc: fn(doc["review_flags"]))


def flag(fid, fn):
    return flags(lambda fl: fn(next(f for f in fl if f["id"] == fid)))


# ---- positive control -------------------------------------------------------------------------
rc, errs, warns = full()
check("clean archive (with its raw/_extract input) passes the whole validator", rc == 0, errs[:3])
check("…and re-computes the lab record (no 'not re-computed' WARN)", not any("not re-computed" in w for w in warns), warns)

# ---- generation markers (R2 / C9 / R14) -------------------------------------------------------
def legacy_plus(fn):
    return lambda d: (synlib.downgrade_to_legacy(d), fn(d))


rc, errs, warns = synlib.validate(synlib.make_legacy(tmp / "legacy0"))
check("wholly legacy archive: rc 0, legacy WARN", rc == 0 and any(w.startswith("archive_generation: legacy") for w in warns), errs[:3])
MARKERS = {
    "a structured file at its current version (labs 2.1)": lambda d: synlib.save(d, "labs.json", synlib.fixture_doc("labs.json")),
    "a ledger with workers[]": lambda d: synlib.save(d, "update_log.json", synlib.fixture_doc("update_log.json")),
    "a sidecar header naming EXTRACTOR": lambda d: synlib.edit_text(d, CT, lambda t: t.replace("FILE_ID: s002\n", "FILE_ID: s002\nEXTRACTOR: p1-s002-1\n", 1)),
}
for label, fn in MARKERS.items():
    d = synlib.make(tmp / f"mk_{abs(hash(label))}", legacy_plus(fn))
    out = subprocess.run([sys.executable, str(VALIDATOR), "--generation", str(d)], capture_output=True, text=True)
    check(f"marker alone ({label}) → --generation prints current", out.stdout.strip() == "current", out.stdout + out.stderr)
    rc, errs, _ = synlib.validate(d)
    check(f"marker alone ({label}) + legacy files → rc 1 (the v2.1 gates are not downgraded)", rc == 1, errs[:2])
# acute_findings.json is a safety surface every pass writes, a legacy Phase-2-only pass included — NOT a marker
d = synlib.make(tmp / "mk_acute_not_marker", legacy_plus(lambda d: synlib.write_legacy_acute(d)))
out = subprocess.run([sys.executable, str(VALIDATOR), "--generation", str(d)], capture_output=True, text=True)
check("acute_findings.json alone is not a marker → --generation prints legacy", out.stdout.strip() == "legacy", out.stdout + out.stderr)
d = synlib.make(tmp / "c01shape", lambda d: synlib.downgrade_to_legacy(d))
out = subprocess.run([sys.executable, str(VALIDATOR), "--generation", str(d)], capture_output=True, text=True)
check("a legacy-shaped schema \"1\" ledger (run_mode full, no workers[]) stays legacy (SKILL Step 1 → legacy_upgrade)",
      out.stdout.strip() == "legacy" and "markers: none" in out.stderr, out.stdout + out.stderr)

# ---- required current files (C1 / R5) ---------------------------------------------------------
import validate_structured_outputs as vso
for fname in vso.REQUIRED_CURRENT_FILES:
    rc, errs, _ = full_after(lambda d, f=fname: (d / f).unlink())
    check(f"current archive without {fname} → ERROR naming it", rc == 1 and any(e.startswith(f"{fname}: missing") for e in errs), errs[:3])
rc, errs, _ = full_after(lambda d: (d / "readiness.json").unlink() or synlib.save(d, "organize_meta.json", {
    "skill": "cancer-buddy-organize", "skill_version": None, "skill_commit": None, "skill_dirty": None,
    "skill_fingerprint": "sha256:" + "0" * 64, "generated_at": "2030-01-20T09:00:00Z",
    "pii_layer1_scan": {"worker_id": "pii-1", "clean": True}}))
check("organize_meta + no readiness.json → ERROR (review flags / recency cannot be skipped)",
      rc == 1 and any(e.startswith("readiness.json: missing") for e in errs), errs[:3])

# ---- jsonschema absent: fail closed on a current archive (R10 / prompts P0) --------------------
shim = tmp / "no_jsonschema"
(shim / "jsonschema").mkdir(parents=True)
(shim / "jsonschema" / "__init__.py").write_text("raise ImportError('blocked for the test')\n", encoding="utf-8")
env = dict(os.environ, PYTHONPATH=str(shim))
d = mk(lambda d: synlib.edit_json(d, "labs.json", lambda doc: doc["panels"][0]["values"][0].__setitem__("value", "3.46")))
p = subprocess.run([sys.executable, str(VALIDATOR), str(d)], capture_output=True, text=True, env=env)
check("no jsonschema + current archive (a candidate promoted to value) → rc 1, never 'all pass'",
      p.returncode == 1 and "jsonschema: not installed" in p.stderr and "all pass" not in p.stdout, p.stdout + p.stderr[-400:])
d = synlib.make_legacy(tmp / "legacy_nojs")
p = subprocess.run([sys.executable, str(VALIDATOR), str(d)], capture_output=True, text=True, env=env)
check("no jsonschema + legacy archive → rc 0 saying the schema rules were not verified",
      p.returncode == 0 and "lightweight checks only" in p.stdout, p.stdout + p.stderr[-300:])

# ---- crash-safe gates (R15) ---------------------------------------------------------------------
CRASH = {
    "finding_class is a list": lambda d: synlib.edit_json(d, "acute_findings.json", lambda doc: doc["findings"][0].__setitem__("finding_class", ["thrombus_embolism"])),
    "medication_refs item is an object": lambda d: synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].__setitem__("medication_refs", [{"id": "MED-001"}])),
    "missing_pages group_key is a list": lambda d: synlib.edit_json(d, "missing_items.json", lambda doc: doc["document_gaps"][0].__setitem__("group_key", ["x"])),
    "uncertainty field_class is a list": lambda d: synlib.edit_text(d, OP, lambda t: t.replace("  field_class: stage", "  field_class: [stage, other]", 1)),
}
for label, fn in CRASH.items():
    d = mk(fn)
    p = subprocess.run([sys.executable, str(VALIDATOR), str(d)], capture_output=True, text=True)
    check(f"{label} → rc 1 with readable ERROR lines, no traceback",
          p.returncode == 1 and "Traceback" not in p.stderr and "ERROR:" in p.stderr, p.stderr[-500:])

# ---- AGENTS.md filled from an earlier shipped template (R1) --------------------------------------
import importlib.util
spec = importlib.util.spec_from_file_location("fill_agents_md", SCRIPTS / "fill_agents_md.py")
fam = importlib.util.module_from_spec(spec); spec.loader.exec_module(fam)
OLD_TEMPLATE = (Path(repo) / "tests/fixtures/organize-regress/agents-md.template.d84b7eb.md").read_text(encoding="utf-8")


def old_agents(template_text=OLD_TEMPLATE):
    def fn(d):
        prof = synlib.load(d, "profile.json")
        (d / "AGENTS.md").write_text(fam.render(template_text, prof["patient_code"],
                                                fam.sanitize_one_line(prof["summary"]["one_line_condition"])), encoding="utf-8")
    return fn


d = synlib.make_legacy(tmp / "legacy_agents")
old_agents()(d)
rc, errs, warns = synlib.validate(d)
check("legacy archive whose AGENTS.md was filled from the main-era template → rc 0 + WARN",
      rc == 0 and any("filled from an earlier template" in w for w in warns), errs[:3])
d = mk()
old_agents()(d)
rc, errs, warns = synlib.validate(d)
check("current archive, AGENTS.md from a KNOWN earlier template → WARN, not ERROR",
      rc == 0 and any("filled from an earlier template" in w for w in warns), errs[:3])
d = mk()
old_agents(OLD_TEMPLATE + "\n<!-- edited -->\n")(d)
rc, errs, _ = synlib.validate(d)
check("current archive, AGENTS.md from an UNKNOWN template → ERROR", rc == 1 and any(e.startswith("agents_md:") for e in errs), errs[:3])
d = synlib.make_legacy(tmp / "legacy_stub")
(d / "AGENTS.md").write_text("# Patient archive pointer: x\n", encoding="utf-8")
rc, errs, _ = synlib.validate(d)
check("legacy archive with a stub AGENTS.md → still ERROR", rc == 1 and any(e.startswith("agents_md:") for e in errs), errs[:3])

# ---- orphan sidecar, header enums, `## PII` last, body page label (R3 / R13 / C10) -------------
ORPHAN = "07_检验/血常规/2030-01-01_血常规_示例医院.md"


def orphan(page_label="第1页 共1页", sha="0" * 64):
    def fn(d):
        text = (msc.header("lab_report", "s009", "p1-s003-1", "text_layer", "none", False, "native_text", sha,
                           page_label) + "\n\n# 版面重建\n\n合成血常规\n\n## PII\n\n- 无\n")
        (d / ORPHAN).parent.mkdir(parents=True, exist_ok=True)
        (d / ORPHAN).write_text(text, encoding="utf-8")
    return fn


rc, errs, _ = full(orphan())
check("bucket sidecar with no source_inventory row → ERROR", any("has no source_inventory.json files[] row" in e for e in errs), errs[:4])
rc, errs, _ = full(orphan(sha="not-a-hash"))
check("orphan sidecar's SHA256 placeholder is still checked → ERROR", any("SHA256 'not-a-hash'" in e for e in errs), errs[:4])
rc, errs, _ = full(orphan(page_label="第1页 共1页 联系电话13812345678"))
check("phone number in an orphan sidecar's PAGE_LABEL → pii_rescan ERROR (masked)",
      any(e.startswith("pii_rescan:") and "[phone]" in e and "13812345678" not in e for e in errs), errs[:4])
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, lambda t: t.replace("READ_MODE: hybrid_verified", "READ_MODE: fast", 1)))
check("READ_MODE outside the pinned values → ERROR", any("READ_MODE 'fast' is not one of" in e for e in errs), errs[:3])
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, lambda t: t.replace("# 版面重建", "## PII\n\n# 版面重建", 1)))
check("an early `## PII` heading (two in the file) → ERROR", any("2 `## PII` headings" in e for e in errs), errs[:3])
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, CT, lambda t: t.rstrip("\n") + "\n\n## 附录\n\n合成\n"))
check("a heading after `## PII` → ERROR", any("a heading follows `## PII`" in e for e in errs), errs[:3])
errs, _ = run("gate_sidecar_headers", lambda d: synlib.edit_text(d, LAB, lambda t: t.replace("肿瘤标志物检测（合成夹具）", "肿瘤标志物检测（合成夹具） 第1页，共2页", 1)))
check("a printed page label in the body while PAGE_LABEL is none → ERROR", any("prints a page label but PAGE_LABEL" in e for e in errs), errs[:3])
errs, _ = run("gate_sidecar_headers")
check("clean archive: no sidecar-header findings", errs == [], errs[:3])

# ---- EXTRACTOR worker phase + files; single-file redispatch (C12 / C11) -------------------------
def extractor(worker):
    return lambda d: (synlib.edit_text(d, CT, lambda t: t.replace("EXTRACTOR: p1-s002-1", f"EXTRACTOR: {worker}", 1)),
                      synlib.edit_json(d, "source_inventory.json", lambda doc: next(r for r in doc["files"] if r["source_id"] == "s002")["extractor_provenance"].__setitem__("worker_id", worker)))


errs, _ = run("gate_sidecar_headers", extractor("p2-1"))
check("sidecar authored by the Phase 2 worker → ERROR", any("is logged with phase phase2" in e for e in errs), errs[:3])
errs, _ = run("gate_sidecar_headers", extractor("p1-s001-1"))
check("sidecar authored by a Phase 1 worker that was not given that source → ERROR", any("was not given this source" in e for e in errs), errs[:3])


def multi_file_retry(d):
    def fn(doc):
        e = doc["entries"][0]
        e["workers"] = [w for w in e["workers"] if w["phase"] != "phase1_retry"] + [
            {"worker_id": "p1-s1-1", "phase": "phase1_retry", "slice_id": "s1", "status": "done", "files": ["s001", "s002", "s003", "s005"]}]
        e["degradations"] = [{"worker_id": "p1-s0-1", "reason": "timeout", "redispatched_as": ["p1-s1-1"]}]
    synlib.edit_json(d, "update_log.json", fn)


errs, _ = run("gate_update_log", multi_file_retry)
check("timed-out slice worker redispatched as ONE 4-file worker → ERROR", any("redispatched as 'p1-s1-1' with 4 files" in e for e in errs), errs[:3])
errs, _ = run("gate_update_log")
check("single-file redispatch (fixture) passes", errs == [], errs[:3])

# ---- skipped_inputs / digest_of handles (C8) -----------------------------------------------------
def inv(fn):
    return lambda d: synlib.edit_json(d, "source_inventory.json", fn)


rc, errs, _ = full(inv(lambda doc: doc["skipped_inputs"].append({"input_ref": "wangxiaoming_CT_2030.jpg", "reason": "duplicate_sha256", "sha256": "a" * 64, "size_bytes": 3})))
check("skipped_inputs input_ref = an upload name (pinyin) → schema ERROR", any("skipped_inputs.1.input_ref" in e for e in errs), errs[:3])
rc, errs, _ = full(inv(lambda doc: doc["skipped_inputs"].append({"input_ref": "skip-002", "reason": "symlink", "sha256": "b" * 64, "size_bytes": 3})))
check("skip-NNN handle with reason symlink passes", rc == 0, errs[:3])
rc, errs, _ = full(inv(lambda doc: next(r for r in doc["files"] if r["source_kind"] == "prior_archive_digest")["digest_of"].__setitem__("archive_ref", "zhangsan-archive-2029")))
check("digest_of.archive_ref that is not a PT- code → schema ERROR", any("digest_of.archive_ref" in e for e in errs), errs[:3])

# ---- every uncertainty token flagged; §6.1 rows; one field per flag (C4 / C5 / C14) -------------
G = "gate_review_flag_semantics"
errs, _ = run(G, flags(lambda fl: fl.pop(0)))
check("[OCR_UNCERTAIN:U-001] with no readiness flag → ERROR", any("[OCR_UNCERTAIN:U-001] has no readiness flag" in e for e in errs), errs[:3])
errs, _ = run(G, flag("RF-001", lambda f: f.__setitem__("severity", "yellow")))
check("uncertain stage (high-risk), no cross-document support, graded yellow → ERROR (§6.1 row 1)",
      any("RF-001 grades an uncertain high-risk field (stage) 'yellow'" in e for e in errs), errs[:3])
errs, _ = run(G, flag("RF-001", lambda f: f.update({"severity": "yellow", "cross_doc_supported": {"status": "supported", "refs": [CT + "#L14"]}})))
check("…yellow with another page's supporting reading passes (§6.1 row 2)", errs == [], errs[:3])
rc, errs, _ = full(flag("RF-001", lambda f: f.update({"severity": "yellow", "cross_doc_supported": {"status": "contradicted", "refs": [CT + "#L14"]}})))
check("cross_doc_supported contradicted graded yellow → schema ERROR (always red)", any("review_flags.0.severity" in e for e in errs), errs[:3])
rc, errs, _ = full(flag("RF-003", lambda f: f.__setitem__("severity", "yellow")))
check("category missing_pages graded yellow → schema ERROR", any("review_flags.2.severity" in e for e in errs), errs[:3])
rc, errs, _ = full(flag("RF-002", lambda f: f.__setitem__("category", "source_recency")))
check("category source_recency graded conflict / red → schema ERROR", any("review_flags.1" in e for e in errs), errs[:3])
errs, _ = run(G, flag("RF-002", lambda f: f.__setitem__("affected_field", "timeline.peritoneum、diagnosis.stage")))
check("one flag for several fields (affected_field with 、) → ERROR", any("lists several fields" in e for e in errs), errs[:3])

# ---- §1.3 entry keys, cross_doc_supported shape, reading channels, rule 6 (C3) ------------------
def op(*pairs):
    def fn(d):
        def edit(t):
            for a, b in pairs:
                assert a in t, a
                t = t.replace(a, b, 1)
            return t
        synlib.edit_text(d, OP, edit)
    return fn


for key in ("field_class", "candidates", "cross_doc_supported", "layout", "layout_intent"):
    line = next(l for l in (synlib.SRC / OP).read_text(encoding="utf-8").splitlines() if l.startswith(f"  {key}:"))
    errs, _ = run(G, op((line + "\n", "")))
    check(f"entry without {key} → ERROR", any("entry U-001 lacks" in e and key in e for e in errs), errs[:3])
errs, _ = run(G, op(("  cross_doc_supported: {status: none, refs: []}", "  cross_doc_supported: {status: supported, refs: []}")))
check("cross_doc_supported supported with no refs → ERROR", any("cross_doc_supported supported with 0 ref(s)" in e for e in errs), errs[:3])
errs, _ = run(G, op(("  cross_doc_supported: {status: none, refs: []}", "  cross_doc_supported: {status: maybe, refs: []}")))
check("cross_doc_supported status outside the vocabulary → ERROR", any("cross_doc_supported must be" in e for e in errs), errs[:3])
errs, _ = run(G, op(('{channel: text_layer, text: "晚"', '{channel: human, text: "晚"')))
check("a reading credited to a channel the header does not name → ERROR", any("is neither the header's PRIMARY_CHANNEL" in e for e in errs), errs[:3])
errs, _ = run(G, op(('{channel: text_layer, text: "晚"', '{channel: "deterministic_ocr:tesseract", text: "晚"')))
check("a second deterministic OCR engine's reading (same category as the header's) passes", errs == [], errs[:3])

lex = tmp / "lexicons"
lex.mkdir()
(lex / "ihc_markers.txt").write_text("CK19\nCK20\nCD20\nCgA\nCEA\n", encoding="utf-8")
(lex / "ln_stations.txt").write_text("10R\n10Ri\n", encoding="utf-8")
(lex / "oncology_drugs.txt").write_text("示例药A\n", encoding="utf-8")
os.environ["CB_ORGANIZE_LEXICON_DIR"] = str(lex)


def ihc(reads, cands, cross=None):
    pairs = [("  field_class: stage", "  field_class: ihc_marker"),
             ('text: "晚", confidence: 0.41', f'text: "{reads[0]}", confidence: 0.41'),
             ('{channel: text_layer, text: "晚"', f'{{channel: text_layer, text: "{reads[1]}"'),
             ("  candidates: []", "  candidates:\n" + "\n".join(f"    - {c}" for c in cands) if cands else "  candidates: []")]
    if cross:
        pairs.append(("  cross_doc_supported: {status: none, refs: []}", f"  cross_doc_supported: {cross}"))
    return op(*pairs)


errs, _ = run(G, ihc(("CgA", "CgA"), []))
check("reading CgA on both channels with candidates [] → ERROR (the mechanical list is [CgA …])",
      any("are not the mechanical list" in e and "CgA=high" in e for e in errs), errs[:3])
errs, _ = run(G, ihc(("CgA", "CgA"), ['{text: CgA, lexicon: ihc_markers, confidence: high}', '{text: CEA, lexicon: ihc_markers, confidence: low}']))
check("…the mechanical list [CgA high, CEA low] passes", errs == [], errs[:3])
# rule 6: another page prints CK19 clearly; it replaces the 3rd mechanical candidate
MECH3 = ['{text: CK20, lexicon: ihc_markers, confidence: high}', '{text: CD20, lexicon: ihc_markers, confidence: low}']
ct_ck19 = lambda d: synlib.edit_text(d, CT, lambda t: t.replace("肝实质未见明确占位。", "肝实质未见明确占位。免疫组化 CK19（+）。", 1))
ref = f"{{status: supported, refs: [\"{CT}#L16\"]}}"
errs, _ = run(G, lambda d: (ct_ck19(d), ihc(("CK2O", "CK20"), MECH3 + ['{text: CK19, lexicon: ihc_markers, confidence: low}'], ref)(d)))
check("rule 6: a clear reading on another page (cross_doc supported, printed on the cited line) in the list passes", errs == [], errs[:3])
errs, _ = run(G, ihc(("CK2O", "CK20"), MECH3 + ['{text: CgA, lexicon: ihc_markers, confidence: low}'],
                     f"{{status: supported, refs: [\"{CT}#L16\"]}}"))
check("rule 6 extra that the cited line does not print → ERROR", any("are not the mechanical list" in e for e in errs), errs[:3])
os.environ.pop("CB_ORGANIZE_LEXICON_DIR")

# ---- status_basis_text / setting_basis are the source's words (C6 / R11) -------------------------
RL = "gate_record_links"
errs, _ = run(RL, lambda d: synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].__setitem__(
    "status_basis_text", "继续示例方案B第9程")))
check("status_basis_text not in any cited source (an invented 第9程) → ERROR", any("episode EP-002 status_basis_text" in e for e in errs), errs[:3])
errs, _ = run(RL, lambda d: synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].__setitem__(
    "status_basis_text", "……")))
check("status_basis_text that is only an ellipsis → ERROR", any("holds no source words" in e for e in errs), errs[:3])
errs, _ = run(RL, lambda d: synlib.edit_json(d, "comorbidities.json", lambda doc: doc["medications"][0].update(
    {"administration_setting": "discharge", "setting_basis": "出院带药"})))
check("administration_setting discharge on an invented 出院带药 heading → ERROR", any("setting_basis" in e and "出院带药" in e for e in errs), errs[:3])
errs, _ = run(RL, lambda d: synlib.edit_json(d, "comorbidities.json", lambda doc: doc["medications"][0].__setitem__(
    "setting_basis", "病区：日间治疗中心；静滴")))
check("setting_basis with two segments, each printed in a cited source, passes", errs == [], errs[:3])

# ---- PS text ellipsis (R4) -------------------------------------------------------------------------
errs, _ = run("gate_profile_demographics", lambda d: [synlib.edit_json(d, f, lambda doc: doc["demographics"]["performance_status_verbatim"][0].__setitem__("text", "……"))
                                                      for f in ("profile.json", "patient_summary.json")])
check("performance_status_verbatim text '……' → ERROR", any("holds no source words" in e for e in errs), errs[:3])

# ---- missing pages: flag per gap, pages_present, uneven copies (C14 / R12 / R23) ----------------
PG = "gate_page_completeness"
errs, _ = run(PG, flags(lambda fl: fl.remove(next(f for f in fl if f["id"] == "RF-003"))))
check("missing_pages gap without its completeness / red flag → ERROR", any("has no readiness flag kind completeness / severity red" in e for e in errs), errs[:3])
errs, _ = run(PG, lambda d: synlib.edit_json(d, "missing_items.json", lambda doc: doc["document_gaps"][0].__setitem__("pages_present", [1, 2])))
check("missing_items pages_present ≠ the labels → ERROR", any("records pages_present [1, 2]" in e for e in errs), errs[:3])


def second_doc(d):
    """The outpatient note's page 2 arrived (s007) — and so did page 1 of ANOTHER 2-page note of the
    same day and institution (s006), without its page 2. Pages {1, 2} are both present, so the old
    rule saw one complete document plus a 'duplicate print' of page 1: no gap. The recorded gap and
    its flag are removed, as a run following the old rule would write it."""
    src = (d / OP).read_text(encoding="utf-8")
    other = d / "03_病程与叙事文书/门诊病历/2030-01-10_门诊病历_示例医院_s006.md"
    other.write_text(src.replace("FILE_ID: s001", "FILE_ID: s006"), encoding="utf-8")
    (d / "03_病程与叙事文书/门诊病历/2030-01-10_门诊病历_示例医院_s007.md").write_text(
        src.replace("FILE_ID: s001", "FILE_ID: s007").replace("PAGE_LABEL: 第1页，共2页", "PAGE_LABEL: 第2页，共2页"), encoding="utf-8")
    synlib.edit_json(d, "missing_items.json", lambda doc: doc.__setitem__("document_gaps", []))
    flags(lambda fl: fl.remove(next(f for f in fl if f["id"] == "RF-003")))(d)


import page_completeness as pc
d = mk(second_doc)
rep = pc.analyze(d)
check("uneven copies (page 1 twice, page 2 once) → a missing-page gap, not a silent duplicate",
      any(g["pages_missing"] == [2] and "重复拍摄" in g["reason_for_artifact"] for g in rep["gaps"])
      and any(x.get("uneven") for x in rep["duplicates"]), json.dumps(rep["gaps"], ensure_ascii=False)[:400])
errs, _ = synlib.gate(PG, d)
check("…and the validator requires it recorded (missing_items gap + completeness / red flag)",
      any("has no missing_pages gap" in e for e in errs) and any("has no readiness flag" in e for e in errs), errs[:3])

# ---- lab `## 列配对` binding + recomputation (C7) ------------------------------------------------
LP = "gate_lab_pairing"


def labs_v(i, fn):
    return lambda d: synlib.edit_json(d, "labs.json", lambda doc: fn(doc["panels"][i]["values"][0]))


errs, _ = run(LP, lambda d: synlib.edit_json(d, "labs.json", lambda doc: [
    doc["panels"][1]["values"][0].__setitem__("candidate_value", "21.73"),
    doc["panels"][2]["values"][0].__setitem__("candidate_value", "118.2")]))
check("two analytes' candidates swapped → ERROR", sum("does not match its `## 列配对` pair" in e for e in errs) == 2, errs[:3])
errs, _ = run(LP, lambda d: synlib.edit_json(d, "labs.json", lambda doc: [v.update(
    {"value": v["candidate_value"], "candidate_value": None, "pairing_method": "bbox", "pairing_confidence": "high"})
    for p in doc["panels"] for v in p["values"]]))
check("every linear candidate relabelled a bbox value → ERROR", sum("does not match its `## 列配对` pair" in e for e in errs) == 8, errs[:2])
errs, _ = run(LP, lambda d: synlib.edit_text(d, LAB, lambda t: t.split("## 列配对")[0] + "## PII\n\n- 无\n"))
check("lab sidecar cited by labs.json without a `## 列配对` record → ERROR", any("has no `## 列配对` record" in e for e in errs), errs[:3])
errs, _ = run(LP, flags(lambda fl: fl.remove(next(f for f in fl if f["id"] == "RF-004"))))
check("position-paired candidates without the legibility / yellow flag → ERROR", any("legibility / severity yellow" in e for e in errs), errs[:3])


def tamper_record_and_labs(d):
    """Swap two pairs in the record AND in labs.json, consistently — only the recomputation can tell."""
    def rec(t):
        return t.replace('"candidate_value": "118.2"', '"candidate_value": "@@"').replace(
            '"candidate_value": "21.73"', '"candidate_value": "118.2"').replace('"candidate_value": "@@"', '"candidate_value": "21.73"')
    synlib.edit_text(d, LAB, rec)
    synlib.edit_json(d, "labs.json", lambda doc: [doc["panels"][1]["values"][0].__setitem__("candidate_value", "21.73"),
                                                  doc["panels"][2]["values"][0].__setitem__("candidate_value", "118.2")])


errs, _ = run(LP, tamper_record_and_labs)
check("record + labs.json consistently swapped → ERROR from re-running the script on raw/_extract", any("is not what scripts/pair_lab_columns.py computes" in e for e in errs), errs[:3])
errs, warns = synlib.gate(LP, mk(tamper_record_and_labs, with_raw=False))
check("…without raw/ the record cannot be re-computed: one WARN (not silent)", errs == [] and any("not re-computed" in w for w in warns), errs + warns)
errs, _ = run(LP, lambda d: (d / "raw" / "_extract" / "s003.lab1.txt").unlink())
check("raw/ present but the recorded input missing → ERROR", any("is missing" in e for e in errs), errs[:3])

# ---- buckets: raw/ocr sub-buckets, originals, depth (R21) ---------------------------------------
BT = "gate_bucket_taxonomy"
for label, fn, needle in (
        ("raw/ under a clinical domain", lambda d: (d / "05_影像" / "raw").mkdir(), "05_影像/raw is not a pinned sub-bucket"),
        ("an original (jpg) inside a bucket", lambda d: (d / "05_影像" / "CT" / "PT_scan.jpg").write_bytes(b"x"), "is not a .md sidecar"),
        ("a directory deeper than domain/sub-bucket", lambda d: (d / "05_影像" / "CT" / "extra").mkdir(), "deeper than <domain>/<sub-bucket>")):
    errs, _ = run(BT, fn)
    check(f"{label} → ERROR", any(needle in e for e in errs), errs[:3])
errs, _ = run(BT, lambda d: (d / "05_影像" / "conversation_notes").mkdir())
check("conversation_notes/ under a clinical domain is allowed", errs == [], errs[:3])
p = subprocess.run([sys.executable, str(SCRIPTS / "check_bucket_path.py"), "05_影像/raw", "03_病程与叙事文书/其他/患者自述"], capture_output=True, text=True)
check("check_bucket_path.py (pre-write) rejects 05_影像/raw and a third directory level", p.returncode == 1 and p.stderr.count("REJECT") == 2, p.stderr)

# ---- vault infrastructure, symlinks, .nii.gz (R22) ----------------------------------------------
import inventory_hash as ih
v = tmp / "vault" / "raw"
(v / "_extract").mkdir(parents=True)
(v / "h1").mkdir()
(v / "_s002_upload.jpg").write_bytes(b"synthetic-a")
(v / "h1" / "scan.nii.gz").write_bytes(b"synthetic-b")
(v / "_extract" / "x.txt").write_bytes(b"engine-output")
(v / "_INPUT_HANDLES_20300120T090000.json").write_bytes(b"{}")
os.symlink("/etc/hosts", v / "h1" / "link.txt")
rep, _ = ih.scan(v)
check("an original whose de-identified name starts with '_' is an input", any(r.get("raw_path") == "raw/_s002_upload.jpg" for r in rep["files"]), rep["files"])
check(".nii.gz (one compressed image) is an input, not an archive container", any(r.get("raw_path") == "raw/h1/scan.nii.gz" for r in rep["files"]), rep["files"])
check("a symlink is skipped (reason symlink), never followed", [s["reason"] for s in rep["skipped_inputs"]] == ["symlink"], rep["skipped_inputs"])
check("pinned infra entries (_extract/, _INPUT_HANDLES_…json) are not inputs", len(rep["files"]) == 2, rep["files"])
rc, errs, _ = full(lambda d: ((d / "raw").mkdir(exist_ok=True), (d / "raw" / "_s009_upload.jpg").write_bytes(b"synthetic-c")))
check("validator: an unaccounted '_'-named original under raw/ → ERROR (no longer hidden as infrastructure)",
      any("input_completeness" in e and "_s009_upload.jpg" in e for e in errs), errs[:3])

# ---- per-worker identity deny lists fail closed (prompts P0) -------------------------------------
LEAK = "测试甲某"


def leak(d):
    synlib.edit_json(d, "profile.json", lambda doc: doc["summary"].__setitem__("one_line_condition", f"来源记录：{LEAK} 示例肿瘤"))


def denylist(files):
    def fn(d):
        for rel, text in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text, encoding="utf-8")
    return fn


rc, errs, _ = full(lambda d: (leak(d), denylist({"raw/_identity_denylist/p1-s001-1.json": json.dumps({"tokens": ["示例乙"]}),
                                                "raw/_identity_denylist/p1-s002-1.json": json.dumps({"tokens": [LEAK]})})(d)))
check("per-worker deny-list files are unioned → the leaked name is found (masked in the ERROR)",
      any("[identity_denylist]" in e and LEAK not in e for e in errs), errs[:3])
rc, errs, _ = full(lambda d: (leak(d), denylist({".identity_denylist.json": '{"tokens": ["示例乙"]}{"tokens": ["%s"]}' % LEAK})(d)))
check("two objects appended into one deny-list file → ERROR (fails closed, not silently disabled)",
      rc == 1 and any("pii_rescan(denylist)" in e and "not parseable" in e for e in errs), errs[:3])
rc, errs, _ = full(denylist({"raw/_identity_denylist/p1-s003-1.json": '{"tokens": ["示例乙"'}))
check("a truncated per-worker deny-list file → ERROR", any("pii_rescan(denylist)" in e for e in errs), errs[:3])

# ---- 段D narrative leads with the emergent/urgent findings (C15: the README/CHANGELOG claim is checked)
AF = synlib.fixture_doc("acute_findings.json")
lead = vso.ACUTE_SUMMARY_LEAD + "左肺上叶舌段肺动脉分支充盈缺损（肺栓塞可能）（2030-01-12）。其后是病情概要。"
check("narrative whose first sentence lists the urgent finding with its date passes",
      vso.case_summary_acute_problems(AF, {"case_summary_narrative": lead}) == [])
check("narrative that does not lead with the urgent finding → problem",
      vso.case_summary_acute_problems(AF, {"case_summary_narrative": "病历记录示例肿瘤。" + lead}) != [])
check("…naming it without its date → problem",
      any("without its date" in m for m in vso.case_summary_acute_problems(
          AF, {"case_summary_narrative": lead.replace("（2030-01-12）", "")})))
check("no emergent/urgent finding → nothing required",
      vso.case_summary_acute_problems({"findings": []}, {"case_summary_narrative": "病历记录示例肿瘤。"}) == [])

print(f"organize-review-fixes: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
