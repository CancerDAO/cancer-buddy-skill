#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/export_share.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/patient/raw" "$tmp/patient/04_docs"
: > "$tmp/patient/profile.json"
: > "$tmp/patient/04_docs/report.md"
: > "$tmp/patient/raw/original.pdf"
ln -s "$tmp/patient/raw" "$tmp/patient/raw_link"

python3 - "$SCRIPT" "$tmp/patient" <<'PY'
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = pathlib.Path(sys.argv[2]).resolve()

selected = module._resolve_includes(root, ["profile.json", "04_docs/report.md"])
assert [rel.as_posix() for rel, _ in selected] == ["profile.json", "04_docs/report.md"]

for unsafe in (["raw"], ["../escape"], ["raw_link"], ["04_docs"]):
    try:
        module._resolve_includes(root, unsafe)
    except ValueError:
        pass
    else:
        raise AssertionError(f"unsafe selection accepted: {unsafe}")

rc = module.export_share(
    root,
    root.parent / "empty-auth",
    ["profile.json"],
    recipient="",
    purpose="test",
    expires_at="2099-01-01T00:00:00Z",
    authorization_ref="auth-1",
)
assert rc == 2

rc = module.export_share(
    root,
    root / "nested-export",
    ["profile.json"],
    recipient="recipient",
    purpose="test",
    expires_at="2099-01-01T00:00:00Z",
    authorization_ref="auth-1",
)
assert rc == 2

print("export-share allowlist checks OK")
PY
