"""
Tests for the queue API, with tiddl replaced by a fake script.
Run from the repository root: python3 -m unittest
"""

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'copy-files'))

import download_queue as dq  # noqa: E402

# Succeeds unless the link's id is listed in fail_ids.txt next to it
FAKE_TIDDL = '''
import sys
from pathlib import Path
args = sys.argv[1:]
if args[0] == 'auth':
    print('token refreshed')
    sys.exit(0)
fail_ids = (Path(__file__).parent / 'fail_ids.txt').read_text().split()
link = args[-1]
print(f'downloading {link}')
if link.rsplit('/', 1)[-1] in fail_ids:
    print('Error: track not available')
    sys.exit(1)
print('done')
'''


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class QueueTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.auth_file = self.dir / 'auth.json'
        self.auth_file.write_text(json.dumps({'token': 'x'}))
        (self.dir / 'fake_tiddl.py').write_text(FAKE_TIDDL)
        self.fail_ids = self.dir / 'fail_ids.txt'
        self.fail_ids.write_text('')
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def make_queue(self):
        return dq.DownloadQueue(
            self.dir,
            tiddl_cmd=[sys.executable, str(self.dir / 'fake_tiddl.py')],
            auth_file=self.auth_file,
            lock=threading.Lock(),
            clock=self.clock,
        )


class TestQueueLogic(QueueTestCase):
    def test_validation_and_dedupe(self):
        q = self.make_queue()
        result = q.add(['1', '1', 'abc', 2], ['3', '-4'], 'woodhouse')
        self.assertEqual(result['queued'], [
            {'type': 'track', 'id': '1'}, {'type': 'track', 'id': '2'}, {'type': 'album', 'id': '3'}])
        self.assertEqual(result['invalid'], ['track/abc', 'album/-4'])

        again = q.add(['1'], None)
        self.assertEqual(again['queued'], [])
        self.assertEqual(again['already'], [{'type': 'track', 'id': '1', 'status': 'queued'}])

        # Track 1 and album 1 are different items
        self.assertEqual(q.add(None, ['1'])['queued'], [{'type': 'album', 'id': '1'}])

    def test_labels(self):
        q = self.make_queue()
        result = q.add([{'id': '5', 'label': 'Kokoroko - Age Of Ascent'}, '6'], None, 'woodhouse')
        self.assertEqual(result['queued'], [{'type': 'track', 'id': '5'}, {'type': 'track', 'id': '6'}])
        self.assertEqual(q.get('track', '5')['label'], 'Kokoroko - Age Of Ascent')
        self.assertIsNone(q.get('track', '6')['label'])
        self.assertEqual(q.add([{'id': 'x'}], None)['invalid'], ['track/x'])
        with self.assertRaises(ValueError):
            q.add([{'id': '7', 'label': 'x' * 201}], None)

    def test_bad_requests(self):
        q = self.make_queue()
        with self.assertRaises(ValueError):
            q.add(None, None)
        with self.assertRaises(ValueError):
            q.add('123', None)
        with self.assertRaises(ValueError):
            q.add([str(i) for i in range(101)], None)
        with self.assertRaises(ValueError):
            q.add(['1'], None, 'x' * 41)
        q.add([str(i) for i in range(100)], None, 'x' * 40)

    def test_open_item_limit(self):
        q = self.make_queue()
        for start in range(0, 1000, 100):
            q.add([str(i) for i in range(start, start + 100)], None)
        with self.assertRaises(OverflowError):
            q.add(['5000'], None)
        # Already queued ids do not count against the limit
        self.assertEqual(len(q.add(['1'], None)['already']), 1)

    def test_tidal_log_counts_as_already(self):
        url = dq.canonical_url('track', '7')
        (self.dir / 'tidal_dl_logs.json').write_text(json.dumps({url: int(self.clock.now) - 3600}))
        q = self.make_queue()
        self.assertEqual(q.add(['7'], None)['already'], [{'type': 'track', 'id': '7', 'status': 'done'}])

        # Downloaded longer than 48 hours ago: queue it again
        (self.dir / 'tidal_dl_logs.json').write_text(json.dumps({url: int(self.clock.now) - 49 * 3600}))
        self.assertEqual(q.add(['7'], None)['queued'], [{'type': 'track', 'id': '7'}])

    def test_drain_success_and_failure(self):
        self.fail_ids.write_text('2')
        q = self.make_queue()
        q.add(['1', '2'], ['3'])
        q.drain()

        self.assertEqual(q.get('track', '1')['status'], 'done')
        self.assertEqual(q.get('album', '3')['status'], 'done')
        failed = q.get('track', '2')
        self.assertEqual(failed['status'], 'queued')
        self.assertEqual(failed['attempts'], 1)
        self.assertEqual(failed['last_error'], 'Error: track not available')

        log = json.loads((self.dir / 'tidal_dl_logs.json').read_text())
        self.assertIn(dq.canonical_url('track', '1'), log)
        self.assertIn(dq.canonical_url('album', '3'), log)
        self.assertNotIn(dq.canonical_url('track', '2'), log)

        # Done within 48 hours is "already"
        self.assertEqual(q.add(['1'], None)['already'][0]['status'], 'done')

        # Retried on the next drain, then succeeds
        self.fail_ids.write_text('')
        q.drain()
        self.assertEqual(q.get('track', '2')['status'], 'done')
        self.assertIsNone(q.get('track', '2')['last_error'])

    def test_failed_after_48_hours(self):
        self.fail_ids.write_text('2')
        q = self.make_queue()
        q.add(['2'], None)
        q.drain()
        self.clock.now += 47 * 3600
        q.drain()
        self.assertEqual(q.get('track', '2')['status'], 'queued')
        self.assertEqual(q.get('track', '2')['attempts'], 2)

        # Past 48 hours it is given up on without another attempt
        self.clock.now += 2 * 3600
        q.drain()
        self.assertEqual(q.get('track', '2')['status'], 'failed')
        self.assertEqual(q.get('track', '2')['attempts'], 2)

        # A failed item can be asked for again
        self.assertEqual(q.add(['2'], None)['queued'], [{'type': 'track', 'id': '2'}])
        self.assertEqual(q.get('track', '2')['attempts'], 0)

    def test_not_authenticated_leaves_items_alone(self):
        self.auth_file.unlink()
        q = self.make_queue()
        self.assertEqual(q.tidal_auth(), 'missing')
        q.add(['1'], None)
        q.drain()
        item = q.get('track', '1')
        self.assertEqual((item['status'], item['attempts']), ('queued', 0))

    def test_persistence_and_restart(self):
        q = self.make_queue()
        q.add(['1', '2'], None, 'woodhouse')
        q.items['track/2']['status'] = 'downloading'
        q._save()

        restarted = self.make_queue()
        self.assertEqual(restarted.get('track', '1')['source'], 'woodhouse')
        self.assertEqual(restarted.get('track', '2')['status'], 'queued')
        self.assertFalse((self.dir / 'download_queue.json.tmp').exists())

    def test_done_items_pruned_after_30_days(self):
        q = self.make_queue()
        q.add(['1'], None)
        q.drain()
        self.clock.now += 31 * 24 * 3600
        restarted = self.make_queue()
        self.assertIsNone(restarted.get('track', '1'))

    def test_delete(self):
        q = self.make_queue()
        q.add(['1', '2'], None)
        q.items['track/2']['status'] = 'downloading'
        self.assertEqual(q.delete('track', '1'), 'deleted')
        self.assertEqual(q.delete('track', '1'), 'not_found')
        self.assertEqual(q.delete('track', '2'), 'downloading')

    def test_timeout(self):
        (self.dir / 'fake_tiddl.py').write_text(
            "import sys, time\nif sys.argv[1] == 'auth': sys.exit(0)\ntime.sleep(30)\n")
        q = self.make_queue()
        q.timeout = 0.5
        q.add(['1'], None)
        q.drain()
        self.assertEqual(q.get('track', '1')['last_error'], 'Timeout (exceeded 2 hours)')


class TestHttpApi(QueueTestCase):
    def setUp(self):
        super().setUp()
        self.queue, self.server = dq.start_api(
            0, self.dir, token='secret', host='127.0.0.1',
            tiddl_cmd=[sys.executable, str(self.dir / 'fake_tiddl.py')],
            auth_file=self.auth_file, lock=threading.Lock())
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, method, path, body=None, token='secret'):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        if data:
            req.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, json.loads(raw) if raw else None

    def wait_for(self, path, status):
        for _ in range(100):
            _, item = self.request('GET', path)
            if item and item.get('status') == status:
                return item
            time.sleep(0.05)
        self.fail(f'{path} never became {status}')

    def test_auth(self):
        self.assertEqual(self.request('GET', '/health', token=None)[0], 401)
        self.assertEqual(self.request('GET', '/health', token='wrong')[0], 401)
        self.assertEqual(self.request('GET', '/health')[0], 200)

    def test_queue_flow(self):
        status, body = self.request('POST', '/queue', {'tracks': ['11', 'x'], 'albums': ['22'], 'source': 'woodhouse'})
        self.assertEqual(status, 202)
        self.assertEqual(body['queued'], [{'type': 'track', 'id': '11'}, {'type': 'album', 'id': '22'}])
        self.assertEqual(body['invalid'], ['track/x'])

        # The POST wakes the worker, which downloads with the fake tiddl
        item = self.wait_for('/queue/track/11', 'done')
        self.assertEqual(item['source'], 'woodhouse')
        self.wait_for('/queue/album/22', 'done')

        status, body = self.request('GET', '/queue?status=done')
        self.assertEqual((status, len(body['items'])), (200, 2))
        self.assertEqual(self.request('GET', '/queue?status=nope')[0], 400)

        status, health = self.request('GET', '/health')
        self.assertEqual(health, {'ok': True, 'running': False, 'queued': 0,
                                  'next_scheduled_run': None, 'tidal_auth': 'ok'})

        self.assertEqual(self.request('DELETE', '/queue/track/11')[0], 204)
        self.assertEqual(self.request('DELETE', '/queue/track/11')[0], 404)
        self.assertEqual(self.request('GET', '/queue/track/11')[0], 404)
        self.assertEqual(self.request('GET', '/queue/video/11')[0], 404)

    def test_bad_post(self):
        self.assertEqual(self.request('POST', '/queue', {})[0], 400)
        self.assertEqual(self.request('POST', '/queue', ['1'])[0], 400)
        self.assertEqual(self.request('POST', '/queue', {'tracks': [str(i) for i in range(101)]})[0], 400)
        self.assertEqual(self.request('POST', '/queue', {'tracks': ['1'], 'source': 'x' * 41})[0], 400)


if __name__ == '__main__':
    unittest.main()
