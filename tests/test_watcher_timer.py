"""Q13: the watcher retires kuhytrack-budget.timer once Phase 2 enforces."""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import TYPE_CHECKING

from leisure_watch import watcher
from leisure_watch.watcher import Watcher
from tests.test_watcher import _cfg, _snap

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import pytest


class _Systemctl:
    """Records systemctl calls; fails while ``ok`` is false."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.ok = True

    def __call__(self, argv: Sequence[str]) -> bool:
        self.calls.append(list(argv))
        return self.ok


DISABLE = ["systemctl", "--user", "disable", "--now", "kuhytrack-budget.timer"]


def test_timer_is_retired_on_the_first_live_tick_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    fake = _Systemctl()
    monkeypatch.setattr(watcher, "systemctl", fake)
    cfg = _cfg(tmp_path)
    w = Watcher(cfg, gather_fn=lambda _c, _s: _snap())
    w.tick()
    assert fake.calls == []  # dormant: Q13, the timer keeps running
    cfg.switch_path.write_text("2026-01-01\n", encoding="ascii")
    w.tick()
    w.tick()
    assert fake.calls == [DISABLE]
    assert caplog.text.count("kuhytrack-budget.timer") == 1
    cfg.switch_path.unlink()  # go-live --undo (it re-enables the timer)
    w.tick()
    cfg.switch_path.write_text("2026-01-01\n", encoding="ascii")
    w.tick()
    assert fake.calls == [DISABLE, DISABLE]


def test_a_failed_disable_is_retried_a_minute_later_and_warned_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = _Systemctl()
    fake.ok = False
    monkeypatch.setattr(watcher, "systemctl", fake)
    clock = [1_800_000_000.0]
    cfg = _cfg(tmp_path)
    cfg.switch_path.write_text("2026-01-01\n", encoding="ascii")
    w = Watcher(cfg, gather_fn=lambda _c, _s: replace(_snap(), ts=clock[0]))
    w.tick()
    clock[0] += 30
    w.tick()
    assert len(fake.calls) == 1
    clock[0] += 31
    w.tick()
    assert len(fake.calls) == 2
    assert caplog.text.count("could not disable") == 1
    fake.ok = True
    clock[0] += 61
    w.tick()
    clock[0] += 61
    w.tick()
    assert len(fake.calls) == 3


def test_systemctl_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(argv: Sequence[str]) -> str | None:
        seen.append(list(argv))
        return None if "fail" in argv else ""

    monkeypatch.setattr("leisure_watch._sensors.run", run)
    assert watcher.run_systemctl(["systemctl", "x"]) is True
    assert watcher.run_systemctl(["systemctl", "fail"]) is False
    assert seen == [["systemctl", "x"], ["systemctl", "fail"]]
