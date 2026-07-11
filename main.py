"""Launch the complete Nafi demo from one root ``.env`` file."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
INTERACTION_SRC = ROOT / "user_interaction" / "src"
PYTHON = ROOT / "user_interaction" / ".venv" / "bin" / "python"
PYTHON_LOCK = ROOT / "requirements.lock"
WEB_UI = ROOT / "web_ui"
if str(INTERACTION_SRC) not in sys.path:
    sys.path.insert(0, str(INTERACTION_SRC))

from user_interaction_layer.config.env import EnvFileError, load_project_env  # noqa: E402
from user_interaction_layer.config.settings import (  # noqa: E402
    ConfigurationError,
    InteractionSettings,
)


class StartupError(RuntimeError):
    """Raised when the local stack cannot become ready."""


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    command: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    health_url: str


@dataclass(frozen=True)
class StackSettings:
    interaction: InteractionSettings
    agentic_host: str
    agentic_port: int
    web_host: str
    web_port: int
    startup_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "StackSettings":
        settings = cls(
            interaction=InteractionSettings.from_env(),
            agentic_host=os.getenv("AGENTIC_HOST", "127.0.0.1").strip(),
            agentic_port=_env_int("AGENTIC_PORT", 8090),
            web_host=os.getenv("WEB_UI_HOST", "127.0.0.1").strip(),
            web_port=_env_int("WEB_UI_PORT", 3000),
            startup_timeout_seconds=_env_float("NAFI_STARTUP_TIMEOUT_SECONDS", 60.0),
        )
        errors: list[str] = []
        for name, host in (
            ("AGENTIC_HOST", settings.agentic_host),
            ("WEB_UI_HOST", settings.web_host),
        ):
            if not host:
                errors.append(f"{name} cannot be empty")
        for name, port in (
            ("AGENTIC_PORT", settings.agentic_port),
            ("WEB_UI_PORT", settings.web_port),
        ):
            if not 1 <= port <= 65_535:
                errors.append(f"{name} must be between 1 and 65535")
        if settings.startup_timeout_seconds < 5 or settings.startup_timeout_seconds > 300:
            errors.append("NAFI_STARTUP_TIMEOUT_SECONDS must be between 5 and 300")
        if errors:
            raise ConfigurationError("Invalid Nafi stack configuration:\n- " + "\n- ".join(errors))
        return settings


def _environment(**values: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(values)
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def _service_specs(settings: StackSettings, python: str) -> tuple[ServiceSpec, ...]:
    interaction_host = settings.interaction.runtime.host
    interaction_port = settings.interaction.runtime.port
    agentic_base_url = f"http://{_connect_host(settings.agentic_host)}:{settings.agentic_port}"
    interaction_base_url = f"http://{_connect_host(interaction_host)}:{interaction_port}"
    # vinext advertises and binds its local dev server on localhost (often ::1)
    # even when a concrete host flag is provided, so readiness follows that
    # canonical URL while backend services retain explicit IPv4 bindings.
    web_base_url = f"http://localhost:{settings.web_port}"
    shared_secret = (
        os.getenv("AGENTIC_NOTIFICATION_SECRET", "").strip()
        or os.getenv("NAFI_LOCAL_CALLBACK_SECRET", "").strip()
        or secrets.token_urlsafe(32)
    )

    return (
        ServiceSpec(
            name="agentic",
            command=(python, str(ROOT / "agentic" / "run_server.py")),
            cwd=ROOT,
            environment=_environment(
                PYTHONPATH=str(ROOT / "agentic" / "src"),
                AGENTIC_HOST=settings.agentic_host,
                AGENTIC_PORT=str(settings.agentic_port),
                AGENTIC_BACKEND=os.getenv("AGENTIC_BACKEND", "mock").strip() or "mock",
                AGENTIC_NOTIFY_URL=(
                    f"{interaction_base_url}/interaction/agentic-notification"
                ),
                AGENTIC_NOTIFY_SECRET=shared_secret,
            ),
            health_url=f"{agentic_base_url}/health",
        ),
        ServiceSpec(
            name="interaction",
            command=(python, str(ROOT / "user_interaction" / "run_server.py")),
            cwd=ROOT,
            environment=_environment(
                PYTHONPATH=str(INTERACTION_SRC),
                AGENTIC_BASE_URL=agentic_base_url,
                AGENTIC_REQUEST_PATH=os.getenv("AGENTIC_REQUEST_PATH", "/agentic/request"),
                USER_INTERACTION_HOST=interaction_host,
                USER_INTERACTION_PORT=str(interaction_port),
                USER_INTERACTION_USE_MOCK_AGENTIC="false",
                SECURITY_GUARD_PROVIDER=os.getenv(
                    "SECURITY_GUARD_PROVIDER",
                    "deterministic",
                ),
                VOICE_AUDIO_PROVIDER=os.getenv("VOICE_AUDIO_PROVIDER", "auto"),
                AGENTIC_NOTIFICATION_SECRET=shared_secret,
            ),
            health_url=f"{interaction_base_url}/health",
        ),
        ServiceSpec(
            name="web",
            command=(
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                settings.web_host,
                "--port",
                str(settings.web_port),
            ),
            cwd=ROOT / "web_ui",
            environment=_environment(
                INTERACTION_API_URL=interaction_base_url,
                AGENTIC_API_URL=agentic_base_url,
                VITE_INTERACTION_API_URL=interaction_base_url,
                VITE_AGENTIC_API_URL=agentic_base_url,
                HOST=settings.web_host,
                PORT=str(settings.web_port),
            ),
            health_url=f"{web_base_url}/api/health",
        ),
    )


def _check_prerequisites(
    specs: tuple[ServiceSpec, ...],
    python: str,
    *,
    require_free_ports: bool = True,
) -> None:
    required_files = (
        ROOT / "agentic" / "run_server.py",
        ROOT / "user_interaction" / "run_server.py",
        ROOT / "web_ui" / "package.json",
    )
    missing_files = [str(path.relative_to(ROOT)) for path in required_files if not path.exists()]
    if missing_files:
        raise StartupError("Missing project files: " + ", ".join(missing_files))
    if shutil.which("node") is None or shutil.which("npm") is None:
        raise StartupError("npm was not found. Install Node.js 22 or newer.")
    node_version = _node_version()
    if node_version < (22, 13, 0):
        raise StartupError(
            f"Node.js 22.13 or newer is required; found {'.'.join(map(str, node_version))}."
        )
    if not (WEB_UI / "node_modules" / ".bin" / "vinext").exists():
        raise StartupError("UI dependencies are missing. Run: npm ci --prefix web_ui")

    dependency_check = subprocess.run(
        [python, "-c", "import dotenv, fastapi, httpx, uvicorn, websockets"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if dependency_check.returncode != 0:
        raise StartupError(
            "Python dependencies are missing. Run: "
            f"{python} -m pip install -r requirements.lock"
        )

    occupied = (
        [spec.health_url for spec in specs if not _port_available(spec.health_url)]
        if require_free_ports
        else []
    )
    if occupied:
        raise StartupError(
            "A Nafi port is already in use. Stop the previous stack or change its port: "
            + ", ".join(occupied)
        )


def _port_available(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        return False
    try:
        with socket.create_connection((host, port), timeout=0.15):
            return False
    except OSError:
        return True


def _node_version() -> tuple[int, int, int]:
    result = subprocess.run(
        ["node", "--version"], capture_output=True, text=True, check=False
    )
    raw = result.stdout.strip().removeprefix("v")
    try:
        values = tuple(int(part) for part in raw.split(".")[:3])
    except ValueError as exc:
        raise StartupError(f"Could not read the installed Node.js version: {raw!r}") from exc
    if len(values) != 3:
        raise StartupError(f"Could not read the installed Node.js version: {raw!r}")
    return values


def _run_setup(command: list[str], *, cwd: Path, label: str) -> None:
    print(f"Setting up {label}…", flush=True)
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise StartupError(f"Could not install {label}. Run the setup command again for details.") from exc


def _bootstrap_dependencies(*, enabled: bool) -> str:
    """Create missing runtimes so a fresh clone starts with one command."""
    if sys.version_info < (3, 10):
        raise StartupError(
            f"Python 3.10 or newer is required; found {sys.version_info.major}.{sys.version_info.minor}."
        )
    if shutil.which("node") is None or shutil.which("npm") is None:
        raise StartupError("Node.js 22.13 or newer with npm is required.")
    node_version = _node_version()
    if node_version < (22, 13, 0):
        raise StartupError(
            f"Node.js 22.13 or newer is required; found {'.'.join(map(str, node_version))}."
        )

    if not PYTHON.exists():
        if not enabled:
            raise StartupError("Python runtime is missing. Run without --no-install to create it.")
        _run_setup(
            [sys.executable, "-m", "venv", str(PYTHON.parent.parent)],
            cwd=ROOT,
            label="the Python virtual environment",
        )

    python = str(PYTHON)
    dependency_check = subprocess.run(
        [python, "-c", "import dotenv, fastapi, httpx, pytest, uvicorn, websockets"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if dependency_check.returncode != 0:
        if not enabled:
            raise StartupError("Python dependencies are missing. Run without --no-install to install them.")
        _run_setup(
            [python, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(PYTHON_LOCK)],
            cwd=ROOT,
            label="Python dependencies",
        )

    if not (WEB_UI / "node_modules" / ".bin" / "vinext").exists():
        if not enabled:
            raise StartupError("UI dependencies are missing. Run without --no-install to install them.")
        _run_setup(
            ["npm", "ci", "--no-audit", "--no-fund"],
            cwd=WEB_UI,
            label="web dependencies",
        )
    return python


def _wait_until_ready(
    processes: dict[str, subprocess.Popen[bytes]],
    specs: tuple[ServiceSpec, ...],
    timeout_seconds: float,
    stop_requested: Callable[[], bool] | None = None,
) -> bool:
    pending = {spec.name: spec for spec in specs}
    deadline = time.monotonic() + timeout_seconds
    while pending and time.monotonic() < deadline:
        if stop_requested is not None and stop_requested():
            return False
        for name, process in processes.items():
            exit_code = process.poll()
            if exit_code is not None:
                raise StartupError(f"{name} stopped during startup with exit code {exit_code}")
        for name, spec in tuple(pending.items()):
            if _healthy(spec.health_url):
                print(f"  ✓ {name} ready", flush=True)
                pending.pop(name)
        if pending:
            time.sleep(0.25)
    if pending:
        names = ", ".join(pending)
        raise StartupError(f"Timed out waiting for: {names}")
    return True


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.75) as response:
            if not 200 <= response.status < 300:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return isinstance(payload, dict) and payload.get("status") == "ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _stop_processes(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    for process in processes.values():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()
    for process in processes.values():
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()


def _connect_host(bind_host: str) -> str:
    if bind_host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return bind_host


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw_value!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw_value!r}") from exc


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the complete Nafi demo stack")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate configuration and dependencies without starting services",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="fail instead of installing missing project dependencies",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    processes: dict[str, subprocess.Popen[bytes]] = {}
    stopping = False
    unexpected_failure = False

    try:
        env_path = load_project_env(ROOT)
        settings = StackSettings.from_env()
        python = _bootstrap_dependencies(enabled=not args.no_install)
        specs = _service_specs(settings, python)
        _check_prerequisites(specs, python, require_free_ports=not args.check)

        print(f"Nafi configuration: {env_path if env_path.exists() else 'built-in demo defaults'}")
        print(
            "Providers: "
            f"banking={os.getenv('AGENTIC_BACKEND', 'mock') or 'mock'}, "
            f"voice={settings.interaction.resolved_voice_provider}, "
            f"model={'OpenAI' if settings.interaction.openai.api_key else 'deterministic mock'}"
        )
        for warning in settings.interaction.configuration_warnings:
            print(f"Warning: {warning}")
        if args.check:
            print("✓ Configuration and dependencies are ready")
            return 0

        def stop(_signum: int | None = None, _frame: object | None = None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

        print("Starting Nafi services…", flush=True)
        for spec in specs:
            processes[spec.name] = subprocess.Popen(
                spec.command,
                cwd=spec.cwd,
                env=spec.environment,
                start_new_session=True,
            )
        ready = _wait_until_ready(
            processes,
            specs,
            settings.startup_timeout_seconds,
            stop_requested=lambda: stopping,
        )
        if not ready:
            return 0

        web_url = f"http://localhost:{settings.web_port}"
        print(f"\n✓ Nafi is ready: {web_url}", flush=True)
        print("Press Ctrl+C to stop all services.\n", flush=True)
        while not stopping:
            failed = next(
                (
                    (name, process.returncode)
                    for name, process in processes.items()
                    if process.poll() is not None
                ),
                None,
            )
            if failed is not None:
                unexpected_failure = True
                print(
                    f"Service {failed[0]} stopped unexpectedly with exit code {failed[1]}",
                    file=sys.stderr,
                )
                break
            time.sleep(0.5)
    except (ConfigurationError, EnvFileError, StartupError) as exc:
        unexpected_failure = True
        print(f"Nafi could not start: {exc}", file=sys.stderr)
    finally:
        if processes:
            print("Stopping Nafi services…", flush=True)
            _stop_processes(processes)
    return 1 if unexpected_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
