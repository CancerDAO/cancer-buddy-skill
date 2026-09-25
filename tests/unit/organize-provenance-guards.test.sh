#!/usr/bin/env bash
# Validator guards for the source-layer rules of the Phase-2 replays on legacy archives (synthetic only):
#   T  a translated acute quote: verbatim_is_translation ↔ the cited sidecar's foreign_language_paraphrase flag
#      (both directions), strict on every archive
#   D  a digest is recognised by any of its three marks (sub-bucket / inventory source_kind / SOURCE header);
#      a record citing it is prior_archive — never mixed with this archive's originals in one record
#   L  longitudinal_observations never carries a digest (prior_archive) performance-status entry
#   U  prior_archive_digest_unrecognised: other / yellow, legacy archives only, and no structured record
#      cites the flagged sidecar
#   R  profile.summary.current_regimen keeps 患者自述：/ 家属自述： when the ongoing episode is a self-report
#   F  patient_summary demographics.function_description is clinician wording found in a cited original
#   P  pair_lab_columns.py reads `--text -` / `--columns -` from stdin (the legacy lab path writes no raw/ file)
# Each negative mutates ONE thing of the clean synthetic archive; the clean copy is the positive control.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib
import validate_structured_outputs as vso

tmp = Path(sys.argv[2])
passed = failed = 0
n = 0
OP, CT, DG, SELF = synlib.SIDE_OUTPATIENT, synlib.SIDE_CT, synlib.SIDE_DIGEST, synlib.SIDE_SELF


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def mk(*fns, legacy=False):
    global n
    n += 1

    def mutate(d):
        if legacy:
            synlib.downgrade_to_legacy(d)
        for fn in fns:
            fn(d)
    return synlib.make(tmp / f"p{n}", mutate)


def gate(name, d):
    return synlib.gate(name, d)


def add_flag(flag):
    return lambda d: synlib.edit_json(d, "readiness.json", lambda doc: doc["review_flags"].append(flag))


def paraphrase_flag(rel):
    return add_flag({"id": "RF-090", "category": "foreign_language_paraphrase", "kind": "other", "severity": "yellow",
                     "affected_field": "05_影像 CT 报告原文语言", "resolution_status": "unresolved",
                     "current_source_values": [{"value": "中文转述", "source_ref": f"{rel}#L16"}],
                     "issue": "外文报告只有中文转述，需要按原文语言重新转写。"})


def af0(fn):
    return lambda d: synlib.edit_json(d, "acute_findings.json", lambda doc: fn(doc["findings"][0]))


# ---- T. translated acute quotes
d = mk()
errs, _ = gate("gate_acute_findings", d)
check("T positive control: clean archive, no translation message", not any("verbatim_is_translation" in e or
      "foreign_language_paraphrase" in e for e in errs), str(errs))
d = mk(paraphrase_flag(CT))
errs, _ = gate("gate_acute_findings", d)
check("T a finding citing a paraphrase-flagged sidecar without verbatim_is_translation → ERROR",
      any("AF-001" in e and "verbatim_is_translation is not true" in e for e in errs), str(errs))
d = mk(paraphrase_flag(CT), af0(lambda f: f.__setitem__("verbatim_is_translation", True)))
errs, _ = gate("gate_acute_findings", d)
check("T …with verbatim_is_translation true → no translation message (positive)",
      not any("verbatim_is_translation" in e for e in errs), str(errs))
d = mk(af0(lambda f: f.__setitem__("verbatim_is_translation", True)))
errs, _ = gate("gate_acute_findings", d)
check("T verbatim_is_translation true without the sidecar's paraphrase flag → ERROR",
      any("has no foreign_language_paraphrase" in e for e in errs), str(errs))
lg = synlib.make(tmp / "t_legacy", lambda d: (synlib.downgrade_to_legacy(d), synlib.write_legacy_acute(d),
                                              paraphrase_flag(CT)(d)))
errs, _ = gate("gate_acute_findings", lg)
check("T legacy archive: the same binding is an ERROR (the acute file's own bindings are strict)",
      any("verbatim_is_translation is not true" in e for e in errs), str(errs))
doc = synlib.fixture_doc("acute_findings.json")
doc["findings"][0]["verbatim_is_translation"] = "yes"
check("T schema: verbatim_is_translation is a boolean", bool(synlib.schema_errors("acute_findings.schema.json", doc)))
doc["findings"][0]["verbatim_is_translation"] = True
check("T schema: verbatim_is_translation true validates", not synlib.schema_errors("acute_findings.schema.json", doc),
      str(synlib.schema_errors("acute_findings.schema.json", doc)))

# ---- D. digest marks and one layer per record
d = mk()
errs, warns = gate("gate_prior_archive_usage", d)
check("D positive control: clean archive → no prior_archive message", errs == [] and
      not any(w.startswith("prior_archive:") for w in warns), str(errs + warns))
d = mk(lambda d: synlib.edit_json(d, "patient_summary.json",
                                  lambda doc: doc["diagnosis"]["source_refs"].append(f"{DG}#L16")))
errs, _ = gate("gate_prior_archive_usage", d)
check("D a source_reported block citing the digest next to an original → ERROR (mixed layers)",
      any("patient_summary.json $.diagnosis" in e and "next to this archive's originals" in e for e in errs), str(errs))
d = mk(lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["summary"]["source_refs"].append(f"{DG}#L17")))
errs, _ = gate("gate_prior_archive_usage", d)
check("D profile.summary (feeds AGENTS.md) citing the digest → ERROR",
      any("profile.json $.summary" in e for e in errs), str(errs))
HEADED = "03_病程与叙事文书/其他/2029-05-01_既往档案摘录副本.md"


def headed_elsewhere(layer):
    def fn(d):
        (d / HEADED).parent.mkdir(parents=True, exist_ok=True)
        (d / HEADED).write_text((d / DG).read_text(encoding="utf-8"), encoding="utf-8")
        synlib.edit_json(d, "molecular.json", lambda doc: doc["hla_typing"].append(dict(
            doc["hla_typing"][0], source_refs=[f"{HEADED}#L17"], provenance_layer=layer)))
    return fn


d = mk(headed_elsewhere("source_reported"))
errs, _ = gate("gate_prior_archive_usage", d)
check("D a digest recognised only by its SOURCE header: a source_reported record citing it → ERROR",
      any("molecular.json $.hla_typing[1]" in e and "sourced only from the prior-archive digest" in e for e in errs),
      str(errs))
d = mk(headed_elsewhere("prior_archive"))
errs, _ = gate("gate_prior_archive_usage", d)
check("D …a prior_archive record citing it is not 'cites no prior_archive_digest source' (positive)",
      not any("hla_typing[1]" in e and "cites no prior_archive_digest" in e for e in errs), str(errs))

# ---- L. the current PS series never carries a digest statement
def longitudinal(ref, layer):
    return lambda d: synlib.save(d, "longitudinal_observations.json", {
        "schema_version": "longitudinal_observations_v2", "patient_code": "PT-5A1F0C",
        "observations": [{"obs_type": "clinician_function_score", "metric": "PS（原文未注明量表）", "value": "1分",
                          "unit": None, "timestamp": "2030-01-10T00:00:00Z", "source_ref": ref,
                          "provenance_layer": layer, "verification_status": "unverified"}]})


d = mk(longitudinal(f"{OP}#L21", "source_reported"))
errs, _ = gate("gate_prior_archive_usage", d)
check("L a dated PS observation from this archive's original → no message (positive)",
      not any("longitudinal_observations" in e for e in errs), str(errs))
d = mk(longitudinal(f"{DG}#L16", "prior_archive"))
errs, _ = gate("gate_prior_archive_usage", d)
check("L a prior_archive PS observation citing the digest → ERROR",
      any("longitudinal_observations.json observations[0]" in e and "current time series" in e for e in errs), str(errs))

# ---- U. a digest-looking sidecar with no mark (legacy archive)
UNMARKED = "03_病程与叙事文书/其他/2029-05-01_旧整理摘录.md"
UFLAG = {"id": "RF-091", "category": "prior_archive_digest_unrecognised", "kind": "other", "severity": "yellow",
         "affected_field": "旧档案摘录（未标记）", "resolution_status": "unresolved",
         "current_source_values": [{"value": "旧档案摘录（未标记）", "source_ref": f"{UNMARKED}#L1"}],
         "issue": "内容像旧档案摘录但没有摘录标记，需要 legacy_upgrade。"}


def unmarked(d):
    (d / UNMARKED).parent.mkdir(parents=True, exist_ok=True)
    (d / UNMARKED).write_text("既往整理档案记载：2029-03 起曾接受示例方案A。\n", encoding="utf-8")


def cite_unmarked(d):
    synlib.edit_json(d, "timeline.json", lambda doc: doc["events"][0]["source_refs"].append(f"{UNMARKED}#L1"))


lg = mk(unmarked, add_flag(UFLAG), legacy=True)
errs, warns = gate("gate_prior_archive_usage", lg)
check("U legacy archive: flag present, no record cites the unmarked sidecar → no message (positive)",
      not any("prior_archive_digest_unrecognised" in m for m in errs + warns), str(errs + warns))
lg = mk(unmarked, add_flag(UFLAG), cite_unmarked, legacy=True)
errs, warns = gate("gate_prior_archive_usage", lg)
check("U legacy archive: a timeline event citing the flagged unmarked sidecar → reported (legacy WARN)",
      any("timeline.json" in w and "prior_archive_digest_unrecognised" in w for w in warns), str(errs + warns))
lg = mk(unmarked, add_flag(dict(UFLAG, severity="red")), legacy=True)
errs, warns = gate("gate_review_flag_semantics", lg)
check("U the flag is other / yellow (red → reported)",
      any("prior_archive_digest_unrecognised is kind other / severity yellow" in m for m in errs + warns), str(errs + warns))
cur = mk(unmarked, add_flag(UFLAG))
errs, _ = gate("gate_review_flag_semantics", cur)
check("U current archive: the flag category exists only on a legacy archive → ERROR",
      any("exists only on a legacy" in e and "prior_archive_digest_unrecognised" in e for e in errs), str(errs))

# ---- R. a self-reported current regimen keeps its marker in profile.summary
def episode_layer(layer):
    def fn(doc):
        for ep in doc["episodes"]:
            if ep["episode_id"] == "EP-002":
                ep["provenance_layer"] = layer
    return lambda d: synlib.edit_json(d, "treatment_lines.json", fn)


def current_regimen(v):
    return lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["summary"].__setitem__("current_regimen", v))


def reg_msgs(d):
    errs, warns = gate("gate_record_links", d)
    return [m for m in errs + warns if "summary.current_regimen" in m]


check("R source_reported ongoing episode, current_regimen without a marker → no message (positive)",
      reg_msgs(mk(current_regimen("示例方案B"))) == [])
check("R caregiver_reported ongoing episode, current_regimen without a marker → ERROR",
      any("家属自述：" in m for m in reg_msgs(mk(episode_layer("caregiver_reported"), current_regimen("示例方案B")))))
check("R caregiver_reported episode, 「家属自述：示例方案B」 → no message (positive)",
      reg_msgs(mk(episode_layer("caregiver_reported"), current_regimen("家属自述：示例方案B"))) == [])
check("R caregiver_reported episode with the patient marker 「患者自述：」 → ERROR (wrong speaker)",
      bool(reg_msgs(mk(episode_layer("caregiver_reported"), current_regimen("患者自述：示例方案B")))))
check("R patient_reported episode, 「患者自述：示例方案B」 → no message (positive)",
      reg_msgs(mk(episode_layer("patient_reported"), current_regimen("患者自述：示例方案B"))) == [])

# ---- F. function_description is clinician wording from a cited original
def fdesc(v, extra_ref=None):
    def fn(doc):
        doc["demographics"]["function_description"] = v
        if extra_ref:
            doc["demographics"]["source_refs"].append(extra_ref)
    return lambda d: synlib.edit_json(d, "patient_summary.json", fn)


def fd_msgs(d):
    errs, warns = gate("gate_record_links", d)
    return [m for m in errs + warns if "function_description" in m]


clin = lambda d: synlib.edit_text(d, OP, lambda s: s.replace("一般状况：PS 1分。", "一般状况：PS 1分，生活可自理。", 1))
check("F clinician wording on a cited original line → no message (positive)",
      fd_msgs(mk(clin, fdesc("生活可自理"))) == [])
check("F wording found in no cited source → ERROR", bool(fd_msgs(mk(fdesc("生活可自理")))))
check("F wording only in a caregiver supplement the block cites → ERROR (a self-description is not demographics)",
      bool(fd_msgs(mk(fdesc("外院检查提示肝转移", f"{SELF}#L16")))))
check("F null → no message", fd_msgs(mk()) == [])

# ---- P. pair_lab_columns.py stdin inputs (the legacy lab path writes nothing under raw/)
PLC = [sys.executable, str(synlib.SCRIPTS / "pair_lab_columns.py")]
cols = {"items": ["示例项A", "示例项B"], "values": ["1.20", "3.4"], "units": ["U/ml", "ng/ml"], "ranges": ["0-5", "0-10"]}
f = tmp / "cols.json"
f.write_text(json.dumps(cols, ensure_ascii=False), encoding="utf-8")
by_file = subprocess.run(PLC + ["--columns", str(f)], capture_output=True, text=True)
by_pipe = subprocess.run(PLC + ["--columns", "-"], input=json.dumps(cols, ensure_ascii=False), capture_output=True, text=True)
check("P --columns - (stdin) gives exactly the file input's output", by_pipe.returncode == 0 and
      by_pipe.stdout == by_file.stdout and json.loads(by_pipe.stdout)["pairing_method"] == "linear_position",
      by_pipe.stderr)
bad = subprocess.run(PLC + ["--columns", "-"], input="not json", capture_output=True, text=True)
check("P --columns - with a malformed stdin → exit 2", bad.returncode == 2, str(bad.returncode))
lin = "检验项目\n示例项A\n示例项B\n结果\n1.20\n3.4\n"
t_file = tmp / "lin.txt"
t_file.write_text(lin, encoding="utf-8")
a = subprocess.run(PLC + ["--text", str(t_file)], capture_output=True, text=True)
b = subprocess.run(PLC + ["--text", "-"], input=lin, capture_output=True, text=True)
check("P --text - (stdin) gives exactly the file input's output", a.stdout == b.stdout and a.returncode == b.returncode,
      a.stderr + b.stderr)

print(f"organize-provenance-guards: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
