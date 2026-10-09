
# Tidal Downloader

This implementation uses the `missing_tracks_tidal.txt` from [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) to use [Tiddl](https://github.com/oskvr37/tiddl) to download the tracks. [Disclaimer](https://github.com/yaronzz/Tidal-Media-Downloader?tab=readme-ov-file#-disclaimer).

You can also use it without [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) just make sure to use the txt file structure similar to the [example](misc/example.txt).

-------

# Table of Contents
* [Installation](#installation)
  * [Binding volume](#binding-volume)
  * [Environment Variables](#environment-variables)
  * [Docker installation](#docker-installation)
  * [Portainer installation](#portainer-installation)
  * [First time login](#first-time-login)
* [Running the synchronization](#running-the-synchronization)
  * [Automatic Scheduling](#automatic-scheduling)
  * [Manual Execution](#manual-execution)
  * [Logging](#logging)
* [Queue API](#queue-api)
* [Support This Open-Source Project ❤️](#support-this-open-source-project-️)
* [Libraries and reference](#libraries-and-reference)
* [Disclaimer](#disclaimer)

## Installation

You can install the service using Docker. This will install [Tiddl](https://github.com/oskvr37/tiddl) with an automated scheduler that runs daily at 15:00 by default.

🚨 IMPORTANT: You need to bind the same volume of [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) to allow for seamless integration

### Binding volume

**Important**: The `/app/config` folder should be bound to the **same volume** as [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) for seamless integration.

**How it works:**
- Spotify to Plex generates `missing_tracks_tidal.txt` and `missing_albums_tidal.txt` in its config directory
- Both containers share the same `/app/config` volume
- Tidal Downloader automatically reads these files and downloads the tracks
- Download logs are stored in `/app/config/download_logs/` (persisted in the shared volume)

**Volumes to bind:**
- `/app/config` - Shared configuration and logs (must be the same as Spotify to Plex config volume)
- `/app/download` - Downloaded music files (link to your media library folder)
- `/root/.tiddl` - Tiddl authentication and config (persists login across container restarts)

**Note**: You can also use this service standalone by manually creating text files in `/app/config` with Tidal links structured like the [example](misc/example.txt).

### Environment Variables

The scheduler can be configured using environment variables:

- `CRON_SCHEDULE`: Cron expression for scheduling downloads (default: `0 15 * * *` - daily at 15:00)
- `TZ`: Timezone for the scheduler (default: `UTC`)

The scheduler will automatically process both `missing_tracks_tidal.txt` and `missing_albums_tidal.txt` if they exist. Files that don't exist or are empty will be skipped gracefully.

### Docker installation

```sh
docker run -d \
    -v /path/to/spotify-to-plex/config:/app/config:rw \
    -v /path/to/music/library:/app/download:rw \
    -v /path/to/tiddl-config:/root/.tiddl:rw \
    -e TZ=UTC \
    -e CRON_SCHEDULE="0 15 * * *" \
    --name=spotify-to-plex-tidal-downloader \
    --restart unless-stopped \
    jjdenhertog/spotify-to-plex-tidal-downloader
```

**Example with actual paths:**
```sh
docker run -d \
    -v /volume1/docker/spotify-to-plex/config:/app/config:rw \
    -v /volume1/music:/app/download:rw \
    -v /volume1/docker/spotify-to-plex/config/tiddl:/root/.tiddl:rw \
    -e TZ=Europe/Amsterdam \
    -e CRON_SCHEDULE="0 15 * * *" \
    --name=spotify-to-plex-tidal-downloader \
    --restart unless-stopped \
    jjdenhertog/spotify-to-plex-tidal-downloader
```

### Portainer installation

Create a new stack with the following configuration when using portainer.

```yaml
version: '3.3'
services:
    spotify-to-plex-tidal-downloader:
        container_name: spotify-to-plex-tidal-downloader
        restart: unless-stopped
        volumes:
            - '/path/to/spotify-to-plex/config:/app/config'
            - '/path/to/music/library:/app/download'
            - '/path/to/tiddl-config:/root/.tiddl'
        environment:
            - TZ=UTC
            - CRON_SCHEDULE=0 15 * * *
        image: 'jjdenhertog/spotify-to-plex-tidal-downloader:latest'
```

**Example with actual paths:**
```yaml
version: '3.3'
services:
    spotify-to-plex-tidal-downloader:
        container_name: spotify-to-plex-tidal-downloader
        restart: unless-stopped
        volumes:
            - '/volume1/docker/spotify-to-plex/config:/app/config'
            - '/volume1/music:/app/download'
            - '/volume1/docker/spotify-to-plex/config/tiddl:/root/.tiddl'
        environment:
            - TZ=Europe/Amsterdam
            - CRON_SCHEDULE=0 2,14 * * *
        image: 'jjdenhertog/spotify-to-plex-tidal-downloader:latest'
```

### First time login

Before you can use this service you need to login to Tiddl. Login to the console of the running container:
 
```bash
docker exec -it spotify-to-plex-tidal-downloader bash
```

Open the Tidal Media Downloader and login. After the login is successful you can start using this service.

```bash
tiddl auth login
```

### Configuration

Tiddl configuration is stored in `/root/.tiddl/config.toml` (which persists via the volume mount). A default config is created automatically on first run. You can modify settings by editing the `config.toml` file in your mounted tiddl config directory.

Example configuration:

```toml
[download]
download_path = "/app/download"
scan_path = "/app/download"
track_quality = "high"     # Options: low, normal, high, max
skip_existing = true
threads_count = 4
atmos_filter = "none"      # Options: none, allow, only

[metadata]
enable = true
lyrics = false
cover = false

[templates]
default = "{album.artist}/{album.title}/{item.number:02d} - {item.title}"
```

See the [tiddl documentation](https://github.com/oskvr37/tiddl) for all available configuration options.

**A note on `track_quality`**: since tiddl 3.4.0 the `max` setting (HI_RES_LOSSLESS) can no longer be obtained with tiddl's default credentials, so hi-res tracks will fail to download. `high` (LOSSLESS, FLAC 16/44.1) is the recommended setting and is used for new installs. If your existing config still says `max`, the container will warn you on startup.

-----------

## Running the synchronization

### Automatic Scheduling

The service automatically runs downloads based on the configured `CRON_SCHEDULE`. By default, it runs every day at 15:00 and processes these files sequentially:

1. `missing_tracks_tidal.txt`
2. `missing_albums_tidal.txt`

Both files are expected to be located in `/app/config`. If a file doesn't exist or is empty, it will be skipped gracefully, and the scheduler will continue with the next file.

### Manual Execution

You can also manually trigger downloads using `docker exec`:

```bash
# Run for tracks
docker exec spotify-to-plex-tidal-downloader sh -c "cd /app && ./download.sh missing_tracks_tidal.txt"

# Run for albums
docker exec spotify-to-plex-tidal-downloader sh -c "cd /app && ./download.sh missing_albums_tidal.txt"
```

### Logging

The service provides comprehensive logging:

- **Scheduler logs**: Visible via `docker logs spotify-to-plex-tidal-downloader`
- **Download logs**: Stored in `/app/config/download_logs/` (timestamped for each run)
- **Error logs**: Stored in `/app/config/error_log.txt`

A run is reported as failed when tiddl is not logged in, when the Tidal token has expired, or when every download in the run failed. Individual unavailable tracks are not treated as a run failure — they are retried on each run for 48 hours before being given up on.

To view real-time scheduler logs:

```bash
docker logs -f spotify-to-plex-tidal-downloader
```

To view the latest download log:

```bash
ls -lt /path/to/config/download_logs/ | head -n 2
cat /path/to/config/download_logs/<latest-log-file>
```

## Queue API

Besides the txt files, the container can run a small HTTP API so another service can ask for specific Tidal tracks or albums to be downloaded right away. It is off by default; nothing changes unless you set `API_PORT`.

### Environment variables

- `API_PORT`: port the API listens on inside the container, e.g. `8791`. The API only starts when this is set.
- `API_TOKEN`: optional. When set, every request needs the header `Authorization: Bearer <token>`, otherwise it gets a `401`.

Publish the port to reach it from outside the container. With `docker run` add `-p 8791:8791 -e API_PORT=8791 -e API_TOKEN=change-me`. In a Portainer stack:

```yaml
        ports:
            - '8791:8791'
        environment:
            - TZ=UTC
            - CRON_SCHEDULE=0 15 * * *
            - API_PORT=8791
            - API_TOKEN=change-me
```

🚨 **Security**: the API has no TLS and lets anyone who can reach it start downloads. Keep it on your LAN (do not forward the port on your router) and set `API_TOKEN`.

### How it works

- Queued items are downloaded one at a time with tiddl, never at the same time as a scheduled run: a request that arrives during a scheduled run waits until that run is done.
- The queue is processed right after every request that adds something, and again at the end of every scheduled run.
- A failed download is retried on later runs for 48 hours after it was queued, then it is marked `failed`.
- Successful downloads are recorded in `tidal_dl_logs.json`, the same file the txt flow uses, under the link `https://tidal.com/browse/track/<id>` or `https://tidal.com/browse/album/<id>`.
- The queue is stored in `/app/config/download_queue.json` and survives restarts. Downloaded items are removed from it after 30 days.
- Progress shows up in the container logs, prefixed with `[queue track/<id>]`.

### Endpoints

**Queue tracks and albums**: `POST /queue`

```bash
curl -X POST http://your-server:8791/queue \
    -H "Authorization: Bearer change-me" \
    -H "Content-Type: application/json" \
    -d '{"tracks": ["309956", "100480232"], "albums": ["456"], "source": "my-script"}'
```

`tracks` and `albums` are lists of Tidal ids (digits only), at most 100 ids per request. An entry can also be an object with a `label` of at most 200 characters, so the queue can tell what it holds: `{"id": "309956", "label": "Artist - Title"}`. `source` is an optional label for who asked, of at most 40 characters. The queue holds at most 1000 items that are waiting or downloading; above that the request gets a `429`.

The response (`202`) tells you what happened with every id. An id is `already` when it is queued, downloading, or was downloaded in the last 48 hours:

```json
{
    "queued": [{"type": "track", "id": "309956"}, {"type": "album", "id": "456"}],
    "already": [{"type": "track", "id": "100480232", "status": "done"}],
    "invalid": []
}
```

**List the queue**: `GET /queue`, optionally filtered with `?status=queued`, `downloading`, `done` or `failed`

```json
{
    "items": [
        {
            "type": "track",
            "id": "309956",
            "status": "queued",
            "label": "Artist - Title",
            "source": "my-script",
            "added_at": "2026-10-09T12:00:00+00:00",
            "updated_at": "2026-10-09T12:05:00+00:00",
            "attempts": 1,
            "last_error": "Error: track not available"
        }
    ]
}
```

**One item**: `GET /queue/track/<id>` or `GET /queue/album/<id>` returns the item, or `404`.

**Remove an item**: `DELETE /queue/track/<id>` returns `204`, `404` when it is not in the queue, or `409` while it is downloading.

**Health**: `GET /health`

```json
{"ok": true, "running": false, "queued": 2, "next_scheduled_run": "2026-10-09T15:00:00+00:00", "tidal_auth": "ok"}
```

`running` is true while a download (queue or scheduled) is in progress. `tidal_auth` is `ok` when tiddl has a login token, `missing` when you still need to run `tiddl auth login`, and `unknown` when the auth file cannot be read. It does not contact Tidal.

------------

## Support This Open-Source Project ❤️

If you appreciate my work, consider starring this repository or making a donation to support ongoing development. Your support means the world to me—thank you!

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/jjdenhertog)

Are you a developer and have some free time on your hand? It would be great if you can help me maintain and improve this library.

------------

## Libraries and reference

- [tiddl](https://github.com/oskvr37/tiddl)
- [tidal-wiki](https://github.com/Fokka-Engineering/TIDAL/wiki)

------------

## Disclaimer
- Private use only.
- Need a Tidal-HIFI subscription. 
- You should not use this method to distribute or pirate music.
- It may be illegal to use this in your country, so be informed.
