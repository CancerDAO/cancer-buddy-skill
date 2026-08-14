#!/usr/bin/env python3
"""Validate and query the small organize-lite Phase 4 file-state DAG.

This is deliberately a planner, not a runtime. It stores no run state, creates no
receipts, has no retry queue and never launches a worker. Completion is inferred
from non-empty owned outputs already present in ``patient_dir``. Call it only
after the previously returned batch has settled; it cannot distinguish an
in-flight task from a task that has not started.

Examples:
    python3 plan_phase4.py --validate-only
    python3 plan_phase4.py /path/to/patients/PT-ABC123 --available-slots 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_DAG = (
    Path(__file__).resolve().parent.parent
    / "references"
    / "runtime-bindings"
    / "phase4-dag.json"
)
EXPECTED_WAVE_A = ["labs", "comorbidities", "missing_items"]
EXPECTED_WAVE_B = ["molecular", "treatment", "patient_summary", "timeline", "case_text"]
RUN_ID_RE = re.compile(r"^RUN-\d{8}T\d{6}Z-[A-F0-9]{6}$")
EXPECTED_SCHEMAS = {
    "labs": {"labs.json": "{skill_dir}/references/schemas/labs.schema.json"},
    "comorbidities": {
        "comorbidities.json": "{skill_dir}/references/schemas/comorbidities.schema.json"
    },
    "missing_items": {
        "missing_items.json": "{skill_dir}/references/schemas/missing_items.schema.json"
    },
    "molecular": {
        "molecular.json": "{skill_dir}/references/schemas/molecular.schema.json"
    },
    "treatment": {
        "treatment_lines.json": "{skill_dir}/references/schemas/treatment_lines.schema.json"
    },
    "patient_summary": {
        "patient_summary.json": "{skill_dir}/references/schemas/patient_summary.schema.json"
    },
    "timeline": {
        "timeline.json": "{skill_dir}/references/schemas/timeline.schema.json",
        "longitudinal_observations.json": (
            "{skill_dir}/references/schemas/longitudinal_observations.schema.json"
        ),
    },
    "readiness_review": {
        "readiness.json": "{skill_dir}/references/schemas/readiness.schema.json"
    },
    "case_summary_data": {
        ".case_summary_data.json": (
            "{skill_dir}/references/schemas/case_summary_data.schema.json"
        )
    },
}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read DAG {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("DAG root must be an object")
    return value


def _artifact_paths(task: dict[str, Any]) -> list[str]:
    return list(task.get("outputs") or []) + list(task.get("optional_outputs") or [])


def _safe_relative_artifact(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts)


def validate_dag(dag: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if dag.get("schema") != "organize_phase4_dag_v1":
        errors.append("schema must be organize_phase4_dag_v1")

    raw_tasks = dag.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return errors + ["tasks must be a non-empty array"]

    tasks: dict[str, dict[str, Any]] = {}
    owner: dict[str, str] = {}
    for index, task in enumerate(raw_tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"tasks[{index}] has no valid id")
            continue
        if task_id in tasks:
            errors.append(f"duplicate task id: {task_id}")
            continue
        tasks[task_id] = task
        if task.get("kind") not in {"llm_worker", "deterministic"}:
            errors.append(f"{task_id}: kind must be llm_worker or deterministic")
        if not isinstance(task.get("stage"), int):
            errors.append(f"{task_id}: stage must be an integer")
        outputs = task.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            errors.append(f"{task_id}: outputs must be a non-empty array")
        for artifact in _artifact_paths(task):
            if not _safe_relative_artifact(artifact):
                errors.append(f"{task_id}: unsafe artifact path: {artifact!r}")
                continue
            previous = owner.get(artifact)
            if previous:
                errors.append(
                    f"output owner conflict: {artifact} is owned by both {previous} and {task_id}"
                )
            else:
                owner[artifact] = task_id
        for required in task.get("required_files") or []:
            if not _safe_relative_artifact(required):
                errors.append(f"{task_id}: unsafe required file: {required!r}")

    for task_id, task in tasks.items():
        deps = task.get("depends_on")
        if not isinstance(deps, list):
            errors.append(f"{task_id}: depends_on must be an array")
            continue
        for dep in deps:
            if dep not in tasks:
                errors.append(f"{task_id}: unknown dependency: {dep}")
            if dep == task_id:
                errors.append(f"{task_id}: self dependency")

    # Kahn's algorithm: any nodes left with indegree > 0 belong to a cycle.
    if tasks:
        indegree = {task_id: 0 for task_id in tasks}
        children = {task_id: [] for task_id in tasks}
        for task_id, task in tasks.items():
            for dep in task.get("depends_on") or []:
                if dep in tasks:
                    indegree[task_id] += 1
                    children[dep].append(task_id)
        queue = sorted(task_id for task_id, degree in indegree.items() if degree == 0)
        seen: list[str] = []
        while queue:
            current = queue.pop(0)
            seen.append(current)
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort()
        if len(seen) != len(tasks):
            cyclic = sorted(task_id for task_id, degree in indegree.items() if degree > 0)
            errors.append(f"dependency cycle detected: {', '.join(cyclic)}")

    contract = dag.get("scheduler_contract") or {}
    wave_a = ((contract.get("wave_a") or {}).get("members"))
    wave_b = ((contract.get("wave_b") or {}).get("members"))
    if wave_a != EXPECTED_WAVE_A:
        errors.append(f"Wave A must be exactly: {', '.join(EXPECTED_WAVE_A)}")
    if wave_b != EXPECTED_WAVE_B:
        errors.append(f"Wave B must be exactly: {', '.join(EXPECTED_WAVE_B)}")
    if (contract.get("wave_a") or {}).get("dispatch") != "all_before_wait":
        errors.append("Wave A dispatch policy must be all_before_wait")
    if (contract.get("wave_b") or {}).get("dispatch") != "up_to_available_slots_then_wait":
        errors.append("Wave B dispatch policy must be up_to_available_slots_then_wait")
    for task_id in EXPECTED_WAVE_A:
        if task_id in tasks and tasks[task_id].get("wave") != "A":
            errors.append(f"{task_id}: must belong to Wave A")
    for task_id in EXPECTED_WAVE_B:
        if task_id in tasks and tasks[task_id].get("wave") != "B":
            errors.append(f"{task_id}: must belong to Wave B")

    # Safety-critical routing is contract, not a prose suggestion.
    required_routes = {
        # Bucket labels are localized; the NN_ prefix is the stable routing key.
        "molecular": ["06_"],
        "treatment": ["03_", "08_", "09_"],
        "comorbidities": ["02_", "03_"],
    }
    for task_id, expected in required_routes.items():
        if task_id in tasks and tasks[task_id].get("sidecar_buckets") != expected:
            errors.append(f"{task_id}: sidecar_buckets must be exactly {expected!r}")

    for task_id, expected in EXPECTED_SCHEMAS.items():
        if task_id in tasks and tasks[task_id].get("schemas") != expected:
            errors.append(f"{task_id}: schemas must be exactly {expected!r}")

    patient_outputs = _artifact_paths(tasks.get("patient_summary", {}))
    if "profile.json" in patient_outputs:
        errors.append("patient_summary must not own profile.json")
    if owner.get("profile.json") != "profile":
        errors.append("profile.json must be owned only by deterministic task profile")
    if owner.get("update_log.json") != "finalize_log":
        errors.append("update_log.json must be owned only by finalize_log")
    finalize = tasks.get("finalize_log") or {}
    commands = finalize.get("commands") or []
    flattened = [str(part) for command in commands for part in (command if isinstance(command, list) else [])]
    if "--finalize-log" not in flattened or "build_inventory_index.py" not in " ".join(flattened):
        errors.append("finalize_log must call build_inventory_index.py --finalize-log")

    return errors


def _usable(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _task_complete(
    task: dict[str, Any], patient_dir: Path, by_id: dict[str, dict[str, Any]], run_id: str
) -> bool:
    outputs = [patient_dir / item for item in task.get("outputs") or []]
    if not outputs or not all(_usable(path) for path in outputs):
        return False
    if task.get("id") == "finalize_log":
        try:
            log = json.loads(outputs[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        runs = log.get("runs") if isinstance(log, dict) else None
        if not isinstance(runs, list) or not any(
            isinstance(row, dict) and row.get("run_id") == run_id for row in runs
        ):
            return False
    if not task.get("fresh_after_dependencies"):
        return True

    dependency_inputs: list[Path] = []
    for dep_id in task.get("depends_on") or []:
        dep = by_id[dep_id]
        dependency_inputs.extend(patient_dir / item for item in dep.get("outputs") or [])
    dependency_inputs.extend(patient_dir / item for item in task.get("required_files") or [])
    usable_inputs = [path for path in dependency_inputs if _usable(path)]
    if len(usable_inputs) != len(dependency_inputs):
        return False
    newest_input = max((path.stat().st_mtime_ns for path in usable_inputs), default=0)
    oldest_output = min(path.stat().st_mtime_ns for path in outputs)
    return oldest_output >= newest_input


def _render(value: Any, *, patient_dir: Path, skill_dir: Path, run_id: str) -> Any:
    if isinstance(value, str):
        return (
            value.replace("{patient_dir}", str(patient_dir))
            .replace("{skill_dir}", str(skill_dir))
            .replace("{run_id}", run_id)
            .replace("{python}", sys.executable)
        )
    if isinstance(value, list):
        return [
            _render(item, patient_dir=patient_dir, skill_dir=skill_dir, run_id=run_id)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _render(item, patient_dir=patient_dir, skill_dir=skill_dir, run_id=run_id)
            for key, item in value.items()
        }
    return value


def next_batch(
    dag: dict[str, Any], patient_dir: Path, available_slots: int, run_id: str
) -> dict[str, Any]:
    tasks_in_order = list(dag["tasks"])
    by_id = {task["id"]: task for task in tasks_in_order}
    complete = {
        task_id: _task_complete(task, patient_dir, by_id, run_id)
        for task_id, task in by_id.items()
    }
    pending = [task["id"] for task in tasks_in_order if not complete[task["id"]]]
    if not pending:
        return {
            "ok": True,
            "complete": True,
            "ready_wave": None,
            "dispatch_policy": None,
            "ready": [],
            "pending": [],
            "completed": [task["id"] for task in tasks_in_order],
        }

    ready = []
    for task in tasks_in_order:
        if complete[task["id"]]:
            continue
        if not all(complete.get(dep, False) for dep in task.get("depends_on") or []):
            continue
        if not all(_usable(patient_dir / item) for item in task.get("required_files") or []):
            continue
        ready.append(task)

    if not ready:
        missing_external = {
            task["id"]: [
                item
                for item in task.get("required_files") or []
                if not _usable(patient_dir / item)
            ]
            for task in tasks_in_order
            if not complete[task["id"]]
            and all(complete.get(dep, False) for dep in task.get("depends_on") or [])
        }
        missing_external = {key: value for key, value in missing_external.items() if value}
        return {
            "ok": True,
            "complete": False,
            "ready_wave": None,
            "dispatch_policy": None,
            "ready": [],
            "pending": pending,
            "completed": [task["id"] for task in tasks_in_order if complete[task["id"]]],
            "blocked_on_required_files": missing_external,
        }

    earliest_stage = min(task["stage"] for task in ready)
    ready = [task for task in ready if task["stage"] == earliest_stage]
    wave = ready[0].get("wave")
    if wave == "A":
        policy = "all_before_wait"
        if available_slots < len(ready):
            return {
                "ok": True,
                "complete": False,
                "ready_wave": "A",
                "dispatch_policy": policy,
                "ready": [],
                "needs_slots": len(ready),
                "available_slots": available_slots,
                "pending": pending,
                "completed": [task["id"] for task in tasks_in_order if complete[task["id"]]],
            }
        selected = ready
    elif wave == "B":
        policy = "up_to_available_slots_then_wait"
        selected = ready[:available_slots]
    else:
        policy = "run_returned_tasks_then_replan"
        selected = ready[:available_slots]

    skill_dir = Path(__file__).resolve().parent.parent
    rendered_ready = []
    for task in selected:
        rendered = _render(
            task, patient_dir=patient_dir, skill_dir=skill_dir, run_id=run_id
        )
        if rendered.get("kind") == "llm_worker":
            # The planner itself is invoked with the host-selected Python.  Carry
            # that exact interpreter into every worker envelope so a child does
            # not silently fall back to a different `python3` without jsonschema.
            rendered["python_executable"] = sys.executable
        rendered_ready.append(rendered)

    return {
        "ok": True,
        "complete": False,
        "ready_wave": wave or f"stage-{earliest_stage}",
        "dispatch_policy": policy,
        "ready": rendered_ready,
        "pending": pending,
        "completed": [task["id"] for task in tasks_in_order if complete[task["id"]]],
        "planner_note": "Re-run only after every task in this returned batch has settled; no in-flight state is stored.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient_dir", nargs="?")
    parser.add_argument("--run-id")
    parser.add_argument("--dag", default=str(DEFAULT_DAG))
    parser.add_argument("--available-slots", type=int, default=3)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        dag = _load(Path(args.dag))
    except ValueError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    errors = validate_dag(dag)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    if args.validate_only:
        print(
            json.dumps(
                {
                    "ok": True,
                    "schema": dag["schema"],
                    "tasks": len(dag["tasks"]),
                    "acyclic": True,
                    "unique_output_owners": True,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if not args.patient_dir:
        parser.error("patient_dir is required unless --validate-only is used")
    if not args.run_id or not RUN_ID_RE.fullmatch(args.run_id):
        parser.error("--run-id must match RUN-YYYYMMDDTHHMMSSZ-XXXXXX")
    if args.available_slots < 1:
        parser.error("--available-slots must be >= 1")
    patient_dir = Path(args.patient_dir).resolve()
    if not patient_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"not a directory: {patient_dir}"}))
        return 2
    try:
        run_state = json.loads((patient_dir / ".organize_run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"ok": False, "error": "active .organize_run.json missing"}))
        return 2
    if run_state.get("status") != "active" or run_state.get("run_id") != args.run_id:
        print(
            json.dumps(
                {"ok": False, "error": f"active run is pinned to {run_state.get('run_id')}"}
            )
        )
        return 2

    print(
        json.dumps(
            next_batch(dag, patient_dir, args.available_slots, args.run_id),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
