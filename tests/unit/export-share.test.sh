#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/export_share.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/patient/raw" "$tmp/patient/04_docs" \
         "$tmp/patient/raw/transcript/s001" "$tmp/patient/raw/_cache/transcripts" \
         "$tmp/patient/15_未分类资料/肠道菌群检测"
: > "$tmp/patient/profile.json"
: > "$tmp/patient/04_docs/report.md"
: > "$tmp/patient/raw/original.pdf"
: > "$tmp/patient/raw/transcript/s001/page-001.md"
: > "$tmp/patient/raw/_cache/transcripts/abc.3.0.m.md"
: > "$tmp/patient/15_未分类资料/肠道菌群检测/report.md"
: > "$tmp/patient/15_未分类资料/肠道菌群检测/original.pdf"
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


def refused(paths, *, include_unclassified=False):
    """Return the refusal message, or raise if the path was ACCEPTED."""
    try:
        module._resolve_includes(root, paths, include_unclassified=include_unclassified)
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"export accepted {paths} (include_unclassified={include_unclassified})")


# organize v3 — the two highest-value plaintext surfaces in the archive. Both sit
# under raw/, but they are named explicitly so that a future refactor loosening the
# `raw` rule still trips over them, and so the operator gets a refusal that says what
# it actually refused. An export is precisely the boundary they must never cross.
msg = refused(["raw/transcript/s001/page-001.md"])
assert "raw/transcript/" in msg, msg
assert "unmasked" in msg, msg
msg = refused(["raw/_cache/transcripts/abc.3.0.m.md"])
assert "raw/_cache/" in msg, msg
assert "cache is not a deliverable" in msg, msg

# 15_ — the OPEN archive. Its .md sidecars are masked like any other, so the reason it
# is withheld is not privacy, it is purpose limitation: open-world material is by
# definition the material nobody classified, so its relevance to THIS export's declared
# purpose has not been established. Shipping it by reflex widens a purpose-limited
# export into a dump.
open_md = "15_未分类资料/肠道菌群检测/report.md"
msg = refused([open_md])
assert "excluded by default" in msg, msg
assert "--include-unclassified" in msg, msg

# …and it is a DELIBERATE, recorded act to turn it on.
selected = module._resolve_includes(root, [open_md], include_unclassified=True)
assert [rel.as_posix() for rel, _ in selected] == [open_md], selected

# even opted in, only the MASKED .md sidecar is exportable — the original stays in raw/
msg = refused(["15_未分类资料/肠道菌群检测/original.pdf"], include_unclassified=True)
assert "only the masked .md sidecar" in msg, msg

# the default must not have flipped: a pinned clinical domain needs no opt-in
selected = module._resolve_includes(root, ["04_docs/report.md"])
assert [rel.as_posix() for rel, _ in selected] == ["04_docs/report.md"]

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

print("export-share allowlist checks OK (incl. raw/transcript, raw/_cache, 15_ opt-in)")
PY
