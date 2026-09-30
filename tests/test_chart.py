"""Chart tests: python3 -m unittest discover -s tests (from the repo root)."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "cancer-buddy" / "scripts"))

from cblib import chart  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "synthetic" / "PT-0000SYN001"


class ChartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-chart-"))
        self.pd = self.tmp / FIXTURE.name
        shutil.copytree(FIXTURE, self.pd)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _labs(self):
        return json.loads((self.pd / "labs.json").read_text(encoding="utf-8"))

    def _write_labs(self, obj):
        (self.pd / "labs.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    # --- series ------------------------------------------------------------------------
    def test_unknown_metric_is_none(self):
        self.assertIsNone(chart.series_for(self.pd, "PSA"))

    def test_series_point_fields(self):
        s = chart.series_for(self.pd, "cea")          # case-insensitive
        p = s["points"][0]
        for k in ("date", "value", "unit", "reference_range", "report_flag", "critical_flag", "method", "source_ref"):
            self.assertIn(k, p)
        self.assertTrue(p["source_ref"].startswith("07_检验/肿瘤标志物/"))

    def test_incomparable_unit_excluded(self):
        s = chart.series_for(self.pd, "CEA")
        self.assertEqual(s["unit"], "ng/mL")
        self.assertEqual([p["date"] for p in s["points"]], ["2026-05-28", "2026-07-03", "2026-08-22"])
        self.assertEqual([(x["point"]["unit"], x["reason"]) for x in s["excluded"]], [("μg/L", "unit")])
        self.assertEqual(s["reference_range"], "0-5")

    def test_method_change_splits_segments(self):
        s = chart.series_for(self.pd, "CA19-9")
        self.assertEqual(len(s["points"]), 3)
        self.assertEqual([len(seg) for seg in s["segments"]], [2, 1])
        self.assertEqual(s["method_changes"][0]["to"], "电化学发光法")
        self.assertIsNone(s["reference_range"])       # 0-37 vs 0-27: no band
        svg = chart.svg_trend(s)
        self.assertEqual(svg.count("<polyline"), 1)   # the new-method point is not joined to the old line
        self.assertNotIn(chart.BAND, svg)

    def test_candidate_value_never_plotted(self):
        s = chart.series_for(self.pd, "NEUT#")
        self.assertNotIn("2026-07-06", [p["date"] for p in s["points"]])
        self.assertNotIn(2.93, [p["value"] for p in s["points"]])
        self.assertIn("unverified_read", [x["reason"] for x in s["excluded"]])
        self.assertNotIn("2.93", chart.svg_trend(s))
        page = chart.render_chart_page(self.pd, "NEUT#").read_text(encoding="utf-8")
        self.assertNotIn("2.93", page)
        self.assertIn("读数未核实", page)

    def test_null_value_even_with_candidate_only_is_not_a_point(self):
        labs = {"panels": [{"analyte": "CEA", "normalized_analyte": "CEA", "values": [
            {"date": "2026-01-01", "value": None, "raw_value": "7.7", "candidate_value": 7.7, "unit": "ng/mL"},
            {"date": "2026-02-01", "value": None, "raw_value": "8.8", "candidate_value": 8.8, "unit": "ng/mL"}]}]}
        self._write_labs(labs)
        self.assertEqual(chart.series_for(self.pd, "CEA")["points"], [])
        self.assertNotIn("CEA", chart.trend_candidates(self.pd))

    # --- candidates ----------------------------------------------------------------------
    def test_trend_candidates_tumor_markers_first_not_by_count(self):
        c = chart.trend_candidates(self.pd, limit=10)
        hb = chart.series_for(self.pd, "Hb")
        cea = chart.series_for(self.pd, "CEA")
        # Hb has more points and a later latest date, yet CEA comes first.
        self.assertGreater(len(hb["points"]), len(cea["points"]))
        self.assertGreater(hb["points"][-1]["date"], cea["points"][-1]["date"])
        self.assertLess(c.index("CEA"), c.index("Hb"))
        self.assertEqual(c[:2], ["CEA", "CA19-9"])
        self.assertEqual(len(chart.trend_candidates(self.pd)), 4)

    def test_tumor_marker_detected_by_bucket(self):
        labs = self._labs()
        for p in labs["panels"]:
            if p["normalized_analyte"] == "CEA":
                p["analyte"] = p["normalized_analyte"] = "XMARK"   # unknown name, tumor-marker bucket
        self._write_labs(labs)
        self.assertTrue(chart.series_for(self.pd, "XMARK")["is_tumor_marker"])
        self.assertEqual(chart.trend_candidates(self.pd)[:2], ["CA19-9", "XMARK"])

    # --- svg ---------------------------------------------------------------------------------
    def test_svg_rules(self):
        for m in ("CEA", "CA19-9", "NEUT#", "Hb", "体重"):
            svg = chart.svg_trend(chart.series_for(self.pd, m))
            sizes = [float(x) for x in re.findall(r'font-size="([\d.]+)"', svg)]
            self.assertTrue(sizes and min(sizes) >= 12, m)
            self.assertNotIn("marker-end", svg)
            for arrow in ("→", "↗", "↘", "⬆", "⬇"):
                self.assertNotIn(arrow, svg)
            self.assertNotIn("green", svg.lower())
            if m == "NEUT#":
                self.assertIn(chart.CRITICAL, svg)            # the report flagged 危急值
            else:
                self.assertNotIn(chart.CRITICAL, svg)
        self.assertIn(chart.BAND, chart.svg_trend(chart.series_for(self.pd, "CEA")))

    def test_real_time_spacing(self):
        s = chart.series_for(self.pd, "CEA")        # 05-28, 07-03 (36 d), 08-22 (50 d)
        xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)"', chart.svg_trend(s))]
        self.assertAlmostEqual((xs[1] - xs[0]) / (xs[2] - xs[1]), 36 / 50, places=2)

    # --- verdicts and the page ------------------------------------------------------------
    def test_verdict_words(self):
        self.assertEqual(chart.verdict_words("CEA 各次报告的数值"), [])
        self.assertIn("好转", chart.verdict_words("CEA 明显好转"))
        self.assertTrue(chart.verdict_words("Tumor is IMPROVING"))
        self.assertTrue(chart.verdict_words("partial response"))
        self.assertTrue(chart.verdict_words("病情稳定了"))
        s = chart.series_for(self.pd, "CEA")
        self.assertEqual(chart.verdict_words(chart.default_title(s)), [])
        self.assertEqual(chart.verdict_words(chart.default_title(s, "en")), [])

    def test_page_refuses_verdict_title(self):
        with self.assertRaises(ValueError) as cm:
            chart.render_chart_page(self.pd, "CEA", title="CEA 持续升高，提示疾病进展")
        self.assertIn("进展", str(cm.exception))
        self.assertFalse((self.pd / "charts").exists())

    def test_page_refuses_single_point(self):
        labs = {"panels": [{"analyte": "CEA", "normalized_analyte": "CEA", "values": [
            {"date": "2026-01-01", "value": 5.1, "raw_value": "5.1", "unit": "ng/mL", "source_refs": []}]}]}
        self._write_labs(labs)
        with self.assertRaises(ValueError) as cm:
            chart.render_chart_page(self.pd, "CEA")
        self.assertIn("目前只有 1 次记录，再测一次就能看到变化", str(cm.exception))
        with self.assertRaises(ValueError):
            chart.render_chart_page(self.pd, "PSA")

    def test_page_content(self):
        out = chart.render_chart_page(self.pd, "CEA")
        self.assertEqual(out, self.pd / "charts" / "CEA_趋势.html")
        page = out.read_text(encoding="utf-8")
        self.assertIn("<svg", page)
        self.assertNotIn("<script", page)
        self.assertNotIn("<link", page)
        for d in ("2025-06-08", "2026-05-28", "2026-07-03", "2026-08-22"):   # every point in the table
            self.assertIn(d, page)
        self.assertIn("单位不同", page)
        self.assertIn("肿瘤标志物 2026-08-22", page)                         # source doc + date
        self.assertIn("可以问医生的问题", page)
        page2 = chart.render_chart_page(self.pd, "CA19-9").read_text(encoding="utf-8")
        self.assertIn("检测方法", page2)
        self.assertIn("不画参考范围带", page2)

    def test_custom_neutral_title(self):
        page = chart.render_chart_page(self.pd, "CEA", title="CEA 每次化验的数值").read_text(encoding="utf-8")
        self.assertIn("CEA 每次化验的数值", page)

    # --- treatment swimlane ---------------------------------------------------------------
    def test_treatment_timeline(self):
        eps = json.loads((self.pd / "treatment_lines.json").read_text(encoding="utf-8"))["episodes"]
        svg = chart.svg_treatment_timeline(eps, "2023-01-01", "2026-09-30")
        self.assertEqual(svg.count("<rect"), 3)
        self.assertIn("今日第 14 程", svg)
        self.assertIn("url(#cb-open)", svg)              # ongoing drawn open-ended
        self.assertEqual(svg.count("url(#cb-open)"), 1)
        self.assertNotIn("marker-end", svg)
        # tolerant of missing dates / empty input
        self.assertIn("<svg", chart.svg_treatment_timeline([{"regimen": "X"}], None, None))
        self.assertIn("<svg", chart.svg_treatment_timeline([], None, None))


if __name__ == "__main__":
    unittest.main()
