"""kuhytrack read routes (GET), mixed into kt_server.Handler."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from ktreport import streak, summary, timeline
from ktstore import (
    HOSTNAME,
    VERSION,
    WEB_DIR,
    bucket_row_to_dict,
    db,
    get_bucket,
    get_events,
)


class GetRoutes:
    """GET handler; relies on Handler's _send/_authed."""

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path.rstrip("/") or "/", parse_qs(u.query)
        if p == "/health":
            return self._send(200, {"ok": True, "version": VERSION})
        # The dashboard shell is served unauthenticated on purpose. It carries no data —
        # it fetches everything from /api/0/*, which stays gated below — and it keeps the
        # token in localStorage. A browser navigating here sends no Authorization header,
        # so gating this would 401 the very page holding the "set token" button, leaving
        # no way to enter the token and no way to reach the dashboard at all.
        if p == "/" or p == "/index.html":
            f = WEB_DIR / "dashboard.html"
            if f.exists():
                return self._send(
                    200, raw=f.read_bytes(), ctype="text/html; charset=utf-8"
                )
            return self._send(404, {"error": "no dashboard"})
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        try:
            if p == "/api/0/info":
                return self._send(
                    200,
                    {
                        "hostname": HOSTNAME,
                        "version": VERSION,
                        "testing": False,
                        "device_id": HOSTNAME,
                    },
                )
            if p == "/api/0/buckets":
                return self._send(
                    200,
                    {
                        b["id"]: b
                        for b in (
                            bucket_row_to_dict(r)
                            for r in db().execute("SELECT * FROM buckets")
                        )
                    },
                )
            m = re.fullmatch(r"/api/0/buckets/([^/]+)", p)
            if m:
                b = get_bucket(m.group(1))
                return (
                    self._send(200, b)
                    if b
                    else self._send(404, {"error": "no such bucket"})
                )
            m = re.fullmatch(r"/api/0/buckets/([^/]+)/events", p)
            if m:
                return self._send(
                    200,
                    get_events(
                        m.group(1),
                        limit=int(q.get("limit", [-1])[0]),
                        start=q.get("start", [None])[0],
                        end=q.get("end", [None])[0],
                    ),
                )
            m = re.fullmatch(r"/api/0/buckets/([^/]+)/events/count", p)
            if m:
                r = (
                    db()
                    .execute(
                        "SELECT COUNT(*) c FROM events WHERE bucket_id=?", (m.group(1),)
                    )
                    .fetchone()
                )
                return self._send(200, r["c"])
            if p == "/api/0/export":
                out = {}
                for r in db().execute("SELECT * FROM buckets"):
                    b = bucket_row_to_dict(r)
                    b["events"] = get_events(b["id"])
                    out[b["id"]] = b
                return self._send(200, {"buckets": out})
            if p == "/api/0/kt/summary":
                return self._send(
                    200,
                    summary(
                        q.get("start", [None])[0],
                        q.get("end", [None])[0],
                        q.get("device", [None])[0],
                        int(q.get("top", [25])[0]),
                    ),
                )
            if p == "/api/0/kt/timeline":
                return self._send(
                    200,
                    timeline(
                        q.get("start", [None])[0],
                        q.get("end", [None])[0],
                        q.get("device", [None])[0],
                        int(q.get("limit", [2000])[0]),
                    ),
                )
            if p == "/api/0/kt/habits":
                habits = []
                for r in db().execute(
                    "SELECT * FROM habits WHERE archived=0 ORDER BY id"
                ):
                    ticks = [
                        t["day"]
                        for t in db().execute(
                            "SELECT day FROM habit_ticks WHERE habit_id=? ORDER BY day DESC LIMIT 400",
                            (r["id"],),
                        )
                    ]
                    habits.append(
                        {
                            "id": r["id"],
                            "name": r["name"],
                            "created": r["created"],
                            "meta": json.loads(r["meta"] or "{}"),
                            "ticks": ticks,
                            "streak": streak(ticks),
                        }
                    )
                return self._send(200, habits)
            if p == "/api/0/kt/sessions":
                return self._send(
                    200,
                    [
                        dict(r)
                        for r in db().execute(
                            "SELECT * FROM sessions ORDER BY start DESC LIMIT 500"
                        )
                    ],
                )
            return self._send(404, {"error": "no route", "path": p})
        except ValueError as e:  # bad timestamp/int in the query string
            return self._send(
                400,
                {
                    "error": "bad request",
                    "detail": str(e),
                    "hint": "url-encode ISO offsets: '+' becomes a space",
                },
            )
        except Exception as e:  # noqa: BLE001 — an activity server must never die
            return self._send(500, {"error": type(e).__name__, "detail": str(e)})
