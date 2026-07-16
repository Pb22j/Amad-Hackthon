"""Bounded, expiring local audio cache; disabled by default for financial speech."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

from app.config import settings
from app.utils.logger import logger


class AudioCache:
    def __init__(
        self,
        cache_dir: str = settings.CACHE_DIR,
        enabled: bool = settings.CACHE_ENABLED,
        *,
        ttl_seconds: int = settings.CACHE_TTL_SECONDS,
        max_entries: int = settings.CACHE_MAX_ENTRIES,
        max_audio_bytes: int = settings.CACHE_MAX_AUDIO_BYTES,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.max_audio_bytes = max_audio_bytes
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def _get_cache_key(provider: str, voice_id: str, text: str) -> str:
        raw_key = f"{provider.casefold()}:{voice_id.casefold()}:{text.strip().casefold()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _path(self, provider: str, voice_id: str, text: str) -> Path:
        return self.cache_dir / f"{self._get_cache_key(provider, voice_id, text)}.mp3"

    def get(self, provider: str, voice_id: str, text: str) -> bytes | None:
        if not self.enabled:
            return None
        path = self._path(provider, voice_id, text)
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            if stat.st_size > self.max_audio_bytes:
                path.unlink(missing_ok=True)
                return None
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("Audio cache read failed: %s", type(exc).__name__)
            return None

    def _evict(self) -> None:
        files = sorted(
            self.cache_dir.glob("*.mp3"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in files[self.max_entries :]:
            path.unlink(missing_ok=True)

    def set(self, provider: str, voice_id: str, text: str, audio_bytes: bytes) -> None:
        if not self.enabled or len(audio_bytes) > self.max_audio_bytes:
            return
        path = self._path(provider, voice_id, text)
        try:
            descriptor, temporary = tempfile.mkstemp(dir=self.cache_dir, prefix=".audio-")
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(audio_bytes)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            self._evict()
        except OSError as exc:
            logger.warning("Audio cache write failed: %s", type(exc).__name__)


audio_cache = AudioCache()
