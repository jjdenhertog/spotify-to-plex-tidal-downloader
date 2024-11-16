
# Tidal Music Downloader

This implementation uses the `missing_tracks_tidal.txt` from [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) to use [Tiddl](https://github.com/oskvr37/tiddl) to download the tracks. [Disclaimer](https://github.com/yaronzz/Tidal-Media-Downloader?tab=readme-ov-file#-disclaimer).

You can also use it without [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) just make sure to use the txt file structure similar to the [example](misc/example.txt).

-------

# Table of Contents
* [Installation](#installation)
  * [Binding volume](#binding-volume)
  * [Docker installation](#docker-installation)
  * [Portainer installation](#portainer-installation)
  * [First time login](#first-time-login)
* [Running the synchronization](#running-the-synchronization)
  * [Logging](#logging)
* [Support This Open-Source Project ❤️](#support-this-open-source-project-️)
* [Libraries and reference](#libraries-and-reference)
* [Disclaimer](#disclaimer)

## Installation

You can install the service using Docker. This will install [Tiddl](https://github.com/oskvr37/tiddl) extended with some extra scripts to do the syncing. 

🚨 **Important: ** You need to bind the same volume of [Spotify to Plex](https://github.com/jjdenhertog/spotify-to-plex) to allow for seamless integration

### Binding volume

All the configuration data is stored in the `/app/config` folder, you need to add it as a volume for persistent storage. In this folder you can add text files folder for downloading. The text files should contain Tidal links structure like the [example](misc/example.txt).

All the download files are stored in `/app/download` folder, link that to the volume where the media files will be stored.

### Docker installation

```sh
docker run -d \
    -v /local/directory/:/app/config:rw \
    -v /local/directory/:/app/download:rw \
    --name=spotify-to-plex-tidal-downloader \
    --network=host \
    --restart on-failure:4 \
    jjdenhertog/spotify-to-plex-tidal-downloader \
    bash -c "sleep infinity"
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
            - '/local/directory:/app/config'
            - '/local/directory:/app/download'
        network_mode: "host"
        image: 'jjdenhertog/spotify-to-plex-tidal-downloader:latest'
        command: bash -c "sleep infinity"
```

### First time login

Before you can use this service you need to login to tidal-dl. Login to the console of the running container:

```bash
docker exec -it spotify-to-plex-tidal-downloader bash
```

Open the Tidal Media Downloader and login. After the login is successful you can start using this service.

```bash
tiddl
```

-----------

## Running the synchronization

The image contains the script `download.sh` which can process a text file that contains links that can be processed by Tiddl. The easiest way to execute the script is by using `docker exec`. Using the command below.

```bash
docker exec spotify-to-plex-tidal-downloader sh -c "cd /app && ./download.sh missing_tracks_tidal.txt"
```

### Logging

When you run this via a task manager or something similar you can store the logs using this command.

```bash
docker exec spotify-to-plex-tidal-downloader sh -c "cd /app && ./download.sh missing_tracks_tidal.txt" > /volume2/Share/tiddl_downloads.log
touch tiddl_downloads.log
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