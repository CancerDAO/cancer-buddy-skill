#!/usr/bin/env python3
"""Generic, deterministic HTML template renderer (stdlib only, ZERO medical logic).

This is a dumb, data-driven template engine. It knows NOTHING about cancer,
patients, labs, lesions, or treatment lines. It only understands three marker
syntaxes already present in the templates and expands them from a JSON `data`
object. Whatever the data says — N labs, 0 lesions, a custom locale string — is
exactly what gets rendered. Over-fitting to any one patient is structurally
impossible here: the engine never hard-codes a field name, a count, or a section.

Marker syntax (matching references/templates/*.template.html):

  1. Placeholders            {{key}}  /  {{a.b.c}}  (dotted path into data)
       - Value is HTML-escaped before substitution.
       - Missing key / null / "" → renders data["fallbacks"][key] if present,
         else data["fallbacks"]["__default__"] if present, else "".
       - The {{i18n.*}} namespace is just dotted-path lookup into data["i18n"].

  2. Loop blocks             <!-- LOOP name -->  ...  <!-- END LOOP -->
       - Repeats the inner block once per element of data[name] (an array).
       - 0 elements (missing / [] ) → the whole block renders to nothing.
       - Inside the block, {{field}} resolves against the current array element
         first, then falls back to the outer (top-level) data. This lets a row
         template reference both per-item fields and shared {{i18n.*}} strings.

  3. Conditional blocks      <!-- RENDER_IF name -->  ...  <!-- END RENDER_IF -->
       - Inner block renders only if data[name] is truthy
         (non-empty list/dict/string, non-zero number, True).
       - Pairs with <!-- RENDER_IF_NOT name --> for the inverse (e.g. an
         "资料缺失" placeholder shown only when the data block is empty), so a
         section can ALWAYS render *something* without the engine deleting it.

All three are evaluated recursively (loops/conditionals may nest). HTML comments
themselves are preserved in output (they carry no PII) except the marker lines,
which are consumed. After rendering, the engine self-checks that no live
`{{...}}` placeholder remains (ignoring text inside HTML comments).

Provenance: the rendered output carries, just before </body>, a comment
    <!-- rendered-by: render_html_template.py | template_sha256: <hex> -->
recording the SHA-256 of the template actually used. validate_case_summary_html.py
echoes this `template_sha` so the final hard-gate report can PROVE the case
summary was machine-rendered from the gold-standard template, not hand-written.

CLI:
    python3 render_html_template.py --template <tmpl.html> --data <data.json> --out <out.html>
    python3 render_html_template.py --template <tmpl.html> --data <data.json>   # → stdout

Exit codes:
    0  — rendered OK, no residual placeholders
    1  — residual {{...}} placeholder(s) survived (data contract gap)
    2  — bad invocation / unbalanced markers / unreadable input
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

# Provenance comment injected just before </body>. Carries the SHA-256 of the
# RAW template text, so validate_case_summary_html.py (and the final report) can
# prove the HTML was machine-rendered from the template rather than hand-written.
PROVENANCE_FMT = "<!-- rendered-by: render_html_template.py | template_sha256: {sha} -->"


def template_sha256(template_text: str) -> str:
    """SHA-256 hex of the raw template text — the provenance fingerprint."""
    return hashlib.sha256(template_text.encode("utf-8")).hexdigest()

# ----- marker patterns -------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Block openers/closers live on HTML-comment lines. We tokenize on them.
# An opener may carry a free-text human note after the name, separated by ':' —
# e.g. `<!-- LOOP lesions: 每个部位一行 -->` or `<!-- LOOP path_items: 每条一行,末条不加 <br> -->`.
# That tail is template scaffolding for human readers and is ignored. The tail can
# itself contain '>' (e.g. a literal `<br>`), so it is matched non-greedily up to
# the comment terminator `-->`, constrained to one line ([^\n]) so a malformed
# marker can never swallow the rest of the document. The name group stays the
# first bare token so downstream lookup is unaffected.
_TAIL = r"(?::[^\n]*?)?"
LOOP_OPEN_RE = re.compile(r"<!--\s*LOOP\s+([A-Za-z0-9_.\-]+)\s*" + _TAIL + r"-->")
LOOP_CLOSE_RE = re.compile(r"<!--\s*END\s+LOOP\s*" + _TAIL + r"-->")
IF_OPEN_RE = re.compile(r"<!--\s*RENDER_IF\s+([A-Za-z0-9_.\-]+)\s*" + _TAIL + r"-->")
IF_NOT_OPEN_RE = re.compile(r"<!--\s*RENDER_IF_NOT\s+([A-Za-z0-9_.\-]+)\s*" + _TAIL + r"-->")
IF_CLOSE_RE = re.compile(r"<!--\s*END\s+RENDER_IF\s*" + _TAIL + r"-->")

_MISSING = object()  # sentinel distinct from a real None value


# ----- value lookup ----------------------------------------------------------
def lookup(scope, key: str):
    """Dotted-path lookup. Returns _MISSING if any segment is absent."""
    cur = scope
    for seg in key.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return _MISSING
    return cur


def resolve_placeholder(key: str, local, root) -> str:
    """Resolve {{key}} → escaped string. Tries local element, then root.

    Missing/null → fallbacks[key] → fallbacks.__default__ → "".
    An EXPLICIT empty string ("") is the author's intentional "render nothing
    here" (e.g. a {{line_marker_class}} that means "no extra CSS class"); it is
    rendered as "" and NEVER replaced by a fallback — otherwise the placeholder
    text ("资料缺失") would leak into a class="..." attribute on every normal
    (non-pending) treatment line / lab and corrupt the markup. Use null/omit the
    key when you want the placeholder; use "" when you want empty.
    """
    val = _MISSING
    if local is not None and local is not root:
        val = lookup(local, key)
    if val is _MISSING:
        val = lookup(root, key)

    # explicit "" → author wants empty; render it, no fallback.
    if isinstance(val, str) and val == "":
        return ""

    if val is _MISSING or val is None:
        fb = root.get("fallbacks") if isinstance(root, dict) else None
        if isinstance(fb, dict):
            if key in fb and fb[key] not in (None, ""):
                return html.escape(str(fb[key]))
            if fb.get("__default__"):
                return html.escape(str(fb["__default__"]))
        return ""

    if isinstance(val, bool):
        val = "true" if val else "false"
    elif isinstance(val, (int, float)):
        val = str(val)
    elif not isinstance(val, str):
        # arrays/objects are not directly placeholder-able; stringify defensively
        val = json.dumps(val, ensure_ascii=False)
    return html.escape(val)


def substitute_placeholders(text: str, local, root) -> str:
    return PLACEHOLDER_RE.sub(lambda m: resolve_placeholder(m.group(1), local, root), text)


def is_truthy(scope, key: str) -> bool:
    val = lookup(scope, key)
    if val is _MISSING or val is None:
        return False
    if isinstance(val, (list, dict, str)):
        return len(val) > 0
    return bool(val)


# ----- block parsing (recursive descent over marker tokens) ------------------
class Token:
    __slots__ = ("kind", "name", "raw", "start", "end")

    def __init__(self, kind, name, raw, start, end):
        self.kind = kind      # 'loop_open' | 'loop_close' | 'if_open' | 'ifnot_open' | 'if_close'
        self.name = name
        self.raw = raw
        self.start = start
        self.end = end


_TOKEN_SPECS = [
    ("loop_open", LOOP_OPEN_RE),
    ("loop_close", LOOP_CLOSE_RE),
    ("if_open", IF_OPEN_RE),
    ("ifnot_open", IF_NOT_OPEN_RE),
    ("if_close", IF_CLOSE_RE),
]


def tokenize(text: str):
    tokens = []
    for kind, rgx in _TOKEN_SPECS:
        for m in rgx.finditer(text):
            name = m.group(1) if m.groups() else None
            tokens.append(Token(kind, name, m.group(0), m.start(), m.end()))
    tokens.sort(key=lambda t: t.start)
    return tokens


def render_segment(text: str, root, local) -> str:
    """Render one segment: expand top-level blocks, substitute placeholders in
    the literal gaps between them. Nested blocks handled by recursion."""
    tokens = tokenize(text)
    out = []
    pos = 0
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        # literal text before this token
        if tok.start > pos:
            out.append(substitute_placeholders(text[pos:tok.start], local, root))

        if tok.kind in ("loop_open", "if_open", "ifnot_open"):
            close_idx = find_matching_close(tokens, i)
            if close_idx is None:
                raise ValueError(f"unbalanced block: '{tok.raw.strip()}' has no matching close")
            inner_start = tok.end
            inner_end = tokens[close_idx].start
            inner = text[inner_start:inner_end]

            if tok.kind == "loop_open":
                out.append(render_loop(tok.name, inner, root, local))
            elif tok.kind == "if_open":
                if is_truthy_scoped(tok.name, root, local):
                    out.append(render_segment(inner, root, local))
            else:  # ifnot_open
                if not is_truthy_scoped(tok.name, root, local):
                    out.append(render_segment(inner, root, local))

            pos = tokens[close_idx].end
            i = close_idx + 1
        else:
            # stray close token — shouldn't happen if balanced; skip its text
            pos = tok.end
            i += 1

    # trailing literal
    if pos < len(text):
        out.append(substitute_placeholders(text[pos:], local, root))
    return "".join(out)


def is_truthy_scoped(name: str, root, local) -> bool:
    """RENDER_IF condition: try local element scope first, then root."""
    if local is not None and local is not root:
        v = lookup(local, name)
        if v is not _MISSING:
            if isinstance(v, (list, dict, str)):
                return len(v) > 0
            return bool(v) and v is not None
    return is_truthy(root, name)


def find_matching_close(tokens, open_idx):
    """Given an opener token index, find its matching closer index, honoring
    nesting and matching loop↔loop / if↔if close kinds."""
    opener = tokens[open_idx]
    if opener.kind == "loop_open":
        open_kinds = {"loop_open"}
        close_kind = "loop_close"
    else:  # if_open / ifnot_open
        open_kinds = {"if_open", "ifnot_open"}
        close_kind = "if_close"

    depth = 0
    for j in range(open_idx + 1, len(tokens)):
        k = tokens[j].kind
        if k in open_kinds:
            depth += 1
        elif k == close_kind:
            if depth == 0:
                return j
            depth -= 1
    return None


def render_loop(name: str, inner: str, root, local) -> str:
    # array lives at root (loops iterate top-level data arrays)
    arr = lookup(root, name)
    if arr is _MISSING or arr is None:
        return ""
    if not isinstance(arr, list):
        raise ValueError(f"LOOP '{name}' expects an array, got {type(arr).__name__}")
    pieces = []
    for elem in arr:
        elem_scope = elem if isinstance(elem, dict) else {"value": elem}
        pieces.append(render_segment(inner, root, elem_scope))
    return "".join(pieces)


# ----- self-check ------------------------------------------------------------
def residual_placeholders(rendered: str):
    """Return list of {{...}} placeholders surviving OUTSIDE HTML comments."""
    stripped = COMMENT_RE.sub("", rendered)
    return PLACEHOLDER_RE.findall(stripped)


# ----- CLI -------------------------------------------------------------------
def render(template_text: str, data: dict) -> str:
    if not isinstance(data, dict):
        raise ValueError("data root must be a JSON object")
    rendered = render_segment(template_text, data, data)
    provenance = PROVENANCE_FMT.format(sha=template_sha256(template_text))
    if "</body>" in rendered:
        rendered = rendered.replace("</body>", f"{provenance}\n</body>", 1)
    else:
        rendered = rendered + "\n" + provenance + "\n"
    return rendered


def missing_i18n_keys(template_text: str, data) -> list:
    """The {{i18n.*}} namespace is REQUIRED scaffold (section titles, disclaimer,
    labels) — unlike clinical fields, a missing i18n key is a bug, not a
    "资料缺失" case. Without this, a missing key silently falls back and the doc
    renders degraded-but-passing. Fail loud instead. Returns the missing refs."""
    refs = set(re.findall(r"\{\{\s*(i18n\.[A-Za-z0-9_]+)\s*\}\}", template_text))
    i18n = data.get("i18n") if isinstance(data, dict) else None
    missing = []
    for ref in sorted(refs):
        key = ref.split(".", 1)[1]
        val = i18n.get(key) if isinstance(i18n, dict) else None
        if not (isinstance(val, str) and val.strip()):
            missing.append(ref)
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generic deterministic HTML template renderer (stdlib only, zero domain logic)."
    )
    ap.add_argument("--template", required=True, help="path to *.template.html")
    ap.add_argument("--data", required=True, help="path to data JSON")
    ap.add_argument("--out", help="output path (default: stdout)")
    ap.add_argument(
        "--allow-residual",
        action="store_true",
        help="do not fail on residual {{...}} placeholders (debug only)",
    )
    args = ap.parse_args()

    try:
        template_text = Path(args.template).read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot read template: {e}", file=sys.stderr)
        return 2
    try:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot read/parse data JSON: {e}", file=sys.stderr)
        return 2

    missing_i18n = missing_i18n_keys(template_text, data)
    if missing_i18n:
        print(
            "ERROR: incomplete i18n scaffold (required keys missing/empty): "
            + ", ".join("{{" + k + "}}" for k in missing_i18n),
            file=sys.stderr,
        )
        return 1

    try:
        rendered = render(template_text, data)
    except ValueError as e:
        print(f"ERROR: render failed: {e}", file=sys.stderr)
        return 2

    residual = residual_placeholders(rendered)
    if residual and not args.allow_residual:
        uniq = sorted(set(residual))
        print(
            "ERROR: residual placeholders survived (data contract gap): "
            + ", ".join("{{" + p + "}}" for p in uniq),
            file=sys.stderr,
        )
        return 1

    sha = template_sha256(template_text)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
        print(f"rendered → {args.out} ({len(rendered)} bytes) template_sha256={sha}")
    else:
        sys.stdout.write(rendered)
        print(f"template_sha256={sha}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
