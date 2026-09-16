#!/usr/bin/env bash
# tests/unit/transcribe-prompt-example.test.sh — organize v3 fix spec B17 (the P1-5
# regression G3 fixed).
#
# 段 1 is the ONE model call in the pipeline, and the only thing the model is given about
# the output format is the worked example in `organizer-prompt-phase1-transcribe.md`. It
# copies that example's shape. `ingest_transcripts.parse_frontmatter` then parses the
# result with a deliberately small hand-rolled YAML subset — scalars, plus four keys
# whose values must be STRICT JSON literals — because full YAML on model-written text is
# a parsing surface untrusted input should not get.
#
# Those two facts make the prompt's example load-bearing in a way documentation usually
# is not: if the example shows `fields: [白细胞计数, 报告日期]`, the model writes exactly
# that, `json.loads` refuses it, and EVERY page of the run is rejected as invalid. The
# failure is total, it looks like a model failure rather than a prompt failure, and the
# obvious "fix" is to loosen the parser — which hands YAML's implicit typing (a gene
# symbol NA becoming null, an accession `1:30` becoming a sexagesimal int) the one
# surface the strict subset was written to keep it away from.
#
# So this file does not read the prompt for prose. It EXTRACTS the example frontmatter
# blocks out of the three documents that hand a model or an integrator a shape, and runs
# each one through the real `parse_frontmatter` + `validate_frontmatter`, demanding zero
# errors. The documentation is treated as executable input, because for 段 1 it is.
#
# Three things keep this from being a gate that passes by doing nothing:
#
#   * the extractor must find at least one block, and at least one LITERAL block. An
#     extractor whose regex silently stops matching reports "0 examples, 0 failures" —
#     which is the exact shape of a green test that checks nothing — so finding nothing
#     is a FAILURE here, not a pass.
#   * the negative arm feeds the same two functions a block written the way the P1-5
#     regression was written (bare-word lists, a YAML block sequence, an inline comment,
#     an angle-bracket placeholder in a token field). If those do NOT error, the positive
#     arm proved only that the functions are permissive.
#   * a block may be a deliberate SHAPE SKETCH (`<…>` placeholders, `…`, `# ` notes) —
#     `runtime-bindings/_template.md` has one on purpose. A sketch is exempt from
#     parsing, but ONLY if the document says so within sight of the block. An unlabelled
#     sketch is indistinguishable from a copyable example, and that is how P1-5 got in.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

DOCS=(
  "$ORG/references/organizer-prompt-phase1-transcribe.md"
  "$ORG/references/organizer-prompt-second-read.md"
  "$ORG/references/runtime-bindings/_template.md"
)

echo "=== 0. the three documents exist ==="
for d in "${DOCS[@]}"; do
  [ -f "$d" ] && ok "present: ${d#$ORG/}" || no "missing: ${d#$ORG/}"
done
(( fail == 0 )) || { echo; echo "== transcribe-prompt-example: $pass passed, $fail failed =="; exit 1; }

# ===========================================================================
# A. every LITERAL frontmatter example in the three docs parses and validates
# ===========================================================================
echo "=== A. example frontmatter blocks vs. the real parser ==="

# Written to a file, not piped through `python3 - <<EOF` inside `$(…)`: the extractor
# has to match markdown fences, and bash re-scans a heredoc nested in a command
# substitution for backquote substitution even when the delimiter is quoted — which
# would quietly rewrite the fence pattern and make the sweep find nothing.
cat > "$tmp/extract.py" <<'PYEOF'
import importlib, pathlib, re, sys, textwrap

ORG, DOCS = sys.argv[1], sys.argv[2:]
sys.path.insert(0, ORG + "/scripts")
it = importlib.import_module("ingest_transcripts")

# the two functions this gate exists to run the docs through — assert they are the real
# ones before trusting a green result off them
for fn in ("parse_frontmatter", "validate_frontmatter"):
    assert callable(getattr(it, fn, None)), f"ingest_transcripts has no {fn}()"

FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+-]*)[ \t]*$")

def code_blocks(path):
    """Yield (line_no, lang, dedented_body) for every fenced block, and for every
    standalone `---` block outside a fence. Broad on purpose: the filter that picks
    page-frontmatter examples out of these is stated separately, below."""
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    i, n = 0, len(lines)
    while i < n:
        m = FENCE.match(lines[i])
        if m:
            fence, lang = m.group(2), m.group(3)
            body, j = [], i + 1
            while j < n:
                m2 = FENCE.match(lines[j])
                if m2 and m2.group(2)[0] == fence[0] and len(m2.group(2)) >= len(fence) \
                   and not m2.group(3):
                    break
                body.append(lines[j]); j += 1
            yield i + 1, lang or "", textwrap.dedent("\n".join(body))
            i = j + 1
            continue
        if lines[i].rstrip() == "---":
            j = i + 1
            body = []
            while j < n and lines[j].rstrip() != "---":
                body.append(lines[j]); j += 1
            if j < n:
                yield i + 1, "<bare>", "---\n" + "\n".join(body) + "\n---\n"
                i = j + 1
                continue
        i += 1

# A block counts as a PAGE-FRONTMATTER EXAMPLE when it is a `--- … ---` block that
# declares `source_id`. That filter is what separates the 段 1 page contract from a
# document's own metadata header and from the 段 1.5 JSON packets.
SKETCH_MARKS = (
    ("angle-bracket placeholder", re.compile(r"<[^>\n]{1,60}>")),
    ("ellipsis placeholder",      re.compile(r"(?<![.\d])\.\.\.(?!\d)|…")),
    ("inline # comment",          re.compile(r"\S[ \t]+#[ \t]")),
)
DISCLAIMERS = ("不是可照抄", "shape sketch", "占位符", "placeholder", "not a copyable")

candidates = literal = sketches = 0
problems = []
per_doc = {}

for doc in DOCS:
    rel = doc.split("/skills/cancer-buddy-organize/")[-1]
    doc_lines = pathlib.Path(doc).read_text(encoding="utf-8").splitlines()
    per_doc[rel] = {"candidates": 0, "literal": 0, "sketch": 0}
    for lineno, lang, body in code_blocks(doc):
        b = body.strip()
        if not b.startswith("---"):
            continue
        if not re.search(r"^[ \t]*source_id[ \t]*:", b, re.M):
            continue          # a doc's own metadata header, not a page example
        candidates += 1
        per_doc[rel]["candidates"] += 1
        marks = [name for name, rx in SKETCH_MARKS if rx.search(b)]
        if marks:
            sketches += 1
            per_doc[rel]["sketch"] += 1
            # exempt from parsing — but only if the document SAYS it is a sketch
            window = "\n".join(doc_lines[max(0, lineno - 13):lineno])
            if not any(d in window for d in DISCLAIMERS):
                problems.append(
                    f"{rel}:{lineno}: an unlabelled shape sketch ({', '.join(marks)}). "
                    "A block that looks like an example and cannot be copied must say so "
                    "within sight of itself, or a model will copy it")
            continue
        literal += 1
        per_doc[rel]["literal"] += 1
        text = b if b.endswith("\n") else b + "\n"
        fm, _body, err = it.parse_frontmatter(text)
        if err:
            problems.append(f"{rel}:{lineno}: parse_frontmatter rejected the example — {err}")
            continue
        errs = it.validate_frontmatter(fm, None, None)
        if errs:
            problems.append(f"{rel}:{lineno}: validate_frontmatter rejected the example — "
                            + "; ".join(errs))

for rel, c in per_doc.items():
    print(f"  · {rel}: candidates={c['candidates']} literal={c['literal']} sketch={c['sketch']}")

assert candidates >= 1, (
    "the extractor found NO frontmatter example in any of the three documents. That is a "
    "failure, not a pass: a gate that inspects nothing reports the same green as a gate "
    "that inspects everything")
assert literal >= 1, (
    f"the extractor found {candidates} example block(s) but classified every one as a "
    "shape sketch, so no block was ever handed to the parser — the gate proved nothing")
assert not problems, "\n".join("    " + p for p in problems)
print(f"OK: {literal} literal example(s) parsed + validated clean, "
      f"{sketches} labelled sketch(es) exempt, {candidates} candidate(s) total")
PYEOF
out="$(python3 "$tmp/extract.py" "$ORG" "${DOCS[@]}" 2>&1)"
rc=$?
echo "$out" | grep '^  ·'
[ "$rc" -eq 0 ] \
  && ok "every literal example frontmatter parses and validates with ZERO errors" \
  || no "an example frontmatter does not survive the real parser:
$out"
grep -q 'literal example(s) parsed' <<<"$out" \
  && ok "…and the extractor actually found ≥1 literal block (an empty sweep FAILS here)" \
  || no "the extractor found no literal block: $out"
grep -q 'sketch(es) exempt' <<<"$out" \
  && ok "…while declared shape sketches are exempt only where the doc labels them as such" \
  || no "sketch accounting missing: $out"

# ===========================================================================
# B. the 段 1.5 documents hand the model JSON, and it must be strict JSON too
# ===========================================================================
# organizer-prompt-second-read.md carries no page frontmatter at all — its examples are
# the request/response packets. Leaving it at "0 candidates, nothing to check" would make
# listing it here decorative, so the same rule is applied in its own format.
echo "=== B. json example blocks are strict JSON ==="
# Written to a file, not piped through `python3 - <<EOF` inside `$(…)`: this script has
# to match a markdown fence, and bash re-scans a heredoc nested in a command substitution
# for backquote substitution even when the delimiter is quoted.
cat > "$tmp/jsonblocks.py" <<'PYEOF'
import json, pathlib, re, sys
FENCE = "`" * 3
found = 0
bad = []
for doc in sys.argv[1:]:
    rel = doc.split("/skills/cancer-buddy-organize/")[-1]
    text = pathlib.Path(doc).read_text(encoding="utf-8")
    rx = re.compile(r"^" + FENCE + r"json[ \t]*\n(.*?)^" + FENCE + r"[ \t]*$", re.M | re.S)
    for m in rx.finditer(text):
        found += 1
        line = text[:m.start()].count("\n") + 1
        try:
            json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            bad.append(f"{rel}:{line}: json example block is not JSON — {exc}")
assert found >= 1, "no json example block found in any of the three documents"
assert not bad, "\n".join("    " + b for b in bad)
print(f"OK: {found} json example block(s) are strict JSON")
PYEOF
out="$(python3 "$tmp/jsonblocks.py" "${DOCS[@]}" 2>&1)"
[ $? -eq 0 ] && ok "every json example block in the three docs round-trips through json.loads" \
  || no "a json example block is not valid JSON:
$out"

# ===========================================================================
# C. negative arm — the same two functions DO reject the P1-5 spellings
# ===========================================================================
echo "=== C. the parser really rejects the loose spellings ==="

# The runner lives in its own file so the CALLER's heredoc is what reaches python's
# stdin — `python3 - <<EOF` would consume stdin for the script itself and hand the
# functions an empty document, which every one of them accepts.
cat > "$tmp/run_fm.py" <<'PYEOF'
import importlib, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
it = importlib.import_module("ingest_transcripts")
text = sys.stdin.read()
assert text.strip(), "no frontmatter reached the runner — the arm would prove nothing"
fm, _body, err = it.parse_frontmatter(text)
msgs = [err] if err else it.validate_frontmatter(fm, None, None)
for m in msgs:
    print(m)
sys.exit(1 if msgs else 0)
PYEOF

neg() {  # <name> <expected substring> <frontmatter on stdin>
  local name="$1" needle="$2"
  out="$(python3 "$tmp/run_fm.py" "$ORG" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    no "$name was ACCEPTED — the positive arm above proves nothing"
  else
    ok "$name is rejected"
    grep -q "$needle" <<<"$out" \
      && ok "…and the message names the defect ($needle)" \
      || no "$name rejected for the wrong reason: $out"
  fi
}

neg "a bare-word list (fields: [白细胞计数, 报告日期], the literal P1-5 spelling)" \
    "not valid JSON" <<'EOF'
---
source_id: "s003"
page: 7
text_layer_kind: "born_digital"
doc_kind: "检验报告"
clinical_class: "lab"
fields: [白细胞计数, 报告日期]
high_risk: ["白细胞计数"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.04
needs_rotation: false
prompt_version: "3.1"
model_id: "claude-opus-4-1"
---
EOF

neg "a YAML block sequence (high_risk: followed by '- ' items)" \
    "must be a list of field labels" <<'EOF'
---
source_id: "s003"
page: 7
text_layer_kind: "born_digital"
doc_kind: "检验报告"
clinical_class: "lab"
fields: []
high_risk:
  - 白细胞计数
uncertain: []
discrepancy: []
unreadable_ratio: 0.04
needs_rotation: false
prompt_version: "3.1"
model_id: "claude-opus-4-1"
---
EOF

neg "an inline '# ' comment after an enum value (the parser does not strip it)" \
    "closed routing enum" <<'EOF'
---
source_id: "s003"
page: 7
text_layer_kind: "born_digital"
doc_kind: "检验报告"
clinical_class: lab   # molecular|lab|imaging|…
fields: []
high_risk: []
uncertain: []
discrepancy: []
unreadable_ratio: 0.04
needs_rotation: false
prompt_version: "3.1"
model_id: "claude-opus-4-1"
---
EOF

neg "an angle-bracket placeholder left in model_id" \
    "not a safe filename token" <<'EOF'
---
source_id: "s003"
page: 7
text_layer_kind: "born_digital"
doc_kind: "检验报告"
clinical_class: "lab"
fields: []
high_risk: []
uncertain: []
discrepancy: []
unreadable_ratio: 0.04
needs_rotation: false
prompt_version: "3.1"
model_id: "<host-provided model id>"
---
EOF

# and the control: the SAME block, written the way B17 requires, is accepted — so the
# four rejections above are about the spelling and not about an unsatisfiable contract.
neg_control="$(python3 - "$ORG" <<'PYEOF' 2>&1
import importlib, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
it = importlib.import_module("ingest_transcripts")
text = '''---
source_id: "s003"
page: 7
text_layer_kind: "born_digital"
doc_kind: "检验报告"
clinical_class: "lab"
fields: [{"label": "白细胞计数", "value": "3.21", "unit": "10^9/L", "span": {"page": 7, "bbox": [0.184, 0.412, 0.397, 0.436]}}]
high_risk: ["白细胞计数"]
uncertain: []
discrepancy: []
unreadable_ratio: 0.04
needs_rotation: false
prompt_version: "3.1"
model_id: "claude-opus-4-1"
---
'''
fm, _b, err = it.parse_frontmatter(text)
assert err is None, err
errs = it.validate_frontmatter(fm, None, None)
assert not errs, errs
print("strict-literal control OK")
PYEOF
)"
[ $? -eq 0 ] \
  && ok "the strict-JSON-literal spelling of the same block IS accepted (control)" \
  || no "the contract the docs teach is unsatisfiable: $neg_control"

echo
echo "== transcribe-prompt-example: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
