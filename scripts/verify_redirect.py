#!/usr/bin/env python3
"""Prove the Phase-2 redirect in a real browser, on a private X display.

Serves a FAKE ``GET /status`` saying active + spent (the packaged allowlist,
10 h of 10 h used), builds the extension against it, opens *url* in a
throwaway Helium / LibreWolf profile and records the extension's reports:
a non-allowlisted page must turn into the bundled ``spent.html``, an
allowlisted one must stay. Run it under Xvfb, never on the live display:

    xvfb-run -a -s "-screen 0 1280x800x24" python3 scripts/verify_redirect.py
        helium https://www.youtube.com/ --expect blocked --shot /path/x.png

Exit 0 = the last reported URL matches --expect.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from verify_extension import SCRATCH, RecordingStore, _helium_cmd, _librewolf_cmd

from leisure_watch.allowlist import load_allowlist
from leisure_watch.extserver import ExtensionServer

BUDGET = 10 * 3600.0
IMPORT = shutil.which("import") or "/usr/bin/import"  # ImageMagick


def fake_status() -> dict[str, object]:
    """Active and spent, with the real packaged lists."""
    allow = load_allowlist(None)
    return {
        "active": True,
        "spent": True,
        "allow": sorted(allow.domains),
        "local_hosts": sorted(allow.local_hosts),
        "deny_ports": sorted(allow.deny_ports),
        "internal_schemes": sorted(allow.internal_schemes),
        "used_seconds": BUDGET,
        "budget_seconds": BUDGET,
        "day": "2026-10-20",
    }


def _verdict(url: str) -> str:
    internal = url.startswith(("chrome-extension://", "moz-extension://"))
    return "blocked" if internal and "/spent.html" in url else "allowed"


def main() -> int:
    """Open one URL and judge where the tab ended up."""
    parser = argparse.ArgumentParser()
    parser.add_argument("browser", choices=["helium", "librewolf"])
    parser.add_argument("url")
    parser.add_argument("--expect", choices=["blocked", "allowed"], required=True)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--shot", type=Path, default=None)
    args = parser.parse_args()
    display = os.environ.get("DISPLAY", "")
    if display in {"", ":0", ":0.0"}:
        sys.stderr.write("refusing: run under xvfb-run, not on the live display\n")
        return 2

    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"redirect-{args.browser}-", dir=SCRATCH))
    store = RecordingStore()
    server = ExtensionServer(0, store, lambda: None, {"/status": fake_status})
    server.start()
    cmd = (
        _helium_cmd(work, server.port, "single", args.url, headless=False)
        if args.browser == "helium"
        else _librewolf_cmd(work, server.port, args.url, headless=False)
    )
    env = {k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"}
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        time.sleep(args.seconds)
        if args.shot is not None:
            args.shot.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([IMPORT, "-window", "root", str(args.shot)], check=True)
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(10)
        server.stop()
    shutil.rmtree(work, ignore_errors=True)
    urls = [r.url for r in store.log]
    last = urls[-1] if urls else ""
    verdict = _verdict(last) if last else "no report"
    result = {"browser": args.browser, "opened": args.url, "reports": len(urls)}
    result |= {"last_url": last, "verdict": verdict, "shot": str(args.shot)}
    sys.stdout.write(json.dumps(result, indent=1) + "\n")
    return 0 if verdict == args.expect else 1


if __name__ == "__main__":
    sys.exit(main())
