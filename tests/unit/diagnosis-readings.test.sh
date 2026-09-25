#!/usr/bin/env bash
# ORG-P1-02 — a token masks only its own span; alt_readings[]; the diagnosis source ladder's mechanical half
# (scripts/_gate_readings.py via validate_structured_outputs.gate_readings):
#   * alt_readings: the field it names keeps literal + ITS token (null → ERROR, no token → ERROR), the token sits
#     on the cited line, only text fields of the block;
#   * one_line_condition carries diagnosis.primary (or 诊断资料缺失 when primary is null);
#   * WARNs: primary without diagnosis_basis; a consistently read diagnosis while primary is null; a consistently
#     read stage / diagnosis that no structured field holds.
# Every negative mutates ONE thing of the clean synthetic archive (the positive control). All data synthetic.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/tests/fixtures/organize-regress")
import synlib

tmp = Path(sys.argv[2])
passed = failed = 0
n = 0
G = "gate_readings"
OP, ORD = synlib.SIDE_OUTPATIENT, synlib.SIDE_ORDER


def run(mutate=None):
    global n
    n += 1
    return synlib.gate(G, synlib.make(tmp / f"r{n}", mutate))


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def diag(fn):
    return lambda d: synlib.edit_json(d, "patient_summary.json", lambda doc: fn(doc["diagnosis"]))


def olc(value):
    return lambda d: synlib.edit_json(d, "profile.json", lambda doc: doc["summary"].__setitem__("one_line_condition", value))


line_dx = next(i for i, l in enumerate((synlib.SRC / OP).read_text(encoding="utf-8").splitlines(), 1) if "诊断：1." in l)
REF = f"{OP}#L{line_dx}"
ALT = {"field": "stage", "uncertain_id": "U-001", "source_ref": REF, "channel": "deterministic_ocr:apple_vision", "text": "晚"}


def with_alt(stage="[OCR_UNCERTAIN:U-001]期", **over):
    return diag(lambda dg: dg.update({"stage": stage, "alt_readings": [dict(ALT, **over)]}))


errs, warns = run()
check("clean archive: readings gate passes, no readings WARN", errs == [] and not any("readings:" in w for w in warns),
      str(errs) + str(warns))

# ---- alt_readings: literal + its own token, never a blank
errs, _ = run(with_alt())
check("stage kept as literal + its token, the other reading in alt_readings → passes", errs == [], str(errs))
errs, _ = run(with_alt(stage=None))
check("stage nulled although alt_readings marks it uncertain → ERROR (a token masks only its own span)",
      any("is null although U-001 marks it uncertain" in e for e in errs), str(errs))
errs, _ = run(with_alt(stage="晚期"))
check("stage written without its token (the alternative promoted) → ERROR",
      any("does not carry its own token" in e for e in errs), str(errs))
errs, _ = run(with_alt(source_ref=synlib.SIDE_CT + "#L18"))
check("alt_readings source_ref not citing the token's line → ERROR", any("does not cite the line holding" in e for e in errs), str(errs))
errs, _ = run(with_alt(field="icd10"))
check("alt_readings on a field that is not a text field → ERROR", any("is not a text field of this block" in e for e in errs), str(errs))
errs, _ = run(lambda d: synlib.edit_json(d, "treatment_lines.json", lambda doc: doc["episodes"][1].update(
    {"regimen": None, "alt_readings": [dict(ALT, field="regimen")]})))
check("episode regimen nulled with alt_readings → ERROR", any("episodes[1].regimen is null" in e for e in errs), str(errs))

# ---- one_line_condition carries the primary
errs, _ = run(olc("在用示例方案B"))
check("one_line_condition without diagnosis.primary → ERROR", any("leaves out diagnosis.primary" in e for e in errs), str(errs))
errs, _ = run(lambda d: (diag(lambda dg: dg.update({"primary": None, "diagnosis_basis": None}))(d), olc("在用示例方案B")(d)))
check("primary null and no 诊断资料缺失 → ERROR", any("does not say 诊断资料缺失" in e for e in errs), str(errs))
errs, _ = run(lambda d: (diag(lambda dg: dg.update({"primary": None, "diagnosis_basis": None}))(d),
                        olc("诊断资料缺失；在用示例方案B")(d),
                        synlib.edit_json(d, "profile.json", lambda doc: doc["summary"].__setitem__("primary", None))))
check("primary null with 诊断资料缺失 → passes", errs == [], str(errs))

# ---- advisory WARNs
errs, warns = run(diag(lambda dg: dg.pop("diagnosis_basis")))
check("primary without diagnosis_basis → WARN only", errs == [] and any("without diagnosis_basis" in w for w in warns), str(warns))


def diag_row(d):
    synlib.edit_text(d, ORD, lambda t: t.replace("| stage | 19 | III期 | 111期 | 无信号 |",
                                                 "| stage | 19 | III期 | 111期 | 无信号 |\n| diagnosis_text | 16 | 示例肿瘤 | 示例肿瘤 | 是 |", 1))


errs, warns = run(lambda d: (diag_row(d), diag(lambda dg: dg.update({"primary": None, "diagnosis_basis": None}))(d),
                            olc("诊断资料缺失")(d)))
check("a diagnosis both channels read while primary is null → WARN", any("read consistently by both channels" in w for w in warns),
      str(warns))
errs, warns = run(lambda d: synlib.edit_text(d, ORD, lambda t: t.replace("| III期 | 111期 | 无信号 |", "| III期 | III期 | 是 |", 1)))
check("a consistently read stage that no structured field holds → completeness WARN",
      any("completeness" in w and "III期" in w for w in warns), str(warns))

# ---- acute-findings.md §2.5: a damaged text-layer run is quoted as is, searched through verbatim_text_search
CT = synlib.SIDE_CT


def damaged(search=None):
    def fn(d):
        synlib.edit_text(d, CT, lambda t: t.replace("## PII", "## 文本层字形异常\n\n- L20：文本层「充盈缺!损」；看图读作「充盈缺损」\n\n## PII", 1))
        def af(doc):
            f = doc["findings"][0]
            f["verbatim_text"] = "左肺上叶舌段肺动脉分支充盈缺!损……请结合临床"
            if search is not None:
                f["verbatim_text_search"] = search
        synlib.edit_json(d, "acute_findings.json", af)
    return fn


errs, _ = run(damaged())
check("acute verbatim quoting a listed damaged run without verbatim_text_search → ERROR",
      any("add verbatim_text_search" in e for e in errs), str(errs))
errs, _ = run(damaged("左肺上叶舌段肺动脉分支充盈缺损……请结合临床"))
check("…with the recomputed verbatim_text_search → passes", errs == [], str(errs))
errs, _ = run(damaged("左肺上叶舌段肺动脉分支充盈缺损"))
check("…with a verbatim_text_search that is not the recomputation → ERROR", any("is not verbatim_text with the listed" in e for e in errs), str(errs))

# ---- schema: the new fields are optional and closed
ps = synlib.fixture_doc("patient_summary.json")
ps["diagnosis"]["alt_readings"] = [ALT]
check("schema accepts alt_readings", synlib.schema_errors("patient_summary.schema.json", ps) == [])
ps["diagnosis"]["diagnosis_basis"] = "guess"
check("schema rejects an unknown diagnosis_basis", bool(synlib.schema_errors("patient_summary.schema.json", ps)))
ps = synlib.fixture_doc("patient_summary.json")
ps["diagnosis"]["alt_readings"] = [dict(ALT, promoted=True)]
check("schema rejects an alt_readings item with extra keys", bool(synlib.schema_errors("patient_summary.schema.json", ps)))
tl = synlib.fixture_doc("treatment_lines.json")
tl["episodes"][1]["alt_readings"] = [dict(ALT, field="regimen")]
check("treatment_lines schema accepts episode alt_readings", synlib.schema_errors("treatment_lines.schema.json", tl) == [])

print(f"diagnosis-readings: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
