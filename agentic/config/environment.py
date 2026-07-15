"""Load the repository-wide backend environment without overriding the process."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


BACKEND_ENV_PATH = Path(__file__).resolve().parents[2] / ".env.backend"


def load_backend_environment(path: str | Path | None = None) -> Path:
    """Load the single backend env file; explicit process variables take precedence."""

    selected = Path(path) if path is not None else BACKEND_ENV_PATH
    load_dotenv(dotenv_path=selected, override=False)
    return selected
