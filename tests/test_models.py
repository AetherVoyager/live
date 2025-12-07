"""Tests for data models."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from telegram_streamer.models import (
    StreamStatus,
    StreamType,
    StreamSource,
    TranscodeSettings,
    StreamSession,
)


class TestStreamStatus:
    """Tests for StreamStatus enum."""
    
    def test_all_statuses_defined(self):
        """Test all expected statuses exist."""
        expected = ["pending", "connecting", "streaming", "reconnecting", 
                    "paused", "stopped", "error"]
        actual = [s.value for s in StreamStatus]
        assert sorted(actual) == sorted(expected)


class TestStreamType:
    """Tests for StreamType enum."""
    
    def test_all_types_defined(self):
        """Test all expected stream types exist."""
        expected = ["m3u", "m3u8", "hls", "rtmp", "youtube", "direct"]
        actual = [t.value for t in StreamType]
        assert sorted(actual) == sorted(expected)


class TestStreamSource:
    """Tests for StreamSource dataclass."""
    
    def test_create_stream_source(self):
        """Test creating a stream source."""
        source = StreamSource(
            url="https://example.com/stream.m3u8",
            stream_type=StreamType.HLS,
            name="Test Stream",
        )
        assert source.url == "https://example.com/stream.m3u8"
        assert source.stream_type == StreamType.HLS
        assert source.name == "Test Stream"
    
    def test_detect_hls_url(self):
        """Test detecting HLS stream from URL."""
        source = StreamSource.detect_type("https://example.com/live/stream.m3u8")
        assert source.stream_type == StreamType.HLS
    
    def test_detect_m3u_url(self):
        """Test detecting M3U playlist from URL."""
        source = StreamSource.detect_type("https://example.com/playlist.m3u")
        assert source.stream_type == StreamType.M3U
    
    def test_detect_rtmp_url(self):
        """Test detecting RTMP stream from URL."""
        source = StreamSource.detect_type("rtmp://server/live/key")
        assert source.stream_type == StreamType.RTMP
    
    def test_detect_rtmps_url(self):
        """Test detecting RTMPS stream from URL."""
        source = StreamSource.detect_type("rtmps://server/live/key")
        assert source.stream_type == StreamType.RTMP
    
    def test_detect_youtube_url(self):
        """Test detecting YouTube URL."""
        source = StreamSource.detect_type("https://www.youtube.com/watch?v=abc123")
        assert source.stream_type == StreamType.YOUTUBE
    
    def test_detect_youtube_short_url(self):
        """Test detecting YouTube short URL."""
        source = StreamSource.detect_type("https://youtu.be/abc123")
        assert source.stream_type == StreamType.YOUTUBE
    
    def test_detect_unknown_defaults_to_hls(self):
        """Test unknown URL defaults to HLS."""
        source = StreamSource.detect_type("https://example.com/video/feed")
        assert source.stream_type == StreamType.HLS


class TestTranscodeSettings:
    """Tests for TranscodeSettings dataclass."""
    
    def test_create_settings(self):
        """Test creating transcode settings."""
        settings = TranscodeSettings(
            width=1280,
            height=720,
            video_bitrate="3000k",
            audio_bitrate="192k",
            fps=30,
        )
        assert settings.width == 1280
        assert settings.height == 720
        assert settings.video_bitrate == "3000k"
        assert settings.audio_bitrate == "192k"
        assert settings.fps == 30
    
    def test_get_480p_profile(self):
        """Test getting 480p profile."""
        settings = TranscodeSettings.get_profile("480p")
        assert settings is not None
        assert settings.width == 854
        assert settings.height == 480
        assert settings.video_bitrate == "1500k"
    
    def test_get_720p_profile(self):
        """Test getting 720p profile."""
        settings = TranscodeSettings.get_profile("720p")
        assert settings is not None
        assert settings.width == 1280
        assert settings.height == 720
        assert settings.video_bitrate == "3000k"
    
    def test_get_1080p_profile(self):
        """Test getting 1080p profile."""
        settings = TranscodeSettings.get_profile("1080p")
        assert settings is not None
        assert settings.width == 1920
        assert settings.height == 1080
        assert settings.video_bitrate == "5000k"
    
    def test_get_auto_profile_returns_none(self):
        """Test auto profile returns None."""
        settings = TranscodeSettings.get_profile("auto")
        assert settings is None
    
    def test_get_invalid_profile_returns_none(self):
        """Test invalid profile returns None."""
        settings = TranscodeSettings.get_profile("invalid")
        assert settings is None


class TestStreamSession:
    """Tests for StreamSession dataclass."""
    
    @pytest.fixture
    def sample_session(self):
        """Create a sample session for testing."""
        source = StreamSource(
            url="https://example.com/stream.m3u8",
            stream_type=StreamType.HLS,
        )
        return StreamSession(
            id="abc123",
            chat_id=-1001234567890,
            source=source,
            profile="720p",
        )
    
    def test_create_session(self, sample_session):
        """Test creating a stream session."""
        assert sample_session.id == "abc123"
        assert sample_session.chat_id == -1001234567890
        assert sample_session.status == StreamStatus.PENDING
        assert sample_session.profile == "720p"
        assert sample_session.reconnect_attempts == 0
    
    def test_mark_streaming(self, sample_session):
        """Test marking session as streaming."""
        sample_session.mark_streaming()
        
        assert sample_session.status == StreamStatus.STREAMING
        assert sample_session.started_at is not None
        assert sample_session.reconnect_attempts == 0
    
    def test_mark_reconnecting(self, sample_session):
        """Test marking session as reconnecting."""
        sample_session.mark_reconnecting()
        
        assert sample_session.status == StreamStatus.RECONNECTING
        assert sample_session.reconnect_attempts == 1
        assert sample_session.last_reconnect_at is not None
        
        # Mark again to increment counter
        sample_session.mark_reconnecting()
        assert sample_session.reconnect_attempts == 2
    
    def test_mark_error(self, sample_session):
        """Test marking session with error."""
        sample_session.mark_error("Connection lost")
        
        assert sample_session.status == StreamStatus.ERROR
        assert sample_session.last_error == "Connection lost"
        assert sample_session.error_count == 1
        
        # Mark again to increment counter
        sample_session.mark_error("Another error")
        assert sample_session.error_count == 2
    
    def test_mark_stopped(self, sample_session):
        """Test marking session as stopped."""
        sample_session.mark_streaming()
        sample_session.mark_stopped()
        
        assert sample_session.status == StreamStatus.STOPPED
        assert sample_session.stopped_at is not None
    
    def test_duration_seconds_not_started(self, sample_session):
        """Test duration is 0 when not started."""
        assert sample_session.duration_seconds == 0.0
    
    def test_duration_seconds_while_streaming(self, sample_session):
        """Test duration calculation while streaming."""
        sample_session.started_at = datetime.utcnow() - timedelta(seconds=60)
        
        duration = sample_session.duration_seconds
        assert 59 <= duration <= 61  # Allow small variance
    
    def test_duration_seconds_after_stopped(self, sample_session):
        """Test duration calculation after stopped."""
        sample_session.started_at = datetime.utcnow() - timedelta(seconds=120)
        sample_session.stopped_at = datetime.utcnow() - timedelta(seconds=60)
        
        duration = sample_session.duration_seconds
        assert 59 <= duration <= 61
    
    def test_to_dict(self, sample_session):
        """Test converting session to dictionary."""
        sample_session.mark_streaming()
        data = sample_session.to_dict()
        
        assert data["id"] == "abc123"
        assert data["chat_id"] == -1001234567890
        assert data["source_url"] == "https://example.com/stream.m3u8"
        assert data["source_type"] == "hls"
        assert data["status"] == "streaming"
        assert data["profile"] == "720p"
        assert "created_at" in data
        assert "started_at" in data
        assert "duration_seconds" in data
