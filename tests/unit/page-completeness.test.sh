#!/usr/bin/env bash
# O-04 printed-page completeness (scripts/page_completeness.py + the validator's
# gate_page_completeness). Groups sidecars by date + document folder + institution slug +
# page total, reports missing printed pages (red missing_pages gap) and duplicates
# (two prints of the same page — info, never a gap). Synthetic sidecars only.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import sys
from pathlib import Path
repo, tmp = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, repo + "/skills/cancer-buddy-organize/scripts")
sys.path.insert(0, repo + "/tests/fixtures/organize-regress")
import page_completeness as pc

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


HDR = "SOURCE: raw/{s}.jpg\nFILE_ID: {s}\nPAGE_LABEL: {label}\n\n# 正文\n\n合成示例文字。\n"


def sidecar(root, rel, label, s="s1", legacy=False):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if legacy:
        p.write_text(f"SOURCE: raw/{s}.jpg\n\n# 正文\n\n{label}\n\n## 文档候选\n- page_label: {label}\n", encoding="utf-8")
    else:
        p.write_text(HDR.format(s=s, label=label), encoding="utf-8")


# ---- label grammar
for text, want in [("第2页，共3页", (2, 3)), ("第1页 共1页", (1, 1)), ("共1页/第1页", (1, 1)),
                   ("共 4 页，第 3 页", (3, 4)), ("第2/3页", (2, 3)), ("Page 2 of 5", (2, 5)),
                   ("2/3", (2, 3)), ("第二页，共三页", (2, 3)), ("第１页，共２页", (1, 2)),
                   ("单页；附图4幅", None), ("未见页码", None), (None, None)]:
    check(f"parse {text!r}", pc.parse_page_label(text) == want, str(pc.parse_page_label(text)))
check("institution slug strips _s001", pc.institution_slug("2030-01-10_门诊病历_示例医院_s001.md") == "示例医院")
check("institution slug without handle", pc.institution_slug("2030-01-10_门诊病历_示例医院.md") == "示例医院")
check("institution slug unknown", pc.institution_slug("2030-01-10_门诊病历.md") == "unknown")

# ---- R16: label grammar the review found unparsed (a gap went undetected) or half-parsed (a false gap)
for text, want in [("第1页(共3页)", (1, 3)), ("第1页【共3页】", (1, 3)), ("第1頁，共3頁", (1, 3)), ("1/3页", (1, 3)),
                   ("P1/3", (1, 3)), ("页码：1/3", (1, 3)), ("1/1500", None)]:
    check(f"R16 parse {text!r}", pc.parse_page_label(text) == want, str(pc.parse_page_label(text)))
check("R16 several labels without ；register every page (no false page-2 gap)",
      pc.parse_page_labels("第1页 共3页 第2页 共3页")[0] == [(1, 3), (2, 3)], str(pc.parse_page_labels("第1页 共3页 第2页 共3页")))
check("R16 body_page_label finds an explicit label, never a date or a bare fraction",
      pc.body_page_label("示例医院 第1页，共2页") == [(1, 2)] and pc.body_page_label("复查 12/31 P1/2") == [], "")
# ---- R17: a content-unit handle (s004-1) or the row's own source_id never splits one document
check("R17 slug strips a content-unit handle _s004-1", pc.institution_slug("2030-01-10_门诊病历_示例医院_s004-1.md") == "示例医院")
check("R17 slug strips an inventory handle in-003", pc.institution_slug("2030-01-10_门诊病历_示例医院_in-003.md") == "示例医院")
check("R17 slug strips the row's own source_id", pc.institution_slug("2029-06-01_摘录_示例医院_prior-20290601.md",
                                                                     ["prior-20290601"]) == "示例医院")
b17 = tmp / "b17"
sidecar(b17, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院_s004-1.md", "第1页，共2页", "s004")
sidecar(b17, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院_s004-2.md", "第2页，共2页", "s004")
check("R17 s004-1 (1/2) + s004-2 (2/2) are one complete document (no gap)", pc.analyze(b17)["gaps"] == [], str(pc.analyze(b17)["gaps"]))

# ---- 1/3 + 2/3 → page 3 missing (red gap)
a = tmp / "a"
sidecar(a, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院_s001.md", "第1页，共3页", "s001")
sidecar(a, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院_s002.md", "第2页，共3页", "s002")
r = pc.analyze(a)
check("1/3+2/3: one gap", len(r["gaps"]) == 1, str(r["gaps"]))
g = r["gaps"][0]
check("1/3+2/3: page 3 missing", g["pages_missing"] == [3] and g["pages_present"] == [1, 2] and g["page_total"] == 3)
check("1/3+2/3: gap is red missing_pages", g["gap_type"] == "missing_pages" and g["severity"] == "red")
check("1/3+2/3: group key = date|folder|institution|total",
      g["group_key"] == "2030-02-01|03_病程与叙事文书/门诊病历|示例医院|3", g["group_key"])

# ---- two complete sets 1/2+2/2 on the same day → no gap, duplicates reported
b = tmp / "b"
for i, lab in enumerate(["第1页，共2页", "第2页，共2页", "第1页，共2页", "第2页，共2页"], start=1):
    sidecar(b, f"03_病程与叙事文书/门诊病历/2030-02-02_门诊病历_示例医院_s00{i}.md", lab, f"s00{i}")
r = pc.analyze(b)
check("two 1/2+2/2 sets: no gap", r["gaps"] == [], str(r["gaps"]))
check("two 1/2+2/2 sets: duplicates reported", len(r["duplicates"]) == 1 and r["duplicates"][0]["duplicate_pages"] == [1, 2]
      and r["duplicates"][0]["copies"] == {"1": 2, "2": 2}, str(r["duplicates"]))

# ---- documents of different totals / dates / institutions never merge
c = tmp / "c"
sidecar(c, "03_病程与叙事文书/门诊病历/2030-02-03_门诊病历_示例医院_s001.md", "第1页，共2页")
sidecar(c, "03_病程与叙事文书/门诊病历/2030-02-03_门诊病历_示例医院_s002.md", "第2页，共3页")
sidecar(c, "03_病程与叙事文书/门诊病历/2030-02-03_门诊病历_另一示例医院_s003.md", "第2页，共2页")
r = pc.analyze(c)
check("different totals / institutions → three groups, three gaps", len(r["groups"]) == 3 and len(r["gaps"]) == 3, str(r["counts"]))

# ---- legacy body label (`- page_label: …`) and inventory page_label are read
d = tmp / "d"
sidecar(d, "03_病程与叙事文书/门诊病历/2030-02-04_门诊病历_示例医院_s001.md", "第1页，共4页", legacy=True)
sidecar(d, "03_病程与叙事文书/门诊病历/2030-02-04_门诊病历_示例医院_s002.md", "第3页，共4页", legacy=True)
r = pc.analyze(d)
check("legacy body label: pages 2 and 4 missing", r["gaps"] and r["gaps"][0]["pages_missing"] == [2, 4], str(r["gaps"]))
check("legacy body label source recorded", r["groups"][0]["sidecars"][0]["label_source"] == "legacy_body_line")
e = tmp / "e"
p = e / "05_影像/CT/2030-02-05_胸部CT_示例医院.md"
p.parent.mkdir(parents=True)
p.write_text("SOURCE: raw/s9.jpg\nFILE_ID: f9\n\n# 正文\n", encoding="utf-8")
(e / "source_inventory.json").write_text('{"files":[{"sidecar_path":"05_影像/CT/2030-02-05_胸部CT_示例医院.md","page_label":"第1页，共2页"}]}', encoding="utf-8")
r = pc.analyze(e)
check("inventory page_label is used", r["gaps"] and r["gaps"][0]["pages_missing"] == [2] and
      r["groups"][0]["sidecars"][0]["label_source"] == "inventory", str(r["gaps"]))
f = tmp / "f"
sidecar(f, "03_病程与叙事文书/门诊病历/2030-02-06_门诊病历_示例医院.md", "第5页，共3页")
r = pc.analyze(f)
check("page number above total → invalid, not a gap", r["invalid"] and r["gaps"] == [])

# ---- one sidecar covering several printed pages lists every label, `；`-separated
#      (organizer-prompt-phase1-ocr.md §3); each page is registered.
check("parse_page_labels: three pages", pc.parse_page_labels("第1页，共3页；第2页，共3页；第3页，共3页")
      == ([(1, 3), (2, 3), (3, 3)], []))
check("parse_page_labels: 共y页/第x页 list", pc.parse_page_labels("共2页/第1页;共2页/第2页") == ([(1, 2), (2, 2)], []))
check("parse_page_labels: one label containing ；is still one label", pc.parse_page_labels("第1页；共3页") == ([(1, 3)], []))
check("parse_page_labels: unparsed segment reported", pc.parse_page_labels("第1页，共3页；none；第3页，共3页")
      == ([(1, 3), (3, 3)], ["none"]))
check("parse_page_label keeps the single-value contract", pc.parse_page_label("第1页，共3页；第2页，共3页") == (1, 3))
m = tmp / "m"
sidecar(m, "06_分子与组学/NGS报告/2030-02-07_NGS报告_示例医院.md", "第1页，共3页；第2页，共3页；第3页，共3页")
r = pc.analyze(m)
check("complete 3-page PDF in one sidecar → no gap", r["gaps"] == [] and r["groups"][0]["pages_present"] == [1, 2, 3], str(r))
m2 = tmp / "m2"
sidecar(m2, "06_分子与组学/NGS报告/2030-02-07_NGS报告_示例医院.md", "第1页，共4页；第2页，共4页；第4页，共4页")
r = pc.analyze(m2)
check("multi-page sidecar missing one page → only that page", len(r["gaps"]) == 1 and r["gaps"][0]["pages_missing"] == [3], str(r["gaps"]))
m3 = tmp / "m3"
sidecar(m3, "06_分子与组学/NGS报告/2030-02-07_NGS报告_示例医院.md", "第1页，共2页；第2页，共2页；第1页，共1页")
r = pc.analyze(m3)
check("segments with different totals go to their own groups", len(r["groups"]) == 2 and r["gaps"] == [], str(r["groups"]))

# the three cases named in the routed request, verbatim
m4 = tmp / "m4"
sidecar(m4, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院.md", "第1页，共3页；第3页，共3页")
r = pc.analyze(m4)
check("one sidecar 1/3；3/3 → page 2 missing", [g["pages_missing"] for g in r["gaps"]] == [[2]], str(r["gaps"]))
m5 = tmp / "m5"
sidecar(m5, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院.md", "第1页，共3页；第2页，共3页；第3页，共3页")
r = pc.analyze(m5)
check("one sidecar 1/3；2/3；3/3 → no gap", r["gaps"] == [] and r["groups"][0]["pages_present"] == [1, 2, 3], str(r))
m6 = tmp / "m6"
sidecar(m6, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院.md", "第1页，共4页；第2页，共4页")
sidecar(m6, "03_病程与叙事文书/门诊病历/2030-02-01_门诊病历_示例医院_f007.md", "第4页，共4页", s="s2")
r = pc.analyze(m6)
check("sidecar A 1/4；2/4 + sidecar B (_f007) 4/4, same group → page 3 missing",
      len(r["groups"]) == 1 and [g["pages_missing"] for g in r["gaps"]] == [[3]], str(r["groups"]))

# ---- validator binding: a detected gap must be a missing_pages gap in missing_items.json
try:
    import jsonschema  # noqa: F401
    import synlib
except ImportError:
    print("SKIP: jsonschema not installed (validator half)", file=sys.stderr)
else:
    clean = synlib.make(tmp / "v1")
    errs, _ = synlib.gate("gate_page_completeness", clean)
    check("clean archive: recorded gap matches → pass", errs == [], str(errs))
    drop = synlib.make(tmp / "v2", lambda d: synlib.edit_json(d, "missing_items.json",
                       lambda doc: doc.__setitem__("document_gaps", [])))
    errs, _ = synlib.gate("gate_page_completeness", drop)
    check("unrecorded missing page → ERROR", any("has no missing_pages gap" in e for e in errs), str(errs))
    wrong = synlib.make(tmp / "v3", lambda d: synlib.edit_json(d, "missing_items.json",
                        lambda doc: doc["document_gaps"][0].update({"pages_missing": [3], "page_total": 3})))
    errs, _ = synlib.gate("gate_page_completeness", wrong)
    check("recorded pages ≠ printed labels → ERROR", any("the page labels show" in e for e in errs), str(errs))
    def multipage(d):
        lab = "第1页，共3页；第2页，共3页；第3页，共3页"
        synlib.edit_text(d, synlib.SIDE_CT, lambda t: t.replace("PAGE_LABEL: 第1页 共1页", "PAGE_LABEL: " + lab, 1))
        synlib.edit_json(d, "source_inventory.json", lambda doc: next(
            r for r in doc["files"] if r["sidecar_path"] == synlib.SIDE_CT).__setitem__("page_label", lab))
    mp = synlib.make(tmp / "v5", multipage)
    errs, _ = synlib.gate("gate_page_completeness", mp)
    check("current archive: complete multi-page label → no missing-page ERROR", errs == [], str(errs))
    legacy = synlib.make_legacy(tmp / "v4")
    errs, warns = synlib.gate("gate_page_completeness", legacy)
    check("legacy archive: unrecorded gap is a WARN", errs == [] and any("page_completeness" in w for w in warns))

print(f"page-completeness: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
