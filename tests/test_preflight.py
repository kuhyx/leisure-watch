"""Tests for the go-live preflight checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
from typing import TYPE_CHECKING

import pytest

from leisure_watch import _preflight, facts, heartbeats, phase2
from leisure_watch._browser import EXTENSION_VERSION
from tests.test_lockstate import _claim, _held
from tests.test_watcher import KEY

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

TS = datetime.fromisoformat("2026-10-20T12:00:00").astimezone().timestamp()
ALL_SHADOW = dict.fromkeys(phase2.SHADOW_KEYS, 0.0)


def _sources(tmp_path: Path) -> _preflight.Sources:
    (tmp_path / "key").write_bytes(KEY)
    return _preflight.Sources(
        now_path=tmp_path / "now.json",
        key_file=tmp_path / "key",
        heartbeat_file=tmp_path / "ext.json",
        playtime_state=tmp_path / "pt.json",
        claims_dir=tmp_path / "claims",
    )


def _healthy(src: _preflight.Sources) -> None:
    now = facts.Now(
        ts=TS - 2,
        seq=1,
        state="free",
        paused_by=None,
        reasons=(),
        focus=facts.Focus("Terminator", "t", None, idle=False),
        extensions={"helium": TS - 2, "librewolf": TS - 2},
    )
    facts.write_now(src.now_path, now, src.key_file)
    # 0.10.0 > 0.2.1: versions compare as numbers, never as strings.
    versions = {"helium": EXTENSION_VERSION, "librewolf": "0.10.0"}
    seen = {"helium": TS - 60, "librewolf": TS, "versions": versions}
    src.heartbeat_file.write_text(json.dumps(seen))
    state = {"day_key": "2026-10-20", "last_tick_at": TS - 3, **ALL_SHADOW}
    src.playtime_state.write_text(json.dumps(state))


def _systemctl(active: Sequence[str]) -> _preflight.Capture:
    def capture(argv: Sequence[str]) -> str | None:
        assert argv[0] == "systemctl"
        return "active\n" if argv[-1] in active else None

    return capture


BOTH = _systemctl(["leisure-watch.service", "steam-backlog-enforcer.service"])


def _by_name(checks: list[_preflight.Check]) -> dict[str, _preflight.Check]:
    return {c.name: c for c in checks}


def test_all_green(tmp_path: Path) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    checks = _preflight.preflight(BOTH, src, TS)
    assert [c.name for c in checks] == [
        "watcher",
        "extension helium",
        "extension librewolf",
        "enforcer",
        "gatelock",
    ]
    assert all(c.ok for c in checks), checks
    assert "[ok]" in _preflight.render(checks)[0]


def test_units_down(tmp_path: Path) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    checks = _by_name(_preflight.preflight(_systemctl([]), src, TS))
    assert not checks["watcher"].ok
    assert "not active" in checks["watcher"].detail
    assert not checks["enforcer"].ok
    assert "FAIL" in _preflight.render([checks["watcher"]])[0]


def test_stale_now_json(tmp_path: Path) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    checks = _by_name(_preflight.preflight(BOTH, src, TS + 60))
    assert not checks["watcher"].ok
    assert "now.json" in checks["watcher"].detail


def test_heartbeats_old_or_missing(tmp_path: Path) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    src.heartbeat_file.write_text(json.dumps({"helium": TS - 25 * 3600}))
    checks = _by_name(_preflight.preflight(BOTH, src, TS))
    assert not checks["extension helium"].ok
    assert "25.0 h ago" in checks["extension helium"].detail
    assert not checks["extension librewolf"].ok
    assert "never" in checks["extension librewolf"].detail


@pytest.mark.parametrize(
    ("versions", "needle"),
    [
        ({}, "version unknown"),
        ({"helium": "0.2.0", "librewolf": "0.1.2"}, "0.2.0 < " + EXTENSION_VERSION),
        ({"helium": "0.2.x", "librewolf": ""}, "0.2.x < " + EXTENSION_VERSION),
    ],
)
def test_extension_version_too_old(
    tmp_path: Path, versions: dict[str, str], needle: str
) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    seen = {"helium": TS, "librewolf": TS, "versions": versions}
    src.heartbeat_file.write_text(json.dumps(seen))
    checks = _by_name(_preflight.preflight(BOTH, src, TS))
    assert not checks["extension helium"].ok
    assert not checks["extension librewolf"].ok
    assert needle in checks["extension helium"].detail


@pytest.mark.parametrize(
    ("state", "needle"),
    [
        (None, "unreadable"),
        ({"day_key": "2026-10-20", "last_tick_at": TS}, "shadow_seconds"),
        ({"day_key": "2026-10-19", "last_tick_at": TS, **ALL_SHADOW}, "day"),
        ({"day_key": "2026-10-20", "last_tick_at": TS - 600, **ALL_SHADOW}, "tick"),
        ({"day_key": "2026-10-20", "last_tick_at": "x", **ALL_SHADOW}, "tick"),
    ],
)
def test_enforcer_state(
    tmp_path: Path, state: dict[str, object] | None, needle: str
) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    if state is None:
        src.playtime_state.unlink()
    else:
        src.playtime_state.write_text(json.dumps(state))
    check = _by_name(_preflight.preflight(BOTH, src, TS))["enforcer"]
    assert not check.ok
    assert needle in check.detail


def test_gatelock_old_claim(tmp_path: Path) -> None:
    src = _sources(tmp_path)
    _healthy(src)
    assert src.claims_dir is not None
    path = _claim(src.claims_dir, "a", app="meal_gate")
    with _held(path):
        check = _by_name(_preflight.preflight(BOTH, src, TS))["gatelock"]
    assert not check.ok
    assert "meal_gate" in check.detail


def test_default_sources(tmp_path: Path) -> None:
    src = _preflight.default_sources()
    assert src.heartbeat_file == heartbeats.default_file()
    assert src.playtime_state == phase2.PLAYTIME_STATE
    assert src.key_file == facts.HMAC_KEY_FILE
    assert replace(src, claims_dir=tmp_path).claims_dir == tmp_path
