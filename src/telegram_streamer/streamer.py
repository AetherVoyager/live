"""Core Telegram client and streaming functionality using Hydrogram + PyTgCalls."""

import asyncio
import uuid
from typing import Callable, Optional

from hydrogram import Client
from hydrogram.errors import (
    AuthKeyUnregistered,
    ChatAdminRequired,
    ChannelPrivate,
    PeerIdInvalid,
    UserNotParticipant,
)
from pytgcalls import PyTgCalls
from pytgcalls.types import (
    AudioQuality,
    VideoQuality,
    MediaStream,
)

from telegram_streamer.config import TranscodeProfile, get_settings
from telegram_streamer.exceptions import (
    AuthenticationError,
    ChatNotFoundError,
    PermissionError,
    StreamConnectionError,
    StreamSourceError,
)
from telegram_streamer.ffmpeg import FFmpegWrapper, resolve_youtube_url
from telegram_streamer.logging_config import get_logger
from telegram_streamer.models import (
    StreamSession,
    StreamSource,
    StreamStatus,
    StreamType,
)

logger = get_logger(__name__)


class TelegramStreamer:
    """Main Telegram streaming client using Pyrogram and PyTgCalls."""

    def __init__(self):
        """Initialize the Telegram streamer."""
        self.settings = get_settings()
        self._client: Optional[Client] = None
        self._tgcalls: Optional[PyTgCalls] = None
        self._sessions: dict[str, StreamSession] = {}
        self._ffmpeg_processes: dict[str, FFmpegWrapper] = {}
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._started = False
        
        # Event callbacks
        self._on_stream_end: Optional[Callable[[str], None]] = None
        self._on_stream_error: Optional[Callable[[str, str], None]] = None

    async def start(self) -> None:
        """Start the Telegram client and PyTgCalls.
        
        Raises:
            AuthenticationError: If authentication fails
        """
        if self._started:
            logger.warning("Streamer already started")
            return

        logger.info("Starting Telegram streamer", bot_mode=self.settings.is_bot_mode)

        try:
            # Initialize Pyrogram client
            if self.settings.is_bot_mode:
                self._client = Client(
                    name=str(self.settings.session_file),
                    api_id=self.settings.api_id,
                    api_hash=self.settings.api_hash,
                    bot_token=self.settings.bot_token,
                )
            else:
                self._client = Client(
                    name=str(self.settings.session_file),
                    api_id=self.settings.api_id,
                    api_hash=self.settings.api_hash,
                    phone_number=self.settings.phone_number,
                )

            # Start Pyrogram
            await self._client.start()
            me = await self._client.get_me()
            logger.info(
                "Pyrogram connected",
                user_id=me.id,
                username=me.username,
                is_bot=me.is_bot,
            )

            # Initialize PyTgCalls
            self._tgcalls = PyTgCalls(self._client)
            await self._tgcalls.start()
            logger.info("PyTgCalls started")

            self._started = True

        except AuthKeyUnregistered:
            raise AuthenticationError("Session expired. Please re-authenticate.")
        except Exception as e:
            logger.error("Failed to start streamer", error=str(e))
            await self.stop()
            raise AuthenticationError(f"Authentication failed: {e}")

    async def stop(self) -> None:
        """Stop the streamer and cleanup all sessions."""
        logger.info("Stopping Telegram streamer")

        # Stop all active streams
        for session_id in list(self._sessions.keys()):
            await self.stop_stream(session_id)

        # Stop reconnect tasks
        for task in self._reconnect_tasks.values():
            task.cancel()
        self._reconnect_tasks.clear()

        # Stop PyTgCalls
        if self._tgcalls:
            try:
                await self._tgcalls.stop()
            except Exception as e:
                logger.warning("Error stopping PyTgCalls", error=str(e))
            self._tgcalls = None

        # Stop Pyrogram
        if self._client:
            try:
                await self._client.stop()
            except Exception as e:
                logger.warning("Error stopping Pyrogram", error=str(e))
            self._client = None

        self._started = False
        logger.info("Telegram streamer stopped")

    async def _resolve_chat_id(self, chat_identifier: str | int) -> int:
        """Resolve chat identifier to numeric ID.
        
        Args:
            chat_identifier: Chat ID, username, or invite link
            
        Returns:
            Numeric chat ID
            
        Raises:
            ChatNotFoundError: If chat cannot be found
        """
        if not self._client:
            raise StreamConnectionError("Client not started")

        try:
            if isinstance(chat_identifier, int):
                return chat_identifier
            
            # Handle usernames and invite links
            chat = await self._client.get_chat(chat_identifier)
            return chat.id
            
        except (PeerIdInvalid, ChannelPrivate) as e:
            raise ChatNotFoundError(f"Chat not found: {chat_identifier}")
        except Exception as e:
            raise ChatNotFoundError(f"Error resolving chat: {e}")

    async def _prepare_stream_url(self, source: StreamSource) -> str:
        """Prepare the stream URL (resolve YouTube, validate, etc.).
        
        Args:
            source: Stream source
            
        Returns:
            Ready-to-use stream URL
        """
        if source.stream_type == StreamType.YOUTUBE:
            logger.info("Resolving YouTube URL", url=source.url)
            return await resolve_youtube_url(source.url)
        
        return source.url

    async def start_stream(
        self,
        chat_identifier: str | int,
        source_url: str,
        profile: TranscodeProfile = TranscodeProfile.AUTO,
    ) -> StreamSession:
        """Start streaming to a Telegram video chat.
        
        Args:
            chat_identifier: Chat ID, username, or invite link
            source_url: Stream source URL
            profile: Transcode profile to use
            
        Returns:
            StreamSession object
            
        Raises:
            StreamConnectionError: If connection fails
            StreamSourceError: If source is invalid
            PermissionError: If insufficient permissions
        """
        if not self._started:
            raise StreamConnectionError("Streamer not started")

        # Resolve chat ID
        chat_id = await self._resolve_chat_id(chat_identifier)

        # Check if already streaming to this chat
        for session in self._sessions.values():
            if session.chat_id == chat_id and session.status in (
                StreamStatus.STREAMING,
                StreamStatus.CONNECTING,
                StreamStatus.RECONNECTING,
            ):
                raise StreamConnectionError(
                    f"Already streaming to chat {chat_id}"
                )

        # Create session
        session_id = str(uuid.uuid4())[:8]
        source = StreamSource.detect_type(source_url)
        session = StreamSession(
            id=session_id,
            chat_id=chat_id,
            source=source,
            profile=profile.value,
        )
        self._sessions[session_id] = session
        
        logger.info(
            "Starting stream",
            session_id=session_id,
            chat_id=chat_id,
            source_type=source.stream_type.value,
            profile=profile.value,
        )

        try:
            session.status = StreamStatus.CONNECTING

            # Prepare stream URL (resolve YouTube, etc.)
            stream_url = await self._prepare_stream_url(source)
            
            # Map profile to PyTgCalls quality
            video_quality = self._map_video_quality(profile)
            
            # Create media stream
            media_stream = MediaStream(
                stream_url,
                video_flags=MediaStream.Flags.AUTO_DETECT,
                audio_flags=MediaStream.Flags.AUTO_DETECT,
            )

            # Join video chat
            await self._tgcalls.play(
                chat_id,
                media_stream,
            )

            session.mark_streaming()
            logger.info(
                "Stream started successfully",
                session_id=session_id,
                chat_id=chat_id,
            )

            return session

        except (ChatAdminRequired, UserNotParticipant) as e:
            session.mark_error(str(e))
            raise PermissionError(
                "Insufficient permissions to join video chat. "
                "Ensure the account/bot has permission to manage video chats."
            )
        except Exception as e:
            session.mark_error(str(e))
            logger.error(
                "Failed to start stream",
                session_id=session_id,
                error=str(e),
            )
            raise StreamConnectionError(f"Failed to start stream: {e}")

    async def stop_stream(self, session_id: str) -> bool:
        """Stop an active stream.
        
        Args:
            session_id: Session ID to stop
            
        Returns:
            True if stopped, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning("Session not found", session_id=session_id)
            return False

        logger.info("Stopping stream", session_id=session_id, chat_id=session.chat_id)

        # Cancel reconnect task if running
        if session_id in self._reconnect_tasks:
            self._reconnect_tasks[session_id].cancel()
            del self._reconnect_tasks[session_id]

        # Stop FFmpeg if running
        if session_id in self._ffmpeg_processes:
            await self._ffmpeg_processes[session_id].stop()
            del self._ffmpeg_processes[session_id]

        # Leave video chat
        if self._tgcalls:
            try:
                await self._tgcalls.leave_call(session.chat_id)
            except Exception as e:
                logger.warning(
                    "Error leaving call",
                    session_id=session_id,
                    error=str(e),
                )

        session.mark_stopped()
        logger.info("Stream stopped", session_id=session_id)
        
        return True

    async def pause_stream(self, session_id: str) -> bool:
        """Pause an active stream.
        
        Args:
            session_id: Session ID to pause
            
        Returns:
            True if paused, False if not found
        """
        session = self._sessions.get(session_id)
        if not session or session.status != StreamStatus.STREAMING:
            return False

        if self._tgcalls:
            try:
                await self._tgcalls.pause_stream(session.chat_id)
                session.status = StreamStatus.PAUSED
                logger.info("Stream paused", session_id=session_id)
                return True
            except Exception as e:
                logger.error("Failed to pause stream", error=str(e))
        
        return False

    async def resume_stream(self, session_id: str) -> bool:
        """Resume a paused stream.
        
        Args:
            session_id: Session ID to resume
            
        Returns:
            True if resumed, False if not found
        """
        session = self._sessions.get(session_id)
        if not session or session.status != StreamStatus.PAUSED:
            return False

        if self._tgcalls:
            try:
                await self._tgcalls.resume_stream(session.chat_id)
                session.status = StreamStatus.STREAMING
                logger.info("Stream resumed", session_id=session_id)
                return True
            except Exception as e:
                logger.error("Failed to resume stream", error=str(e))
        
        return False

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get a session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            StreamSession or None
        """
        return self._sessions.get(session_id)

    def get_all_sessions(self) -> list[StreamSession]:
        """Get all sessions.
        
        Returns:
            List of all sessions
        """
        return list(self._sessions.values())

    def get_active_sessions(self) -> list[StreamSession]:
        """Get all active streaming sessions.
        
        Returns:
            List of active sessions
        """
        return [
            s for s in self._sessions.values()
            if s.status in (StreamStatus.STREAMING, StreamStatus.PAUSED, StreamStatus.RECONNECTING)
        ]

    def _map_video_quality(self, profile: TranscodeProfile) -> VideoQuality:
        """Map transcode profile to PyTgCalls VideoQuality.
        
        Args:
            profile: Transcode profile
            
        Returns:
            VideoQuality enum value
        """
        mapping = {
            TranscodeProfile.AUTO: VideoQuality.HD_720p,
            TranscodeProfile.P480: VideoQuality.SD_480p,
            TranscodeProfile.P720: VideoQuality.HD_720p,
            TranscodeProfile.P1080: VideoQuality.FHD_1080p,
        }
        return mapping.get(profile, VideoQuality.HD_720p)

    @property
    def is_started(self) -> bool:
        """Check if streamer is started."""
        return self._started

    @property
    def client(self) -> Optional[Client]:
        """Get Pyrogram client."""
        return self._client

    @property
    def tgcalls(self) -> Optional[PyTgCalls]:
        """Get PyTgCalls instance."""
        return self._tgcalls


# Global streamer instance
_streamer: Optional[TelegramStreamer] = None


async def get_streamer() -> TelegramStreamer:
    """Get or create the global streamer instance.
    
    Returns:
        TelegramStreamer instance
    """
    global _streamer
    if _streamer is None:
        _streamer = TelegramStreamer()
    return _streamer
