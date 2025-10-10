
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

To view real-time scheduler logs:

```bash
docker logs -f spotify-to-plex-tidal-downloader
```

To view the latest download log:

```bash
ls -lt /path/to/config/download_logs/ | head -n 2
cat /path/to/config/download_logs/<latest-log-file>
```

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
