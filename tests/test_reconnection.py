"""Tests for reconnection logic."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_streamer.exceptions import (
    ReconnectionError,
    StreamConnectionError,
)
from telegram_streamer.models import StreamSession, StreamSource, StreamStatus, StreamType
from telegram_streamer.reconnection import ReconnectionManager, HealthMonitor


class TestReconnectionManager:
    """Tests for ReconnectionManager class."""
    
    @pytest.fixture
    def mock_start_stream(self):
        """Mock start stream function."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_stop_stream(self):
        """Mock stop stream function."""
        return AsyncMock()
    
    @pytest.fixture
    def reconnection_manager(self, mock_start_stream, mock_stop_stream, mock_settings):
        """Create reconnection manager for testing."""
        with patch("telegram_streamer.reconnection.get_settings", return_value=mock_settings):
            return ReconnectionManager(mock_start_stream, mock_stop_stream)
    
    @pytest.fixture
    def sample_session(self):
        """Create sample session for testing."""
        source = StreamSource(
            url="https://example.com/stream.m3u8",
            stream_type=StreamType.HLS,
        )
        session = StreamSession(
            id="test123",
            chat_id=-1001234567890,
            source=source,
            status=StreamStatus.STREAMING,
        )
        return session
    
    @pytest.mark.asyncio
    async def test_handle_disconnect_starts_reconnection(
        self,
        reconnection_manager,
        sample_session,
    ):
        """Test that handle_disconnect starts reconnection task."""
        await reconnection_manager.handle_disconnect(sample_session)
        
        # Give task time to start
        await asyncio.sleep(0.1)
        
        assert reconnection_manager.is_reconnecting(sample_session.id)
        
        # Cleanup
        await reconnection_manager.cancel_reconnection(sample_session.id)
    
    @pytest.mark.asyncio
    async def test_handle_disconnect_when_disabled(
        self,
        mock_start_stream,
        mock_stop_stream,
        sample_session,
    ):
        """Test handle_disconnect when reconnection is disabled."""
        mock_settings = MagicMock()
        mock_settings.reconnect_enabled = False
        
        with patch("telegram_streamer.reconnection.get_settings", return_value=mock_settings):
            manager = ReconnectionManager(mock_start_stream, mock_stop_stream)
            await manager.handle_disconnect(sample_session, "Test error")
            
            assert sample_session.status == StreamStatus.ERROR
            assert sample_session.last_error == "Test error"
            assert not manager.is_reconnecting(sample_session.id)
    
    @pytest.mark.asyncio
    async def test_handle_disconnect_max_attempts_exceeded(
        self,
        reconnection_manager,
        sample_session,
        mock_settings,
    ):
        """Test handle_disconnect when max attempts exceeded."""
        sample_session.reconnect_attempts = mock_settings.reconnect_max_attempts
        
        await reconnection_manager.handle_disconnect(sample_session)
        
        assert sample_session.status == StreamStatus.ERROR
        assert "Max reconnection attempts" in sample_session.last_error
    
    @pytest.mark.asyncio
    async def test_cancel_reconnection(
        self,
        reconnection_manager,
        sample_session,
    ):
        """Test cancelling a reconnection attempt."""
        await reconnection_manager.handle_disconnect(sample_session)
        await asyncio.sleep(0.1)
        
        result = await reconnection_manager.cancel_reconnection(sample_session.id)
        
        assert result is True
        assert not reconnection_manager.is_reconnecting(sample_session.id)
    
    @pytest.mark.asyncio
    async def test_cancel_reconnection_not_found(self, reconnection_manager):
        """Test cancelling non-existent reconnection."""
        result = await reconnection_manager.cancel_reconnection("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_is_reconnecting(
        self,
        reconnection_manager,
        sample_session,
    ):
        """Test checking if session is reconnecting."""
        assert not reconnection_manager.is_reconnecting(sample_session.id)
        
        await reconnection_manager.handle_disconnect(sample_session)
        await asyncio.sleep(0.1)
        
        assert reconnection_manager.is_reconnecting(sample_session.id)
        
        await reconnection_manager.cancel_reconnection(sample_session.id)
    
    @pytest.mark.asyncio
    async def test_stop_cancels_all_reconnections(
        self,
        reconnection_manager,
        sample_session,
    ):
        """Test stopping manager cancels all reconnections."""
        await reconnection_manager.handle_disconnect(sample_session)
        await asyncio.sleep(0.1)
        
        await reconnection_manager.stop()
        
        assert not reconnection_manager.is_reconnecting(sample_session.id)
    
    @pytest.mark.asyncio
    async def test_successful_reconnection(
        self,
        mock_start_stream,
        mock_stop_stream,
        sample_session,
    ):
        """Test successful reconnection updates session status."""
        mock_settings = MagicMock()
        mock_settings.reconnect_enabled = True
        mock_settings.reconnect_min_delay = 0.1
        mock_settings.reconnect_max_delay = 0.2
        mock_settings.reconnect_max_attempts = 3
        mock_settings.reconnect_timeout = 10
        
        # Make start_stream succeed
        mock_start_stream.return_value = sample_session
        
        with patch("telegram_streamer.reconnection.get_settings", return_value=mock_settings):
            manager = ReconnectionManager(mock_start_stream, mock_stop_stream)
            await manager.handle_disconnect(sample_session)
            
            # Wait for reconnection to complete
            await asyncio.sleep(0.5)
            
            assert sample_session.status == StreamStatus.STREAMING
            mock_start_stream.assert_called()


class TestHealthMonitor:
    """Tests for HealthMonitor class."""
    
    @pytest.fixture
    def mock_reconnection_manager(self):
        """Create mock reconnection manager."""
        return MagicMock()
    
    @pytest.fixture
    def health_monitor(self, mock_reconnection_manager):
        """Create health monitor for testing."""
        return HealthMonitor(mock_reconnection_manager, check_interval=1)
    
    @pytest.fixture
    def sample_session(self):
        """Create sample session for testing."""
        source = StreamSource(
            url="https://example.com/stream.m3u8",
            stream_type=StreamType.HLS,
        )
        return StreamSession(
            id="test123",
            chat_id=-1001234567890,
            source=source,
            status=StreamStatus.STREAMING,
        )
    
    def test_register_session(self, health_monitor, sample_session):
        """Test registering a session for monitoring."""
        health_monitor.register_session(sample_session)
        assert sample_session.id in health_monitor._sessions
    
    def test_unregister_session(self, health_monitor, sample_session):
        """Test unregistering a session."""
        health_monitor.register_session(sample_session)
        health_monitor.unregister_session(sample_session.id)
        assert sample_session.id not in health_monitor._sessions
    
    def test_unregister_nonexistent_session(self, health_monitor):
        """Test unregistering non-existent session does not raise."""
        health_monitor.unregister_session("nonexistent")  # Should not raise
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self, health_monitor):
        """Test starting and stopping the monitor."""
        await health_monitor.start()
        assert health_monitor._active is True
        assert health_monitor._monitor_task is not None
        
        await health_monitor.stop()
        assert health_monitor._active is False
    
    @pytest.mark.asyncio
    async def test_monitor_already_started(self, health_monitor):
        """Test starting an already started monitor."""
        await health_monitor.start()
        await health_monitor.start()  # Should not raise
        
        await health_monitor.stop()
