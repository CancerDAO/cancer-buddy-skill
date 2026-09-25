"""_gate_second_read.py — the second-read gate of validate_structured_outputs.py (phase1 §4 G, §5).

Kept in its own module so the validator only imports and registers it. For every sidecar written under
the current contract that carries a `## 高风险字段复读` block written by scripts/second_read_align.py (and
for every pixel-page sidecar — READ_MODE model_vision_primary — which must carry one), it runs
second_read_align.check():

  1. the table rows cover every high-risk span _high_risk_spans.py derives from the body (plus the
     worker's declared spans, which can only add);
  2. every row's 是 / 否 / 无信号 recomputes from the stored engine output;
  3. agree and no-signal spans carry no [OCR_UNCERTAIN] token; conflict / declared spans carry one, right
     after the span's literal;
  4. the second-channel readings (table and `## 不确定字段`) are the engine's own strings (masking aside);
  5. body_sha256 equals the token-free body, and the body is the one the engine was run against
     (only PII masking may differ) — the transcription was not edited towards the engine.

A copy without raw/ (an export, a readonly audit of a shared archive) cannot recompute: only the body
hash is checked and the rest is one WARN. A legacy archive gets WARNs only.
"""
from __future__ import annotations

from pathlib import Path


def table_of(text: str) -> dict | None:
    """The parsed `## 高风险字段复读` block of a sidecar ({engine, body_sha256, record, rows[]}) or None when
    the sidecar has no script-written block (no `engine:` line)."""
    import second_read_align as sra
    sec = sra.parse_section(sra.section_block(sra.split_sidecar(text)["sections"], "高风险字段复读"))
    return sec if "engine" in sec else None


def signal_rows(sec: dict | None) -> tuple[int, int]:
    """(rows the engine read — 是 / 否, rows with no signal — 无信号)."""
    if not sec:
        return 0, 0
    states = [r.get("state") for r in sec.get("rows") or []]
    return sum(s in ("是", "否") for s in states), sum(s == "无信号" for s in states)


def gate_second_read(patient_dir: Path, errors: list, warnings: list | None = None,
                     generation: str | None = None) -> None:
    import second_read_align as sra
    import validate_structured_outputs as vso
    current = vso._generation(patient_dir, generation)
    if not vso._bucket_sidecars(patient_dir):
        return
    scoped = vso.sidecar_contract_scope(patient_dir)[0] if current else vso._bucket_sidecars(patient_dir)
    no_raw = not (patient_dir / "raw").is_dir()
    unverified = 0
    for sc in scoped:
        errs, warns = sra.check(sc, patient_dir)
        if no_raw and warns:
            unverified += 1
        for e in errs:
            msg = f"second_read: {e}"
            if current:
                errors.append(msg)
            elif warnings is not None:
                warnings.append("legacy archive: " + msg)
        if warnings is not None and not no_raw:
            warnings.extend(f"second_read: {w}" for w in warns)
    if unverified and warnings is not None:
        warnings.append(f"second_read: {unverified} sidecar(s) checked by body_sha256 only — this copy has no raw/ "
                        "(the engine outputs and second-read records live there)")
