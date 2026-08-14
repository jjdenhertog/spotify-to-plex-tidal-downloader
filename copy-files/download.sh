#!/bin/bash

# Paths
CONFIG_DIR="/app/config"
LINKS_FILE="$CONFIG_DIR/$1"
LOG_FILE="$CONFIG_DIR/tidal_dl_logs.json"
AUTH_FILE="/root/.tiddl/auth.json"

# Constants
TIME_LIMIT=$((48 * 60 * 60)) # 48 hours in seconds

# Counters
total=0
failed=0
skipped=0

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

# tiddl exits 0 even when it is not authenticated, so check up front.
# Without this every link would be reported as downloaded successfully.
check_auth() {
    if [[ ! -f "$AUTH_FILE" ]] || ! jq -e '.token // empty' "$AUTH_FILE" >/dev/null 2>&1; then
        log "Error: tiddl is not authenticated. Run 'tiddl auth login' inside the container."
        exit 1
    fi

    local refresh_output
    local refresh_status
    refresh_output=$(tiddl auth refresh 2>&1)
    refresh_status=$?
    echo "$refresh_output"

    # An expired or revoked token makes the refresh throw, which would otherwise
    # show up as every single link failing to download.
    if [[ $refresh_status -ne 0 ]] || grep -qi "not logged in" <<<"$refresh_output"; then
        log "Error: tiddl token is no longer valid. Run 'tiddl auth login' inside the container."
        exit 1
    fi
}

# Check if a link was first tried more than 48 hours ago.
# Links are retried on every run for 48 hours, then given up on.
link_too_old() {
    local link="$1"
    local timestamp
    timestamp=$(jq -r --arg link "$link" '.[$link]' "$LOG_FILE")

    if [[ "$timestamp" != "null" && $(($(date +%s) - timestamp)) -gt $TIME_LIMIT ]]; then
        return 0
    fi
    return 1
}

# Record the first time we tried a link
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
        # Strip carriage returns and surrounding whitespace
        link="${link//$'\r'/}"
        link="${link#"${link%%[![:space:]]*}"}"
        link="${link%"${link##*[![:space:]]}"}"

        if [[ -z "$link" ]]; then
            continue
        fi

        # Skip if we have been retrying this one for over 48 hours
        if link_too_old "$link"; then
            log "Skipping: first tried this link more than 48 hours ago."
            skipped=$((skipped + 1))
            continue
        fi

        total=$((total + 1))
        log "Processing link: $link"

        # --raise-errors makes tiddl exit non-zero on a failed resource;
        # without it failures are swallowed and reported as success.
        if tiddl download --raise-errors url "$link" 2>&1; then
            log "Download successful for: $link"
            update_log "$link"
        else
            log "Error: Download failed for $link. Will retry on the next run."
            failed=$((failed + 1))
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

    initialize_files
    check_auth

    log "Starting download process..."
    process_links
    log "Download process completed. attempted=$total failed=$failed skipped=$skipped"

    # Only treat this as a run failure when nothing at all got through --
    # individual unavailable tracks are normal and get retried for 48 hours.
    if [[ $total -gt 0 && $failed -eq $total ]]; then
        log "Error: every download in this run failed."
        exit 1
    fi
}

main "$@"
