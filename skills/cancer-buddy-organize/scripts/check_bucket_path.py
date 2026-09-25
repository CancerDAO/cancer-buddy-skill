#!/usr/bin/env python3
"""check_bucket_path.py — PRE-WRITE bucket whitelist check (O-09).

The terminal gate (`validate_structured_outputs.py::gate_bucket_taxonomy`) used to be
the only place a bucket name was checked, so an off-taxonomy folder such as
`14_患者自管补充/患者自述` or `03_病程与叙事文书/既往资料摘录` was created, filled, and
only rejected at the very end of a run. Phase 2 now calls this script BEFORE any
mkdir/move; the terminal gate imports the same function, so there is exactly one
whitelist implementation reading `references/bucket_taxonomy.json`.

Rules (deterministic, no medical judgement):
  * the first path segment must be a pinned `NN_` domain slug (zh or en form) or the
    pinned infra bucket `99_…`;
  * the second segment, when it is a directory, must be one of that domain's pinned
    sub-bucket slugs (zh or en), the universal fallback `其他/other`, or
    `conversation_notes` (段C notes are cross-domain, bucket-taxonomy.md); under the infra
    bucket `99_…` only its pinned children (high_confidence / uncertain). `raw` and `ocr` are
    top-level infrastructure only — never a sub-bucket of a clinical domain (originals live
    once in `<patient_dir>/raw/`);
  * no directory deeper than domain/sub-bucket;
  * a path whose last segment carries a file extension is a file: only its directory
    segments are checked (a file directly under a domain dir is allowed), and it must be a
    `.md` sidecar — an original (jpg / pdf / txt …) never lives in a bucket;
  * absolute paths, `..` segments and empty paths are rejected.

CLI:
    check_bucket_path.py <rel_path> [<rel_path> ...] [--json]
Exit codes: 0 = every path is on the whitelist; 1 = at least one violation
(each printed with the pinned slugs expected); 2 = bad invocation / taxonomy unreadable.

Importable:
    load_taxonomy(path=None) -> dict
    bucket_path_violation(rel_path, tax) -> str | None
    check_paths(paths, tax) -> list[tuple[str, str]]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_JSON = SKILL_ROOT / "references" / "bucket_taxonomy.json"
_DOMAIN_DIR_RE = re.compile(r"^\d{2}_")
_FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def load_taxonomy(path: Path | str | None = None) -> dict:
    p = Path(path) if path else TAXONOMY_JSON
    return json.loads(p.read_text(encoding="utf-8"))


def _index(tax: dict) -> dict:
    domain_by_slug: dict[str, dict] = {}
    expected_by_nn: dict[str, tuple[str, str]] = {}
    for d in tax.get("domains", []):
        domain_by_slug[d["zh"]] = d
        domain_by_slug[d["en"]] = d
        expected_by_nn[d["nn"]] = (d["zh"], d["en"])
    infra_top: dict[str, dict] = {}
    for ib in tax.get("infra_buckets", []):
        infra_top[ib["zh"]] = ib
        infra_top[ib["en"]] = ib
        expected_by_nn.setdefault(ib["nn"], (ib["zh"], ib["en"]))
    ascii_infra = set(tax.get("ascii_infra_dirs", []))
    fallback_subs: set[str] = set()
    for s in tax.get("universal_fallback_sub_buckets", []):
        fallback_subs.update((s["zh"], s["en"]))
    return {
        "domain_by_slug": domain_by_slug,
        "expected_by_nn": expected_by_nn,
        "infra_top": infra_top,
        "ascii_infra": ascii_infra,
        "fallback_subs": fallback_subs,
    }


# The only ASCII infra dir allowed as a sub-bucket of a CLINICAL domain: 段C conversation notes
# are filed under the conversation_notes/ of their clinical domain (bucket-taxonomy.md). raw/ and
# ocr/ are top-level infrastructure; high_confidence/ and uncertain/ are the 99_ quarantine's own
# children (bucket_taxonomy.json infra_buckets[].sub_buckets_ascii).
DOMAIN_ASCII_SUBS = frozenset({"conversation_notes"})
MAX_BUCKET_DEPTH = 2  # <NN_domain>/<sub-bucket>


def allowed_sub_buckets(domain: dict, tax: dict) -> set[str]:
    idx = _index(tax)
    allowed: set[str] = set()
    for s in domain.get("sub_buckets", []):
        allowed.update((s["zh"], s["en"]))
    return allowed | idx["fallback_subs"] | (idx["ascii_infra"] & DOMAIN_ASCII_SUBS)


def top_level_violation(name: str, tax: dict) -> str | None:
    """Violation text for a top-level `NN_` directory name, or None when pinned."""
    idx = _index(tax)
    if name in idx["domain_by_slug"] or name in idx["infra_top"]:
        return None
    nn = name[:2]
    hint = idx["expected_by_nn"].get(nn)
    if hint:
        zh, en = hint
        expect = f"expected the pinned {nn}_ domain slug '{zh}' (en: '{en}')"
    else:
        expect = (
            f"'{nn}_' is not a pinned domain number — valid domains are 01_..14_ "
            "(see bucket_taxonomy.json); re-file its contents onto the correct "
            "clinical domain"
        )
    return f"top-level dir '{name}' is not a pinned domain slug; {expect}"


def sub_bucket_violation(domain_name: str, sub: str, tax: dict) -> str | None:
    """Violation text for `<domain_name>/<sub>` (sub is a directory), or None."""
    idx = _index(tax)
    if domain_name in idx["domain_by_slug"]:
        domain = idx["domain_by_slug"][domain_name]
        if sub in allowed_sub_buckets(domain, tax):
            return None
        zh = domain["zh"]
        return (
            f"{domain_name}/{sub} is not a pinned sub-bucket of {zh}; re-file onto a "
            f"pinned slug from bucket_taxonomy.json (domain {domain['nn']} pinned "
            f"sub-buckets: {', '.join(s['zh'] for s in domain.get('sub_buckets', []))}) "
            f"or the fallback 其他/other"
        )
    if domain_name in idx["infra_top"]:
        ib = idx["infra_top"][domain_name]
        allowed = set(ib.get("sub_buckets_ascii", []))
        if sub in allowed:
            return None
        return (
            f"{domain_name}/{sub} is not a pinned child of infra bucket {ib['zh']} "
            f"(allowed: {', '.join(sorted(allowed))})"
        )
    return top_level_violation(domain_name, tax)


def bucket_path_violation(rel_path: str, tax: dict) -> str | None:
    """Return a violation message for a bucket-relative path, or None when allowed."""
    if not isinstance(rel_path, str) or not rel_path.strip():
        return "empty bucket path"
    raw = rel_path.strip()
    if raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return f"{raw}: absolute paths are not bucket paths"
    path = raw[2:] if raw.startswith("./") else raw
    path = path.split("#", 1)[0].rstrip("/")
    segments = [s for s in path.split("/") if s != ""]
    if not segments:
        return f"{raw}: empty bucket path"
    if any(s in (".", "..") for s in segments):
        return f"{raw}: '.'/'..' segments are not allowed"
    is_file = bool(_FILE_EXT_RE.search(segments[-1])) and len(segments) > 1
    dirs = segments[:-1] if is_file else segments
    if not dirs:
        return f"{raw}: a file must live inside a pinned NN_ bucket"
    top = dirs[0]
    if not _DOMAIN_DIR_RE.match(top):
        return f"{raw}: not under a pinned NN_ bucket (first segment '{top}')"
    msg = top_level_violation(top, tax)
    if msg:
        return msg
    if len(dirs) >= 2:
        msg = sub_bucket_violation(top, dirs[1], tax)
        if msg:
            return msg
    if len(dirs) > MAX_BUCKET_DEPTH:
        return (f"{raw}: directory '{'/'.join(dirs)}' is deeper than <domain>/<sub-bucket> — "
                "sidecars sit directly in a pinned sub-bucket")
    if is_file and not segments[-1].lower().endswith(".md"):
        return (f"{raw}: only .md sidecars live in a bucket — the original stays once in raw/ "
                "(source_inventory.json raw_path points at it)")
    return None


def check_paths(paths, tax: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in paths:
        msg = bucket_path_violation(p, tax)
        if msg:
            out.append((p, msg))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-write bucket whitelist check (bucket_taxonomy.json).")
    ap.add_argument("paths", nargs="+", help="bucket-relative dir or file path(s), e.g. 07_检验/其他")
    ap.add_argument("--json", action="store_true", help="print a JSON report on stdout")
    ap.add_argument("--taxonomy", default=None, help="override bucket_taxonomy.json path")
    args = ap.parse_args(argv)
    try:
        tax = load_taxonomy(args.taxonomy)
    except Exception as exc:  # unreadable whitelist must never read as "all allowed"
        print(f"ERROR: cannot load bucket taxonomy: {exc}", file=sys.stderr)
        return 2
    violations = check_paths(args.paths, tax)
    if args.json:
        print(json.dumps({
            "ok": not violations,
            "checked": len(args.paths),
            "violations": [{"path": p, "message": m} for p, m in violations],
        }, ensure_ascii=False, indent=2))
    for p, m in violations:
        print(f"REJECT: {p} — {m}", file=sys.stderr)
    if not violations and not args.json:
        print(f"bucket paths OK ({len(args.paths)} checked)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
