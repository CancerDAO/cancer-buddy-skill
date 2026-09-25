#!/usr/bin/env bash
# ORG-P0-02 — the deterministic second read of a pixel-page sidecar (scripts/second_read_align.py,
# scripts/_high_risk_spans.py, scripts/run_ocr_engine.py parse-tsv / which).
#   tri-state per high-risk span: agree (no token) / no_signal (no token, no flag) / conflict (token +
#   entry); the table, tokens and readings are the script's; --check recomputes them.
# Engine outputs are synthetic run_ocr_engine.py documents (no OCR engine needed: runs on ubuntu CI).
# Every negative case mutates ONE thing of a clean --apply result; the clean result is the positive control.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import json, os, re, subprocess, sys
from pathlib import Path

REPO, TMP = Path(sys.argv[1]), Path(sys.argv[2])
S = REPO / "skills" / "cancer-buddy-organize" / "scripts"
sys.path.insert(0, str(S))
import _high_risk_spans as hrs
import second_read_align as sra

passed = failed = 0
n = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


HEADER = """SOURCE: order_sheet
FILE_ID: s001
EXTRACTOR: p1-s001-1
PRIMARY_CHANNEL: llm_vision
SECOND_READ_CHANNEL: none
INDEPENDENT_REREAD: false
READ_MODE: model_vision_primary
ADAPTER: temp_raster
CONFIDENCE: medium
SHA256: """ + "ab" * 32 + """
PAGE_LABEL: null
MODALITY: image
"""
BODY = ["# 版面重建", "", "示例医院 临时医嘱单（合成夹具）", "开立日期：2030-01-08",
        "卡铂 300 mg 静滴 第1程", "分期：cT3N2M0"]


def eng(lines, engine="apple_vision"):
    return {"tool": "run_ocr_engine", "version": "1", "engine": engine, "channel": f"deterministic_ocr:{engine}",
            "engine_version": "synthetic", "os_version": None, "languages": ["zh-Hans", "en-US"],
            "confidence_scale": "0-1", "no_signal_below": 0.5,
            "pages": [{"page": 1, "image": None, "image_sha256": None, "width": None, "height": None,
                       "lines": [{"text": t, "confidence": c, "bbox": [0, i, 1, 1]} for i, (t, c) in enumerate(lines)]}]}


GOOD = [("示例医院 临时医嘱单（合成夹具）", 0.9), ("开立日期：2030-01-08", 0.95), ("卡铂 300 mg 静滴 第1程", 0.9),
        ("分期：cT3N2M0", 0.9)]


def make(body=BODY, engine_lines=GOOD, declared=None, deny=None, engine="apple_vision", apply=True):
    """A patient dir with one Phase-1 sidecar; --apply with a synthetic engine output → (pd, sidecar, rc, out)."""
    global n
    n += 1
    pd = TMP / f"pd{n}"
    (pd / "ocr").mkdir(parents=True)
    (pd / "raw" / "_extract").mkdir(parents=True)
    sc = pd / "ocr" / "s001.md"
    sc.write_text(HEADER + "\n" + "\n".join(body) + "\n\n## PII\n\nmasked: none\n", encoding="utf-8")
    if declared is not None:
        (pd / "raw" / "_extract" / "s001.declared.json").write_text(json.dumps({"spans": declared}, ensure_ascii=False),
                                                                    encoding="utf-8")
    if deny:
        (pd / "raw" / "_identity_denylist").mkdir(parents=True)
        (pd / "raw" / "_identity_denylist" / "p1-s001-1.json").write_text(json.dumps({"tokens": deny}), encoding="utf-8")
    if not apply:
        return pd, sc, None, None
    ej = TMP / f"eng{n}.json"
    ej.write_text(json.dumps(eng(engine_lines, engine), ensure_ascii=False), encoding="utf-8")
    rc, out = run_apply(pd, sc, ej)
    return pd, sc, rc, out


def run_apply(pd, sc, ej=None, engine=None):
    args = [sys.executable, str(S / "second_read_align.py"), "--apply", str(sc), "--patient-dir", str(pd)]
    args += ["--engine-json", str(ej)] if ej else ["--engine", engine or "none"]
    p = subprocess.run(args, capture_output=True, text=True)
    out = p.stdout if p.returncode == 0 else p.stderr
    try:
        return p.returncode, json.loads(out.strip().splitlines()[-1])
    except Exception:
        return p.returncode, {"raw": out}


def chk(pd, sc):
    return sra.check(sc, pd)


def hdr(sc):
    return sra.header_dict(sra.split_sidecar(sc.read_text(encoding="utf-8"))["header"])


def rows(sc):
    return sra.parse_section(sra.section_block(sra.split_sidecar(sc.read_text(encoding="utf-8"))["sections"],
                                               "高风险字段复读"))["rows"]


# ---- positive control: every span agrees
pd, sc, rc, out = make()
check("clean: --apply exit 0", rc == 0, str(out))
summ = out.get("second_read_summary", {})
check("clean: spans derived by the script (date, drug, dose, cycle, TNM)", summ.get("spans_total") == 5, str(summ))
check("clean: all agree, no token", summ.get("agree") == 5 and not out.get("tokens"), str(out))
h = hdr(sc)
check("clean: header SECOND_READ_CHANNEL = the engine", h["SECOND_READ_CHANNEL"] == "deterministic_ocr:apple_vision", str(h))
check("clean: INDEPENDENT_REREAD true (an engine read ≥ 1 span)", h["INDEPENDENT_REREAD"] == "true", str(h))
check("clean: CONFIDENCE high (independent, no token, no no-signal row)", h["CONFIDENCE"] == "high", str(h))
check("clean: high_risk_review_status passed_independent_reread",
      out.get("high_risk_review_status") == "passed_independent_reread", str(out))
text = sc.read_text(encoding="utf-8")
check("clean: section order 复读 → PII", text.index("## 高风险字段复读") < text.index("## PII"))
check("clean: body_sha256 line + engine line written", re.search(r"^body_sha256: [0-9a-f]{64}$", text, re.M)
      and "engine: deterministic_ocr:apple_vision" in text)
errs, warns = chk(pd, sc)
check("clean: --check passes", errs == [], str(errs))
clean_text = text

# ---- no signal: empty read, garbage, low confidence, ungrammatical TNM → no token, no entry
for label, lines in [
    ("engine read nothing on the date line", [GOOD[0], ("", 0.9), GOOD[2], GOOD[3]]),
    ("engine read garbage", [GOOD[0], ("WH,ano", 0.9), GOOD[2], GOOD[3]]),
    ("engine confidence under 0.5", [GOOD[0], ("开立日期：2030-01-03", 0.3), GOOD[2], GOOD[3]]),
    ("TNM not grammatical (CT3M2M0)", [GOOD[0], GOOD[1], GOOD[2], ("分期：CT3M2M0", 0.9)]),
]:
    pd, sc, rc, out = make(engine_lines=lines)
    t = sc.read_text(encoding="utf-8")
    check(f"no signal — {label}: no token, no `## 不确定字段`", rc == 0 and "[OCR_UNCERTAIN" not in t
          and "## 不确定字段" not in t and out["second_read_summary"]["no_signal"] >= 1, str(out))
    check(f"no signal — {label}: --check passes", chk(pd, sc)[0] == [], str(chk(pd, sc)[0]))
    check(f"no signal — {label}: CONFIDENCE medium", hdr(sc)["CONFIDENCE"] == "medium", str(hdr(sc)))

# ---- conflict: a confident, grammatical, different reading → token + entry
pd, sc, rc, out = make(engine_lines=[GOOD[0], ("开立日期：2030-01-03", 0.95), GOOD[2], GOOD[3]])
t = sc.read_text(encoding="utf-8")
check("conflict — date: token right after the transcription's literal",
      "开立日期：2030-01-08[OCR_UNCERTAIN:U-001]" in t, t[:900])
check("conflict — date: entry with the engine's own string + confidence",
      '{channel: "deterministic_ocr:apple_vision", text: "2030-01-03", confidence: 0.95}' in t, t)
check("conflict — date: entry field_class date, line = token line",
      re.search(r"- id: U-001\n  line: 17\n  field_class: date", t) is not None, t)
check("conflict — CONFIDENCE low", hdr(sc)["CONFIDENCE"] == "low")
check("conflict — --check passes", chk(pd, sc)[0] == [], str(chk(pd, sc)[0]))
conflict_pd, conflict_sc = pd, sc
pd, sc, rc, out = make(body=BODY[:4] + ["顺铂 300 mg 静滴 第1程", BODY[5]],
                       engine_lines=[GOOD[0], GOOD[1], ("卡铂 300 mg 静滴 第1程", 0.9), GOOD[3]])
t = sc.read_text(encoding="utf-8")
check("conflict — another lexicon drug (顺铂/卡铂) → token with lexicon candidates",
      "顺铂[OCR_UNCERTAIN:U-001]" in t and "lexicon: oncology_drugs" in t, t)
pd, sc, rc, out = make(body=BODY + ["| 血红蛋白 | 11.5 | g/L |"], engine_lines=GOOD + [("| 血红蛋白 | 115 | g/L |", 0.9)])
check("conflict — a lost decimal point (11.5/115)", "11.5[OCR_UNCERTAIN:U-001]" in sc.read_text(encoding="utf-8"),
      sc.read_text(encoding="utf-8"))

# ---- agree through normalisation
for label, body_line, engine_line in [
    ("superscript unit 10°9", "| 白细胞 | 3.2 | ×10⁹/L |", "| 白细胞 | 3.2 | 10°9/L |"),
    ("superscript unit x109", "| 白细胞 | 3.2 | ×10^9/L |", "| 白细胞 | 3.2 | x109/L |"),
    ("date 2026-07.06", "复查日期：2026-07-06", "复查日期：2026-07.06"),
    ("date 2026-0707", "复查日期：2026-07-07", "复查日期：2026-0707"),
]:
    pd, sc, rc, out = make(body=BODY + [body_line], engine_lines=GOOD + [(engine_line, 0.9)])
    check(f"agree — {label}: no token", rc == 0 and "[OCR_UNCERTAIN" not in sc.read_text(encoding="utf-8")
          and out["second_read_summary"]["conflict"] == 0, str(out))

# ---- lexicon near-miss → no signal, no token
for label, body_line, engine_line in [("斯鲁利单抗/斯重利单抗", "斯鲁利单抗 200 mg", "斯重利单抗 200 mg"),
                                      ("INSM1/INSMI", "免疫组化：INSM1(+)", "免疫组化：INSMI(+)")]:
    pd, sc, rc, out = make(body=BODY + [body_line], engine_lines=GOOD + [(engine_line, 0.9)])
    check(f"lexicon near-miss {label}: no token", "[OCR_UNCERTAIN" not in sc.read_text(encoding="utf-8")
          and out["second_read_summary"]["no_signal"] >= 1, str(out))

# ---- pure comparisons the gate shares
lex = hrs.load_lexicons()
for fc, a, b, want in [("other", "Diﬀ", "Diff", "agree"), ("other", "CO2", "co2", "agree"), ("other", "İ", "I", "agree"),
                       ("stage", "III期", "111期", "no_signal"), ("drug_name", "白蛋白结合型紫杉醇", "白蛋白结合紫杉醇", "no_signal"),
                       ("number", "300 mg", "300 g", "no_signal"), ("number", "300 mg", "300", "no_signal")]:
    got = hrs.classify(fc, a, b, 0.9, "apple_vision", lex)[0]
    check(f"classify {fc} {a!r}/{b!r} → {want}", got == want, got)
check("tesseract confidence scale (49 < 50) → no signal",
      hrs.classify("date", "2030-01-08", "2030-01-03", 49, "tesseract", lex)[0] == "no_signal")
check("tesseract confidence 80 → conflict", hrs.classify("date", "2030-01-08", "2030-01-03", 80, "tesseract", lex)[0] == "conflict")

spans = hrs.derive_spans(["病理分期：pT2N0（示例）", "临床分期：cT3N2M0"], 1, lex)
check("TNM with and without the M component are stage spans (pT2N0 / cT3N2M0)",
      [s["text"] for s in spans if s["field_class"] == "stage"] == ["pT2N0", "cT3N2M0"], str(spans))

# ---- chart ticks are not spans; a result on its own line is
spans = hrs.derive_spans(["CA 19-9", "2,401", "U/mL", "Normal range: 0 - 35", "0", "35"], 1, lex)
check("chart tick lines (0 / 35 under a Normal range line) are not spans",
      [s["text"] for s in spans] == ["2,401", "0 - 35"], str([s["text"] for s in spans]))

# ---- no engine on the host → every span 无信号, not independent
pd, sc, rc, out = make(apply=False)
rc, out = run_apply(pd, sc, engine="none")
h = hdr(sc)
check("no engine: exit 0, all rows 无信号", rc == 0 and all(r["state"] == "无信号" for r in rows(sc)) and rows(sc), str(out))
check("no engine: SECOND none / INDEPENDENT false / CONFIDENCE medium",
      (h["SECOND_READ_CHANNEL"], h["INDEPENDENT_REREAD"], h["CONFIDENCE"]) == ("none", "false", "medium"), str(h))
check("no engine: --check passes", chk(pd, sc)[0] == [], str(chk(pd, sc)[0]))

# ---- engine readings are masked
pd, sc, rc, out = make(engine_lines=[GOOD[0], ("开立日期：2030-01-08 张测试", 0.95), GOOD[2], GOOD[3]], deny=["张测试"])
check("engine readings pass the identity word list", "张测试" not in sc.read_text(encoding="utf-8"))

# ---- declared spans: only add
pd, sc, rc, out = make(body=BODY + ["诊断：示例肿瘤"], engine_lines=GOOD + [("诊断：示例肿瘤", 0.9)],
                       declared=[{"line": 20, "text": "示例肿瘤", "field_class": "diagnosis_text"}])
check("declared diagnosis becomes a table row", any(r["field_class"] == "diagnosis_text" for r in rows(sc)), str(rows(sc)))
pd, sc, rc, out = make(declared=[{"line": 17, "text": "不存在的字", "field_class": "other"}])
check("declared text not on its line → exit 2", rc == 2, str(out))
pd, sc, rc, out = make(body=BODY + ["医师签名：[不可读]"], engine_lines=GOOD + [("医师签名：", 0.9)],
                       declared=[{"line": 20, "text": "[不可读]", "field_class": "other", "kind": "unreadable"}])
t = sc.read_text(encoding="utf-8")
check("declared unreadable → token + entry with a null model reading",
      "[不可读][OCR_UNCERTAIN:U-001]" in t and "{channel: llm_vision, text: null, confidence: null}" in t, t)

# ---- --check negatives (each mutates ONE thing of the conflict result / the clean result)
def mutate(src_pd, src_sc, fn):
    global n
    n += 1
    import shutil
    dst = TMP / f"m{n}"
    shutil.copytree(src_pd, dst)
    sc2 = dst / "ocr" / "s001.md"
    sc2.write_text(fn(sc2.read_text(encoding="utf-8")), encoding="utf-8")
    return chk(dst, sc2)[0], dst, sc2


errs, _, _ = mutate(conflict_pd, conflict_sc, lambda t: re.sub(r"^\| number \| 18 .*\n", "", t, count=1, flags=re.M))
check("--check: a derived span missing from the table → ERROR", any("not the recomputed second read" in e for e in errs), str(errs))
errs, _, _ = mutate(conflict_pd, conflict_sc, lambda t: t.replace("卡铂 300 mg", "卡铂[OCR_UNCERTAIN:U-002] 300 mg", 1))
check("--check: a token on an agree span → ERROR", any("sits on no conflict" in e for e in errs), str(errs))
errs, _, _ = mutate(conflict_pd, conflict_sc, lambda t: t.replace("| 2030-01-08 | 2030-01-03 | 否 |", "| 2030-01-08 | 2030-01-08 | 否 |", 1))
check("--check: table reading ≠ the engine's string → ERROR", any("is not the engine's own string" in e for e in errs), str(errs))
errs, _, _ = mutate(conflict_pd, conflict_sc, lambda t: t.replace('text: "2030-01-03", confidence: 0.95', 'text: "2030-01-08", confidence: 0.95', 1))
check("--check: `## 不确定字段` reading ≠ the engine's string → ERROR", any("engine reading is not the engine's own string" in e for e in errs), str(errs))
errs, _, _ = mutate(conflict_pd, conflict_sc, lambda t: t.replace("静滴 第1程", "静滴 第2程", 1))
check("--check: body edited after the second read → body_sha256 ERROR", any("body_sha256" in e for e in errs), str(errs))
errs, _, _ = mutate(conflict_pd, conflict_sc, lambda t: t.replace("[OCR_UNCERTAIN:U-001]", "", 1)
                    .replace("| 2030-01-08 | 2030-01-03 | 否 |", "| 2030-01-08 | 2030-01-03 | 是 |", 1))
check("--check: a conflict re-labelled 是 without its token → ERROR", any("not the recomputed second read" in e for e in errs), str(errs))
errs, _, _ = mutate(pd, sc, lambda t: t.replace("INDEPENDENT_REREAD: true", "INDEPENDENT_REREAD: false", 1))
check("--check: INDEPENDENT_REREAD not mechanical → ERROR", any("INDEPENDENT_REREAD" in e for e in errs), str(errs))

# ---- re-apply: PII masking only → accepted; any other body change after the engine read → exit 4
import shutil
n += 1
d1 = TMP / f"re{n}"
shutil.copytree(conflict_pd, d1)
s1 = d1 / "ocr" / "s001.md"
s1.write_text(s1.read_text(encoding="utf-8").replace("示例医院 临时医嘱单", "[PII_MASKED] 临时医嘱单", 1), encoding="utf-8")
rc, out = run_apply(d1, s1, engine="auto")  # reuses the saved engine output (one engine run per page)
check("re-apply after PII masking only → exit 0", rc == 0, str(out))
n += 1
d2 = TMP / f"re{n}"
shutil.copytree(conflict_pd, d2)
s2 = d2 / "ocr" / "s001.md"
s2.write_text(s2.read_text(encoding="utf-8").replace("2030-01-08[OCR_UNCERTAIN:U-001]", "2030-01-03", 1), encoding="utf-8")
rc, out = run_apply(d2, s2, engine="auto")
check("re-apply after editing the body towards the engine → exit 4", rc == 4, str(out))
n += 1
d3 = TMP / f"re{n}"
shutil.copytree(conflict_pd, d3)
s3 = d3 / "ocr" / "s001.md"
rc, out = run_apply(d3, s3, engine="none")
check("re-apply with --engine none replays the recorded engine read (the conflict token stays)",
      rc == 0 and "[OCR_UNCERTAIN:U-001]" in s3.read_text(encoding="utf-8"), str(out))

# ---- --apply refuses a sidecar that is not ready
pd, sc, _, _ = make(apply=False)
sc.write_text(sc.read_text(encoding="utf-8").replace("\n## PII\n\nmasked: none\n", "\n"), encoding="utf-8")
rc, out = run_apply(pd, sc, engine="none")
check("--apply before the `## PII` trailer → exit 2", rc == 2, str(out))
pd, sc, _, _ = make(apply=False)
sc.write_text(sc.read_text(encoding="utf-8").replace("PRIMARY_CHANNEL: llm_vision", "PRIMARY_CHANNEL: deterministic_ocr:tesseract"), encoding="utf-8")
rc, out = run_apply(pd, sc, engine="none")
check("--apply on a pixel page whose primary is not llm_vision → exit 2", rc == 2, str(out))

# ---- run_ocr_engine: tesseract TSV normalisation, `which` with no engine
tsv = TMP / "t.tsv"
tsv.write_text("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
               "5\t1\t1\t1\t1\t1\t10\t10\t40\t20\t91.5\t开立\n5\t1\t1\t1\t1\t2\t55\t10\t40\t20\t42.0\t日期\n"
               "5\t1\t1\t1\t2\t1\t10\t40\t90\t20\t88\t2030-01-08\n", encoding="utf-8")
p = subprocess.run([sys.executable, str(S / "run_ocr_engine.py"), "parse-tsv", str(tsv), "--out", str(TMP / "t.json")],
                   capture_output=True, text=True)
doc = json.loads((TMP / "t.json").read_text(encoding="utf-8")) if p.returncode == 0 else {}
lines = (doc.get("pages") or [{}])[0].get("lines", [])
check("parse-tsv: words grouped per line, line confidence = lowest word", [(l["text"], l["confidence"]) for l in lines]
      == [("开立 日期", 42.0), ("2030-01-08", 88.0)], str(lines))
check("parse-tsv: channel deterministic_ocr:tesseract", doc.get("channel") == "deterministic_ocr:tesseract")
env = dict(os.environ, CB_ORGANIZE_OCR_ENGINE="none")
p = subprocess.run([sys.executable, str(S / "run_ocr_engine.py"), "which"], capture_output=True, text=True, env=env)
check("which with no engine → exit 3", p.returncode == 3, p.stdout + p.stderr)
import shutil as _sh
if _sh.which("tesseract"):
    p = subprocess.run([sys.executable, str(S / "run_ocr_engine.py"), "which"], capture_output=True, text=True,
                       env=dict(os.environ, CB_ORGANIZE_OCR_ENGINE="tesseract"))
    check("which with only tesseract → exit 0 and a WARN", p.returncode == 0 and "WARN: only tesseract" in p.stderr, p.stderr)

print(f"second-read-align: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
