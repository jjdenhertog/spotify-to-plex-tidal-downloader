#!/bin/bash

# Paths
CONFIG_DIR="/app/config"
LINKS_FILE="$CONFIG_DIR/$1"
LOG_FILE="$CONFIG_DIR/tidal_dl_logs.json"
TOKEN_FILE="$CONFIG_DIR/tiddl_settings.json"
TARGET_TOKEN_FILE="/root/tiddl.json"

# Constants
TIME_LIMIT=$((48 * 60 * 60)) # 48 hours in seconds

# Function to print messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Ensure necessary files exist
initialize_files() {
    if [[ ! -f "$LINKS_FILE" ]]; then
        log "Error: Links file '$LINKS_FILE' does not exist!"
        exit 1
    fi

    if [[ ! -f "$LOG_FILE" ]]; then
        echo "{}" >"$LOG_FILE"
    fi
}

# Check if a link was processed more than 48 hours ago
link_too_old() {
    local link="$1"
    local timestamp
    timestamp=$(jq -r --arg link "$link" '.[$link]' "$LOG_FILE")

    if [[ "$timestamp" != "null" && $(($(date +%s) - timestamp)) -gt $TIME_LIMIT ]]; then
        return 0
    fi
    return 1
}

# Update the log file
update_log() {
    local link="$1"
    local timestamp=$(date +%s)

    if ! jq -e --arg link "$link" '.[$link] != null' "$LOG_FILE" >/dev/null 2>&1; then
        jq --arg link "$link" --argjson ts "$timestamp" \
            '.[$link] = $ts' "$LOG_FILE" >"$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}

# Main processing loop
process_links() {
    while IFS= read -r link || [[ -n "$link" ]]; do
        if [[ -z "$link" ]]; then
            continue
        fi

        log "Processing link: $link"

        # Skip if processed recently
        if link_too_old "$link"; then
            log "Skipping: Tried to sync this link longer than 48 hours ago."
            continue
        fi

        # Execute tidal-dl command safely
        if tiddl url $link download >/dev/null 2>&1; then
            log "Download successful for: $link"
            update_log "$link"
        else
            log "Error: Download failed for $link. Retrying may be necessary."
        fi
    done <"$LINKS_FILE"
}

# Entry point
main() {
    if [[ -z "$1" ]]; then
        log "Error: No links file provided."
        echo "Usage: $0 <links_filename>"
        exit 1
    fi

    if [[ -f "$TOKEN_FILE" ]]; then
        if jq -e '.auth' "$TOKEN_FILE" >/dev/null 2>&1; then
            log "Token file contains 'token'. Copying to $TARGET_TOKEN_FILE..."
            cp "$TOKEN_FILE" "$TARGET_TOKEN_FILE"
        else
            log "Token file does not contain 'token'. Skipping copy step."
        fi
    else
        log "Token file not found. Skipping token copy step."
    fi

    initialize_files
    log "Starting download process..."
    process_links
    log "Download process completed."

    log "Storing token."
    cp /root/tiddl.json /app/config/tiddl_settings.json
}

main "$@"
