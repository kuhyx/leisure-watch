"""kuhytrack storage: config, time helpers, sqlite schema, buckets, events, heartbeat.

Split out of kt_server.py to keep each file under 250 lines. Pure stdlib.
Env (KT_DB, KT_HOST, KT_PORT, KT_TOKEN, KT_WEB) is read once at import.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = "kuhytrack 0.1.0"
DB_PATH = Path(
    os.environ.get("KT_DB", Path.home() / ".local/share/kuhytrack/kt.db")
).expanduser()
HOST = os.environ.get("KT_HOST", "127.0.0.1")
PORT = int(os.environ.get("KT_PORT", "5600"))
TOKEN = os.environ.get("KT_TOKEN", "")
WEB_DIR = Path(os.environ.get("KT_WEB", Path(__file__).resolve().parent.parent / "web"))
HOSTNAME = socket.gethostname()

# ---------------------------------------------------------------- time helpers

ISO_Z = "%Y-%m-%dT%H:%M:%S.%f%z"


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(s) -> datetime:
    """Accept anything ActivityWatch watchers emit."""
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    s = str(s).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # 2024-01-01T10:00:00.123456789+00:00 -> trim ns to us
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------- schema

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS buckets (
  id TEXT PRIMARY KEY, created TEXT, name TEXT, type TEXT, client TEXT,
  hostname TEXT, device TEXT, data TEXT DEFAULT '{}', last_updated TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bucket_id TEXT NOT NULL, timestamp TEXT NOT NULL, duration REAL NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(bucket_id) REFERENCES buckets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_events_bucket_ts ON events(bucket_id, timestamp DESC);
CREATE TABLE IF NOT EXISTS habits (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
  created TEXT, meta TEXT DEFAULT '{}', archived INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS habit_ticks (
  habit_id INTEGER NOT NULL, day TEXT NOT NULL, value REAL DEFAULT 1,
  ts TEXT, device TEXT, PRIMARY KEY(habit_id, day)
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, tag TEXT, device TEXT,
  start TEXT, end TEXT, notes TEXT
);
"""

_local = threading.local()


def db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _local.conn = conn
    return conn


# ------------------------------------------------------------------ core logic


def bucket_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "created": r["created"],
        "name": r["name"],
        "type": r["type"],
        "client": r["client"],
        "hostname": r["hostname"],
        "device": r["device"],
        "data": json.loads(r["data"] or "{}"),
        "last_updated": r["last_updated"],
    }


def get_bucket(bid: str):
    r = db().execute("SELECT * FROM buckets WHERE id=?", (bid,)).fetchone()
    return bucket_row_to_dict(r) if r else None


def create_bucket(bid: str, body: dict):
    hostname = body.get("hostname") or "unknown"
    db().execute(
        "INSERT OR IGNORE INTO buckets(id,created,name,type,client,hostname,device,data,last_updated)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (
            bid,
            body.get("created") or fmt_ts(now()),
            body.get("name") or bid,
            body.get("type") or "unknown",
            body.get("client") or "unknown",
            hostname,
            body.get("device") or hostname,
            json.dumps(body.get("data") or {}),
            fmt_ts(now()),
        ),
    )


def row_to_event(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "timestamp": r["timestamp"],
        "duration": r["duration"],
        "data": json.loads(r["data"]),
    }


def get_events(bid: str, limit=-1, start=None, end=None) -> list:
    q = "SELECT * FROM events WHERE bucket_id=?"
    args: list = [bid]
    if start:
        q += " AND timestamp >= ?"
        args.append(fmt_ts(parse_ts(start)))
    if end:
        q += " AND timestamp <= ?"
        args.append(fmt_ts(parse_ts(end)))
    q += " ORDER BY timestamp DESC"
    if limit and int(limit) > 0:
        q += " LIMIT ?"
        args.append(int(limit))
    return [row_to_event(r) for r in db().execute(q, args)]


def insert_event(bid: str, ev: dict) -> dict:
    ts = fmt_ts(parse_ts(ev["timestamp"]))
    dur = float(ev.get("duration") or 0)
    data = json.dumps(ev.get("data") or {}, sort_keys=True)
    cur = db().execute(
        "INSERT INTO events(bucket_id,timestamp,duration,data) VALUES(?,?,?,?)",
        (bid, ts, dur, data),
    )
    db().execute("UPDATE buckets SET last_updated=? WHERE id=?", (fmt_ts(now()), bid))
    return {
        "id": cur.lastrowid,
        "timestamp": ts,
        "duration": dur,
        "data": json.loads(data),
    }


def heartbeat(bid: str, ev: dict, pulsetime: float) -> dict:
    """Exact port of aw-core aw_transform.heartbeats.heartbeat_merge.

    Merge iff data is identical AND
    last.timestamp <= hb.timestamp <= last.timestamp + last.duration + pulsetime.
    New duration = max(old, (hb.ts - last.ts) + hb.duration).
    """
    hb_ts = parse_ts(ev["timestamp"])
    hb_dur = float(ev.get("duration") or 0)
    hb_data = json.dumps(ev.get("data") or {}, sort_keys=True)

    last = (
        db()
        .execute(
            "SELECT * FROM events WHERE bucket_id=? ORDER BY timestamp DESC, id DESC LIMIT 1",
            (bid,),
        )
        .fetchone()
    )
    if last is not None and last["data"] == hb_data:
        last_ts = parse_ts(last["timestamp"])
        last_dur = float(last["duration"])
        if last_dur >= 0:
            window_end = last_ts + timedelta(seconds=last_dur + pulsetime)
            if last_ts <= hb_ts <= window_end:
                new_dur = max(last_dur, (hb_ts - last_ts).total_seconds() + hb_dur)
                db().execute(
                    "UPDATE events SET duration=? WHERE id=?", (new_dur, last["id"])
                )
                db().execute(
                    "UPDATE buckets SET last_updated=? WHERE id=?", (fmt_ts(now()), bid)
                )
                return {
                    "id": last["id"],
                    "timestamp": last["timestamp"],
                    "duration": new_dur,
                    "data": json.loads(hb_data),
                }
    return insert_event(
        bid,
        {"timestamp": fmt_ts(hb_ts), "duration": hb_dur, "data": json.loads(hb_data)},
    )
