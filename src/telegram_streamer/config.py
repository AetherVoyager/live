"""Configuration management using Pydantic Settings."""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TranscodeProfile(str, Enum):
    """Video transcode profiles."""
    AUTO = "auto"
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TG_",
        case_sensitive=False,
    )

    # Telegram API credentials (from https://my.telegram.org)
    api_id: int = Field(..., description="Telegram API ID")
    api_hash: str = Field(..., description="Telegram API Hash")
    
    # Session configuration
    session_name: str = Field(default="telegram_streamer", description="Pyrogram session name")
    session_path: Path = Field(default=Path("./sessions"), description="Path to store sessions")
    
    # Bot mode (optional - use userbot if not provided)
    bot_token: Optional[str] = Field(default=None, description="Bot token (if using bot mode)")
    
    # Phone number for userbot mode
    phone_number: Optional[str] = Field(default=None, description="Phone number for userbot auth")
    
    # Streaming defaults
    default_profile: TranscodeProfile = Field(
        default=TranscodeProfile.AUTO,
        description="Default transcode profile"
    )
    
    # FFmpeg configuration
    ffmpeg_path: str = Field(default="ffmpeg", description="Path to FFmpeg binary")
    ffmpeg_threads: int = Field(default=2, description="FFmpeg thread count")
    ffmpeg_timeout: int = Field(default=30, description="FFmpeg startup timeout in seconds")
    
    # Reconnection settings
    reconnect_enabled: bool = Field(default=True, description="Enable auto-reconnection")
    reconnect_min_delay: int = Field(default=5, description="Minimum reconnect delay in seconds")
    reconnect_max_delay: int = Field(default=30, description="Maximum reconnect delay in seconds")
    reconnect_max_attempts: int = Field(default=10, description="Maximum reconnection attempts")
    reconnect_timeout: int = Field(default=90, description="Max time to establish reconnection")
    
    # API server settings
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8080, description="API server port")
    api_workers: int = Field(default=1, description="API worker count")
    
    # Logging
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    log_json: bool = Field(default=False, description="Use JSON log format")
    
    # Health check
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    
    @field_validator("session_path", mode="before")
    @classmethod
    def validate_session_path(cls, v: str | Path) -> Path:
        """Ensure session path exists."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_bot_mode(self) -> bool:
        """Check if running in bot mode."""
        return self.bot_token is not None

    @property
    def session_file(self) -> Path:
        """Get full session file path."""
        return self.session_path / self.session_name


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
