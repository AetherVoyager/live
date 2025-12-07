"""Test configuration and fixtures."""

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Set test environment variables before importing app modules
os.environ.setdefault("TG_API_ID", "12345678")
os.environ.setdefault("TG_API_HASH", "test_api_hash_0123456789abcdef")
os.environ.setdefault("TG_SESSION_NAME", "test_session")
os.environ.setdefault("TG_SESSION_PATH", "./test_sessions")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock settings with test values."""
    from telegram_streamer.config import Settings, TranscodeProfile, LogLevel
    
    return Settings(
        api_id=12345678,
        api_hash="test_api_hash_0123456789abcdef",
        session_name="test_session",
        session_path="./test_sessions",
        bot_token="123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
        default_profile=TranscodeProfile.AUTO,
        ffmpeg_path="ffmpeg",
        ffmpeg_threads=2,
        reconnect_enabled=True,
        reconnect_min_delay=1,
        reconnect_max_delay=5,
        reconnect_max_attempts=3,
        reconnect_timeout=30,
        api_host="127.0.0.1",
        api_port=8080,
        log_level=LogLevel.DEBUG,
        log_json=False,
    )


@pytest.fixture
def mock_pyrogram_client():
    """Mock Pyrogram Client."""
    client = AsyncMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.get_me = AsyncMock(return_value=MagicMock(
        id=123456789,
        username="test_bot",
        is_bot=True,
    ))
    client.get_chat = AsyncMock(return_value=MagicMock(
        id=-1001234567890,
        title="Test Chat",
    ))
    return client


@pytest.fixture
def mock_tgcalls():
    """Mock PyTgCalls instance."""
    tgcalls = AsyncMock()
    tgcalls.start = AsyncMock()
    tgcalls.stop = AsyncMock()
    tgcalls.play = AsyncMock()
    tgcalls.leave_call = AsyncMock()
    tgcalls.pause_stream = AsyncMock()
    tgcalls.resume_stream = AsyncMock()
    return tgcalls


@pytest.fixture
def mock_ffmpeg_process():
    """Mock FFmpeg subprocess."""
    process = AsyncMock()
    process.pid = 12345
    process.returncode = None
    process.stdout = AsyncMock()
    process.stdout.read = AsyncMock(return_value=b"video_data")
    process.stderr = AsyncMock()
    process.stderr.read = AsyncMock(return_value=b"")
    process.terminate = MagicMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


@pytest.fixture
def sample_stream_sources():
    """Sample stream source URLs for testing."""
    return {
        "hls": "https://example.com/live/stream.m3u8",
        "m3u": "https://example.com/playlist.m3u",
        "rtmp": "rtmp://server.example.com/live/stream_key",
        "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "direct": "https://example.com/video.mp4",
    }
