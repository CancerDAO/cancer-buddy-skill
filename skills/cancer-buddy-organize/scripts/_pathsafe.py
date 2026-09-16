#!/usr/bin/env python3
"""_pathsafe.py — the one place organize decides whether a string may become a path.

WHY IT EXISTS (fix spec A9)
    Several organize v3 scripts take identifiers straight from *model output* or from a
    CLI flag and then join them onto a filesystem path:

        raw/transcript/<source_id>/page-NNN.md
        raw/_provenance/<run_id>/...
        raw/_cache/transcripts/<sha>.<text_layer_sha>.<prompt_version>.<model_id>.md

    A `source_id` of `../../.ssh` or a `prompt_version` of `../../../etc/x` turns each of
    those into a write outside the patient directory. The model that produced the value is
    reading patient-uploaded pages, so the value is untrusted by construction.

    Two complementary defences, and BOTH are required:

      safe_component()  a WHITELIST on the string itself. Whitelists are used rather than
                        blacklists because the blacklist of "dangerous" path characters is
                        open-ended — NFKC-foldable fullwidth solidus (U+FF0F), the RTL
                        override (U+202E) that makes `gpj.exe` render as `exe.jpg`, zero
                        width joiners, NUL, bare `.`/`..`. Enumerating what is ALLOWED is
                        finite and auditable.

      contained()       a check on the RESULT, after os.path.realpath. This is what
                        catches what the whitelist cannot see: a symlink somewhere in the
                        middle of an otherwise blameless relative path.

    Neither one subsumes the other. A whitelist cannot see a symlink; a realpath check
    cannot stop `run_id = ".."` from silently retargeting a whole provenance directory to
    a sibling run. Callers are expected to apply both: validate every component, then
    assert containment of the joined path before writing.

NOT A SANITIZER
    safe_component REJECTS; it does not repair. A repaired identifier is a DIFFERENT
    identifier, and silently renaming `../../x` to `___x` would make the manifest disagree
    with the model output it claims to record. Callers record the rejection (`invalid`)
    and move on; they never write a page under a guessed-at name.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

__all__ = [
    "PathSafetyError",
    "SAFE_COMPONENT_RE",
    "safe_component",
    "is_safe_component",
    "safe_filename_token",
    "sanitize_component",
    "contained",
    "require_contained",
    "no_hardlink",
    "safe_relpath",
]

# CJK Unified Ideographs (一-鿿) are allowed because Chinese filenames are the norm in
# this archive; everything else is ASCII alphanumerics plus `_` and `-`. No dot: a
# component is never a suffixed filename here, and forbidding `.` removes `.`/`..` and
# every hidden-file trick in one rule.
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9一-鿿_-]{1,64}$")

# A FILENAME TOKEN is a component that legitimately contains dots — a `prompt_version`
# like `3.0`, or a `model_id` like `claude-opus-4.1`, both of which are joined into the
# cache filename `<sha>.<text_layer_sha>.<prompt_version>.<model_id>.md`. Dots are allowed
# inside, but the token may not BE `.` or `..`, may not start with a dot (no hidden
# files), may not contain `..` anywhere, and may not contain a separator.
#
# Deliberately a SEPARATE rule from safe_component: the no-dot rule is what makes `..`
# unrepresentable where a value becomes a whole DIRECTORY name (source_id, run_id), and
# one exception to it is all a traversal needs. Two rules, two blast radii.
SAFE_FILENAME_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9一-鿿_-][A-Za-z0-9一-鿿._-]{0,63}$"
)

# Explicitly named so the rejection message can say WHICH class tripped, rather than a
# generic "does not match". Each of these has been a real path-traversal or
# filename-spoofing primitive somewhere.
_ZERO_WIDTH = {"​", "‌", "‍", "⁠", "﻿", "­"}
_BIDI = {"‪", "‫", "‬", "‭", "‮",
         "⁦", "⁧", "⁨", "⁩"}
_FULLWIDTH_SEPARATORS = {"／", "＼", "⁄", "∕", "．"}


class PathSafetyError(ValueError):
    """Raised when an untrusted string may not be used as a path component."""


def _describe_reject(s: str) -> str:
    if s == "":
        return "empty"
    if s in (".", ".."):
        return f"the relative-path token {s!r}"
    if "/" in s or "\\" in s:
        return "contains a path separator"
    if any(ch in _FULLWIDTH_SEPARATORS for ch in s):
        return "contains a fullwidth/alternate separator that NFKC-folds to '/' or '.'"
    if any(ch in _ZERO_WIDTH for ch in s):
        return "contains a zero-width character"
    if any(ch in _BIDI for ch in s):
        return "contains a bidirectional-override character"
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") for ch in s):
        return "contains a control/format character"
    if len(s) > 64:
        return f"is {len(s)} characters long (max 64)"
    bad = sorted({ch for ch in s if not SAFE_COMPONENT_RE.match(ch)})
    return "contains disallowed character(s): " + ", ".join(repr(c) for c in bad[:8])


def is_safe_component(s: object) -> bool:
    """True when `s` may be used verbatim as ONE path component."""
    if not isinstance(s, str):
        return False
    if s in (".", ".."):
        return False
    # NFKC first: U+FF0F FULLWIDTH SOLIDUS folds to '/', and a filesystem (or any later
    # normalisation step) may do that fold for us. Validate what the string will BECOME.
    if unicodedata.normalize("NFKC", s) != s:
        return False
    if any(ch in _ZERO_WIDTH or ch in _BIDI for ch in s):
        return False
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") for ch in s):
        return False
    return bool(SAFE_COMPONENT_RE.match(s))


def safe_component(s: object, what: str = "value") -> str:
    """Return `s` unchanged if it is a legal path component, else raise PathSafetyError."""
    if not isinstance(s, str):
        raise PathSafetyError(f"{what} must be a string, got {type(s).__name__}")
    if not is_safe_component(s):
        raise PathSafetyError(
            f"{what} {s!r} is not a safe path component: {_describe_reject(s)}. "
            f"Allowed: 1-64 chars from [A-Za-z0-9一-鿿_-]"
        )
    return s


def safe_filename_token(s: object, what: str = "value") -> str:
    """Like safe_component, but dots are allowed INSIDE the token (never at the start)."""
    if not isinstance(s, str):
        raise PathSafetyError(f"{what} must be a string, got {type(s).__name__}")
    if s in (".", "..") or "/" in s or "\\" in s:
        raise PathSafetyError(f"{what} {s!r} is not a safe filename token: {_describe_reject(s)}")
    if unicodedata.normalize("NFKC", s) != s:
        raise PathSafetyError(f"{what} {s!r} changes under NFKC normalisation")
    if any(ch in _ZERO_WIDTH or ch in _BIDI for ch in s):
        raise PathSafetyError(f"{what} {s!r} contains a zero-width or bidi-override character")
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") for ch in s):
        raise PathSafetyError(f"{what} {s!r} contains a control/format character")
    if ".." in s:
        raise PathSafetyError(f"{what} {s!r} contains '..'")
    if not SAFE_FILENAME_TOKEN_RE.match(s):
        raise PathSafetyError(
            f"{what} {s!r} is not a safe filename token: {_describe_reject(s)}. "
            f"Allowed: 1-64 chars from [A-Za-z0-9\u4e00-\u9fff._-], not starting with '.'"
        )
    return s


def sanitize_component(s: object, fallback: str = "src", max_len: int = 40) -> str:
    """Coerce an arbitrary string into a legal component (for IDS WE MINT, not ones we read).

    This is only for identifiers this pipeline GENERATES from a filename stem, where a
    lossy fold is acceptable because the fold is combined with a content hash (A8) and the
    verbatim original name is preserved in raw/_FILENAME_MAPPING.md. Never use it to
    "repair" an identifier that arrived from a model: see the module docstring.
    """
    text = unicodedata.normalize("NFKC", str(s or ""))
    text = "".join(
        ch for ch in text
        if ch not in _ZERO_WIDTH and ch not in _BIDI
        and unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co", "Cn")
    )
    out = re.sub(r"[^A-Za-z0-9一-鿿_-]+", "_", text).strip("_")[:max_len]
    if not out or out in (".", ".."):
        return fallback
    return out


def contained(path: os.PathLike | str, root: os.PathLike | str) -> bool:
    """True when `path` really resolves inside `root`.

    os.path.realpath (not Path.resolve(strict=True)) so a not-yet-created output path is
    still checkable — the whole point is to verify BEFORE writing. Symlinks anywhere along
    either side are resolved, which is what makes this catch the case the whitelist can't.
    """
    try:
        real_path = os.path.realpath(str(path))
        real_root = os.path.realpath(str(root))
    except (OSError, ValueError):
        return False
    if real_path == real_root:
        return True
    try:
        rel = os.path.relpath(real_path, real_root)
    except ValueError:  # different drive on Windows
        return False
    return rel != ".." and not rel.startswith(".." + os.sep)


def require_contained(path: os.PathLike | str, root: os.PathLike | str,
                      what: str = "path") -> Path:
    """contained() as an assertion; returns the Path so it can be used inline."""
    if not contained(path, root):
        raise PathSafetyError(
            f"{what} {str(path)!r} resolves outside {str(root)!r} — refusing to write. "
            "Every product of this pipeline stays inside the patient directory"
        )
    return Path(path)


def no_hardlink(path: os.PathLike | str, what: str = "path") -> Path:
    """Refuse to write to an EXISTING file that has more than one name (fix spec B10).

    realpath() closes the symlink hole; it does not close this one. A hard link has no
    "target" to resolve — the second name IS the file — so `contained()` sees a perfectly
    ordinary path inside the patient directory and approves it, while the bytes written
    appear simultaneously at the attacker's name outside. Concretely: anything that can
    create `ocr/SRC/page-001.md` as a hard link to a file elsewhere on the volume turns
    every subsequent masked-copy write into a write to that elsewhere.

    st_nlink is the only signal available before opening, and it is the RIGHT one: every
    file this pipeline produces is created by this pipeline, so a link count above 1 on an
    output path is never a legitimate state of the archive — it is always something else
    reaching in. Missing files pass (nothing to alias yet); directories are not checked
    here (a directory's link count is its subdirectory count).

    TOCTOU is not closed by this, and cannot be from user space; the check narrows the
    window from "always" to "between stat and write", and it is paired with, not a
    substitute for, containment.
    """
    p = Path(path)
    try:
        st = os.stat(p, follow_symlinks=False)
    except FileNotFoundError:
        return p
    except OSError as exc:
        raise PathSafetyError(f"{what} {str(p)!r} could not be stat'ed: {exc}") from exc
    if not os.path.isdir(p) and st.st_nlink > 1:
        raise PathSafetyError(
            f"{what} {str(p)!r} has {st.st_nlink} hard links — refusing to write. A second "
            "name for this file means the bytes also land wherever that name lives, which "
            "containment cannot see: a hard link has no target to resolve"
        )
    return p


def safe_relpath(rel: str, root: os.PathLike | str, what: str = "path") -> Path:
    """Validate a RELATIVE, multi-component path (e.g. a --source target under raw/)."""
    if not isinstance(rel, str) or not rel.strip():
        raise PathSafetyError(f"{what} must be a non-empty relative path")
    p = Path(rel)
    if p.is_absolute():
        raise PathSafetyError(f"{what} {rel!r} must be relative, not absolute")
    for part in p.parts:
        if part in (".", ".."):
            raise PathSafetyError(f"{what} {rel!r} contains the relative token {part!r}")
    joined = Path(root) / p
    require_contained(joined, root, what)
    # Every product path in organize is built through this function, so the hard-link
    # refusal belongs here rather than at each of the ~20 call sites: a check that has to
    # be remembered is a check that gets forgotten on the twenty-first.
    no_hardlink(joined, what)
    return joined
