"""Tests for the daily classification log and its report."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import TYPE_CHECKING

from leisure_watch.daylog import DayLog, gaming_day, render_report
from leisure_watch.facts import Focus, Now, Reason

if TYPE_CHECKING:
    from pathlib import Path

LOCAL = datetime.now().astimezone().tzinfo
NOON = datetime(2026, 10, 19, 12, 0, tzinfo=LOCAL).timestamp()
YT = Reason("focus", "domain:youtube.com", 1, "YouTube")
MPV = Reason("media", "app:mpv", 2, "x — mpv")


def _now(ts: float, state: str, reasons: tuple[Reason, ...], app: str) -> Now:
    return Now(ts, 1, state, None, reasons, Focus(app, "", None, idle=False))


def test_gaming_day_rolls_at_six() -> None:
    assert gaming_day(datetime(2026, 10, 19, 5, 59, tzinfo=LOCAL).timestamp()) == date(
        2026, 10, 18
    )
    assert gaming_day(datetime(2026, 10, 19, 6, 0, tzinfo=LOCAL).timestamp()) == date(
        2026, 10, 19
    )


def test_aggregates_per_state_source_key(tmp_path: Path) -> None:
    log = DayLog(tmp_path)
    log.add(_now(NOON, "leisure", (YT, MPV), "Helium"), 5.0)
    log.add(_now(NOON + 5, "leisure", (YT,), "Helium"), 5.0)
    log.add(_now(NOON + 10, "free", (), "Terminator"), 5.0)
    log.flush()
    rows = [
        json.loads(line)
        for line in (tmp_path / "2026-10-19.jsonl").read_text().splitlines()
    ]
    by_key = {(r["state"], r["source"], r["key"]): r["seconds"] for r in rows}
    assert by_key[("leisure", "focus", "domain:youtube.com")] == 10.0
    assert by_key[("leisure", "media", "app:mpv")] == 5.0
    assert by_key[("free", "focus", "app:terminator")] == 5.0
    assert by_key[("leisure", "total", "wall")] == 10.0


def test_resumes_the_day_after_a_restart(tmp_path: Path) -> None:
    first = DayLog(tmp_path)
    first.add(_now(NOON, "leisure", (YT,), "Helium"), 5.0)
    first.flush()
    second = DayLog(tmp_path)
    second.add(_now(NOON + 5, "leisure", (YT,), "Helium"), 5.0)
    second.flush()
    report = render_report(tmp_path, date(2026, 10, 19))
    assert "10s" in report
    assert "domain:youtube.com" in report


def test_new_day_starts_fresh(tmp_path: Path) -> None:
    log = DayLog(tmp_path)
    log.add(_now(NOON, "leisure", (YT,), "Helium"), 5.0)
    log.add(_now(NOON + 86400, "leisure", (MPV,), "mpv"), 7.0)
    log.flush()
    assert (tmp_path / "2026-10-19.jsonl").exists()
    today = (tmp_path / "2026-10-20.jsonl").read_text()
    assert "app:mpv" in today
    assert "youtube" not in today


def test_corrupt_lines_are_skipped(tmp_path: Path) -> None:
    row = {"state": "leisure", "source": "focus", "key": "k", "label": "l"}
    lines = [
        "{bad",
        "[1]",
        json.dumps({**row, "seconds": "x"}),
        json.dumps({**row, "key": "k2", "seconds": 3600}),
    ]
    (tmp_path / "2026-10-19.jsonl").write_text("\n".join(lines), encoding="utf-8")
    report = render_report(tmp_path, date(2026, 10, 19))
    assert "1h00m" in report
    assert "k2" in report


def test_report_for_an_empty_day(tmp_path: Path) -> None:
    assert "no leisure" in render_report(tmp_path, date(2026, 1, 1))


def test_flush_without_data_writes_nothing(tmp_path: Path) -> None:
    DayLog(tmp_path / "sub").flush()
    assert not (tmp_path / "sub").exists()


def test_report_orders_and_formats(tmp_path: Path) -> None:
    log = DayLog(tmp_path)
    log.add(_now(NOON, "leisure", (MPV,), "mpv"), 125.0)
    log.add(_now(NOON, "leisure", (YT,), "Helium"), 4000.0)
    log.flush()
    lines = render_report(tmp_path, date(2026, 10, 19), top=2).splitlines()
    assert "1h06m" in lines[1]
    assert "domain:youtube.com" in lines[1]
    assert "2m05s" in lines[2]
