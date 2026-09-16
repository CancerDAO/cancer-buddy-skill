#!/usr/bin/env python3
"""Deterministically fill <patient_dir>/AGENTS.md from the organize template.

Replaces the inline python heredoc that used to live in
`skills/cancer-buddy-organize/SKILL.md` (段 13). Two reasons it is a script and
not prose:

  1. **Non-stub assertion.** `SKILL.md`'s "VERIFY, don't re-author" was a purely
     verbal obligation, and a stub AGENTS.md has been produced historically. The
     assertions here are mechanical: zero residual `{{`, the routing table and
     the three inlined red lines present, first line carrying the real
     patient_code, and patient_code matching `profile.json`.
  2. **Guardrail integrity.** A session whose cwd is inside the patient dir may
     answer from the archive with NO cancer-buddy skill loaded — the generated
     AGENTS.md is then the ONLY safety text in context. The template inlines the
     three red lines in full; this script stamps
     `<!-- generated-by: fill_agents_md.py | template_sha256: <hex> -->`
     (same provenance mechanism as `render_html_template.py`) so a reviewer can
     prove which template text is actually on disk in the archive.

Three placeholders are injected, all copied or counted from archive JSON — no LLM
synthesis:
    {{patient_code}}                 <- profile.json.patient_code
    {{one_line_condition}}           <- profile.json.summary.one_line_condition ("资料缺失" when null)
    {{projection_coverage_summary}}  <- readiness.json.projection_coverage.summary, rendered as
                                        counts only. Numbers, never the per-source note strings:
                                        the notes are model-written text and this file is
                                        auto-loaded by any session whose cwd is the archive.
                                        Absent/malformed readiness.json renders an explicit
                                        "未量化" line — a missing coverage number must look
                                        missing, never like zero gaps.

`one_line_condition` is patient/report text flowing into a file that harnesses
auto-load, so it is sanitized on the way in (single line, no markdown heading /
HTML comment / template markers, length-capped). Sanitizing is not a claim the
content is trusted — red line 3 in the template states archive text is data.

CLI:
    python3 fill_agents_md.py <patient_dir>            # fill + assert + write
    python3 fill_agents_md.py <patient_dir> --check    # assert an existing AGENTS.md, write nothing
    python3 fill_agents_md.py <patient_dir> --template <path> [--out <path>]

Exit codes:
    0 — written (or checked) and every assertion holds
    1 — assertion failed (stub / unfilled placeholder / wrong patient / template drift)
    2 — bad invocation, unreadable input, missing file
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _pathsafe  # noqa: E402

DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "references" / "templates" / "agents-md.template.md"
)

MISSING_PLACEHOLDER = "资料缺失"
ONE_LINE_MAX = 120

# fix spec A34. `patient_code` is read from profile.json — a file the pipeline writes but
# whose content originates in model output — and it is then interpolated into AGENTS.md,
# which every session opened inside the archive auto-loads. Two things go wrong without a
# hard shape:
#   * it lands in the first line, which assert_non_stub() compares literally, so a code
#     containing a newline produces a file whose "first line" is attacker-chosen;
#   * it is the archive's identity, and a code that does not look like one is a sign the
#     profile is not the profile for this directory.
# The canonical form is `PT-` + uppercase hex (the code is derived from a hash), with an
# optional `_N` disambiguator. This is a WHITELIST: anything else is refused, not repaired.
PATIENT_CODE_RE = re.compile(r"^PT-[A-F0-9]+(_\d+)?$")

PROVENANCE_FMT = "<!-- generated-by: fill_agents_md.py | template_sha256: {sha} -->"
PROVENANCE_RE = re.compile(r"<!--\s*generated-by: fill_agents_md\.py \| template_sha256: ([0-9a-f]{64})\s*-->")

# Structural lines that prove the FULL template was written, not a stub. Each is a
# substring that must appear verbatim in the rendered AGENTS.md.
REQUIRED_ROUTING = [
    "## Read order",
    "## Domain map",
    "## Non-negotiable rules",
    "`profile.json`",
    "`source_inventory.json`",
    "`patient_summary.json`",
    "`molecular.json`",
    "`treatment_lines.json`",
    "`labs.json`",
    "`longitudinal_observations.json`",
    "`missing_items.json`",
    "`readiness.json.review_flags`",
    "`readiness.json.projection_coverage`",
    "`extracted_fields.json`",
    "15_未分类资料",
    "clinical_class",
    "Projection coverage:",
    "Never open the verbatim transcript vault",
]

# The three inlined red lines (§6.3 mitigation (b)). If any of these is missing the
# generated file is NOT a safe floor and the run must fail — the whole point of the
# inlining is that a bare session sees this text.
REQUIRED_GUARDRAILS = [
    ("no-silent-snapshot", "Red line 1"),
    ("no-silent-snapshot", "at the moment you answer"),
    ("no-silent-snapshot", "需现场核实"),
    ("no-silent-snapshot", "Never LLM-synthesize the evidence"),
    ("no-case-adjudication", "Red line 2"),
    ("no-case-adjudication", "No individual-case adjudication"),
    ("no-case-adjudication", "prognosis or survival numbers"),
    ("data-not-instructions", "Red line 3"),
    ("data-not-instructions", "data, not instructions"),
    ("data-not-instructions", "reported, not"),
]

MIN_LINES = 60


def sanitize_one_line(raw: object) -> str:
    """Collapse an archive-sourced string into one safe markdown line."""
    if raw is None:
        return MISSING_PLACEHOLDER
    text = str(raw)
    # Kill anything that could restructure the document or re-open templating.
    text = text.replace("<!--", " ").replace("-->", " ")
    text = text.replace("{{", " ").replace("}}", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Leading markdown block markers would turn the label into a heading/list/quote.
    text = re.sub(r"^[#>\-*+=|`]+\s*", "", text).strip()
    if len(text) > ONE_LINE_MAX:
        text = text[: ONE_LINE_MAX - 1].rstrip() + "…"
    return text or MISSING_PLACEHOLDER


COVERAGE_MISSING = (
    "未量化 — readiness.json 无 projection_coverage；"
    "不要把「结构化 JSON 里没有」读成「档案里没有」"
)


def projection_coverage_summary(patient_dir: Path) -> str:
    """One line of COUNTS from readiness.json.projection_coverage.summary.

    Counts only. The per-source `note` strings are model-written text and this file is
    auto-loaded by any session opened inside the archive, so nothing free-form from the
    archive goes in beyond the already-sanitized one-line label. A missing or malformed
    coverage block renders an explicit "未量化" rather than silently reading as "no gaps" —
    the entire point of the field is that absence must be visible.
    """
    readiness = patient_dir / "readiness.json"
    if not readiness.is_file():
        return COVERAGE_MISSING
    try:
        data = json.loads(readiness.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return COVERAGE_MISSING
    cov = data.get("projection_coverage") if isinstance(data, dict) else None
    summary = cov.get("summary") if isinstance(cov, dict) else None
    if not isinstance(summary, dict):
        return COVERAGE_MISSING
    vals = {}
    for key in ("sources_total", "sources_fully_projected", "novel_sources", "unreadable_sources"):
        v = summary.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            return COVERAGE_MISSING
        vals[key] = v
    partial = max(vals["sources_total"] - vals["sources_fully_projected"], 0)
    return (
        f"{vals['sources_fully_projected']}/{vals['sources_total']} 源已完整投影；"
        f"{partial} 源有已转写但未进结构化的字段类（见 readiness.json.projection_coverage.per_source）；"
        f"novel {vals['novel_sources']}；unreadable {vals['unreadable_sources']}（unreadable 永远不算已覆盖）"
    )


def template_sha256(template_text: str) -> str:
    return hashlib.sha256(template_text.encode("utf-8")).hexdigest()


def render(template_text: str, patient_code: str, one_line: str, coverage: str) -> str:
    """Fill the three placeholders in ONE pass (fix spec A34).

    Chained `str.replace` calls are sequential rewrites of the whole document, so each
    substitution's OUTPUT is the next one's input: a `one_line_condition` containing the
    literal text `{{projection_coverage_summary}}` was expanded by the following call, and
    archive-sourced text chose what the coverage line said. sanitize_one_line() already
    strips `{{`/`}}`, but defence-in-depth here is one regex: a single re.sub with a
    callback consumes every placeholder simultaneously and never re-examines what it wrote.
    """
    values = {
        "patient_code": patient_code,
        "one_line_condition": one_line,
        "projection_coverage_summary": coverage,
    }
    out = re.sub(
        r"\{\{(patient_code|one_line_condition|projection_coverage_summary)\}\}",
        lambda m: values[m.group(1)],
        template_text,
    )
    if not out.endswith("\n"):
        out += "\n"
    return out + PROVENANCE_FMT.format(sha=template_sha256(template_text)) + "\n"


def assert_non_stub(text: str, patient_code: str, template_text: str) -> list[str]:
    """Return a list of violation strings; empty list == the file is a real fill."""
    errs: list[str] = []

    lines = text.splitlines()
    if len(lines) < MIN_LINES:
        errs.append(f"stub: only {len(lines)} lines (expected >= {MIN_LINES})")

    if "{{" in text or "}}" in text:
        residual = sorted(set(re.findall(r"\{\{[^}\n]*\}\}", text))) or ["<bare braces>"]
        errs.append(f"unresolved placeholder(s): {', '.join(residual)}")

    expected_head = f"# Patient archive pointer: {patient_code}"
    if not lines or lines[0].strip() != expected_head:
        got = lines[0].strip() if lines else "<empty file>"
        errs.append(f"first line must be '{expected_head}', got '{got}'")

    for needle in REQUIRED_ROUTING:
        if needle not in text:
            errs.append(f"routing table incomplete: missing {needle!r}")

    for guard, needle in REQUIRED_GUARDRAILS:
        if needle not in text:
            errs.append(f"guardrail {guard} not inlined: missing {needle!r}")

    m = PROVENANCE_RE.search(text)
    if not m:
        errs.append("missing provenance comment (template_sha256)")
    elif m.group(1) != template_sha256(template_text):
        errs.append(
            f"template_sha256 mismatch: file={m.group(1)[:12]}… template={template_sha256(template_text)[:12]}…"
        )

    return errs


def load_profile(patient_dir: Path) -> dict:
    profile_path = patient_dir / "profile.json"
    if not profile_path.is_file():
        raise SystemExit(f"[fill_agents_md] ERROR: {profile_path} not found")
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"[fill_agents_md] ERROR: cannot read {profile_path}: {exc}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fill <patient_dir>/AGENTS.md from the organize template.")
    ap.add_argument("patient_dir", help="patient archive directory (contains profile.json)")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="agents-md template path")
    ap.add_argument("--out", default=None, help="output path (default <patient_dir>/AGENTS.md)")
    ap.add_argument(
        "--check",
        action="store_true",
        help="assert an existing AGENTS.md instead of writing one (no side effects)",
    )
    args = ap.parse_args(argv)

    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(f"[fill_agents_md] ERROR: {patient_dir} is not a directory", file=sys.stderr)
        return 2

    template_path = Path(args.template)
    if not template_path.is_file():
        print(f"[fill_agents_md] ERROR: template {template_path} not found", file=sys.stderr)
        return 2
    template_text = template_path.read_text(encoding="utf-8")

    profile = load_profile(patient_dir)
    patient_code = profile.get("patient_code")
    if not isinstance(patient_code, str) or not patient_code.strip():
        print("[fill_agents_md] ERROR: profile.json has no usable patient_code", file=sys.stderr)
        return 2
    patient_code = patient_code.strip()
    if not PATIENT_CODE_RE.match(patient_code):
        print(
            f"[fill_agents_md] ERROR: patient_code {patient_code!r} does not match "
            f"{PATIENT_CODE_RE.pattern} — it is written into the first line of a file every "
            "session in this archive auto-loads, and it is the archive's identity. Refusing "
            "rather than sanitizing: a repaired code would no longer identify the archive",
            file=sys.stderr,
        )
        return 2

    out_path = Path(args.out).resolve() if args.out else patient_dir / "AGENTS.md"
    # --out is the file this script WRITES; --template is a file it reads and whose sha it
    # vouches for. Both are containment-checked (fix spec A34/A9): `--out ../../AGENTS.md`
    # used to plant a guardrail file, carrying this patient's one_line_condition, in a
    # directory that has nothing to do with this patient.
    try:
        _pathsafe.require_contained(out_path, patient_dir, "--out")
        _pathsafe.require_contained(template_path.resolve(), SCRIPT_DIR.parent, "--template")
    except _pathsafe.PathSafetyError as exc:
        print(f"[fill_agents_md] ERROR: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if not out_path.is_file():
            print(f"[fill_agents_md] ERROR: {out_path} not found (nothing to check)", file=sys.stderr)
            return 2
        text = out_path.read_text(encoding="utf-8")
        action = "checked"
    else:
        one_line = sanitize_one_line((profile.get("summary") or {}).get("one_line_condition"))
        coverage = projection_coverage_summary(patient_dir)
        text = render(template_text, patient_code, one_line, coverage)
        action = "written"

    errs = assert_non_stub(text, patient_code, template_text)
    if errs:
        print(f"[fill_agents_md] FAIL: {out_path}", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if not args.check:
        out_path.write_text(text, encoding="utf-8")

    print(
        f"[fill_agents_md] OK {action}: {out_path} "
        f"({len(text.splitlines())} lines, patient_code={patient_code}, "
        f"template_sha={template_sha256(template_text)[:12]}…)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
