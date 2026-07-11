"""Dependency-free loading for Nafi's single project-level ``.env`` file."""

from __future__ import annotations

import os
import re
from pathlib import Path


_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvFileError(ValueError):
    """Raised when an environment file is present but malformed."""


def load_env_file(path: str | Path, *, override: bool = False) -> tuple[str, ...]:
    """Load a dotenv file without overwriting exported shell variables.

    The parser deliberately supports the small, predictable dotenv subset used
    by this project: blank lines, comments, optional ``export``, quoted values,
    and plain ``KEY=value`` pairs.  Invalid keys fail with a useful line number
    instead of being silently ignored.
    """

    env_path = Path(path)
    if not env_path.exists():
        return ()

    loaded: list[str] = []
    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvFileError(f"{env_path}:{line_number}: expected KEY=value")
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY.fullmatch(key):
            raise EnvFileError(f"{env_path}:{line_number}: invalid environment key {key!r}")
        value = _clean_value(value.strip(), env_path=env_path, line_number=line_number)
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return tuple(loaded)


def load_project_env(project_root: str | Path | None = None) -> Path:
    """Load the root Nafi env file and return the path that was considered.

    ``NAFI_ENV_FILE`` can point to another file for deployment environments.
    Shell variables always take precedence over file values.
    """

    configured_path = os.getenv("NAFI_ENV_FILE", "").strip()
    if configured_path:
        env_path = Path(configured_path).expanduser()
        if not env_path.is_absolute() and project_root is not None:
            env_path = Path(project_root) / env_path
        if not env_path.exists():
            raise EnvFileError(f"NAFI_ENV_FILE does not exist: {env_path}")
    else:
        root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[4]
        env_path = root / ".env"
    load_env_file(env_path)
    return env_path


def _clean_value(value: str, *, env_path: Path, line_number: int) -> str:
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        closing_index = _closing_quote_index(value, quote)
        if closing_index is None:
            raise EnvFileError(f"{env_path}:{line_number}: unterminated quoted value")
        remainder = value[closing_index + 1 :].strip()
        if remainder and not remainder.startswith("#"):
            raise EnvFileError(f"{env_path}:{line_number}: unexpected text after quoted value")
        return value[1:closing_index]
    comment_index = value.find(" #")
    if comment_index >= 0:
        value = value[:comment_index]
    return value.rstrip()


def _closing_quote_index(value: str, quote: str) -> int | None:
    for index in range(1, len(value)):
        if value[index] == quote and value[index - 1] != "\\":
            return index
    return None
