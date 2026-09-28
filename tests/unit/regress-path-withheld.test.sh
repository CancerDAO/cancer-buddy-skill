#!/usr/bin/env bash
# tests/integration/organize-regress.sh prints counts only — never a caller-supplied archive path, which
# may embed a name. A missing real-archive directory is reported as "path withheld".
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
probe="/nonexistent/zz-name-probe-$$"
out="$(CB_REGRESS_CASES="probe=$probe" bash "$REPO_ROOT/tests/integration/organize-regress.sh" 2>&1)"
fail=0
grep -q "SKIP probe: not a directory (path withheld)" <<<"$out" || { echo "FAIL: skip line missing" >&2; fail=1; }
grep -q "zz-name-probe" <<<"$out" && { echo "FAIL: the archive path was printed" >&2; fail=1; }
echo "regress-path-withheld: $([ $fail -eq 0 ] && echo '2 passed, 0 failed' || echo 'failed')"
exit $fail
