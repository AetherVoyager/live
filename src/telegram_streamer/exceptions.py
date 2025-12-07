"""Custom exceptions for Telegram Streamer."""


class TelegramStreamerError(Exception):
    """Base exception for all Telegram Streamer errors."""
    pass


class ConfigurationError(TelegramStreamerError):
    """Configuration-related errors."""
    pass


class AuthenticationError(TelegramStreamerError):
    """Telegram authentication errors."""
    pass


class StreamError(TelegramStreamerError):
    """Base streaming error."""
    pass


class StreamSourceError(StreamError):
    """Error with stream source (invalid URL, unavailable, etc.)."""
    pass


class StreamConnectionError(StreamError):
    """Error connecting to Telegram voice/video chat."""
    pass


class StreamTranscodeError(StreamError):
    """FFmpeg transcoding error."""
    pass


class ReconnectionError(StreamError):
    """Failed to reconnect after maximum attempts."""
    pass


class ChatNotFoundError(StreamError):
    """Target chat/group/channel not found."""
    pass


class PermissionError(StreamError):
    """Insufficient permissions to join or stream."""
    pass


class FFmpegError(TelegramStreamerError):
    """FFmpeg-related errors."""
    pass


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg binary not found."""
    pass


class FFmpegProcessError(FFmpegError):
    """FFmpeg process failed."""
    
    def __init__(self, message: str, returncode: int | None = None, stderr: str | None = None):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
