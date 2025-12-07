"""Automatic reconnection logic with exponential backoff."""

import asyncio
from datetime import datetime
from typing import Callable, Optional

from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    retry_if_exception_type,
)

from telegram_streamer.config import get_settings
from telegram_streamer.exceptions import (
    ReconnectionError,
    StreamConnectionError,
    StreamSourceError,
)
from telegram_streamer.logging_config import get_logger
from telegram_streamer.models import StreamSession, StreamStatus

logger = get_logger(__name__)


class ReconnectionManager:
    """Manages automatic reconnection for stream sessions."""

    def __init__(
        self,
        start_stream_func: Callable,
        stop_stream_func: Callable,
    ):
        """Initialize reconnection manager.
        
        Args:
            start_stream_func: Async function to start a stream
            stop_stream_func: Async function to stop a stream
        """
        self.settings = get_settings()
        self._start_stream = start_stream_func
        self._stop_stream = stop_stream_func
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._active = True

    async def handle_disconnect(
        self,
        session: StreamSession,
        error: Optional[str] = None,
    ) -> None:
        """Handle a stream disconnection event.
        
        Args:
            session: The disconnected session
            error: Optional error message
        """
        if not self.settings.reconnect_enabled:
            logger.info(
                "Reconnection disabled, marking session as error",
                session_id=session.id,
            )
            session.mark_error(error or "Disconnected")
            return

        if session.reconnect_attempts >= self.settings.reconnect_max_attempts:
            logger.error(
                "Max reconnection attempts reached",
                session_id=session.id,
                attempts=session.reconnect_attempts,
            )
            session.mark_error("Max reconnection attempts reached")
            return

        # Start reconnection task
        if session.id not in self._reconnect_tasks:
            task = asyncio.create_task(self._reconnect_loop(session))
            self._reconnect_tasks[session.id] = task

    async def _reconnect_loop(self, session: StreamSession) -> None:
        """Execute reconnection loop with exponential backoff.
        
        Args:
            session: Session to reconnect
        """
        session.mark_reconnecting()
        logger.info(
            "Starting reconnection",
            session_id=session.id,
            chat_id=session.chat_id,
            attempt=session.reconnect_attempts,
        )

        try:
            async for attempt in AsyncRetrying(
                stop=(
                    stop_after_attempt(self.settings.reconnect_max_attempts) |
                    stop_after_delay(self.settings.reconnect_timeout)
                ),
                wait=wait_exponential(
                    multiplier=1,
                    min=self.settings.reconnect_min_delay,
                    max=self.settings.reconnect_max_delay,
                ),
                retry=retry_if_exception_type((StreamConnectionError, StreamSourceError)),
                reraise=True,
            ):
                with attempt:
                    if not self._active:
                        raise ReconnectionError("Reconnection manager stopped")

                    session.reconnect_attempts = attempt.retry_state.attempt_number
                    session.last_reconnect_at = datetime.utcnow()

                    logger.info(
                        "Reconnection attempt",
                        session_id=session.id,
                        attempt=session.reconnect_attempts,
                    )

                    # Try to restart the stream
                    await self._start_stream(
                        session.chat_id,
                        session.source.url,
                        session.profile,
                    )

                    session.mark_streaming()
                    logger.info(
                        "Reconnection successful",
                        session_id=session.id,
                        attempts=session.reconnect_attempts,
                    )

        except RetryError as e:
            logger.error(
                "Reconnection failed after all attempts",
                session_id=session.id,
                attempts=session.reconnect_attempts,
            )
            session.mark_error("Reconnection failed after all attempts")
        except ReconnectionError as e:
            logger.warning(
                "Reconnection cancelled",
                session_id=session.id,
                reason=str(e),
            )
        except Exception as e:
            logger.error(
                "Unexpected reconnection error",
                session_id=session.id,
                error=str(e),
            )
            session.mark_error(str(e))
        finally:
            # Cleanup task reference
            if session.id in self._reconnect_tasks:
                del self._reconnect_tasks[session.id]

    async def cancel_reconnection(self, session_id: str) -> bool:
        """Cancel an active reconnection attempt.
        
        Args:
            session_id: Session ID to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        if session_id in self._reconnect_tasks:
            self._reconnect_tasks[session_id].cancel()
            try:
                await self._reconnect_tasks[session_id]
            except asyncio.CancelledError:
                pass
            del self._reconnect_tasks[session_id]
            logger.info("Reconnection cancelled", session_id=session_id)
            return True
        return False

    def is_reconnecting(self, session_id: str) -> bool:
        """Check if a session is currently reconnecting.
        
        Args:
            session_id: Session ID to check
            
        Returns:
            True if reconnecting
        """
        return session_id in self._reconnect_tasks

    async def stop(self) -> None:
        """Stop all reconnection attempts."""
        self._active = False
        
        for session_id in list(self._reconnect_tasks.keys()):
            await self.cancel_reconnection(session_id)
        
        logger.info("Reconnection manager stopped")


class HealthMonitor:
    """Monitors stream health and triggers reconnection when needed."""

    def __init__(
        self,
        reconnection_manager: ReconnectionManager,
        check_interval: int = 30,
    ):
        """Initialize health monitor.
        
        Args:
            reconnection_manager: ReconnectionManager instance
            check_interval: Health check interval in seconds
        """
        self.settings = get_settings()
        self._reconnection_manager = reconnection_manager
        self._check_interval = check_interval
        self._sessions: dict[str, StreamSession] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._active = False

    def register_session(self, session: StreamSession) -> None:
        """Register a session for health monitoring.
        
        Args:
            session: Session to monitor
        """
        self._sessions[session.id] = session
        logger.debug("Session registered for health monitoring", session_id=session.id)

    def unregister_session(self, session_id: str) -> None:
        """Unregister a session from health monitoring.
        
        Args:
            session_id: Session ID to unregister
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug("Session unregistered from health monitoring", session_id=session_id)

    async def start(self) -> None:
        """Start the health monitor."""
        if self._active:
            return

        self._active = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor started", interval=self._check_interval)

    async def stop(self) -> None:
        """Stop the health monitor."""
        self._active = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        logger.info("Health monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main health monitoring loop."""
        while self._active:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_all_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitor error", error=str(e))

    async def _check_all_sessions(self) -> None:
        """Check health of all registered sessions."""
        for session in list(self._sessions.values()):
            await self._check_session(session)

    async def _check_session(self, session: StreamSession) -> None:
        """Check health of a single session.
        
        Args:
            session: Session to check
        """
        # Skip sessions that are not streaming
        if session.status not in (StreamStatus.STREAMING, StreamStatus.PAUSED):
            return

        # TODO: Implement actual health checks
        # - Check FFmpeg process status
        # - Check PyTgCalls connection status
        # - Check stream data flow
        
        logger.debug(
            "Session health check",
            session_id=session.id,
            status=session.status.value,
            duration=session.duration_seconds,
        )
