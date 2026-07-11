#!/usr/bin/env python3
"""Structure validator for the 段D「关键趋势」cancer-type → marker reference table.

Validates skills/cancer-buddy-organize/references/cancer-trend-markers.md against
the 69 NCCN cancer-type slugs derived from the treatment-landscape corpus.

Usage:
    python3 validate_cancer_trend_markers.py --markers <md> [--expected-count 69]
    python3 validate_cancer_trend_markers.py --markers <md> --slugs <landscapes_dir>

Exit codes:
    0 = structure valid
    1 = violations found (reasons printed to stderr, with line numbers where applicable)
"""
import argparse
import glob
import os
import sys


def landscape_slugs(d):
    out = set()
    for p in glob.glob(os.path.join(d, "*-treatment-landscape-2026-07.md")):
        b = os.path.basename(p)
        out.add(b[: -len("-treatment-landscape-2026-07.md")])
    return out


def parse_rows(md):
    rows = []
    for i, line in enumerate(md.splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            # a pipe line with <5 cols that's not the separator is malformed
            if set("".join(cells)) <= set("-: "):  # separator row
                continue
            rows.append((i, None))
            continue
        if cells[0].lower() == "slug" or set("".join(cells)) <= set("-: "):
            continue
        rows.append((i, cells[:5]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markers", required=True)
    ap.add_argument(
        "--slugs",
        help="optional treatment-landscape directory for an external slug cross-check",
    )
    ap.add_argument(
        "--expected-count",
        type=int,
        help="optional expected number of unique marker rows",
    )
    a = ap.parse_args()
    md = open(a.markers, encoding="utf-8").read()
    rows = parse_rows(md)
    errs = []
    slugs = []
    for ln, cells in rows:
        if cells is None:
            errs.append(f"L{ln}: 行列数<5")
            continue
        slug, name, primary, secondary, caveat = cells
        slugs.append(slug)
        if not slug or not name:
            errs.append(f"L{ln}: slug/癌种为空")
        if not primary:
            errs.append(f"L{ln}: primary 为空（无标志物须写 —）")
    have = set(slugs)
    if a.slugs:
        want = landscape_slugs(a.slugs)
        if not want:
            errs.append(f"外部 slug 目录没有匹配文件: {a.slugs}")
        missing = want - have
        extra = have - want
        if missing:
            errs.append(f"缺 {len(missing)} 癌种: {sorted(missing)[:5]}...")
        if extra:
            errs.append(f"多出非 NCCN slug: {sorted(extra)[:5]}")
    if len(slugs) != len(set(slugs)):
        errs.append("slug 有重复")
    if a.expected_count is not None and len(have) != a.expected_count:
        errs.append(f"唯一 slug 数量应为 {a.expected_count}，实际为 {len(have)}")
    if errs:
        print("\n".join(errs), file=sys.stderr)
        sys.exit(1)
    print(f"OK: {len(slugs)} 癌种，结构合法")
    sys.exit(0)


if __name__ == "__main__":
    main()
