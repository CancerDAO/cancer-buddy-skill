#!/usr/bin/env bash
# cancer-buddy-organize — mechanical checks on the prompt-side contracts that the
# deterministic scripts depend on. Static, fully automatable; no judgement:
#
#   A. SKILL.md fits the host load budget: ≤ 51,200 bytes (≤ 50 KiB).
#   B. references/lexicons/*.txt are one plain term per line — the validator treats every
#      whole line as a candidate spelling, so a line that is empty, padded, a duplicate or
#      a mapping (`O药 | 纳武利尤单抗`, `a: b`, `a = b`, `a -> b`, `a → b`) would turn into
#      a "candidate" nobody meant.
#   C. organizer-prompt-phase1-ocr.md §3 shows exactly the 12 pinned sidecar header keys in
#      the pinned order — the same tuple pii_rescan.PINNED_HEADER_KEYS exempts from the PII
#      scan and validate_structured_outputs.py enforces — and its SOURCE document-type list
#      equals validate_structured_outputs.SIDECAR_SOURCE_TYPES.
#   D. acute-findings.md §3 table lists exactly the 10 finding_class values of
#      acute_findings.schema.json, and its 默认 acuity column equals the validator's fixed
#      table (ACUTE_CLASS_DEFAULT).
#   E. every `field_class` / `layout` value the phase1 §5 `## 不确定字段` example lists is one
#      the validator accepts (UNCERTAIN_FIELD_CLASSES / UNCERTAIN_LAYOUTS). Subset, not
#      equality: a value only the prompt knows would fail every sidecar written with it, while
#      a value the validator also accepts is harmless until the prompt adopts it.
#   F. one stale-source sentence: scripts/source_freshness.py STALE_WARNING_TEMPLATE. Every
#      line of SKILL.md or references/*.md that contains 距本次整理 is the template with its two
#      slots filled — Phase 2 copies the script's `warning` verbatim, so a prompt must not teach
#      another wording. The template itself (with its {latest} / {days} placeholders) must be
#      present in the phase2 §6.2 ```text block and in SKILL.md Step 8, and the repo-root
#      references/patient-profile-schema.md readiness example's warnings[0] is the template
#      filled with that example's own latest_source_date / days_since_latest.
#   G. run_mode vocabulary (D1): the phase2 §0 Call-parameters `run_mode` list names every value
#      of validate_structured_outputs.FULL_RUN_MODES, and neither SKILL.md nor references/**/*.md
#      documents the retired boolean parameter (`legacy_upgrade`（布尔 / legacy_upgrade: true).
#   H. acute-findings.md §4.1 ```text block (the pinned words behind each acuity adjustment, the
#      per-class escalation routes (target acuity + words; ESCALATION_ROUTES), the
#      classes with a chronic adjustment, the unchanged-comparison words) equals the validator's
#      ACUITY_BASIS_TOKENS / CHRONIC_ADJUSTABLE_CLASSES / THROMBUS_STABLE_TOKENS, value for value.
#   J. SKILL.md, references/*.md and runtime-bindings/*.md run every script as
#      python3 "<skill_dir>/scripts/…", or a sibling charts script as
#      python3 "<skill_dir>/../cancer-buddy-charts/scripts/…" (a worker's cwd is not the skill dir; the
#      orchestrator's shell may be anywhere).
#   K. phase2 §6.1's 不可信内容标记 row states the grading scan_untrusted_markers.py emits.
#   L. no recursive `rm` in SKILL.md, references/*.md or runtime-bindings/*.md names `$src` / `${src}`, a `raw`
#      path, `<patient_dir>` or `$patient_dir`: `$src` can be the user's own input folder or the archive's
#      raw/ vault (legacy_upgrade), so the only directory a clean-up may remove is an archive's temp
#      `unpack_dir` (SKILL.md Steps 1 and 17). Only the command's argument tokens are checked, so prose
#      that names `$src` or raw/ next to a command does not trip it.
#   M. one 段D stale notice: phase2 §7 carries validate_structured_outputs.CASE_SUMMARY_STALE_NOTICE verbatim
#      in a ```text block — the validator looks for that sentence in review_summary.md and readiness warnings[]
#      whenever the 段D render predates emergent/urgent findings, so the prompt must teach exactly it.
#   N. one 段D lead: case-summary-html-prompt.md「急性/附带发现」carries validate_structured_outputs.ACUTE_SUMMARY_LEAD
#      (the neutral 报告写到 — never the retired 报告原文写到 lead), the translated item form 「（<日期>，中文转述）」
#      (ACUTE_LEAD_TRANSLATION_MARK) and the caveat prefix ACUTE_CAVEAT_TRANSLATION_PREFIX — the validator checks the
#      narrative's first sentence and the caveats against exactly these strings; phase2 §7 quotes the same lead.
#      The rule too: the prompt states ACUTE_CAVEAT_ITEM_RULE (item-scoped, listing ACUTE_CAVEAT_ORIGINAL_CLAIMS; not the
#      retired quotation-slot rule) and one caveat item per finding; its own two caveat forms, run through
#      translated_caveat_problems, pass / reject / ignore a nested quote (colon or quote mark before it included) as it
#      says, and the bypass forms (报告原文写明…, 外院报告原文提示…, <AF1>…<AF2>, a listed claim next to the prefix) fail.
#      Surfaces: profile-card.md labels a translation 中文转述，非报告原句 (acute-findings.md §2.4 lists Step 11), and
#      SKILL.md Step 12, phase2 §9 and §10 route an 「ERROR: .case_summary_data.json」 line to the 段D re-render
#      (§9 excepting the validator's 'the pinned stale notice … is missing' line: that is Phase 2's own notice).
#   I. phase1 §3 table rows READ_MODE / ADAPTER / MODALITY list exactly the validator's
#      SIDECAR_READ_MODES / SIDECAR_ADAPTERS / SIDECAR_MODALITIES (checked on the header itself, so
#      a sidecar without an inventory row cannot carry free text there).
#
# CB_ORG_DIR overrides the skill directory and CB_REPO_REFS_DIR the repo-root references/
# directory (tests/unit/organize-contract-lints.test.sh runs this lint on mutated copies to
# prove each check fires).
set -euo pipefail
source "$(dirname "$0")/_common.sh"
errs=0
ORG="${CB_ORG_DIR:-$SKILLS_DIR/cancer-buddy-organize}"
ROOT_REFS="${CB_REPO_REFS_DIR:-$REFS_DIR}"
[[ -d "$ORG" ]] || { fail "organize skill dir not found: $ORG"; summarize "organize-prompt-contracts"; }

rc=0
python3 - "$ORG" "$ROOT_REFS" <<'PY' || rc=$?
import json, re, sys, unicodedata
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ in the skill dir
org = Path(sys.argv[1])
root_refs = Path(sys.argv[2])
bad = 0


def fail(msg):
    global bad
    bad += 1
    print(f"FAIL: organize-prompt-contracts: {msg}", file=sys.stderr)


# ---- A. SKILL.md byte budget
SKILL_MAX = 51200
size = (org / "SKILL.md").stat().st_size
if size > SKILL_MAX:
    fail(f"SKILL.md is {size} bytes (> {SKILL_MAX}); move detail into references/")

# ---- B. lexicon hygiene
lex_files = sorted((org / "references" / "lexicons").glob("*.txt"))
if not lex_files:
    fail("references/lexicons/*.txt missing")
FORBIDDEN = (" | ", ":", "：", "=", "＝", "->", "→")
for f in lex_files:
    seen = {}
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
        where = f"{f.name}:{i}"
        if not line.strip():
            fail(f"{where}: empty line")
            continue
        if line != line.strip():
            fail(f"{where}: leading/trailing whitespace in {line!r}")
        hit = [t for t in FORBIDDEN if t in line]
        if hit:
            fail(f"{where}: {line!r} is a mapping, not a single term (contains {hit[0]!r})")
        key = unicodedata.normalize("NFKC", line).strip()
        if key in seen:
            fail(f"{where}: duplicate of line {seen[key]} ({line!r})")
        else:
            seen[key] = i

# ---- C. phase1 §3 header block + SOURCE list
sys.path.insert(0, str(org / "scripts"))
try:
    import pii_rescan
    pinned = list(pii_rescan.PINNED_HEADER_KEYS)
except Exception as e:  # the script is part of the contract
    fail(f"cannot import scripts/pii_rescan.py: {e}")
    pinned = []
PINNED = ["SOURCE", "FILE_ID", "EXTRACTOR", "PRIMARY_CHANNEL", "SECOND_READ_CHANNEL", "INDEPENDENT_REREAD",
          "READ_MODE", "ADAPTER", "CONFIDENCE", "SHA256", "PAGE_LABEL", "MODALITY"]
if pinned and pinned != PINNED:
    fail(f"pii_rescan.PINNED_HEADER_KEYS {pinned} ≠ the pinned 12 keys {PINNED}")
p1 = (org / "references" / "organizer-prompt-phase1-ocr.md").read_text(encoding="utf-8")
sec = re.search(r"^## 3\. .*?$(.*?)^## 4\. ", p1, re.S | re.M)
if not sec:
    fail("organizer-prompt-phase1-ocr.md has no `## 3.` … `## 4.` section")
else:
    body = sec.group(1)
    block = re.search(r"```text\n(.*?)```", body, re.S)
    if not block:
        fail("phase1 §3 has no ```text header example")
    else:
        keys = [m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*):", block.group(1), re.M)]
        if keys != PINNED:
            fail(f"phase1 §3 header example keys {keys} ≠ pinned order {PINNED}")
    row = re.search(r"^\|\s*`SOURCE`\s*\|(.*)\|\s*$", body, re.M)
    if not row:
        fail("phase1 §3 table has no `SOURCE` row")
    else:
        listed = re.findall(r"`([a-z_]+)`", row.group(1))
        try:
            import validate_structured_outputs as vso
            want = list(vso.SIDECAR_SOURCE_TYPES)
        except Exception as e:
            fail(f"cannot import scripts/validate_structured_outputs.py: {e}")
            want = listed
        if listed != want:
            fail(f"phase1 §3 SOURCE types {listed} ≠ validator SIDECAR_SOURCE_TYPES {want}")

# ---- D. acute-findings.md §3 table ↔ schema enum ↔ validator default table
schema = json.loads((org / "references" / "schemas" / "acute_findings.schema.json").read_text(encoding="utf-8"))
enum = schema["properties"]["findings"]["items"]["properties"]["finding_class"]["enum"]
af = (org / "references" / "acute-findings.md").read_text(encoding="utf-8")
sec = re.search(r"^## 3\. .*?$(.*?)^## 4\. ", af, re.S | re.M)
if not sec:
    fail("acute-findings.md has no `## 3.` … `## 4.` section")
else:
    rows = re.findall(r"^\|\s*`([a-z_]+)`[^|]*\|\s*([a-z]+)\s*\|", sec.group(1), re.M)
    classes = [c for c, _ in rows]
    dup = sorted({c for c in classes if classes.count(c) > 1})
    if dup:
        fail(f"acute-findings.md §3 table lists {dup} more than once")
    if set(classes) != set(enum) or len(enum) != 10:
        fail(f"acute-findings.md §3 table classes {sorted(set(classes))} ≠ schema finding_class enum "
             f"{sorted(enum)} (expected the 10 pinned values)")
    try:
        import validate_structured_outputs as vso
        for c, default in rows:
            if vso.ACUTE_CLASS_DEFAULT.get(c) != default:
                fail(f"acute-findings.md §3: {c} default {default!r} ≠ validator ACUTE_CLASS_DEFAULT "
                     f"{vso.ACUTE_CLASS_DEFAULT.get(c)!r}")
    except ImportError as e:
        fail(f"cannot import scripts/validate_structured_outputs.py: {e}")

# ---- E. phase1 §5 `## 不确定字段` example ⊆ validator vocabulary
sec = re.search(r"^## 5\. .*?$(.*?)^## 6\. ", p1, re.S | re.M)
if not sec:
    fail("organizer-prompt-phase1-ocr.md has no `## 5.` … `## 6.` section")
else:
    try:
        import validate_structured_outputs as vso
        vocab = {"field_class": vso.UNCERTAIN_FIELD_CLASSES, "layout": vso.UNCERTAIN_LAYOUTS}
    except (ImportError, AttributeError) as e:
        fail(f"validate_structured_outputs.py has no uncertainty vocabulary: {e}")
        vocab = {}
    for key, allowed in vocab.items():
        m = re.search(rf"^\s*{key}:\s*\S+\s*#\s*(.+)$", sec.group(1), re.M)
        if not m:
            fail(f"phase1 §5 example has no `{key}: <value>  # a | b …` line")
            continue
        listed = [mm.group(1) for mm in (re.match(r"\s*`?([a-z][a-z_]*)", piece) for piece in m.group(1).split("|")) if mm]
        extra = [v for v in listed if v not in allowed]
        if not listed or extra:
            fail(f"phase1 §5 {key} values {listed} include {extra or 'nothing parseable'} — not in the validator's "
                 f"{'UNCERTAIN_FIELD_CLASSES' if key == 'field_class' else 'UNCERTAIN_LAYOUTS'} {list(allowed)}")

# ---- F. stale-source sentence ↔ source_freshness.STALE_WARNING_TEMPLATE
try:
    import source_freshness as sfm
    tmpl = sfm.STALE_WARNING_TEMPLATE
except (ImportError, AttributeError) as e:
    fail(f"scripts/source_freshness.py has no STALE_WARNING_TEMPLATE: {e}")
    tmpl = None
if tmpl:
    slot = r"[^，；。\s]+"
    pat = re.compile(re.escape(tmpl).replace(re.escape("{latest}"), slot).replace(re.escape("{days}"), slot))
    F_FILES = sorted((org / "references").glob("*.md")) + [org / "SKILL.md"]
    for f in F_FILES:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            if "距本次整理" in line and not pat.search(line):
                fail(f"{f.relative_to(org)}:{i} quotes a stale-source sentence that is not "
                     f"source_freshness.STALE_WARNING_TEMPLATE ({tmpl!r})")
    # the template itself, placeholders and all, where Phase 2 and the orchestrator read it
    p2 = (org / "references" / "organizer-prompt-phase2-synthesis.md").read_text(encoding="utf-8")
    sec = re.search(r"^### 6\.2 .*?$(.*?)(?=^##)", p2, re.S | re.M)
    blocks = re.findall(r"```text\n(.*?)```", sec.group(1), re.S) if sec else []
    if not any(tmpl in b.splitlines() for b in blocks):
        fail("organizer-prompt-phase2-synthesis.md §6.2 has no ```text block holding "
             f"source_freshness.STALE_WARNING_TEMPLATE verbatim ({tmpl!r})")
    step8 = [l for l in (org / "SKILL.md").read_text(encoding="utf-8").splitlines() if l.startswith("8. ")]
    if not any(tmpl in l for l in step8):
        fail(f"SKILL.md Step 8 does not quote source_freshness.STALE_WARNING_TEMPLATE verbatim ({tmpl!r})")
    pps = root_refs / "patient-profile-schema.md"
    try:
        doc = pps.read_text(encoding="utf-8")
        sec = re.search(r"^## readiness\.json\s*$(.*?)(?=^## |\Z)", doc, re.S | re.M)
        ex = json.loads(re.search(r"```json\n(.*?)```", sec.group(1), re.S).group(1))
        want = tmpl.format(latest=ex["latest_source_date"], days=ex["days_since_latest"])
        got = (ex.get("warnings") or [None])[0]
        if got != want:
            fail(f"{pps.name} readiness example warnings[0] {got!r} ≠ STALE_WARNING_TEMPLATE filled with "
                 f"the example's own date and day count ({want!r})")
    except (OSError, AttributeError, KeyError, ValueError) as e:
        fail(f"{pps}: cannot read the ## readiness.json ```json example: {e!r}")

# ---- G. run_mode vocabulary: phase2 §0 lists FULL_RUN_MODES; the retired boolean is gone
try:
    import validate_structured_outputs as vso
    full_modes = list(vso.FULL_RUN_MODES)
except (ImportError, AttributeError) as e:
    fail(f"validate_structured_outputs.py has no FULL_RUN_MODES: {e}")
    full_modes = []
p2 = (org / "references" / "organizer-prompt-phase2-synthesis.md").read_text(encoding="utf-8")
sec = re.search(r"^## 0\. .*?$(.*?)^## 1\. ", p2, re.S | re.M)
start = sec.group(1).find("`run_mode`（") if sec else -1
end = sec.group(1).find("`as_of_run_date`", start) if start >= 0 else -1
if start < 0 or end < 0:
    fail("organizer-prompt-phase2-synthesis.md §0 Call parameters have no `run_mode`（…）list before `as_of_run_date`")
else:
    listed = sec.group(1)[start:end]
    missing = [m for m in full_modes if f"`{m}`" not in listed]
    if missing:
        fail(f"phase2 §0 run_mode list lacks {missing} — validate_structured_outputs.FULL_RUN_MODES {full_modes} "
             "are the runs that re-transcribe every sidecar")
retired = re.compile(r"`?legacy_upgrade`?\s*（\s*布尔|`?legacy_upgrade`?\s*[:：=]\s*`?true", re.I)
for f in [org / "SKILL.md"] + sorted((org / "references").rglob("*.md")):
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
        if retired.search(line):
            fail(f"{f.relative_to(org)}:{i} documents the retired boolean legacy_upgrade parameter — "
                 "a legacy upgrade is run_mode legacy_upgrade")

# ---- H. acute-findings.md §4.1 pinned words ↔ validator constants
try:
    import validate_structured_outputs as vso
    want_h = {"source_wording_chronic": list(vso.ACUITY_BASIS_TOKENS["source_wording_chronic"]),
              "source_critical_flag": list(vso.ACUITY_BASIS_TOKENS["source_critical_flag"]),
              "chronic_classes": list(vso.CHRONIC_ADJUSTABLE_CLASSES),
              "thrombus_unchanged": list(vso.THROMBUS_STABLE_TOKENS),
              "escalation_obstructive_only": list(vso.OBSTRUCTIVE_ONLY_ESCALATION),
              "obstructive_words": list(vso.OBSTRUCTIVE_WORDS)}
    for cls_, (target, toks) in vso.ESCALATION_ROUTES.items():
        want_h[f"escalation_{cls_}"] = [target] + list(toks)
except (ImportError, AttributeError, KeyError) as e:
    fail(f"validate_structured_outputs.py has no acuity token constants: {e}")
    want_h = {}
sec = re.search(r"^### 4\.1 .*?$(.*?)(?=^## )", af, re.S | re.M)
block = re.search(r"```text\n(.*?)```", sec.group(1), re.S) if sec else None
if want_h and not block:
    fail("acute-findings.md has no `### 4.1` section with a ```text block of pinned acuity words")
elif want_h:
    got_h = {}
    for line in block.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep:
            got_h[k.strip()] = [x.strip() for x in v.split("|") if x.strip()]
    for k, v in want_h.items():
        if got_h.get(k) != v:
            fail(f"acute-findings.md §4.1 `{k}:` lists {got_h.get(k)} ≠ validator {v}")
    extra = sorted(set(got_h) - set(want_h))
    if extra:
        fail(f"acute-findings.md §4.1 block has keys the validator does not know: {extra}")

# ---- I. phase1 §3 READ_MODE / ADAPTER / MODALITY rows ↔ validator header vocabularies
sec3 = re.search(r"^## 3\. .*?$(.*?)^## 4\. ", p1, re.S | re.M)
try:
    import validate_structured_outputs as vso
    rows_i = {"READ_MODE": list(vso.SIDECAR_READ_MODES), "ADAPTER": list(vso.SIDECAR_ADAPTERS),
              "MODALITY": list(vso.SIDECAR_MODALITIES)}
except (ImportError, AttributeError) as e:
    fail(f"validate_structured_outputs.py has no header vocabularies: {e}")
    rows_i = {}
for key, want in rows_i.items():
    row = re.search(rf"^\|\s*`{key}`\s*\|(.*)\|\s*$", sec3.group(1), re.M) if sec3 else None
    if not row:
        fail(f"phase1 §3 table has no `{key}` row")
        continue
    listed = re.findall(r"`([a-z_]+)`", row.group(1))
    if listed != want:
        fail(f"phase1 §3 {key} values {listed} ≠ validator {want}")

# ---- J. every script call a worker or the orchestrator runs resolves against <skill_dir>
#      (subagents do not run in the skill directory; SKILL.md Workflow note)
docs_j = [org / "SKILL.md"] + sorted((org / "references").glob("*.md")) + sorted((org / "references" / "runtime-bindings").glob("*.md"))
call_j = re.compile(r"python3\s+(\S+?\.py)")
for f in docs_j:
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
        for m in call_j.finditer(line):
            target = m.group(1).strip("\"'`")
            if "scripts/" in target and not target.startswith(("<skill_dir>/scripts/",
                                                                 "<skill_dir>/../cancer-buddy-charts/scripts/")):
                fail(f"{f.relative_to(org)}:{i} runs {target} without the <skill_dir>/ prefix "
                     "(write python3 \"<skill_dir>/scripts/<script>.py\" or "
                     "\"<skill_dir>/../cancer-buddy-charts/scripts/<script>.py\")")

# ---- L. a recursive rm never names $src, raw/ or the patient directory (patient originals)
rm_cmd = re.compile(r"(?<![\w-])rm\s+((?:-[A-Za-z]+\s+)+)([^;&|#\n]*)")
arg_tok = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')
protected = re.compile(r"\$\{?src\b|(?:^|[/\"'])raw(?:[/\"']|$)|<patient_dir>|\$\{?patient_dir\b")
for f in docs_j:
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
        for m in rm_cmd.finditer(line):
            if not re.search(r"[rR]", m.group(1)):
                continue
            for tok in arg_tok.findall(m.group(2)):
                if protected.search(tok):
                    fail(f"{f.relative_to(org)}:{i} runs a recursive rm on {tok} — $src may be the user's input "
                         "folder or the raw/ vault; only an archive's temp unpack_dir is ever removed (SKILL.md Step 17)")

# ---- K. the untrusted-content severity row equals what scan_untrusted_markers.py emits
try:
    import scan_untrusted_markers as sum_
    src_k = Path(sum_.__file__).read_text(encoding="utf-8")
    emits = re.search(r'"severity":\s*"yellow" if worst == "high" else "info"', src_k) is not None
except ImportError as e:
    fail(f"scan_untrusted_markers.py not importable: {e}")
    emits = None
row_k = next((l for l in p2.splitlines() if l.startswith("| 不可信内容标记")), None)
if emits and (row_k is None or "high → `yellow`" not in row_k or "`info`" not in row_k):
    fail("phase2 §6.1 has no 不可信内容标记 row stating the scanner's grading (worst hit high → yellow, else info)")

# ---- M. the pinned 段D stale notice ↔ validate_structured_outputs.CASE_SUMMARY_STALE_NOTICE
try:
    import validate_structured_outputs as vso_m
    notice_m = vso_m.CASE_SUMMARY_STALE_NOTICE
except Exception as e:
    fail(f"validate_structured_outputs.py has no CASE_SUMMARY_STALE_NOTICE: {e}")
    notice_m = None
if notice_m is not None:
    sec_m = re.search(r"^## 7\. .*?$(.*?)^## 8\. ", p2, re.S | re.M)
    blocks_m = re.findall(r"```text\n(.*?)```", sec_m.group(1), re.S) if sec_m else []
    if not any(notice_m in b for b in blocks_m):
        fail("organizer-prompt-phase2-synthesis.md §7 has no ```text block holding "
             f"validate_structured_outputs.CASE_SUMMARY_STALE_NOTICE verbatim ({notice_m!r})")

# ---- N. the 段D lead and the translation labels ↔ validate_structured_outputs constants
try:
    import validate_structured_outputs as vso_n
    lead_n, mark_n = vso_n.ACUTE_SUMMARY_LEAD, vso_n.ACUTE_LEAD_TRANSLATION_MARK
    cav_n = vso_n.ACUTE_CAVEAT_TRANSLATION_PREFIX
except Exception as e:
    fail(f"validate_structured_outputs.py has no ACUTE_SUMMARY_LEAD / ACUTE_LEAD_TRANSLATION_MARK / "
         f"ACUTE_CAVEAT_TRANSLATION_PREFIX: {e}")
    lead_n = None
if lead_n is not None:
    csp = (org / "references" / "case-summary-html-prompt.md").read_text(encoding="utf-8")
    sec_n = re.search(r"^- 急性/附带发现(.*?)^- 旧档案摘录", csp, re.S | re.M)
    body_n = sec_n.group(1) if sec_n else ""
    if not sec_n:
        fail("case-summary-html-prompt.md has no 「- 急性/附带发现」 bullet (followed by 「- 旧档案摘录」)")
    else:
        if f"“{lead_n}<label>（<日期>）" not in body_n:
            fail("case-summary-html-prompt.md 急性/附带发现 does not teach the lead "
                 f"validate_structured_outputs.ACUTE_SUMMARY_LEAD verbatim ({lead_n!r} followed by <label>（<日期>）)")
        if "报告原文写到需要尽快告知治疗团队" in body_n:
            fail("case-summary-html-prompt.md 急性/附带发现 still teaches the retired lead 「资料中有报告原文写到…」 — a "
                 "translated finding is in the same list, so the lead is neutral (acute-findings.md §2.4)")
        if f"<label>（<日期>，{mark_n}）" not in body_n:
            fail(f"case-summary-html-prompt.md 急性/附带发现 does not teach the translated item form 「<label>（<日期>，{mark_n}）」")
        if cav_n not in body_n:
            fail("case-summary-html-prompt.md 急性/附带发现 does not teach the caveat prefix "
                 f"validate_structured_outputs.ACUTE_CAVEAT_TRANSLATION_PREFIX ({cav_n!r})")
    # phase2 §7 tells Phase 2 which renders count as "not written" by quoting the same lead
    sec_n7 = re.search(r"^## 7\. .*?$(.*?)^## 8\. ", p2, re.S | re.M)
    if not sec_n7 or f"“{lead_n}”开头" not in sec_n7.group(1):
        fail("organizer-prompt-phase2-synthesis.md §7 段D 过期提示 does not quote "
             f"validate_structured_outputs.ACUTE_SUMMARY_LEAD verbatim ({lead_n!r}) as the lead a current render starts with")

# ---- N (rule). The caveat check itself, not only its strings: the prompt states the validator's item-scoped rule
# (ACUTE_CAVEAT_ITEM_RULE, whitespace-insensitive — it lists ACUTE_CAVEAT_ORIGINAL_CLAIMS) and one caveat item per
# finding, not the retired quotation-slot rule; and the prompt's own two caveat forms behave as the prompt says when run
# through translated_caveat_problems — the translated form passes, the 报告原文 form rejects a translated quote, a
# translated finding's words inside another finding's correctly quoted original are no quote of it (also when that
# original holds a colon or a quote mark before them), and every form that presents a rendering as the report's words
# (报告原文写明…, 外院报告原文提示…, 报告原文：<AF1>（…）<AF2>, any listed claim next to the prefix) is rejected.
def _ws(s):
    return re.sub(r"\s+", "", s)


if lead_n is not None and sec_n:
    try:
        item_rule = vso_n.ACUTE_CAVEAT_ITEM_RULE
        claims_n = vso_n.ACUTE_CAVEAT_ORIGINAL_CLAIMS
        tcp = vso_n.translated_caveat_problems
    except Exception as e:
        fail("validate_structured_outputs.py has no ACUTE_CAVEAT_ITEM_RULE / ACUTE_CAVEAT_ORIGINAL_CLAIMS / "
             f"translated_caveat_problems: {e}")
        item_rule = None
    if item_rule is not None:
        wb = _ws(body_n)
        if _ws(item_rule) not in wb:
            fail("case-summary-html-prompt.md 急性/附带发现 does not state the item-scoped caveat rule "
                 f"validate_structured_outputs.ACUTE_CAVEAT_ITEM_RULE ({item_rule!r})")
        if "引文位置（冒号或开引号之后" in wb:
            fail("case-summary-html-prompt.md 急性/附带发现 still states the retired quotation-slot rule — the validator "
                 "checks each caveat item whole (ACUTE_CAVEAT_ITEM_RULE)")
        if "一条发现单独一条caveat" not in wb:
            fail("case-summary-html-prompt.md 急性/附带发现 does not require one caveat item per finding (「一条发现单独一条 "
                 "caveat」) — the item-scoped check reads a caveat holding a translated finding's words as that finding's")
        forms = re.findall(r"“([^“”]*<verbatim_text>[^“”]*)”", wb)
        tr_forms = [f for f in forms if cav_n + "<verbatim_text>" in f]
        orig_forms = [f for f in forms if "报告原文：<verbatim_text>" in f]
        if not tr_forms or not orig_forms:
            fail("case-summary-html-prompt.md 急性/附带发现 lacks a caveat form with 「" + cav_n + "<verbatim_text>」 or one with "
                 "「报告原文：<verbatim_text>」 (the two forms the validator's caveat check is run on)")
        else:
            def inst(form, quote, day):
                return form.replace("<verbatim_text>", quote).replace("<日期>", day).replace("<来源文书>", "示例报告")

            q_tr, q_long = "示例充盈缺损", "示例左肺动脉分支示例充盈缺损待查"
            f_tr = {"finding_id": "AF-T", "verbatim_text": q_tr, "verbatim_is_translation": True,
                    "exam_date": "2030-01-05", "acuity": "incidental"}
            f_orig = {"finding_id": "AF-O", "verbatim_text": q_long, "exam_date": "2030-01-12", "acuity": "urgent"}

            def probs(findings, *caveats):
                return tcp({"findings": findings}, {"caveats": [{"caveat_text": c} for c in caveats]})

            if probs([f_tr], inst(tr_forms[0], q_tr, "2030-01-05")):
                fail("the prompt's translated caveat form 「" + tr_forms[0] + "」 is rejected by translated_caveat_problems")
            if not probs([f_tr], inst(orig_forms[0], q_tr, "2030-01-05")):
                fail("the prompt's 报告原文 caveat form 「" + orig_forms[0] + "」 quoting a translated finding passes "
                     "translated_caveat_problems")
            if probs([f_tr, f_orig], inst(orig_forms[0], q_long, "2030-01-12"), inst(tr_forms[0], q_tr, "2030-01-05")):
                fail("a translated finding's words inside another finding's 报告原文 quote (the prompt's form) are "
                     "reported as a quote of the translated finding")
            # a colon or a quote mark inside that other finding's original opens nothing (the retired slot parser
            # read one as a new quotation and rejected the prompt's own 报告原文 form)
            for vt in ("诊断意见：示例充盈缺损（考虑示例）", "印象：示例充盈缺损。请结合临床", "结论：示例充盈缺损；建议复查",
                       "提示“示例充盈缺损”。请结合临床"):
                if probs([f_tr, dict(f_orig, verbatim_text=vt)], inst(orig_forms[0], vt, "2030-01-12"),
                         inst(tr_forms[0], q_tr, "2030-01-05")):
                    fail(f"the prompt's 报告原文 form quoting another finding's original 「{vt}」 (a colon / quote mark "
                         "before the translated words) is reported as a quote of the translated finding")
            # forms that present the rendering as the report's own words are rejected wherever the colon sits
            bypass = [f"报告原文写明{q_tr}（2030-01-05，示例报告）", f"外院报告原文提示{q_tr}（2030-01-05）",
                      inst(orig_forms[0], q_long, "2030-01-12") + q_tr]
            bypass += [f"{c}：{cav_n}{q_tr}（2030-01-05，示例报告）" for c in claims_n]
            for form in bypass:
                if not probs([f_tr, f_orig], form):
                    fail(f"「{form}」 presents the translated finding as the report's own words and passes "
                         "translated_caveat_problems")

# ---- N (surfaces). Every surface that shows acute findings labels a translation: profile-card.md (Step 11) says
# 中文转述，非报告原句 and no longer calls every finding 「报告原文写明的」; acute-findings.md §2.4 lists Step 11 among the
# surfaces. And a .case_summary_data.json ERROR routes to the 段D re-render: SKILL.md Step 12, phase2 §9 (the error
# Phase 2 may leave) and phase2 §10 (case_summary_rerender_required) all name 「ERROR: .case_summary_data.json」.
pc = (org / "references" / "profile-card.md").read_text(encoding="utf-8")
pc_acute = next((b for b in re.split(r"\n(?=- )", pc) if "acute_findings.json" in b), "")
if "中文转述，非报告原句" not in _ws(pc_acute):
    fail("profile-card.md: the acute-findings bullet does not label a verbatim_is_translation finding "
         "「中文转述，非报告原句」 (acute-findings.md §2.4)")
if "报告原文写明的急性" in _ws(pc):
    fail("profile-card.md still presents every acute finding as 「报告原文写明的」 — a translation is not the report's words")
af_md = (org / "references" / "acute-findings.md").read_text(encoding="utf-8")
m_sf = re.search(r"\*\*转述不是原文\*\*：.*?任何展示面（([^）]*)）", af_md, re.S)
if not m_sf or "Step 11" not in m_sf.group(1):
    fail("acute-findings.md §2.4 「转述不是原文」 does not list Step 11 (the Profile Card) among the display surfaces")
ROUTE = "ERROR: .case_summary_data.json"
vso_src = (org / "scripts" / "validate_structured_outputs.py").read_text(encoding="utf-8")
step12 = next((l for l in (org / "SKILL.md").read_text(encoding="utf-8").splitlines() if l.startswith("12. ")), "")
if ROUTE not in step12:
    fail(f"SKILL.md Step 12 does not make a validator line 「{ROUTE}」 a 段D re-render trigger")
sec9 = re.search(r"^## 9\. .*?$(.*?)^## 10\. ", p2, re.S | re.M)
if not sec9 or ROUTE not in sec9.group(1):
    fail(f"organizer-prompt-phase2-synthesis.md §9 does not name 「{ROUTE}」 lines as errors Phase 2 leaves for Step 12")
elif "the pinned stale notice" not in sec9.group(1) or "the pinned stale notice" not in vso_src:
    fail("organizer-prompt-phase2-synthesis.md §9 lets Phase 2 leave every .case_summary_data.json ERROR without "
         "excepting the validator's 'the pinned stale notice … is missing' line — that one is Phase 2's own §7 notice")
rr = next((l for l in p2.splitlines() if l.startswith("- `case_summary_rerender_required`")), "")
if ROUTE not in rr:
    fail(f"organizer-prompt-phase2-synthesis.md §10 case_summary_rerender_required is not true on a 「{ROUTE}」 line")

sys.exit(min(bad, 100))
PY
errs=$((errs + rc))
summarize "organize-prompt-contracts"
