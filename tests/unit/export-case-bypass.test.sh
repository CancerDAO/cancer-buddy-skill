#!/usr/bin/env bash
# tests/unit/export-case-bypass.test.sh — export_share.py, allowlist bypass by CASE.
#
# tests/unit/export-share.test.sh already proves the allowlist refuses the lowercase
# spellings. This file is about the bypass: refusing `raw/transcript/…` while accepting
# `Raw/Transcript/…` is not a partial defence, it is NO defence, because on the two
# filesystems this archive actually lives on the two strings open the SAME FILE.
#
#   macOS APFS and Windows NTFS are case-INSENSITIVE by default. `RAW/TRANSCRIPT/s001/
#   page-001.md` matches none of the literal prefixes in FORBIDDEN_PATH_PREFIXES and then
#   opens, byte for byte, the verbatim UNMASKED per-page transcription the prefix exists
#   to keep inside the vault. A refusal decided on a different equivalence than the one
#   the filesystem uses is decorative on two of three platforms.
#
# So every membership test in export_share is done on a CASEFOLDED string, and casefold()
# rather than lower() because lower() leaves ﬁ (U+FB01) and ẞ alone and a case-insensitive
# filesystem does not. There is a second layer too: _true_spelling() walks the real
# directory entries and re-judges the path as the filesystem SPELLS it, so a path that
# exists under a different casing is judged as what it IS rather than as what was typed.
#
# What is at stake behind each refused path:
#   raw/transcript/  the verbatim page transcription — the single richest plaintext in
#                    the archive, pre-masking, with every identifier the original had.
#   raw/_cache/      the same text again, as the model returned it. A cache is not a
#                    deliverable, and it is equally unmasked.
#   15_未分类资料/    masked like any other sidecar, so the reason it is withheld is not
#                    privacy but PURPOSE LIMITATION: open-world material is by definition
#                    the material nobody classified, so its relevance to THIS export's
#                    declared purpose has not been established. Shipping it by reflex
#                    turns a purpose-limited export into a dump — hence an explicit,
#                    recorded --include-unclassified rather than a default.
#
# And a positive arm, because an exporter that refuses everything is not a safe exporter,
# it is a broken one: an ordinary clinical bucket sidecar must still export cleanly and
# land in the manifest.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORG="$REPO_ROOT/skills/cancer-buddy-organize"
SCRIPT="$ORG/scripts/export_share.py"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  ok   — $1"; }
no() { fail=$((fail+1)); echo "FAIL: $1" >&2; }

# ---------------------------------------------------------------- fixtures ----
# The directories are created in their canonical LOWERCASE spelling; every bypass below
# asks for a different casing of the same path.
P="$tmp/patient"
mkdir -p "$P/raw/transcript/s001" "$P/raw/_cache/transcripts" \
         "$P/04_诊断与分期/病理报告" "$P/15_未分类资料/肠道菌群检测" \
         "$P/case_summary_versions"
printf -- '---\nsource_id: s001\npage: 1\n---\n# 全文\n姓名 张三 住院号 0012345678\n' \
  > "$P/raw/transcript/s001/page-001.md"
printf -- '# cached model output\n姓名 张三\n' \
  > "$P/raw/_cache/transcripts/abc.3.0.test-model.md"
printf -- 'SOURCE: pathology | CONFIDENCE: high\n浸润性腺癌，中分化\n' \
  > "$P/04_诊断与分期/病理报告/report.md"
printf -- 'SOURCE: novel | CONFIDENCE: medium\n肠道菌群多样性指数 3.2\n' \
  > "$P/15_未分类资料/肠道菌群检测/report.md"
printf -- '<html>v1</html>\n' > "$P/case_summary_versions/v1.html"
: > "$P/profile.json"
# B7 — export_share.py now walks update_log.runs[] BEFORE it copies anything, and an
# archive with no run history is refused outright: the log is the only place the archive
# records whether the semantic PII pass ever ran, so its absence is not the absence of a
# problem. The positive arms below are about the path allowlist, not about that refusal,
# so the fixture carries a clean full run to get past it. (Section E asserts the refusal
# itself, and that it fires before a single byte is written.)
cat > "$P/update_log.json" <<'EOF'
{"schema_version":"1","runs":[
  {"run_id":"run-001","run_mode":"full","started_at":"2026-09-16T00:00:00Z",
   "added_sources":[{"source_id":"s001","read_mode":"model_vision_primary"}],
   "pii_semantic":"clean","faithfulness_method":"vision_second_read"} ]}
EOF

# Each case is driven through _resolve_includes (the decision point) and reported back
# one line per assertion so the counters reflect the number of facts actually checked.
python3 - "$SCRIPT" "$P" > "$tmp/results.tsv" <<'PYEOF'
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = pathlib.Path(sys.argv[2]).resolve()

results = []
src_preview = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")


def report(good, label):
    results.append(("OK" if good else "NO") + "\t" + label)


def refusal(paths, *, include_unclassified=False):
    """Return the refusal message, or None if the path was ACCEPTED."""
    try:
        module._resolve_includes(root, paths, include_unclassified=include_unclassified)
    except ValueError as exc:
        return str(exc)
    return None


# ------------------------------------------------------------------ A. case ---
# Three spellings of two protected prefixes, plus the mixed-case top-level `raw` the
# prefixes sit under. Each must be refused AND must be refused for the RIGHT reason:
# a generic "unsafe path" would leave the operator guessing, and would not survive a
# refactor that loosened the `raw` rule.
CASE_BYPASS = [
    ("Raw/transcript/s001/page-001.md", "raw/transcript/",
     "`Raw/` — a single capital on the top-level directory"),
    ("RAW/TRANSCRIPT/s001/page-001.md", "raw/transcript/",
     "`RAW/TRANSCRIPT/` — fully upper-cased"),
    ("raw/_Cache/transcripts/abc.3.0.test-model.md", "raw/_cache/",
     "`raw/_Cache/` — a capital inside the cache directory name"),
    ("RAW/_CACHE/transcripts/abc.3.0.test-model.md", "raw/_cache/",
     "`RAW/_CACHE/` — fully upper-cased"),
    ("rAw/TrAnScRiPt/s001/page-001.md", "raw/transcript/",
     "`rAw/TrAnScRiPt/` — alternating case"),
]
for path, expect_prefix, why in CASE_BYPASS:
    msg = refusal([path])
    report(msg is not None, f"REFUSED: {why}")
    if msg is None:
        continue
    report("forbidden export path" in msg,
           f"…refused as a forbidden export path, not a generic error ({why})")
    report(expect_prefix in msg,
           f"…and names the canonical prefix {expect_prefix!r} it matched ({why})")

# the refusal explains WHAT it is protecting, in the operator's terms
msg = refusal(["RAW/TRANSCRIPT/s001/page-001.md"])
report(msg is not None and "unmasked" in msg,
       "the raw/transcript/ refusal says the content is UNMASKED source text")
msg = refusal(["RAW/_CACHE/transcripts/abc.3.0.test-model.md"])
report(msg is not None and "cache is not a deliverable" in msg,
       "the raw/_cache/ refusal says a cache is not a deliverable")

# SECOND LAYER. Casefolding the requested string closes the direct bypass; _true_spelling
# closes the one after it, by walking the real directory entries and re-judging the path
# as the FILESYSTEM spells it. The two layers overlap on purpose — a mis-cased raw/ path
# is already refused by the casefolded string rule, so this is the belt behind the braces
# and is asserted directly rather than through a refusal message it never gets to add.
spelled = module._true_spelling(root, pathlib.Path("Raw/Transcript/s001/PAGE-001.md"))
on_case_insensitive_fs = spelled is not None
report(not on_case_insensitive_fs
       or spelled.as_posix() == "raw/transcript/s001/page-001.md",
       f"_true_spelling resolves a mis-cased request to the on-disk spelling "
       f"(got {spelled.as_posix() if spelled else None!r})")
report(module._forbidden_reason(pathlib.Path("raw/transcript/s001/page-001.md")) is not None,
       "…and that on-disk spelling is itself forbidden, so both layers agree")
report("case-insensitive" in src_preview,
       "the module states that a case-insensitive volume opens the same file either way")

# the whole-directory forbidden list is casefolded too, not just the two named prefixes
for path, why in [("Raw/original.pdf", "`Raw/` as a bare top-level directory"),
                  ("Case_Summary_Versions/v1.html", "`Case_Summary_Versions/` (version history)"),
                  ("CASE_SUMMARY_VERSIONS/v1.html", "`CASE_SUMMARY_VERSIONS/` upper-cased")]:
    msg = refusal([path])
    report(msg is not None, f"REFUSED: {why}")

# casefold(), not lower(): the reason is written into the module and must stay there,
# because "lower() is the same thing" is the change that silently reopens this.
src = src_preview
report("casefold() rather than lower()" in src,
       "the module records WHY casefold() and not lower() (ﬁ / ẞ fold differently)")
report(src.count(".lower()") == 0,
       "no membership test in export_share.py is decided with .lower()")

# ...and the rule is applied everywhere, not just at the first check: a path is judged
# before AND after resolution, so a case-folded spelling cannot slip past one of them.
report("_FORBIDDEN_TOPLEVEL_CF" in src and "_FORBIDDEN_PREFIXES_CF" in src,
       "the forbidden sets exist in pre-casefolded form (not folded ad hoc at each site)")

# ------------------------------------------------------- B. 15_ purpose limit ---
OPEN_MD = "15_未分类资料/肠道菌群检测/report.md"

msg = refusal([OPEN_MD])
report(msg is not None, "REFUSED by default: a 15_未分类资料/ sidecar")
report(msg is not None and "excluded by default" in msg,
       "…the refusal says it is excluded BY DEFAULT (not forbidden outright)")
report(msg is not None and "--include-unclassified" in msg,
       "…and names the flag that turns it on deliberately")
report(msg is not None and "purpose" in msg,
       "…and gives the reason as purpose limitation, not privacy")

selected = module._resolve_includes(root, [OPEN_MD], include_unclassified=True)
report([rel.as_posix() for rel, _ in selected] == [OPEN_MD],
       "ACCEPTED with --include-unclassified: the opt-in is what changes the answer")

# the opt-in widens exactly one thing: it does not unlock raw/, in any casing
report(refusal(["RAW/TRANSCRIPT/s001/page-001.md"], include_unclassified=True) is not None,
       "--include-unclassified does NOT unlock raw/transcript/ (the flag is scoped to 15_)")
report(refusal(["raw/_Cache/transcripts/abc.3.0.test-model.md"],
               include_unclassified=True) is not None,
       "--include-unclassified does NOT unlock raw/_cache/")

# ------------------------------------------------------------- C. positive ----
# An exporter that refuses everything is broken, not safe.
selected = module._resolve_includes(root, ["04_诊断与分期/病理报告/report.md"])
report([rel.as_posix() for rel, _ in selected] == ["04_诊断与分期/病理报告/report.md"],
       "ACCEPTED with no opt-in at all: an ordinary clinical bucket sidecar")

selected = module._resolve_includes(
    root, ["profile.json", "04_诊断与分期/病理报告/report.md"])
report(len(selected) == 2,
       "ACCEPTED: several pinned-domain paths in one call keep their order and count")

print("\n".join(results))
PYEOF

while IFS=$'\t' read -r verdict label; do
  [ -z "${verdict:-}" ] && continue
  if [ "$verdict" = "OK" ]; then ok "$label"; else no "$label"; fi
done < "$tmp/results.tsv"

# ===========================================================================
# D. end to end — the CLI, and a real export that actually writes files
# ===========================================================================
echo "=== D. through the CLI ==="

set +e
out="$(python3 "$SCRIPT" "$P" --out "$tmp/export-bypass" \
        --include "RAW/TRANSCRIPT/s001/page-001.md" \
        --recipient center --purpose second-opinion \
        --expires-at 2099-01-01T00:00:00Z --authorization-ref auth-1 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] \
  && ok "the CLI refuses an upper-cased raw/transcript/ include (rc=$rc, non-zero)" \
  || no "the CLI ACCEPTED an upper-cased raw/transcript/ include"
# rc 2 is this script's "bad invocation" code; rc 1 is reserved for a run that was well
# formed but failed a gate. An allowlist violation is the former. Pinned so a change to
# the code split is a deliberate one.
[ "$rc" -eq 2 ] \
  && ok "…with rc=2 (bad invocation), leaving rc=1 for a well-formed run that fails a gate" \
  || no "expected rc=2 for an allowlist violation, got rc=$rc"
echo "$out" | grep -q "raw/transcript/" \
  && ok "…and the CLI error names the canonical prefix" || no "CLI error is vague: $out"
[ ! -e "$tmp/export-bypass" ] \
  && ok "…and no destination directory was created (nothing half-exported)" \
  || no "the refused export still created $tmp/export-bypass"

# The positive end-to-end arm stubs the STRUCTURAL ACCEPTANCE GATE, which is a different
# contract (it wants a complete archive: readiness.json, source_inventory.json, AGENTS.md
# …) and is covered by its own tests. Stubbing it is what isolates this file to the
# allowlist decision — otherwise "export refused" would be ambiguous between the two.
set +e
out="$(python3 - "$SCRIPT" "$P" "$tmp/export-ok" <<'PYEOF' 2>&1
import importlib.util
import json
import pathlib
import sys

spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._run_acceptance_gate = lambda patient_dir: True

root = pathlib.Path(sys.argv[2]).resolve()
dest = pathlib.Path(sys.argv[3])

rc = module.export_share(
    root, dest, ["04_诊断与分期/病理报告/report.md"],
    recipient="receiving-center", purpose="second-opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-1",
)
assert rc == 0, f"a legal bucket sidecar failed to export, rc={rc}"

copied = dest / "04_诊断与分期/病理报告/report.md"
assert copied.is_file(), "the sidecar was not copied"
assert "浸润性腺癌" in copied.read_text(encoding="utf-8"), "the copied sidecar lost its content"

manifest = json.loads((dest / "_SHARE_MANIFEST.json").read_text(encoding="utf-8"))
assert manifest["included_paths"] == ["04_诊断与分期/病理报告/report.md"], manifest
assert manifest["raw_originals_included"] is False, manifest
assert manifest["verbatim_transcripts_included"] is False, manifest
assert manifest["unclassified_archive_opted_in"] is False, manifest
assert manifest["authorization_ref"] == "auth-1", manifest

# nothing from raw/ rode along
leaked = [p for p in dest.rglob("*") if "transcript" in p.as_posix()
          or "_cache" in p.as_posix() or p.name.endswith(".pdf")]
assert not leaked, f"protected material reached the export: {leaked}"
print("ok")
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "POSITIVE: a normal bucket sidecar exports with rc=0, content intact, manifest written" \
  || no "the positive export arm failed: $out"

# and the same call with the opt-in RECORDS it — the flag is an audited act, not a mood
set +e
out="$(python3 - "$SCRIPT" "$P" "$tmp/export-open" <<'PYEOF' 2>&1
import importlib.util
import json
import pathlib
import sys

spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._run_acceptance_gate = lambda patient_dir: True

root = pathlib.Path(sys.argv[2]).resolve()
dest = pathlib.Path(sys.argv[3])
rc = module.export_share(
    root, dest, ["15_未分类资料/肠道菌群检测/report.md"],
    recipient="receiving-center", purpose="second-opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-1",
    include_unclassified=True,
)
assert rc == 0, f"the opted-in open-archive export failed, rc={rc}"
manifest = json.loads((dest / "_SHARE_MANIFEST.json").read_text(encoding="utf-8"))
assert manifest["unclassified_archive_opted_in"] is True, manifest
print("ok")
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "…and an opted-in 15_ export records unclassified_archive_opted_in: true in the manifest" \
  || no "the opt-in is not recorded in the share manifest: $out"

# ===========================================================================
# E. B7 — no update_log.json is a REFUSAL, not a clean slate
# ===========================================================================
echo "=== E. an archive that cannot say whether the PII pass ran ==="

# The export is a one-way boundary: once files leave the vault no later pass can reach
# them. The evidence that they are safe to leave lives in update_log.runs[], and an
# archive missing that file is not an archive with nothing to hide — it is an archive
# with nothing to check. Deleting one file must not be the cheapest way past the PII
# refusal that section C of pii-deferred-gate.test.sh pins.
#
# This arm uses the SAME directory and the SAME call that exported cleanly two
# assertions ago, with only update_log.json removed. That isolation is the point: the
# difference in verdict can only have come from the missing log.
mv "$P/update_log.json" "$tmp/update_log.stash"
set +e
out="$(python3 - "$SCRIPT" "$P" "$tmp/export-nolog" <<'PYEOF' 2>&1
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._run_acceptance_gate = lambda patient_dir: True
sys.exit(module.export_share(
    pathlib.Path(sys.argv[2]).resolve(), pathlib.Path(sys.argv[3]),
    ["04_诊断与分期/病理报告/report.md"],
    recipient="receiving-center", purpose="second-opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-1"))
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 1 ] \
  && ok "the same legal sidecar, with update_log.json deleted → export exits 1 (B7)" \
  || no "an archive with no run history exported anyway, rc=$rc"
echo "$out" | grep -q 'update_log.json is missing' \
  && ok "…and the refusal names the missing file rather than the path it was copying" \
  || no "the refusal blames the wrong thing: $out"
echo "$out" | grep -q 'absent file must never read as an absent problem' \
  && ok "…and states why absence is not evidence of cleanliness" \
  || no "the reasoning is not stated: $out"
[ -d "$tmp/export-nolog" ] \
  && no "the destination was created before the refusal — a partial export is still an export" \
  || ok "…and not one byte reached the destination"

# a runs[] that is not a list is the same refusal: an unwalkable history is no history.
# This is the shape a hand-edit produces, and it used to make the walk silently vacuous.
printf '{"schema_version":"1","runs":{}}' > "$P/update_log.json"
set +e
out="$(python3 - "$SCRIPT" "$P" "$tmp/export-badruns" <<'PYEOF' 2>&1
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._run_acceptance_gate = lambda patient_dir: True
sys.exit(module.export_share(
    pathlib.Path(sys.argv[2]).resolve(), pathlib.Path(sys.argv[3]),
    ["04_诊断与分期/病理报告/report.md"],
    recipient="receiving-center", purpose="second-opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-1"))
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 1 ] \
  && ok "update_log.runs is an object rather than an array → export exits 1" \
  || no "a non-list runs[] made the PII walk vacuous and the export proceeded, rc=$rc"
[ -d "$tmp/export-badruns" ] \
  && no "the destination was created despite the refusal" \
  || ok "…and again nothing was written"

# restoring the log restores the export: the gate is about the evidence, not about the
# archive being permanently condemned.
mv "$tmp/update_log.stash" "$P/update_log.json"
set +e
out="$(python3 - "$SCRIPT" "$P" "$tmp/export-restored" <<'PYEOF' 2>&1
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("export_share", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._run_acceptance_gate = lambda patient_dir: True
sys.exit(module.export_share(
    pathlib.Path(sys.argv[2]).resolve(), pathlib.Path(sys.argv[3]),
    ["04_诊断与分期/病理报告/report.md"],
    recipient="receiving-center", purpose="second-opinion",
    expires_at="2099-01-01T00:00:00Z", authorization_ref="auth-1"))
PYEOF
)"
rc=$?
set -e
[ "$rc" -eq 0 ] \
  && ok "…and putting the clean run history back lets the very same export through" \
  || no "the B7 refusal is unconditional rather than evidence-driven: $out"
[ -f "$tmp/export-restored/04_诊断与分期/病理报告/report.md" ] \
  && ok "…with the sidecar actually written this time" || no "export claimed success but wrote nothing"

# ---------------------------------------------------------------------------
echo
echo "== export-case-bypass: $pass passed, $fail failed =="
(( fail == 0 )) || exit 1
