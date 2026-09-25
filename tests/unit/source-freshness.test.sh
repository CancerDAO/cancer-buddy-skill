#!/usr/bin/env bash
# O-04 source recency (scripts/source_freshness.py + gate_source_freshness).
# latest_source_date = newest `YYYY-MM-DD_` sidecar under NN_ buckets (14_ patient
# supplements, 99_, prior-archive digests and dates after as-of excluded);
# days_since_latest = as_of − latest; > 14 days is stale (exactly 14 is not — organizer-prompt-phase2-synthesis.md §6.2).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/skills/cancer-buddy-organize/scripts/source_freshness.py"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" "$SCRIPT" <<'PY'
import json, subprocess, sys
from pathlib import Path
repo, tmp, script = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, repo + "/skills/cancer-buddy-organize/scripts")
sys.path.insert(0, repo + "/tests/fixtures/organize-regress")
import source_freshness as sf

passed = failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def touch(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("SOURCE: raw/x.jpg\n\n合成\n", encoding="utf-8")


a = tmp / "a"
touch(a, "05_影像/CT/2030-03-01_胸部CT_示例医院.md")
touch(a, "07_检验/血常规/2030-02-20_血常规_示例医院.md")
touch(a, "14_患者自管补充/患者补充/2030-03-10_自述.md")          # patient supplement: excluded
touch(a, "03_病程与叙事文书/既往档案摘录/2030-03-12_既往档案摘录.md")  # digest: excluded
touch(a, "99_无关文件/uncertain/2030-03-13_x.md")                # quarantine: excluded
touch(a, "05_影像/MRI/2030-04-01_预约单_示例医院.md")               # after as-of: excluded

r = sf.compute(a, "2030-03-14")
check("13 days → not stale, no warning", r["days_since_latest"] == 13 and r["stale"] is False and r["warning"] is None, str(r))
r = sf.compute(a, "2030-03-15")
check("14 days: latest is the newest clinical source", r["latest_source_date"] == "2030-03-01", str(r))
check("14 days: exactly 14 → not stale", r["days_since_latest"] == 14 and r["stale"] is False and r["warning"] is None)
r = sf.compute(a, "2030-03-16")
check("15 days → stale", r["days_since_latest"] == 15 and r["stale"] is True)
check("15 days → warning states the day count", "15 天" in r["warning"] and "2030-03-01" in r["warning"])
check("exclusions counted", r["excluded"]["patient_supplement_or_quarantine"] == 2 and
      r["excluded"]["prior_archive_digest"] == 1 and len(r["excluded"]["after_as_of"]) == 1, str(r["excluded"]))

# as-of defaults: readiness.as_of_run_date, else readiness.generated_at, else today
(a / "readiness.json").write_text(json.dumps({"as_of_run_date": "2030-03-20"}), encoding="utf-8")
check("as-of from readiness.as_of_run_date", sf.compute(a)["as_of_source"] == "readiness.as_of_run_date"
      and sf.compute(a)["days_since_latest"] == 19)
(a / "readiness.json").write_text(json.dumps({"generated_at": "2030-03-05T08:00:00Z"}), encoding="utf-8")
check("as-of from readiness.generated_at", sf.compute(a)["as_of_run_date"] == "2030-03-05")

# no dated source → null / not stale
b = tmp / "b"
touch(b, "14_患者自管补充/患者补充/undated_自述.md")
r = sf.compute(b, "2030-03-15")
check("no dated clinical source → nulls", r["latest_source_date"] is None and r["days_since_latest"] is None and not r["stale"])

# D5: ONE canonical stale sentence — a constant the script renders and every prompt copies
T = sf.STALE_WARNING_TEMPLATE
check("STALE_WARNING_TEMPLATE carries the {latest} and {days} slots", "{latest}" in T and "{days}" in T, T)
check("stale_warning() renders exactly the template",
      sf.stale_warning("2030-03-01", 15) == T.format(latest="2030-03-01", days=15))
check("compute().warning is the rendered template",
      sf.compute(a, "2030-03-16")["warning"] == T.format(latest="2030-03-01", days=15))
check("the rendered sentence states the day count the validator looks for (“15 天”)",
      "15 天" in sf.stale_warning("2030-03-01", 15))

# D6: without --as-of / readiness dates the fallback is the LOCAL date of the run (update_log
# `at` is UTC; the validator's ±1 day covers the difference). UTC+14 and UTC-12 are 26 h apart,
# so at any moment at least one of them is on a different calendar day than UTC.
c = tmp / "c"
touch(c, "05_影像/CT/2030-03-01_胸部CT_示例医院.md")
import os
for tz in ("Etc/GMT-14", "Etc/GMT+12"):
    env = dict(os.environ, TZ=tz)
    today = lambda: subprocess.run([sys.executable, "-c", "import datetime; print(datetime.date.today())"],
                                   env=env, capture_output=True, text=True).stdout.strip()
    before = today()
    p = subprocess.run([sys.executable, script, str(c), "--json"], env=env, capture_output=True, text=True)
    after = today()
    rep_ = json.loads(p.stdout) if p.returncode == 0 else {}
    check(f"no as-of anywhere ({tz}) → today's LOCAL date", rep_.get("as_of_run_date") in (before, after)
          and rep_.get("as_of_source") == "today_local", f"{rep_.get('as_of_run_date')} vs {before}/{after} {p.stderr[-200:]}")

# CLI: --as-of injectable, bad date → exit 2
p = subprocess.run([sys.executable, script, str(a), "--as-of", "2030-03-16", "--json"], capture_output=True, text=True)
check("CLI --as-of", p.returncode == 0 and json.loads(p.stdout)["days_since_latest"] == 15)
p = subprocess.run([sys.executable, script, str(a), "--as-of", "16/03/2030"], capture_output=True, text=True)
check("CLI bad --as-of → exit 2", p.returncode == 2)

# ---- validator binding (current archive)
try:
    import jsonschema  # noqa: F401
    import synlib
except ImportError:
    print("SKIP: jsonschema not installed (validator half)", file=sys.stderr)
else:
    def ready(fn):
        return lambda d: synlib.edit_json(d, "readiness.json", fn)
    d = synlib.make(tmp / "v1")
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("clean archive (5 days) passes", errs == [], str(errs))
    d = synlib.make(tmp / "v2", ready(lambda r: r.update({"days_since_latest": 9})))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("day count ≠ as_of − latest → ERROR", any("days_since_latest 9" in e for e in errs), str(errs))
    d = synlib.make(tmp / "v3", ready(lambda r: r.update({"latest_source_date": "2030-01-12", "days_since_latest": 8})))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("latest_source_date ≠ newest dated source → ERROR", any("newest dated source is '2030-01-15'" in e for e in errs), str(errs))
    def run_on(day):  # the organize run (update_log entry) happened on `day`
        return lambda d: synlib.edit_json(d, "update_log.json",
                                          lambda u: u["entries"][0].__setitem__("at", day + "T09:00:00Z"))
    d = synlib.make(tmp / "v4", lambda d: (run_on("2030-01-30")(d), ready(
        lambda r: r.update({"as_of_run_date": "2030-01-30", "days_since_latest": 15}))(d)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("15 days without a warning stating it → ERROR",
          any("does not hold the stale-source sentence" in e for e in errs), str(errs))
    check("…and the ERROR quotes the canonical sentence to copy",
          any(sf.stale_warning("2030-01-15", 15) in e for e in errs), str(errs))
    STALE_FLAG = {"id": "RF-009", "category": "source_recency", "affected_field": "archive.recency",
                  "current_source_values": [], "issue": "资料最新日期距本次整理 15 天。",
                  "resolution_status": "unresolved", "severity": "yellow", "kind": "completeness"}

    def stale_ok(extra_warnings=None, flag=True):
        def fn(r):
            r.update({"as_of_run_date": "2030-01-30", "days_since_latest": 15,
                      "warnings": extra_warnings if extra_warnings is not None else [sf.stale_warning("2030-01-15", 15)]})
            if flag:
                r["review_flags"].append(dict(STALE_FLAG))
        return fn
    d = synlib.make(tmp / "v5", lambda d: (run_on("2030-01-30")(d), ready(stale_ok())(d)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("15 days with the warning and the completeness / yellow flag → pass", errs == [], str(errs))
    d = synlib.make(tmp / "v5b", lambda d: (run_on("2030-01-30")(d), ready(stale_ok(flag=False))(d)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("15 days with the warning but no completeness / yellow flag → ERROR (phase2 §6.1)",
          any("no review flag kind completeness / severity yellow" in e for e in errs), str(errs))
    d = synlib.make(tmp / "v5c", lambda d: (run_on("2030-01-30")(d), ready(stale_ok(["随访间隔 115 天内无影像"]))(d)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("a warnings[] line that merely contains '15 天' (…115 天…) is not the stale sentence → ERROR",
          any("does not hold the stale-source sentence" in e for e in errs), str(errs))
    d = synlib.make(tmp / "v6", lambda d: (run_on("2030-01-29")(d), ready(
        lambda r: r.update({"as_of_run_date": "2030-01-29", "days_since_latest": 14}))(d)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("14 days needs no warning", errs == [], str(errs))
    # as_of_run_date is the RUN date: backdating it to the newest source zeroes the count
    d = synlib.make(tmp / "v8", lambda d: (
        run_on("2030-02-20")(d), ready(lambda r: r.update({"as_of_run_date": "2030-01-15", "days_since_latest": 0}))(d)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("as_of_run_date set to the newest source date (run was 36 days later) → ERROR",
          any("is not the date of this run" in e for e in errs), str(errs))
    check("…the ERROR explains ±1 day as local run date vs UTC timestamps",
          any("LOCAL run date" in e and "UTC" in e for e in errs), str(errs))
    d = synlib.make(tmp / "v9", ready(lambda r: r.update({"as_of_run_date": "2030-01-21", "days_since_latest": 6})))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("as_of_run_date one day after the logged run (time zones) passes", errs == [], str(errs))
    META = {"skill": "cancer-buddy-organize", "skill_version": None, "skill_commit": None, "skill_dirty": None,
            "skill_fingerprint": "sha256:" + "0" * 64, "generated_at": "2030-01-20T10:00:00Z"}
    # R6: the recency is measured from THIS run — the latest entry that reconciled inputs — never
    # an earlier run of the ledger (pinned to it, a later incremental run would zero the count)
    def later_run(d):
        synlib.edit_json(d, "update_log.json", lambda u: u["entries"].append(dict(u["entries"][0], at="2030-02-20T09:00:00Z")))
    d = synlib.make(tmp / "v10", lambda d: (later_run(d), synlib.save(d, "organize_meta.json", META)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("as_of_run_date pinned to an EARLIER run of the ledger (36 → 5 days) → ERROR",
          any("is not the date of this run" in e and "2030-02-20" in e for e in errs), str(errs))
    d = synlib.make(tmp / "v10b", lambda d: (
        synlib.edit_json(d, "update_log.json", lambda u: u["entries"][0].__setitem__("inputs", [])),
        synlib.save(d, "organize_meta.json", META)))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("no entry reconciled inputs → organize_meta.generated_at is the run date", errs == [], str(errs))
    d = synlib.make(tmp / "v11", lambda d: (d / "05_影像" / "CT" / "2030-02-01_胸部CT_示例医院.md").write_text(
        (d / synlib.SIDE_CT).read_text(encoding="utf-8"), encoding="utf-8"))
    errs, _ = synlib.gate("gate_source_freshness", d)
    check("a source dated after as_of_run_date → ERROR (a run date cannot precede a source it read)",
          any("after readiness.as_of_run_date" in e for e in errs), str(errs))
    legacy = synlib.make(tmp / "v7", lambda d: (synlib.downgrade_to_legacy(d), synlib.edit_json(d, "readiness.json",
                         lambda r: r.update({"generated_at": "2030-02-10T00:00:00Z"}))))
    errs, warns = synlib.gate("gate_source_freshness", legacy)
    check("legacy archive: stale recency is a WARN with the day count",
          errs == [] and any("26 days before 2030-02-10" in w for w in warns), str(warns))

print(f"source-freshness: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
