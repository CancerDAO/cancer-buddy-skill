#!/usr/bin/env python3
"""Simple same-run semantic PII gate.

The gate deliberately has no generations, worker scheduler, hazard ledger or
cross-run lineage.  It freezes a scope, validates one semantic report, applies
only exact-token ``[PII_MASKED]`` replacements, and requires a clean rescan in
the same pinned organize run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import run_context


SCOPE_SCHEMA = "semantic_pii_scope_v1"
REPORT_SCHEMA = "semantic_pii_report_v1"
CORRECTIONS_SCHEMA = "semantic_pii_corrections_v1"
REVIEW_SCHEMA = "semantic_pii_review_v1"
MASK = "[PII_MASKED]"

FINAL_SURFACES = (
    "profile.json",
    "patient_summary.json",
    "molecular.json",
    "treatment_lines.json",
    "labs.json",
    "comorbidities.json",
    "timeline.json",
    "timeline.md",
    "readiness.json",
    "source_inventory.json",
    "high_risk_review.json",
    "missing_items.json",
    "update_log.json",
    "case_text.md",
    "INDEX.md",
    "AGENTS.md",
    "review_summary.md",
    "review_flags.md",
    "longitudinal_observations.json",
    ".case_summary_data.json",
    "病情简要总结.html",
)


class PiiGateError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(value)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n")


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PiiGateError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PiiGateError(f"invalid {label}: expected object")
    return value


def patient_and_run(patient_arg: str, run_id: str) -> tuple[Path, dict]:
    try:
        patient = run_context.patient_dir(patient_arg)
        state = run_context.load_state(patient)
    except run_context.RunContextError as exc:
        raise PiiGateError(str(exc)) from exc
    if state is None or state["status"] != "active":
        raise PiiGateError("semantic PII gate requires an active organize run")
    if state["run_id"] != run_id:
        raise PiiGateError(f"active run is pinned to {state['run_id']}; refusing {run_id}")
    return patient, state


def relative_inside(patient: Path, value: Path, label: str) -> str:
    try:
        rel = value.resolve().relative_to(patient.resolve()).as_posix()
    except ValueError as exc:
        raise PiiGateError(f"{label} escapes patient directory") from exc
    if rel.startswith("raw/") or rel.startswith(".staging/rasters/"):
        raise PiiGateError(f"{label} cannot target raw image data")
    return rel


def run_file(patient: Path, run_id: str, name: str) -> Path:
    path = patient / ".staging" / "runs" / run_id / "pii" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def collect_scope(patient: Path, stage: str) -> list[Path]:
    if stage == "phase1":
        paths = sorted((patient / "ocr").glob("*.md"))
    else:
        paths = []
        for bucket in sorted(patient.glob("[0-9][0-9]_*")):
            if bucket.is_dir():
                paths.extend(sorted(bucket.rglob("*.md")))
        paths.extend(patient / name for name in FINAL_SURFACES if (patient / name).is_file())
    unique = sorted({p.resolve() for p in paths if p.is_file()}, key=lambda p: p.as_posix())
    if not unique:
        raise PiiGateError(f"no files found for semantic PII stage {stage}")
    return unique


def build_scope(patient: Path, run_id: str, stage: str, pass_name: str) -> dict:
    rows = []
    for path in collect_scope(patient, stage):
        rows.append({"path": relative_inside(patient, path, "scope path"), "sha256": sha256_file(path)})
    identity = {"run_id": run_id, "stage": stage, "files": rows}
    return {
        "schema": SCOPE_SCHEMA,
        "run_id": run_id,
        "stage": stage,
        "pass": pass_name,
        "files": rows,
        "scope_sha256": sha256_bytes(canonical_bytes(identity)),
    }


def default_scope_path(patient: Path, run_id: str, stage: str, pass_name: str) -> Path:
    return run_file(patient, run_id, f"{stage}-{pass_name}-scope.json")


def default_report_path(patient: Path, run_id: str, stage: str, pass_name: str) -> Path:
    return run_file(patient, run_id, f"{stage}-{pass_name}-report.json")


def validate_scope(patient: Path, run_id: str, scope_path: Path, *, live: bool) -> dict:
    scope = load_json(scope_path, "semantic scope")
    if set(scope) != {"schema", "run_id", "stage", "pass", "files", "scope_sha256"}:
        raise PiiGateError("semantic scope has unexpected keys")
    if scope["schema"] != SCOPE_SCHEMA or scope["run_id"] != run_id:
        raise PiiGateError("semantic scope identity mismatch")
    if scope["stage"] not in {"phase1", "final"} or scope["pass"] not in {"before", "after"}:
        raise PiiGateError("semantic scope stage/pass is invalid")
    rows = scope["files"]
    if not isinstance(rows, list) or not rows:
        raise PiiGateError("semantic scope files must be a non-empty array")
    seen: set[str] = set()
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise PiiGateError("semantic scope file row is invalid")
        rel, digest = row["path"], row["sha256"]
        if not isinstance(rel, str) or not isinstance(digest, str) or len(digest) != 64:
            raise PiiGateError("semantic scope file row has invalid values")
        target = patient / rel
        if relative_inside(patient, target, "scope path") != rel or rel in seen:
            raise PiiGateError("semantic scope path is unsafe or duplicated")
        seen.add(rel)
        if live and (not target.is_file() or sha256_file(target) != digest):
            raise PiiGateError(f"semantic scope is stale: {rel}")
        normalized.append({"path": rel, "sha256": digest})
    identity = {"run_id": run_id, "stage": scope["stage"], "files": normalized}
    if sha256_bytes(canonical_bytes(identity)) != scope["scope_sha256"]:
        raise PiiGateError("semantic scope hash mismatch")
    if live:
        current = [relative_inside(patient, path, "current scope path")
                   for path in collect_scope(patient, scope["stage"])]
        if current != [row["path"] for row in normalized]:
            raise PiiGateError("semantic scope membership changed")
    return scope


def occurrences(line: str, token: str) -> list[tuple[int, int]]:
    out = []
    cursor = 0
    while True:
        start = line.find(token, cursor)
        if start < 0:
            return out
        out.append((start, start + len(token)))
        cursor = start + len(token)


def validate_report(patient: Path, run_id: str, scope: dict, report_path: Path, *, clean: bool | None) -> dict:
    report = load_json(report_path, "semantic report")
    exact = {"schema", "run_id", "stage", "scope_sha256", "scanned", "findings", "clean"}
    if set(report) != exact:
        raise PiiGateError("semantic report must use the exact v1 contract")
    if (
        report["schema"] != REPORT_SCHEMA
        or report["run_id"] != run_id
        or report["stage"] != scope["stage"]
        or report["scope_sha256"] != scope["scope_sha256"]
    ):
        raise PiiGateError("semantic report identity mismatch")
    expected = [row["path"] for row in scope["files"]]
    if report["scanned"] != expected:
        raise PiiGateError("semantic report must scan the exact frozen scope in order")
    findings = report["findings"]
    if not isinstance(findings, list):
        raise PiiGateError("semantic findings must be an array")
    row_by_path = {row["path"]: row for row in scope["files"]}
    claimed: set[tuple[str, int, int, str]] = set()
    for finding in findings:
        keys = {"surface", "line", "occurrence", "exact_text", "category"}
        if not isinstance(finding, dict) or set(finding) != keys:
            raise PiiGateError("semantic finding must use the exact v1 contract")
        rel = finding["surface"]
        line_no = finding["line"]
        occurrence = finding["occurrence"]
        token = finding["exact_text"]
        category = finding["category"]
        if rel not in row_by_path or not isinstance(line_no, int) or line_no < 1:
            raise PiiGateError("semantic finding surface/line is invalid")
        if not isinstance(occurrence, int) or occurrence < 1:
            raise PiiGateError("semantic finding occurrence must be >= 1")
        if not isinstance(token, str) or not token or len(token) > 256 or "\n" in token or "\r" in token:
            raise PiiGateError("semantic finding exact_text must be one non-empty line")
        if token == MASK or not isinstance(category, str) or not category.strip():
            raise PiiGateError("semantic finding token/category is invalid")
        lines = (patient / rel).read_text(encoding="utf-8").splitlines()
        if line_no > len(lines) or occurrence > len(occurrences(lines[line_no - 1], token)):
            raise PiiGateError(f"semantic finding does not resolve exactly: {rel}:{line_no}")
        identity = (rel, line_no, occurrence, token)
        if identity in claimed:
            raise PiiGateError("duplicate semantic finding")
        claimed.add(identity)
    if not isinstance(report["clean"], bool) or report["clean"] != (len(findings) == 0):
        raise PiiGateError("semantic report clean flag does not match findings")
    if clean is not None and report["clean"] != clean:
        raise PiiGateError("semantic report does not have the required clean state")
    return report


def cmd_scope(args: argparse.Namespace) -> dict:
    patient, _ = patient_and_run(args.patient_dir, args.run_id)
    scope = build_scope(patient, args.run_id, args.stage, args.pass_name)
    output = Path(args.output).resolve() if args.output else default_scope_path(
        patient, args.run_id, args.stage, args.pass_name
    )
    relative_inside(patient, output, "scope output")
    atomic_json(output, scope)
    report_path = default_report_path(patient, args.run_id, args.stage, args.pass_name)
    return {
        "scope_path": str(output),
        "report_path": str(report_path),
        "scope_sha256": scope["scope_sha256"],
        "files": len(scope["files"]),
    }


def cmd_validate(args: argparse.Namespace) -> dict:
    patient, _ = patient_and_run(args.patient_dir, args.run_id)
    scope_path = Path(args.scope).resolve()
    report_path = Path(args.report).resolve()
    relative_inside(patient, scope_path, "scope")
    relative_inside(patient, report_path, "report")
    scope = validate_scope(patient, args.run_id, scope_path, live=True)
    report = validate_report(patient, args.run_id, scope, report_path, clean=True if args.require_clean else None)
    return {"stage": scope["stage"], "clean": report["clean"], "findings": len(report["findings"])}


def apply_report(patient: Path, report: dict) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for finding in report["findings"]:
        grouped.setdefault(finding["surface"], []).append(finding)
    changes = []
    prepared: dict[Path, bytes] = {}
    for rel, findings in grouped.items():
        path = patient / rel
        before = path.read_bytes()
        text = before.decode("utf-8")
        lines = text.splitlines(keepends=True)
        edits_by_line: dict[int, list[tuple[int, int, dict]]] = {}
        for finding in findings:
            index = finding["line"] - 1
            full_line = lines[index]
            body = full_line.rstrip("\r\n")
            spans = occurrences(body, finding["exact_text"])
            start, end = spans[finding["occurrence"] - 1]
            edits_by_line.setdefault(index, []).append((start, end, finding))
        file_ops = []
        for index, edits in edits_by_line.items():
            ordered = sorted(edits, key=lambda item: (item[0], item[1]))
            if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
                raise PiiGateError(f"overlapping semantic findings in {rel}")
            full_line = lines[index]
            newline = full_line[len(full_line.rstrip("\r\n")) :]
            body = full_line.rstrip("\r\n")
            for start, end, finding in reversed(ordered):
                body = body[:start] + MASK + body[end:]
                file_ops.append(
                    {
                        "line": finding["line"],
                        "occurrence": finding["occurrence"],
                        "category": finding["category"],
                        "original_sha256": sha256_bytes(finding["exact_text"].encode("utf-8")),
                    }
                )
            lines[index] = body + newline
        after = "".join(lines).encode("utf-8")
        if path.suffix == ".json":
            try:
                json.loads(after.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise PiiGateError(f"masking would invalidate JSON {rel}: {exc}") from exc
        prepared[path] = after
        changes.append(
            {
                "path": rel,
                "before_sha256": sha256_bytes(before),
                "after_sha256": sha256_bytes(after),
                "operations": sorted(file_ops, key=lambda item: (item["line"], item["occurrence"])),
            }
        )
    for path, after in prepared.items():
        atomic_bytes(path, after)
    return sorted(changes, key=lambda item: item["path"])


def cmd_apply(args: argparse.Namespace) -> dict:
    patient, _ = patient_and_run(args.patient_dir, args.run_id)
    scope_path, report_path = Path(args.scope).resolve(), Path(args.report).resolve()
    relative_inside(patient, scope_path, "scope")
    relative_inside(patient, report_path, "report")
    scope = validate_scope(patient, args.run_id, scope_path, live=True)
    report = validate_report(patient, args.run_id, scope, report_path, clean=False)
    changes = apply_report(patient, report)
    receipt = {
        "schema": CORRECTIONS_SCHEMA,
        "run_id": args.run_id,
        "stage": scope["stage"],
        "before_scope_sha256": scope["scope_sha256"],
        "report_sha256": sha256_file(report_path),
        "finding_count": len(report["findings"]),
        "files": changes,
    }
    output = Path(args.receipt).resolve() if args.receipt else run_file(
        patient, args.run_id, f"{scope['stage']}-corrections.json"
    )
    relative_inside(patient, output, "corrections receipt")
    atomic_json(output, receipt)
    return {"receipt_path": str(output), "findings": len(report["findings"]), "files": len(changes)}


def review_name(stage: str) -> str:
    return ".semantic_pii_review.phase1.json" if stage == "phase1" else ".semantic_pii_review.json"


def cmd_record(args: argparse.Namespace) -> dict:
    patient, _ = patient_and_run(args.patient_dir, args.run_id)
    scope_path, report_path = Path(args.scope).resolve(), Path(args.report).resolve()
    relative_inside(patient, scope_path, "scope")
    relative_inside(patient, report_path, "report")
    scope = validate_scope(patient, args.run_id, scope_path, live=True)
    report = validate_report(patient, args.run_id, scope, report_path, clean=True)
    corrections_path = Path(args.corrections).resolve() if args.corrections else None
    corrections_rel = None
    corrections_sha = None
    if corrections_path:
        corrections_rel = relative_inside(patient, corrections_path, "corrections")
        corrections = load_json(corrections_path, "corrections")
        if corrections.get("schema") != CORRECTIONS_SCHEMA or corrections.get("run_id") != args.run_id:
            raise PiiGateError("corrections receipt identity mismatch")
        if corrections.get("stage") != scope["stage"]:
            raise PiiGateError("corrections receipt stage mismatch")
        current = {row["path"]: row["sha256"] for row in scope["files"]}
        for row in corrections.get("files", []):
            if current.get(row.get("path")) != row.get("after_sha256"):
                raise PiiGateError("clean scope does not match corrections postimage")
        corrections_sha = sha256_file(corrections_path)
    receipt = {
        "schema": REVIEW_SCHEMA,
        "run_id": args.run_id,
        "stage": scope["stage"],
        "clean": True,
        "scope_path": relative_inside(patient, scope_path, "scope"),
        "scope_sha256": scope["scope_sha256"],
        "scope_file_sha256": sha256_file(scope_path),
        "report_path": relative_inside(patient, report_path, "report"),
        "report_sha256": sha256_file(report_path),
        "corrections_path": corrections_rel,
        "corrections_sha256": corrections_sha,
    }
    output = patient / review_name(scope["stage"])
    atomic_json(output, receipt)
    return {"review_path": str(output), "stage": scope["stage"], "clean": True}


def cmd_check(args: argparse.Namespace) -> dict:
    patient = run_context.patient_dir(args.patient_dir)
    state = run_context.load_state(patient)
    if state is None:
        raise PiiGateError("no organize run exists")
    receipt_path = patient / review_name(args.stage)
    receipt = load_json(receipt_path, "semantic review receipt")
    exact = {
        "schema", "run_id", "stage", "clean", "scope_path", "scope_sha256",
        "scope_file_sha256", "report_path", "report_sha256", "corrections_path",
        "corrections_sha256",
    }
    if set(receipt) != exact or receipt.get("schema") != REVIEW_SCHEMA:
        raise PiiGateError("semantic review receipt contract mismatch")
    if receipt["run_id"] != state["run_id"] or receipt["stage"] != args.stage or receipt["clean"] is not True:
        raise PiiGateError("semantic review receipt identity mismatch")
    scope_path = patient / receipt["scope_path"]
    report_path = patient / receipt["report_path"]
    if sha256_file(scope_path) != receipt["scope_file_sha256"] or sha256_file(report_path) != receipt["report_sha256"]:
        raise PiiGateError("semantic review evidence hash mismatch")
    scope = validate_scope(patient, state["run_id"], scope_path, live=args.stage == "final")
    if scope["scope_sha256"] != receipt["scope_sha256"]:
        raise PiiGateError("semantic review scope binding mismatch")
    validate_report(patient, state["run_id"], scope, report_path, clean=True)
    if receipt["corrections_path"] is not None:
        corrections = patient / receipt["corrections_path"]
        if sha256_file(corrections) != receipt["corrections_sha256"]:
            raise PiiGateError("semantic corrections evidence hash mismatch")
    return {"stage": args.stage, "run_id": state["run_id"], "clean": True}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    scope = sub.add_parser("scope")
    scope.add_argument("patient_dir")
    scope.add_argument("--run-id", required=True)
    scope.add_argument("--stage", choices=("phase1", "final"), required=True)
    scope.add_argument("--pass", dest="pass_name", choices=("before", "after"), required=True)
    scope.add_argument("--output")
    scope.set_defaults(func=cmd_scope)

    validate = sub.add_parser("validate-report")
    validate.add_argument("patient_dir")
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--scope", required=True)
    validate.add_argument("--report", required=True)
    validate.add_argument("--require-clean", action="store_true")
    validate.set_defaults(func=cmd_validate)

    apply = sub.add_parser("apply")
    apply.add_argument("patient_dir")
    apply.add_argument("--run-id", required=True)
    apply.add_argument("--scope", required=True)
    apply.add_argument("--report", required=True)
    apply.add_argument("--receipt")
    apply.set_defaults(func=cmd_apply)

    record = sub.add_parser("record-clean")
    record.add_argument("patient_dir")
    record.add_argument("--run-id", required=True)
    record.add_argument("--scope", required=True)
    record.add_argument("--report", required=True)
    record.add_argument("--corrections")
    record.set_defaults(func=cmd_record)

    check = sub.add_parser("check")
    check.add_argument("patient_dir")
    check.add_argument("--stage", choices=("phase1", "final"), required=True)
    check.set_defaults(func=cmd_check)
    return ap


def main() -> int:
    args = parser().parse_args()
    try:
        result = args.func(args)
    except (PiiGateError, run_context.RunContextError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
