#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/library_verify.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

TODAY="2026-08-03"

# ---------------------------------------------------------------- L2 fixture
mkdir -p "$tmp/l2/guidelines" "$tmp/l2/literature" "$tmp/outside"
printf 'current guideline\n' > "$tmp/l2/guidelines/current.md"
printf 'old guideline\n' > "$tmp/l2/guidelines/stale.md"
printf 'placeholder version\n' > "$tmp/l2/guidelines/placeholder.md"
printf 'expired\n' > "$tmp/l2/guidelines/expired.md"
printf 'nobody registered me\n' > "$tmp/l2/literature/orphan.md"
printf '住院号：Z0012345 患者姓名：张三\n' > "$tmp/l2/literature/leaky.md"
printf 'secret\n' > "$tmp/outside/secret.txt"
ln -s "$tmp/outside/secret.txt" "$tmp/l2/guidelines/escaping-link.md"

cat > "$tmp/l2/index.json" <<'JSON'
{
  "schema_version": 1,
  "entries": [
    {"file": "guidelines/current.md", "title": "current", "publisher": "Pub", "version": "2026.v1",
     "date": "2026-01-01", "retrieved_at": "2026-01-02", "lang": "zh",
     "redistribution": "allowed", "patient_scope": "general"},
    {"file": "guidelines/stale.md", "title": "stale", "publisher": "Pub", "version": "2015.v1",
     "date": "2015-01-01", "retrieved_at": "2015-01-02", "lang": "zh",
     "redistribution": "allowed", "patient_scope": "general"},
    {"file": "guidelines/placeholder.md", "title": "placeholder", "publisher": "Pub", "version": "待填",
     "date": "2026-01-01", "retrieved_at": "2026-01-02", "lang": "zh",
     "redistribution": "restricted", "patient_scope": "general"},
    {"file": "guidelines/expired.md", "title": "expired", "publisher": "Pub", "version": "2026.v1",
     "date": "2026-01-01", "retrieved_at": "2026-01-02", "expires_at": "2026-03-01", "lang": "zh",
     "redistribution": "allowed", "patient_scope": "general"},
    {"file": "guidelines/gone.md", "title": "listed but missing", "publisher": "Pub", "version": "2026.v1",
     "date": "2026-01-01", "retrieved_at": "2026-01-02", "lang": "zh",
     "redistribution": "allowed", "patient_scope": "general"},
    {"file": "../../../etc/passwd", "title": "path escape", "publisher": "attacker", "version": "v1",
     "date": "2026-01-01", "retrieved_at": "2026-01-02", "lang": "zh",
     "redistribution": "allowed", "patient_scope": "general"},
    {"file": "guidelines/escaping-link.md", "title": "symlink escape", "publisher": "attacker",
     "version": "v1", "date": "2026-01-01", "retrieved_at": "2026-01-02", "lang": "zh",
     "redistribution": "allowed", "patient_scope": "general"},
    {"file": "literature/leaky.md", "title": "cross-patient entry with a record number",
     "publisher": "Pub", "version": "v1", "date": "2026-01-01", "retrieved_at": "2026-01-02",
     "lang": "zh", "redistribution": "allowed", "patient_scope": "general"}
  ]
}
JSON

set +e
CANCER_BUDDY_GUIDELINES="$tmp/l2" python3 "$SCRIPT" --layer L2 --today "$TODAY" \
  --out "$tmp/verified_entries.json" > "$tmp/l2.out" 2> "$tmp/l2.err"
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "FAIL: a library holding an escaping entry and a scope violation must exit non-zero" >&2
  exit 1
fi
grep -q "patient-identifying content" "$tmp/l2.err" || {
  echo "FAIL: scope violation not reported on stderr" >&2; exit 1; }

python3 - "$tmp/verified_entries.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
layer = payload["layers"][0]
verified = {entry["file"] for entry in layer["verified_entries"]}
assert verified == {"guidelines/current.md"}, verified

for entry in layer["verified_entries"]:
    assert entry["trust_tier"] == "user_supplied", entry
    assert entry["layer"] == "L2"

rejected = {item["file"]: " ".join(item["reasons"]) for item in layer["rejected_entries"]}
assert "stale" in rejected["guidelines/stale.md"], rejected["guidelines/stale.md"]
assert "placeholder" in rejected["guidelines/placeholder.md"], rejected["guidelines/placeholder.md"]
assert "expired on" in rejected["guidelines/expired.md"], rejected["guidelines/expired.md"]
assert "does not exist" in rejected["guidelines/gone.md"], rejected["guidelines/gone.md"]
assert "unsafe library path" in rejected["../../../etc/passwd"], rejected["../../../etc/passwd"]
assert "symbolic links" in rejected["guidelines/escaping-link.md"], rejected["guidelines/escaping-link.md"]
assert "patient-identifying" in rejected["literature/leaky.md"], rejected["literature/leaky.md"]

assert "literature/orphan.md" in layer["orphan_files"], layer["orphan_files"]
assert "guidelines/current.md" not in layer["orphan_files"]
assert payload["scope_violation_total"] == 1, payload["scope_violation_total"]
violation = layer["scope_violations"][0]
assert "medical_record_no" in violation["matched"], violation
assert "L3" in violation["action"], violation
PY

# ---------------------------------------- L1 redistribution + self-declared tier
mkdir -p "$tmp/l1/datasets"
printf '{"a": 1}\n' > "$tmp/l1/datasets/facts.jsonl"
cat > "$tmp/l1/index.json" <<'JSON'
{
  "schema_version": 1,
  "entries": [
    {"file": "datasets/facts.jsonl", "title": "restricted in L1", "publisher": "Pub",
     "version": "v1", "date": "2026-01-01", "retrieved_at": "2026-07-01", "lang": "zh",
     "redistribution": "restricted", "patient_scope": "general", "trust_tier": "curated"}
  ]
}
JSON

set +e
CANCER_BUDDY_L1_LIBRARY="$tmp/l1" python3 "$SCRIPT" --layer L1 --today "$TODAY" \
  --out "$tmp/l1_verified.json" > "$tmp/l1.out" 2> "$tmp/l1.err"
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "FAIL: L1 must reject a non-allowed redistribution and a self-declared trust_tier" >&2
  exit 1
fi

python3 - "$tmp/l1_verified.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
layer = payload["layers"][0]
assert layer["verified_entries"] == [], layer["verified_entries"]
reasons = " ".join(layer["rejected_entries"][0]["reasons"])
assert "redistribution: allowed" in reasons, reasons
schema_errors = " ".join(layer["errors"])
assert "trust_tier" in schema_errors, schema_errors
PY

# ---------------------------------------------- missing index.json / size caps
mkdir -p "$tmp/l3/library/other"
printf 'unregistered\n' > "$tmp/l3/library/other/loose.pdf"
python3 "$SCRIPT" --patient-dir "$tmp/l3" --layer L3 --today "$TODAY" --out "$tmp/l3.json" \
  > /dev/null 2> "$tmp/l3.err" && { echo "FAIL: missing index.json must exit non-zero" >&2; exit 1; }
python3 - "$tmp/l3.json" <<'PY'
import json
import sys

layer = json.load(open(sys.argv[1], encoding="utf-8"))["layers"][0]
assert layer["verified_entries"] == []
assert "other/loose.pdf" in layer["orphan_files"], layer["orphan_files"]
assert any("index.json is missing" in msg for msg in layer["errors"]), layer["errors"]
PY

set +e
CANCER_BUDDY_GUIDELINES="$tmp/l2" python3 "$SCRIPT" --layer L2 --today "$TODAY" \
  --max-entries 2 --out "$tmp/cap.json" > /dev/null 2> "$tmp/cap.err"
rc=$?
set -e
[ "$rc" -ne 0 ] || { echo "FAIL: --max-entries cap not enforced" >&2; exit 1; }
grep -q "exceeds --max-entries" "$tmp/cap.err" || { echo "FAIL: entry cap message missing" >&2; exit 1; }

set +e
CANCER_BUDDY_GUIDELINES="$tmp/l2" python3 "$SCRIPT" --layer L2 --today "$TODAY" \
  --max-total-bytes 1 --out "$tmp/bytes.json" > /dev/null 2> "$tmp/bytes.err"
rc=$?
set -e
[ "$rc" -ne 0 ] || { echo "FAIL: --max-total-bytes cap not enforced" >&2; exit 1; }
python3 - "$tmp/bytes.json" <<'PY'
import json
import sys

layer = json.load(open(sys.argv[1], encoding="utf-8"))["layers"][0]
assert layer["verified_entries"] == [], "byte cap must invalidate the whole layer"
PY

# -------------------------------------------------- symlinked / hard-linked bits
mkdir -p "$tmp/sym/lib"
printf '{"schema_version": 1, "entries": []}' > "$tmp/sym/elsewhere.json"
ln -s "$tmp/sym/elsewhere.json" "$tmp/sym/lib/index.json"
set +e
CANCER_BUDDY_GUIDELINES="$tmp/sym/lib" python3 "$SCRIPT" --layer L2 --today "$TODAY" \
  --out "$tmp/sym.json" > /dev/null 2> "$tmp/sym.err"
rc=$?
set -e
[ "$rc" -ne 0 ] || { echo "FAIL: a symlinked index.json must not be read" >&2; exit 1; }
grep -q "index.json is a symbolic link" "$tmp/sym.err" || {
  echo "FAIL: symlinked manifest not reported" >&2; exit 1; }

mkdir -p "$tmp/hard/lib/guidelines"
printf 'shared inode\n' > "$tmp/outside/hardlink-target.md"
ln "$tmp/outside/hardlink-target.md" "$tmp/hard/lib/guidelines/hard.md"
cat > "$tmp/hard/lib/index.json" <<'JSON'
{"schema_version": 1, "entries": [
  {"file": "guidelines/hard.md", "title": "hard link", "publisher": "Pub", "version": "v1",
   "date": "2026-01-01", "retrieved_at": "2026-07-01", "lang": "zh",
   "redistribution": "allowed", "patient_scope": "general"}
]}
JSON
CANCER_BUDDY_GUIDELINES="$tmp/hard/lib" python3 "$SCRIPT" --layer L2 --today "$TODAY" \
  --out "$tmp/hard.json" > /dev/null 2>&1 || true
python3 - "$tmp/hard.json" <<'PY'
import json
import sys

layer = json.load(open(sys.argv[1], encoding="utf-8"))["layers"][0]
assert layer["verified_entries"] == [], layer["verified_entries"]
assert "hard-linked" in " ".join(layer["rejected_entries"][0]["reasons"])
PY

# ------------------------------------------- fallback validator (no jsonschema)
python3 - "$SCRIPT" <<'PY'
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("library_verify", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

schema = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
good = {
    "entries": [
        {"file": "a.md", "title": "t", "publisher": "p", "version": "v", "date": "2026-01-01",
         "retrieved_at": "2026-01-01", "lang": "zh", "redistribution": "allowed",
         "patient_scope": "general"}
    ]
}
assert module._fallback_validate(good, schema) == []

bad = json.loads(json.dumps(good))
bad["entries"][0]["trust_tier"] = "curated"
bad["entries"][0]["redistribution"] = "public-domain"
del bad["entries"][0]["retrieved_at"]
errors = " ".join(module._fallback_validate(bad, schema))
assert "trust_tier" in errors and "assigned by layer position" in errors, errors
assert "redistribution" in errors, errors
assert "retrieved_at" in errors, errors
print("library-verify fallback validator OK")
PY

echo "library-verify reconciliation checks OK"
