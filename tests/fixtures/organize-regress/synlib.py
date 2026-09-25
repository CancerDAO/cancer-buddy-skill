"""Helpers for the organize v2.1 gate tests (tests/unit/*.test.sh import this).

Every negative test is "copy the clean synthetic archive, mutate ONE thing, expect the
named gate to fire"; the unmutated copy is the positive control. All data synthetic.
"""
from __future__ import annotations

import copy
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ORG = REPO / "skills" / "cancer-buddy-organize"
SCRIPTS = ORG / "scripts"
SCHEMAS = ORG / "references" / "schemas"
SRC = HERE / "syn-current" / "src"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

SIDE_OUTPATIENT = "03_病程与叙事文书/门诊病历/2030-01-10_门诊病历_示例医院_s001.md"
SIDE_CT = "05_影像/CT/2030-01-12_胸部CT_示例医院.md"
SIDE_LAB = "07_检验/肿瘤标志物/2030-01-15_肿瘤标志物_示例医院.md"
SIDE_DIGEST = "03_病程与叙事文书/既往档案摘录/2029-06-01_既往档案摘录.md"
SIDE_SELF = "14_患者自管补充/患者补充/undated_家属自述.md"
SIDE_ORDER = "08_治疗/处方医嘱/2030-01-08_临时医嘱单_示例医院.md"  # a pixel page with a script-run second read


def load(d: Path, name: str):
    return json.loads((Path(d) / name).read_text(encoding="utf-8"))


def save(d: Path, name: str, obj) -> None:
    (Path(d) / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def edit_json(d: Path, name: str, fn) -> None:
    """Mutate the parsed document IN PLACE with fn (its return value is ignored)."""
    obj = load(d, name)
    fn(obj)
    save(d, name, obj)


def edit_text(d: Path, rel: str, fn) -> None:
    p = Path(d) / rel
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def fill_agents(d: Path) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / "fill_agents_md.py"), str(d)],
                   check=True, capture_output=True, text=True)


def write_extract(dst: Path) -> None:
    """The raw/_extract files the fixture's sidecars name (make_syn_current.EXTRACT_FILES): the `## 列配对`
    input of the lab sidecar, and the engine output + second-read record of the pixel-page sidecar.
    The repository ignores every raw/, so they are written into the test copy here."""
    import make_syn_current
    for rel, text in make_syn_current.EXTRACT_FILES.items():
        p = Path(dst) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def make(dst: Path, mutate=None, with_raw: bool = True) -> Path:
    dst = Path(dst)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst)
    if with_raw:
        write_extract(dst)
    if mutate:
        mutate(dst)
    fill_agents(dst)
    return dst


def validate(d: Path) -> tuple[int, list[str], list[str]]:
    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate_structured_outputs.py"), str(d)],
                          capture_output=True, text=True)
    errs = [l[len("ERROR: "):] for l in proc.stderr.splitlines() if l.startswith("ERROR: ")]
    warns = [l[len("WARN: "):] for l in proc.stderr.splitlines() if l.startswith("WARN: ")]
    return proc.returncode, errs, warns


def gate(name: str, d: Path, **kw) -> tuple[list[str], list[str]]:
    v = importlib.import_module("validate_structured_outputs")
    errors: list[str] = []
    warnings: list[str] = []
    getattr(v, name)(Path(d), errors, warnings, **kw)
    return errors, warnings


def schema_errors(schema_name: str, doc) -> list[str]:
    import jsonschema
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    val = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '$'}: {e.message}" for e in val.iter_errors(doc)]


def fixture_doc(name: str):
    return copy.deepcopy(load(SRC, name))


# --------------------------------------------------------------------------- #
# legacy (d84b7eb-era) archive derived from the clean fixture: every structured file
# back at its pre-v2.1 version with the v2.1 fields removed, no acute_findings.json,
# no organize_meta.json, headers without EXTRACTOR, hashless update_log.
# --------------------------------------------------------------------------- #
_LEGACY_DROP = {
    "readiness.json": ("2", [("", ["latest_source_date", "days_since_latest", "as_of_run_date"]),
                              ("review_flags[]", ["severity", "kind", "cross_doc_supported", "uncertain_ids"])]),
    "timeline.json": ("2", [("events[]", ["conflict_group", "acute_finding_id"])]),
    "molecular.json": ("2", [("", ["hla_typing"])]),
    "treatment_lines.json": ("2", [("episodes[]", ["status", "status_basis", "status_basis_text",
                                                   "status_as_of", "line_number", "medication_refs"])]),
    "labs.json": ("2", [("panels[].values[]", ["candidate_value", "pairing_method",
                                               "pairing_confidence", "pairing_note"])]),
    "comorbidities.json": ("2", [("medications[]", ["administration_setting", "setting_basis",
                                                    "order_role", "medication_id"])]),
    "missing_items.json": ("2", [("document_gaps[]", ["severity", "group_key", "pages_present",
                                                      "pages_missing", "page_total"])]),
}


def _targets(obj, path: str):
    if not path:
        return [obj]
    head, _, rest = path.partition(".")
    key = head[:-2] if head.endswith("[]") else head
    nxt = obj.get(key, []) if isinstance(obj, dict) else []
    items = nxt if head.endswith("[]") else [nxt]
    out = []
    for it in items:
        out.extend(_targets(it, rest))
    return out


def downgrade_to_legacy(d: Path) -> None:
    d = Path(d)
    for name, (ver, drops) in _LEGACY_DROP.items():
        doc = load(d, name)
        doc["schema_version"] = ver
        for path, keys in drops:
            for t in _targets(doc, path):
                for k in keys:
                    t.pop(k, None)
        if name == "timeline.json":
            for e in doc["events"]:
                if e["category"] == "acute_finding":
                    e["category"] = "imaging"
                if e["provenance_layer"] == "prior_archive":
                    e["provenance_layer"] = "source_reported"
        if name == "treatment_lines.json":
            for e in doc["episodes"]:
                if e["provenance_layer"] == "prior_archive":
                    e["provenance_layer"] = "patient_reported"
        if name == "missing_items.json":
            doc["document_gaps"] = [{"document_category": "检验结果报告", "gap_type": "not_in_archive",
                                     "reason_for_artifact": "合成夹具"}]
        if name == "readiness.json":
            doc["review_flags"] = [f for f in doc["review_flags"] if f["id"] != "RF-003"]
        save(d, name, doc)
    ps = load(d, "patient_summary.json")
    ps["schema_version"] = "2"
    for k in ("age_as_of", "age_observations", "birth_year", "height_cm_as_of", "weight_kg_as_of",
              "ecog_as_of", "performance_status_verbatim"):
        ps["demographics"].pop(k, None)
    save(d, "patient_summary.json", ps)
    prof = load(d, "profile.json")
    prof.pop("demographics", None)
    save(d, "profile.json", prof)
    inv = load(d, "source_inventory.json")
    inv["schema"] = "source_inventory_v2"
    inv.pop("skipped_inputs", None)
    for row in inv["files"]:
        for k in ("sha256", "size_bytes", "page_count", "page_label", "source_kind", "digest_of",
                  "second_read_channel", "independent_reread"):
            row.pop(k, None)
        row["extractor_provenance"].pop("worker_id", None)
        if row["raw_path"] is None:  # legacy runs faked a pointer for the digest row
            row["raw_path"] = "raw/ingest/prior_archive_pointer.txt"
            row["read_mode"] = "native_text"
    save(d, "source_inventory.json", inv)
    for name in ("acute_findings.json", "organize_meta.json"):
        (d / name).unlink(missing_ok=True)
    save(d, "update_log.json", {"schema_version": "1", "patient_code": prof["patient_code"],
                                "entries": [{"at": "2030-01-20T09:00:00Z", "run_mode": "full",
                                             "phase": "phase2", "input_count": 4,
                                             "source_ids": ["s001", "s002", "s003", "s005"],
                                             "summary": "legacy entry"}]})
    for sc in (SIDE_OUTPATIENT, SIDE_CT, SIDE_LAB, SIDE_DIGEST, SIDE_SELF, SIDE_ORDER):
        def strip_header(text: str) -> str:
            keep = ("SOURCE:", "FILE_ID:", "READ_MODE:", "ADAPTER:", "CONFIDENCE:", "MODALITY:")
            lines = text.splitlines()
            out = []
            in_header = True
            for line in lines:
                if in_header and not line.strip():
                    in_header = False
                if in_header and not line.startswith(keep):
                    continue
                out.append(line)
            return "\n".join(out).replace("[OCR_UNCERTAIN:U-001]", "[OCR_UNCERTAIN]") + "\n"
        edit_text(d, sc, strip_header)
    # the legacy outpatient sidecar has no `## 不确定字段` block and a body page label line
    edit_text(d, SIDE_OUTPATIENT, lambda t: t.split("## 不确定字段")[0] + "- page_label: 第1页，共2页\n\n## PII\n\n- 无\n")
    # legacy archives filed the digest under 其他 (no pinned digest bucket yet)
    old = d / SIDE_DIGEST
    new = d / "03_病程与叙事文书/其他/2029-06-01_既往整理档案摘录.md"
    new.parent.mkdir(parents=True, exist_ok=True)
    old.rename(new)
    old.parent.rmdir()
    new_rel = new.relative_to(d).as_posix()
    for name in ("timeline.json", "treatment_lines.json", "molecular.json", "source_inventory.json"):
        p = d / name
        p.write_text(p.read_text(encoding="utf-8").replace(SIDE_DIGEST, new_rel), encoding="utf-8")


def make_legacy(dst: Path) -> Path:
    return make(dst, downgrade_to_legacy)


def write_legacy_acute(d: Path, fn=None) -> None:
    """The acute_findings.json a Phase-2-only pass writes on a LEGACY archive (phase2 §4.0): the same
    finding, anchored to the impression line of the header-stripped CT sidecar, timeline_event_id null
    (no acute_finding event is added to the legacy timeline). fn(finding) mutates the finding."""
    doc = fixture_doc("acute_findings.json")
    f = doc["findings"][0]
    lines = (Path(d) / SIDE_CT).read_text(encoding="utf-8").splitlines()
    n_imp = next(i for i, l in enumerate(lines, start=1) if l.startswith("印象："))
    f.update({"source_ref": f"{SIDE_CT}#L{n_imp}", "timeline_event_id": None})
    if fn:
        fn(f)
    save(d, "acute_findings.json", doc)
