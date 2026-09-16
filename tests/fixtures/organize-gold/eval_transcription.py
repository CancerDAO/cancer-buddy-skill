#!/usr/bin/env python3
"""eval_transcription.py — score a run's verbatim transcripts against the local gold set.

WHAT THIS IS
    A deterministic scorer. It reads one `page-NNN.expected.frontmatter.yaml` per
    ground-truthed page, opens the candidate transcription the run produced for that same
    page, and reports three numbers separately: high-risk field accuracy stratified by
    class, miss rate, and full-text token recall. It calls no model, opens no socket, and
    makes no judgement of its own — every comparison is a documented string operation.

WHAT IT CANNOT PROVE
    It measures TRANSCRIPTION, i.e. whether the characters on the page were copied
    faithfully. It says nothing about whether the page itself was right, whether the
    fields mean what their labels claim, or whether the archive is clinically usable. A
    100% score never licenses dropping the channel-independent second read.

USAGE
    eval_transcription.py <gold_dir> <patient_dir> [--json OUT] [--strict]

Exit codes:
    0  the evaluation ran
    1  usage/IO error (gold dir has no annotations, no candidate page could be opened)
    2  bad invocation (argparse)
    3  --strict and a threshold was breached
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------- #
# The 12 + 1 stratification.
#
# references/high-risk-fields.md §1.1 pins 9 domain-independent classes and §1.2 mounts
# the oncology pack. `other` is not a 13th class: it is the catch-all tier for a
# ground-truthed field that no class claims, and it exists so that such a field stays in
# the DENOMINATOR instead of vanishing from the report. A field nobody classified is
# still a field a run can get wrong.
# --------------------------------------------------------------------------- #
GENERIC_9 = (
    "identifier", "date", "drug_name", "dose", "frequency",
    "lab_value", "unit", "reference_range", "accession",
)
ONCOLOGY_3 = ("stage", "variant", "vaf")
CATCH_ALL = "other"
STRATA = GENERIC_9 + ONCOLOGY_3 + (CATCH_ALL,)

# `response_wording` is listed in high-risk-fields.md §1.2 as class 13 while the same
# section's header still says "3 类", and plan_second_read.py's keyword table does NOT
# carry it. It therefore cannot be part of the 12+1 keyword stratification, but a gold
# page that declares it must not be silently dumped into `other`: it gets its own row,
# appended after the fixed strata, and the drift is printed as a diagnostic.
EXTRA_DECLARED = ("response_wording",)

# --------------------------------------------------------------------------- #
# The high-risk keyword taxonomy.
#
# This must be the SAME table the pipeline uses to compute its high-risk denominator
# (fix spec A11). It is imported from plan_second_read.py when the skill tree is
# reachable, so the two can never drift silently; the literal below is a MIRROR used only
# when the scorer is run against an exported gold set with no skill tree beside it, and a
# drift check compares the two whenever the import succeeds.
# --------------------------------------------------------------------------- #
MIRRORED_HIGH_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "identifier": ("姓名", "住院号", "门诊号", "病案号", "就诊卡", "身份证", "患者编号",
                   "mrn", "patient id", "patient_id", "name"),
    "date": ("日期", "时间", "入院", "出院", "采集", "报告日", "手术日", "给药",
             "date", "collected", "reported", "admission", "discharge"),
    "drug_name": ("药物", "药品", "方案", "用药", "化疗", "靶向", "免疫", "通用名", "商品名",
                  "drug", "regimen", "medication"),
    "dose": ("剂量", "用量", "剂", "mg", "mg/m", "g/m", "dose", "dosage"),
    "frequency": ("频次", "频率", "每日", "每周", "隔日", "q3w", "q3d", "qd", "bid", "tid",
                  "frequency", "schedule"),
    "lab_value": ("检验", "结果", "数值", "计数", "浓度", "值", "指标",
                  "value", "result", "count", "level"),
    "unit": ("单位", "unit", "10^9", "g/l", "ng/ml", "u/l", "mmol", "umol", "μ"),
    "reference_range": ("参考", "范围", "区间", "上限", "下限",
                        "reference", "range", "normal"),
    "accession": ("检验号", "标本号", "样本号", "条码", "条形码", "报告编号", "病理号",
                  "accession", "specimen", "barcode", "sample id"),
    "stage": ("分期", "tnm", "ajcc", "figo", "stage", "ct4", "cn", "pt", "ypt"),
    "variant": ("突变", "变异", "融合", "基因", "拷贝数", "hgvs", "c.", "p.",
                "variant", "mutation", "fusion", "gene"),
    "vaf": ("vaf", "丰度", "等位基因频率", "突变频率", "allele frequency"),
}


def _load_pipeline_taxonomy():
    """Import the pipeline's ONE high-risk classifier (scripts/_high_risk.py).

    Walks up from this file looking for the skill's scripts directory. Importing the real
    module is preferred over the mirror for the obvious reason: a mirror that nobody
    checks is a copy that is wrong six months later. Returns (classify_fn, provenance,
    drift_notes); the mirrored keyword table is only the fallback when no skill tree is
    beside the gold set.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "skills" / "cancer-buddy-organize" / "scripts"
        if (cand / "_high_risk.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            try:
                import _high_risk as hr  # noqa: PLC0415
            except Exception as exc:  # pragma: no cover - defensive
                return (_mirror_classify,
                        f"mirrored (import of _high_risk.py failed: {exc!r})", [])
            drift = []
            mirror_classes = set(MIRRORED_HIGH_RISK_KEYWORDS)
            real_classes = set(getattr(hr, "HIGH_RISK_CLASSES", ()))
            if real_classes and real_classes != mirror_classes:
                drift.append(
                    "MIRRORED_HIGH_RISK_KEYWORDS class set has drifted from _high_risk.py"
                    + f"; only upstream: {sorted(real_classes - mirror_classes)}"
                    + f"; only in the mirror: {sorted(mirror_classes - real_classes)}"
                )
            return hr.classify_label, f"imported from {cand / '_high_risk.py'}", drift
    return _mirror_classify, "mirrored (no skill tree found beside the gold set)", []


def _mirror_classify(label: str):
    if not isinstance(label, str):
        return None
    probe = label.strip().lower()
    if not probe:
        return None
    for cls, words in MIRRORED_HIGH_RISK_KEYWORDS.items():
        for w in words:
            if w in probe:
                return cls
    return None


_CLASSIFY, TAXONOMY_PROVENANCE, TAXONOMY_DRIFT = _load_pipeline_taxonomy()
HIGH_RISK_KEYWORDS = MIRRORED_HIGH_RISK_KEYWORDS  # kept for report headers; classification uses _CLASSIFY


def classify_high_risk(label: str) -> str | None:
    """The pipeline's own classifier (scripts/_high_risk.classify_label), same rule as plan_second_read."""
    if not isinstance(label, str):
        return None
    return _CLASSIFY(label)


# --------------------------------------------------------------------------- #
# Normalization — the scoring POLICY. Declared here, never smuggled into a truth file.
# --------------------------------------------------------------------------- #
_DASHES = "‐‑‒–—―−﹣－"
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


def norm(value: object, *, fold_case: bool = True) -> str:
    """Documented normalization, applied identically to gold and candidate.

    1. NFKC: full-width digits/letters fold to ASCII, `mg/m²` folds to `mg/m2`.
    2. Every Unicode dash variant folds to ASCII `-`.
    3. A comma (ASCII or full-width) flanked by digits is deleted: `1,234` -> `1234`.
    4. Whitespace runs collapse to one space; the result is stripped.
    5. Case is folded (Latin only in practice).

    Deliberately NOT done: numeric equality. `12.4` and `12.40` stay different answers,
    because a transcription that changes the printed significant figures has changed what
    the page says. `--numeric-equality` opts into the looser policy explicitly.
    """
    s = unicodedata.normalize("NFKC", "" if value is None else str(value))
    s = "".join("-" if ch in _DASHES else ch for ch in s)
    s = re.sub(r"(?<=\d)[,，](?=\d)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold() if fold_case else s


def values_equal(gold: object, cand: object, numeric_equality: bool) -> bool:
    a, b = norm(gold), norm(cand)
    if a == b:
        return True
    if numeric_equality:
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return False


def token_present(token: str, body_spaced: str, body_nospace: str) -> bool:
    """Is this gold spot-check token present in the candidate body?

    TOKENIZER (the metric's whole definition, so it is stated in --help too):

      * A token containing any CJK/kana character is tested by WHITESPACE-INSENSITIVE
        substring containment — both sides have every space removed first. CJK has no
        word boundaries, so per-character containment IS the boundary-free test; line
        wrapping and column reflow in a table must not count as a dropped token.
      * A Latin/numeric token is tested boundary-anchored: the token's own internal
        whitespace is relaxed to `\\s+`, and the match must not be flanked by
        `[0-9A-Za-z_]`. This is the same rule plan_second_read._token_present uses, and
        for the same reason: `128` must not be satisfied by `1128`, and `WBC` must not be
        satisfied by `WBCX`.
      * A mixed token takes the CJK branch: the CJK part already carries the signal and a
        boundary test on a CJK/Latin seam means nothing.
    """
    t = norm(token)
    if not t:
        return True
    if _CJK_RE.search(t):
        return t.replace(" ", "") in body_nospace
    pattern = r"\s+".join(re.escape(part) for part in t.split(" ") if part)
    if not pattern:
        return True
    return re.search(rf"(?<![0-9A-Za-z_]){pattern}(?![0-9A-Za-z_])", body_spaced) is not None


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)
_BODY_HEADING_RE = re.compile(r"^#[ \t]*全文[ \t]*$", re.MULTILINE)


class ParseError(Exception):
    pass


def _mini_yaml(text: str):
    """A deliberately small YAML subset parser, used when PyYAML is absent.

    Covers exactly the shapes the annotation format and the 段 1 frontmatter contract
    use: comments, block mappings, block sequences of mappings or scalars, flow
    sequences/mappings written as JSON, and quoted/plain scalars. It is not YAML, it does
    not try to be, and it refuses input it does not understand rather than guessing —
    guessing is how `c.1:30` becomes a sexagesimal integer.
    """
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw).rstrip()
        if not stripped.strip():
            continue
        lines.append((len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))

    def scalar(blob: str):
        blob = blob.strip()
        if blob == "":
            return None
        low = blob.lower()
        if low in ("null", "~", "none"):
            return None
        if low in ("true", "false"):
            return low == "true"
        if blob[0] in "[{":
            try:
                return json.loads(blob)
            except json.JSONDecodeError as exc:
                raise ParseError(f"flow collection is not valid JSON: {blob!r} ({exc.msg})") from exc
        if len(blob) >= 2 and blob[0] == blob[-1] and blob[0] in "\"'":
            return blob[1:-1]
        for cast in (int, float):
            try:
                return cast(blob)
            except ValueError:
                pass
        return blob

    pos = 0

    def parse_block(indent: int):
        nonlocal pos
        if pos >= len(lines):
            return None
        if lines[pos][1].startswith("- "):
            out_list = []
            while pos < len(lines) and lines[pos][0] == indent and lines[pos][1].startswith("- "):
                ind, content = lines[pos]
                item = content[2:].strip()
                pos += 1
                if ":" in item and not item.startswith(("[", "{", '"', "'")):
                    # a mapping whose first key shares the dash's line
                    k, _, v = item.partition(":")
                    node: dict = {}
                    inner_indent = ind + 2
                    node[k.strip()] = (scalar(v) if v.strip()
                                       else _nested(inner_indent + 2))
                    while pos < len(lines) and lines[pos][0] >= inner_indent \
                            and not lines[pos][1].startswith("- "):
                        ind2, content2 = lines[pos]
                        if ind2 != inner_indent:
                            raise ParseError(f"unexpected indent at {content2!r}")
                        k2, sep, v2 = content2.partition(":")
                        if not sep:
                            raise ParseError(f"expected `key: value`, got {content2!r}")
                        pos += 1
                        node[k2.strip()] = scalar(v2) if v2.strip() else _nested(ind2 + 1)
                    out_list.append(node)
                else:
                    out_list.append(scalar(item))
            return out_list
        out_map: dict = {}
        while pos < len(lines) and lines[pos][0] == indent:
            _ind, content = lines[pos]
            k, sep, v = content.partition(":")
            if not sep:
                raise ParseError(f"expected `key: value`, got {content!r}")
            pos += 1
            out_map[k.strip()] = scalar(v) if v.strip() else _nested(indent + 1)
        return out_map

    def _nested(min_indent: int):
        if pos < len(lines) and lines[pos][0] >= min_indent:
            return parse_block(lines[pos][0])
        return None

    result = parse_block(lines[0][0]) if lines else {}
    if pos != len(lines):
        raise ParseError(f"unparsed trailing content starting at {lines[pos][1]!r}")
    return result


def _strip_comment(raw: str) -> str:
    """Drop a trailing YAML comment, quote-aware.

    A `#` only opens a comment at the start of the line or after whitespace, and never
    inside a quoted scalar. The naive `raw.split("#", 1)[0]` truncates `value: "a#b"`, and
    a "does this line contain a quote?" guard truncates nothing on the gold file's own
    header comment (`… the page's embedded text layer …`) and then hands an English
    sentence to the mapping parser.
    """
    in_single = in_double = False
    prev = ""
    for i, ch in enumerate(raw):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (i == 0 or prev in " \t"):
            return raw[:i]
        prev = ch
    return raw


def parse_yaml(text: str, parser: str):
    if parser in ("auto", "yaml"):
        try:
            import yaml  # noqa: PLC0415
        except ImportError:
            if parser == "yaml":
                raise ParseError("PyYAML requested with --frontmatter-parser yaml but not installed")
        else:
            try:
                return yaml.safe_load(text)
            except Exception as exc:
                raise ParseError(f"PyYAML could not parse the document: {exc}") from exc
    return _mini_yaml(text)


def split_page(text: str, parser: str) -> tuple[dict, str, list[str]]:
    """Split a candidate `page-NNN.md` into (frontmatter, 全文 body, structural defects)."""
    defects: list[str] = []
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ParseError("no YAML frontmatter block (--- ... ---) at the start of the page")
    fm = parse_yaml(m.group(1), parser)
    if not isinstance(fm, dict):
        raise ParseError("frontmatter did not parse to a mapping")
    rest = text[m.end():]
    heading = _BODY_HEADING_RE.search(rest)
    if heading:
        body = rest[heading.end():]
    else:
        defects.append("no `# 全文` heading: the whole post-frontmatter remainder was "
                       "scored as the body, which the 段 1 output contract forbids")
        body = rest
    return fm, body, defects


# --------------------------------------------------------------------------- #
# Gold set discovery
# --------------------------------------------------------------------------- #
_EXPECTED_RE = re.compile(r"^page-(?P<page>\d+)\.expected\.frontmatter\.yaml$")


def discover_gold(gold_dir: Path) -> list[tuple[str, int, Path]]:
    """Find every ground-truthed page as (dir_key, page_no, path).

    Two layouts are accepted, because both exist in the tree this scores:
      <gold>/<source_id>/page-NNN.expected.frontmatter.yaml   (README §3, the real set)
      <gold>/page-NNN.expected.frontmatter.yaml               (SYNTHETIC-example/)
    In the flat case the directory's own name is the key.
    """
    found: list[tuple[str, int, Path]] = []
    for path in sorted(gold_dir.glob("page-*.expected.frontmatter.yaml")):
        m = _EXPECTED_RE.match(path.name)
        if m:
            found.append((gold_dir.name, int(m.group("page")), path))
    for sub in sorted(p for p in gold_dir.iterdir() if p.is_dir()):
        for path in sorted(sub.glob("page-*.expected.frontmatter.yaml")):
            m = _EXPECTED_RE.match(path.name)
            if m:
                found.append((sub.name, int(m.group("page")), path))
    return found


def candidate_path(patient_dir: Path, dir_key: str, fm_source_id: object,
                   page: int) -> tuple[Path | None, list[Path]]:
    """Locate `raw/transcript/<source_id>/page-NNN.md`.

    `<source_id>` is ambiguous in the fixture as it stands: SYNTHETIC-example's annotation
    declares `source_id: SYN001` while the directory holding it is `SYNTHETIC-example`.
    Both are tried, directory name first, and the one that exists is reported.
    """
    keys: list[str] = [dir_key]
    if isinstance(fm_source_id, str) and fm_source_id.strip() and fm_source_id != dir_key:
        keys.append(fm_source_id.strip())
    tried: list[Path] = []
    for key in keys:
        p = patient_dir / "raw" / "transcript" / key / f"page-{page:03d}.md"
        tried.append(p)
        if p.is_file():
            return p, tried
    return None, tried


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def new_bucket() -> dict:
    return {"n_expected": 0, "n_matched": 0, "n_wrong": 0, "n_missing": 0}


def score(gold_dir: Path, patient_dir: Path, args) -> tuple[dict, int]:
    pages = discover_gold(gold_dir)
    if not pages:
        print(f"ERROR: no page-NNN.expected.frontmatter.yaml under {gold_dir}", file=sys.stderr)
        return {}, 1

    by_class: dict[str, dict] = {}
    overall = new_bucket()
    token_hit = token_total = 0
    page_reports: list[dict] = []
    defects: list[dict] = []
    taxonomy_rows: list[dict] = []
    side = {"text_layer_kind": [0, 0], "doc_kind": [0, 0], "clinical_class": [0, 0]}
    pages_opened = 0
    disputed_excluded = 0

    def bucket(cls: str) -> dict:
        return by_class.setdefault(cls, new_bucket())

    for dir_key, page_no, gold_path in pages:
        try:
            gold = parse_yaml(gold_path.read_text(encoding="utf-8"), args.frontmatter_parser)
        except (OSError, ParseError) as exc:
            print(f"ERROR: gold annotation {gold_path.name} in {dir_key}: {exc}", file=sys.stderr)
            return {}, 1
        if not isinstance(gold, dict):
            print(f"ERROR: gold annotation {gold_path.name} in {dir_key} is not a mapping",
                  file=sys.stderr)
            return {}, 1

        gold_fields = [f for f in (gold.get("fields") or []) if isinstance(f, dict)]
        gold_tokens = [t for t in (gold.get("full_text_tokens") or []) if isinstance(t, str)]

        cand_file, tried = candidate_path(patient_dir, dir_key, gold.get("source_id"), page_no)
        prep: dict = {
            "source_dir": dir_key, "page": page_no,
            "gold": str(gold_path), "candidate": str(cand_file) if cand_file else None,
            "fields": [], "tokens": {"expected": len(gold_tokens), "found": 0, "missing": []},
        }

        cand_fm: dict = {}
        body_spaced = body_nospace = ""
        page_present = False
        if cand_file is None:
            defects.append({"source_dir": dir_key, "page": page_no, "severity": "page_missing",
                            "detail": "no candidate transcript; tried "
                                      + ", ".join(_display_path(p) for p in tried)})
        else:
            try:
                cand_fm, body, structural = split_page(
                    cand_file.read_text(encoding="utf-8"), args.frontmatter_parser)
            except (OSError, UnicodeDecodeError, ParseError) as exc:
                defects.append({"source_dir": dir_key, "page": page_no,
                                "severity": "page_unparseable", "detail": str(exc)})
            else:
                page_present = True
                pages_opened += 1
                for d in structural:
                    defects.append({"source_dir": dir_key, "page": page_no,
                                    "severity": "structural", "detail": d})
                body_spaced = norm(body)
                body_nospace = body_spaced.replace(" ", "")

        cand_fields: dict[str, dict] = {}
        for f in (cand_fm.get("fields") or []):
            if isinstance(f, dict) and isinstance(f.get("label"), str):
                cand_fields.setdefault(norm(f["label"]), f)

        # ---- (a) field accuracy + (b) miss rate, stratified -------------------
        for gf in gold_fields:
            label = gf.get("label")
            gold_value = gf.get("value")
            declared = gf.get("high_risk_class")
            pipeline_cls = classify_high_risk(label if isinstance(label, str) else "")
            taxonomy_rows.append({"source_dir": dir_key, "page": page_no, "label": label,
                                  "declared": declared, "pipeline": pipeline_cls})

            if args.class_source == "pipeline":
                cls = pipeline_cls or CATCH_ALL
            else:
                cls = declared if isinstance(declared, str) and declared.strip() else \
                    (pipeline_cls or CATCH_ALL)
            if cls not in STRATA and cls not in EXTRA_DECLARED:
                defects.append({"source_dir": dir_key, "page": page_no, "severity": "unknown_class",
                                "detail": f"field {label!r} declares high_risk_class {cls!r}, "
                                          "which is in neither high-risk-fields.md §1 nor the "
                                          "catch-all tier; scored under `other`"})
                cls = CATCH_ALL

            if gold_value is None:
                # README §4: a disputed page has no truth value and leaves the denominator.
                disputed_excluded += 1
                prep["fields"].append({"label": label, "class": cls, "verdict": "excluded_disputed"})
                continue

            b = bucket(cls)
            b["n_expected"] += 1
            overall["n_expected"] += 1
            cf = cand_fields.get(norm(label)) if isinstance(label, str) else None
            if cf is None:
                b["n_missing"] += 1
                overall["n_missing"] += 1
                verdict, got = "missing", None
            elif values_equal(gold_value, cf.get("value"), args.numeric_equality):
                b["n_matched"] += 1
                overall["n_matched"] += 1
                verdict, got = "match", cf.get("value")
            else:
                b["n_wrong"] += 1
                overall["n_wrong"] += 1
                verdict, got = "wrong_value", cf.get("value")
            prep["fields"].append({"label": label, "class": cls, "verdict": verdict,
                                   "expected": gold_value, "got": got})
            if verdict != "match":
                defects.append({"source_dir": dir_key, "page": page_no, "severity": verdict,
                                "detail": f"[{cls}] {label!r}: expected {gold_value!r}, got {got!r}"})
            if cf is not None and gf.get("unit") is not None and \
                    not values_equal(gf.get("unit"), cf.get("unit"), False):
                defects.append({"source_dir": dir_key, "page": page_no, "severity": "unit_mismatch",
                                "detail": f"[{cls}] {label!r}: unit expected {gf.get('unit')!r}, "
                                          f"got {cf.get('unit')!r} (reported, not folded into "
                                          "field accuracy)"})

        # ---- (c) full-text token recall ---------------------------------------
        for tok in gold_tokens:
            token_total += 1
            if page_present and token_present(tok, body_spaced, body_nospace):
                token_hit += 1
                prep["tokens"]["found"] += 1
            else:
                prep["tokens"]["missing"].append(tok)
                defects.append({"source_dir": dir_key, "page": page_no, "severity": "token_missing",
                                "detail": f"全文 token {tok!r} not found in the candidate body"})

        # ---- side signals, reported alongside and never folded in -------------
        if page_present:
            for key in ("text_layer_kind", "doc_kind", "clinical_class"):
                if gold.get(key) is None:
                    continue
                side[key][1] += 1
                if norm(gold.get(key)) == norm(cand_fm.get(key)):
                    side[key][0] += 1
                else:
                    defects.append({"source_dir": dir_key, "page": page_no,
                                    "severity": f"{key}_mismatch",
                                    "detail": f"expected {gold.get(key)!r}, "
                                              f"got {cand_fm.get(key)!r} (side signal)"})
        if gold.get("known_defect"):
            prep["known_defect"] = gold["known_defect"]
        page_reports.append(prep)

    if pages_opened == 0:
        print(f"ERROR: none of the {len(pages)} ground-truthed page(s) had a readable candidate "
              f"under {patient_dir / 'raw' / 'transcript'}", file=sys.stderr)
        return {}, 1

    report = {
        "gold_dir": str(gold_dir), "patient_dir": str(patient_dir),
        "pages_ground_truthed": len(pages), "pages_scored": pages_opened,
        "class_source": args.class_source,
        "numeric_equality": args.numeric_equality,
        "taxonomy_provenance": TAXONOMY_PROVENANCE,
        "taxonomy_drift": TAXONOMY_DRIFT,
        "disputed_fields_excluded": disputed_excluded,
        "by_class": by_class, "overall": overall,
        "full_text_recall": {"found": token_hit, "expected": token_total},
        "side_signals": {k: {"agreed": v[0], "compared": v[1]} for k, v in side.items()},
        "pages": page_reports,
        "defects": defects,
        "taxonomy_rows": taxonomy_rows,
    }
    return report, 0


def _rate(num: int, den: int) -> str:
    return "     n/a" if den == 0 else f"{num / den * 100:7.2f}%"


def _display_path(p: str | Path) -> str:
    """Render a path for the human report without leaking the host filesystem.

    An absolute path in a printed report carries the OS username and where the vault sits
    on disk, and this report gets pasted into READMEs and issues. Paths under the working
    directory print relative to it; anything else falls back to a `~`-abbreviated form.
    The JSON report keeps the resolved paths, because a machine consumer needs them.
    """
    path = Path(p)
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        pass
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def print_report(r: dict, args) -> None:
    w = sys.stdout.write
    w("=" * 78 + "\n")
    w("TRANSCRIPTION ACCURACY vs GOLD SET\n")
    w("=" * 78 + "\n")
    w(f"gold        : {_display_path(r['gold_dir'])}\n")
    w(f"candidate   : {_display_path(r['patient_dir'])}\n")
    w(f"pages       : {r['pages_scored']} scored / {r['pages_ground_truthed']} ground-truthed\n")
    prov = r["taxonomy_provenance"]
    if prov.startswith("imported from "):
        prov = "imported from " + _display_path(prov[len("imported from "):])
    w(f"class source: {r['class_source']}   taxonomy: {prov}\n")
    w(f"value policy: {'numeric equality ON' if r['numeric_equality'] else 'verbatim after documented normalization (12.4 != 12.40)'}\n")
    if r["disputed_fields_excluded"]:
        w(f"excluded    : {r['disputed_fields_excluded']} disputed field(s) with a null truth value\n")
    for d in r["taxonomy_drift"]:
        w(f"WARNING     : {d}\n")

    w("\n(a) FIELD-LEVEL ACCURACY and (b) MISS RATE, by high-risk class (12 + `other`)\n")
    head = f"{'class':<18}{'n_exp':>7}{'match':>7}{'wrong':>7}{'miss':>7}{'accuracy':>10}{'miss rate':>11}\n"
    w(head)
    w("-" * (len(head) - 1) + "\n")
    order = list(STRATA) + [c for c in EXTRA_DECLARED if c in r["by_class"]] \
        + [c for c in r["by_class"] if c not in STRATA and c not in EXTRA_DECLARED]
    for cls in order:
        b = r["by_class"].get(cls)
        if b is None:
            if args.show_empty_classes:
                w(f"{cls:<18}{0:>7}{0:>7}{0:>7}{0:>7}{'     n/a':>10}{'      n/a':>11}\n")
            continue
        w(f"{cls:<18}{b['n_expected']:>7}{b['n_matched']:>7}{b['n_wrong']:>7}{b['n_missing']:>7}"
          f"{_rate(b['n_matched'], b['n_expected']):>10}{_rate(b['n_missing'], b['n_expected']):>11}\n")
    w("-" * (len(head) - 1) + "\n")
    o = r["overall"]
    w(f"{'OVERALL':<18}{o['n_expected']:>7}{o['n_matched']:>7}{o['n_wrong']:>7}{o['n_missing']:>7}"
      f"{_rate(o['n_matched'], o['n_expected']):>10}{_rate(o['n_missing'], o['n_expected']):>11}\n")

    ft = r["full_text_recall"]
    w("\n(c) FULL-TEXT TOKEN RECALL (全文 spot-check tokens found in the candidate body)\n")
    w(f"{'tokens':<18}{ft['found']:>7} / {ft['expected']:<7}"
      f"{_rate(ft['found'], ft['expected']):>28}\n")

    w("\nSIDE SIGNALS (reported alongside, never folded into the three numbers)\n")
    for k, v in r["side_signals"].items():
        w(f"{k:<18}{v['agreed']:>7} / {v['compared']:<7}{_rate(v['agreed'], v['compared']):>28}\n")

    dis = [t for t in r["taxonomy_rows"]
           if t["declared"] and t["pipeline"] and t["declared"] != t["pipeline"]]
    unseen = [t for t in r["taxonomy_rows"] if t["declared"] and not t["pipeline"]]
    w("\nTAXONOMY DIAGNOSTIC (gold-declared class vs plan_second_read.py's keyword table)\n")
    w(f"  ground-truthed fields          : {len(r['taxonomy_rows'])}\n")
    w(f"  the keyword table classifies   : {len(r['taxonomy_rows']) - len(unseen)}\n")
    w(f"  the keyword table MISSES       : {len(unseen)}"
      f"{'  <- these would not enter the A11 deterministic denominator' if unseen else ''}\n")
    for t in unseen[:args.max_detail]:
        w(f"      {t['source_dir']} p{t['page']:03d} {t['label']!r} declared={t['declared']}\n")
    if dis:
        w(f"  disagreements                  : {len(dis)}\n")
        for t in dis[:args.max_detail]:
            w(f"      {t['source_dir']} p{t['page']:03d} {t['label']!r} "
              f"declared={t['declared']} keyword={t['pipeline']}\n")

    if r["defects"]:
        w(f"\nDEFECTS ({len(r['defects'])})\n")
        for d in r["defects"][:args.max_detail]:
            w(f"  [{d['severity']}] {d['source_dir']} p{d['page']:03d}: {d['detail']}\n")
        if len(r["defects"]) > args.max_detail:
            w(f"  … {len(r['defects']) - args.max_detail} more (see --json)\n")

    w("\nWHAT THESE NUMBERS CANNOT PROVE: they describe character-level transcription only.\n"
      "They do not show the page was clinically correct, that a matched field means what its\n"
      "label says, or that a field absent from the gold annotation was read right — only the\n"
      "high-risk classes are ground-truthed. A 100% row never licenses skipping the\n"
      "channel-independent second read.\n")


EPILOG = """\
WHAT THE THREE METRICS MEAN

  (a) FIELD-LEVEL ACCURACY, stratified by high-risk class
      n_matched / n_expected, where a gold field counts as matched when the candidate
      frontmatter carries a field with the SAME label (after normalization) AND an equal
      value. Reported per class because a 2% aggregate error is a different problem when
      it all sits in `dose` than when it all sits in `identifier`.

      NORMALIZATION (the scoring policy, applied identically to both sides):
        1. NFKC — full-width digits/letters fold to ASCII; `mg/m²` folds to `mg/m2`
        2. every Unicode dash variant folds to ASCII `-`
        3. a comma flanked by digits is deleted: `1,234` -> `1234`
        4. whitespace runs collapse to one space, then strip
        5. case folding
      NOT done by default: numeric equality. `12.4` and `12.40` remain different answers,
      because changing the printed significant figures changes what the page says. Pass
      --numeric-equality to opt into the looser policy on purpose.

  (b) MISS RATE
      n_missing / n_expected, where missing means the candidate never emitted a field with
      that label AT ALL. Split out from accuracy because a field the model never claimed
      is invisible to an accuracy score: it is not wrong, it is absent, and nothing
      downstream will ever ask for it.

  (c) FULL-TEXT TOKEN RECALL
      gold `full_text_tokens` found in the candidate `# 全文` body / total tokens.
      TOKENIZER: a token containing CJK/kana is matched by whitespace-insensitive
      substring containment (CJK has no word boundaries, and table reflow must not read as
      a dropped token). A Latin/numeric token is matched boundary-anchored — internal
      whitespace relaxed to `\\s+`, and the match may not be flanked by [0-9A-Za-z_], so
      `128` is not satisfied by `1128`. A mixed token takes the CJK branch.

WHAT THEY CANNOT PROVE

  * Nothing clinical. This is a character-copying measurement. A page transcribed
    perfectly can still be a wrong report, and the metric has no opinion about that.
  * Nothing about fields outside the gold annotation. Only the 12 high-risk classes are
    ground-truthed (references/high-risk-fields.md §1); everything else on the page is
    unmeasured, and `other` only collects ground-truthed fields no class claimed.
  * Nothing about a single page. One page is an anecdote; these numbers mean something
    against the multi-page local gold set described in README §2.
  * It never licenses dropping the channel-independent second read for high-risk fields.
  * A disputed gold field (`value: null`) is excluded from the denominator, not guessed.

STRATIFICATION
  9 domain-independent classes + the 3-class oncology pack + one `other` catch-all tier.
  Classes come from the gold annotation's `high_risk_class` by default and fall back to
  plan_second_read.py's keyword table; --class-source pipeline scores by the keyword table
  alone, which is what the pipeline's own A11 denominator would see.
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="eval_transcription.py",
        description="Score a run's verbatim transcripts against the local gold set. "
                    "Deterministic, no network, no model.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("gold_dir", nargs="?",
                    help="directory of page-NNN.expected.frontmatter.yaml annotations "
                         "(flat, or one subdirectory per source_id)")
    ap.add_argument("patient_dir", nargs="?",
                    help="the run's patient directory; transcripts are read from "
                         "<patient_dir>/raw/transcript/<source_id>/page-NNN.md. It may live "
                         "anywhere on disk — it does not have to be inside tests/.")
    # README §5 spells the same two arguments as flags; both forms are accepted so the
    # documented convention there stays literally runnable.
    ap.add_argument("--gold", dest="gold_flag", help="alias for the gold_dir positional")
    ap.add_argument("--run", dest="run_flag", help="alias for the patient_dir positional")
    ap.add_argument("--run-id", help="optional; recorded in the JSON report for traceability")
    ap.add_argument("--json", dest="json_out", metavar="OUT",
                    help="also write the full machine-readable report here ('-' for stdout)")
    ap.add_argument("--report", dest="json_out_alias", metavar="OUT",
                    help="alias for --json (the spelling used in README §5)")
    ap.add_argument("--class-source", choices=("gold", "pipeline"), default="gold",
                    help="gold (default): stratify by the annotation's declared "
                         "high_risk_class, falling back to the keyword table. "
                         "pipeline: stratify by plan_second_read.py's keyword table only.")
    ap.add_argument("--numeric-equality", action="store_true",
                    help="treat 12.4 and 12.40 as equal. OFF by default: verbatim is the "
                         "annotation contract, and loosening it is a policy choice, not a fix.")
    ap.add_argument("--frontmatter-parser", choices=("auto", "yaml", "builtin"), default="auto",
                    help="auto (default) uses PyYAML when importable and the built-in "
                         "subset parser otherwise; builtin forces the stdlib-only path, "
                         "which is what runs on a host with no PyYAML.")
    ap.add_argument("--max-detail", type=int, default=40,
                    help="cap on printed per-defect lines (the JSON report is never capped)")
    ap.add_argument("--show-empty-classes", action="store_true",
                    help="print classes with no ground-truthed field instead of omitting them")
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 when a threshold below is breached. The thresholds are a "
                         "POLICY for CI, not a measurement: they are where this repo has "
                         "decided a regression stops being acceptable.")
    ap.add_argument("--min-accuracy", type=float, default=0.95, metavar="F",
                    help="--strict floor on overall field accuracy (default 0.95)")
    ap.add_argument("--max-miss-rate", type=float, default=0.02, metavar="F",
                    help="--strict ceiling on overall miss rate (default 0.02)")
    ap.add_argument("--min-recall", type=float, default=0.98, metavar="F",
                    help="--strict floor on full-text token recall (default 0.98)")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    gold_s = args.gold_dir or args.gold_flag
    run_s = args.patient_dir or args.run_flag
    if not gold_s or not run_s:
        ap.error("both a gold directory and a patient directory are required "
                 "(positionally, or via --gold/--run)")
    json_out = args.json_out or args.json_out_alias

    gold_dir = Path(gold_s).expanduser().resolve()
    patient_dir = Path(run_s).expanduser().resolve()
    if not gold_dir.is_dir():
        print(f"ERROR: gold directory not found: {gold_dir}", file=sys.stderr)
        return 1
    if not patient_dir.is_dir():
        print(f"ERROR: patient directory not found: {patient_dir}", file=sys.stderr)
        return 1

    report, rc = score(gold_dir, patient_dir, args)
    if rc:
        return rc
    if args.run_id:
        report["run_id"] = args.run_id

    print_report(report, args)

    if json_out:
        blob = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False)
        if json_out == "-":
            print(blob)
        else:
            out = Path(json_out).expanduser().resolve()
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(blob + "\n", encoding="utf-8")
            except OSError as exc:
                print(f"ERROR: could not write {out}: {exc}", file=sys.stderr)
                return 1
            print(f"\nJSON report written to {_display_path(out)}")

    if args.strict:
        o = report["overall"]
        ft = report["full_text_recall"]
        acc = o["n_matched"] / o["n_expected"] if o["n_expected"] else 1.0
        miss = o["n_missing"] / o["n_expected"] if o["n_expected"] else 0.0
        rec = ft["found"] / ft["expected"] if ft["expected"] else 1.0
        breaches = []
        if acc < args.min_accuracy:
            breaches.append(f"field accuracy {acc:.4f} < --min-accuracy {args.min_accuracy}")
        if miss > args.max_miss_rate:
            breaches.append(f"miss rate {miss:.4f} > --max-miss-rate {args.max_miss_rate}")
        if rec < args.min_recall:
            breaches.append(f"token recall {rec:.4f} < --min-recall {args.min_recall}")
        if breaches:
            print("\n--strict: " + "; ".join(breaches), file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
