"""Run the user interaction HTTP/WebSocket server."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from user_interaction_layer.api.fastapi_app import create_fastapi_app
from user_interaction_layer.config.env import load_project_env
from user_interaction_layer.config.settings import InteractionSettings


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    load_project_env(project_root)
    settings = InteractionSettings.from_env()
    print(
        "Nafi interaction service: "
        f"voice={settings.resolved_voice_provider}, "
        f"agentic={'mock' if settings.runtime.use_mock_agentic else 'http'}"
    )
    for warning in settings.configuration_warnings:
        print(f"Configuration warning: {warning}")
    uvicorn.run(
        create_fastapi_app(settings=settings),
        host=settings.runtime.host,
        port=settings.runtime.port,
    )
