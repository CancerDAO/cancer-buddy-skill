#!/usr/bin/env python3
"""Validate Cancer Buddy's installable Codex skill packages.

The validator intentionally uses only Python's standard library so it can run
in a clean checkout and in CI without installing a YAML dependency.  It checks
the small, well-defined YAML subset used by this repository and verifies local
Markdown links as they will exist after the ``skills`` CLI copies the skill
directories.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)")
INTERFACE_KEY_RE = re.compile(r'^  ([a-z_]+):\s*("(?:[^"\\]|\\.)*")\s*$')
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

FRONTMATTER_KEYS = {"name", "description"}
INTERFACE_KEYS = {
    "display_name",
    "short_description",
    "icon_small",
    "icon_large",
    "brand_color",
    "default_prompt",
}


class ValidationError(Exception):
    """A user-facing validation failure tied to one repository path."""


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _frontmatter_value(lines: list[str], key: str) -> str:
    prefix = f"{key}:"
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        raw = line[len(prefix) :].strip()
        if re.fullmatch(r"[>|][+-]?", raw):
            block: list[str] = []
            for block_line in lines[index + 1 :]:
                if TOP_LEVEL_KEY_RE.match(block_line):
                    break
                if block_line.strip():
                    if not block_line.startswith((" ", "\t")):
                        raise ValidationError(
                            f"{key!r} block lines must be indented"
                        )
                    block.append(block_line.strip())
            return " ".join(block)
        if not raw:
            return ""
        if raw.startswith('"'):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"invalid quoted {key}: {exc.msg}") from exc
            if not isinstance(value, str):
                raise ValidationError(f"{key!r} must be a string")
            return value
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1].replace("''", "'")
        return raw
    raise ValidationError(f"missing {key!r}")


def validate_skill_md(skill_dir: Path, repo_root: Path) -> str:
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        raise ValidationError(f"{_relative(path, repo_root)} is missing")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValidationError(
            f"{_relative(path, repo_root)} must start with YAML frontmatter"
        )
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError(
            f"{_relative(path, repo_root)} has no closing frontmatter delimiter"
        ) from exc

    frontmatter = lines[1:end]
    keys = [match.group(1) for line in frontmatter if (match := TOP_LEVEL_KEY_RE.match(line))]
    unknown = sorted(set(keys) - FRONTMATTER_KEYS)
    duplicate = sorted(key for key in FRONTMATTER_KEYS if keys.count(key) > 1)
    missing = sorted(FRONTMATTER_KEYS - set(keys))
    if unknown or duplicate or missing:
        detail = []
        if unknown:
            detail.append(f"unsupported keys: {', '.join(unknown)}")
        if duplicate:
            detail.append(f"duplicate keys: {', '.join(duplicate)}")
        if missing:
            detail.append(f"missing keys: {', '.join(missing)}")
        raise ValidationError(
            f"{_relative(path, repo_root)} frontmatter must contain only name and "
            f"description ({'; '.join(detail)})"
        )

    try:
        name = _frontmatter_value(frontmatter, "name")
        description = _frontmatter_value(frontmatter, "description")
    except ValidationError as exc:
        raise ValidationError(f"{_relative(path, repo_root)}: {exc}") from exc

    if not NAME_RE.fullmatch(name) or len(name) > 64:
        raise ValidationError(
            f"{_relative(path, repo_root)} has invalid lower-kebab-case name {name!r}"
        )
    if name != skill_dir.name:
        raise ValidationError(
            f"{_relative(path, repo_root)} name {name!r} must match directory "
            f"{skill_dir.name!r}"
        )
    if not description.strip():
        raise ValidationError(f"{_relative(path, repo_root)} has an empty description")
    if len(description) > 1024:
        raise ValidationError(
            f"{_relative(path, repo_root)} description exceeds 1024 characters"
        )
    if "<" in description or ">" in description:
        raise ValidationError(
            f"{_relative(path, repo_root)} description must not contain angle brackets"
        )
    if len(lines) > 500:
        raise ValidationError(
            f"{_relative(path, repo_root)} has {len(lines)} lines; keep SKILL.md at "
            "or below 500 lines and move details into references/"
        )
    return name


def validate_openai_yaml(skill_dir: Path, skill_name: str, repo_root: Path) -> None:
    path = skill_dir / "agents" / "openai.yaml"
    if not path.is_file():
        raise ValidationError(f"{_relative(path, repo_root)} is missing")

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "interface:":
        raise ValidationError(
            f"{_relative(path, repo_root)} must start with an interface mapping"
        )

    values: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith("  "):
            # Other documented top-level sections may follow interface.
            break
        match = INTERFACE_KEY_RE.fullmatch(line)
        if not match:
            raise ValidationError(
                f"{_relative(path, repo_root)} interface strings must use quoted "
                f"generator-compatible YAML: {line!r}"
            )
        key, encoded = match.groups()
        if key not in INTERFACE_KEYS:
            raise ValidationError(
                f"{_relative(path, repo_root)} has unsupported interface key {key!r}"
            )
        if key in values:
            raise ValidationError(
                f"{_relative(path, repo_root)} repeats interface key {key!r}"
            )
        values[key] = json.loads(encoded)

    required = {"display_name", "short_description", "default_prompt"}
    missing = sorted(required - values.keys())
    if missing:
        raise ValidationError(
            f"{_relative(path, repo_root)} is missing interface fields: "
            f"{', '.join(missing)}"
        )
    if not values["display_name"].strip():
        raise ValidationError(f"{_relative(path, repo_root)} display_name is empty")
    short = values["short_description"]
    if not 25 <= len(short) <= 64:
        raise ValidationError(
            f"{_relative(path, repo_root)} short_description must be 25-64 "
            f"characters (got {len(short)})"
        )
    skill_token = f"${skill_name}"
    if skill_token not in values["default_prompt"]:
        raise ValidationError(
            f"{_relative(path, repo_root)} default_prompt must explicitly contain "
            f"{skill_token}"
        )
    if not values["default_prompt"].strip():
        raise ValidationError(f"{_relative(path, repo_root)} default_prompt is empty")

    for icon_key in ("icon_small", "icon_large"):
        if icon_key not in values:
            continue
        icon = (skill_dir / values[icon_key]).resolve()
        if not icon.is_file():
            raise ValidationError(
                f"{_relative(path, repo_root)} {icon_key} target does not exist: "
                f"{values[icon_key]}"
            )


def _markdown_target(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        return raw[1 : raw.index(">")]
    # A whitespace-separated suffix is an optional Markdown link title.
    return raw.split(maxsplit=1)[0]


def validate_markdown_links(skill_dir: Path, repo_root: Path) -> None:
    resolved_root = repo_root.resolve()
    for path in sorted(skill_dir.rglob("*.md")):
        in_fence = False
        fence = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
            if fence_match:
                marker = fence_match.group(1)[0]
                if not in_fence:
                    in_fence = True
                    fence = marker
                elif marker == fence:
                    in_fence = False
                    fence = ""
                continue
            if in_fence:
                # Output templates contain links to artifacts that will exist in
                # the generated patient directory, not in the source repository.
                continue
            for match in MARKDOWN_LINK_RE.finditer(line):
                target = _markdown_target(match.group(1))
                if not target or target.startswith("#") or SCHEME_RE.match(target):
                    continue
                if any(marker in target for marker in ("{{", "}}", "${")):
                    continue
                target = unquote(target.split("#", 1)[0].split("?", 1)[0])
                if not target:
                    continue
                if target.startswith("/"):
                    raise ValidationError(
                        f"{_relative(path, repo_root)} has non-portable absolute link: "
                        f"{match.group(1)}"
                    )
                destination = (path.parent / target).resolve()
                try:
                    destination.relative_to(resolved_root)
                except ValueError as exc:
                    raise ValidationError(
                        f"{_relative(path, repo_root)} link escapes repository: {target}"
                    ) from exc
                if not destination.exists():
                    raise ValidationError(
                        f"{_relative(path, repo_root)} has broken local link: {target}"
                    )


def validate_repository(repo_root: Path) -> list[str]:
    skills_root = repo_root / "skills"
    if not skills_root.is_dir():
        raise ValidationError(f"{_relative(skills_root, repo_root)} is missing")
    skill_dirs = sorted(
        path for path in skills_root.iterdir() if path.is_dir() and not path.name.startswith(".")
    )
    if not skill_dirs:
        raise ValidationError("skills/ contains no installable skill directories")

    names: list[str] = []
    for skill_dir in skill_dirs:
        name = validate_skill_md(skill_dir, repo_root)
        validate_openai_yaml(skill_dir, name, repo_root)
        validate_markdown_links(skill_dir, repo_root)
        names.append(name)
    if len(names) != len(set(names)):
        raise ValidationError("skill names must be unique")
    return names


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate installable Codex skills and UI metadata."
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to this script's parent repository)",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    try:
        names = validate_repository(repo_root)
    except (OSError, UnicodeError, ValidationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"PASS: validated {len(names)} Codex skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
