"""organize pipeline: prepare -> next -> place -> (synthesis) -> finish -> review, all from disk state."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "cancer-buddy" / "scripts"))

from cblib import organize, prepare as prep, check as chk, export as exp  # noqa: E402
from cblib.common import load_json, write_json, iter_sidecars, rel  # noqa: E402

P = "04_诊断与分期/病理报告/2026-03-15_病理报告_示例医院.md"
C = "05_影像/CT/2026-03-20_CT报告_示例医院.md"
L = "07_检验/血常规/2026-03-21_血常规_示例医院.md"


def transcript(d, name, sid, pages, kind, date, bucket, body):
    (d / ".work" / "transcripts" / name).write_text(
        f"---\nsource_id: {sid}\npages: {pages}\ndoc_kind: {kind}\ndoc_date: {date}\n"
        f"institution: 示例医院\nbucket: {bucket}\nread: vision\n---\n{body}\n", encoding="utf-8")


def fake_synthesis(d, errors_left=True, fix_round=0):
    """Stand-in for the synthesis worker: writes the minimum archive, optionally with mistakes."""
    w = lambda n, o: write_json(d / n, o)  # noqa: E731
    w("profile.json", {"schema": "cancer_buddy_profile_v3", "patient_code": d.name, "locale": "zh",
                       "summary": {"one_line_condition": "腺癌", "stage": "{?pT3|pT2}N1M0"},
                       "latest_status": {"regimen": None}, "source_refs": [P + "#L10"]})
    w("patient_summary.json", {"diagnosis": {"primary": "腺癌", "stage": "{?pT3|pT2}N1M0", "source_refs": [P + "#L10"]}})
    findings = [{"finding_id": "AF-001", "label": "肺栓塞", "verbatim_text": "考虑肺栓塞",
                 "source_ref": C + "#L9", "acuity": "urgent"}]
    if errors_left:
        findings.append({"finding_id": "AF-002", "label": "积液", "verbatim_text": "大量胸腔积液",
                         "source_ref": C + "#L9", "acuity": "urgent"})
    w("acute_findings.json", {"findings": findings})
    w("labs.json", {"panels": [{"analyte": "CEA", "values": [
        {"date": "2026-03-21", "raw_value": "6.1", "source_refs": [L + "#L9"]}]}]})
    for n, k in [("molecular.json", "variants"), ("treatment_lines.json", "episodes"), ("timeline.json", "events"),
                 ("comorbidities.json", "medications"), ("readiness.json", "review_flags"),
                 ("missing_items.json", "document_gaps")]:
        w(n, {k: []})
    (d / "case_text.md").write_text(f"诊断腺癌 [[src:{P}#L10]]\n", encoding="utf-8")
    (d / "timeline.md").write_text("时间线\n", encoding="utf-8")
    (d / "review_summary.md").write_text("抽检\n", encoding="utf-8")
    w(".work/synth_done.json", {"at": f"t{fix_round}", "inputs_digest": organize.inputs_digest(d), "fix_round": fix_round})


class OrganizeFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["CANCER_BUDDY_PATIENTS_DIR"] = str(self.tmp / "patients")
        inp = self.tmp / "in"
        (inp / "sub").mkdir(parents=True)
        (inp / "sub" / "note.txt").write_text("家属记录", encoding="utf-8")
        (inp / "sub" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        (inp / "lab.txt").write_text("CEA 6.1", encoding="utf-8")
        (inp / "empty.txt").write_text("", encoding="utf-8")
        (inp / ".DS_Store").write_text("x")
        with zipfile.ZipFile(inp / "bundle.zip", "w") as z:
            z.writestr("dup/lab.txt", "CEA 6.1")            # duplicate by content
            z.writestr("__MACOSX/._junk", "x")
            z.writestr("new/ct.txt", "CT 报告")
        self.inp = inp

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _prepare(self):
        r = prep.prepare([str(self.inp)])
        return Path(r["patient_dir"]), r

    def test_prepare_dedupes_and_skips_junk(self):
        d, r = self._prepare()
        self.assertRegex(d.name, r"^PT-[0-9A-F]{10}$")
        self.assertEqual(len(r["added"]), 4)                  # lab, ct, note, photo
        reasons = {s["reason"].split(":")[0] for s in r["skipped"]}
        self.assertIn("duplicate_of", reasons)
        self.assertIn("empty_file", reasons)
        self.assertTrue(all((d / f["raw_path"]).exists() for f in load_json(d / "source_inventory.json")["files"]))
        again = prep.prepare([str(self.inp)], patient_dir=d)  # idempotent
        self.assertEqual(again["added"], [])

    def test_uploaded_filenames_never_reach_derived_files(self):
        (self.inp / "爸爸王某某_病理.txt").write_text("CEA 6.1", encoding="utf-8")   # duplicate content, named
        d, r = self._prepare()
        organize._write_index(d)
        for name in ("source_inventory.json", "INDEX.md"):
            self.assertNotIn("王某某", (d / name).read_text(encoding="utf-8"))
        self.assertIn("王某某", (d / "raw" / "_FILENAME_MAPPING.md").read_text(encoding="utf-8"))
        self.assertTrue(all(s["input_ref"].startswith("raw/_FILENAME_MAPPING.md#skip-") for s in r["skipped"]))

    def test_duplicate_staged_transcripts_are_parked(self):
        d, _ = self._prepare()
        sid = load_json(d / "source_inventory.json")["files"][0]["source_id"]
        transcript(d, f"{sid}_a.md", sid, "1", "血常规", "2026-03-21", "07_检验/血常规", "CEA 6.1")
        transcript(d, f"{sid}_b.md", sid, "1", "血常规", "2026-03-21", "07_检验/血常规", "CEA 6.1")
        out = organize.place(d)
        self.assertEqual(len(out["placed"]), 1)
        self.assertEqual(len(list((d / ".work" / "duplicates").glob("*.md"))), 1)

    def test_resume_only_redispatches_missing_pages(self):
        d, _ = self._prepare()
        first = organize.next_step(d)
        self.assertEqual(first["stage"], "transcribe")
        inv = load_json(d / "source_inventory.json")["files"]
        done = inv[0]["source_id"]
        transcript(d, f"{done}_p1.md", done, "1", "血常规", "2026-03-21", "07_检验/血常规", "CEA 6.1")
        again = organize.next_step(d)
        prompt = "".join(Path(t["prompt_file"]).read_text(encoding="utf-8") for t in again["tasks"])
        self.assertNotIn(f"### {done}（", prompt)
        for f in inv[1:]:
            self.assertIn(f"### {f['source_id']}（", prompt)

    def test_task_packing_limits_images(self):
        d, _ = self._prepare()
        pages = d / ".work" / "pages" / "s099"
        pages.mkdir(parents=True)
        for i in range(1, 31):
            (pages / f"p{i:03d}.png").write_bytes(b"x")
        inv = load_json(d / "source_inventory.json")
        inv["files"].append({"source_id": "s099", "contract": "v2", "kind": "pdf", "page_count": 30,
                             "raw_path": "raw/s099.pdf", "sha256": "z", "sidecar_paths": []})
        write_json(d / "source_inventory.json", inv)
        tasks = organize.next_step(d)["tasks"]
        self.assertTrue(all(t["images"] <= organize.MAX_IMAGES_PER_TASK for t in tasks))
        self.assertEqual(sum(t["pages"] for t in tasks), 30 + 4)

    def test_open_world_placement(self):
        self.assertEqual(organize.resolve_bucket("血常规", "血常规", "zh"), "07_检验/血常规")
        self.assertEqual(organize.resolve_bucket("", "novel:肠道菌群检测", "zh"), "15_其他资料/肠道菌群检测")
        self.assertEqual(organize.resolve_bucket("05_imaging/CT", "CT", "zh"), "05_影像/CT")
        self.assertEqual(organize.resolve_bucket("06_分子与组学/新公司面板", "NGS", "zh"), "06_分子与组学/新公司面板")

    def _full_run(self, errors_left=True):
        d, _ = self._prepare()
        T = d / ".work" / "transcripts"
        ids = [f["source_id"] for f in load_json(d / "source_inventory.json")["files"]]
        transcript(d, f"{ids[0]}.md", ids[0], "1", "病理报告", "2026-03-15", "04_诊断与分期/病理报告",
                   "患者：张某某示例\n诊断：腺癌，分期 {?pT3|pT2}N1M0")
        transcript(d, f"{ids[1]}.md", ids[1], "1", "CT报告", "2026-03-20", "05_影像/CT",
                   "右肺下叶考虑肺栓塞。电话 13812345678")
        transcript(d, f"{ids[2]}.md", ids[2], "1", "血常规", "2026-03-21", "07_检验/血常规", "CEA 6.1")
        transcript(d, f"{ids[3]}.md", ids[3], "1", "风景照", "", "99_无关文件", "一张风景照")
        (d / "raw" / "_identity").mkdir(parents=True, exist_ok=True)
        write_json(d / "raw" / "_identity" / "t.json", {"names": ["张某某示例"], "phones": ["13812345678"]})
        self.assertEqual(organize.next_step(d)["stage"], "place")
        organize.place(d)
        self.assertFalse(list(T.glob("*.md")))
        self.assertEqual(organize.next_step(d)["stage"], "synthesize")
        fake_synthesis(d, errors_left=errors_left)
        self.assertEqual(organize.next_step(d)["stage"], "finish")
        return d, organize.finish(d)

    def test_finish_masks_identity_and_reports_real_problems(self):
        d, res = self._full_run(errors_left=True)
        self.assertGreaterEqual(res["masked"], 2)
        for p in iter_sidecars(d):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("张某某示例", text)
            self.assertNotIn("13812345678", text)
        self.assertTrue(any("大量胸腔积液" in e for e in res["errors"]))
        self.assertFalse(any("考虑肺栓塞" in e for e in res["errors"]))
        self.assertEqual((d / "INDEX.md").read_text(encoding="utf-8").splitlines()[0], f"# patient_code: {d.name}")
        self.assertTrue((d / "AGENTS.md").exists())
        r = load_json(d / "readiness.json")
        self.assertEqual(r["latest_source_date"], "2026-03-21")

    def test_fix_loop_is_bounded(self):
        d, _ = self._full_run(errors_left=True)
        nxt = organize.next_step(d)
        self.assertEqual(nxt["stage"], "synthesize")
        self.assertIn("大量胸腔积液", Path(nxt["tasks"][0]["prompt_file"]).read_text(encoding="utf-8"))
        fake_synthesis(d, errors_left=True, fix_round=1)       # the fix did not help
        self.assertEqual(organize.next_step(d)["stage"], "finish")
        organize.finish(d)
        final = organize.next_step(d)
        self.assertEqual(final["stage"], "review")
        self.assertTrue(final["show"]["unresolved_check_errors"])
        self.assertEqual(final["show"]["acute_findings"][0]["label"], "肺栓塞")
        self.assertEqual(len(final["show"]["unrelated_pending"]), 1)

    def test_clean_run_reaches_review_and_finish_is_idempotent(self):
        d, res = self._full_run(errors_left=False)
        html_errors = [e for e in res["errors"] if "渲染失败" not in e]
        self.assertEqual(html_errors, [])
        organize.finish(d)
        n = len(load_json(d / "update_log.json")["entries"])
        organize.finish(d)
        self.assertEqual(len(load_json(d / "update_log.json")["entries"]), n)

    def test_pages_cleared_at_finish_and_rebuilt_when_needed(self):
        d, _ = self._full_run(errors_left=False)
        self.assertFalse((d / ".work" / "pages").exists())
        lab = [rel(d, p) for p in iter_sidecars(d) if "血常规" in p.name][0]
        (d / lab).unlink()                                   # a transcript went missing
        nxt = organize.next_step(d)
        self.assertEqual(nxt["stage"], "transcribe")
        prompt = Path(nxt["tasks"][0]["prompt_file"]).read_text(encoding="utf-8")
        self.assertNotIn("无图，无文本层", prompt)
        self.assertTrue(list((d / ".work" / "pages").rglob("p001.*")))

    def test_lab_value_may_sit_on_any_cited_line(self):
        d, _ = self._full_run(errors_left=False)
        labs = load_json(d / "labs.json")
        labs["panels"][0]["values"][0]["source_refs"] = [P + "#L9", L + "#L9"]   # date line first, value line second
        write_json(d / "labs.json", labs)
        self.assertFalse([e for e in chk.check(d)["errors"] if "labs.json" in e])

    def test_incremental_only_transcribes_new_source(self):
        d, _ = self._full_run(errors_left=False)
        new = self.tmp / "new.txt"
        new.write_text("CEA 7.0", encoding="utf-8")
        r = prep.prepare([str(new)], patient_dir=d)
        self.assertEqual(r["run_mode"], "incremental")
        nxt = organize.next_step(d)
        self.assertEqual(nxt["stage"], "transcribe")
        self.assertEqual(sum(t["pages"] for t in nxt["tasks"]), 1)

    def test_incremental_synthesis_names_the_new_sidecars(self):
        d, _ = self._full_run(errors_left=False)
        first = Path(d / ".work" / "tasks" / "synthesize.md").read_text(encoding="utf-8")
        self.assertIn("完整汇总", first)
        new = self.tmp / "new.txt"
        new.write_text("CEA 7.0", encoding="utf-8")
        prep.prepare([str(new)], patient_dir=d)
        sid = load_json(d / "source_inventory.json")["files"][-1]["source_id"]
        transcript(d, f"{sid}.md", sid, "1", "肿瘤标志物", "2026-05-10", "07_检验/肿瘤标志物", "CEA 7.0")
        organize.place(d)
        task = Path(organize.next_step(d)["tasks"][0]["prompt_file"]).read_text(encoding="utf-8")
        self.assertIn("增量更新", task)
        self.assertIn("2026-05-10_肿瘤标志物", task)

    def test_conversation_note_triggers_resynthesis(self):
        d, _ = self._full_run(errors_left=False)
        self.assertEqual(organize.next_step(d)["stage"], "review")
        out = organize.add_note(d, "上周开始吃奥美拉唑", "patient_reported", "08")
        self.assertTrue(out["note"].startswith("08_治疗/conversation_notes/"))
        self.assertEqual(organize.next_step(d)["stage"], "synthesize")

    def test_discard_needs_confirmation_and_keeps_raw(self):
        d, _ = self._full_run(errors_left=False)
        junk = [rel(d, p) for p in iter_sidecars(d) if rel(d, p).startswith("99_")][0]
        with self.assertRaises(SystemExit):
            organize.discard(d, junk, "")
        with self.assertRaises(SystemExit):
            organize.discard(d, P, "删吧")
        organize.discard(d, junk, "风景照删掉吧")
        self.assertFalse((d / junk).exists())
        self.assertEqual(len([p for p in (d / "raw").glob("s*")]), 4)

    def test_v1_archive_upgrade(self):
        d = Path(os.environ["CANCER_BUDDY_PATIENTS_DIR"]) / "PT-AAAAAAAAAA"
        (d / "raw" / "原件").mkdir(parents=True)
        (d / "raw" / "原件" / "p1.jpg").write_bytes(b"\xff\xd8old")
        (d / "raw" / "_extract").mkdir()
        (d / "raw" / "_extract" / "x.txt").write_text("infra")
        (d / "04_诊断与分期" / "病理报告").mkdir(parents=True)
        (d / "04_诊断与分期" / "病理报告" / "old.md").write_text("v1 sidecar")
        write_json(d / "profile.json", {"patient_code": d.name, "locale": "zh"})
        write_json(d / "source_inventory.json", {"files": [{"file_id": "f1", "sha256": "abc"}]})
        r = prep.prepare([], patient_dir=d)
        self.assertEqual(r["run_mode"], "v1_upgrade")
        self.assertEqual([a["source_id"] for a in r["added"]], ["s001"])
        self.assertFalse((d / "04_诊断与分期").exists())
        self.assertTrue(list((d / "raw").glob("_legacy_*/04_诊断与分期/病理报告/old.md")))
        self.assertTrue((d / "raw" / "原件" / "p1.jpg").exists())


class ExportGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.d = self.tmp / "PT-BBBBBBBBBB"
        (self.d / "raw" / "_identity").mkdir(parents=True)
        write_json(self.d / "raw" / "_identity" / "t.json", {"names": ["李某某示例"]})
        write_json(self.d / "profile.json", {"patient_code": self.d.name, "summary": {"one_line_condition": "李某某示例 腺癌"}})

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_refuses_raw_and_past_expiry(self):
        with self.assertRaises(SystemExit):
            exp.export(self.d, self.tmp / "o", ["raw/_identity/t.json"], "王医生", "会诊", "2099-01-01")
        with self.assertRaises(SystemExit):
            exp.export(self.d, self.tmp / "o", ["profile.json"], "王医生", "会诊", "2000-01-01")

    def test_export_masks_and_writes_manifest(self):
        out = exp.export(self.d, self.tmp / "o", ["profile.json"], "王医生", "会诊", "2099-01-01")
        text = (self.tmp / "o" / "profile.json").read_text(encoding="utf-8")
        self.assertNotIn("李某某示例", text)
        self.assertFalse((self.tmp / "o" / "raw").exists())
        m = load_json(self.tmp / "o" / "_SHARE_MANIFEST.json")
        self.assertEqual(m["recipient"], "王医生")
        self.assertEqual(out["files"], ["profile.json"])


if __name__ == "__main__":
    unittest.main()
