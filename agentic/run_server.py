"""Run the mock-backed agentic financial service."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent / ".env")
    # Import only after dotenv is loaded: importing the ASGI module constructs
    # the selected provider runtime and must see the final fail-closed config.
    from agentic_service.api import app

    uvicorn.run(
        app,
        host=os.getenv("AGENTIC_HOST", "127.0.0.1"),
        port=int(os.getenv("AGENTIC_PORT", "8090")),
    )
