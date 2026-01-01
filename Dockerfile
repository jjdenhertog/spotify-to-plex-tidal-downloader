FROM python:3.13-slim

# Set a default shell
SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        jq && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    tiddl==3.1.5 \
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

# Create tiddl config directory
RUN mkdir -p /root/.tiddl

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
