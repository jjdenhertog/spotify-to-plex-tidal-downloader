"""
Tidal Downloader Queue API
A small HTTP API so another service can ask for specific Tidal tracks/albums
to be downloaded on demand. Only started when API_PORT is set.

Standard library only. Runs as threads inside scheduler.py, sharing one lock
with the scheduled txt-file job so tiddl never runs twice at the same time.
"""

import hmac
import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# Held while tiddl runs, by both the scheduled job and the queue worker
DOWNLOAD_LOCK = threading.Lock()

TYPES = ('track', 'album')
STATUSES = ('queued', 'downloading', 'done', 'failed')
ID_PATTERN = re.compile(r'^\d{1,20}$')

MAX_IDS_PER_REQUEST = 100
MAX_OPEN_ITEMS = 1000
MAX_SOURCE_LENGTH = 40
MAX_BODY_BYTES = 64 * 1024
RETRY_WINDOW = 48 * 60 * 60  # retry failed items for 48 hours, same as the txt flow
DONE_RETENTION = 30 * 24 * 60 * 60  # prune done items after 30 days
DOWNLOAD_TIMEOUT = 7200  # 2 hours per item


def canonical_url(item_type, item_id):
    """The link format Spotify to Plex writes to the txt files"""
    return f"https://tidal.com/browse/{item_type}/{item_id}"


def iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class DownloadQueue:
    """Queue state persisted in download_queue.json, plus the download worker"""

    def __init__(self, config_dir, tiddl_cmd=('tiddl',), auth_file='/root/.tiddl/auth.json',
                 lock=DOWNLOAD_LOCK, timeout=DOWNLOAD_TIMEOUT, clock=time.time):
        self.config_dir = Path(config_dir)
        self.queue_file = self.config_dir / 'download_queue.json'
        self.tidal_log_file = self.config_dir / 'tidal_dl_logs.json'
        self.tiddl_cmd = list(tiddl_cmd)
        self.auth_file = Path(auth_file)
        self.lock = lock
        self.timeout = timeout
        self.clock = clock

        # Guards self.items and the queue file; never held while tiddl runs
        self.state_lock = threading.Lock()
        self.wake_event = threading.Event()
        self.items = {}
        self._load()

    # ---- state ----

    def _load(self):
        if self.queue_file.exists():
            try:
                data = json.loads(self.queue_file.read_text())
                self.items = {f"{i['type']}/{i['id']}": i for i in data.get('items', [])}
            except Exception as e:
                logger.error(f"Queue: could not read {self.queue_file}, starting empty: {e}")
                self.items = {}

        # A download that was running when the container stopped never finished
        for item in self.items.values():
            if item['status'] == 'downloading':
                item['status'] = 'queued'
        self._save()

    def _save(self):
        """Prune old done items and write the file atomically (temp file + rename)"""
        now = self.clock()
        self.items = {
            key: item for key, item in self.items.items()
            if not (item['status'] == 'done' and now - item['updated_at'] > DONE_RETENTION)
        }
        tmp_file = self.queue_file.with_suffix('.json.tmp')
        tmp_file.write_text(json.dumps({'items': list(self.items.values())}, indent=2))
        os.replace(tmp_file, self.queue_file)

    def _read_tidal_log(self):
        try:
            return json.loads(self.tidal_log_file.read_text())
        except Exception:
            return {}

    def _record_tidal_log(self, url):
        """Same memory as download.sh: the first successful download per link"""
        data = self._read_tidal_log()
        if url in data:
            return
        data[url] = int(self.clock())
        tmp_file = self.tidal_log_file.with_suffix('.json.tmp')
        tmp_file.write_text(json.dumps(data))
        os.replace(tmp_file, self.tidal_log_file)

    @staticmethod
    def public(item):
        return {
            'type': item['type'],
            'id': item['id'],
            'status': item['status'],
            'source': item.get('source'),
            'added_at': iso(item['added_at']),
            'updated_at': iso(item['updated_at']),
            'attempts': item['attempts'],
            'last_error': item.get('last_error'),
        }

    def open_count(self):
        with self.state_lock:
            return sum(1 for i in self.items.values() if i['status'] in ('queued', 'downloading'))

    def list_items(self, status=None):
        with self.state_lock:
            return [self.public(i) for i in self.items.values() if status is None or i['status'] == status]

    def get(self, item_type, item_id):
        with self.state_lock:
            item = self.items.get(f"{item_type}/{item_id}")
            return self.public(item) if item else None

    def delete(self, item_type, item_id):
        """Returns 'deleted', 'not_found' or 'downloading'"""
        with self.state_lock:
            key = f"{item_type}/{item_id}"
            item = self.items.get(key)
            if not item:
                return 'not_found'
            if item['status'] == 'downloading':
                return 'downloading'
            del self.items[key]
            self._save()
            return 'deleted'

    def add(self, tracks, albums, source=None):
        """
        Validate and queue ids. Raises ValueError for a bad request and
        OverflowError when the queue is full.
        Returns {'queued': [...], 'already': [...], 'invalid': [...]}
        """
        if tracks is None:
            tracks = []
        if albums is None:
            albums = []
        if not isinstance(tracks, list) or not isinstance(albums, list):
            raise ValueError('tracks and albums must be lists')
        if not tracks and not albums:
            raise ValueError('nothing to queue: provide tracks and/or albums')
        if len(tracks) + len(albums) > MAX_IDS_PER_REQUEST:
            raise ValueError(f'at most {MAX_IDS_PER_REQUEST} ids per request')
        if source is not None and (not isinstance(source, str) or len(source) > MAX_SOURCE_LENGTH):
            raise ValueError(f'source must be text of at most {MAX_SOURCE_LENGTH} characters')

        result = {'queued': [], 'already': [], 'invalid': []}
        wanted = []
        for item_type, ids in (('track', tracks), ('album', albums)):
            for raw in ids:
                if isinstance(raw, int) and not isinstance(raw, bool):
                    raw = str(raw)
                if not isinstance(raw, str) or not ID_PATTERN.match(raw):
                    result['invalid'].append(f"{item_type}/{raw}")
                    continue
                if (item_type, raw) not in wanted:
                    wanted.append((item_type, raw))

        now = self.clock()
        tidal_log = self._read_tidal_log()
        with self.state_lock:
            to_queue = []
            for item_type, item_id in wanted:
                item = self.items.get(f"{item_type}/{item_id}")
                if item and (item['status'] in ('queued', 'downloading') or
                             (item['status'] == 'done' and now - item['updated_at'] <= RETRY_WINDOW)):
                    result['already'].append({'type': item_type, 'id': item_id, 'status': item['status']})
                    continue
                downloaded_at = tidal_log.get(canonical_url(item_type, item_id))
                if isinstance(downloaded_at, (int, float)) and now - downloaded_at <= RETRY_WINDOW:
                    result['already'].append({'type': item_type, 'id': item_id, 'status': 'done'})
                    continue
                to_queue.append((item_type, item_id))

            open_items = sum(1 for i in self.items.values() if i['status'] in ('queued', 'downloading'))
            if open_items + len(to_queue) > MAX_OPEN_ITEMS:
                raise OverflowError(f'queue is full (at most {MAX_OPEN_ITEMS} open items)')

            # A failed or older done item is simply queued again
            for item_type, item_id in to_queue:
                self.items[f"{item_type}/{item_id}"] = {
                    'type': item_type,
                    'id': item_id,
                    'status': 'queued',
                    'source': source,
                    'added_at': now,
                    'updated_at': now,
                    'attempts': 0,
                    'last_error': None,
                }
                result['queued'].append({'type': item_type, 'id': item_id})

            if to_queue:
                self._save()

        if to_queue:
            logger.info(f"Queue: added {len(to_queue)} item(s)" + (f" from {source}" if source else ""))
            self.wake()
        return result

    def _update(self, key, **fields):
        with self.state_lock:
            item = self.items.get(key)
            if item:
                item.update(fields, updated_at=self.clock())
                self._save()
            return item

    # ---- worker ----

    def wake(self):
        self.wake_event.set()

    def tidal_auth(self):
        """ok / missing / unknown, from the auth file only (no call to Tidal)"""
        if not self.auth_file.exists():
            return 'missing'
        try:
            return 'ok' if json.loads(self.auth_file.read_text()).get('token') else 'unknown'
        except Exception:
            return 'unknown'

    def _check_auth(self):
        """
        tiddl exits 0 even when it is not authenticated, so check up front like
        download.sh does, otherwise every item would be marked done.
        """
        if self.tidal_auth() != 'ok':
            logger.error("Queue: tiddl is not authenticated. Run 'tiddl auth login' inside the container.")
            return False
        try:
            refresh = subprocess.run(self.tiddl_cmd + ['auth', 'refresh'], capture_output=True, text=True, timeout=120)
        except Exception as e:
            logger.error(f"Queue: tiddl auth refresh failed: {e}")
            return False
        if refresh.returncode != 0 or 'not logged in' in (refresh.stdout + refresh.stderr).lower():
            logger.error("Queue: tiddl token is no longer valid. Run 'tiddl auth login' inside the container.")
            return False
        return True

    def _run_tiddl(self, key, url):
        """Run tiddl for one link, streaming output to stdout. Returns (success, error)"""
        process = subprocess.Popen(
            self.tiddl_cmd + ['download', '--raise-errors', 'url', url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True  # own process group, so a timeout also kills its children
        )

        timed_out = threading.Event()

        def kill_on_timeout():
            timed_out.set()
            os.killpg(process.pid, signal.SIGKILL)

        timer = threading.Timer(self.timeout, kill_on_timeout)
        timer.start()
        last_line = ''
        try:
            for line in process.stdout:
                line = line.rstrip('\n')
                if line.strip():
                    last_line = line.strip()
                print(f"  [queue {key}] {line}", flush=True)
            process.wait()
        finally:
            timer.cancel()
            process.stdout.close()

        if timed_out.is_set():
            return False, 'Timeout (exceeded 2 hours)'
        if process.returncode != 0:
            return False, (last_line or f"exit code {process.returncode}")[:200]
        return True, None

    def drain(self):
        """Try every queued item once"""
        now = self.clock()
        with self.state_lock:
            # Retried for 48 hours after it was asked for, then given up on
            for item in self.items.values():
                if item['status'] == 'queued' and item['attempts'] > 0 and now - item['added_at'] > RETRY_WINDOW:
                    item['status'] = 'failed'
                    item['updated_at'] = now
            self._save()
            keys = [k for k, i in sorted(self.items.items(), key=lambda kv: kv[1]['added_at']) if i['status'] == 'queued']

        if not keys:
            return

        logger.info(f"Queue: processing {len(keys)} item(s)")
        with self.lock:
            if not self._check_auth():
                return

        done = failed = 0
        for key in keys:
            # Take the lock per item, so a scheduled run can get in between
            with self.lock:
                with self.state_lock:
                    item = self.items.get(key)
                    if not item or item['status'] != 'queued':
                        continue  # deleted or changed in the meantime
                    item.update(status='downloading', updated_at=self.clock())
                    self._save()
                    url = canonical_url(item['type'], item['id'])

                logger.info(f"Queue: downloading {url}")
                try:
                    success, error = self._run_tiddl(key, url)
                except Exception as e:
                    success, error = False, str(e)[:200]

                if success:
                    self._record_tidal_log(url)
                    self._update(key, status='done', last_error=None)
                    logger.info(f"Queue: ✓ downloaded {url}")
                    done += 1
                else:
                    with self.state_lock:
                        item = self.items.get(key)
                        if item:
                            item['attempts'] += 1
                            item['last_error'] = error
                            item['updated_at'] = self.clock()
                            expired = item['updated_at'] - item['added_at'] > RETRY_WINDOW
                            item['status'] = 'failed' if expired else 'queued'
                            self._save()
                    logger.warning(f"Queue: ✗ download failed for {url}: {error}")
                    failed += 1

        logger.info(f"Queue: finished, {done} downloaded, {failed} failed")

    def worker_loop(self):
        while True:
            self.wake_event.wait()
            self.wake_event.clear()
            try:
                self.drain()
            except Exception as e:
                logger.error(f"Queue: worker error: {e}")


# ---- HTTP API ----

def make_handler(queue, token=None, next_run=lambda: None):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'TidalDownloaderQueue/1'

        def log_message(self, format, *args):
            pass  # keep the container logs for downloads, not for every request

        def _send(self, status, body=None):
            data = b'' if body is None else json.dumps(body).encode()
            self.send_response(status)
            if body is not None:
                self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)

        def _error(self, status, message):
            self._send(status, {'error': message})

        def _authorized(self):
            if not token:
                return True
            header = self.headers.get('Authorization', '')
            expected = f"Bearer {token}"
            if hmac.compare_digest(header.encode(), expected.encode()):
                return True
            self._error(401, 'unauthorized')
            return False

        def _item_path(self, parts):
            """/queue/<type>/<id> -> (type, id) or None"""
            if len(parts) == 3 and parts[0] == 'queue' and parts[1] in TYPES and ID_PATTERN.match(parts[2]):
                return parts[1], parts[2]
            return None

        def _route(self):
            url = urlparse(self.path)
            return url, [p for p in url.path.split('/') if p]

        def do_GET(self):
            if not self._authorized():
                return
            url, parts = self._route()

            if parts == ['health']:
                next_run_time = next_run()
                return self._send(200, {
                    'ok': True,
                    'running': queue.lock.locked(),
                    'queued': len(queue.list_items('queued')),
                    'next_scheduled_run': next_run_time.isoformat() if next_run_time else None,
                    'tidal_auth': queue.tidal_auth(),
                })

            if parts == ['queue']:
                status = parse_qs(url.query).get('status', [None])[0]
                if status is not None and status not in STATUSES:
                    return self._error(400, f"status must be one of {', '.join(STATUSES)}")
                return self._send(200, {'items': queue.list_items(status)})

            target = self._item_path(parts)
            if target:
                item = queue.get(*target)
                return self._send(200, item) if item else self._error(404, 'not found')

            self._error(404, 'not found')

        def do_POST(self):
            if not self._authorized():
                return
            _, parts = self._route()
            if parts != ['queue']:
                return self._error(404, 'not found')

            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                return self._error(400, 'invalid Content-Length')
            if length > MAX_BODY_BYTES:
                return self._error(413, 'request body too large')
            try:
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._error(400, 'body must be a JSON object')

            try:
                result = queue.add(body.get('tracks'), body.get('albums'), body.get('source'))
            except ValueError as e:
                return self._error(400, str(e))
            except OverflowError as e:
                return self._error(429, str(e))
            self._send(202, result)

        def do_DELETE(self):
            if not self._authorized():
                return
            _, parts = self._route()
            target = self._item_path(parts)
            if not target:
                return self._error(404, 'not found')

            outcome = queue.delete(*target)
            if outcome == 'deleted':
                return self._send(204)
            if outcome == 'downloading':
                return self._error(409, 'item is downloading')
            self._error(404, 'not found')

    return Handler


def start_api(port, config_dir, token=None, next_run=lambda: None, host='0.0.0.0', **queue_options):
    """Start the HTTP server and the worker as daemon threads. Returns (queue, server)"""
    queue = DownloadQueue(config_dir, **queue_options)
    server = ThreadingHTTPServer((host, port), make_handler(queue, token, next_run))
    server.daemon_threads = True

    threading.Thread(target=server.serve_forever, name='queue-api', daemon=True).start()
    threading.Thread(target=queue.worker_loop, name='queue-worker', daemon=True).start()

    # Pick up whatever was left in the queue before a restart
    queue.wake()
    return queue, server
