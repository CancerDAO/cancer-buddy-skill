"""Paths, JSON IO, front matter and bucket helpers shared by every command."""
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from . import VERSION

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = SCRIPTS_DIR.parent                      # skills/cancer-buddy
SKILLS_ROOT = SKILL_DIR.parent                      # skills/
REFERENCES = SKILL_DIR / "references"
ORGANIZE_PROMPTS = SKILLS_ROOT / "cancer-buddy-organize" / "prompts"

PATIENT_CODE_RE = re.compile(r"^PT-[0-9A-F]{10}$")


def patients_root() -> Path:
    for var in ("CANCER_BUDDY_PATIENTS_DIR", "VMTB_PATIENT_DATA_ROOT"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser()
    return Path.home() / "CancerDAO" / "patients"


def new_patient_code() -> str:
    return "PT-" + secrets.token_hex(5).upper()


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return _dt.date.today().isoformat()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# --- front matter -----------------------------------------------------------
# Sidecars start with a flat "key: value" block between two '---' lines.

def read_frontmatter(text: str):
    """Return (meta dict, body str). Missing block -> ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    meta = {}
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1:])
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            v = v.split(" #", 1)[0].strip()
            meta[k.strip()] = v.strip("\"'")
    return {}, text


def write_frontmatter(meta: dict, body: str) -> str:
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{head}\n---\n{body.lstrip(chr(10))}"


# --- buckets ----------------------------------------------------------------

def buckets(locale: str = "zh") -> dict:
    """Default drawers for a locale: {'domains': [(name, [sub,…])…], 'other': name, 'unrelated': name}."""
    data = load_json(REFERENCES / "buckets.json")
    key = "zh" if (locale or "zh").lower().startswith("zh") else "en"
    return {
        "domains": [(d[key], [s[key] for s in d["sub"]]) for d in data["domains"]],
        "other": data["other"][key],
        "unrelated": data["unrelated"][key],
    }


BUCKET_DIR_RE = re.compile(r"^(0[1-9]|1[0-5])_")
UNRELATED_DIR_RE = re.compile(r"^99_")


def is_clinical_bucket(name: str) -> bool:
    return bool(BUCKET_DIR_RE.match(name))


def iter_sidecars(patient_dir):
    """Every placed transcript (clinical buckets 01–15 and 99), sorted."""
    patient_dir = Path(patient_dir)
    out = []
    for child in sorted(patient_dir.iterdir()) if patient_dir.exists() else []:
        if child.is_dir() and (is_clinical_bucket(child.name) or UNRELATED_DIR_RE.match(child.name)):
            out.extend(sorted(p for p in child.rglob("*.md")))
    return out


def rel(patient_dir, path) -> str:
    return Path(path).resolve().relative_to(Path(patient_dir).resolve()).as_posix()


def profile_locale(patient_dir, default="zh") -> str:
    prof = load_json(Path(patient_dir) / "profile.json", {}) or {}
    return prof.get("locale") or default


__all__ = [n for n in dir() if not n.startswith("_")] + ["VERSION"]
