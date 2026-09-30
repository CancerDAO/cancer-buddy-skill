"""Render tests + fixture integrity: python3 -m unittest discover -s tests (from the repo root)."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "cancer-buddy" / "scripts"))

from cblib import render  # noqa: E402
from cblib.common import read_frontmatter, today  # noqa: E402

SYN = REPO / "tests" / "fixtures" / "synthetic"
FIXTURE = SYN / "PT-0000SYN001"
REF_RE = re.compile(r"^(?P<path>[^#\s]+\.md)#L(?P<a>\d+)-L(?P<b>\d+)$")

SECTIONS = ["需要尽快告知治疗团队的发现", "自上次以来的变化", "基本信息", "诊断与分期", "病情概要", "趋势图",
            "分子检测", "近期检验", "治疗经过", "需要核对的地方"]


def identity_strings(pd):
    out = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and len(o) >= 2:
            out.append(o)
    walk(json.loads((pd / "raw" / "_identity.json").read_text(encoding="utf-8")))
    return out


class RenderBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-render-"))
        self.pd = self.tmp / FIXTURE.name
        shutil.copytree(FIXTURE, self.pd)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self, name):
        return json.loads((self.pd / name).read_text(encoding="utf-8"))

    def save(self, name, obj):
        (self.pd / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def html(self, **kw):
        return render.render_case_summary(self.pd, **kw).read_text(encoding="utf-8")


class CaseSummaryTest(RenderBase):
    def test_full_fixture_all_sections_in_order(self):
        out = render.render_case_summary(self.pd)
        self.assertEqual(out, self.pd / "病情简要总结.html")
        h = out.read_text(encoding="utf-8")
        pos = [h.find(f"<h2>{s}</h2>") for s in SECTIONS]
        self.assertTrue(all(p > 0 for p in pos), dict(zip(SECTIONS, pos)))
        self.assertEqual(pos, sorted(pos))
        self.assertIn('<meta name="generator" content="cancer-buddy v2 render">', h)
        self.assertIn("本页是资料索引，不替代主诊医生的判断", h)
        self.assertEqual(h.count("<svg"), 5)                     # 4 trends + treatment swimlane
        self.assertIn("@page", h)
        # stale banner at the top, from readiness.json verbatim
        self.assertIn("本档案最新一份资料日期为 2026-08-25，距今 21 天，之后如有新检查请补充", h)
        self.assertLess(h.find("距今 21 天"), h.find("需要尽快告知治疗团队的发现"))
        # changes since last
        self.assertIn("2026-08-22 起 CA19-9 改用电化学发光法检测", h)

    def test_offline_and_no_scripts(self):
        h = self.html()
        self.assertNotIn("<script", h.lower())
        self.assertNotIn("<link", h.lower())
        self.assertNotIn("<img", h.lower())
        self.assertIsNone(re.search(r"(src|href)=\"https?:", h))
        self.assertNotIn("@import", h)
        self.assertNotIn("url(http", h)

    def test_red_only_for_critical(self):
        h = self.html()
        # the only red elements are the report's own 危急值 (NEUT# 0.42)
        crit = re.findall(r'<span class="crit">([^<]*)</span>', h)
        self.assertEqual(sorted(crit), sorted(["0.42", "↓ 危急值"]))
        # NEUT# is not among the 4 summary trends, so no chart point is red either
        self.assertEqual(h.count('fill="#c0392b"'), 0)
        # acute box and review flags use amber/yellow, never the critical red
        body = h.split("</style>")[1]
        self.assertEqual(body.count("#c0392b"), 0)
        self.assertIn('class="acute"', body)
        self.assertIn('class="flagbox"', body)

    def test_snapshot_versions(self):
        self.html()
        self.html()                                      # identical output -> no new snapshot
        vdir = self.pd / "case_summary_versions"
        self.assertEqual(sorted(p.name for p in vdir.iterdir()), [f"病情简要总结_{today()}.html"])
        narr = self.pd / ".work" / "summary_narrative.json"
        data = json.loads(narr.read_text(encoding="utf-8"))
        data["narrative"] += "（补充一句）"
        narr.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.html()
        names = sorted(p.name for p in vdir.iterdir())
        self.assertEqual(names, [f"病情简要总结_{today()}.html", f"病情简要总结_{today()}_2.html"])
        self.html(snapshot=False)
        self.assertEqual(len(list(vdir.iterdir())), 2)

    def test_core_facts_never_dropped(self):
        h = self.html()
        self.assertIn("待核对（读作 pT3；另一读法 pT2）", h)
        self.assertIn("N1a", h)
        for gene in ("KRAS", "TP53", "APC", "ATM"):
            self.assertIn(gene, h)
        self.assertIn("c.34G&gt;T (p.G12C)", h)
        self.assertIn("23.4%", h)
        self.assertIn("FOLFIRI+贝伐珠单抗", h)
        self.assertIn("今日第 14 程", h)
        self.assertIn("甲状腺乳头状癌", h)                         # second primary
        self.assertIn("意义不明（VUS）", h)

    def test_uncertain_stage_rendered_as_to_check(self):
        h = self.html()
        self.assertIn('<span class="unc">待核对（读作 pT3；另一读法 pT2）</span>N1a', h)
        self.assertNotIn("{?", h)

    def test_single_reading_marker(self):
        ps = self.load("patient_summary.json")
        ps["diagnosis"]["stage"] = "{?pT4a}N0"
        self.save("patient_summary.json", ps)
        prof = self.load("profile.json")
        prof["summary"]["stage"] = "{?pT4a}N0"
        self.save("profile.json", prof)
        self.assertIn("待核对（读作 pT4a）N0", re.sub(r"<[^>]+>", "", self.html()))

    def test_structured_text_fields_never_render_as_python_repr(self):
        tx = self.load("treatment_lines.json")
        tx["episodes"][0]["clinician_reported_response"] = {"verbatim": "病灶较前缩小", "source": "CT"}
        self.save("treatment_lines.json", tx)
        h = self.html()
        self.assertNotIn("{&#x27;", h)
        self.assertIn("病灶较前缩小", h)

    def test_acute_box_holds_only_emergent_and_urgent(self):
        af = self.load("acute_findings.json")
        af["findings"].append({"finding_id": "AF-9", "label": "HCG 复查提示", "verbatim_text": "repeat in 48 hours",
                               "acuity": "advisory", "exam_date": "2026-08-01"})
        self.save("acute_findings.json", af)
        h = self.html()
        box = h.split('<section class="acute">')[1].split("</section>")[0]
        self.assertNotIn("repeat in 48 hours", box)
        self.assertIn("报告里写的复查提示", h)
        self.assertIn("repeat in 48 hours", h)

    def test_labs_table_is_latest_value_only(self):
        h = self.html()
        table = h.split("<h2>近期检验</h2>")[1].split("</section>")[0]
        self.assertEqual(table.count("<td>中性粒细胞绝对值</td>"), 1)

    def test_candidate_value_never_shown(self):
        h = self.html()
        self.assertNotIn("2.93", h)
        self.assertIn("中性粒细胞绝对值一栏空白", h)            # surfaced as a review item instead
        labs = self.load("labs.json")                          # latest reading misaligned: marked in the table
        for p in labs["panels"]:
            for v in p["values"]:
                if v.get("candidate_value") is not None:
                    v["date"] = "2026-09-01"
                    v["flag_normalized"] = "low"
        self.save("labs.json", labs)
        h = self.html()
        self.assertNotIn("2.93", h)
        self.assertIn("表格对不齐，读数未核实", h)

    def test_age_weight_with_dates_and_provenance(self):
        text = re.sub(r"<[^>]+>", "", self.html())
        self.assertIn("55 岁（2026-08-25 记录）", text)
        self.assertIn("63 kg（2026-08-25 记录）", text)
        self.assertIn("家属自述", text)
        self.assertIn("日期不详", text)                             # undated family statement
        self.assertNotIn("52 岁", text)                            # age history is not a conflict flag

    def test_acute_box_present_first(self):
        h = self.html()
        self.assertIn("右肺下叶后基底段肺动脉分支充盈缺损，考虑肺栓塞，请结合临床。", h)
        self.assertIn("这是报告里写到的、需要尽快告知治疗团队的发现", h)
        self.assertLess(h.find('class="acute"'), h.find("<h2>基本信息</h2>"))

    def test_acute_box_absent(self):
        self.save("acute_findings.json", {"findings": []})
        h = self.html()
        self.assertNotIn("需要尽快告知治疗团队的发现", h)
        self.assertNotIn('class="acute"', h)

    def test_translated_finding_labelled(self):
        af = self.load("acute_findings.json")
        af["findings"][0]["verbatim_is_translation"] = True
        self.save("acute_findings.json", af)
        self.assertIn("转述，非报告原句", self.html())

    def test_no_changes_or_stale_when_absent(self):
        (self.pd / ".work" / "summary_narrative.json").write_text(json.dumps({"narrative": "一段话。"}), encoding="utf-8")
        r = self.load("readiness.json")
        r["days_since_latest"] = 5
        self.save("readiness.json", r)
        h = self.html()
        self.assertNotIn("自上次以来的变化", h)
        self.assertNotIn("之后如有新检查请补充", h)
        self.assertIn("一段话。", h)

    def test_identity_name_never_in_output(self):
        idents = identity_strings(self.pd)
        self.assertIn("张某某示例", idents)
        h = self.html()
        vp = render.render_visit_prep(self.pd, SYN / "visit_prep.json").read_text(encoding="utf-8")
        for s in idents:
            self.assertNotIn(s, h)
            self.assertNotIn(s, vp)

    def test_identity_masked_even_if_leaked_into_json(self):
        narr = {"narrative": "张某某示例 的资料。", "changes_since_last": ["电话 13900001234"]}
        (self.pd / ".work" / "summary_narrative.json").write_text(json.dumps(narr, ensure_ascii=False), encoding="utf-8")
        h = self.html()
        self.assertNotIn("张某某示例", h)
        self.assertNotIn("13900001234", h)

    def test_html_escapes_injected_script(self):
        evil = '<script>alert("x")</script>'
        labs = self.load("labs.json")
        labs["panels"][0]["analyte"] = evil
        labs["panels"][0]["values"][0]["raw_value"] = evil
        self.save("labs.json", labs)
        af = self.load("acute_findings.json")
        af["findings"][0]["label"] = evil
        self.save("acute_findings.json", af)
        mol = self.load("molecular.json")
        mol["variants"][0]["variant"] = evil + "{?a<b|c>d}"
        self.save("molecular.json", mol)
        h = self.html()
        self.assertNotIn("<script", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn("读作 a&lt;b；另一读法 c&gt;d", h)

    def test_empty_patient_dir(self):
        empty = self.tmp / "PT-00000EMPTY"
        empty.mkdir()
        (empty / "profile.json").write_text(json.dumps({"patient_code": "PT-00000EMPTY", "locale": "zh-CN"}),
                                            encoding="utf-8")
        h = render.render_case_summary(empty).read_text(encoding="utf-8")
        self.assertIn("资料缺失", h)
        self.assertNotIn("需要尽快告知治疗团队的发现", h)
        self.assertNotIn("之后如有新检查请补充", h)
        self.assertIn("暂不画趋势图", h)
        for s in SECTIONS[2:]:
            self.assertIn(f"<h2>{s}</h2>", h)
        self.assertTrue((empty / "case_summary_versions").is_dir())

    def test_totally_empty_dir_and_bad_json_shapes(self):
        empty = self.tmp / "PT-00000NONE0"
        empty.mkdir()
        self.assertIn("资料缺失", render.render_case_summary(empty, snapshot=False).read_text(encoding="utf-8"))
        # wrong container shapes must not crash
        for name in ("labs.json", "molecular.json", "treatment_lines.json", "acute_findings.json"):
            (empty / name).write_text("[]", encoding="utf-8")
        (empty / "patient_summary.json").write_text(json.dumps({"diagnosis": {"stage": None, "metastasis_sites": [None]}}),
                                                    encoding="utf-8")
        render.render_case_summary(empty, snapshot=False)

    def test_english_locale(self):
        prof = self.load("profile.json")
        prof["locale"] = "en"
        self.save("profile.json", prof)
        h = self.html()
        self.assertIn("<h1>Case summary</h1>", h)
        self.assertIn("To be checked (read as pT3; could also be pT2)", h)
        self.assertIn("FOLFIRI+贝伐珠单抗", h)                     # clinical strings stay verbatim
        self.assertIn('lang="en"', h)


class VisitPrepTest(RenderBase):
    def test_visit_prep(self):
        out = render.render_visit_prep(self.pd, SYN / "visit_prep.json")
        self.assertEqual(out, self.pd / "就诊准备包.html")
        h = out.read_text(encoding="utf-8")
        for s in ("医生 30 秒速览", "想问医生的问题", "要带的东西", "上次以来的变化"):
            self.assertIn(f"<h2>{s}</h2>", h)
        self.assertLess(h.find("医生 30 秒速览"), h.find("想问医生的问题"))
        self.assertIn('<div class="flagbox"><h3>请医生帮忙确认</h3>', h)     # review flags: soft yellow box
        self.assertNotIn('class="crit"', h)
        self.assertNotIn("#c0392b\"", h.split("</style>")[1])
        self.assertIn("待核对（读作 pT3；另一读法 pT2）", h)
        self.assertIn("出处：病理报告 2023-03-15", h)
        self.assertIn('<meta name="generator" content="cancer-buddy v2 render">', h)
        self.assertNotIn("<script", h)

    def test_first_visit_without_changes(self):
        data = json.loads((SYN / "visit_prep.json").read_text(encoding="utf-8"))
        data["visit_type"] = "first"
        data["changes_since_last"] = []
        p = self.tmp / "vp.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        h = render.render_visit_prep(self.pd, p).read_text(encoding="utf-8")
        self.assertIn("首次就诊", h)
        self.assertNotIn("上次以来的变化", h)

    def test_empty_visit_prep(self):
        p = self.tmp / "vp.json"
        p.write_text("{}", encoding="utf-8")
        h = render.render_visit_prep(self.pd, p).read_text(encoding="utf-8")
        self.assertIn("资料缺失", h)


class FixtureIntegrityTest(unittest.TestCase):
    """The synthetic fixture must obey the §4 contract it is meant to exercise."""

    @classmethod
    def setUpClass(cls):
        cls.lines = {}

    def cited(self, ref):
        m = REF_RE.match(ref)
        self.assertIsNotNone(m, ref)
        path = FIXTURE / m.group("path")
        self.assertTrue(path.is_file(), ref)
        lines = self.lines.setdefault(path, path.read_text(encoding="utf-8").splitlines())
        a, b = int(m.group("a")), int(m.group("b"))
        self.assertTrue(1 <= a <= b <= len(lines), ref)
        return "\n".join(lines[a - 1:b])

    def walk(self, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("source_refs", "source_ref", "metastasis_source_refs"):
                    for r in (v if isinstance(v, list) else [v]):
                        if r:
                            yield r
                else:
                    yield from self.walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from self.walk(v)

    def test_all_json_refs_resolve(self):
        n = 0
        for p in list(FIXTURE.glob("*.json")) + [SYN / "visit_prep.json"]:
            if p.name == "source_inventory.json":
                continue
            for r in self.walk(json.loads(p.read_text(encoding="utf-8"))):
                self.cited(r)
                n += 1
        self.assertGreater(n, 50)

    def test_md_anchors_resolve(self):
        for name in ("case_text.md", "timeline.md"):
            refs = re.findall(r"\[\[src:([^\]\s]+)\]\]", (FIXTURE / name).read_text(encoding="utf-8"))
            self.assertTrue(refs)
            for r in refs:
                self.cited(r)

    def test_acute_verbatim_and_lab_raw_values_in_cited_lines(self):
        for f in json.loads((FIXTURE / "acute_findings.json").read_text(encoding="utf-8"))["findings"]:
            self.assertIn(f["verbatim_text"], self.cited(f["source_ref"]))
        for panel in json.loads((FIXTURE / "labs.json").read_text(encoding="utf-8"))["panels"]:
            for v in panel["values"]:
                if v.get("raw_value") not in (None, ""):
                    self.assertIn(v["raw_value"], self.cited(v["source_refs"][0]), (panel["analyte"], v["date"]))

    def test_sidecar_front_matter(self):
        sidecars = [p for p in FIXTURE.rglob("*.md") if re.match(r"^(0[1-9]|1[0-5]|99)_", p.relative_to(FIXTURE).parts[0])]
        self.assertGreaterEqual(len(sidecars), 16)
        for p in sidecars:
            text = p.read_text(encoding="utf-8")
            meta, _ = read_frontmatter(text)
            for k in ("source_id", "source_file", "pages", "doc_kind", "doc_date", "institution", "bucket",
                      "language", "read", "uncertain"):
                self.assertIn(k, meta, (p, k))
            self.assertEqual(int(meta["uncertain"]), text.count("{?"), p)
            self.assertEqual(meta["bucket"], "/".join(p.relative_to(FIXTURE).parts[:-1]), p)

    def test_no_identity_in_derived_files(self):
        idents = identity_strings(FIXTURE)
        for p in FIXTURE.rglob("*"):
            if p.is_file() and "raw" not in p.relative_to(FIXTURE).parts:
                text = p.read_text(encoding="utf-8")
                for s in idents:
                    self.assertNotIn(s, text, p)
        for s in idents:
            self.assertNotIn(s, (SYN / "visit_prep.json").read_text(encoding="utf-8"))

    def test_fixture_scenarios_present(self):
        ps = json.loads((FIXTURE / "patient_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(ps["diagnosis"]["stage"], "{?pT3|pT2}N1a")
        self.assertTrue(ps["diagnosis"]["additional_primaries"])
        self.assertEqual([a["value"] for a in ps["demographics"]["age_observations"]], [52, 55])
        r = json.loads((FIXTURE / "readiness.json").read_text(encoding="utf-8"))
        self.assertGreater(r["days_since_latest"], 14)
        self.assertFalse([f for f in r["review_flags"] if f["kind"] == "conflict"])   # 52 vs 55 is not a conflict
        self.assertTrue(list((FIXTURE / "15_其他资料" / "肠道菌群检测").glob("*.md")))
        self.assertTrue(list((FIXTURE / "99_无关文件").glob("*")))
        gaps = json.loads((FIXTURE / "missing_items.json").read_text(encoding="utf-8"))["document_gaps"]
        self.assertIn("missing_pages", [g["gap_type"] for g in gaps])
        tl = json.loads((FIXTURE / "timeline.json").read_text(encoding="utf-8"))["events"]
        self.assertTrue([e for e in tl if e["date"] is None and e["provenance_layer"] == "caregiver_reported"])


if __name__ == "__main__":
    unittest.main()
