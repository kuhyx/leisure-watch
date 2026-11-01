"""kt-import wakapi: pull per-day project totals from a wakapi server."""

from __future__ import annotations

import base64
import urllib.parse
from datetime import datetime, timedelta, timezone

from ktimp_common import get_json, kt_call


def import_wakapi(args):
    """wakapi speaks the WakaTime API. /api/compat/wakatime/v1/users/current/summaries
    gives per-day project/language/editor totals. We store one event per project per day,
    typed app.editor.activity so it lines up with aw-watcher-vscode data if you add it."""
    key = base64.b64encode(args.key.encode()).decode()
    hdr = {"Authorization": f"Basic {key}"}
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=args.days)
    url = (
        args.url.rstrip("/")
        + "/api/compat/wakatime/v1/users/current/summaries?"
        + urllib.parse.urlencode({"start": start.isoformat(), "end": end.isoformat()})
    )
    data = get_json(url, hdr)

    bucket = f"kt-import-wakapi_{args.device}"
    kt_call(
        f"/api/0/buckets/{bucket}",
        "POST",
        {
            "client": "kt-import-wakapi",
            "type": "app.editor.activity",
            "hostname": args.device,
            "device": args.device,
        },
    )
    existing = {
        e["timestamp"] for e in kt_call(f"/api/0/buckets/{bucket}/events?limit=-1")
    }
    evs = []
    for day in data.get("data", []):
        d = day["range"]["date"]
        for proj in day.get("projects", []):
            ts = f"{d}T12:00:00.000Z"
            key_ts = ts
            if key_ts in existing and not args.force:
                continue
            langs = ", ".join(x["name"] for x in day.get("languages", [])[:3])
            evs.append(
                {
                    "timestamp": ts,
                    "duration": proj["total_seconds"],
                    "data": {
                        "app": "code",
                        "project": proj["name"],
                        "language": langs,
                        "title": proj["name"],
                        "source": "wakapi",
                    },
                }
            )
    if evs:
        kt_call(f"/api/0/buckets/{bucket}/events", "POST", evs)
    print(f"imported {len(evs)} project-days from wakapi into {bucket}")
