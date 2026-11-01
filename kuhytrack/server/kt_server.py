#!/usr/bin/env python3
"""
kuhytrack server — a stdlib-only, zero-dependency, ActivityWatch-API-compatible
activity store with first-class multi-device support.

Why stdlib only: it has to run as a systemd unit on Arch and inside Termux on a
Pixel with no pip, forever, without a dependency bumping and breaking it.
http.server + sqlite3 is more than enough for ~1 write/5s from 3 devices.

Wire-compatible with ActivityWatch's REST API (/api/0/...), so every existing
aw-watcher-* binary can point at this and Just Work. Extensions live under
/api/0/kt/ so they can never collide with upstream.

Run:  KT_DB=~/.local/share/kuhytrack/kt.db KT_TOKEN=secret python3 kt_server.py
Env:
  KT_DB      sqlite path         (default ~/.local/share/kuhytrack/kt.db)
  KT_HOST    bind host           (default 127.0.0.1)
  KT_PORT    bind port           (default 5600 — same as ActivityWatch)
  KT_TOKEN   bearer token        (default empty = no auth; set it if not on loopback)
  KT_WEB     dashboard dir       (default ../web next to this file)

Layout (split to keep every file under 250 lines; all siblings of this file, so
`python3 server/kt_server.py` finds them with no sys.path tricks):
  ktstore.py        config, time helpers, sqlite schema, buckets/events/heartbeat
  ktreport.py       summary, timeline, habit streaks
  ktroutes_get.py   GET routes     ktroutes_write.py  POST/DELETE routes
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ktreport import streak, summary, timeline
from ktroutes_get import GetRoutes
from ktroutes_write import WriteRoutes
from ktstore import (
    DB_PATH,
    HOST,
    PORT,
    TOKEN,
    VERSION,
    create_bucket,
    db,
    fmt_ts,
    get_events,
    heartbeat,
    insert_event,
    parse_ts,
)

# Names tests and tools import from here; listing them keeps the facade explicit.
__all__ = [
    "create_bucket",
    "db",
    "fmt_ts",
    "get_events",
    "heartbeat",
    "insert_event",
    "parse_ts",
    "streak",
    "summary",
    "timeline",
]


class Handler(GetRoutes, WriteRoutes, BaseHTTPRequestHandler):
    server_version = "kuhytrack"
    protocol_version = "HTTP/1.1"

    # ---- plumbing
    def log_message(self, fmt, *a):
        if os.environ.get("KT_VERBOSE"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))

    def _send(self, code, payload=None, ctype="application/json", raw=None):
        body = raw if raw is not None else json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _authed(self) -> bool:
        if not TOKEN:
            return True
        h = self.headers.get("Authorization", "")
        return h == f"Bearer {TOKEN}" or self.headers.get("X-Api-Key", "") == TOKEN

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        self._send(204, raw=b"")


def main():
    db()
    print(
        f"{VERSION} -> http://{HOST}:{PORT}  db={DB_PATH}  auth={'on' if TOKEN else 'OFF'}",
        flush=True,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
