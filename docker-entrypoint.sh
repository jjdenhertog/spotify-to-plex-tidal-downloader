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

# Check if tiddl is configured and copy token if available
if [ -f /app/config/tiddl_settings.json ]; then
    if jq -e '.token' /app/config/tiddl_settings.json > /dev/null 2>&1; then
        echo "✅ Tiddl token found - copying to /root/.tiddl_config.json"
        cp /app/config/tiddl_settings.json /root/tiddl.json
        echo "✅ Tiddl authenticated and ready"
    else
        echo "⚠️  Warning: Tiddl token not found in tiddl_settings.json"
        echo "   Please login first:"
        echo "   docker exec -it spotify-to-plex-tidal-downloader bash"
        echo "   tiddl"
    fi
else
    # Set default tiddl download folder to /app/download (tiddl config prompts the create of config file)
    tiddl config
    if [ -f /root/tiddl.json ]; then
        jq '.download.path="/app/download" | .download.scan_path="/app/download"' /root/tiddl.json > /root/tiddl.json.tmp && \
        mv /root/tiddl.json.tmp /root/tiddl.json
        echo "✅ Updated /root/tiddl.json default download path to /app/download"
    else
        echo "⚠️ Tiddl did not generate /root/tiddl.json";
    fi
    echo "⚠️  Warning: Tiddl not configured (no tiddl_settings.json found)"
    echo "   Please login first:"
    echo "   docker exec -it spotify-to-plex-tidal-downloader bash"
    echo "   tiddl"
    echo "   (The token will be saved to /app/config/tiddl_settings.json)"
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
