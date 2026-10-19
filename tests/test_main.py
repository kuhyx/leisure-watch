"""Tests for the command line."""

from __future__ import annotations

import json
from pathlib import Path
import signal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from leisure_watch import __main__ as cli
from leisure_watch.extserver import ExtensionServer, ReportStore
from leisure_watch.watcher import Watcher

if TYPE_CHECKING:
    from collections.abc import Callable
    import threading


DOC: dict[str, object] = {
    "state": "leisure",
    "paused_by": None,
    "reasons": [{"key": "app:mpv"}],
    "sig": "x",
}


def test_status_json_from_the_live_watcher(capsys: pytest.CaptureFixture[str]) -> None:
    srv = ExtensionServer(0, ReportStore(), lambda: None, {"/now": lambda: DOC})
    srv.start()
    try:
        with patch.object(cli, "PORT", srv.port):
            assert cli.main(["status", "--json"]) == 0
    finally:
        srv.stop()
    assert json.loads(capsys.readouterr().out) == DOC


def test_status_falls_back_to_standalone(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(cli, "live_status", return_value=None),
        patch(
            "leisure_watch.__main__.Watcher.status_doc",
            return_value={**DOC, "paused_by": "i3lock"},
        ),
    ):
        assert cli.main(["status"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "leisure by i3lock: app:mpv"
    assert "standalone" in out.err


def test_status_plain_without_reasons(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(cli, "live_status", return_value={"state": "free", "reasons": 3}):
        cli.main(["status"])
    assert capsys.readouterr().out.strip() == "free: -"


def test_live_status_handles_garbage() -> None:
    srv = ExtensionServer(
        0, ReportStore(), lambda: None, {"/now": lambda: json.loads("[1]")}
    )
    srv.start()
    try:
        assert cli.live_status(srv.port) is None
    finally:
        srv.stop()
    assert cli.live_status(1) is None


def test_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(cli, "DEFAULT_DIR", tmp_path):
        assert cli.main(["report", "--day", "2026-10-19"]) == 0
        assert cli.main(["report"]) == 0
    assert "no leisure" in capsys.readouterr().out


def test_build_extension(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = Path(cli.__file__).resolve().parent.parent / "extension"
    assert cli.main(["build-extension", str(src), str(tmp_path), "--port", "9"]) == 0
    assert "xpi:" in capsys.readouterr().out


def test_run_stops_on_sigterm() -> None:
    handlers: dict[int, Callable[[int, object], None]] = {}

    def fake_run(_self: object, stop: threading.Event) -> None:
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        assert stop.is_set()

    with (
        patch("leisure_watch.__main__.signal.signal", handlers.__setitem__),
        patch("leisure_watch.__main__.Watcher.run", fake_run),
        patch("leisure_watch.__main__.Watcher", wraps=Watcher) as made,
    ):
        assert cli.main(["run"]) == 0
    assert made.called


def test_go_live_routes_its_flags() -> None:
    with (
        patch("leisure_watch.__main__.golive.go_live", return_value=0) as live,
        patch("leisure_watch.__main__.golive.undo", return_value=3) as undo,
    ):
        assert (
            cli.main(["go-live", "--force", "--dry-run", "--date", "2026-11-01"]) == 0
        )
        assert cli.main(["go-live", "--undo"]) == 3
    kwargs = live.call_args.kwargs
    assert (kwargs["force"], kwargs["dry_run"], str(kwargs["day"])) == (
        True,
        True,
        "2026-11-01",
    )
    assert undo.call_args.kwargs == {"dry_run": False}


def test_go_live_help_names_every_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["go-live", "--help"])
    out = capsys.readouterr().out
    for flag in ("--force", "--undo", "--dry-run", "--date"):
        assert flag in out
