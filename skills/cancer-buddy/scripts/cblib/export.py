"""Purpose-limited export: copy selected derived files, never raw/, with a share manifest."""
import datetime as _dt
import shutil
from pathlib import Path

from .common import load_json, write_json, now_iso, sha256_file
from .check import load_identity, mask_identity

FORBIDDEN_TOP = {"raw", ".work", "library", "share_log.json"}


def export(patient_dir, out, includes, recipient, purpose, expires_at, authorization_ref="") -> dict:
    patient_dir = Path(patient_dir).resolve()
    out = Path(out).expanduser().resolve()
    if not (recipient and purpose and expires_at):
        raise SystemExit("导出需要写明接收方（--recipient）、目的（--purpose）和到期时间（--expires-at）")
    try:
        exp = _dt.datetime.fromisoformat(expires_at)
    except ValueError:
        raise SystemExit("--expires-at 需要 ISO 日期，例如 2026-12-31")
    if exp.date() <= _dt.date.today():
        raise SystemExit("到期时间必须晚于今天")
    if not includes:
        raise SystemExit("至少选择一个要导出的文件（--include）")

    files = []
    for inc in includes:
        src = (patient_dir / inc).resolve()
        if patient_dir not in src.parents:
            raise SystemExit(f"不在患者目录内：{inc}")
        top = src.relative_to(patient_dir).parts[0]
        if top in FORBIDDEN_TOP or top.startswith("99_"):
            raise SystemExit(f"不能导出 {top}/（原件和工作文件不对外）：{inc}")
        if src.is_symlink() or not src.exists():
            raise SystemExit(f"文件不存在或是链接：{inc}")
        members = [p for p in src.rglob("*") if p.is_file() and not p.is_symlink()] if src.is_dir() else [src]
        for m in members:
            if m.stat().st_nlink > 1:
                raise SystemExit(f"拒绝导出硬链接文件：{m.relative_to(patient_dir)}")
            files.append(m)

    out.mkdir(parents=True, exist_ok=True)
    listed = []
    for m in files:
        r = m.relative_to(patient_dir)
        dest = out / r
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(m, dest)
        listed.append(r.as_posix())

    # The copies get the same identity masking as the archive itself.
    fake = out / "raw" / "_identity"
    fake.mkdir(parents=True, exist_ok=True)
    write_json(fake / "export.json", {k: sorted(v) for k, v in load_identity(patient_dir).items()})
    masked = mask_identity(out)
    shutil.rmtree(out / "raw")

    manifest = {
        "patient_code": patient_dir.name, "created_at": now_iso(), "recipient": recipient,
        "purpose": purpose, "expires_at": expires_at, "authorization_ref": authorization_ref,
        "files": [{"path": r, "sha256": sha256_file(out / r)} for r in listed],
        "masked_identity_strings": masked,
        "note": "已遮蔽已知的姓名、证件号、电话等，但病历内容本身仍可能被认出是谁，不等于匿名。",
    }
    write_json(out / "_SHARE_MANIFEST.json", manifest)
    log_path = patient_dir / "share_log.json"
    log = load_json(log_path) or {"shares": []}
    log["shares"].append({k: manifest[k] for k in ("created_at", "recipient", "purpose", "expires_at", "authorization_ref")}
                         | {"out": str(out), "files": listed})
    write_json(log_path, log)
    return {"out": str(out), "files": listed, "masked": masked}
