"""_gate_provenance.py — the audit-log gate of validate_structured_outputs.py (ORG-P1-09).

The orchestrator's own record `raw/_dispatch_log.jsonl` (one `{at, event, worker_id, phase, files}` line per
dispatch / kill / redispatch, appended as it happens) is cross-checked against the ledger Phase 2 writes:

  * every `kill` is a worker that update_log.json records as `killed` / `timeout` with a degradation — a kill
    rewritten as `retried` or `done`, or its degradation deleted, is an ERROR;
  * every Phase 1 kill is followed by a dispatch / redispatch of (some of) the same files — single-file workers
    or a stub worker (SKILL.md Step 4);
  * a Phase 2 job is dispatched at most twice (the first dispatch + one redispatch): a third dispatch after kills
    is `phase2_retry_exceeded`.

update_log.json's `prev_sha256` chain (scripts/update_log_append.py) is re-computed whenever an entry carries it;
under --final a ledger with no chain at all is one WARN. A worker's `prompt_file_sha256` (the sha256 of the prompt
file it read) must equal the skill's own file for that phase — a worker handed an edited or abridged copy of its
prompt file reports another hash. (It binds the worker to the shipped file; when the orchestrator pastes the prompt
text inline it cannot prove the pasted text was unaltered — that stays a prompt rule, SKILL.md invariant 4.)
Nothing here runs when the data is absent: an archive without a dispatch log, a chain or prompt hashes is checked
as before.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DISPATCH_LOG = "raw/_dispatch_log.jsonl"
KILLED_STATUSES = ("killed", "timeout")
PHASE2_MAX_DISPATCHES = 2
# the prompt file each worker phase reads (paths relative to the skill directory)
PROMPT_FILES = {
    "phase1": "references/organizer-prompt-phase1-ocr.md",
    "phase1_retry": "references/organizer-prompt-phase1-ocr.md",
    "phase1_continuation": "references/organizer-prompt-phase1-ocr.md",
    "phase1_digest": "references/organizer-prompt-phase1-ocr.md",
    "stub": "references/organizer-prompt-phase1-ocr.md",
    "phase2": "references/organizer-prompt-phase2-synthesis.md",
    "phase2_5": "references/organizer-prompt-phase2_5-faithfulness.md",
    "pii_rescan": "references/pii-rescan-prompt.md",
    "segment_c": "references/conversation-incremental-prompt.md",
    "segment_d": "references/case-summary-html-prompt.md",
}


def load_dispatch_log(patient_dir: Path) -> tuple[list[dict] | None, list[str]]:
    p = patient_dir / DISPATCH_LOG
    if not p.is_file():
        return None, []
    events, problems = [], []
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            problems.append(f"{DISPATCH_LOG}:{i} is not one JSON object per line")
            continue
        if isinstance(e, dict):
            events.append(e)
    return events, problems


def _phase_of(e: dict) -> str:
    return str(e.get("phase") or "")


def dispatch_problems(events: list[dict], ledger: dict) -> list[str]:
    out: list[str] = []
    workers: dict[str, dict] = {}
    degraded: set[str] = set()
    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for w in entry.get("workers") or []:
            if isinstance(w, dict) and isinstance(w.get("worker_id"), str):
                workers.setdefault(w["worker_id"], w)
                if w.get("status") in KILLED_STATUSES:
                    workers[w["worker_id"]] = w
        for d in entry.get("degradations") or []:
            if isinstance(d, dict):
                degraded.add(str(d.get("worker_id")))
    kills = [(i, e) for i, e in enumerate(events) if e.get("event") == "kill"]
    for i, e in kills:
        wid = str(e.get("worker_id"))
        w = workers.get(wid)
        if w is None:
            out.append(f"{DISPATCH_LOG}: worker {wid!r} was killed but update_log.json does not list it in workers[]")
        elif w.get("status") not in KILLED_STATUSES:
            out.append(f"update_log.json: worker {wid!r} was killed ({DISPATCH_LOG}) but is recorded as {w.get('status')!r} "
                       "— a kill is recorded as status killed (or timeout) with a degradation, never rewritten")
        if wid not in degraded:
            out.append(f"update_log.json: worker {wid!r} was killed ({DISPATCH_LOG}) but no degradations[] entry records it")
        if _phase_of(e).startswith("phase1") and _phase_of(e) != "phase1_digest":
            files = set(map(str, e.get("files") or (w or {}).get("files") or []))
            later = [x for x in events[i + 1:] if x.get("event") in ("dispatch", "redispatch")
                     and (not files or files & set(map(str, x.get("files") or [])))]
            if not later:
                out.append(f"{DISPATCH_LOG}: Phase 1 worker {wid!r} was killed and none of its files was redispatched "
                           "(single-file worker or stub worker, SKILL.md Step 4)")
    # Phase 2: a job is its first dispatch plus the redispatches that follow a kill of the previous attempt
    killed = {str(e.get("worker_id")) for _, e in kills}
    chain = 0
    prev_killed = False
    for e in events:
        if _phase_of(e) != "phase2" or e.get("event") not in ("dispatch", "redispatch"):
            continue
        chain = chain + 1 if prev_killed else 1
        prev_killed = str(e.get("worker_id")) in killed
        if chain > PHASE2_MAX_DISPATCHES:
            out.append(f"phase2_retry_exceeded: Phase 2 was dispatched {chain} times for one job ({e.get('worker_id')!r} "
                       f"at {e.get('at')}) — the same prompt is redispatched once, then the run stops and reports "
                       "(SKILL.md invariant 4)")
    return out


def _sha_file(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def prompt_problems(ledger: dict, skill_dir: Path, ingest_modes: tuple = ()) -> list[str]:
    """Only the current run is compared with the current skill files: entries from the last ingest run onward (all
    entries when there is none). The ledger is append-only across runs while the skill is updated between them, so
    an earlier run's hashes legitimately name earlier prompt files."""
    out: list[str] = []
    cache: dict[str, str | None] = {}
    entries = [e for e in ledger.get("entries") or [] if isinstance(e, dict)]
    last = max((i for i, e in enumerate(entries) if e.get("run_mode") in ingest_modes), default=0)
    for entry in entries[last:]:
        for w in (entry.get("workers") or []) if isinstance(entry, dict) else []:
            if not isinstance(w, dict) or not w.get("prompt_file_sha256"):
                continue
            rel = PROMPT_FILES.get(str(w.get("phase")))
            if rel is None:
                continue
            if rel not in cache:
                cache[rel] = _sha_file(skill_dir / rel)
            if cache[rel] and w["prompt_file_sha256"] != cache[rel]:
                out.append(f"update_log.json: worker {w.get('worker_id')!r} ({w.get('phase')}) read a prompt file hashing to "
                           f"{str(w['prompt_file_sha256'])[:12]}…, not the skill's {rel} ({cache[rel][:12]}…) — worker "
                           "prompts are the reference file verbatim (SKILL.md invariant 4)")
    return out


def gate_provenance(patient_dir: Path, errors: list, warnings: list | None = None,
                    generation: str | None = None, final: bool = False) -> None:
    import update_log_append as ula
    import validate_structured_outputs as vso
    add = vso._router(errors, warnings, vso._generation(patient_dir, generation))
    ledger = vso._load_json_quiet(patient_dir / vso.UPDATE_LOG_NAME)
    if not isinstance(ledger, dict) or ledger.get("schema_version") != "1" or not isinstance(ledger.get("entries"), list):
        return
    events, problems = load_dispatch_log(patient_dir)
    for p in problems:
        add(p)
    if events is not None:
        for p in dispatch_problems(events, ledger):
            add(p)
    chain = ula.chain_problems(ledger["entries"])
    for p in chain:
        add(f"update_log_chain_broken: {p}")
    if final and warnings is not None and len(ledger["entries"]) > 1 and \
            not any(isinstance(e, dict) and "prev_sha256" in e for e in ledger["entries"]):
        warnings.append("update_log.json: no entry carries prev_sha256 — Phase 2 appends its entry through "
                        "scripts/update_log_append.py so a later edit of an earlier entry is detectable (phase2 §8)")
    for p in prompt_problems(ledger, vso.REPO_ROOT, vso.INGEST_RUN_MODES):
        add(p)
