#!/usr/bin/env python3
"""build_inventory_index.py — Step 4a 确定性产物（零 LLM，lite 绑定）。

从 phase0_manifest.json + 桶内 sidecar 落位确定性生成：
- source_inventory.json（source_inventory_v2，全字段可推导，不花模型调用）
- INDEX.md 骨架（桶 → 文件清单；叙事注释留给 Step 4c 追加，本脚本只写结构）
- `--finalize-log --run-id ...` 时才给 update_log.json 追加一条待最终门验证的 run 记录

用法:
  build_inventory_index.py <patient_dir> [--run-mode full|incremental]
  build_inventory_index.py <patient_dir> --finalize-log [--run-mode full|incremental]

普通调用只写 inventory + INDEX。update_log 等 Phase 4 全部产物齐后，由编排层
显式调用 --finalize-log；随后它本身也进入最终 PII 与 strict validator 的扫描范围。
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from high_risk_review import (
    find_review_record,
    inventory_review_status,
    load_review_records,
)

BUCKET_RE = re.compile(r"^\d{2}_")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def sidecar_locations(patient_dir):
    """source_id → 桶内相对路径（含待归类）。"""
    out = {}
    for bucket in sorted(p for p in patient_dir.iterdir() if p.is_dir() and BUCKET_RE.match(p.name)):
        for md in sorted(bucket.rglob("*.md")):
            text = ""
            try:
                text = md.read_text(encoding="utf-8")
            except Exception:
                continue
            m = re.search(r"^source_id:\s*(\S+)", text, re.M)
            if m:
                out[m.group(1)] = md.relative_to(patient_dir).as_posix()
    return out


def adapter_for(source):
    """Map Phase-0's concrete preparation to the source-inventory enum."""
    if source.get("status") != "ok":
        return "unsupported_stub"
    ext = Path(str(source.get("raw_path") or "")).suffix.lower()
    if ext == ".pdf":
        return "pdf_pages"
    if ext in {".heic", ".heif"}:
        return "temp_raster"
    return "none"


def missing_sidecars(manifest, located):
    return [
        src.get("source_id")
        for src in manifest.get("sources", [])
        if src.get("status") == "ok" and src.get("source_id") not in located
    ]


def finalize_update_log(patient_dir, manifest, run_mode, run_id, missing):
    if missing:
        return False, "readable sources are missing sidecars"
    for required in ("source_inventory.json", "INDEX.md"):
        if not (patient_dir / required).is_file():
            return False, f"{required} missing; run the normal build first"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state = read_json(patient_dir / ".organize_run.json")
    if not isinstance(state, dict) or state.get("status") != "active":
        return False, "active .organize_run.json missing"
    if state.get("run_id") != run_id:
        return False, f"active run is pinned to {state.get('run_id')}"
    log = read_json(patient_dir / "update_log.json") or {
        "schema": "update_log_v1", "runs": []
    }
    prior = [row for row in log.get("runs", [])
             if isinstance(row, dict) and row.get("run_id") == run_id]
    if prior:
        # Refresh the deterministic task's mtime after downstream regeneration
        # without duplicating the run event. The Phase-4 planner uses this to
        # distinguish a current finalization from a stale pre-regeneration log.
        (patient_dir / "update_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return True, None
    log.setdefault("runs", []).append({
        "run_id": run_id,
        "run_mode": run_mode,
        "at": now,
        "status": "ready_for_final_validation",
        "sources": manifest.get("total"),
        "blocked": manifest.get("blocked", 0),
        "missing_sidecars": [],
    })
    (patient_dir / "update_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patient_dir")
    ap.add_argument("--run-mode", choices=("full", "incremental"), default="full")
    ap.add_argument("--finalize-log", action="store_true",
                    help="append update_log after Phase 4, before final PII/strict gates")
    ap.add_argument("--run-id", help="pinned organize run (required with --finalize-log)")
    args = ap.parse_args()
    patient_dir = Path(args.patient_dir)
    manifest = read_json(patient_dir / "phase0_manifest.json")
    if not manifest:
        print(json.dumps({"ok": False, "reason": "phase0_manifest.json missing"}))
        return 2
    located = sidecar_locations(patient_dir)
    missing = missing_sidecars(manifest, located)
    if args.finalize_log:
        if not args.run_id:
            print(json.dumps({"ok": False, "reason": "--run-id is required with --finalize-log"}))
            return 2
        ok, reason = finalize_update_log(
            patient_dir, manifest, args.run_mode, args.run_id, missing)
        print(json.dumps({"ok": ok, "finalized_log": ok, "reason": reason,
                          "missing_sidecars": missing}, ensure_ascii=False))
        return 0 if ok else 1

    review = load_review_records(patient_dir / "high_risk_review.json")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    rows = []
    for src in manifest.get("sources", []):
        sid = src["source_id"]
        file_id = str(src.get("file_id") or sid)  # lite v1 manifest is 1:1
        sidecar = located.get(sid)
        review_record = find_review_record(review, file_id, sid, sidecar)
        blocked = src.get("status") != "ok"
        provenance = ({
            "engine": "phase0_prepare",
            "version": None,
            "raw_output_ref": None,
            "llm_role": "none",
        } if blocked else {
            "engine": "kimi-lite phase-1 (model_vision, verbatim card)",
            "version": None,
            "raw_output_ref": None,
            "llm_role": "transcription",
        })
        rows.append({
            "file_id": file_id,
            "source_id": sid,
            # Portable, de-identified handle. The protected raw location remains
            # available separately in raw_path.
            "original_path": sid,
            "raw_path": src.get("raw_path"),
            "page_range": None,
            "bucket_path": Path(sidecar).parent.as_posix() if sidecar else None,
            "sidecar_path": sidecar,
            "modality": "image" if src.get("raster_paths") else "binary_other",
            "read_mode": "stub_unreadable" if blocked else "model_vision_assist",
            "extractor_provenance": provenance,
            # Some individually verified values do not prove complete reread.
            "high_risk_review_status": ("needs_human_review" if blocked
                                        else inventory_review_status(review_record)),
            "adapter": adapter_for(src),
            "persist": True,
        })
    inventory = {"schema": "source_inventory_v2", "patient_dir": patient_dir.name,
                 "generated_at": now, "files": rows}
    (patient_dir / "source_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # INDEX.md 骨架：桶结构 + 文件清单（Step 4c 审计后可在文末追加叙事注释）
    lines = [f"# patient_code: {patient_dir.name}", "", "# INDEX", "",
             f"- 生成时间: {now}", f"- 来源总数: {manifest.get('total')}"
             f"（blocked: {manifest.get('blocked', 0)}）", ""]
    by_bucket = {}
    for sid, rel in sorted(located.items(), key=lambda kv: kv[1]):
        by_bucket.setdefault(rel.split("/")[0], []).append(rel)
    for bucket, rels in sorted(by_bucket.items()):
        lines.append(f"## {bucket}")
        lines += [f"- {rel}" for rel in rels] + [""]
    (patient_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"ok": not missing, "rows": len(rows), "missing_sidecars": missing},
                     ensure_ascii=False))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
