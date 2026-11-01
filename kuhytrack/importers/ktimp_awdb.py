"""kt-import awdb: import straight from an aw-server sqlite file."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from ktimp_common import kt_call


def _bucket_window(dst):
    """Existing (min, max) timestamp in a target bucket, or (None, None).

    Deliberately NOT the `GET /events?limit=-1` dedupe that import_aw uses: a real
    aw-server db is ~137k events, which comes back as ~22 MB of JSON in a single body
    through stdlib http.server. Two aggregate queries cost nothing and make re-runs
    O(1) in payload instead of O(events).
    """
    try:
        r = kt_call(f"/api/0/buckets/{dst}/events?limit=1")
        if not r:
            return None, None
        newest = r[0]["timestamp"]
        oldest = kt_call(
            f"/api/0/buckets/{dst}/events?limit=-1&end={urllib.parse.quote(newest)}"
        )
        return (oldest[-1]["timestamp"] if oldest else newest), newest
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise


def import_awdb(args):
    """Import directly from an aw-server sqlite file (peewee-sqlite.v2.db).

    aw-server stores events as bucketmodel(key,id,type,client,hostname) joined to
    eventmodel(bucket_id,timestamp,duration,datastr). Opened read-only via a URI so the
    source database is never modified, and safe to run while aw-server is stopped --
    which is the normal case, since the alternative importers need it running.
    """
    import sqlite3

    src = Path(args.file).expanduser()
    if not src.exists():
        sys.exit(f"no such file: {src}")
    con = sqlite3.connect(f"file:{urllib.parse.quote(str(src))}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    cols = {r[1] for r in con.execute("PRAGMA table_info(bucketmodel)")}
    keycol = "key" if "key" in cols else "id"

    total = 0
    for b in con.execute(
        f"SELECT {keycol} AS pk, id, type, client, hostname FROM bucketmodel"
    ):
        dev = args.device or b["hostname"] or "imported"
        dst = b["id"] if b["id"].endswith(dev) else f"{b['id']}_{dev}"
        kt_call(
            f"/api/0/buckets/{dst}",
            "POST",
            {
                "client": b["client"] or "aw-import",
                "type": b["type"] or "currentwindow",
                "hostname": dev,
                "device": dev,
            },
        )

        lo, hi = _bucket_window(dst)
        n = skipped = 0
        batch = []
        for e in con.execute(
            "SELECT timestamp,duration,datastr FROM eventmodel WHERE bucket_id=?"
            " ORDER BY timestamp",
            (b["pk"],),
        ):
            ts = _norm_ts(e["timestamp"])
            # Anything inside the range already imported is a re-run; skip it. Events
            # outside that window (older backfill, newer data) still import.
            if lo and hi and lo <= _cmp_ts(ts) <= hi:
                skipped += 1
                continue
            try:
                data = json.loads(e["datastr"] or "{}")
            except json.JSONDecodeError:
                skipped += 1
                continue
            batch.append(
                {"timestamp": ts, "duration": e["duration"] or 0, "data": data}
            )
            if len(batch) >= 500:
                kt_call(f"/api/0/buckets/{dst}/events", "POST", batch)
                n += len(batch)
                batch = []
        if batch:
            kt_call(f"/api/0/buckets/{dst}/events", "POST", batch)
            n += len(batch)
        print(f"  {b['id']:<40} -> {dst:<42} +{n} (skipped {skipped})")
        total += n
    con.close()
    print(f"imported {total} events")


def _norm_ts(s):
    """aw-server writes '2025-07-07 08:29:07.636000+00:00'; the API wants ISO-T form."""
    return str(s).strip().replace(" ", "T")


def _cmp_ts(s):
    """Normalise to the server's own render ('...T08:29:07.636Z') for range comparison.

    The two formats are not string-comparable: '.060000+00:00' sorts BEFORE '.060Z'
    because '0' < 'Z', so the oldest event escaped an inclusive window and re-imported
    itself on every run. Compare datetimes, formatted the way the server stores them.
    """
    dt = datetime.fromisoformat(_norm_ts(s).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
