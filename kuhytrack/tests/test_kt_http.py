#!/usr/bin/env python3
"""python3 tests/test_kt_http.py  -- the real server process, over HTTP.

Split out of test_kt.py (250-line cap). Auth, the unauthenticated dashboard shell,
and the bucket/event/habit routes, each against a freshly spawned server.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
TMP = Path(tempfile.mkdtemp())
os.environ["KT_DB"] = str(TMP / "test.db")
os.environ["KT_TOKEN"] = ""
import kt_server as kt  # noqa: E402

T0 = datetime(2026, 8, 8, 10, 0, 0, tzinfo=timezone.utc)


def ts(offset_s):
    return kt.fmt_ts(T0 + timedelta(seconds=offset_s))


class HttpApi(unittest.TestCase):
    proc = None
    port = 5699

    @classmethod
    def setUpClass(cls):
        env = dict(
            os.environ,
            KT_DB=str(TMP / "http.db"),
            KT_PORT=str(cls.port),
            KT_TOKEN="testtoken",
            KT_HOST="127.0.0.1",
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "server" / "kt_server.py")],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/health", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()

    def req(self, method, path, body=None, token="testtoken"):
        r = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.loads(resp.read() or b"null")

    def test_auth_required(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.req("GET", "/api/0/buckets/", token=None)
        self.assertEqual(cm.exception.code, 401)

    def raw(self, path, token=None):
        """Fetch without JSON-decoding, the way a browser asks for a page."""
        r = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()

    def test_dashboard_served_without_token(self):
        """A browser navigating to / sends no Authorization header. If the shell were
        gated, the page holding the 'set token' button would 401 and the dashboard
        would be permanently unreachable."""
        status, ctype, body = self.raw("/", token=None)
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b'id="tok"', body)  # the token button, not its wording

    def test_api_still_gated_without_token(self):
        """Serving the shell must not have opened up the data behind it."""
        for path in ("/api/0/buckets/", "/api/0/kt/summary", "/api/0/export"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.raw(path, token=None)
            self.assertEqual(cm.exception.code, 401, f"{path} should require a token")

    def test_full_watcher_flow(self):
        self.req(
            "POST",
            "/api/0/buckets/aw-watcher-window_test",
            {
                "client": "aw-watcher-window",
                "type": "currentwindow",
                "hostname": "test",
            },
        )
        for i in range(3):
            self.req(
                "POST",
                "/api/0/buckets/aw-watcher-window_test/heartbeat?pulsetime=60",
                {
                    "timestamp": ts(i * 5),
                    "duration": 0,
                    "data": {"app": "kitty", "title": "zsh"},
                },
            )
        evs = self.req("GET", "/api/0/buckets/aw-watcher-window_test/events")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["duration"], 10)
        self.assertEqual(
            self.req("GET", "/api/0/buckets/aw-watcher-window_test/events/count"), 1
        )
        exp = self.req("GET", "/api/0/export")
        self.assertIn("aw-watcher-window_test", exp["buckets"])

    def test_habits_and_streak(self):
        h = self.req("POST", "/api/0/kt/habits", {"name": "5x5 squats"})
        today = datetime.now(timezone.utc).date()
        for d in range(3):
            self.req(
                "POST",
                f"/api/0/kt/habits/{h['id']}/tick",
                {"day": (today - timedelta(days=d)).isoformat()},
            )
        hs = [x for x in self.req("GET", "/api/0/kt/habits") if x["id"] == h["id"]][0]
        self.assertEqual(hs["streak"], 3)

    def test_unknown_bucket_heartbeat_404s(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.req(
                "POST",
                "/api/0/buckets/nope/heartbeat",
                {"timestamp": ts(0), "data": {}},
            )
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
