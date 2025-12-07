"""CLI interface using Typer for Telegram Streamer."""

import asyncio
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from telegram_streamer import __version__
from telegram_streamer.config import TranscodeProfile, get_settings
from telegram_streamer.logging_config import setup_logging, get_logger

app = typer.Typer(
    name="tg-streamer",
    help="Production-ready Telegram streaming app for group/channel video chats",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"Telegram Streamer v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Telegram Streamer CLI - Stream video to Telegram group/channel video chats."""
    pass


@app.command()
def stream(
    chat: str = typer.Argument(
        ...,
        help="Target chat (ID, username, or invite link)",
    ),
    source: str = typer.Argument(
        ...,
        help="Stream source URL (M3U/M3U8/HLS/RTMP/YouTube)",
    ),
    profile: str = typer.Option(
        "auto",
        "--profile",
        "-p",
        help="Transcode profile: auto, 480p, 720p, 1080p",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging level: DEBUG, INFO, WARNING, ERROR",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Use JSON log format",
    ),
) -> None:
    """Start streaming to a Telegram video chat.
    
    Examples:
    
        tg-streamer stream @mychannel https://example.com/stream.m3u8
        
        tg-streamer stream -1001234567890 https://youtube.com/watch?v=xxx --profile 720p
        
        tg-streamer stream @mygroup rtmp://server/live/key --profile 1080p
    """
    from telegram_streamer.config import LogLevel
    
    # Setup logging
    try:
        level = LogLevel(log_level.upper())
    except ValueError:
        console.print(f"[red]Invalid log level: {log_level}[/red]")
        raise typer.Exit(1)
    
    setup_logging(level, json_logs)
    logger = get_logger(__name__)

    # Validate profile
    try:
        transcode_profile = TranscodeProfile(profile.lower())
    except ValueError:
        console.print(f"[red]Invalid profile: {profile}. Use: auto, 480p, 720p, 1080p[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Starting stream to {chat}...[/green]")
    console.print(f"[dim]Source: {source}[/dim]")
    console.print(f"[dim]Profile: {transcode_profile.value}[/dim]")

    async def run_stream() -> None:
        from telegram_streamer.streamer import get_streamer
        
        streamer = await get_streamer()
        
        try:
            await streamer.start()
            session = await streamer.start_stream(chat, source, transcode_profile)
            
            console.print(f"[green]✓ Stream started![/green]")
            console.print(f"[dim]Session ID: {session.id}[/dim]")
            console.print(f"[dim]Chat ID: {session.chat_id}[/dim]")
            console.print("[dim]Press Ctrl+C to stop...[/dim]")
            
            # Wait indefinitely until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping stream...[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.exception("Stream error")
            raise typer.Exit(1)
        finally:
            await streamer.stop()
            console.print("[green]Stream stopped.[/green]")

    try:
        asyncio.run(run_stream())
    except KeyboardInterrupt:
        pass


@app.command()
def serve(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="API server host",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        "-p",
        help="API server port",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        "-l",
        help="Logging level: DEBUG, INFO, WARNING, ERROR",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Use JSON log format",
    ),
) -> None:
    """Start the REST API server.
    
    Examples:
    
        tg-streamer serve
        
        tg-streamer serve --host 127.0.0.1 --port 9000
        
        tg-streamer serve --log-level DEBUG
    """
    import uvicorn
    from telegram_streamer.config import LogLevel
    
    # Setup logging
    try:
        level = LogLevel(log_level.upper())
    except ValueError:
        console.print(f"[red]Invalid log level: {log_level}[/red]")
        raise typer.Exit(1)
    
    setup_logging(level, json_logs)

    console.print(f"[green]Starting API server on {host}:{port}...[/green]")
    
    uvicorn.run(
        "telegram_streamer.api:app",
        host=host,
        port=port,
        log_level=log_level.lower(),
        reload=False,
    )


@app.command()
def check(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information",
    ),
) -> None:
    """Check system requirements and configuration.
    
    Verifies FFmpeg installation, Telegram credentials, and other dependencies.
    """
    import shutil
    
    console.print("[bold]System Check[/bold]\n")
    
    all_ok = True
    
    # Check Python version
    py_version = sys.version_info
    py_ok = py_version >= (3, 11)
    status = "✓" if py_ok else "✗"
    color = "green" if py_ok else "red"
    console.print(f"[{color}]{status}[/{color}] Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    all_ok = all_ok and py_ok
    
    # Check FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_ok = ffmpeg_path is not None
    status = "✓" if ffmpeg_ok else "✗"
    color = "green" if ffmpeg_ok else "red"
    console.print(f"[{color}]{status}[/{color}] FFmpeg: {ffmpeg_path or 'Not found'}")
    all_ok = all_ok and ffmpeg_ok
    
    if verbose and ffmpeg_ok:
        async def get_ffmpeg_ver() -> str:
            from telegram_streamer.ffmpeg import FFmpegWrapper
            return await FFmpegWrapper.get_ffmpeg_version()
        
        try:
            version = asyncio.run(get_ffmpeg_ver())
            console.print(f"  [dim]{version}[/dim]")
        except Exception:
            pass
    
    # Check yt-dlp
    ytdlp_path = shutil.which("yt-dlp")
    ytdlp_ok = ytdlp_path is not None
    status = "✓" if ytdlp_ok else "○"  # Optional
    color = "green" if ytdlp_ok else "yellow"
    console.print(f"[{color}]{status}[/{color}] yt-dlp: {ytdlp_path or 'Not found (optional)'}")
    
    # Check environment variables
    console.print("\n[bold]Configuration[/bold]\n")
    
    try:
        settings = get_settings()
        console.print(f"[green]✓[/green] TG_API_ID: {'*' * 8}")
        console.print(f"[green]✓[/green] TG_API_HASH: {'*' * 16}")
        
        if settings.bot_token:
            console.print(f"[green]✓[/green] TG_BOT_TOKEN: {'*' * 20}")
            console.print(f"  [dim]Mode: Bot[/dim]")
        elif settings.phone_number:
            console.print(f"[green]✓[/green] TG_PHONE_NUMBER: {settings.phone_number[:4]}***")
            console.print(f"  [dim]Mode: Userbot[/dim]")
        else:
            console.print(f"[yellow]○[/yellow] No bot token or phone number configured")
            console.print(f"  [dim]Set TG_BOT_TOKEN or TG_PHONE_NUMBER[/dim]")
        
        if verbose:
            console.print(f"\n[dim]Session path: {settings.session_path}[/dim]")
            console.print(f"[dim]Default profile: {settings.default_profile.value}[/dim]")
            console.print(f"[dim]Reconnection: {'enabled' if settings.reconnect_enabled else 'disabled'}[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗[/red] Configuration error: {e}")
        console.print(f"  [dim]Set TG_API_ID and TG_API_HASH environment variables[/dim]")
        all_ok = False
    
    # Summary
    console.print()
    if all_ok:
        console.print("[green]All checks passed![/green]")
    else:
        console.print("[red]Some checks failed. Please fix the issues above.[/red]")
        raise typer.Exit(1)


@app.command()
def sessions(
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json",
    ),
) -> None:
    """List active streaming sessions (requires API server running)."""
    import httpx
    
    settings = get_settings()
    api_url = f"http://{settings.api_host}:{settings.api_port}"
    
    try:
        response = httpx.get(f"{api_url}/api/streams", timeout=5.0)
        response.raise_for_status()
        data = response.json()
        
        if format == "json":
            import json
            console.print(json.dumps(data, indent=2))
        else:
            if not data.get("streams"):
                console.print("[dim]No active streams[/dim]")
                return
            
            table = Table(title="Active Streams")
            table.add_column("ID", style="cyan")
            table.add_column("Chat ID", style="magenta")
            table.add_column("Status", style="green")
            table.add_column("Profile")
            table.add_column("Duration")
            table.add_column("Source")
            
            for stream in data["streams"]:
                duration = f"{stream['duration_seconds']:.0f}s"
                source = stream["source_url"][:40] + "..." if len(stream["source_url"]) > 40 else stream["source_url"]
                
                table.add_row(
                    stream["id"],
                    str(stream["chat_id"]),
                    stream["status"],
                    stream["profile"],
                    duration,
                    source,
                )
            
            console.print(table)
            
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to API server at {api_url}[/red]")
        console.print(f"[dim]Start the server with: tg-streamer serve[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
