"""FastAPI REST API for Telegram Streamer."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response

from telegram_streamer import __version__
from telegram_streamer.config import TranscodeProfile, get_settings
from telegram_streamer.exceptions import (
    ChatNotFoundError,
    PermissionError,
    StreamConnectionError,
    StreamSourceError,
    TelegramStreamerError,
)
from telegram_streamer.logging_config import setup_logging, get_logger
from telegram_streamer.streamer import get_streamer

# Prometheus metrics
STREAM_STARTS = Counter(
    "telegram_streamer_stream_starts_total",
    "Total number of stream starts",
    ["profile", "source_type"],
)
STREAM_STOPS = Counter(
    "telegram_streamer_stream_stops_total",
    "Total number of stream stops",
    ["reason"],
)
STREAM_ERRORS = Counter(
    "telegram_streamer_stream_errors_total",
    "Total number of stream errors",
    ["error_type"],
)
ACTIVE_STREAMS = Gauge(
    "telegram_streamer_active_streams",
    "Number of currently active streams",
)
RECONNECTION_ATTEMPTS = Counter(
    "telegram_streamer_reconnection_attempts_total",
    "Total reconnection attempts",
)
STREAM_DURATION = Histogram(
    "telegram_streamer_stream_duration_seconds",
    "Stream duration in seconds",
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400, 28800],
)

logger = get_logger(__name__)


# Request/Response models
class StartStreamRequest(BaseModel):
    """Request to start a new stream."""
    
    chat: str = Field(
        ...,
        description="Target chat (ID, username, or invite link)",
        examples=["@mychannel", "-1001234567890"],
    )
    source: str = Field(
        ...,
        description="Stream source URL (M3U/M3U8/HLS/RTMP/YouTube)",
        examples=["https://example.com/stream.m3u8", "rtmp://server/live/key"],
    )
    profile: str = Field(
        default="auto",
        description="Transcode profile: auto, 480p, 720p, 1080p",
    )


class StreamResponse(BaseModel):
    """Stream session response."""
    
    id: str
    chat_id: int
    source_url: str
    source_type: str
    status: str
    profile: str
    created_at: str
    started_at: Optional[str]
    stopped_at: Optional[str]
    duration_seconds: float
    reconnect_attempts: int
    last_error: Optional[str]
    error_count: int


class StreamListResponse(BaseModel):
    """List of streams response."""
    
    streams: list[StreamResponse]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    version: str
    uptime_seconds: float
    telegram_connected: bool
    active_streams: int


class ErrorResponse(BaseModel):
    """Error response."""
    
    error: str
    detail: Optional[str] = None


# Application state
class AppState:
    """Application state container."""
    
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.streamer_started = False


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    logger.info("Starting Telegram Streamer API", version=__version__)
    
    # Start the streamer
    try:
        streamer = await get_streamer()
        await streamer.start()
        app_state.streamer_started = True
        logger.info("Streamer initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize streamer", error=str(e))
        # Continue without streamer - health check will show not connected
    
    yield
    
    # Shutdown
    logger.info("Shutting down Telegram Streamer API")
    if app_state.streamer_started:
        streamer = await get_streamer()
        await streamer.stop()


# Create FastAPI app
app = FastAPI(
    title="Telegram Streamer API",
    description="Production-ready API for streaming video to Telegram group/channel video chats",
    version=__version__,
    lifespan=lifespan,
)


# Exception handlers
@app.exception_handler(TelegramStreamerError)
async def telegram_streamer_error_handler(request, exc: TelegramStreamerError):
    """Handle Telegram Streamer errors."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    
    if isinstance(exc, ChatNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, PermissionError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (StreamSourceError, StreamConnectionError)):
        status_code = status.HTTP_400_BAD_REQUEST
    
    STREAM_ERRORS.labels(error_type=type(exc).__name__).inc()
    
    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


# Health endpoints
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check endpoint",
)
async def health():
    """Check API and streamer health status."""
    uptime = (datetime.utcnow() - app_state.start_time).total_seconds()
    
    streamer = await get_streamer()
    active_count = len(streamer.get_active_sessions())
    
    return HealthResponse(
        status="healthy" if streamer.is_started else "degraded",
        version=__version__,
        uptime_seconds=uptime,
        telegram_connected=streamer.is_started,
        active_streams=active_count,
    )


@app.get(
    "/metrics",
    tags=["Health"],
    summary="Prometheus metrics endpoint",
)
async def metrics():
    """Export Prometheus metrics."""
    # Update active streams gauge
    streamer = await get_streamer()
    ACTIVE_STREAMS.set(len(streamer.get_active_sessions()))
    
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# Stream management endpoints
@app.post(
    "/api/streams",
    response_model=StreamResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Streams"],
    summary="Start a new stream",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Chat not found"},
    },
)
async def start_stream(request: StartStreamRequest):
    """Start streaming to a Telegram video chat.
    
    **Supported sources:**
    - M3U/M3U8 playlists
    - HLS streams
    - RTMP streams
    - YouTube Live (requires yt-dlp)
    - Direct video file URLs
    
    **Transcode profiles:**
    - `auto`: Copy stream without transcoding (best quality, lowest CPU)
    - `480p`: 854x480, 1.5 Mbps
    - `720p`: 1280x720, 3 Mbps
    - `1080p`: 1920x1080, 5 Mbps
    """
    # Validate profile
    try:
        profile = TranscodeProfile(request.profile.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile: {request.profile}. Use: auto, 480p, 720p, 1080p",
        )
    
    streamer = await get_streamer()
    
    if not streamer.is_started:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Streamer not initialized. Check Telegram credentials.",
        )
    
    session = await streamer.start_stream(request.chat, request.source, profile)
    
    # Update metrics
    STREAM_STARTS.labels(
        profile=profile.value,
        source_type=session.source.stream_type.value,
    ).inc()
    
    return StreamResponse(**session.to_dict())


@app.get(
    "/api/streams",
    response_model=StreamListResponse,
    tags=["Streams"],
    summary="List all streams",
)
async def list_streams(
    active_only: bool = False,
):
    """List all streaming sessions.
    
    Set `active_only=true` to only show currently active streams.
    """
    streamer = await get_streamer()
    
    if active_only:
        sessions = streamer.get_active_sessions()
    else:
        sessions = streamer.get_all_sessions()
    
    streams = [StreamResponse(**s.to_dict()) for s in sessions]
    
    return StreamListResponse(streams=streams, count=len(streams))


@app.get(
    "/api/streams/{session_id}",
    response_model=StreamResponse,
    tags=["Streams"],
    summary="Get stream details",
    responses={
        404: {"model": ErrorResponse, "description": "Stream not found"},
    },
)
async def get_stream(session_id: str):
    """Get details of a specific streaming session."""
    streamer = await get_streamer()
    session = streamer.get_session(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stream not found: {session_id}",
        )
    
    return StreamResponse(**session.to_dict())


@app.delete(
    "/api/streams/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Streams"],
    summary="Stop a stream",
    responses={
        404: {"model": ErrorResponse, "description": "Stream not found"},
    },
)
async def stop_stream(session_id: str):
    """Stop a streaming session."""
    streamer = await get_streamer()
    session = streamer.get_session(session_id)
    
    if session:
        STREAM_DURATION.observe(session.duration_seconds)
    
    success = await streamer.stop_stream(session_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stream not found: {session_id}",
        )
    
    STREAM_STOPS.labels(reason="manual").inc()


@app.post(
    "/api/streams/{session_id}/pause",
    response_model=StreamResponse,
    tags=["Streams"],
    summary="Pause a stream",
    responses={
        404: {"model": ErrorResponse, "description": "Stream not found"},
        409: {"model": ErrorResponse, "description": "Stream not in pausable state"},
    },
)
async def pause_stream(session_id: str):
    """Pause an active stream."""
    streamer = await get_streamer()
    success = await streamer.pause_stream(session_id)
    
    if not success:
        session = streamer.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stream not found: {session_id}",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stream not in pausable state: {session.status.value}",
        )
    
    session = streamer.get_session(session_id)
    return StreamResponse(**session.to_dict())


@app.post(
    "/api/streams/{session_id}/resume",
    response_model=StreamResponse,
    tags=["Streams"],
    summary="Resume a paused stream",
    responses={
        404: {"model": ErrorResponse, "description": "Stream not found"},
        409: {"model": ErrorResponse, "description": "Stream not paused"},
    },
)
async def resume_stream(session_id: str):
    """Resume a paused stream."""
    streamer = await get_streamer()
    success = await streamer.resume_stream(session_id)
    
    if not success:
        session = streamer.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stream not found: {session_id}",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stream not paused: {session.status.value}",
        )
    
    session = streamer.get_session(session_id)
    return StreamResponse(**session.to_dict())
