import os
import shutil
import pytest
from app.utils.cache import AudioCache

@pytest.fixture
def temp_cache():
    cache_dir = "test_cache_dir"
    # Ensure empty
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        
    cache = AudioCache(cache_dir=cache_dir, enabled=True)
    yield cache
    
    # Cleanup
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)

def test_cache_set_and_get(temp_cache):
    provider = "openai"
    voice_id = "alloy"
    text = "hello test response"
    audio_data = b"my_synthetic_voice_data_123"

    # Check cache miss
    assert temp_cache.get(provider, voice_id, text) is None

    # Save to cache
    temp_cache.set(provider, voice_id, text, audio_data)

    # Check cache hit
    cached_data = temp_cache.get(provider, voice_id, text)
    assert cached_data == audio_data

def test_cache_disabled():
    cache = AudioCache(cache_dir="test_cache_disabled", enabled=False)
    cache.set("openai", "alloy", "hello", b"data")
    assert cache.get("openai", "alloy", "hello") is None
    # No directory should be created
    assert not os.path.exists("test_cache_disabled")
