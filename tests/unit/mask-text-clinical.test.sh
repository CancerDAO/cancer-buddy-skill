#!/usr/bin/env bash
# tests/unit/mask-text-clinical.test.sh — organize v3 fix spec A7, pii_rescan.mask_text().
#
# WHY THIS FILE EXISTS
#   Detection and rewriting are different jobs with OPPOSITE error costs, and A7 exists
#   because they were once done by one shared regex set.
#
#     A DETECTOR that over-fires costs a human one glance. The line is flagged, someone
#     reads it in context, and moves on. Nothing is lost.
#
#     A REWRITER that over-fires destroys a clinical value in the only copy anything
#     downstream will ever read — the masked sidecar is the single plaintext boundary;
#     timeline.md / case_text.md / profile.json / the 段D HTML all read it and NEVER
#     re-open the original. And it does so SILENTLY: the deleted characters are not in
#     the output to be noticed. The archive ends up asserting an amylase of
#     "[PII_MASKED]" and no gate anywhere can tell that it ever said 105.
#
#   Two shapes were doing exactly that and are now DETECT-ONLY:
#     US 10-digit  \(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}   matches `淀粉酶 105 350 1200` —
#         a result followed by the two ends of the printed reference range. An entire
#         lab row, character for character.
#     E.164        \+\d[\d\s().-]{6,}\d                matches `ΔSUV +4.20 (2.10-8.30)`
#         and any signed value trailed by parenthesised numbers.
#   Both stay in the DETECT set (`scan_line`) so a human is still told; neither rewrites.
#
#   Added in their place: LABEL-ANCHORED Chinese record identifiers. A bare 7-digit
#   住院号 is indistinguishable from a lab value by shape alone, but is unambiguous once
#   `住院号` sits next to it — and only the digits are replaced, the label survives.
#
# WHAT THIS FILE ASSERTS
#   20 clinical strings survive mask_text() BYTE-FOR-BYTE, and 5 real identifiers do not.
#   The clinical corpus is the load-bearing half: any future widening of the rewrite set
#   has to walk past 20 named lab rows, doses, variants, ranges, dates and percentages.
#   It also pins the ASYMMETRY directly — `淀粉酶 105 350 1200` must be REPORTED by
#   scan_line() and left ALONE by mask_text() — because "just use the same regexes for
#   both" is the exact refactor A7 undoes.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# The corpus and the assertions live in Python (mask_text is a Python function and the
# strings are full of CJK + regex-hostile punctuation), but every single case is reported
# back as its own line so the bash-level counters stay honest about how many facts were
# actually checked.
python3 - "$ORG" > "$tmp/results.tsv" <<'PYEOF'
import importlib
import re
import sys

sys.path.insert(0, sys.argv[1] + "/scripts")
p = importlib.import_module("pii_rescan")

results = []


def report(good: bool, label: str) -> None:
    results.append(("OK" if good else "NO") + "\t" + label)


# --------------------------------------------------------------------------- #
# A. 20 clinical strings that must come back UNCHANGED.
#    Each one is a shape that a naive "mask anything that looks like a number run"
#    rewriter eats. The comment on each says which rewrite rule it is defending against.
# --------------------------------------------------------------------------- #
CLINICAL = [
    # the canonical A7 regression: result + both ends of the printed reference range
    ("淀粉酶 105 350 1200", "lab result + reference range (the US-phone false positive)"),
    ("剂量 200 400 1200 mg", "a dose-escalation row of three plain numbers"),
    ("c.2573T>G", "an HGVS coding-level variant"),
    ("ΔSUV +4.20 (2.10-8.30)", "a signed delta with a parenthesised range (the E.164 false positive)"),
    ("Telomere length 5200", "the literal 'tel'-substring regression that ate a telomere length"),
    ("血常规 WBC 3.21 RBC 4.05 HGB 128 PLT 210", "a four-analyte blood-count panel"),
    ("肌酐 88 62 115 umol/L", "creatinine + range, three bare integers in a row"),
    ("T2N1M0 IIIA期", "a TNM stage string"),
    ("p.L858R 丰度 32.5%", "a protein-level variant with an allele fraction"),
    ("EGFR exon 19 del 检出", "a gene / exon / deletion call"),
    ("2026-03-15 门诊复查", "an ISO clinical date"),
    ("中性粒细胞 1.80 ×10^9/L", "a 10^9/L cell count"),
    ("HBsAg 0.05 IU/mL", "a serology titre below 1"),
    ("Ki-67 30%", "an IHC proliferation index"),
    ("第 3 周期 D1 化疗", "a chemotherapy cycle / day number"),
    ("参考范围 3.50-9.50", "a bare reference interval"),
    ("紫杉醇 175 mg/m2 d1 q21d", "a body-surface-area dose with a schedule"),
    ("PSA 4.02 0.00 4.00 ng/mL", "a tumour marker printed with a 0-bounded range"),
    ("(415) 555-0132", "a US-format phone — DETECT-ONLY under A7, never rewritten"),
    ("+1 415 555 0132", "an E.164 number with separators — DETECT-ONLY under A7"),
]
assert len(CLINICAL) == 20, f"the clinical corpus must stay at 20 strings, got {len(CLINICAL)}"

for text, why in CLINICAL:
    masked, spans = p.mask_text(text)
    unchanged = masked == text and not spans
    detail = "" if unchanged else f"  -> {masked!r} spans={spans}"
    report(unchanged, f"UNCHANGED: {why} :: {text!r}{detail}")

# The clinical corpus must not be quietly satisfied by a mask_text that masks nothing.
probe, _ = p.mask_text("13812345678")
report(p.MASK_TOKEN in probe,
       "control: the masker is actually live (a known CN mobile IS replaced)")

# --------------------------------------------------------------------------- #
# B. 5 real identifiers that MUST be masked — and the clinical characters beside
#    them must survive, because a rewriter that eats its neighbours is the other
#    half of the same failure.
# --------------------------------------------------------------------------- #
PII = [
    ("身份证 110101199003072316 登记于 2026-03-15",
     "110101199003072316",
     ["身份证", "登记于", "2026-03-15"],
     "id_number",
     "an 18-digit Chinese ID number"),
    ("证件号 11010119900307231X 复核 Ki-67 30%",
     "11010119900307231X",
     ["证件号", "复核", "Ki-67 30%"],
     "id_number",
     "an 18-digit Chinese ID ending in the X check character"),
    ("联系电话 13812345678 家属 WBC 3.21",
     "13812345678",
     ["联系电话", "家属", "WBC 3.21"],
     "phone",
     "a CN mobile 13812345678"),
    ("报告发送至 zhang.san@example.com 附 c.2573T>G",
     "zhang.san@example.com",
     ["报告发送至", "附", "c.2573T>G"],
     "email",
     "an email address"),
    ("住院号 0012345678 床号 12 淀粉酶 105",
     "0012345678",
     ["住院号", "床号 12", "淀粉酶 105"],
     "record_number",
     "住院号 0012345678 (label-anchored; the LABEL survives, only the digits go)"),
    ("条码 123456789012 扫描 Ki-67 30%",
     "123456789012",
     ["条码", "扫描", "Ki-67 30%"],
     "numeric_id",
     "a bare 12-digit run of digits"),
]

for text, ident, survivors, want_kind, why in PII:
    masked, spans = p.mask_text(text)
    report(p.MASK_TOKEN in masked, f"MASKED: {why}")
    # gone whole — not shortened, not partially masked. A half-masked identifier
    # (`1101011990[PII_MASKED]`) is still a lookup key.
    report(ident not in masked, f"…the identifier {ident!r} is absent from the output ({why})")
    ident_run = max(re.findall(r"\d+", ident), key=len, default="")
    if ident_run:
        longest = max(re.findall(r"\d+", masked), key=len, default="")
        report(len(longest) < len(ident_run),
               f"…no digit run as long as the original ({len(ident_run)} digits) "
               f"survives ({why})")
    report(any(s["kind"] == want_kind for s in spans),
           f"…the span records kind={want_kind!r}, got {[s['kind'] for s in spans]}")
    # SPANS, NOT SNIPPETS: echoing the matched text into the manifest would reopen
    # exactly the leak the masking just closed.
    report(all(set(s) <= {"kind", "len", "line"} for s in spans),
           f"…the span carries only {{kind,len,line}} and never the matched value ({why})")
    for keep in survivors:
        report(keep in masked,
               f"…surrounding clinical text {keep!r} is untouched ({why})")

# 5 distinct identifier CLASSES are covered (the 6 rows above collapse to 5 kinds plus
# the labelled-record arm A7 added).
kinds = set()
for text, _i, _s, _k, _w in PII:
    kinds.update(s["kind"] for s in p.mask_text(text)[1])
report(kinds >= {"id_number", "phone", "email", "record_number", "numeric_id"},
       f"the rewrite set covers all five A7 classes, saw {sorted(kinds)}")

# --------------------------------------------------------------------------- #
# C. the ASYMMETRY itself — detect wide, rewrite narrow.
#    This is the assertion that stops someone "simplifying" the two sets back into one.
# --------------------------------------------------------------------------- #
for text, why in [("淀粉酶 105 350 1200", "the amylase row"),
                  ("+1 415 555 0132", "a separated E.164 number"),
                  ("(415) 555-0132", "a US-format phone")]:
    detected = p.scan_line(text)
    masked, _ = p.mask_text(text)
    report(bool(detected), f"DETECTED by scan_line: {why} (a human still gets told)")
    report(masked == text, f"…but NOT rewritten by mask_text: {why}")

report(len(p._MASK_PATTERNS) < len(p._STANDALONE),
       f"the rewrite set is strictly narrower than the detect set "
       f"({len(p._MASK_PATTERNS)} vs {len(p._STANDALONE)} patterns)")

# multi-line input keeps its line accounting, and an overlapping match (an 18-digit ID is
# also a ≥11-digit run) is merged into ONE span so no half-masked identifier can ship.
multi = "WBC 3.21\n身份证 110101199003072316\nKi-67 30%\n"
masked, spans = p.mask_text(multi)
report(masked.splitlines()[0] == "WBC 3.21" and masked.splitlines()[2] == "Ki-67 30%",
       "in a multi-line body only the offending line is rewritten")
report(masked.endswith("\n"), "a trailing newline is preserved (no silent file-shape change)")
report(len(spans) == 1 and spans[0]["line"] == 2 and spans[0]["len"] == 18,
       f"overlapping id_number/numeric_id matches merge into one 18-char span, got {spans}")

print("\n".join(results))
PYEOF

while IFS=$'\t' read -r verdict label; do
  [ -z "${verdict:-}" ] && continue
  if [ "$verdict" = "OK" ]; then ok "$label"; else no "$label"; fi
done < "$tmp/results.tsv"

# ===========================================================================
# D. the rationale is written down where the next editor will read it
# ===========================================================================
echo "=== D. the narrowing is documented in the script, not just in a spec file ==="

says() {  # <grep-pattern> <label>
  grep -q "$1" "$ORG/scripts/pii_rescan.py" \
    && ok "$2" || no "$2 — not found in pii_rescan.py"
}
says "淀粉酶 105 350 1200" "the amylase regression is named verbatim in the source"
says "DETECT-ONLY\|detect set\|DETECT set" "the detect-vs-rewrite split is stated"
says "Telomere length" "the telomere over-rewrite that motivated dropping the 'tel' key is recorded"
says "住院号" "the label-anchored record-number rule is present"

# ---------------------------------------------------------------------------
echo
echo "== mask-text-clinical: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
