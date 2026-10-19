"""The extension's background script under a fake browser API (node).

Fail closed (Q8): the last ``GET /status`` is persisted, and while the
daemon is unreachable a last-known ACTIVE status blocks as if spent -- a
cold start with the daemon down must not let leisure run free. Every
report names the extension version, so go-live can tell builds apart.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from leisure_watch import phase2
from leisure_watch.allowlist import load_allowlist

HARNESS = Path(__file__).resolve().parent / "background_harness.js"
NODE = shutil.which("node")
TABS = [
    {"id": 1, "url": "https://www.youtube.com/watch?v=x"},
    {"id": 2, "url": "https://github.com/kuhyx"},
    {"id": 3, "url": "file:///home/kuhy/x.mp4"},
]

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _status(*, active: bool, spent: bool) -> dict[str, object]:
    doc = phase2.block_doc(load_allowlist(None), 0.0)
    return {**doc, "active": active, "spent": spent}


def _run(stored: object, status: object) -> dict[str, list[object]]:
    assert NODE is not None
    feed = {"stored": stored, "status": status, "tabs": TABS, "wait_ms": 300}
    done = subprocess.run(
        [NODE, str(HARNESS)],
        input=json.dumps(feed),
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    result: dict[str, list[object]] = json.loads(done.stdout)
    return result


def _blocked(out: dict[str, list[object]]) -> set[object]:
    return {u[0] for u in out["updates"] if isinstance(u, list)}


def test_daemon_down_with_last_status_active_fails_closed() -> None:
    out = _run(_status(active=True, spent=False), None)
    assert _blocked(out) == {1, 3}


def test_daemon_down_with_nothing_known_blocks_nothing() -> None:
    assert _blocked(_run(None, None)) == set()


def test_daemon_down_while_dormant_blocks_nothing() -> None:
    assert _blocked(_run(_status(active=False, spent=False), None)) == set()


def test_daemon_answering_not_spent_unblocks() -> None:
    stored = _status(active=True, spent=True)
    assert _blocked(_run(stored, _status(active=True, spent=False))) == set()


def test_daemon_answering_spent_blocks_and_is_persisted() -> None:
    status = _status(active=True, spent=True)
    out = _run(None, status)
    assert _blocked(out) == {1, 3}
    assert {"leisureStatus": status} in out["saved"]


def test_a_malformed_answer_counts_as_unreachable() -> None:
    out = _run(_status(active=True, spent=False), {"active": True})
    assert _blocked(out) == {1, 3}


def test_every_report_names_the_extension_version() -> None:
    reports = _run(None, None)["reports"]
    assert reports
    assert all(isinstance(r, dict) and r["version"] == "9.9.9" for r in reports)
