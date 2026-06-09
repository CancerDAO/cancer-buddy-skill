#!/usr/bin/env python3
"""
run_redaction_job.py — pre-persist 段B PaddleOCR redaction batch processor.

Reads redaction_manifest.json (produced by 段A phase2-synthesis), redacts each
bucket image in place using the vendored redact_ocr.redact_image_ocr(), QA-gates
the result with a second PaddleOCR pass, and — only when QA passes — replaces the
bucket image and its 10_原始文件/ mirror with the redacted version and deletes the
pre-redaction originals. Progress is written to redaction_status.json.

This is the irreversible step: an original (upload copy + mirror copy) is deleted
ONLY when its file entry reaches qa_passed=true. QA failure keeps the original and
marks the file 'failed' for manual review.

Run model: a backend worker may schedule this after 段A/段D, but archive/persist
must wait for it. The platform worker hands the manifest to this script before
any source file leaves the local workspace. Idempotent and retryable — files
already 'done' are skipped on re-run.

venv: requires PaddleOCR in ~/.venvs/mtb-ocr. If that venv is missing, every file
is marked 'blocked' and the status file explains how to provision it. No PaddleOCR
is invoked in that case.

Usage:
    python3 run_redaction_job.py <patient_dir>
    python3 run_redaction_job.py --manifest <path/to/redaction_manifest.json>

Contracts:
    references/schemas/redaction_manifest.schema.json   (input)
    references/schemas/redaction_status.schema.json      (output)
    references/redaction-job.md                           (prose)

Exit codes:
    0  — status written; no fatal errors (per-file failed/blocked are not fatal)
    1  — at least one file ended 'failed' or 'blocked'
    2  — bad invocation / manifest unreadable
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = Path(os.environ.get("HOME", "")) / ".venvs" / "mtb-ocr" / "bin" / "python"

MANIFEST_NAME = "redaction_manifest.json"
STATUS_NAME = "redaction_status.json"

# QA gate: a redacted image passes only when a second redaction-detection pass
# finds at most this many residual PII regions inside it. Any residual region
# means a target PII area was not fully covered → fail, keep original.
QA_RESIDUAL_PII_ALLOWED = 0


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# venv / engine availability
# ---------------------------------------------------------------------------


def venv_available() -> bool:
    """True only when the PaddleOCR venv interpreter exists. We do not import
    paddleocr from this process — the venv interpreter owns those deps. This
    script is expected to be launched WITH ~/.venvs/mtb-ocr/bin/python so that
    `import redact_ocr` resolves paddleocr/PIL transitively at redact time."""
    return VENV_PYTHON.is_file()


def _import_redactor():
    """Import the vendored redactor. Returns (module, None) or (None, error_str)."""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import redact_ocr  # type: ignore

        return redact_ocr, None
    except Exception as e:  # pragma: no cover — env-dependent
        return None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# manifest / status IO
# ---------------------------------------------------------------------------


def load_manifest(manifest_path: Path) -> dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != "redaction_manifest_v1":
        raise ValueError(
            f"unexpected manifest schema: {data.get('schema')!r} "
            "(expected 'redaction_manifest_v1')"
        )
    if not isinstance(data.get("files"), list):
        raise ValueError("manifest.files must be a list")
    return data


def load_existing_status(status_path: Path) -> dict[str, dict]:
    """Return {id: file_entry} from a prior status file, or {} if none/invalid."""
    if not status_path.is_file():
        return {}
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {e["id"]: e for e in data.get("files", []) if "id" in e}
    except Exception:
        return {}


def write_status(status_path: Path, patient_dir: Path, file_entries: list[dict]) -> dict:
    """Recompute summary, write redaction_status.json atomically. Returns the doc."""
    summary = {"total": len(file_entries), "pending": 0, "done": 0, "failed": 0, "blocked": 0}
    for e in file_entries:
        st = e.get("status", "pending")
        if st in summary:
            summary[st] += 1
    doc = {
        "schema": "redaction_status_v1",
        "patient_dir": str(patient_dir),
        "updated_at": _now_iso(),
        "summary": summary,
        "files": file_entries,
    }
    tmp = status_path.with_suffix(status_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, status_path)
    return doc


# ---------------------------------------------------------------------------
# per-file redaction + QA gate
# ---------------------------------------------------------------------------


def qa_gate(redactor, redacted_path: Path) -> tuple[bool, str | None]:
    """
    Second-pass QA on the already-redacted image. Re-runs the same OCR+NER PII
    detection over the masked image; if it still finds recognizable PII regions,
    the original masking left a residual and the gate FAILS.

    Returns (passed, reason). reason is None when passed.
    """
    with tempfile.TemporaryDirectory(prefix="redact_qa_") as td:
        throwaway = str(Path(td) / ("qa_" + redacted_path.name))
        try:
            res = redactor.redact_image_ocr(
                input_path=str(redacted_path),
                output_path=throwaway,
                confidence_threshold=0.5,
                debug=False,
                no_ner=False,
            )
        except Exception as e:
            return (False, f"QA 二次扫描异常: {type(e).__name__}: {e}")

    if not res.get("success"):
        return (False, f"QA 二次扫描失败: {res.get('error', 'unknown')}")

    residual = res.get("pii_detected", 0)
    if residual > QA_RESIDUAL_PII_ALLOWED:
        previews = [r.get("text_preview", "?") for r in res.get("regions", [])][:5]
        return (False, f"QA 残留 PII: 二次扫描仍检出 {residual} 个 PII 区域未被框覆盖 ({previews})")
    return (True, None)


def process_file(
    redactor,
    patient_dir: Path,
    entry: dict,
) -> dict:
    """
    Redact one manifest entry, QA-gate it, and — only on pass — replace bucket
    image + mirror and delete the pre-redaction originals.

    Returns a redaction_status.json file entry.
    """
    fid = entry["id"]
    bucket_rel = entry["bucket_path"]
    mirror_rel = entry["mirror_path"]
    bucket_abs = patient_dir / bucket_rel
    mirror_abs = patient_dir / mirror_rel

    base = {
        "id": fid,
        "status": "pending",
        "redacted_path": None,
        "qa_passed": None,
        "original_deleted": None,
        "reason": None,
    }

    if not bucket_abs.is_file():
        base.update(status="failed", reason=f"桶内图缺失: {bucket_rel}")
        return base

    # 1) Redact into a sidecar temp next to the bucket image (never overwrite
    #    the original until QA passes — keep a recoverable state on failure).
    redacted_tmp = bucket_abs.with_name(bucket_abs.stem + "__redacted_tmp" + bucket_abs.suffix)
    try:
        res = redactor.redact_image_ocr(
            input_path=str(bucket_abs),
            output_path=str(redacted_tmp),
            confidence_threshold=0.5,
            debug=False,
            no_ner=False,
        )
    except Exception as e:
        _safe_unlink(redacted_tmp)
        base.update(status="failed", reason=f"打码异常: {type(e).__name__}: {e}")
        return base

    if not res.get("success"):
        _safe_unlink(redacted_tmp)
        base.update(status="failed", reason=f"打码失败: {res.get('error', 'unknown')}")
        return base

    # 2) QA gate — irreversible deletes are gated on this.
    passed, reason = qa_gate(redactor, redacted_tmp)
    base["qa_passed"] = passed
    if not passed:
        # Keep the pre-redaction original untouched; discard the failed redaction.
        _safe_unlink(redacted_tmp)
        base.update(status="failed", original_deleted=False, reason=reason)
        return base

    # 3) QA passed → commit: redacted image replaces bucket image + mirror,
    #    pre-redaction originals deleted (mirror keeps only the redacted version).
    try:
        # 3a) bucket: redacted_tmp → bucket_abs (atomic replace = delete upload original)
        os.replace(str(redacted_tmp), str(bucket_abs))
        # 3b) mirror: overwrite the audit copy with the redacted version
        #     (deletes the pre-redaction mirror original; mirror chain stays redacted)
        mirror_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(bucket_abs), str(mirror_abs))
    except Exception as e:
        _safe_unlink(redacted_tmp)
        base.update(
            status="failed",
            original_deleted=False,
            reason=f"提交替换失败(原件保留): {type(e).__name__}: {e}",
        )
        return base

    base.update(
        status="done",
        redacted_path=bucket_rel,
        original_deleted=True,
        reason=None,
    )
    return base


def _safe_unlink(p: Path) -> None:
    try:
        if p.is_file():
            p.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def run_job(manifest_path: Path) -> int:
    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        print(f"ERROR: cannot read manifest {manifest_path}: {e}", file=sys.stderr)
        return 2

    patient_dir = Path(manifest["patient_dir"]).resolve()
    status_path = manifest_path.parent / STATUS_NAME
    prior = load_existing_status(status_path)
    files = manifest["files"]

    # venv gate — no PaddleOCR available → everything blocked, no redaction run.
    if not venv_available():
        reason = (
            f"PaddleOCR venv {VENV_PYTHON.parent.parent} 缺失。请先创建: "
            "python3 -m venv ~/.venvs/mtb-ocr && "
            "~/.venvs/mtb-ocr/bin/pip install paddleocr paddlepaddle，"
            "然后用 ~/.venvs/mtb-ocr/bin/python 重跑本脚本。"
        )
        entries = [
            {
                "id": f["id"],
                "status": "blocked",
                "redacted_path": None,
                "qa_passed": None,
                "original_deleted": None,
                "reason": reason,
            }
            for f in files
        ]
        write_status(status_path, patient_dir, entries)
        print(
            f"BLOCKED: {len(entries)} file(s) — PaddleOCR venv missing. "
            f"Status: {status_path}",
            file=sys.stderr,
        )
        return 1

    redactor, imp_err = _import_redactor()
    if redactor is None:
        reason = (
            f"redact_ocr 导入失败({imp_err})。请用 ~/.venvs/mtb-ocr/bin/python 运行本脚本，"
            "确保 paddleocr/paddlepaddle/Pillow 已装在该 venv。"
        )
        entries = [
            {
                "id": f["id"],
                "status": "blocked",
                "redacted_path": None,
                "qa_passed": None,
                "original_deleted": None,
                "reason": reason,
            }
            for f in files
        ]
        write_status(status_path, patient_dir, entries)
        print(f"BLOCKED: {len(entries)} file(s) — {reason}", file=sys.stderr)
        return 1

    # Per-file processing, idempotent: skip files already 'done'.
    entries: list[dict] = []
    for f in files:
        fid = f["id"]
        prev = prior.get(fid)
        if prev and prev.get("status") == "done":
            entries.append(prev)
            # flush incrementally so partial runs are recoverable
            write_status(status_path, patient_dir, entries + _remaining_pending(files, entries))
            continue

        entry = process_file(redactor, patient_dir, f)
        entries.append(entry)
        # write after each file so a worker can be killed/retried safely
        write_status(status_path, patient_dir, entries + _remaining_pending(files, entries))

    doc = write_status(status_path, patient_dir, entries)
    s = doc["summary"]
    print(
        f"redaction job: total={s['total']} done={s['done']} "
        f"failed={s['failed']} blocked={s['blocked']} → {status_path}"
    )
    return 0 if (s["failed"] == 0 and s["blocked"] == 0) else 1


def _remaining_pending(files: list[dict], done_entries: list[dict]) -> list[dict]:
    """Placeholder 'pending' entries for files not yet processed, so the status
    file always lists every manifest id (summary counters stay consistent)."""
    processed_ids = {e["id"] for e in done_entries}
    out = []
    for f in files:
        if f["id"] in processed_ids:
            continue
        out.append(
            {
                "id": f["id"],
                "status": "pending",
                "redacted_path": None,
                "qa_passed": None,
                "original_deleted": None,
                "reason": None,
            }
        )
    return out


def resolve_manifest_path(args) -> Path | None:
    if args.manifest:
        return Path(args.manifest).expanduser().resolve()
    if args.patient_dir:
        return (Path(args.patient_dir).expanduser().resolve() / MANIFEST_NAME)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-persist PaddleOCR redaction batch processor (段B).",
    )
    parser.add_argument(
        "patient_dir",
        nargs="?",
        help=f"Patient directory containing {MANIFEST_NAME}.",
    )
    parser.add_argument(
        "--manifest",
        help=f"Explicit path to {MANIFEST_NAME} (overrides patient_dir).",
    )
    args = parser.parse_args()

    manifest_path = resolve_manifest_path(args)
    if manifest_path is None:
        parser.error("provide a patient_dir or --manifest")
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    return run_job(manifest_path)


if __name__ == "__main__":
    sys.exit(main())
