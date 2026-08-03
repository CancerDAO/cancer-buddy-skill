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

Only two placeholders are injected, copied verbatim from `profile.json` — no LLM
synthesis:
    {{patient_code}}       <- profile.json.patient_code
    {{one_line_condition}} <- profile.json.summary.one_line_condition ("资料缺失" when null)

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

DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "references" / "templates" / "agents-md.template.md"
)

MISSING_PLACEHOLDER = "资料缺失"
ONE_LINE_MAX = 120

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


def template_sha256(template_text: str) -> str:
    return hashlib.sha256(template_text.encode("utf-8")).hexdigest()


def render(template_text: str, patient_code: str, one_line: str) -> str:
    out = template_text.replace("{{patient_code}}", patient_code)
    out = out.replace("{{one_line_condition}}", one_line)
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

    patient_dir = Path(args.patient_dir)
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

    out_path = Path(args.out) if args.out else patient_dir / "AGENTS.md"

    if args.check:
        if not out_path.is_file():
            print(f"[fill_agents_md] ERROR: {out_path} not found (nothing to check)", file=sys.stderr)
            return 2
        text = out_path.read_text(encoding="utf-8")
        action = "checked"
    else:
        one_line = sanitize_one_line((profile.get("summary") or {}).get("one_line_condition"))
        text = render(template_text, patient_code, one_line)
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
