"""FFmpeg wrapper for transcoding streams."""

import asyncio
import shutil
import signal
from pathlib import Path
from typing import AsyncIterator, Optional

from telegram_streamer.config import TranscodeProfile, get_settings
from telegram_streamer.exceptions import (
    FFmpegError,
    FFmpegNotFoundError,
    FFmpegProcessError,
)
from telegram_streamer.logging_config import get_logger
from telegram_streamer.models import StreamSource, StreamType, TranscodeSettings

logger = get_logger(__name__)


class FFmpegWrapper:
    """Wrapper for FFmpeg transcoding operations."""

    def __init__(
        self,
        source: StreamSource,
        profile: TranscodeProfile = TranscodeProfile.AUTO,
    ):
        """Initialize FFmpeg wrapper.
        
        Args:
            source: Stream source to transcode
            profile: Transcode profile to use
        """
        self.source = source
        self.profile = profile
        self.settings = get_settings()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False

    @staticmethod
    def check_ffmpeg(ffmpeg_path: str = "ffmpeg") -> bool:
        """Check if FFmpeg is available.
        
        Args:
            ffmpeg_path: Path to FFmpeg binary
            
        Returns:
            True if FFmpeg is available
        """
        return shutil.which(ffmpeg_path) is not None

    @staticmethod
    async def get_ffmpeg_version(ffmpeg_path: str = "ffmpeg") -> str:
        """Get FFmpeg version string.
        
        Args:
            ffmpeg_path: Path to FFmpeg binary
            
        Returns:
            FFmpeg version string
            
        Raises:
            FFmpegNotFoundError: If FFmpeg is not found
        """
        if not FFmpegWrapper.check_ffmpeg(ffmpeg_path):
            raise FFmpegNotFoundError(f"FFmpeg not found at: {ffmpeg_path}")

        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        first_line = stdout.decode().split("\n")[0]
        return first_line

    def _build_input_args(self) -> list[str]:
        """Build FFmpeg input arguments based on source type.
        
        Returns:
            List of input arguments
        """
        args = []
        
        # Reconnection options for network streams
        if self.source.stream_type in (StreamType.HLS, StreamType.M3U8, StreamType.M3U):
            args.extend([
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
            ])
        
        # RTMP specific options
        if self.source.stream_type == StreamType.RTMP:
            args.extend([
                "-rtmp_live", "live",
            ])
        
        # Common input options
        args.extend([
            "-analyzeduration", "5000000",  # 5 seconds
            "-probesize", "5000000",
            "-fflags", "+genpts+discardcorrupt",
            "-i", self.source.url,
        ])
        
        return args

    def _build_video_args(self) -> list[str]:
        """Build FFmpeg video encoding arguments.
        
        Returns:
            List of video arguments
        """
        args = []
        
        transcode_settings = TranscodeSettings.get_profile(self.profile.value)
        
        if transcode_settings:
            # Specific profile - transcode
            args.extend([
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-vf", f"scale={transcode_settings.width}:{transcode_settings.height}",
                "-b:v", transcode_settings.video_bitrate,
                "-maxrate", transcode_settings.video_bitrate,
                "-bufsize", f"{int(transcode_settings.video_bitrate[:-1]) * 2}k",
                "-r", str(transcode_settings.fps),
                "-g", str(transcode_settings.fps * 2),  # Keyframe every 2 seconds
                "-pix_fmt", "yuv420p",
            ])
        else:
            # Auto mode - copy if possible, otherwise transcode
            args.extend([
                "-c:v", "copy",
            ])
        
        return args

    def _build_audio_args(self) -> list[str]:
        """Build FFmpeg audio encoding arguments.
        
        Returns:
            List of audio arguments
        """
        transcode_settings = TranscodeSettings.get_profile(self.profile.value)
        
        if transcode_settings:
            return [
                "-c:a", "aac",
                "-b:a", transcode_settings.audio_bitrate,
                "-ar", "48000",
                "-ac", "2",
            ]
        else:
            return [
                "-c:a", "copy",
            ]

    def _build_output_args(self, output: str = "pipe:1") -> list[str]:
        """Build FFmpeg output arguments.
        
        Args:
            output: Output destination (pipe or file)
            
        Returns:
            List of output arguments
        """
        return [
            "-f", "mpegts",  # MPEG-TS container for piping
            "-flush_packets", "1",
            output,
        ]

    def build_command(self, output: str = "pipe:1") -> list[str]:
        """Build complete FFmpeg command.
        
        Args:
            output: Output destination
            
        Returns:
            Complete FFmpeg command as list
        """
        cmd = [self.settings.ffmpeg_path]
        
        # Global options
        cmd.extend([
            "-y",  # Overwrite output
            "-hide_banner",
            "-loglevel", "warning",
            "-threads", str(self.settings.ffmpeg_threads),
        ])
        
        # Input
        cmd.extend(self._build_input_args())
        
        # Video
        cmd.extend(self._build_video_args())
        
        # Audio
        cmd.extend(self._build_audio_args())
        
        # Output
        cmd.extend(self._build_output_args(output))
        
        return cmd

    async def start(self) -> asyncio.subprocess.Process:
        """Start FFmpeg process.
        
        Returns:
            FFmpeg subprocess
            
        Raises:
            FFmpegNotFoundError: If FFmpeg is not found
            FFmpegProcessError: If process fails to start
        """
        if not self.check_ffmpeg(self.settings.ffmpeg_path):
            raise FFmpegNotFoundError(
                f"FFmpeg not found at: {self.settings.ffmpeg_path}"
            )

        cmd = self.build_command()
        logger.info("Starting FFmpeg", command=" ".join(cmd))

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )
            self._running = True
            logger.info("FFmpeg started", pid=self._process.pid)
            return self._process
        except Exception as e:
            raise FFmpegProcessError(f"Failed to start FFmpeg: {e}")

    async def read_stream(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Read transcoded stream data.
        
        Args:
            chunk_size: Size of chunks to read
            
        Yields:
            Chunks of transcoded data
        """
        if not self._process or not self._process.stdout:
            raise FFmpegError("FFmpeg process not started")

        while self._running:
            try:
                chunk = await self._process.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error reading FFmpeg stream", error=str(e))
                break

    async def stop(self) -> None:
        """Stop FFmpeg process gracefully."""
        self._running = False
        
        if self._process:
            logger.info("Stopping FFmpeg", pid=self._process.pid)
            
            try:
                # Try graceful termination first
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Force kill if graceful termination fails
                    logger.warning("FFmpeg did not terminate, killing")
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass  # Process already dead
            
            self._process = None
            logger.info("FFmpeg stopped")

    async def get_stderr(self) -> str:
        """Get FFmpeg stderr output.
        
        Returns:
            Stderr content
        """
        if self._process and self._process.stderr:
            stderr = await self._process.stderr.read()
            return stderr.decode()
        return ""

    @property
    def is_running(self) -> bool:
        """Check if FFmpeg process is running."""
        return (
            self._running
            and self._process is not None
            and self._process.returncode is None
        )


async def resolve_youtube_url(url: str) -> str:
    """Resolve YouTube URL to direct stream URL using yt-dlp.
    
    Args:
        url: YouTube video/stream URL
        
    Returns:
        Direct stream URL
        
    Raises:
        StreamSourceError: If URL cannot be resolved
    """
    from telegram_streamer.exceptions import StreamSourceError
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--get-url",
            "-f", "best[ext=mp4]/best",
            "--no-playlist",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        
        if proc.returncode != 0:
            raise StreamSourceError(
                f"yt-dlp failed: {stderr.decode()}"
            )
        
        direct_url = stdout.decode().strip().split("\n")[0]
        if not direct_url:
            raise StreamSourceError("No stream URL found")
            
        return direct_url
    except asyncio.TimeoutError:
        raise StreamSourceError("yt-dlp timed out")
    except FileNotFoundError:
        raise StreamSourceError("yt-dlp not found")
