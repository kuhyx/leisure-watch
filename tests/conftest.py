"""Shared fixtures: every test sees a private, empty /proc and config."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def fake_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every /proc reader at ``tmp_path/proc`` (created empty)."""
    proc = tmp_path / "proc"
    proc.mkdir()
    for module in (
        "leisure_watch.procscan._steam",
        "leisure_watch.procscan._cmdline",
        "leisure_watch._proctree",
    ):
        monkeypatch.setattr(f"{module}._PROC", proc)
    return proc


@pytest.fixture(autouse=True)
def fake_counted_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the counted-process loader at a config file that does not exist."""
    path = tmp_path / "sbe-config.json"
    monkeypatch.setattr("leisure_watch.procscan._counted.DEFAULT_CONFIG_FILE", path)
    return path


@pytest.fixture(autouse=True)
def fake_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No test may read the real /etc/leisure-watch/leisure_from (C6).

    ``leisure_from`` / ``leisure_active`` bind their ``path=`` default at
    definition time, so patching the module constant alone is not enough:
    the defaults are redirected too, and so is our own copy of the path.
    """
    import earned_time
    from earned_time import _leisure

    path = tmp_path / "etc-leisure-watch" / "leisure_from"
    monkeypatch.setattr(_leisure, "LEISURE_FROM_PATH", path)
    monkeypatch.setattr(earned_time, "LEISURE_FROM_PATH", path)
    for func in (_leisure.leisure_from, _leisure.leisure_active):
        defaults = func.__defaults__ or ()
        monkeypatch.setattr(func, "__defaults__", (*defaults[:-1], path))
    monkeypatch.setattr("leisure_watch.phase2.SWITCH_PATH", path)
    return path


@pytest.fixture(autouse=True)
def fake_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the enforcer state and the heartbeat file at ``tmp_path``."""
    state = tmp_path / "playtime_state.json"
    monkeypatch.setattr("leisure_watch.phase2.PLAYTIME_STATE", state)
    monkeypatch.setattr(
        "leisure_watch.heartbeats.DEFAULT_FILE", tmp_path / "state" / "ext.json"
    )
    return state


@pytest.fixture(autouse=True)
def no_real_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default runners raise: no test reaches sudo or systemctl."""

    def refuse(argv: object) -> NoReturn:
        msg = f"test tried to run a real command: {argv!r}"
        raise AssertionError(msg)

    monkeypatch.setattr("leisure_watch.golive.capture", refuse)
    monkeypatch.setattr("leisure_watch.golive.execute", refuse)
    # The watcher retires kuhytrack-budget.timer once Phase 2 is on (Q13).
    monkeypatch.setattr("leisure_watch.watcher.systemctl", refuse)
