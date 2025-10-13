FROM ubuntu:22.04

# Set a default shell
SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Python 3.11 (available in Ubuntu 22.04 by default)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        python3-pip \
        build-essential \
        curl \
        ca-certificates \
        jq && \
    rm -rf /var/lib/apt/lists/*

# Update pip for Python 3.11
RUN python3.11 -m pip install --upgrade pip

# Install Python packages
RUN pip3.11 install --no-cache-dir \
    tiddl \
    mutagen \
    supervisor \
    apscheduler \
    pytz \
    tzdata

# Set up the container environment
RUN mkdir -p /app/download && \
    mkdir -p /app/config && \
    mkdir -p /app/config/download_logs && \
    mkdir -p /var/log/supervisor && \
    chmod 755 /app/config

# Copy application files
COPY copy-files/download.sh /app/download.sh
COPY copy-files/scheduler.py /app/scheduler.py
COPY copy-files/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh

# Set default tiddl download folder to /app/download
RUN if [ -f /root/tiddl.json ]; then \
        jq '.download.path="/app/download" | .download.scan_path="/app/download"' /root/tiddl.json > /root/tiddl.json.tmp && \
        mv /root/tiddl.json.tmp /root/tiddl.json; \
    else \
        echo "⚠️ Tiddl did not generate /root/tiddl.json during build"; \
    fi

# Set permissions
RUN chmod +x /app/download.sh && \
    chmod +x /app/scheduler.py && \
    chmod +x /docker-entrypoint.sh

# Set default environment variables
ENV TZ=UTC \
    CRON_SCHEDULE="0 */12 * * *"

# Set entrypoint for initialization
ENTRYPOINT ["/docker-entrypoint.sh"]

# Start supervisor to manage the scheduler service
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
