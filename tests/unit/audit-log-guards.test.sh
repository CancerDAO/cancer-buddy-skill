#!/usr/bin/env bash
# ORG-P1-09 — the audit log cannot be rewritten quietly (scripts/_gate_provenance.py, scripts/update_log_append.py):
#   * raw/_dispatch_log.jsonl ↔ update_log.json: a kill stays a kill (status killed / timeout + a degradation), a
#     Phase 1 kill is followed by a redispatch of its files, a Phase 2 job is dispatched at most twice;
#   * the prev_sha256 hash chain written by update_log_append.py: an earlier entry edited afterwards breaks it;
#   * a worker's prompt_file_sha256 must be the skill's own prompt file for its phase.
# The clean synthetic archive (no dispatch log, no chain) is the positive control; each negative mutates ONE thing.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! python3 -c "import jsonschema" 2>/dev/null; then
  echo "SKIP: jsonschema not installed" >&2; exit 0
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

python3 - "$REPO_ROOT" "$tmp" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
REPO, TMP = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(REPO / "tests/fixtures/organize-regress"))
import synlib

S = REPO / "skills/cancer-buddy-organize/scripts"
APPEND = S / "update_log_append.py"
G = "gate_provenance"
passed = failed = 0
n = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def run(mutate=None, **kw):
    global n
    n += 1
    return synlib.gate(G, synlib.make(TMP / f"a{n}", mutate), **kw)


SRC = ["s001", "s002", "s003", "s005", "s006"]


def events(extra=None, drop=None):
    ev = [{"at": "2030-01-20T08:00:00Z", "event": "dispatch", "worker_id": "p1-s0-1", "phase": "phase1", "files": SRC},
          {"at": "2030-01-20T08:11:00Z", "event": "kill", "worker_id": "p1-s0-1", "phase": "phase1", "files": SRC}]
    ev += [{"at": "2030-01-20T08:12:00Z", "event": "redispatch", "worker_id": f"p1-{s}-1", "phase": "phase1_retry",
            "files": [s]} for s in SRC]
    ev += [{"at": "2030-01-20T08:40:00Z", "event": "dispatch", "worker_id": "p2-1", "phase": "phase2", "files": []}]
    if drop:
        ev = [e for e in ev if not drop(e)]
    return ev + (extra or [])


def dlog(ev):
    def fn(d):
        p = d / "raw" / "_dispatch_log.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ev), encoding="utf-8")
    return fn


def ledger(fn):
    return lambda d: synlib.edit_json(d, "update_log.json", fn)


def worker(doc, wid):
    return next(w for e in doc["entries"] for w in e["workers"] if w["worker_id"] == wid)


errs, _ = run()
check("clean archive without a dispatch log → passes", errs == [], str(errs))
errs, _ = run(dlog(events()))
check("dispatch log consistent with the ledger → passes", errs == [], str(errs))

# ---- a kill stays a kill
errs, _ = run(lambda d: (dlog(events())(d), ledger(lambda doc: worker(doc, "p1-s0-1").__setitem__("status", "retried"))(d)))
check("kill rewritten as retried → ERROR", any("recorded as 'retried'" in e for e in errs), str(errs))
errs, _ = run(lambda d: (dlog(events())(d), ledger(lambda doc: doc["entries"][0].__setitem__("degradations", []))(d)))
check("the kill's degradation deleted → ERROR", any("no degradations[] entry records it" in e for e in errs), str(errs))
errs, _ = run(dlog(events(drop=lambda e: e["event"] == "redispatch")))
check("Phase 1 kill with none of its files redispatched → ERROR", any("none of its files was redispatched" in e for e in errs), str(errs))
errs, _ = run(dlog(events(extra=[{"at": "2030-01-20T09:00:00Z", "event": "kill", "worker_id": "p9-ghost", "phase": "phase2"}])))
check("a killed worker missing from the ledger → ERROR", any("does not list it in workers[]" in e for e in errs), str(errs))


# ---- Phase 2: one redispatch, then stop
def p2_attempts(k, kill_last=False):
    ev = []
    for i in range(1, k + 1):
        ev.append({"at": f"2030-01-20T09:{i:02d}:00Z", "event": "dispatch" if i == 1 else "redispatch",
                   "worker_id": f"p2-k{i}", "phase": "phase2", "files": []})
        if i < k or kill_last:
            ev.append({"at": f"2030-01-20T09:{i:02d}:30Z", "event": "kill", "worker_id": f"p2-k{i}", "phase": "phase2"})
    return ev


def p2_ledger(k):
    def fn(doc):
        e = doc["entries"][0]
        for i in range(1, k + 1):
            e["workers"].append({"worker_id": f"p2-k{i}", "phase": "phase2", "slice_id": None,
                                 "status": "killed" if i < k else "done", "files": []})
        e["degradations"] += [{"worker_id": f"p2-k{i}", "reason": "timeout", "redispatched_as": [f"p2-k{i + 1}"]}
                              for i in range(1, k)]
    return fn


errs, _ = run(lambda d: (dlog(events(extra=p2_attempts(2)))(d), ledger(p2_ledger(2))(d)))
check("Phase 2 dispatched, killed, redispatched once → passes", errs == [], str(errs))
errs, _ = run(lambda d: (dlog(events(extra=p2_attempts(3)))(d), ledger(p2_ledger(3))(d)))
check("Phase 2 dispatched three times for one job → phase2_retry_exceeded", any("phase2_retry_exceeded" in e for e in errs), str(errs))
jobs = [{"at": f"2030-01-20T1{i}:00:00Z", "event": "dispatch", "worker_id": f"p2-j{i}", "phase": "phase2", "files": []} for i in range(3)]
errs, _ = run(dlog(events(extra=jobs)))
check("three separate Phase 2 jobs (none killed) → passes", errs == [], str(errs))


def bad_line(d):
    dlog(events())(d)
    with open(d / "raw" / "_dispatch_log.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json\n")


errs, _ = run(bad_line)
check("a dispatch-log line that is not JSON → ERROR", any("not one JSON object per line" in e for e in errs), str(errs))


# ---- the hash chain (update_log_append.py)
def rechain(d):
    doc = synlib.load(d, "update_log.json")
    (d / "update_log.json").unlink()
    for e in doc["entries"]:
        p = subprocess.run([sys.executable, str(APPEND), str(d), "--entry", "-", "--patient-code", doc["patient_code"]],
                           input=json.dumps(e, ensure_ascii=False), capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
    # a second entry so the chain has a link to check
    e2 = dict(doc["entries"][0], at="2030-01-20T10:00:00Z", run_mode="faithfulness_patch", added=[], degradations=[],
              workers=[{"worker_id": "p25-1", "phase": "phase2_5", "slice_id": None, "status": "done", "files": []}])
    p = subprocess.run([sys.executable, str(APPEND), str(d), "--entry", "-"], input=json.dumps(e2, ensure_ascii=False),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


errs, _ = run(rechain)
check("entries appended through update_log_append.py → chain passes", errs == [], str(errs))
n += 1
d = synlib.make(TMP / f"a{n}", rechain)
doc = synlib.load(d, "update_log.json")
check("first entry prev_sha256 null, second links the first",
      doc["entries"][0]["prev_sha256"] is None and doc["entries"][1]["prev_sha256"] ==
      hashlib.sha256(json.dumps(doc["entries"][0], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
p = subprocess.run([sys.executable, str(APPEND), str(d), "--check"], capture_output=True, text=True)
check("update_log_append.py --check on an intact chain → exit 0", p.returncode == 0, p.stdout + p.stderr)
errs, _ = run(lambda d: (rechain(d), ledger(lambda doc: worker(doc, "p1-s0-1").__setitem__("status", "retried"))(d)))
check("an earlier entry edited after the next one was appended → update_log_chain_broken",
      any("update_log_chain_broken" in e for e in errs), str(errs))
n += 1
d = synlib.make(TMP / f"a{n}", lambda d: (rechain(d), ledger(lambda doc: doc["entries"][0]["degradations"].clear())(d)))
p = subprocess.run([sys.executable, str(APPEND), str(d), "--check"], capture_output=True, text=True)
check("update_log_append.py --check on a broken chain → exit 1", p.returncode == 1, p.stdout)
errs, _ = run(lambda d: (rechain(d), ledger(lambda doc: doc["entries"][1].pop("prev_sha256"))(d)))
check("an entry without prev_sha256 after the chain started → ERROR", any("has no prev_sha256" in e for e in errs), str(errs))
errs, warns = run(ledger(lambda doc: doc["entries"].append(dict(doc["entries"][0], at="2030-01-20T10:00:00Z"))), final=True)
check("--final on a two-entry ledger without any chain → one WARN, no ERROR",
      not any("chain" in e for e in errs) and any("no entry carries prev_sha256" in w for w in warns), str(errs) + str(warns))

# ---- prompt_file_sha256 = the skill's own prompt file
P1 = REPO / "skills/cancer-buddy-organize/references/organizer-prompt-phase1-ocr.md"
real = hashlib.sha256(P1.read_bytes()).hexdigest()
errs, _ = run(ledger(lambda doc: worker(doc, "p1-s001-1").__setitem__("prompt_file_sha256", real)))
check("a worker that read the shipped phase1 prompt → passes", errs == [], str(errs))
errs, _ = run(ledger(lambda doc: worker(doc, "p1-s001-1").__setitem__("prompt_file_sha256", "0" * 64)))
check("a worker that read another (edited / abridged) prompt file → ERROR", any("not the skill's references/organizer-prompt-phase1-ocr.md" in e for e in errs), str(errs))
check("schema accepts prompt_file_sha256 and prev_sha256",
      synlib.schema_errors("update_log.schema.json", synlib.load(d, "update_log.json")) == [])

print(f"audit-log-guards: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
