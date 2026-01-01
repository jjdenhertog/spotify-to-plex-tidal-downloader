#!/bin/bash
set -e

echo "🎵 Tidal Downloader Starting..."
echo "=============================="

# Ensure config directory exists and has correct permissions
if [ ! -d /app/config ]; then
    echo "📁 Creating config directory..."
    mkdir -p /app/config
fi

if [ ! -w /app/config ]; then
    echo "⚠️  Warning: /app/config is not writable. Trying to fix permissions..."
    chmod 755 /app/config || true
fi

# Create log directories
mkdir -p /app/config/download_logs
mkdir -p /var/log/supervisor

# Set default environment variables if not provided
export TZ="${TZ:-UTC}"
export CRON_SCHEDULE="${CRON_SCHEDULE:-0 */12 * * *}"

# Display configuration
echo "✅ Cron Schedule: $CRON_SCHEDULE"
echo "✅ Timezone: $TZ"
echo "✅ Config Directory: /app/config"
echo "✅ Download Logs: /app/config/download_logs"
echo "✅ Error Log: /app/config/error_log.txt"

# Check if tiddl is authenticated (tiddl 3.x uses ~/.tiddl/auth.json)
TIDDL_AUTH_FILE="/root/.tiddl/auth.json"

if [ -f "$TIDDL_AUTH_FILE" ]; then
    if jq -e '.token' "$TIDDL_AUTH_FILE" > /dev/null 2>&1; then
        echo "✅ Tiddl authenticated and ready"
    else
        echo "⚠️  Warning: Tiddl auth file exists but token is missing"
        echo "   Please login:"
        echo "   docker exec -it spotify-to-plex-tidal-downloader bash"
        echo "   tiddl auth login"
    fi
else
    echo "⚠️  Warning: Tiddl not authenticated"
    echo "   Please login first:"
    echo "   docker exec -it spotify-to-plex-tidal-downloader bash"
    echo "   tiddl auth login"
fi

# Initialize tiddl config if needed (set download path)
TIDDL_CONFIG_FILE="/root/.tiddl/config.toml"
if [ ! -f "$TIDDL_CONFIG_FILE" ]; then
    echo "📝 Creating default tiddl config..."
    mkdir -p /root/.tiddl
    cat > "$TIDDL_CONFIG_FILE" << 'EOF'
[download]
download_path = "/app/download"
scan_path = "/app/download"
track_quality = "max"
skip_existing = true
threads_count = 4

[metadata]
enable = true

[templates]
default = "{album.artist}/{album.title}/{item.number:02d} - {item.title}"
EOF
    echo "✅ Created default tiddl config"
fi

# Check if download files exist
if [ -f /app/config/missing_tracks_tidal.txt ]; then
    echo "✅ Found missing_tracks_tidal.txt"
else
    echo "ℹ️  Info: missing_tracks_tidal.txt not found (will be skipped)"
fi

if [ -f /app/config/missing_albums_tidal.txt ]; then
    echo "✅ Found missing_albums_tidal.txt"
else
    echo "ℹ️  Info: missing_albums_tidal.txt not found (will be skipped)"
fi

# Start supervisor
echo "=============================="
echo "🚀 Starting scheduler service..."
echo "=============================="
exec "$@"
