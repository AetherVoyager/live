"""Tests for FFmpeg wrapper."""

import asyncio
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_streamer.config import TranscodeProfile
from telegram_streamer.exceptions import (
    FFmpegError,
    FFmpegNotFoundError,
    FFmpegProcessError,
    StreamSourceError,
)
from telegram_streamer.ffmpeg import FFmpegWrapper, resolve_youtube_url
from telegram_streamer.models import StreamSource, StreamType


class TestFFmpegWrapper:
    """Tests for FFmpegWrapper class."""
    
    @pytest.fixture
    def hls_source(self):
        """Create HLS source for testing."""
        return StreamSource(
            url="https://example.com/live/stream.m3u8",
            stream_type=StreamType.HLS,
        )
    
    @pytest.fixture
    def rtmp_source(self):
        """Create RTMP source for testing."""
        return StreamSource(
            url="rtmp://server/live/key",
            stream_type=StreamType.RTMP,
        )
    
    def test_check_ffmpeg_available(self):
        """Test checking if FFmpeg is available."""
        with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
            assert FFmpegWrapper.check_ffmpeg() is True
    
    def test_check_ffmpeg_not_available(self):
        """Test checking when FFmpeg is not available."""
        with patch.object(shutil, "which", return_value=None):
            assert FFmpegWrapper.check_ffmpeg() is False
    
    @pytest.mark.asyncio
    async def test_get_ffmpeg_version(self):
        """Test getting FFmpeg version."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"ffmpeg version 6.0 Copyright...\n", b"")
        )
        
        with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                version = await FFmpegWrapper.get_ffmpeg_version()
                assert "ffmpeg version 6.0" in version
    
    @pytest.mark.asyncio
    async def test_get_ffmpeg_version_not_found(self):
        """Test getting version when FFmpeg not found."""
        with patch.object(shutil, "which", return_value=None):
            with pytest.raises(FFmpegNotFoundError):
                await FFmpegWrapper.get_ffmpeg_version()
    
    def test_build_command_auto_profile(self, hls_source, mock_settings):
        """Test building FFmpeg command with auto profile."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
            cmd = wrapper.build_command()
            
            assert "ffmpeg" in cmd
            assert "-i" in cmd
            assert hls_source.url in cmd
            assert "-c:v" in cmd
            assert "copy" in cmd  # Auto uses copy
    
    def test_build_command_720p_profile(self, hls_source, mock_settings):
        """Test building FFmpeg command with 720p profile."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            wrapper = FFmpegWrapper(hls_source, TranscodeProfile.P720)
            cmd = wrapper.build_command()
            
            assert "ffmpeg" in cmd
            assert "-c:v" in cmd
            assert "libx264" in cmd
            assert "1280:720" in " ".join(cmd)
            assert "3000k" in cmd
    
    def test_build_command_hls_reconnect_options(self, hls_source, mock_settings):
        """Test HLS sources include reconnection options."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
            cmd = wrapper.build_command()
            
            assert "-reconnect" in cmd
            assert "-reconnect_streamed" in cmd
    
    def test_build_command_rtmp_options(self, rtmp_source, mock_settings):
        """Test RTMP sources include RTMP-specific options."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            wrapper = FFmpegWrapper(rtmp_source, TranscodeProfile.AUTO)
            cmd = wrapper.build_command()
            
            assert "-rtmp_live" in cmd
            assert "live" in cmd
    
    def test_build_command_output_format(self, hls_source, mock_settings):
        """Test output format is MPEG-TS."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
            cmd = wrapper.build_command()
            
            assert "-f" in cmd
            assert "mpegts" in cmd
    
    @pytest.mark.asyncio
    async def test_start_ffmpeg_not_found(self, hls_source, mock_settings):
        """Test starting FFmpeg when not found."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            with patch.object(shutil, "which", return_value=None):
                wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
                
                with pytest.raises(FFmpegNotFoundError):
                    await wrapper.start()
    
    @pytest.mark.asyncio
    async def test_start_ffmpeg_success(self, hls_source, mock_settings, mock_ffmpeg_process):
        """Test starting FFmpeg successfully."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
                with patch("asyncio.create_subprocess_exec", return_value=mock_ffmpeg_process):
                    wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
                    process = await wrapper.start()
                    
                    assert process is not None
                    assert wrapper.is_running is True
    
    @pytest.mark.asyncio
    async def test_stop_ffmpeg(self, hls_source, mock_settings, mock_ffmpeg_process):
        """Test stopping FFmpeg process."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
                with patch("asyncio.create_subprocess_exec", return_value=mock_ffmpeg_process):
                    wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
                    await wrapper.start()
                    await wrapper.stop()
                    
                    mock_ffmpeg_process.terminate.assert_called_once()
                    assert wrapper.is_running is False
    
    @pytest.mark.asyncio
    async def test_read_stream(self, hls_source, mock_settings, mock_ffmpeg_process):
        """Test reading stream data from FFmpeg."""
        # Setup mock to return data then empty
        mock_ffmpeg_process.stdout.read = AsyncMock(
            side_effect=[b"chunk1", b"chunk2", b""]
        )
        
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            with patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"):
                with patch("asyncio.create_subprocess_exec", return_value=mock_ffmpeg_process):
                    wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
                    await wrapper.start()
                    
                    chunks = []
                    async for chunk in wrapper.read_stream():
                        chunks.append(chunk)
                    
                    assert len(chunks) == 2
                    assert chunks[0] == b"chunk1"
                    assert chunks[1] == b"chunk2"
    
    @pytest.mark.asyncio
    async def test_read_stream_without_start_raises_error(self, hls_source, mock_settings):
        """Test reading stream without starting raises error."""
        with patch("telegram_streamer.ffmpeg.get_settings", return_value=mock_settings):
            wrapper = FFmpegWrapper(hls_source, TranscodeProfile.AUTO)
            
            with pytest.raises(FFmpegError):
                async for _ in wrapper.read_stream():
                    pass


class TestResolveYoutubeUrl:
    """Tests for YouTube URL resolution."""
    
    @pytest.mark.asyncio
    async def test_resolve_youtube_url_success(self):
        """Test resolving YouTube URL successfully."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"https://manifest.googlevideo.com/stream.m3u8\n", b"")
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(
                b"https://manifest.googlevideo.com/stream.m3u8\n", b""
            )):
                mock_process.communicate = AsyncMock(
                    return_value=(b"https://manifest.googlevideo.com/stream.m3u8\n", b"")
                )
                
                url = await resolve_youtube_url("https://youtube.com/watch?v=test")
                assert "googlevideo.com" in url
    
    @pytest.mark.asyncio
    async def test_resolve_youtube_url_not_found(self):
        """Test resolving YouTube URL when yt-dlp not found."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(StreamSourceError, match="yt-dlp not found"):
                await resolve_youtube_url("https://youtube.com/watch?v=test")
    
    @pytest.mark.asyncio
    async def test_resolve_youtube_url_timeout(self):
        """Test resolving YouTube URL timeout."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock()
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with pytest.raises(StreamSourceError, match="timed out"):
                    await resolve_youtube_url("https://youtube.com/watch?v=test")
    
    @pytest.mark.asyncio
    async def test_resolve_youtube_url_yt_dlp_error(self):
        """Test resolving YouTube URL when yt-dlp fails."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"ERROR: Video not found")
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"", b"ERROR: Video not found")):
                mock_process.communicate = AsyncMock(
                    return_value=(b"", b"ERROR: Video not found")
                )
                
                with pytest.raises(StreamSourceError, match="yt-dlp failed"):
                    await resolve_youtube_url("https://youtube.com/watch?v=invalid")
