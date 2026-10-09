#!/usr/bin/env python3
"""
Tidal Downloader Scheduler
Runs download.sh scripts on a configurable cron schedule
"""

import os
import signal
import sys
import subprocess
import logging
import threading
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from download_queue import DOWNLOAD_LOCK, start_api

# Configuration from environment variables
CRON_SCHEDULE = os.getenv('CRON_SCHEDULE', '0 15 * * *')  # Default: daily at 15:00
TIMEZONE = os.getenv('TZ', 'UTC')
CONFIG_DIR = Path('/app/config')
LOG_DIR = CONFIG_DIR / 'download_logs'
ERROR_LOG_FILE = CONFIG_DIR / 'error_log.txt'
APP_DIR = Path('/app')
DOWNLOAD_TIMEOUT = 7200  # 2 hours per file
API_PORT = os.getenv('API_PORT', '').strip()  # Queue API, only started when set
API_TOKEN = os.getenv('API_TOKEN', '').strip() or None

# Set when the queue API is running
download_queue = None

# Files to process (in order)
DOWNLOAD_FILES = [
    'missing_tracks_tidal.txt',
    'missing_albums_tidal.txt'
]

# Setup logging
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def log_error(message, error=None):
    """Log errors to both stdout and error log file"""
    error_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    if error:
        error_msg += f"\nError details: {str(error)}"

    logger.error(message)

    try:
        with open(ERROR_LOG_FILE, 'a') as f:
            f.write(error_msg + '\n\n')
    except Exception as e:
        logger.error(f"Failed to write to error log: {e}")


def run_download_script(filename):
    """
    Execute download.sh for a specific file
    Returns: (success: bool, output: str)
    """
    file_path = CONFIG_DIR / filename

    # A missing file is expected when Spotify to Plex has nothing to hand over,
    # so it is not an error worth writing to error_log.txt
    if not file_path.exists():
        logger.info(f"Skipping {filename}: file not found")
        return True, "File not found, skipping"

    # Check if file is empty
    if file_path.stat().st_size == 0:
        logger.info(f"Skipping {filename}: file is empty")
        return True, "File is empty, skipping"

    logger.info(f"Starting download for: {filename}")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = LOG_DIR / f"{filename.replace('.txt', '')}_{timestamp}.log"

    try:
        # Stream the output line by line so progress shows up in the container
        # logs (Portainer / docker logs) while the download is running, instead
        # of only in the log file once everything has finished.
        process = subprocess.Popen(
            ['bash', str(APP_DIR / 'download.sh'), filename],
            cwd=str(APP_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True  # own process group, so a timeout also kills tiddl
        )

        # Kill the script when it exceeds the 2 hour timeout
        timed_out = threading.Event()

        def kill_on_timeout():
            timed_out.set()
            os.killpg(process.pid, signal.SIGKILL)

        timer = threading.Timer(DOWNLOAD_TIMEOUT, kill_on_timeout)
        timer.start()

        output = []
        try:
            with open(log_filename, 'w') as f:
                f.write(f"=== Download Log for {filename} ===\n")
                f.write(f"Start time: {timestamp}\n\n")

                for line in process.stdout:
                    line = line.rstrip('\n')
                    output.append(line)
                    print(f"  [{filename}] {line}", flush=True)
                    f.write(line + '\n')
                    f.flush()

                process.wait()
                f.write(f"\nExit code: {process.returncode}\n")
        finally:
            timer.cancel()

        output = '\n'.join(output)

        if timed_out.is_set():
            log_error(f"Download script timed out for {filename} (exceeded 2 hours)")
            return False, "Timeout"

        # Check if successful
        if process.returncode == 0:
            logger.info(f"✓ Successfully completed download for: {filename}")
            return True, output
        else:
            error_msg = f"Download script failed for {filename} (exit code: {process.returncode})"
            log_error(error_msg)
            return False, output

    except Exception as e:
        log_error(f"Exception while running download for {filename}", e)
        return False, str(e)


def run_scheduled_job():
    """Execute all download scripts sequentially"""
    logger.info("=" * 60)
    logger.info("Starting scheduled download job")
    logger.info(f"Timezone: {TIMEZONE}")
    logger.info(f"Files to process: {', '.join(DOWNLOAD_FILES)}")
    logger.info("=" * 60)

    results = {}

    # Shared with the queue worker, so tiddl never runs twice at the same time
    with DOWNLOAD_LOCK:
        # Process each file sequentially
        for filename in DOWNLOAD_FILES:
            success, output = run_download_script(filename)
            results[filename] = {'success': success, 'output': output}

            # Continue to next file even if this one failed
            if not success:
                logger.warning(f"Failed to process {filename}, continuing to next file...")

    # Summary
    logger.info("=" * 60)
    logger.info("Download job completed")
    successful = sum(1 for r in results.values() if r['success'])
    logger.info(f"Results: {successful}/{len(DOWNLOAD_FILES)} successful")
    for filename, result in results.items():
        status = "✓" if result['success'] else "✗"
        logger.info(f"  {status} {filename}")
    logger.info("=" * 60)

    # Retry whatever is still waiting in the queue
    if download_queue:
        download_queue.wake()


def start_queue_api(scheduler):
    """Start the queue API and its worker next to the scheduler"""
    global download_queue

    try:
        port = int(API_PORT)
    except ValueError:
        log_error(f"Invalid API_PORT: {API_PORT}, queue API not started")
        return

    def next_scheduled_run():
        job = scheduler.get_job('download_job')
        return getattr(job, 'next_run_time', None) if job else None

    try:
        download_queue, _ = start_api(port, CONFIG_DIR, token=API_TOKEN, next_run=next_scheduled_run)
    except Exception as e:
        log_error(f"Failed to start queue API on port {port}", e)
        return

    logger.info(f"Queue API listening on port {port}" + ("" if API_TOKEN else " (no API_TOKEN set)"))


def main():
    """Initialize and start the scheduler"""
    logger.info("=" * 60)
    logger.info("Tidal Downloader Scheduler Starting")
    logger.info("=" * 60)
    logger.info(f"Cron schedule: {CRON_SCHEDULE}")
    logger.info(f"Timezone: {TIMEZONE}")
    logger.info(f"Config directory: {CONFIG_DIR}")
    logger.info(f"Log directory: {LOG_DIR}")
    logger.info(f"Error log: {ERROR_LOG_FILE}")
    logger.info("=" * 60)

    # Validate timezone
    try:
        tz = pytz.timezone(TIMEZONE)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Invalid timezone: {TIMEZONE}, falling back to UTC")
        tz = pytz.UTC

    # Create scheduler
    scheduler = BlockingScheduler(timezone=tz)

    try:
        # Parse and add cron job
        # Cron format: minute hour day month day_of_week
        cron_parts = CRON_SCHEDULE.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron format: {CRON_SCHEDULE}")

        trigger = CronTrigger(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
            timezone=tz
        )

        scheduler.add_job(
            run_scheduled_job,
            trigger=trigger,
            id='download_job',
            name='Tidal Download Job',
            misfire_grace_time=3600  # Allow 1 hour grace time for missed jobs
        )

        next_run = trigger.get_next_fire_time(None, datetime.now(tz))

        if API_PORT:
            start_queue_api(scheduler)

        logger.info("Scheduler configured successfully. Starting...")
        logger.info(f"Next download run: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)

        # Start the scheduler (blocking)
        scheduler.start()

    except ValueError as e:
        logger.error(f"Invalid cron schedule format: {e}")
        log_error(f"Failed to start scheduler: Invalid cron schedule format", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        log_error("Scheduler crashed", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
