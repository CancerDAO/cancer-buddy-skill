#!/usr/bin/env bash
# organize_meta.json (scripts/write_organize_meta.py): which organize build produced an
# archive — skill_version / skill_commit (+dirty) / skill_fingerprint / generated_at.
# SMTB reads skill_commit into its manifest. Schema-valid, deterministic fingerprint,
# fallbacks when there is no git checkout.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/write_organize_meta.py"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$SCRIPT" "$tmp" "$REPO_ROOT" <<'PY'
import json, shutil, subprocess, sys
from pathlib import Path
script, tmp, repo = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


pd = tmp / "pt"
pd.mkdir()
p = subprocess.run([sys.executable, script, str(pd), "--generated-at", "2030-01-20T09:00:00Z"], capture_output=True, text=True)
check("writes organize_meta.json", p.returncode == 0 and (pd / "organize_meta.json").is_file(), p.stderr)
meta = json.loads((pd / "organize_meta.json").read_text(encoding="utf-8"))
check("pinned keys present", {"skill", "skill_version", "skill_commit", "skill_fingerprint", "generated_at"} <= set(meta))
check("skill name", meta["skill"] == "cancer-buddy-organize")
check("fingerprint format", meta["skill_fingerprint"].startswith("sha256:") and len(meta["skill_fingerprint"]) == 71)
check("generated_at override", meta["generated_at"] == "2030-01-20T09:00:00Z")
check("version resolved (frontmatter or plugin.json)", isinstance(meta["skill_version"], str) and meta["skill_version"])
if (repo / ".git").exists():
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    check("commit = git HEAD of the checkout", meta["skill_commit"] == head, f"{meta['skill_commit']} vs {head}")
    check("dirty flag is a bool", isinstance(meta["skill_dirty"], bool))

# deterministic fingerprint; changes when a skill file changes
p2 = subprocess.run([sys.executable, script, str(pd), "--print"], capture_output=True, text=True)
check("fingerprint deterministic", json.loads(p2.stdout)["skill_fingerprint"] == meta["skill_fingerprint"])
copy = tmp / "installed" / "cancer-buddy-organize"
shutil.copytree(repo / "skills" / "cancer-buddy-organize", copy, ignore=shutil.ignore_patterns("__pycache__"))
m_copy = json.loads(subprocess.run([sys.executable, script, str(pd), "--skill-dir", str(copy), "--print"],
                                   capture_output=True, text=True).stdout)
check("installed copy (no git) → same fingerprint", m_copy["skill_fingerprint"] == meta["skill_fingerprint"])
check("installed copy without .skill_source.json → commit null", m_copy["skill_commit"] is None)
(copy / ".skill_source.json").write_text(json.dumps({"repo": "x", "commit": "abcdef1234567", "dirty": False}), encoding="utf-8")
m_copy = json.loads(subprocess.run([sys.executable, script, str(pd), "--skill-dir", str(copy), "--print"],
                                   capture_output=True, text=True).stdout)
check("installed copy reads .skill_source.json", m_copy["skill_commit"] == "abcdef1234567" and m_copy["skill_dirty"] is False)
(copy / "references" / "extra.md").write_text("x", encoding="utf-8")
m2 = json.loads(subprocess.run([sys.executable, script, str(pd), "--skill-dir", str(copy), "--print"],
                               capture_output=True, text=True).stdout)
check("fingerprint changes with skill content", m2["skill_fingerprint"] != meta["skill_fingerprint"])
(copy / "references" / "extra.md").unlink()
# a copy sitting UNTRACKED inside some other git repository (a dotfiles-managed ~/.agents):
# the outer HEAD does not describe this skill → commit null, not the outer HEAD
outer = tmp / "dotfiles"
outer.mkdir()
git = ["git", "-C", str(outer), "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
subprocess.run(git + ["init", "-q"], check=True)
(outer / "README").write_text("x", encoding="utf-8")
subprocess.run(git + ["add", "README"], check=True)
subprocess.run(git + ["commit", "-qm", "init"], check=True)
nested = outer / "skills" / "cancer-buddy-organize"
shutil.copytree(repo / "skills" / "cancer-buddy-organize", nested, ignore=shutil.ignore_patterns("__pycache__"))
m_nested = json.loads(subprocess.run([sys.executable, script, str(pd), "--skill-dir", str(nested), "--print"],
                                     capture_output=True, text=True).stdout)
outer_head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
check("untracked copy inside another repo → commit null (not the outer HEAD)",
      m_nested["skill_commit"] is None and m_nested["skill_commit"] != outer_head, str(m_nested["skill_commit"]))
(nested / ".skill_source.json").write_text(json.dumps({"repo": "x", "commit": "1234567abcdef", "dirty": True}), encoding="utf-8")
m_nested = json.loads(subprocess.run([sys.executable, script, str(pd), "--skill-dir", str(nested), "--print"],
                                     capture_output=True, text=True).stdout)
check(".skill_source.json wins over any enclosing checkout", m_nested["skill_commit"] == "1234567abcdef" and m_nested["skill_dirty"] is True)
(nested / ".skill_source.json").unlink()
subprocess.run(git + ["add", "skills"], check=True)
subprocess.run(git + ["commit", "-qm", "track skill"], check=True)
outer_head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
m_nested = json.loads(subprocess.run([sys.executable, script, str(pd), "--skill-dir", str(nested), "--print"],
                                     capture_output=True, text=True).stdout)
check("once that repo TRACKS the skill, its HEAD is the commit", m_nested["skill_commit"] == outer_head, str(m_nested))

p3 = subprocess.run([sys.executable, script, str(tmp / "missing")], capture_output=True, text=True)
check("missing patient dir → exit 2", p3.returncode == 2)

try:
    sys.path.insert(0, str(repo / "tests" / "fixtures" / "organize-regress"))
    import synlib
    check("schema-valid", synlib.schema_errors("organize_meta.schema.json", meta) == [])
    bad = dict(meta, skill_commit="not-a-sha")
    check("schema rejects a non-hex commit", bool(synlib.schema_errors("organize_meta.schema.json", bad)))
    d = synlib.make(tmp / "arch", lambda d: subprocess.run([sys.executable, script, str(d), "--pii-layer1", "pii-1"],
                                                           check=True, capture_output=True))
    rc, errs, _ = synlib.validate(d)
    check("archive with organize_meta.json (+ clean Layer-1 PII scan) validates (current generation)", rc == 0, str(errs[:3]))
    m = synlib.load(d, "organize_meta.json")
    check("--pii-layer1 records {worker_id, clean: true}", m.get("pii_layer1_scan") == {"worker_id": "pii-1", "clean": True}, str(m))
    check("schema accepts the recorded scan", synlib.schema_errors("organize_meta.schema.json", m) == [])
    check("schema rejects a scan that is not clean",
          bool(synlib.schema_errors("organize_meta.schema.json", dict(m, pii_layer1_scan={"worker_id": "pii-1", "clean": False}))))
    # DoD 3 on disk: without the recorded clean semantic scan a current archive does not pass
    d = synlib.make(tmp / "arch_nopii", lambda d: subprocess.run([sys.executable, script, str(d)], check=True,
                                                                capture_output=True))
    rc, errs, _ = synlib.validate(d)
    check("organize_meta.json without pii_layer1_scan → ERROR (DoD 3 not shown)",
          rc == 1 and any("no pii_layer1_scan" in e for e in errs), str(errs[:3]))
    bad_id = subprocess.run([sys.executable, script, str(pd), "--pii-layer1", "orchestrator"], capture_output=True, text=True)
    check("--pii-layer1 refuses the orchestrator's reserved name (exit 2)", bad_id.returncode == 2, bad_id.stderr)
    # ---- X-P0-05 `--can-stop`: a turn may end only when the run is finished
    VAL = repo / "skills" / "cancer-buddy-organize" / "scripts" / "validate_structured_outputs.py"

    def can_stop(d, validator=VAL):
        q = subprocess.run([sys.executable, str(validator), "--can-stop", str(d)], capture_output=True, text=True)
        return q.returncode, q.stdout + q.stderr
    d = synlib.make(tmp / "cs_nometa")
    rc, out = can_stop(d)
    check("--can-stop without organize_meta.json → exit 5 and names the next step",
          rc == 5 and "organize_meta.json 不存在" in out and "Step 17" in out, out)
    d = synlib.make(tmp / "cs_ok", synlib.finish_final)
    rc, out = can_stop(d)
    check("--can-stop on a finished archive (meta + every --final gate green) → exit 0", rc == 0 and "可以结束" in out, out)
    check("--can-stop writes nothing (readonly)", not (d / "readiness.json").read_text(encoding="utf-8").count("UNTRUSTED"), "")
    d = synlib.make(tmp / "cs_noindex", lambda d: (synlib.finish_final(d), (d / "INDEX.md").unlink()))
    rc, out = can_stop(d)
    check("--can-stop with a --final gate failing (INDEX.md missing) → exit 5", rc == 5 and "未完成" in out and "INDEX.md" in out, out)

    # ---- X-P1-01: --final re-checks the skill build organize_meta.json recorded
    skill = tmp / "skillcopy" / "cancer-buddy-organize"
    shutil.copytree(repo / "skills" / "cancer-buddy-organize", skill, ignore=shutil.ignore_patterns("__pycache__"))
    d = synlib.make(tmp / "fp", lambda d: synlib.finish_final(d, skill_dir=skill))
    q = subprocess.run([sys.executable, str(skill / "scripts" / "validate_structured_outputs.py"), str(d), "--final"],
                       capture_output=True, text=True)
    check("--final with the skill unchanged since organize_meta.json → rc 0", q.returncode == 0, q.stderr[-400:])
    (skill / "scripts" / "build_helper_for_this_patient.py").write_text("print(1)\n", encoding="utf-8")
    q = subprocess.run([sys.executable, str(skill / "scripts" / "validate_structured_outputs.py"), str(d), "--final"],
                       capture_output=True, text=True)
    check("--final after a file was written into the skill dir → ERROR skill_changed_since_meta",
          q.returncode == 1 and "skill_changed_since_meta" in q.stderr, q.stderr[-400:])
    rc, out = can_stop(d, skill / "scripts" / "validate_structured_outputs.py")
    check("…and --can-stop refuses to end the turn", rc == 5 and "skill_changed_since_meta" in out, out)
    (skill / "scripts" / "build_helper_for_this_patient.py").unlink()
    src = skill / "references" / "organizer-prompt-phase1-ocr.md"
    src.write_text(src.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    q = subprocess.run([sys.executable, str(skill / "scripts" / "validate_structured_outputs.py"), str(d), "--final"],
                       capture_output=True, text=True)
    check("--final after a prompt file was edited → ERROR skill_changed_since_meta",
          q.returncode == 1 and "skill_changed_since_meta" in q.stderr, q.stderr[-400:])
except ImportError:
    print("SKIP: jsonschema not installed (schema half)", file=sys.stderr)

print(f"organize-meta: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
