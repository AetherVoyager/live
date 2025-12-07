"""Tests for configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from telegram_streamer.config import (
    Settings,
    TranscodeProfile,
    LogLevel,
    get_settings,
)


class TestTranscodeProfile:
    """Tests for TranscodeProfile enum."""
    
    def test_profile_values(self):
        """Test all profile values are defined."""
        assert TranscodeProfile.AUTO.value == "auto"
        assert TranscodeProfile.P480.value == "480p"
        assert TranscodeProfile.P720.value == "720p"
        assert TranscodeProfile.P1080.value == "1080p"
    
    def test_profile_from_string(self):
        """Test creating profile from string."""
        assert TranscodeProfile("auto") == TranscodeProfile.AUTO
        assert TranscodeProfile("480p") == TranscodeProfile.P480
        assert TranscodeProfile("720p") == TranscodeProfile.P720
        assert TranscodeProfile("1080p") == TranscodeProfile.P1080
    
    def test_invalid_profile(self):
        """Test invalid profile raises error."""
        with pytest.raises(ValueError):
            TranscodeProfile("invalid")


class TestLogLevel:
    """Tests for LogLevel enum."""
    
    def test_log_level_values(self):
        """Test all log level values."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"


class TestSettings:
    """Tests for Settings configuration."""
    
    def test_settings_from_env(self, mock_settings):
        """Test settings can be loaded from environment."""
        assert mock_settings.api_id == 12345678
        assert mock_settings.api_hash == "test_api_hash_0123456789abcdef"
        assert mock_settings.session_name == "test_session"
    
    def test_is_bot_mode_with_token(self, mock_settings):
        """Test bot mode detection with token."""
        assert mock_settings.is_bot_mode is True
    
    def test_is_bot_mode_without_token(self):
        """Test bot mode detection without token."""
        settings = Settings(
            api_id=12345678,
            api_hash="test_hash_1234567890123456",
            phone_number="+1234567890",
        )
        assert settings.is_bot_mode is False
    
    def test_session_file_path(self, mock_settings):
        """Test session file path generation."""
        expected = Path("./test_sessions") / "test_session"
        assert mock_settings.session_file == expected
    
    def test_default_values(self):
        """Test default configuration values."""
        settings = Settings(
            api_id=12345678,
            api_hash="test_hash_1234567890123456",
        )
        
        assert settings.default_profile == TranscodeProfile.AUTO
        assert settings.ffmpeg_path == "ffmpeg"
        assert settings.ffmpeg_threads == 2
        assert settings.reconnect_enabled is True
        assert settings.reconnect_max_attempts == 10
        assert settings.api_port == 8080
        assert settings.log_level == LogLevel.INFO
    
    def test_reconnect_settings(self, mock_settings):
        """Test reconnection configuration."""
        assert mock_settings.reconnect_enabled is True
        assert mock_settings.reconnect_min_delay == 1
        assert mock_settings.reconnect_max_delay == 5
        assert mock_settings.reconnect_max_attempts == 3
        assert mock_settings.reconnect_timeout == 30


class TestGetSettings:
    """Tests for get_settings function."""
    
    def test_get_settings_returns_instance(self):
        """Test get_settings returns Settings instance."""
        # Clear cache first
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {
            "TG_API_ID": "12345678",
            "TG_API_HASH": "test_hash_1234567890123456",
        }):
            settings = get_settings()
            assert isinstance(settings, Settings)
    
    def test_get_settings_is_cached(self):
        """Test get_settings returns cached instance."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {
            "TG_API_ID": "12345678",
            "TG_API_HASH": "test_hash_1234567890123456",
        }):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2
