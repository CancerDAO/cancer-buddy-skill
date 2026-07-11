#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
S="$ROOT/skills/cancer-buddy-organize/scripts/safe_extract_archive.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 - "$tmp" <<'PY'
import io, pathlib, stat, sys, tarfile, zipfile
p = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(p/'good.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('reports/a.txt', 'ok')
with zipfile.ZipFile(p/'traversal.zip', 'w') as z:
    z.writestr('../escape.txt', 'bad')
with zipfile.ZipFile(p/'symlink.zip', 'w') as z:
    i = zipfile.ZipInfo('link')
    i.create_system = 3
    i.external_attr = (stat.S_IFLNK | 0o777) << 16
    z.writestr(i, '/etc/passwd')
with zipfile.ZipFile(p/'ratio.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('zeros.bin', b'0' * 1024 * 1024)
with tarfile.open(p/'symlink.tar', 'w') as t:
    i = tarfile.TarInfo('link')
    i.type = tarfile.SYMTYPE
    i.linkname = '/etc/passwd'
    t.addfile(i)
PY

python3 "$S" "$tmp/good.zip" --out "$tmp/good-out" >/dev/null
[[ "$(cat "$tmp/good-out/reports/a.txt")" == "ok" ]]
[[ "$(stat -f '%Lp' "$tmp/good-out/reports/a.txt" 2>/dev/null || stat -c '%a' "$tmp/good-out/reports/a.txt")" == "600" ]]

if python3 "$S" "$tmp/traversal.zip" --out "$tmp/traversal-out" >/dev/null 2>&1; then
  echo "FAIL: traversal archive accepted" >&2; exit 1
fi
[[ ! -e "$tmp/escape.txt" ]]

if python3 "$S" "$tmp/symlink.zip" --out "$tmp/symlink-out" >/dev/null 2>&1; then
  echo "FAIL: ZIP symlink accepted" >&2; exit 1
fi
if python3 "$S" "$tmp/symlink.tar" --out "$tmp/tar-out" >/dev/null 2>&1; then
  echo "FAIL: TAR symlink accepted" >&2; exit 1
fi
if python3 "$S" "$tmp/ratio.zip" --out "$tmp/ratio-out" --max-ratio 2 >/dev/null 2>&1; then
  echo "FAIL: suspicious compression ratio accepted" >&2; exit 1
fi
mkdir "$tmp/existing"
if python3 "$S" "$tmp/good.zip" --out "$tmp/existing" >/dev/null 2>&1; then
  echo "FAIL: existing destination accepted" >&2; exit 1
fi

echo "safe-extract-archive: pass"
