#!/usr/bin/env python3
"""kt-import — pull other trackers' data into kuhytrack so there is one store.

  kt-import.py aw --file aw-buckets-export.json --device arch
  kt-import.py aw --from http://127.0.0.1:5600 --device oldlaptop   # live aw-server
  kt-import.py awdb --file ~/.local/share/activitywatch/aw-server/peewee-sqlite.v2.db
  kt-import.py wakapi --url https://wakapi.example --key <api key> --days 30

Idempotent-ish: aw import is keyed on bucket+timestamp and skips events already present;
wakapi import rewrites the last N days of its own bucket instead of appending duplicates.
Env: KT_URL, KT_TOKEN
"""

from __future__ import annotations

import argparse
import json
import sys

from ktimp_awdb import import_awdb
from ktimp_common import get_json, kt_call
from ktimp_wakapi import import_wakapi


def import_aw(args):
    if args.file:
        raw = json.loads(open(args.file).read())
        buckets = raw.get("buckets", raw)
    else:
        buckets = get_json(args.from_url.rstrip("/") + "/api/0/export")["buckets"]

    total = 0
    for bid, b in buckets.items():
        dev = args.device or b.get("hostname") or "imported"
        dst = f"{bid}_{dev}" if not bid.endswith(dev) else bid
        kt_call(
            f"/api/0/buckets/{dst}",
            "POST",
            {
                "client": b.get("client", "aw-import"),
                "type": b.get("type", "currentwindow"),
                "hostname": dev,
                "device": dev,
            },
        )
        existing = {
            e["timestamp"] for e in kt_call(f"/api/0/buckets/{dst}/events?limit=-1")
        }
        evs = [
            {
                "timestamp": e["timestamp"],
                "duration": e.get("duration", 0),
                "data": e["data"],
            }
            for e in b.get("events", [])
            if e["timestamp"] not in existing
        ]
        for i in range(0, len(evs), 500):
            kt_call(f"/api/0/buckets/{dst}/events", "POST", evs[i : i + 500])
        print(
            f"  {bid:<44} -> {dst:<46} +{len(evs)} (skipped {len(b.get('events', [])) - len(evs)})"
        )
        total += len(evs)
    print(f"imported {total} events")


ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("aw")
p.add_argument("--file")
p.add_argument("--from", dest="from_url")
p.add_argument("--device")
p.set_defaults(fn=import_aw)
p = sub.add_parser("awdb", help="import straight from an aw-server sqlite file")
p.add_argument(
    "--file",
    required=True,
    help="~/.local/share/activitywatch/aw-server/peewee-sqlite.v2.db",
)
p.add_argument("--device")
p.set_defaults(fn=import_awdb)
p = sub.add_parser("wakapi")
p.add_argument("--url", required=True)
p.add_argument("--key", required=True)
p.add_argument("--days", type=int, default=30)
p.add_argument("--device", default="code")
p.add_argument("--force", action="store_true")
p.set_defaults(fn=import_wakapi)
a = ap.parse_args()
if a.cmd == "aw" and not (a.file or a.from_url):
    sys.exit("aw import needs --file or --from")
a.fn(a)
