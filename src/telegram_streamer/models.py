"""Data models for streaming operations."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class StreamStatus(str, Enum):
    """Stream lifecycle states."""
    PENDING = "pending"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class StreamType(str, Enum):
    """Supported stream source types."""
    M3U = "m3u"
    M3U8 = "m3u8"
    HLS = "hls"
    RTMP = "rtmp"
    YOUTUBE = "youtube"
    DIRECT = "direct"  # Direct video file URL


@dataclass
class StreamSource:
    """Represents a stream source."""
    url: str
    stream_type: StreamType
    name: Optional[str] = None
    
    @classmethod
    def detect_type(cls, url: str) -> "StreamSource":
        """Auto-detect stream type from URL.
        
        Args:
            url: Stream URL
            
        Returns:
            StreamSource with detected type
        """
        url_lower = url.lower()
        
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return cls(url=url, stream_type=StreamType.YOUTUBE)
        elif url_lower.endswith(".m3u"):
            return cls(url=url, stream_type=StreamType.M3U)
        elif url_lower.endswith(".m3u8") or "/hls/" in url_lower:
            return cls(url=url, stream_type=StreamType.HLS)
        elif url_lower.startswith("rtmp://") or url_lower.startswith("rtmps://"):
            return cls(url=url, stream_type=StreamType.RTMP)
        else:
            # Assume HLS for most HTTP streams
            return cls(url=url, stream_type=StreamType.HLS)


@dataclass
class TranscodeSettings:
    """FFmpeg transcode settings for a profile."""
    width: int
    height: int
    video_bitrate: str
    audio_bitrate: str = "128k"
    fps: int = 30
    
    # Preset profiles
    PROFILES: dict = field(default_factory=dict, repr=False, init=False)
    
    def __post_init__(self) -> None:
        """Initialize preset profiles."""
        TranscodeSettings.PROFILES = {
            "480p": TranscodeSettings(width=854, height=480, video_bitrate="1500k", fps=30),
            "720p": TranscodeSettings(width=1280, height=720, video_bitrate="3000k", fps=30),
            "1080p": TranscodeSettings(width=1920, height=1080, video_bitrate="5000k", fps=30),
        }
    
    @classmethod
    def get_profile(cls, profile: str) -> Optional["TranscodeSettings"]:
        """Get transcode settings for a profile name.
        
        Args:
            profile: Profile name (480p, 720p, 1080p)
            
        Returns:
            TranscodeSettings or None if auto/unknown
        """
        profiles = {
            "480p": cls(width=854, height=480, video_bitrate="1500k", fps=30),
            "720p": cls(width=1280, height=720, video_bitrate="3000k", fps=30),
            "1080p": cls(width=1920, height=1080, video_bitrate="5000k", fps=30),
        }
        return profiles.get(profile)


@dataclass
class StreamSession:
    """Active streaming session state."""
    id: str
    chat_id: int
    source: StreamSource
    status: StreamStatus = StreamStatus.PENDING
    profile: str = "auto"
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    
    # Reconnection tracking
    reconnect_attempts: int = 0
    last_reconnect_at: Optional[datetime] = None
    
    # Error tracking
    last_error: Optional[str] = None
    error_count: int = 0
    
    # Stats
    bytes_streamed: int = 0
    frames_sent: int = 0
    
    def mark_streaming(self) -> None:
        """Mark session as actively streaming."""
        self.status = StreamStatus.STREAMING
        self.started_at = datetime.utcnow()
        self.reconnect_attempts = 0
    
    def mark_reconnecting(self) -> None:
        """Mark session as reconnecting."""
        self.status = StreamStatus.RECONNECTING
        self.reconnect_attempts += 1
        self.last_reconnect_at = datetime.utcnow()
    
    def mark_error(self, error: str) -> None:
        """Mark session with an error."""
        self.status = StreamStatus.ERROR
        self.last_error = error
        self.error_count += 1
    
    def mark_stopped(self) -> None:
        """Mark session as stopped."""
        self.status = StreamStatus.STOPPED
        self.stopped_at = datetime.utcnow()
    
    @property
    def duration_seconds(self) -> float:
        """Get streaming duration in seconds."""
        if not self.started_at:
            return 0.0
        end = self.stopped_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "source_url": self.source.url,
            "source_type": self.source.stream_type.value,
            "status": self.status.value,
            "profile": self.profile,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "duration_seconds": self.duration_seconds,
            "reconnect_attempts": self.reconnect_attempts,
            "last_error": self.last_error,
            "error_count": self.error_count,
            "bytes_streamed": self.bytes_streamed,
            "frames_sent": self.frames_sent,
        }
