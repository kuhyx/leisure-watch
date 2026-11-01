"""kuhytrack write routes (POST, DELETE), mixed into kt_server.Handler."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from ktstore import (
    HOSTNAME,
    create_bucket,
    db,
    fmt_ts,
    get_bucket,
    heartbeat,
    insert_event,
    now,
    parse_ts,
)


class WriteRoutes:
    """POST/DELETE handlers; rely on Handler's _send/_authed/_body."""

    def do_POST(self):
        u = urlparse(self.path)
        p, q = u.path.rstrip("/") or "/", parse_qs(u.query)
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        body = self._body()
        try:
            m = re.fullmatch(r"/api/0/buckets/([^/]+)", p)
            if m:
                create_bucket(m.group(1), body if isinstance(body, dict) else {})
                return self._send(200, get_bucket(m.group(1)))
            m = re.fullmatch(r"/api/0/buckets/([^/]+)/events", p)
            if m:
                bid = m.group(1)
                if not get_bucket(bid):
                    return self._send(404, {"error": "no such bucket"})
                evs = body if isinstance(body, list) else [body]
                return self._send(200, [insert_event(bid, e) for e in evs])
            m = re.fullmatch(r"/api/0/buckets/([^/]+)/heartbeat", p)
            if m:
                bid = m.group(1)
                if not get_bucket(bid):
                    return self._send(404, {"error": "no such bucket"})
                pulse = float(q.get("pulsetime", ["60"])[0])
                return self._send(200, heartbeat(bid, body, pulse))
            if p == "/api/0/import":
                n = 0
                for bid, b in (body.get("buckets") or {}).items():
                    create_bucket(bid, b)
                    for e in b.get("events", []):
                        insert_event(bid, e)
                        n += 1
                return self._send(200, {"imported_events": n})
            if p == "/api/0/kt/habits":
                db().execute(
                    "INSERT OR IGNORE INTO habits(name,created,meta) VALUES(?,?,?)",
                    (body["name"], fmt_ts(now()), json.dumps(body.get("meta") or {})),
                )
                r = (
                    db()
                    .execute("SELECT * FROM habits WHERE name=?", (body["name"],))
                    .fetchone()
                )
                return self._send(200, {"id": r["id"], "name": r["name"]})
            m = re.fullmatch(r"/api/0/kt/habits/(\d+)/tick", p)
            if m:
                day = body.get("day") or now().strftime("%Y-%m-%d")
                if body.get("value") == 0:
                    db().execute(
                        "DELETE FROM habit_ticks WHERE habit_id=? AND day=?",
                        (m.group(1), day),
                    )
                else:
                    db().execute(
                        "INSERT OR REPLACE INTO habit_ticks(habit_id,day,value,ts,device)"
                        " VALUES(?,?,?,?,?)",
                        (
                            m.group(1),
                            day,
                            body.get("value", 1),
                            fmt_ts(now()),
                            body.get("device") or HOSTNAME,
                        ),
                    )
                return self._send(200, {"ok": True, "day": day})
            if p == "/api/0/kt/sessions":
                cur = db().execute(
                    "INSERT INTO sessions(kind,tag,device,start,end,notes) VALUES(?,?,?,?,?,?)",
                    (
                        body.get("kind", "focus"),
                        body.get("tag"),
                        body.get("device") or HOSTNAME,
                        fmt_ts(parse_ts(body["start"])),
                        fmt_ts(parse_ts(body["end"])) if body.get("end") else None,
                        body.get("notes"),
                    ),
                )
                return self._send(200, {"id": cur.lastrowid})
            return self._send(404, {"error": "no route", "path": p})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": type(e).__name__, "detail": str(e)})

    def do_DELETE(self):
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        m = re.fullmatch(
            r"/api/0/buckets/([^/]+)", urlparse(self.path).path.rstrip("/")
        )
        if m:
            db().execute("DELETE FROM events WHERE bucket_id=?", (m.group(1),))
            db().execute("DELETE FROM buckets WHERE id=?", (m.group(1),))
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "no route"})
