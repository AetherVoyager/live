"""Tests for the Telegram streamer module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_streamer.config import TranscodeProfile
from telegram_streamer.exceptions import (
    AuthenticationError,
    ChatNotFoundError,
    PermissionError,
    StreamConnectionError,
)
from telegram_streamer.models import StreamStatus


class TestTelegramStreamer:
    """Tests for TelegramStreamer class."""
    
    @pytest.fixture
    def streamer(self, mock_settings):
        """Create streamer instance for testing."""
        with patch("telegram_streamer.streamer.get_settings", return_value=mock_settings):
            from telegram_streamer.streamer import TelegramStreamer
            return TelegramStreamer()
    
    @pytest.mark.asyncio
    async def test_start_creates_client(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test starting streamer creates Pyrogram client and PyTgCalls."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                await streamer.start()
                
                assert streamer.is_started is True
                assert streamer.client is not None
                mock_pyrogram_client.start.assert_called_once()
                mock_tgcalls.start.assert_called_once()
                
                await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_start_already_started(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test starting an already started streamer."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                await streamer.start()
                await streamer.start()  # Should not raise
                
                # Client.start should only be called once
                assert mock_pyrogram_client.start.call_count == 1
                
                await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_stop_cleans_up(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test stopping streamer cleans up resources."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                await streamer.start()
                await streamer.stop()
                
                assert streamer.is_started is False
                mock_tgcalls.stop.assert_called_once()
                mock_pyrogram_client.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_stream_not_started_raises_error(self, streamer):
        """Test starting stream when not started raises error."""
        with pytest.raises(StreamConnectionError, match="not started"):
            await streamer.start_stream(
                "@testchannel",
                "https://example.com/stream.m3u8",
            )
    
    @pytest.mark.asyncio
    async def test_start_stream_success(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test starting a stream successfully."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                with patch("telegram_streamer.streamer.MediaStream"):
                    await streamer.start()
                    
                    session = await streamer.start_stream(
                        "-1001234567890",
                        "https://example.com/stream.m3u8",
                        TranscodeProfile.P720,
                    )
                    
                    assert session is not None
                    assert session.status == StreamStatus.STREAMING
                    assert session.profile == "720p"
                    mock_tgcalls.play.assert_called_once()
                    
                    await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_stop_stream_success(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test stopping a stream successfully."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                with patch("telegram_streamer.streamer.MediaStream"):
                    await streamer.start()
                    
                    session = await streamer.start_stream(
                        "-1001234567890",
                        "https://example.com/stream.m3u8",
                    )
                    
                    result = await streamer.stop_stream(session.id)
                    
                    assert result is True
                    assert session.status == StreamStatus.STOPPED
                    mock_tgcalls.leave_call.assert_called_once()
                    
                    await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_stop_stream_not_found(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test stopping non-existent stream."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                await streamer.start()
                
                result = await streamer.stop_stream("nonexistent")
                
                assert result is False
                
                await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_get_session(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test getting a session by ID."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                with patch("telegram_streamer.streamer.MediaStream"):
                    await streamer.start()
                    
                    session = await streamer.start_stream(
                        "-1001234567890",
                        "https://example.com/stream.m3u8",
                    )
                    
                    retrieved = streamer.get_session(session.id)
                    
                    assert retrieved is session
                    assert streamer.get_session("nonexistent") is None
                    
                    await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_get_all_sessions(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test getting all sessions."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                with patch("telegram_streamer.streamer.MediaStream"):
                    await streamer.start()
                    
                    await streamer.start_stream(
                        "-1001234567890",
                        "https://example.com/stream1.m3u8",
                    )
                    await streamer.start_stream(
                        "-1001234567891",
                        "https://example.com/stream2.m3u8",
                    )
                    
                    sessions = streamer.get_all_sessions()
                    
                    assert len(sessions) == 2
                    
                    await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_get_active_sessions(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test getting only active sessions."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                with patch("telegram_streamer.streamer.MediaStream"):
                    await streamer.start()
                    
                    session1 = await streamer.start_stream(
                        "-1001234567890",
                        "https://example.com/stream1.m3u8",
                    )
                    session2 = await streamer.start_stream(
                        "-1001234567891",
                        "https://example.com/stream2.m3u8",
                    )
                    
                    await streamer.stop_stream(session1.id)
                    
                    active = streamer.get_active_sessions()
                    
                    assert len(active) == 1
                    assert active[0].id == session2.id
                    
                    await streamer.stop()
    
    @pytest.mark.asyncio
    async def test_pause_resume_stream(
        self,
        streamer,
        mock_pyrogram_client,
        mock_tgcalls,
    ):
        """Test pausing and resuming a stream."""
        with patch("telegram_streamer.streamer.Client", return_value=mock_pyrogram_client):
            with patch("telegram_streamer.streamer.PyTgCalls", return_value=mock_tgcalls):
                with patch("telegram_streamer.streamer.MediaStream"):
                    await streamer.start()
                    
                    session = await streamer.start_stream(
                        "-1001234567890",
                        "https://example.com/stream.m3u8",
                    )
                    
                    # Pause
                    result = await streamer.pause_stream(session.id)
                    assert result is True
                    assert session.status == StreamStatus.PAUSED
                    
                    # Resume
                    result = await streamer.resume_stream(session.id)
                    assert result is True
                    assert session.status == StreamStatus.STREAMING
                    
                    await streamer.stop()
