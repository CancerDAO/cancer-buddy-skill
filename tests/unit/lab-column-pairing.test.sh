#!/usr/bin/env bash
# O-03 lab column pairing (scripts/pair_lab_columns.py) — phase1 §7; CHANGELOG [Unreleased].
#
# Rule, per column: items == numeric results → results paired BY POSITION as
# candidate_value (value stays null); unit / range / flag columns are counted
# separately and paired only when their own count equals the item count, else left
# null with the count recorded; items != results → every pairing refused.
# Fixture: tests/fixtures/organize-regress/syn-lab-columns/src/linear.txt — a synthetic
# linear OCR text with the real failure shape (columns interleaved, 8 items / 8 results
# / 7 units / 7 ranges, arrow glyphs rendered as 小/个); every analyte order, range and value is invented.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/pair_lab_columns.py"
FIX="$REPO_ROOT/tests/fixtures/organize-regress/syn-lab-columns/src/linear.txt"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$SCRIPT" "$FIX" "$tmp" "$REPO_ROOT" <<'PY'
import json, subprocess, sys
from pathlib import Path
script, fix, tmp, repo = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def run(args):
    p = subprocess.run([sys.executable, script, *args], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


lines = fix.read_text(encoding="utf-8").splitlines()

# ---- positive: 8 items / 8 values / 7 units / 7 ranges → 8 candidates, unit+range null
rc, r = run(["--text", str(fix)])
check("positive: exit 0", rc == 0, str(rc))
check("positive: status paired", r["status"] == "paired")
check("positive: counts 8/8/7/7", (r["counts"]["items"], r["counts"]["values"], r["counts"]["units"],
      r["counts"]["ranges"]) == (8, 8, 7, 7), str(r["counts"]))
expected = [("AFP", "3.46"), ("ProGRP", "118.2"), ("NSE", "21.73"), ("HE4", "96.5"),
            ("SCC", "0.8"), ("CA15-3", "12.40"), ("FER", "402.6"), ("CA50", "7.9")]
got = [(p["item_code"], p["candidate_value"]) for p in r["pairs"]]
check("positive: 8 candidate values paired by position", got == expected, str(got))
check("positive: candidates never become confirmed values", all(p["value"] is None for p in r["pairs"]))
check("positive: pairing_method linear_position", all(p["pairing_method"] == "linear_position" for p in r["pairs"]))
check("positive: unit column (7 ≠ 8) left null", all(p["unit"] is None for p in r["pairs"]))
check("positive: range column (7 ≠ 8) left null", all(p["reference_range"] is None for p in r["pairs"]))
check("positive: columns_paired records value-only", r["columns_paired"] == {"value": True, "unit": False, "range": False, "flag": False})
check("positive: aux-column mismatch lowers confidence to low", all(p["pairing_confidence"] == "low" for p in r["pairs"]))
check("positive: counts stated in the note", "项目 8 / 数值 8 / 单位 7 / 参考范围 7" in r["pairs"][0]["pairing_note"])
check("positive: raw column strings recorded", r["column_raw"]["units"][0] == "ng/ml" and len(r["column_raw"]["ranges"]) == 7)
# artifact glyphs: '402.6小' → 402.6 + note; standalone '个' attaches to the preceding value
p6, p2, p1 = r["pairs"][6], r["pairs"][2], r["pairs"][1]
check("glyph: '402.6小' → candidate 402.6, raw kept", p6["candidate_value"] == "402.6" and p6["raw_value"] == "402.6小")
check("glyph: recorded as artifact, not a report flag", p6["artifact_glyphs"] == ["小"] and p6["flag"] is None
      and "未作为报告旗标写入" in p6["pairing_note"])
check("glyph: standalone '个' line attaches to the previous value", p2["artifact_glyphs"] == ["个"])
check("glyph: '118.2个' → 118.2", p1["candidate_value"] == "118.2" and p1["artifact_glyphs"] == ["个"])
check("glyph: a bare '个' line is not a result", r["counts"]["values"] == 8)
check("header lines with ：/，(dates, titles) are ignored", "2030/01/15" not in json.dumps(r["column_raw"]))
check("positive: top-level pairing_method / confidence", r["pairing_method"] == "linear_position"
      and r["pairing_confidence"] == "low", str((r["pairing_method"], r["pairing_confidence"])))
check("positive: counts.results = number of results", r["counts"]["results"] == 8)
check("positive: per-column decisions (value paired, 7-long unit/range columns null)",
      r["column_decisions"] == {"value": "paired", "unit": "null_count_mismatch", "range": "null_count_mismatch",
                                "flag": "null_count_mismatch"}, str(r["column_decisions"]))

# ---- negative ① (B8): one VALUE missing (items 8 / values 7) → every pairing refused
neg1 = tmp / "missing_value.txt"
drop = lines.index("12.40")
neg1.write_text("\n".join(lines[:drop] + lines[drop + 1:]) + "\n", encoding="utf-8")
rc, r = run(["--text", str(neg1)])
check("neg①: exit 3 (refused)", rc == 3, str(rc))
check("neg①: status refused / item_value_count_mismatch",
      r["status"] == "refused" and r["refused_reason"] == "item_value_count_mismatch")
check("neg①: NO candidate bound to any item", all(p["candidate_value"] is None and p["value"] is None for p in r["pairs"]))
check("neg①: pairing_method none for all 8 items", len(r["pairs"]) == 8 and all(p["pairing_method"] == "none" for p in r["pairs"]))
check("neg①: every column decision is refused_all, method none",
      set(r["column_decisions"].values()) == {"refused_all"} and r["pairing_method"] == "none"
      and r["pairing_confidence"] is None, str(r["column_decisions"]))
check("neg①: counts + raw strings reported", r["counts"]["values"] == 7 and "12.40" not in r["column_raw"]["values"]
      and "项目 8 / 数值 7" in r["notes"][0])

# ---- negative ② (B8): one UNIT missing → values still paired, unit column null + count
neg2 = tmp / "missing_unit.txt"
first_unit = lines.index("ng/ml")
neg2.write_text("\n".join(lines[:first_unit] + lines[first_unit + 1:]) + "\n", encoding="utf-8")
rc, r = run(["--text", str(neg2)])
check("neg②: values still paired", rc == 0 and r["status"] == "paired" and len(r["pairs"]) == 8)
check("neg②: unit count 6 recorded, column null", r["counts"]["units"] == 6 and all(p["unit"] is None for p in r["pairs"]))
check("neg②: note names the unpaired unit column", "单位列 6 个" in r["notes"][0])

# ---- all four columns agree → units/ranges paired, confidence medium
cols = {"items": ["A（AAA）", "B（BBB）"], "values": ["1.5", "2.5↑".replace("↑", "个")],
        "units": ["U/ml", "ng/ml"], "ranges": ["0-5", "≥3"]}
cf = tmp / "cols.json"
cf.write_text(json.dumps(cols, ensure_ascii=False), encoding="utf-8")
rc, r = run(["--columns", str(cf)])
check("columns mode: units paired when counts match", rc == 0 and [p["unit"] for p in r["pairs"]] == ["U/ml", "ng/ml"])
check("columns mode: ranges paired when counts match", [p["reference_range"] for p in r["pairs"]] == ["0-5", "≥3"])
check("columns mode: full agreement → medium confidence (never high on linear text)",
      all(p["pairing_confidence"] == "medium" for p in r["pairs"]))

# ---- `<x` is ambiguous (a below-limit result OR a one-sided reference range). Here a result
#      was lost by OCR and `<5.0` (AFP's range) fills its slot: items 3 == numbers 3, so a
#      count-only rule would bind a reference range as FER's value. Refuse instead.
lt1 = tmp / "lt_range_in_value_slot.txt"
lt1.write_text("检验项目\n甲胎蛋白（AFP）\n胃泌素释放肽前体（ProGRP）\n铁蛋白（FER）\n结果\n3.2\n20.1\n"
               "参考范围\n<5.0\n0-35\n0-37\n", encoding="utf-8")
rc, r = run(["--text", str(lt1)])
check("`<x` token with an incomplete range column → refused", rc == 3 and r["status"] == "refused"
      and r["refused_reason"] == "ambiguous_inequality_token", str(r and r["refused_reason"]))
check("…nothing bound, the ambiguous count reported", all(p["candidate_value"] is None for p in r["pairs"])
      and r["counts"]["ambiguous"] == 1 and "<5.0" in r["notes"][0])
lt3 = tmp / "lt_below_limit_result.txt"
lt3.write_text("检验项目\n甲胎蛋白（AFP）\n胃泌素释放肽前体（ProGRP）\n结果\n<0.50\n20.1\n"
               "参考范围\n0-5\n0-35\n", encoding="utf-8")
rc, r = run(["--text", str(lt3)])
check("`<x` with a complete range column is a result → paired",
      rc == 0 and [p["candidate_value"] for p in r["pairs"]] == ["<0.50", "20.1"]
      and [p["reference_range"] for p in r["pairs"]] == ["0-5", "0-35"], str(r and r["pairs"]))
check("the committed fixture has no ambiguous token", run(["--text", str(fix)])[1]["counts"]["ambiguous"] == 0)

# ---- one item + one result → single_value: the number IS the value (nothing to mis-align)
sv = tmp / "single_value.txt"
sv.write_text("检验项目\n甲胎蛋白（AFP）\n结果\n5.20\n单位\nng/ml\n参考范围\n0-5\n", encoding="utf-8")
rc, r = run(["--text", str(sv)])
check("single_value: exit 0, method single_value", rc == 0 and r["pairing_method"] == "single_value", str(r))
p = r["pairs"][0]
check("single_value: value filled, no candidate", p["value"] == "5.20" and p["candidate_value"] is None
      and p["pairing_method"] == "single_value" and p["unit"] == "ng/ml" and p["reference_range"] == "0-5", str(p))
check("single_value: complete aux columns → high", r["pairing_confidence"] == "high" and p["pairing_confidence"] == "high")
sv2 = tmp / "single_item_two_values.txt"
sv2.write_text("检验项目\n甲胎蛋白（AFP）\n结果\n5.20\n6.10\n", encoding="utf-8")
rc, r = run(["--text", str(sv2)])
check("one item / two results → refused, no value", rc == 3 and r["pairing_method"] == "none"
      and r["pairs"][0]["value"] is None and r["pairs"][0]["candidate_value"] is None, str(r and r["pairs"]))
sv3 = tmp / "single_ambiguous.txt"
sv3.write_text("检验项目\n甲胎蛋白（AFP）\n结果\n<5.0\n", encoding="utf-8")
rc, r = run(["--text", str(sv3)])
check("one item / one `<x` token with no range column → refused (could be the range)",
      rc == 3 and r["refused_reason"] == "ambiguous_inequality_token", str(r and r["refused_reason"]))

# ---- no item header → refused, nothing paired
nh = tmp / "no_header.txt"
nh.write_text("结果\n1.2\n3.4\n", encoding="utf-8")
rc, r = run(["--text", str(nh)])
check("no item header → refused", rc == 3 and r["refused_reason"] == "no_item_header" and r["pairs"] == [])

# ---- the labs.json schema enforces the same rule (candidate never in value)
sys.path.insert(0, repo + "/tests/fixtures/organize-regress")
try:
    import synlib
    doc = synlib.fixture_doc("labs.json")
    v = doc["panels"][0]["values"][0]
    check("labs fixture: linear_position rows keep value null", v["value"] is None and v["candidate_value"] == "3.46")
    v["value"] = 3.46
    check("labs schema: linear_position with a value → rejected", bool(synlib.schema_errors("labs.schema.json", doc)))
    v.update({"pairing_method": "single_value", "candidate_value": None, "value": "3.46", "pairing_confidence": "high"})
    check("labs schema: single_value with a value → accepted", synlib.schema_errors("labs.schema.json", doc) == [])
except ImportError:
    print("SKIP: jsonschema not installed (schema half)", file=sys.stderr)

# ---- review findings (R7 / R8 / R9 / R18 / R19): tokens that used to shift or refuse -------------
def text_case(name, lines_):
    f = tmp / f"{name}.txt"
    f.write_text("\n".join(lines_) + "\n", encoding="utf-8")
    return run(["--text", str(f)])


rc, r = text_case("arrows", ["检验项目", "白细胞计数", "中性粒细胞百分比", "血红蛋白", "血小板计数", "结果", "11.20↑", "85.3↑",
                             "98↓", "250", "单位", "10^9/L", "%", "g/L", "10^9/L", "参考范围", "3.5-9.5", "40-75", "130-175", "125-350"])
check("R9 results with a printed ↑/↓ are results (4/4 paired, not refused)",
      rc == 0 and [p["candidate_value"] for p in r["pairs"]] == ["11.20", "85.3", "98", "250"], str(r and r["counts"]))
check("R9 …the glyph is kept as flag_glyph + in the note, never as the report flag",
      [p["flag_glyph"] for p in r["pairs"]] == ["↑", "↑", "↓", None] and all(p["flag"] is None for p in r["pairs"])
      and "印刷标记「↑」" in r["pairs"][0]["pairing_note"], str([(p["flag_glyph"], p["flag"]) for p in r["pairs"]]))
rc, r = text_case("hflag", ["检验项目", "ALT", "AST", "结果", "56 H", "30", "单位", "U/L", "U/L", "参考范围", "9-50", "15-40"])
check("R9 `56 H` is a result with flag glyph H", rc == 0 and r["pairs"][0]["candidate_value"] == "56" and r["pairs"][0]["flag_glyph"] == "H", str(r and r["pairs"][:1]))
rc, r = text_case("merge_single", ["检验项目", "血红蛋白", "血小板计数(PLT)", "结果", "98", "单位", "g/L", "参考范围", "130-175"])
check("R7 an item with no code is not merged into the next (血红蛋白 + 血小板计数(PLT) = 2 items) → refused, no value",
      rc == 3 and r["counts"]["items"] == 2 and all(p["value"] is None for p in r["pairs"]), str(r and r["counts"]))
rc, r = text_case("merge_shift", ["检验项目", "白细胞计数(WBC)", "血红蛋白", "血小板计数(PLT)", "结果", "98", "250", "单位", "g/L",
                                  "10^9/L", "参考范围", "130-175", "125-350"])
check("R8 merged item names can no longer make items == values (shifted candidates) → refused",
      rc == 3 and r["refused_reason"] == "item_value_count_mismatch", str(r and r["refused_reason"]))
rc, r = text_case("single_qual", ["检验项目", "24小时尿蛋白定量", "结果", "阴性", "参考范围", "0.15"])
check("R7 one item whose qualitative result stands beside a one-number reference → refused (not value 0.15)",
      rc == 3 and all(p["value"] is None for p in r["pairs"]), str(r and r["pairs"]))
rc, r = text_case("qual_shift", ["检验项目", "尿蛋白", "尿比重", "pH", "结果", "阳性", "1.020", "6.0", "参考范围", "阴性", "1.003-1.030", "8"])
check("R8 a qualitative result + a stray number no longer shift the candidates → refused",
      rc == 3 and all(p["candidate_value"] is None for p in r["pairs"]), str(r and r["refused_reason"]))
rc, r = text_case("qual", ["检验项目", "尿蛋白", "尿糖", "尿比重", "pH", "结果", "阴性", "2+", "1.020", "6.0",
                           "参考范围", "阴性", "阴性", "1.003-1.030", "5.0-8.0"])
check("qualitative results are results; 阴性 under 参考范围 is the reference (4/4, ranges paired)",
      rc == 0 and [p["candidate_value"] for p in r["pairs"]] == ["阴性", "2+", "1.020", "6.0"]
      and r["pairs"][0]["reference_range"] == "阴性", str(r and r["pairs"]))
rc, r = text_case("odd", ["检验项目", "A", "B", "结果", "1.1", "见附页", "2.2", "参考范围", "0-5", "0-5"])
check("R8 an unclassifiable value-zone token → refused (unclassified_value_zone_tokens)",
      rc == 3 and r["refused_reason"] == "unclassified_value_zone_tokens" and "见附页" in r["notes"][0], str(r and r["refused_reason"]))
rc, r = text_case("cn_units", ["检验项目", "红细胞", "白细胞", "管型", "凝血酶原时间", "结果", "3", "12", "0", "13.5", "单位", "个/HP",
                               "个/μl", "个/LP", "秒", "参考范围", "0-3", "0-25", "0-1", "11-14.5"])
check("R18 个/HP · 个/μl · 秒 are units (column paired)", rc == 0 and [p["unit"] for p in r["pairs"]] == ["个/HP", "个/μl", "个/LP", "秒"],
      str(r and r["counts"]))
rc, r = text_case("titer", ["检验项目", "抗核抗体", "补体C3", "结果", "1:320", "0.85", "参考范围", "1:100以下", "0.9-1.8"])
check("R18 a titer 1:320 is a result (no longer dropped as metadata)", r["counts"]["values"] >= 2 and "1:320" in r["column_raw"]["values"],
      str(r and r["column_raw"]))
big = tmp / "huge.txt"
big.write_text("检验项目\n项目A(X)\n" + "\n".join(f"名称片段{i}" for i in range(40000)) + "\n结果\n1\n", encoding="utf-8")
import time
t0 = time.time()
rc, r = run(["--text", str(big)])
check("R19 a 40,000-line item zone is refused quickly (linear merge, zone cap)", rc == 3 and time.time() - t0 < 5,
      f"{time.time() - t0:.1f}s {r and r['refused_reason']}")
rc, r = text_case("single_merged", ["检验项目", "胃泌素释放肽前体", "（ProGRP）", "结果", "45.1", "单位", "pg/ml", "参考范围", "0-65"])
check("R7 one item wrapped over two lines is a (low) candidate, never single_value",
      rc == 0 and r["pairing_method"] == "linear_position" and r["pairs"][0]["value"] is None
      and r["pairs"][0]["candidate_value"] == "45.1" and r["pairing_confidence"] == "low", str(r and r["pairs"]))

# ---- --tsv: word boxes → rows → pairing_method bbox (a formal value, from coordinates) -------------
HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def words(y, cells):
    """cells: [(x, text)] — CJK header text is split per character, as tesseract prints it."""
    out = []
    for x, text in cells:
        if text in ("检验项目", "结果", "单位", "参考范围"):
            for k, ch in enumerate(text):
                out.append(f"5\t1\t1\t1\t1\t1\t{x + 20 * k}\t{y}\t18\t20\t91.0\t{ch}")
        else:
            out.append(f"5\t1\t1\t1\t1\t1\t{x}\t{y}\t{max(18, 12 * len(text))}\t20\t88.0\t{text}")
    return out


tsv_rows = [HEAD, "4\t1\t1\t1\t1\t0\t10\t100\t700\t20\t-1\t"]
tsv_rows += words(100, [(10, "检验项目"), (300, "结果"), (450, "单位"), (600, "参考范围")])
tsv_rows += words(140, [(10, "甲胎蛋白（AFP）"), (300, "4.10"), (450, "ng/ml"), (600, "0-7")])
tsv_rows += words(180, [(10, "神经元特异性烯醇化酶（NSE）"), (300, "19.60↑"), (450, "ng/ml"), (600, "0-16.3")])
tsv_rows += words(221, [(10, "人附睾蛋白")])
tsv_rows += words(260, [(10, "4（HE4）"), (300, "61.3"), (450, "pmol/L"), (600, "0-140")])
tsv_rows += words(300, [(10, "肌酐"), (300, "5.2"), (340, "6.1"), (450, "μmol/L"), (600, "59-104")])
tsv_rows += words(340, [(10, "检验者：示例")])
tf = tmp / "table.tsv"
tf.write_text("\n".join(tsv_rows) + "\n", encoding="utf-8")
rc, r = run(["--tsv", str(tf)])
got = [(p["item"], p["value"], p["pairing_method"]) for p in r["pairs"]] if r else None
check("--tsv: rows clustered by y, cells by the nearest column header → bbox values",
      rc == 0 and got[:3] == [("甲胎蛋白（AFP）", "4.10", "bbox"), ("神经元特异性烯醇化酶（NSE）", "19.60", "bbox"),
                              ("人附睾蛋白4（HE4）", "61.3", "bbox")], str(got))
check("--tsv: bbox values are values (not candidates), unit and range from the same row",
      r["pairs"][0]["candidate_value"] is None and r["pairs"][0]["unit"] == "ng/ml" and r["pairs"][0]["reference_range"] == "0-7",
      str(r["pairs"][0]))
check("--tsv: an attached ↑ is a flag glyph, not the report flag", r["pairs"][1]["flag_glyph"] == "↑" and r["pairs"][1]["flag"] is None)
check("--tsv: a row whose result cell holds two numbers is NOT paired (method none, value null)",
      got[3][0] == "肌酐" and got[3][1] is None and got[3][2] == "none", str(got))
check("--tsv: the footer row (检验者：…) ends the table", len(r["pairs"]) == 4, str(len(r["pairs"])))
tf2 = tmp / "noheader.tsv"
tf2.write_text("\n".join([HEAD] + words(140, [(10, "甲胎蛋白（AFP）"), (300, "4.10")])) + "\n", encoding="utf-8")
rc, r = run(["--tsv", str(tf2)])
check("--tsv without an item + result header row → refused", rc == 3 and r["refused_reason"] == "no_item_header", str(r and r["refused_reason"]))

print(f"lab-column-pairing: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
