"""Tests for the persisted last-seen time of each browser's extension."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leisure_watch import heartbeats
from leisure_watch._browser import ExtReport

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _report(browser: str, received: float, version: str | None = None) -> ExtReport:
    return ExtReport(
        browser, "https://github.com/", "GitHub", True, (), received, version=version
    )


def test_load_missing_is_empty(tmp_path: Path) -> None:
    assert heartbeats.load(tmp_path / "none.json") == {}


def test_load_keeps_only_known_browsers_with_numbers(tmp_path: Path) -> None:
    path = tmp_path / "ext.json"
    doc = {"helium": 5, "librewolf": "x", "chrome": 3.0, "x": True}
    path.write_text(json.dumps(doc))
    assert heartbeats.load(path) == {"helium": 5.0}


def test_load_rejects_bool(tmp_path: Path) -> None:
    path = tmp_path / "ext.json"
    path.write_text(json.dumps({"helium": True}))
    assert heartbeats.load(path) == {}


def test_log_persists_first_report_then_throttles(tmp_path: Path) -> None:
    path = tmp_path / "state" / "ext.json"
    log = heartbeats.HeartbeatLog(path)
    log.update({"helium": _report("helium", 1000.0)})
    assert heartbeats.load(path) == {"helium": 1000.0}
    log.update({"helium": _report("helium", 1030.0)})  # < 60 s later: no write
    assert heartbeats.load(path) == {"helium": 1000.0}
    assert log.seen == {"helium": 1000.0}
    log.update({"helium": _report("helium", 1060.0)})
    assert heartbeats.load(path) == {"helium": 1060.0}


def test_new_browser_is_written_at_once(tmp_path: Path) -> None:
    path = tmp_path / "ext.json"
    log = heartbeats.HeartbeatLog(path)
    log.update({"helium": _report("helium", 1000.0)})
    log.update(
        {"helium": _report("helium", 1001.0), "librewolf": _report("librewolf", 5.0)}
    )
    # The write carries every newer time along, helium's included.
    assert heartbeats.load(path) == {"helium": 1001.0, "librewolf": 5.0}


def test_an_older_report_never_moves_it_back(tmp_path: Path) -> None:
    path = tmp_path / "ext.json"
    path.write_text(json.dumps({"helium": 5000.0}))
    log = heartbeats.HeartbeatLog(path)
    log.update({"helium": _report("helium", 10.0)})
    assert heartbeats.load(path) == {"helium": 5000.0}


def test_write_failure_is_logged_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    log = heartbeats.HeartbeatLog(blocker / "ext.json")
    log.update({"helium": _report("helium", 1.0)})
    assert "heartbeat" in caplog.text
    assert log.seen == {}


def test_default_path_is_patched(tmp_path: Path) -> None:
    assert heartbeats.default_file() == tmp_path / "state" / "ext.json"


def test_versions_are_persisted_and_a_change_is_written_at_once(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ext.json"
    log = heartbeats.HeartbeatLog(path)
    log.update({"helium": _report("helium", 1000.0, "0.2.0")})
    assert heartbeats.load_versions(path) == {"helium": "0.2.0"}
    log.update({"helium": _report("helium", 1001.0, "0.2.0")})  # throttled
    assert heartbeats.load(path) == {"helium": 1000.0}
    log.update({"helium": _report("helium", 1002.0, "0.2.1")})  # new build
    assert heartbeats.load_versions(path) == {"helium": "0.2.1"}
    assert heartbeats.load(path) == {"helium": 1002.0}
    log.update({"helium": _report("helium", 1003.0)})  # no version: kept
    assert heartbeats.load_versions(path) == {"helium": "0.2.1"}
    assert heartbeats.HeartbeatLog(path).versions == {"helium": "0.2.1"}


def test_load_versions_of_an_old_or_odd_file(tmp_path: Path) -> None:
    path = tmp_path / "ext.json"
    path.write_text(json.dumps({"helium": 5.0}))  # 0.2.0 layout: no versions
    assert heartbeats.load(path) == {"helium": 5.0}
    assert heartbeats.load_versions(path) == {}
    path.write_text(json.dumps({"versions": ["x"]}))
    assert heartbeats.load_versions(path) == {}
    odd = {"helium": 1, "librewolf": "0.2.1", "chrome": "1.0"}
    path.write_text(json.dumps({"versions": odd}))
    assert heartbeats.load_versions(path) == {"librewolf": "0.2.1"}
