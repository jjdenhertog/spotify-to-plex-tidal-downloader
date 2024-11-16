# Builder stage
FROM ubuntu:20.04 AS builder

# Set a default shell
SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive

# Updates and installs
RUN apt update && \
    apt -y install software-properties-common curl && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt update && \
    apt -y install \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        build-essential \
        nano \
        jq && \
    rm -rf /var/lib/apt/lists/*

# Install the latest pip using get-pip.py
RUN curl -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python3.11 get-pip.py && \
    rm get-pip.py

# Copy necessary files to the builder
COPY copy-files/ /copy-files/

# Final stage
FROM ubuntu:20.04

# Set a default shell
SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive

# Updates and installs
RUN apt update && \
    apt -y install software-properties-common curl && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt update && \
    apt -y install \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        build-essential \
        nano \
        jq && \
    rm -rf /var/lib/apt/lists/*

# Install the latest pip using get-pip.py
RUN curl -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python3.11 get-pip.py && \
    rm get-pip.py

# Install tiddl
RUN pip3 install --no-cache-dir tiddl --upgrade
RUN pip3 install --no-cache-dir mutagen --upgrade

# Set up the container environment
RUN mkdir -p /app/download && \
    mkdir -p /app/config

# Copy files from the builder stage
COPY --from=builder /copy-files/download.sh /app/download.sh
COPY --from=builder /copy-files/tiddl_settings.json /root/.tiddl_config.json

# Set permissions
RUN chmod +x /app/download.sh

# Entry point configuration
ENTRYPOINT []