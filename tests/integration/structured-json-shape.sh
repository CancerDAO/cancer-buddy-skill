#!/usr/bin/env bash
# Guard against the recurring "a consumer doc shows a structured-JSON file with a
# retired/non-canonical SHAPE that contradicts its schema" class (e.g. the vault
# data-vault.md timeline.json block that used the flat version/patient_id/documents
# shape instead of the canonical patient_code/schema_version/events[].source_refs[]).
#
# For every schemas/*.schema.json with "additionalProperties": false (a CLOSED shape),
# find ```json code blocks in skills/**.md + references/*.md + *.html that sit under a
# heading naming that file (e.g. "## ... timeline.json ...") and assert the block's
# top-level keys are all allowed by the schema. Heading-anchored association keeps the
# check high-precision (no false failures on correct examples under other headings).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import json, re, glob, os, sys
root = sys.argv[1]
os.chdir(root)

# closed structured-JSON schemas → allowed top-level property names
closed = {}
for sp in glob.glob("skills/cancer-buddy-organize/references/schemas/*.schema.json"):
    sc = json.load(open(sp))
    if sc.get("additionalProperties", True) is False:
        name = os.path.basename(sp).replace(".schema.json", ".json")
        closed[name] = set((sc.get("properties") or {}).keys())

files = [f for f in (glob.glob("skills/**/*.md", recursive=True)
                     + glob.glob("references/*.md")
                     + glob.glob("skills/**/*.html", recursive=True))
         if "/docs/superpowers/" not in f]
fence = re.compile(r'```json\s*\n(.*?)```', re.DOTALL)
namepat = re.compile(r'\b([a-z_]+\.json)\b')
strip = lambda s: re.sub(r'//[^\n]*', '', s)

errs = 0
for f in files:
    txt = open(f, encoding="utf-8", errors="replace").read()
    lines = txt.splitlines()
    for m in fence.finditer(txt):
        start = txt[:m.start()].count("\n")
        # nearest preceding HEADING line that names a closed-schema file (lookback 12)
        target = None
        for ln in range(start - 1, max(-1, start - 12), -1):
            if ln < 0:
                break
            if lines[ln].lstrip().startswith("#"):
                hit = [n for n in namepat.findall(lines[ln]) if n in closed]
                if hit:
                    target = hit[-1]
                    break
        if not target:
            continue
        try:
            obj = json.loads(strip(m.group(1)))
        except Exception:
            continue  # illustrative/partial snippet, not strict JSON — skip
        if not isinstance(obj, dict):
            continue
        unknown = sorted(set(obj.keys()) - closed[target])
        if unknown:
            print(f"FAIL: {f}:{start+1} json block under a '{target}' heading uses keys "
                  f"the schema forbids (additionalProperties:false): {unknown}", file=sys.stderr)
            errs += 1

if errs:
    print(f"{errs} structured-json-shape violation(s)", file=sys.stderr)
    sys.exit(1)
print("structured-json shapes consistent with closed schemas")
PY
