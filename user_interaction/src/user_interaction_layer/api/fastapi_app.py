"""FastAPI HTTP and WebSocket runtime for chat and voice."""

from __future__ import annotations

import json
import hmac
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.api.server import build_application_from_env
from user_interaction_layer.application import InteractionApplication
from user_interaction_layer.config.settings import InteractionSettings
from user_interaction_layer.voice.models import AudioInput, VoiceTurnResult
from user_interaction_layer.voice.personaplex_bridge import (
    PersonaPlexBridgeConfig,
    PersonaPlexBridgeError,
    bridge_personaplex_websocket,
)
from user_interaction_layer.voice.providers import (
    MockVoiceAudioProvider,
    OpenAIVoiceAudioProvider,
    VoiceAudioProvider,
    VoiceProviderError,
)
from user_interaction_layer.voice.service import VoiceInteractionService


def create_fastapi_app(
    *,
    interaction_app: InteractionApplication | None = None,
    voice_provider: VoiceAudioProvider | None = None,
    settings: InteractionSettings | None = None,
) -> FastAPI:
    app_settings = settings or InteractionSettings.from_env()
    application = interaction_app or build_application_from_env(settings=app_settings)
    audio_provider = voice_provider or _build_voice_provider(app_settings)
    voice_service = VoiceInteractionService(
        orchestrator=application.orchestrator,
        audio_provider=audio_provider,
    )

    app = FastAPI(title="Nafi Interaction Layer", version="0.2.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "nafi-interaction",
            "version": "0.2.0",
            "mode": "api" if app_settings.openai.api_key else "demo",
            "providers": {
                "agentic": "mock" if app_settings.runtime.use_mock_agentic else "http",
                "voice": audio_provider.provider_name,
                "openai_configured": bool(app_settings.openai.api_key),
                "openrouter_configured": bool(app_settings.openrouter.api_key),
            },
            "capabilities": {
                "chat": True,
                "voice_websocket": True,
                "voice_audio": True,
                "english": True,
                "arabic": True,
            },
            "warnings": list(app_settings.configuration_warnings),
        }

    @app.post("/interaction/chat")
    async def chat(payload: dict[str, Any]) -> JSONResponse:
        try:
            return JSONResponse(application.handle_chat(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/interaction/voice/transcript")
    async def voice_transcript(payload: dict[str, Any]) -> JSONResponse:
        try:
            return JSONResponse(application.handle_voice_transcript(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/interaction/agentic-notification")
    async def agentic_notification(
        payload: dict[str, Any],
        webhook_secret: str | None = Header(default=None, alias="X-Agentic-Webhook-Secret"),
    ) -> JSONResponse:
        try:
            expected_secret = app_settings.agentic.notification_secret
            if expected_secret and not hmac.compare_digest(expected_secret, webhook_secret or ""):
                raise HTTPException(status_code=401, detail="Unauthorized agentic notification")
            return JSONResponse(application.handle_agentic_notification(payload))
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/interaction/voice/ws")
    async def voice_websocket(
        websocket: WebSocket,
        user_id: str = Query(...),
        language: str = Query("en"),
        session_id: str | None = Query(None),
        source_provider: str | None = Query(None),
        audio_mime_type: str = Query("audio/wav"),
        audio_filename: str = Query("input.wav"),
    ) -> None:
        await _handle_voice_pipeline_websocket(
            websocket=websocket,
            voice_service=voice_service,
            user_id=user_id,
            language=Language(language),
            source_provider=source_provider or _default_source_provider(Language(language), app_settings),
            session_id=session_id,
            audio_mime_type=audio_mime_type,
            audio_filename=audio_filename,
        )

    @app.websocket("/interaction/voice/personaplex/ws")
    async def personaplex_websocket(websocket: WebSocket) -> None:
        config = PersonaPlexBridgeConfig(
            base_url=app_settings.personaplex.url,
            api_key=app_settings.personaplex.api_key,
            voice_prompt=app_settings.personaplex.voice,
            text_prompt=app_settings.personaplex.text_prompt,
        )
        try:
            await bridge_personaplex_websocket(websocket, config)
        except PersonaPlexBridgeError as exc:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1011)

    return app


async def _handle_voice_pipeline_websocket(
    *,
    websocket: WebSocket,
    voice_service: VoiceInteractionService,
    user_id: str,
    language: Language,
    source_provider: str,
    session_id: str | None,
    audio_mime_type: str,
    audio_filename: str,
) -> None:
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "ready",
            "mode": "pipeline",
            "language": language.value,
            "source_provider": source_provider,
        }
    )

    audio_buffer = bytearray()
    active_session_id = session_id
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                audio_buffer.extend(message["bytes"])
                await websocket.send_json({"type": "audio_buffered", "bytes": len(audio_buffer)})
                continue

            text_message = message.get("text")
            if text_message is None:
                continue

            command = _parse_command(text_message)
            command_type = command.get("type")
            if command_type == "commit":
                if not audio_buffer:
                    await websocket.send_json({"type": "error", "message": "No audio buffered for commit"})
                    continue
                result = await voice_service.handle_audio_turn(
                    user_id=user_id,
                    audio=AudioInput(
                        data=bytes(audio_buffer),
                        mime_type=str(command.get("audio_mime_type", audio_mime_type)),
                        filename=str(command.get("audio_filename", audio_filename)),
                    ),
                    language=language,
                    source_provider=str(command.get("source_provider", source_provider)),
                    session_id=active_session_id,
                )
                active_session_id = result.session_id
                audio_buffer.clear()
                await _send_voice_turn(websocket, result)
            elif command_type == "text":
                transcript = str(command.get("text", "")).strip()
                if not transcript:
                    await websocket.send_json({"type": "error", "message": "Text command requires non-empty text"})
                    continue
                result = await voice_service.handle_text_turn(
                    user_id=user_id,
                    transcript=transcript,
                    language=language,
                    source_provider=str(command.get("source_provider", source_provider)),
                    session_id=active_session_id,
                )
                active_session_id = result.session_id
                await _send_voice_turn(websocket, result)
            elif command_type == "clear":
                audio_buffer.clear()
                await websocket.send_json({"type": "cleared"})
            elif command_type == "close":
                await websocket.close()
                return
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown command: {command_type}"})
    except WebSocketDisconnect:
        return
    except RuntimeError as exc:
        if "disconnect message" in str(exc):
            return
        raise
    except (VoiceProviderError, ValueError) as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1011)


async def _send_voice_turn(websocket: WebSocket, result: VoiceTurnResult) -> None:
    await websocket.send_json(
        {
            "type": "voice_turn",
            "session_id": result.session_id,
            "transcript": result.transcript,
            "message_to_user": result.message_to_user,
            "decision_type": result.decision_type,
            "language": result.language.value,
            "task_id": result.task_id,
            "request_id": result.request_id,
            "audio_mime_type": result.audio_mime_type,
            "audio_format": result.audio_format,
            "provider": result.provider,
        }
    )
    await websocket.send_json(
        {
            "type": "audio_start",
            "mime_type": result.audio_mime_type,
            "format": result.audio_format,
            "bytes": len(result.audio),
        }
    )
    await websocket.send_bytes(result.audio)
    await websocket.send_json({"type": "audio_end"})


def _parse_command(text_message: str) -> dict[str, Any]:
    try:
        command = json.loads(text_message)
    except json.JSONDecodeError as exc:
        raise ValueError("WebSocket text messages must be JSON commands") from exc
    if not isinstance(command, dict):
        raise ValueError("WebSocket command must be a JSON object")
    return command


def _build_voice_provider(settings: InteractionSettings) -> VoiceAudioProvider:
    provider = settings.resolved_voice_provider
    if provider == "mock":
        return MockVoiceAudioProvider()
    if provider == "openai":
        return OpenAIVoiceAudioProvider(
            api_key=settings.voice_audio.openai_api_key,
            stt_model=settings.voice_audio.stt_model,
            tts_model=settings.voice_audio.tts_model,
            tts_voice_en=settings.voice_audio.tts_voice_en,
            tts_voice_ar=settings.voice_audio.tts_voice_ar,
            tts_format=settings.voice_audio.tts_format,
            base_url=settings.openai.base_url,
        )
    raise ValueError(f"Unsupported VOICE_AUDIO_PROVIDER: {provider}")


def _default_source_provider(language: Language, settings: InteractionSettings) -> str:
    if language == Language.ARABIC:
        return settings.arabic_voice.provider or "arabic_voice"
    return "personaplex"
