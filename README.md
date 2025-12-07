# Telegram Streamer

[![CI](https://github.com/AetherVoyager/live/actions/workflows/ci.yml/badge.svg)](https://github.com/AetherVoyager/live/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production-ready Telegram streaming app that joins Telegram group/channel video chats and streams live video sources.

## Features

- 🎥 **Multi-Source Streaming**: M3U/M3U8/HLS, RTMP, and YouTube Live support
- 🔄 **Auto-Reconnection**: Resilient reconnection within 30-90 seconds
- 📊 **Transcode Profiles**: auto, 480p, 720p, 1080p quality options
- 🖥️ **Dual Interface**: CLI and REST API
- 📈 **Monitoring**: Prometheus metrics and health endpoints
- 🐳 **Docker Ready**: Production Docker images with docker-compose
- ✅ **Well Tested**: 70%+ unit test coverage

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg
- Telegram API credentials (from [my.telegram.org](https://my.telegram.org/apps))
- Optional: yt-dlp (for YouTube Live support)

### Installation

```bash
# Clone the repository
git clone https://github.com/AetherVoyager/live.git
cd live

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e ".[dev]"
```

### Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your Telegram credentials:

```env
# Required: Telegram API credentials
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash

# Authentication (choose one):
TG_BOT_TOKEN=your_bot_token       # Bot mode
# TG_PHONE_NUMBER=+1234567890     # Userbot mode
```

### Verify Setup

```bash
tg-streamer check --verbose
```

## Usage

### CLI Commands

#### Start streaming directly:

```bash
# Stream to a channel using HLS
tg-streamer stream @mychannel https://example.com/live/stream.m3u8

# Stream to a group with specific profile
tg-streamer stream -1001234567890 https://example.com/stream.m3u8 --profile 720p

# Stream from RTMP source
tg-streamer stream @mygroup rtmp://server/live/stream_key --profile 1080p

# Stream YouTube Live
tg-streamer stream @mychannel "https://www.youtube.com/watch?v=live_video_id"
```

#### Start the API server:

```bash
# Start with defaults (0.0.0.0:8080)
tg-streamer serve

# Custom host and port
tg-streamer serve --host 127.0.0.1 --port 9000

# With debug logging
tg-streamer serve --log-level DEBUG
```

#### List active sessions:

```bash
# Requires API server running
tg-streamer sessions

# JSON output
tg-streamer sessions --format json
```

### REST API

Once the server is running, the full API documentation is available at:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

#### Start a stream:

```bash
curl -X POST http://localhost:8080/api/streams \
  -H "Content-Type: application/json" \
  -d '{
    "chat": "@mychannel",
    "source": "https://example.com/stream.m3u8",
    "profile": "720p"
  }'
```

#### List streams:

```bash
curl http://localhost:8080/api/streams
```

#### Stop a stream:

```bash
curl -X DELETE http://localhost:8080/api/streams/{session_id}
```

#### Health check:

```bash
curl http://localhost:8080/health
```

#### Prometheus metrics:

```bash
curl http://localhost:8080/metrics
```

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f telegram-streamer

# Stop
docker-compose down
```

### With Monitoring Stack

```bash
# Start with Prometheus and Grafana
docker-compose --profile monitoring up -d

# Access Grafana at http://localhost:3000 (admin/admin)
```

### Manual Docker Build

```bash
# Build image
docker build -t telegram-streamer:latest .

# Run container
docker run -d \
  --name telegram-streamer \
  -p 8080:8080 \
  -v telegram_sessions:/app/sessions \
  -e TG_API_ID=your_api_id \
  -e TG_API_HASH=your_api_hash \
  -e TG_BOT_TOKEN=your_bot_token \
  telegram-streamer:latest
```

## Systemd Service

For running on Linux servers without Docker:

```bash
# Copy service file
sudo cp telegram-streamer.service /etc/systemd/system/

# Edit the service file with your paths
sudo nano /etc/systemd/system/telegram-streamer.service

# Reload systemd and start
sudo systemctl daemon-reload
sudo systemctl enable telegram-streamer
sudo systemctl start telegram-streamer

# Check status
sudo systemctl status telegram-streamer
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TG_API_ID` | Telegram API ID (required) | - |
| `TG_API_HASH` | Telegram API Hash (required) | - |
| `TG_BOT_TOKEN` | Bot token for bot mode | - |
| `TG_PHONE_NUMBER` | Phone number for userbot mode | - |
| `TG_SESSION_NAME` | Session file name | `telegram_streamer` |
| `TG_SESSION_PATH` | Path to store sessions | `./sessions` |
| `TG_DEFAULT_PROFILE` | Default transcode profile | `auto` |
| `TG_FFMPEG_PATH` | Path to FFmpeg binary | `ffmpeg` |
| `TG_FFMPEG_THREADS` | FFmpeg thread count | `2` |
| `TG_RECONNECT_ENABLED` | Enable auto-reconnection | `true` |
| `TG_RECONNECT_MAX_ATTEMPTS` | Max reconnect attempts | `10` |
| `TG_RECONNECT_TIMEOUT` | Reconnect timeout (seconds) | `90` |
| `TG_API_HOST` | API server host | `0.0.0.0` |
| `TG_API_PORT` | API server port | `8080` |
| `TG_LOG_LEVEL` | Logging level | `INFO` |
| `TG_LOG_JSON` | Use JSON log format | `false` |

## Transcode Profiles

| Profile | Resolution | Video Bitrate | Audio Bitrate | Use Case |
|---------|------------|---------------|---------------|----------|
| `auto` | Source | Source | Source | Best quality, lowest CPU |
| `480p` | 854x480 | 1.5 Mbps | 128 kbps | Mobile, slow connections |
| `720p` | 1280x720 | 3 Mbps | 128 kbps | Balanced quality |
| `1080p` | 1920x1080 | 5 Mbps | 128 kbps | High quality |

## Bot vs Userbot Mode

### Bot Mode (`TG_BOT_TOKEN`)

**Pros:**
- Easy to set up
- No phone number required
- Can be added to multiple groups

**Cons:**
- ⚠️ Bots cannot join video chats by themselves
- Must be added to the chat as admin with "Manage Video Chats" permission
- Limited to groups where they're added

### Userbot Mode (`TG_PHONE_NUMBER`)

**Pros:**
- Full access to join any video chat (if you're a member)
- Can create video chats
- Works like a regular user

**Cons:**
- Requires phone number verification
- Risk of account restrictions if abused
- Only one session per phone number

**Recommendation:** Use userbot mode for production streaming applications.

## Reconnection Behavior

The streamer automatically reconnects on disconnection:

1. **Exponential Backoff**: Starts at 5s, doubles up to 30s max
2. **Max Attempts**: 10 reconnection attempts by default
3. **Timeout**: Maximum 90 seconds to re-establish connection
4. **State Tracking**: Session status updates throughout the process

Configure via environment variables:
```env
TG_RECONNECT_ENABLED=true
TG_RECONNECT_MIN_DELAY=5
TG_RECONNECT_MAX_DELAY=30
TG_RECONNECT_MAX_ATTEMPTS=10
TG_RECONNECT_TIMEOUT=90
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=src/telegram_streamer --cov-report=html

# Specific test file
pytest tests/test_ffmpeg.py -v
```

### Code Quality

```bash
# Format code
black src tests

# Lint
ruff check src tests

# Type checking
mypy src
```

## Monitoring

### Health Endpoint

```json
GET /health
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600.5,
  "telegram_connected": true,
  "active_streams": 2
}
```

### Prometheus Metrics

Available at `/metrics`:

- `telegram_streamer_stream_starts_total` - Total stream starts
- `telegram_streamer_stream_stops_total` - Total stream stops
- `telegram_streamer_stream_errors_total` - Total stream errors
- `telegram_streamer_active_streams` - Current active streams
- `telegram_streamer_reconnection_attempts_total` - Reconnection attempts
- `telegram_streamer_stream_duration_seconds` - Stream duration histogram

## Troubleshooting

### Common Issues

**"FFmpeg not found"**
```bash
# Windows
choco install ffmpeg

# Linux
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

**"Session expired"**
- Delete the session file in `./sessions/` and re-authenticate

**"Cannot join video chat"**
- Ensure the bot/user has proper permissions
- For bots: must be admin with "Manage Video Chats" permission
- For userbots: must be a member of the group/channel

**"Stream source error"**
- Verify the stream URL is accessible
- For YouTube: ensure yt-dlp is installed
- Check if the source requires authentication

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Acknowledgments

- [Pyrogram](https://github.com/pyrogram/pyrogram) - Telegram MTProto API framework
- [PyTgCalls](https://github.com/pytgcalls/pytgcalls) - Telegram Group Calls library
- [FFmpeg](https://ffmpeg.org/) - Multimedia framework
