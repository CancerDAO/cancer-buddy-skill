#!/usr/bin/env python3
"""build_inventory_index.py — Step 4a 确定性产物（零 LLM，lite 绑定）。

从 phase0_manifest.json + 桶内 sidecar 落位确定性生成：
- source_inventory.json（source_inventory_v2，全字段可推导，不花模型调用）
- INDEX.md 骨架（桶 → 文件清单；叙事注释留给 Step 4c 追加，本脚本只写结构）
- update_log.json 追加一条 run 记录

用法: build_inventory_index.py <patient_dir> [--run-mode full|incremental]
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patient_dir")
    ap.add_argument("--run-mode", default="full")
    args = ap.parse_args()
    patient_dir = Path(args.patient_dir)
    manifest = read_json(patient_dir / "phase0_manifest.json")
    if not manifest:
        print(json.dumps({"ok": False, "reason": "phase0_manifest.json missing"}))
        return 2
    located = sidecar_locations(patient_dir)
    review = (read_json(patient_dir / "high_risk_review.json") or {}).get("values", {})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    rows, missing = [], []
    for src in manifest.get("sources", []):
        sid = src["source_id"]
        sidecar = located.get(sid)
        if sidecar is None and src.get("status") == "ok":
            missing.append(sid)
        rows.append({
            "file_id": sid,
            "source_id": sid,
            "original_path": src.get("raw_path"),
            "raw_path": src.get("raw_path"),
            "page_range": None,
            "bucket_path": sidecar,
            "sidecar_path": sidecar,
            "modality": "image" if src.get("raster_paths") else "binary_other",
            "read_mode": "model_vision" if src.get("status") == "ok" else "blocked",
            "extractor_provenance": {
                "engine": "kimi-lite phase-1 (model_vision, verbatim card)",
                "version": None, "raw_output_ref": None, "llm_role": "transcription",
            },
            # 逐值核验状态在 high_risk_review.json；行级只标"该源是否有已核验值"
            "high_risk_review_status": ("second_read_partial"
                                        if sidecar and review.get(sidecar) else "needs_human_review"),
            "adapter": "phase0_prepare",
            "persist": True,
        })
    inventory = {"schema": "source_inventory_v2", "patient_dir": patient_dir.name,
                 "generated_at": now, "files": rows}
    (patient_dir / "source_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # INDEX.md 骨架：桶结构 + 文件清单（Step 4c 审计后可在文末追加叙事注释）
    lines = ["# INDEX", "", f"- 生成时间: {now}", f"- 来源总数: {manifest.get('total')}"
             f"（blocked: {manifest.get('blocked', 0)}）", ""]
    by_bucket = {}
    for sid, rel in sorted(located.items(), key=lambda kv: kv[1]):
        by_bucket.setdefault(rel.split("/")[0], []).append(rel)
    for bucket, rels in sorted(by_bucket.items()):
        lines.append(f"## {bucket}")
        lines += [f"- {rel}" for rel in rels] + [""]
    (patient_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

    log = read_json(patient_dir / "update_log.json") or {"schema": "update_log_v1", "runs": []}
    log.setdefault("runs", []).append({"run_mode": args.run_mode, "at": now,
                                       "sources": manifest.get("total"),
                                       "blocked": manifest.get("blocked", 0),
                                       "missing_sidecars": missing})
    (patient_dir / "update_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(json.dumps({"ok": not missing, "rows": len(rows), "missing_sidecars": missing},
                     ensure_ascii=False))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
