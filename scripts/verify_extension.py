#!/usr/bin/env python3
"""Prove the extension heartbeats from a real, headless browser.

A unit test cannot: the reporter is JavaScript inside Helium / LibreWolf, and
the risk is the browser suspending its service worker / event page (then the
daemon fails closed). This serves the real endpoint on a free port, builds
the extension against it, launches the browser HEADLESS with a throwaway
profile under ~/data/claude-scratch, and records every report.

    python3 scripts/verify_extension.py helium [--seconds 45] [--mode single]
    python3 scripts/verify_extension.py librewolf [--seconds 45]

``--mode two-flags`` loads two copies via two separate --load-extension
switches, ``--mode comma`` via one comma-joined switch: which copies report
settles whether Chromium honours every switch or only the last.

Never touches the user's profile or display (DISPLAY is dropped). Exit 0 =
the expected copies reported, with no gap over 15 s.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING

from leisure_watch._extbuild import GECKO_ID, build
from leisure_watch.extserver import ExtensionServer, ReportStore

if TYPE_CHECKING:
    from leisure_watch._browser import ExtReport

SCRATCH = Path.home() / "data" / "claude-scratch" / "leisure-watch-ext"
HELIUM = "/opt/helium-browser-bin/helium"
LIBREWOLF = "/usr/bin/librewolf"
REPO = Path(__file__).resolve().parent.parent
MAX_GAP = 15.0
FIREFOX_PREFS = (
    'user_pref("xpinstall.signatures.required", false);\n'
    'user_pref("extensions.autoDisableScopes", 14);\n'
    'user_pref("browser.shell.checkDefaultBrowser", false);\n'
)


class RecordingStore(ReportStore):
    """Keeps every report, not only the latest."""

    def __init__(self) -> None:
        """Start with an empty log."""
        super().__init__()
        self.log: list[ExtReport] = []

    def update(self, report: ExtReport) -> None:
        """Record *report*, then keep it as the latest."""
        super().update(report)
        self.log.append(report)


def _helium_cmd(work: Path, port: int, mode: str) -> list[str]:
    first = build(REPO / "extension", work / "a", port)["chromium"]
    flags = [f"--load-extension={first}"]
    if mode != "single":
        second = build(REPO / "extension", work / "b", port)["chromium"]
        js = second / "background.js"
        js.write_text(js.read_text().replace('"helium"', '"librewolf"', 1))
        joined = f"--load-extension={first},{second}"
        flags = [joined] if mode == "comma" else [*flags, f"--load-extension={second}"]
    return [
        HELIUM,
        "--headless=new",
        "--no-first-run",
        "--disable-gpu",
        f"--user-data-dir={work / 'profile'}",
        *flags,
        "about:blank",
    ]


def _librewolf_cmd(work: Path, port: int) -> list[str]:
    xpi = build(REPO / "extension", work / "ext", port)["xpi"]
    profile = work / "profile"
    (profile / "extensions").mkdir(parents=True)
    shutil.copy(xpi, profile / "extensions" / f"{GECKO_ID}.xpi")
    (profile / "user.js").write_text(FIREFOX_PREFS)
    return [
        LIBREWOLF,
        "--headless",
        "--no-remote",
        "--profile",
        str(profile),
        "about:blank",
    ]


def _summary(log: list[ExtReport], started: float, ended: float) -> dict[str, object]:
    out: dict[str, object] = {}
    for browser in sorted({r.browser for r in log}):
        times = [started] + [r.received for r in log if r.browser == browser] + [ended]
        gaps = [b - a for a, b in itertools.pairwise(times)]
        out[browser] = {
            "reports": len(times) - 2,
            "first_after_s": round(gaps[0], 1),
            "max_gap_s": round(max(gaps[1:]), 1),
        }
    return out


def main() -> int:
    """Run one browser for --seconds and judge its heartbeats."""
    parser = argparse.ArgumentParser()
    parser.add_argument("browser", choices=["helium", "librewolf"])
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument(
        "--mode", choices=["single", "two-flags", "comma"], default="single"
    )
    args = parser.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{args.browser}-", dir=SCRATCH))
    store = RecordingStore()
    server = ExtensionServer(0, store, lambda: None, dict)
    server.start()
    cmd = (
        _helium_cmd(work, server.port, args.mode)
        if args.browser == "helium"
        else _librewolf_cmd(work, server.port)
    )
    env = {
        k: v for k, v in os.environ.items() if k not in {"DISPLAY", "WAYLAND_DISPLAY"}
    }
    started = time.time()
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        time.sleep(args.seconds)
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(10)
        server.stop()
    result = _summary(store.log, started, time.time())
    sys.stdout.write(json.dumps({"mode": args.mode, "result": result}, indent=1) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    stats = [v for v in result.values() if isinstance(v, dict)]
    healthy = bool(stats) and all(s["max_gap_s"] <= MAX_GAP for s in stats)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
