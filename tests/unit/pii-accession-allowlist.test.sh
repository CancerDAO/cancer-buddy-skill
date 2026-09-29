#!/usr/bin/env bash
# pii_rescan.py: sequence-database accessions (Ensembl / RefSeq / LRG / COSMIC / dbSNP) are
# clinical content, not identifiers. The letter-prefixed token is masked before the shape
# scan, so an NGS variant line cannot fail the sidecar gate (phase1 §9.1 forbids masking
# it), while a bare phone / ID-number digit run on the same line — or behind a fake prefix —
# still fires. All values synthetic.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import sys
repo = sys.argv[1]
sys.path.insert(0, repo + "/skills/cancer-buddy-organize/scripts")
import pii_rescan as pr

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


clean = [
    "KRAS NM_004985.5 ENST00000311936.8 c.35G>A p.(G12D)",
    "CHEK2 ENST00000404276.6 c.592+3A>T",
    "translation dropped a digit: ENST0000040276.6",
    "gene ENSG00000133703 protein ENSP00000256078.4",
    "NC_000012.12:g.25245350C>T LRG_344t1",
    "COSV55497369 COSM521 rs121913529",
]
for line in clean:
    res = pr.scan_line(line)
    check(f"accession line does not fire: {line!r}", res == [], str(res))

fire = {
    "bare 11-digit lab id still fires": "检验号 24080800634",
    "phone beside an accession still fires": "ENST00000311936.8 联系电话 13812345678",
    "fake prefix glued to digits is not an accession": "XENST00000311936",
    "prefix with too few digits is not an accession": "ENST01 13812345678",
}
for label, line in fire.items():
    res = pr.scan_line(line)
    check(label, res != [], str(res))

print(f"pii-accession-allowlist: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
