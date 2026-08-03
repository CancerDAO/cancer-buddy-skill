#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/library_resolve.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/lib/guidelines" "$tmp/lib/literature" "$tmp/outside" "$tmp/patient/library"
printf 'registered\n' > "$tmp/lib/guidelines/good.md"
printf 'orphan\n' > "$tmp/lib/literature/unregistered.md"
printf 'secret\n' > "$tmp/outside/secret.txt"
ln -s "$tmp/outside/secret.txt" "$tmp/lib/guidelines/escaping-link.md"
ln -s "$tmp/outside" "$tmp/lib/escaping-dir"

cat > "$tmp/lib/index.json" <<'JSON'
{
  "schema_version": 1,
  "entries": [
    {
      "file": "guidelines/good.md",
      "title": "registered entry",
      "publisher": "Test Publisher",
      "version": "v1",
      "date": "2026-01-01",
      "retrieved_at": "2026-01-02",
      "lang": "zh",
      "redistribution": "allowed",
      "patient_scope": "general"
    },
    {
      "file": "../../../etc/passwd",
      "title": "path escape",
      "publisher": "attacker",
      "version": "v1",
      "date": "2026-01-01",
      "retrieved_at": "2026-01-02",
      "lang": "zh",
      "redistribution": "allowed",
      "patient_scope": "general"
    },
    {
      "file": "guidelines/escaping-link.md",
      "title": "symlink escape",
      "publisher": "attacker",
      "version": "v1",
      "date": "2026-01-01",
      "retrieved_at": "2026-01-02",
      "lang": "zh",
      "redistribution": "allowed",
      "patient_scope": "general"
    },
    {
      "file": "escaping-dir/secret.txt",
      "title": "symlinked directory escape",
      "publisher": "attacker",
      "version": "v1",
      "date": "2026-01-01",
      "retrieved_at": "2026-01-02",
      "lang": "zh",
      "redistribution": "allowed",
      "patient_scope": "general"
    }
  ]
}
JSON

# ---------------------------------------------------------------- module level
python3 - "$SCRIPT" "$tmp" <<'PY'
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location("library_resolve", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tmp = pathlib.Path(sys.argv[2])
root = (tmp / "lib").resolve()

real = module.resolve_entry_path(root, "guidelines/good.md")
assert real == (root / "guidelines/good.md").resolve(), real

unsafe = [
    "../../../etc/passwd",          # relative escape
    "/etc/passwd",                  # absolute path
    "guidelines/../../outside/secret.txt",
    "guidelines/escaping-link.md",  # symlinked file
    "escaping-dir/secret.txt",      # symlinked directory in the middle
    "guidelines",                   # directory, not a file
    "guidelines/missing.md",        # registered but absent
    "index.json",                   # housekeeping file
    "",                             # empty
    ".",
]
for candidate in unsafe:
    try:
        module.resolve_entry_path(root, candidate)
    except module.LibraryPathError:
        pass
    else:
        raise AssertionError(f"unsafe entry accepted: {candidate!r}")

# trust_tier is positional and cannot be raised by anything in the file
assert module.LAYER_TRUST_TIER == {"L1": "curated", "L2": "user_supplied", "L3": "user_supplied"}

info = module.describe_layer("L2", root)
assert info["registered_files"] == ["guidelines/good.md"], info["registered_files"]
assert len(info["unsafe_entries"]) == 3, info["unsafe_entries"]
assert "literature/unregistered.md" in info["orphan_files"], info["orphan_files"]
assert "guidelines/good.md" not in info["orphan_files"]
assert info["trust_tier"] == "user_supplied"

print("library-resolve module checks OK")
PY

# ------------------------------------------------------------------- CLI level
set +e
CANCER_BUDDY_GUIDELINES="$tmp/lib" python3 "$SCRIPT" --layer L2 > "$tmp/out.json" 2> "$tmp/err.txt"
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "FAIL: index with an escaping entry must exit non-zero" >&2
  exit 1
fi

python3 - "$tmp/out.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
layer = payload["layers"][0]
assert layer["layer"] == "L2"
assert layer["exists"] is True
assert layer["index_exists"] is True
assert payload["unsafe_entry_total"] == 3, payload["unsafe_entry_total"]
assert payload["orphan_total"] >= 1, payload["orphan_total"]
reasons = " ".join(item["reason"] for item in layer["unsafe_entries"])
assert "unsafe library path" in reasons, reasons
assert "symbolic links are not usable" in reasons, reasons
assert "escapes library root" in reasons, reasons
PY

# L3 resolution follows the patient directory; L1 stays product-owned.
CANCER_BUDDY_GUIDELINES="$tmp/lib" CANCER_BUDDY_L1_LIBRARY="$tmp/l1" \
  python3 "$SCRIPT" --patient-dir "$tmp/patient" --layer L3 --layer L1 > "$tmp/roots.json"
python3 - "$tmp/roots.json" "$tmp" <<'PY'
import json
import pathlib
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
tmp = pathlib.Path(sys.argv[2]).resolve()
by_layer = {item["layer"]: item for item in payload["layers"]}
assert payload["search_order"] == ["L3", "L1"], payload["search_order"]
assert pathlib.Path(by_layer["L3"]["root"]) == tmp / "patient" / "library"
assert by_layer["L3"]["trust_tier"] == "user_supplied"
assert by_layer["L1"]["trust_tier"] == "curated"
assert by_layer["L1"]["exists"] is False
PY

echo "library-resolve boundary checks OK"
