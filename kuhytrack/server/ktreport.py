"""kuhytrack reports: per-device summary, timeline and habit streaks.

Split out of kt_server.py to keep each file under 250 lines.
"""

from __future__ import annotations

import json
from datetime import timedelta

from ktstore import bucket_row_to_dict, db, fmt_ts, now, parse_ts

AFK_TYPES = ("afkstatus",)


def summary(start=None, end=None, device=None, top=25) -> dict:
    end_dt = parse_ts(end) if end else now()
    start_dt = parse_ts(start) if start else end_dt - timedelta(days=1)
    args_win = (fmt_ts(start_dt), fmt_ts(end_dt))
    buckets = [bucket_row_to_dict(r) for r in db().execute("SELECT * FROM buckets")]
    if device:
        buckets = [b for b in buckets if b["device"] == device]

    per_device: dict = {}
    per_app: dict = {}
    per_type: dict = {}
    intervals: list = []
    for b in buckets:
        rows = (
            db()
            .execute(
                "SELECT timestamp,duration,data FROM events WHERE bucket_id=? "
                "AND timestamp>=? AND timestamp<=?",
                (b["id"], *args_win),
            )
            .fetchall()
        )
        if b["type"] in ("currentwindow", "app.usage", "android.usage"):
            for r in rows:
                t0 = parse_ts(r["timestamp"]).timestamp()
                intervals.append((t0, t0 + float(r["duration"])))
        tot = sum(float(r["duration"]) for r in rows)
        per_type[b["type"]] = per_type.get(b["type"], 0) + tot
        if b["type"] in ("currentwindow", "app.usage", "android.usage"):
            d = per_device.setdefault(b["device"], {"seconds": 0.0, "apps": {}})
            d["seconds"] += tot
            for r in rows:
                data = json.loads(r["data"])
                app = data.get("app") or data.get("package") or data.get("title") or "?"
                d["apps"][app] = d["apps"].get(app, 0) + float(r["duration"])
                per_app[app] = per_app.get(app, 0) + float(r["duration"])
    for d in per_device.values():
        d["apps"] = dict(sorted(d["apps"].items(), key=lambda kv: -kv[1])[:top])
    # wall-clock time where *any* device was active: phone + laptop overlap, so summing
    # per-device totals double-counts. Both numbers are useful; report both.
    union = 0.0
    cur_s = cur_e = None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            union += (cur_e - cur_s) if cur_e is not None else 0
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        union += cur_e - cur_s
    return {
        "start": fmt_ts(start_dt),
        "end": fmt_ts(end_dt),
        "union_seconds": union,
        "total_seconds": sum(d["seconds"] for d in per_device.values()),
        "per_device": per_device,
        "per_type": per_type,
        "top_apps": dict(sorted(per_app.items(), key=lambda kv: -kv[1])[:top]),
        "devices": sorted({b["device"] for b in buckets}),
    }


def timeline(start=None, end=None, device=None, limit=2000) -> list:
    end_dt = parse_ts(end) if end else now()
    start_dt = parse_ts(start) if start else end_dt - timedelta(days=1)
    q = (
        "SELECT e.timestamp,e.duration,e.data,b.device,b.type,b.id AS bucket "
        "FROM events e JOIN buckets b ON b.id=e.bucket_id "
        "WHERE e.timestamp>=? AND e.timestamp<=?"
    )
    args = [fmt_ts(start_dt), fmt_ts(end_dt)]
    if device:
        q += " AND b.device=?"
        args.append(device)
    q += " ORDER BY e.timestamp DESC LIMIT ?"
    args.append(int(limit))
    out = []
    for r in db().execute(q, args):
        data = json.loads(r["data"])
        out.append(
            {
                "timestamp": r["timestamp"],
                "duration": r["duration"],
                "device": r["device"],
                "type": r["type"],
                "bucket": r["bucket"],
                "app": data.get("app") or data.get("package"),
                "title": data.get("title") or data.get("classname"),
                "status": data.get("status"),
                "data": data,
            }
        )
    return out


def streak(days: list) -> int:
    """Consecutive-day streak ending today or yesterday."""
    if not days:
        return 0
    s = set(days)
    d = now().date()
    if d.isoformat() not in s:
        d = d - timedelta(days=1)
        if d.isoformat() not in s:
            return 0
    n = 0
    while d.isoformat() in s:
        n += 1
        d -= timedelta(days=1)
    return n
