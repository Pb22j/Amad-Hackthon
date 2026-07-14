import os
import hashlib
from app.config import settings
from app.utils.logger import logger

class AudioCache:
    def __init__(self, cache_dir: str = settings.CACHE_DIR, enabled: bool = settings.CACHE_ENABLED):
        self.cache_dir = cache_dir
        self.enabled = enabled
        if self.enabled and not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            logger.info(f"Created audio cache directory at: {self.cache_dir}")

    def _get_cache_key(self, provider: str, voice_id: str, text: str) -> str:
        """Generate a unique cache key based on provider, voice_id, and text content."""
        raw_key = f"{provider.lower()}:{voice_id.lower()}:{text.strip().lower()}"
        hashed = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return hashed

    def get(self, provider: str, voice_id: str, text: str) -> bytes | None:
        """Retrieve audio bytes from cache if exists."""
        if not self.enabled:
            return None
        
        cache_key = self._get_cache_key(provider, voice_id, text)
        file_path = os.path.join(self.cache_dir, f"{cache_key}.mp3")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    logger.info(f"Cache hit for provider={provider}, voice_id={voice_id}")
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading audio cache file: {e}")
        return None

    def set(self, provider: str, voice_id: str, text: str, audio_bytes: bytes) -> None:
        """Store audio bytes in cache."""
        if not self.enabled:
            return
        
        cache_key = self._get_cache_key(provider, voice_id, text)
        file_path = os.path.join(self.cache_dir, f"{cache_key}.mp3")
        
        try:
            with open(file_path, "wb") as f:
                f.write(audio_bytes)
            logger.info(f"Cached audio bytes to {file_path}")
        except Exception as e:
            logger.error(f"Failed to write audio cache to file: {e}")

# Global cache instance
audio_cache = AudioCache()
