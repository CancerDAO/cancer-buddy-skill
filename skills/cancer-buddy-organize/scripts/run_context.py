#!/usr/bin/env python3
"""Create and pin one organize run per patient directory.

An active run is always resumed.  Starting a different run requires the current
run to be completed first and an explicit ``--new`` flag.  This small contract
prevents a recovery attempt from silently splitting one organize job across two
run IDs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "organize_run_v1"
STATE_NAME = ".organize_run.json"
LOCK_NAME = ".organize_run.lock"
PATIENT_RE = re.compile(r"^PT-[A-F0-9]{6,32}$")
RUN_RE = re.compile(r"^RUN-\d{8}T\d{6}Z-[A-F0-9]{6}$")


class RunContextError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"RUN-{stamp}-{secrets.token_hex(3).upper()}"


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def patient_dir(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_dir():
        raise RunContextError(f"patient directory does not exist: {path}")
    if not PATIENT_RE.fullmatch(path.name):
        raise RunContextError(f"patient directory name is not a patient_code: {path.name}")
    return path


def state_path(patient: Path) -> Path:
    return patient / STATE_NAME


@contextmanager
def exclusive_update(patient: Path):
    """Use a non-blocking OS lock, which the kernel releases after a crash."""
    lock = patient / LOCK_NAME
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RunContextError("another organizer is updating the pinned run; retry") from exc
            acquired = True
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RunContextError("another organizer is updating the pinned run; retry") from exc
            acquired = True
        yield
    finally:
        try:
            if acquired and os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            elif acquired:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def load_state(patient: Path) -> dict | None:
    path = state_path(patient)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunContextError(f"invalid {STATE_NAME}: {exc}") from exc
    required = {"schema", "patient_code", "run_id", "status", "started_at"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise RunContextError(f"invalid {STATE_NAME}: missing required fields")
    if value["schema"] != SCHEMA or value["patient_code"] != patient.name:
        raise RunContextError(f"invalid {STATE_NAME}: identity mismatch")
    if value["status"] not in {"active", "complete"}:
        raise RunContextError(f"invalid {STATE_NAME}: unknown status")
    if not isinstance(value["run_id"], str) or not RUN_RE.fullmatch(value["run_id"]):
        raise RunContextError(f"invalid {STATE_NAME}: malformed run_id")
    return value


def cmd_start(args: argparse.Namespace) -> dict:
    patient = patient_dir(args.patient_dir)
    with exclusive_update(patient):
        current = load_state(patient)
        requested = args.run_id
        if requested and not RUN_RE.fullmatch(requested):
            raise RunContextError("--run-id must match RUN-YYYYMMDDTHHMMSSZ-XXXXXX")

        if current and current["status"] == "active":
            if args.new:
                raise RunContextError("an active run already exists; complete it before --new")
            if requested and requested != current["run_id"]:
                raise RunContextError(
                    f"active run is pinned to {current['run_id']}; refusing {requested}"
                )
            result = dict(current)
            result["resumed"] = True
            return result

        if current and current["status"] == "complete" and not args.new:
            raise RunContextError("previous run is complete; pass --new to start another run")

        if current and requested == current["run_id"]:
            raise RunContextError("--new must use a different run_id from the completed run")

        run_id = requested or new_run_id()
        value = {
            "schema": SCHEMA,
            "patient_code": patient.name,
            "run_id": run_id,
            "status": "active",
            "started_at": now_iso(),
        }
        atomic_json(state_path(patient), value)
        (patient / ".staging" / "runs" / run_id).mkdir(parents=True, exist_ok=True)
        result = dict(value)
        result["resumed"] = False
        return result


def cmd_status(args: argparse.Namespace) -> dict:
    patient = patient_dir(args.patient_dir)
    current = load_state(patient)
    if current is None:
        raise RunContextError("no organize run exists")
    return current


def cmd_complete(args: argparse.Namespace) -> dict:
    patient = patient_dir(args.patient_dir)
    with exclusive_update(patient):
        current = load_state(patient)
        if current is None or current["status"] != "active":
            raise RunContextError("no active organize run exists")
        if args.run_id != current["run_id"]:
            raise RunContextError(
                f"active run is pinned to {current['run_id']}; refusing {args.run_id}"
            )
        value = dict(current)
        value["status"] = "complete"
        value["completed_at"] = now_iso()
        atomic_json(state_path(patient), value)
        return value


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start or resume the one active run")
    start.add_argument("patient_dir")
    start.add_argument("--run-id")
    start.add_argument("--new", action="store_true")
    start.set_defaults(func=cmd_start)

    status = sub.add_parser("status", help="print the pinned run")
    status.add_argument("patient_dir")
    status.set_defaults(func=cmd_status)

    complete = sub.add_parser("complete", help="mark the pinned run complete")
    complete.add_argument("patient_dir")
    complete.add_argument("--run-id", required=True)
    complete.set_defaults(func=cmd_complete)
    return ap


def main() -> int:
    args = parser().parse_args()
    try:
        result = args.func(args)
    except RunContextError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
