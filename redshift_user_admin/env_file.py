from __future__ import annotations

import os
from pathlib import Path


def _parse_double_quoted(s: str) -> str:
    """Parse a double-quoted shell-style string (leading quote already stripped from flow)."""
    if not s.startswith('"'):
        return s
    i = 1
    out: list[str] = []
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            out.append(s[i + 1])
            i += 2
            continue
        if c == '"':
            return "".join(out)
        out.append(c)
        i += 1
    raise ValueError(f"Unterminated double-quoted value in env file: {s!r}")


def _parse_single_quoted(s: str) -> str:
    if not s.startswith("'"):
        return s
    i = 1
    out: list[str] = []
    n = len(s)
    while i < n:
        c = s[i]
        if c == "'" and i + 1 < n and s[i + 1] == "'":
            out.append("'")
            i += 2
            continue
        if c == "'":
            return "".join(out)
        out.append(c)
        i += 1
    raise ValueError(f"Unterminated single-quoted value in env file: {s!r}")


def _parse_env_value(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith('"'):
        return _parse_double_quoted(raw)
    if raw.startswith("'"):
        return _parse_single_quoted(raw)
    return raw


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=value lines from a file (optional ``export `` prefix, ``#`` comments)."""
    text = path.read_text()
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        result[key] = _parse_env_value(value)
    return result


def merged_environ(env_file: Path | None) -> dict[str, str]:
    """Process environment merged with optional env file (file keys override)."""
    base: dict[str, str] = dict(os.environ)
    if env_file is not None:
        base.update(parse_env_file(env_file))
    return base
