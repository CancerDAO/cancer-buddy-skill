#!/usr/bin/env bash
# tests/unit/high-risk-classify.test.sh — organize v3→v4 fix spec B1 / B18.
#
# scripts/_high_risk.py is the single authority that answers "must this field be
# independently re-read?". Two consumers depend on that one answer: plan_second_read.py
# builds the 段 1.5 queue from it (the NUMERATOR's input) and
# validate_structured_outputs.py reconciles the inventory's high_risk_fields[] against it
# (the DENOMINATOR). While each script carried its own word list they drifted, and the
# drift was silent in the worst direction: the validator accepted a manifest that had
# dropped `WBC` because its own copy of the list only knew 「白细胞计数」. A denominator
# each consumer may redefine is not a denominator.
#
# So classify_label() is not an ordinary helper — it is a contract, and this file pins the
# behaviours that other files' correctness rests on:
#
#   * 「白细胞计数参考范围」 and `WBC ref` are reference_range, NOT lab_value. That is an
#     ORDERING fact, not a wording preference: lab_value's substrings (「值」/value/result/
#     count) are the broadest in the table, so if it were asked first every printed
#     interval would classify as a value. The printed reference interval is its own
#     failure mode — inverted bounds, or an interval串行 from the neighbouring row — and
#     collapsing it into lab_value loses the class that names that failure;
#   * `c.2573T>G` is a variant — the `c.`/`p.` position swap is the single most damaging
#     one-character misread in a molecular report;
#   * 「评效」 is response_wording, the fourth oncology class. It is high-risk precisely
#     because this skill may never re-derive it: a response code can only be copied, so a
#     copy error has no second correction path downstream;
#   * 「奥希替尼」 is drug_name (the 「替尼」 suffix family is where look-alike drug names
#     live);
#   * 「血压」 is None — and the negative arm matters as much as the positive one. A
#     classifier that quietly bottoms out into some catch-all class would put every label
#     on a page into the denominator, every archive would fail the reconciliation gate,
#     and the cure for the noise would be deleting labels from frontmatter — the same
#     defect the gate exists to stop, one level down.
#
# The last section is the no-drift check (B18). references/high-risk-fields.md explains
# WHICH classes exist and why each is dangerous; this .py holds the keywords. Two files,
# one fact — so the test asserts they still agree on the class list: 9 general + 4
# oncology, the same 13 keys, and the prose naming this module as the sole authority for
# the word table. The oncology count is the one that actually drifted: the heading said
# "3 类" while the table listed four, because response_wording was added later.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
HR="$ORG/scripts/_high_risk.py"
MD="$ORG/references/high-risk-fields.md"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

[ -f "$HR" ] || { echo "FAIL: missing $HR" >&2; exit 1; }
[ -f "$MD" ] || { echo "FAIL: missing $MD" >&2; exit 1; }

# ===========================================================================
# A. The gold table — every label classified in ONE import, then compared here
# ===========================================================================
echo "=== A. classify_label() gold labels ==="

# label <TAB> expected class ("None" spelled out for the labels that must NOT be
# high-risk). Every class name below is read off the module's own enumeration — see
# section C, which fails if these names ever stop being the real ones.
cat > "$tmp/gold.tsv" <<'GOLD'
白细胞计数参考范围	reference_range
WBC ref	reference_range
参考范围	reference_range
c.2573T>G	variant
EGFR	variant
评效	response_wording
PR	response_wording
奥希替尼	drug_name
WBC	lab_value
中性粒细胞绝对值	lab_value
住院号	identifier
病理号	accession
报告日期	date
10^9/L	unit
剂量	dose
q3w	frequency
TNM分期	stage
变异等位基因频率	vaf
血压	None
主诉	None
影像所见	None
科室	None
GOLD

cut -f1 "$tmp/gold.tsv" > "$tmp/labels.txt"
python3 - "$ORG" "$tmp/labels.txt" > "$tmp/actual.tsv" <<'PYEOF'
import sys, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
h = importlib.import_module("_high_risk")
for line in pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    print(f"{line}\t{h.classify_label(line)}")
PYEOF

while IFS=$'\t' read -r label want; do
  got="$(awk -F'\t' -v l="$label" '$1==l {print $2; exit}' "$tmp/actual.tsv")"
  if [ "$got" = "$want" ]; then
    ok "classify_label($label) = $want"
  else
    no "classify_label($label) = ${got:-<no output>}, expected $want"
  fi
done < "$tmp/gold.tsv"

# The two orderings that are load-bearing, asserted as a RELATION rather than as two
# independent facts: a table that stopped asking reference_range before lab_value would
# still classify both labels — into the wrong class, together.
rr="$(awk -F'\t' '$1=="白细胞计数参考范围"{print $2}' "$tmp/actual.tsv")"
lv="$(awk -F'\t' '$1=="白细胞计数"||$1=="WBC"{print $2; exit}' "$tmp/actual.tsv")"
[ "$rr" = "reference_range" ] && [ "$rr" != "$lv" ] \
  && ok "the interval and the value land in DIFFERENT classes (ordering intact)" \
  || no "reference_range collapsed into lab_value: interval=$rr value=$lv"

# ===========================================================================
# B. The negative arm — nothing falls through into a catch-all
# ===========================================================================
echo
echo "=== B. non-high-risk labels return None, and so do non-labels ==="

python3 - "$ORG" > "$tmp/neg.txt" <<'PYEOF'
import sys, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
h = importlib.import_module("_high_risk")

# Labels a real page prints that carry no one-character catastrophe. If any of these
# classified, the denominator would swallow the whole page.
benign = ["血压", "身高", "体重", "主诉", "现病史", "既往史", "家族史", "科室",
          "影像所见", "肿瘤大小", "签名", "备注"]
print("benign_all_none", all(h.classify_label(x) is None for x in benign))
print("benign_is_high_risk_all_false", not any(h.is_high_risk(x) for x in benign))

# Total on junk input: the validator calls this on whatever a model wrote into
# frontmatter, so a non-string must be None, not a TypeError that takes the gate down.
junk = [None, 123, 4.5, ["白细胞"], {"label": "WBC"}, b"WBC", "", "   ", "\n"]
print("junk_all_none", all(h.classify_label(x) is None for x in junk))

# Deterministic: same label, same answer, every call. The validator recomputes a set and
# compares it with a declaration; a comparison against a non-deterministic function
# proves nothing.
probes = ["WBC", "住院号", "c.2573T>G", "评效", "奥希替尼", "血压"]
first = [h.classify_label(x) for x in probes]
print("deterministic", all(first == [h.classify_label(x) for x in probes] for _ in range(5)))

# Every class it can return is a declared class. A stray string here would be a class no
# schema, no reference and no consumer knows about.
returned = {h.classify_label(x) for x in
            ["WBC", "住院号", "报告日期", "剂量", "q3w", "10^9/L", "参考范围", "病理号",
             "奥希替尼", "TNM分期", "c.2573T>G", "变异等位基因频率", "评效"]}
print("classes_declared", returned <= set(h.HIGH_RISK_CLASSES) and len(returned) == 13)
print("is_high_risk_agrees",
      all(h.is_high_risk(x) == (h.classify_label(x) is not None)
          for x in benign + ["WBC", "住院号", "评效", "c.2573T>G"]))
PYEOF

check_flag() {  # <key> <human-readable claim>
  grep -q "^$1 True$" "$tmp/neg.txt" && ok "$2" || no "$2 — got: $(grep "^$1 " "$tmp/neg.txt")"
}
check_flag benign_all_none "12 benign page labels all classify to None (no catch-all class)"
check_flag benign_is_high_risk_all_false "is_high_risk() is False for all of them"
check_flag junk_all_none "non-string / empty / whitespace input returns None, never raises"
check_flag deterministic "classify_label is deterministic across repeated calls"
check_flag classes_declared "every class returned is one of the 13 declared classes"
check_flag is_high_risk_agrees "is_high_risk() is exactly classify_label() is not None"

# ===========================================================================
# C. No drift between the word table (.py) and the class list (.md) — B18
# ===========================================================================
echo
echo "=== C. _high_risk.py vs references/high-risk-fields.md ==="

python3 - "$ORG" "$MD" > "$tmp/drift.txt" <<'PYEOF'
import sys, re, pathlib, importlib
sys.path.insert(0, sys.argv[1] + "/scripts")
h = importlib.import_module("_high_risk")
md = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")

print("py_general", len(h.GENERAL_CLASSES))
print("py_oncology", len(h.ONCOLOGY_CLASSES))
print("py_total", len(h.HIGH_RISK_CLASSES))
print("py_unique", len(set(h.HIGH_RISK_CLASSES)) == len(h.HIGH_RISK_CLASSES))
# Internal consistency: the evaluation order and the keyword tables must cover exactly
# the declared classes. A class present in _ORDER but absent from HIGH_RISK_CLASSES (or
# vice versa) is a class that is matched but never reportable, or declared but dead.
order = set(h._ORDER)
tables = set(h._SUBSTRING) | set(h._TOKEN)
print("py_order_covers", order == set(h.HIGH_RISK_CLASSES))
print("py_tables_covered", tables <= set(h.HIGH_RISK_CLASSES))

def section(heading_re, stop_re):
    start = re.search(heading_re, md)
    if not start:
        return None, []
    rest = md[start.end():]
    stop = re.search(stop_re, rest)
    body = rest[: stop.start()] if stop else rest
    return start.group(1), re.findall(r"^\|\s*`([a-z_]+)`", body, re.M)

g_n, g_keys = section(r"###\s*1\.1\s*通用层（(\d+)\s*类", r"###\s*1\.2")
o_n, o_keys = section(r"###\s*1\.2\s*肿瘤\s*pack（(\d+)\s*类", r"###\s*1\.3")
print("md_general_count", g_n)
print("md_oncology_count", o_n)
print("md_general_rows", len(g_keys))
print("md_oncology_rows", len(o_keys))
print("md_general_keys_match", sorted(g_keys) == sorted(h.GENERAL_CLASSES))
print("md_oncology_keys_match", sorted(o_keys) == sorted(h.ONCOLOGY_CLASSES))
print("md_response_wording_listed", "response_wording" in o_keys)
# B18: the .md may describe the classes, but it must point at this module for the words.
print("md_names_authority", "_high_risk.py" in md)
PYEOF

val() { grep "^$1 " "$tmp/drift.txt" | cut -d' ' -f2; }

[ "$(val py_general)" = "9" ] && ok "_high_risk.GENERAL_CLASSES has 9 classes" \
  || no "GENERAL_CLASSES has $(val py_general), expected 9"
[ "$(val py_oncology)" = "4" ] && ok "_high_risk.ONCOLOGY_CLASSES has 4 classes (B18)" \
  || no "ONCOLOGY_CLASSES has $(val py_oncology), expected 4"
[ "$(val py_total)" = "13" ] && ok "HIGH_RISK_CLASSES = 9 + 4 = 13" \
  || no "HIGH_RISK_CLASSES has $(val py_total), expected 13"
[ "$(val py_unique)" = "True" ] && ok "no class name appears in both layers" \
  || no "duplicate class name across the two layers"
[ "$(val py_order_covers)" = "True" ] && ok "_ORDER covers exactly the declared classes" \
  || no "_ORDER and HIGH_RISK_CLASSES disagree — a class is matched but not declared"
[ "$(val py_tables_covered)" = "True" ] && ok "every keyword table key is a declared class" \
  || no "a keyword table declares a class that does not exist"

[ "$(val md_general_count)" = "9" ] && ok "high-risk-fields.md §1.1 heading says 9 类" \
  || no "§1.1 heading says $(val md_general_count) 类, code has 9"
[ "$(val md_oncology_count)" = "4" ] && ok "high-risk-fields.md §1.2 heading says 4 类 (B18)" \
  || no "§1.2 heading says $(val md_oncology_count) 类, code has 4 — the drift B18 fixed"
[ "$(val md_general_rows)" = "9" ] && ok "§1.1 table lists 9 rows" \
  || no "§1.1 table lists $(val md_general_rows) rows"
[ "$(val md_oncology_rows)" = "4" ] && ok "§1.2 table lists 4 rows" \
  || no "§1.2 table lists $(val md_oncology_rows) rows"
[ "$(val md_general_keys_match)" = "True" ] && ok "§1.1 keys are exactly GENERAL_CLASSES" \
  || no "§1.1 keys differ from GENERAL_CLASSES"
[ "$(val md_oncology_keys_match)" = "True" ] && ok "§1.2 keys are exactly ONCOLOGY_CLASSES" \
  || no "§1.2 keys differ from ONCOLOGY_CLASSES"
[ "$(val md_response_wording_listed)" = "True" ] \
  && ok "response_wording is documented as the 4th oncology class" \
  || no "response_wording missing from §1.2"
[ "$(val md_names_authority)" = "True" ] \
  && ok "the reference names scripts/_high_risk.py as the sole word-table authority" \
  || no "the reference does not point at _high_risk.py (B18)"

echo
echo "== high-risk-classify: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
