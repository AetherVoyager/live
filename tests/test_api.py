"""Tests for REST API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

# Mock the streamer before importing API
with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
    mock_streamer = AsyncMock()
    mock_streamer.is_started = True
    mock_streamer.get_active_sessions.return_value = []
    mock_streamer.get_all_sessions.return_value = []
    mock_get_streamer.return_value = mock_streamer


class TestHealthEndpoints:
    """Tests for health check endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from telegram_streamer.api import app
        
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.is_started = True
            mock_streamer.get_active_sessions.return_value = []
            mock_get_streamer.return_value = mock_streamer
            
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client
    
    def test_health_endpoint(self, client):
        """Test /health endpoint."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.is_started = True
            mock_streamer.get_active_sessions.return_value = []
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "version" in data
            assert "uptime_seconds" in data
    
    def test_metrics_endpoint(self, client):
        """Test /metrics endpoint."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.is_started = True
            mock_streamer.get_active_sessions.return_value = []
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/metrics")
            
            assert response.status_code == 200
            assert "telegram_streamer" in response.text


class TestStreamEndpoints:
    """Tests for stream management endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from telegram_streamer.api import app
        return TestClient(app, raise_server_exceptions=False)
    
    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        from telegram_streamer.models import (
            StreamSession,
            StreamSource,
            StreamStatus,
            StreamType,
        )
        
        source = StreamSource(
            url="https://example.com/stream.m3u8",
            stream_type=StreamType.HLS,
        )
        return StreamSession(
            id="abc123",
            chat_id=-1001234567890,
            source=source,
            status=StreamStatus.STREAMING,
        )
    
    def test_list_streams_empty(self, client):
        """Test listing streams when none exist."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_all_sessions.return_value = []
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/api/streams")
            
            assert response.status_code == 200
            data = response.json()
            assert data["streams"] == []
            assert data["count"] == 0
    
    def test_list_streams_with_sessions(self, client, mock_session):
        """Test listing streams with active sessions."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_all_sessions.return_value = [mock_session]
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/api/streams")
            
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["streams"][0]["id"] == "abc123"
    
    def test_list_streams_active_only(self, client, mock_session):
        """Test listing only active streams."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_active_sessions.return_value = [mock_session]
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/api/streams?active_only=true")
            
            assert response.status_code == 200
            mock_streamer.get_active_sessions.assert_called_once()
    
    def test_start_stream_success(self, client, mock_session):
        """Test starting a stream successfully."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.is_started = True
            mock_streamer.start_stream.return_value = mock_session
            mock_get_streamer.return_value = mock_streamer
            
            response = client.post("/api/streams", json={
                "chat": "@testchannel",
                "source": "https://example.com/stream.m3u8",
                "profile": "720p",
            })
            
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "abc123"
    
    def test_start_stream_invalid_profile(self, client):
        """Test starting stream with invalid profile."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.is_started = True
            mock_get_streamer.return_value = mock_streamer
            
            response = client.post("/api/streams", json={
                "chat": "@testchannel",
                "source": "https://example.com/stream.m3u8",
                "profile": "invalid_profile",
            })
            
            assert response.status_code == 400
            assert "Invalid profile" in response.json()["detail"]
    
    def test_start_stream_streamer_not_started(self, client):
        """Test starting stream when streamer not initialized."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.is_started = False
            mock_get_streamer.return_value = mock_streamer
            
            response = client.post("/api/streams", json={
                "chat": "@testchannel",
                "source": "https://example.com/stream.m3u8",
            })
            
            assert response.status_code == 503
    
    def test_get_stream_success(self, client, mock_session):
        """Test getting stream details."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_session.return_value = mock_session
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/api/streams/abc123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "abc123"
    
    def test_get_stream_not_found(self, client):
        """Test getting non-existent stream."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_session.return_value = None
            mock_get_streamer.return_value = mock_streamer
            
            response = client.get("/api/streams/nonexistent")
            
            assert response.status_code == 404
    
    def test_stop_stream_success(self, client, mock_session):
        """Test stopping a stream."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_session.return_value = mock_session
            mock_streamer.stop_stream.return_value = True
            mock_get_streamer.return_value = mock_streamer
            
            response = client.delete("/api/streams/abc123")
            
            assert response.status_code == 204
    
    def test_stop_stream_not_found(self, client):
        """Test stopping non-existent stream."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.get_session.return_value = None
            mock_streamer.stop_stream.return_value = False
            mock_get_streamer.return_value = mock_streamer
            
            response = client.delete("/api/streams/nonexistent")
            
            assert response.status_code == 404
    
    def test_pause_stream_success(self, client, mock_session):
        """Test pausing a stream."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.pause_stream.return_value = True
            mock_streamer.get_session.return_value = mock_session
            mock_get_streamer.return_value = mock_streamer
            
            response = client.post("/api/streams/abc123/pause")
            
            assert response.status_code == 200
    
    def test_resume_stream_success(self, client, mock_session):
        """Test resuming a paused stream."""
        with patch("telegram_streamer.api.get_streamer") as mock_get_streamer:
            mock_streamer = AsyncMock()
            mock_streamer.resume_stream.return_value = True
            mock_streamer.get_session.return_value = mock_session
            mock_get_streamer.return_value = mock_streamer
            
            response = client.post("/api/streams/abc123/resume")
            
            assert response.status_code == 200
