"""Tests for ``leisure-watch go-live``: preflight, the switch file, the timer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

import earned_time
import pytest

from leisure_watch import _preflight, golive
from tests.test_preflight import BOTH, TS, _healthy, _sources

if TYPE_CHECKING:
    from collections.abc import Sequence

TIMER = "kuhytrack-budget.timer"


@dataclass
class Fake:
    """A sudo/systemctl stand-in that really writes/removes the switch file."""

    fail: str = ""
    calls: list[list[str]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def execute(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if self.fail and self.fail in argv:
            return 1
        if argv[:2] == ["sudo", "install"]:
            target = argv[-1]
            assert argv[2:-2] == ["-D", "-m", "0644", "-o", "root", "-g", "root"]
            Path(target).parent.mkdir(parents=True, exist_ok=True)  # -D
            shutil.copyfile(argv[-2], target)
        elif argv[:3] == ["sudo", "rm", "-f"]:
            Path(argv[3]).unlink(missing_ok=True)
        return 0


def _env(tmp_path: Path, switch: Path, fake: Fake, ts: float = TS) -> golive.Env:
    src = _sources(tmp_path)
    _healthy(src)
    return golive.Env(
        capture=BOTH,
        execute=fake.execute,
        sources=src,
        switch=switch,
        clock=lambda: ts,
        out=fake.lines.append,
    )


def _text(fake: Fake) -> str:
    return "\n".join(fake.lines)


def test_goes_live_tomorrow(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    assert golive.go_live(_env(tmp_path, fake_switch, fake)) == 0
    assert fake_switch.read_text() == "2026-10-21\n"
    assert earned_time.leisure_from(fake_switch) == date(2026, 10, 21)
    # Q13: the timer runs until Phase 2 enforces; the WATCHER disables it on
    # the first tick of the go-live day, go-live itself never touches it.
    assert [c[:2] for c in fake.calls] == [["sudo", "install"]]
    text = _text(fake)
    assert "2026-10-21 06:00" in text
    assert "--undo" in text
    assert f"{TIMER}: the watcher disables it on 2026-10-21" in text


def test_before_six_is_still_the_previous_gaming_day(
    tmp_path: Path, fake_switch: Path
) -> None:
    fake = Fake()
    early = TS - 7 * 3600  # 05:00 on the 20th = gaming day 2026-10-19
    env = _env(tmp_path, fake_switch, fake, ts=early)
    assert golive.go_live(env, force=True) == 0
    assert fake_switch.read_text() == "2026-10-20\n"


def test_explicit_day(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    assert golive.go_live(env, day=date(2026, 10, 25)) == 0
    assert fake_switch.read_text() == "2026-10-25\n"


@pytest.mark.parametrize("day", [date(2026, 10, 20), date(2026, 10, 1)])
def test_refuses_a_day_not_after_today(
    tmp_path: Path, fake_switch: Path, day: date
) -> None:
    fake = Fake()
    assert golive.go_live(_env(tmp_path, fake_switch, fake), day=day) == 2
    assert fake.calls == []
    assert "not after" in _text(fake)


@pytest.mark.parametrize(
    ("day", "code"), [(date(2026, 11, 3), 0), (date(2026, 11, 4), 2)]
)
def test_a_date_at_most_14_days_ahead(
    tmp_path: Path, fake_switch: Path, day: date, code: int
) -> None:
    fake = Fake()
    assert golive.go_live(_env(tmp_path, fake_switch, fake), day=day) == code
    if code:
        assert fake.calls == []
        assert "more than 14 days" in _text(fake)
    else:
        assert fake_switch.read_text() == "2026-11-03\n"


@pytest.mark.parametrize("dry_run", [False, True])
def test_already_live_is_success(
    tmp_path: Path, fake_switch: Path, *, dry_run: bool
) -> None:
    fake_switch.parent.mkdir(parents=True)
    fake_switch.write_text("2026-10-20\n")
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    assert golive.go_live(env, force=True, dry_run=dry_run) == 0
    assert "already live since 2026-10-20" in _text(fake)
    assert fake.calls == []


def test_preflight_failure_refuses_without_force(
    tmp_path: Path, fake_switch: Path
) -> None:
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    env.sources.heartbeat_file.unlink()
    assert golive.go_live(env) == 1
    assert not fake_switch.exists()
    assert fake.calls == []
    assert "--force" in _text(fake)
    assert "never" in _text(fake)


def test_force_goes_live_anyway(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    env.sources.heartbeat_file.unlink()
    assert golive.go_live(env, force=True) == 0
    assert fake_switch.read_text() == "2026-10-21\n"
    assert "forced" in _text(fake)


@pytest.mark.parametrize("broken", [False, True])
def test_dry_run_writes_nothing(
    tmp_path: Path, fake_switch: Path, *, broken: bool
) -> None:
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    if broken:
        env.sources.heartbeat_file.unlink()
    assert golive.go_live(env, dry_run=True) == (1 if broken else 0)
    assert fake.calls == []
    assert not fake_switch.exists()
    text = _text(fake)
    assert "would write 2026-10-21" in text
    assert "systemctl" not in text
    assert "would refuse" in text if broken else "would refuse" not in text


def test_sudo_failure(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake(fail="install")
    assert golive.go_live(_env(tmp_path, fake_switch, fake)) == 1
    assert len(fake.calls) == 1
    assert "sudo install failed" in _text(fake)


def test_write_not_seen_by_earned_time(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    env = golive.Env(**{**env.__dict__, "execute": lambda argv: 0})
    assert golive.go_live(env) == 1
    assert "earned_time reads" in _text(fake)


def test_undo(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    assert golive.go_live(env) == 0
    assert golive.undo(env) == 0
    assert not fake_switch.exists()
    assert fake.calls[-2] == ["sudo", "rm", "-f", str(fake_switch)]
    assert fake.calls[-1] == ["systemctl", "--user", "enable", "--now", TIMER]
    assert "undone" in _text(fake)


def test_undo_dry_run(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    assert golive.undo(_env(tmp_path, fake_switch, fake), dry_run=True) == 0
    assert fake.calls == []
    assert "would run" in _text(fake)


@pytest.mark.parametrize("step", ["rm", "enable"])
def test_undo_failures(tmp_path: Path, fake_switch: Path, step: str) -> None:
    fake = Fake(fail=step)
    assert golive.undo(_env(tmp_path, fake_switch, fake)) == 1


def test_undo_rm_that_leaves_the_file(tmp_path: Path, fake_switch: Path) -> None:
    fake_switch.parent.mkdir(parents=True)
    fake_switch.write_text("2026-10-21\n")
    fake = Fake()
    env = _env(tmp_path, fake_switch, fake)
    env = golive.Env(**{**env.__dict__, "execute": lambda argv: 0})
    assert golive.undo(env) == 1
    assert "still" in _text(fake)


def test_default_env_reads_patched_runners(fake_switch: Path) -> None:
    lines: list[str] = []
    env = golive.default_env(lines.append)
    assert env.switch == fake_switch
    assert env.sources == _preflight.default_sources()
    with pytest.raises(AssertionError, match="real command"):
        env.execute(["true"])
    with pytest.raises(AssertionError, match="real command"):
        env.capture(["true"])
    assert isinstance(env.clock(), float)


def test_run_command_reports_exit_status() -> None:
    assert golive.run_command(["true"]) == 0
    assert golive.run_command(["false"]) == 1
    assert golive.run_command(["/nonexistent/leisure-watch-test"]) == 127
