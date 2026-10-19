"""``python -m leisure_watch {run,status,report,build-extension,go-live}``."""

from __future__ import annotations

import argparse
from datetime import date
import json
import logging
from pathlib import Path
import signal
import sys
import threading
import time
import urllib.request

from leisure_watch import _extbuild, golive
from leisure_watch.daylog import DEFAULT_DIR, gaming_day, render_report
from leisure_watch.extserver import PORT
from leisure_watch.watcher import Config, Watcher


def _out(text: str) -> None:
    sys.stdout.write(text + "\n")


def _err(text: str) -> None:
    sys.stderr.write(text + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leisure-watch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="publish now.json every 5 s (the systemd unit)")
    status = sub.add_parser("status", help="the current computed state")
    status.add_argument("--json", action="store_true", help="now.json-shaped output")
    report = sub.add_parser("report", help="top leisure keys of a day")
    report.add_argument("--day", type=date.fromisoformat, default=None)
    report.add_argument("--top", type=int, default=25)
    build = sub.add_parser("build-extension", help="build Helium + LibreWolf variants")
    build.add_argument("src", type=Path)
    build.add_argument("out", type=Path)
    build.add_argument("--port", type=int, default=PORT)
    live = sub.add_parser(
        "go-live",
        help="switch the leisure budget on from tomorrow (sudo for one file)",
        description=(
            "Preflight, then write tomorrow's gaming day to "
            "/etc/leisure-watch/leisure_from (sudo install) and disable "
            "kuhytrack-budget.timer. --undo removes it and re-enables the timer."
        ),
    )
    live.add_argument("--force", action="store_true", help="go past failed checks")
    live.add_argument("--undo", action="store_true", help="remove the switch file")
    live.add_argument(
        "--dry-run", action="store_true", help="preflight + print; write nothing"
    )
    live.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="first leisure day (default: tomorrow; after today, <= 14 days ahead)",
    )
    return parser


def _cmd_run() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()
    watcher = Watcher(Config())

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()
        watcher.wake()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    watcher.run(stop)
    return 0


def live_status(port: int | None = None) -> dict[str, object] | None:
    """The running watcher's document (it has the extension data), or ``None``."""
    url = f"http://127.0.0.1:{PORT if port is None else port}/now"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            doc = json.loads(resp.read())
    except OSError, ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def _cmd_status(*, as_json: bool) -> int:
    doc = live_status()
    if doc is None:
        _err(
            "leisure-watch: watcher not reachable; computed standalone "
            "(no extension data, so a focused browser reads as failclosed)"
        )
        doc = Watcher(Config()).status_doc()
    if as_json:
        _out(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0
    reasons = doc.get("reasons")
    keys = (
        [r.get("key") for r in reasons if isinstance(r, dict)]
        if isinstance(reasons, list)
        else []
    )
    paused = f" by {doc['paused_by']}" if doc.get("paused_by") else ""
    _out(f"{doc.get('state')}{paused}: {', '.join(map(str, keys)) or '-'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = _parser().parse_args(argv)
    if args.cmd == "run":
        return _cmd_run()
    if args.cmd == "status":
        return _cmd_status(as_json=args.json)
    if args.cmd == "go-live":
        env = golive.default_env(_out)
        if args.undo:
            return golive.undo(env, dry_run=args.dry_run)
        return golive.go_live(
            env, force=args.force, dry_run=args.dry_run, day=args.date
        )
    if args.cmd == "report":
        day = args.day or gaming_day(time.time())
        _out(render_report(DEFAULT_DIR, day, top=args.top))
        return 0
    for name, path in _extbuild.build(args.src, args.out, args.port).items():
        _out(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
