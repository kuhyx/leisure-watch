"""Tests for the Phase-2 switch and the spent/active doc behind GET /status."""

from __future__ import annotations

from datetime import datetime
import json
from typing import TYPE_CHECKING

import earned_time
import pytest

from leisure_watch import phase2
from leisure_watch.allowlist import load_allowlist

if TYPE_CHECKING:
    from pathlib import Path


def _ts(text: str) -> float:
    return datetime.fromisoformat(text).astimezone().timestamp()


NOON = _ts("2026-10-20T12:00:00")


def _switch(path: Path, day: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(day + "\n", encoding="ascii")


def _state(path: Path, **fields: object) -> None:
    doc = {"day_key": "2026-10-20", "seconds": 100.0, "budget_seconds": 200.0}
    doc.update(fields)
    path.write_text(json.dumps(doc), encoding="utf-8")


class TestHygiene:
    def test_the_real_switch_file_is_never_read(self, fake_switch: Path) -> None:
        assert str(fake_switch) != "/etc/leisure-watch/leisure_from"
        assert fake_switch == phase2.SWITCH_PATH
        _switch(fake_switch, "2026-10-19")
        # A bare call (default path) sees the fake file, so the canary holds.
        assert earned_time.leisure_active(earned_time.LEISURE_FROM)
        assert earned_time.leisure_from().isoformat() == "2026-10-19"


class TestActive:
    def test_parked_without_a_switch_file(self) -> None:
        assert phase2.active(NOON) is False

    def test_on_from_the_switch_day(self, fake_switch: Path) -> None:
        _switch(fake_switch, "2026-10-20")
        assert phase2.active(NOON) is True

    @pytest.mark.parametrize(
        ("when", "expected"),
        [("2026-10-20T05:59:00", False), ("2026-10-20T06:00:00", True)],
    )
    def test_gaming_day_boundary_is_six(
        self, fake_switch: Path, when: str, *, expected: bool
    ) -> None:
        _switch(fake_switch, "2026-10-20")
        assert phase2.active(_ts(when)) is expected

    def test_explicit_path(self, tmp_path: Path) -> None:
        other = tmp_path / "other"
        _switch(other, "2026-01-01")
        assert phase2.active(NOON, other) is True


class TestBudget:
    def test_dormant_is_never_spent(self, fake_state: Path) -> None:
        _state(fake_state, seconds=999.0)
        assert phase2.budget_today(NOON, is_active=False) == phase2.Budget(
            None, None, spent=False
        )

    def test_under_budget(self, fake_state: Path) -> None:
        _state(fake_state)
        assert phase2.budget_today(NOON, is_active=True) == phase2.Budget(
            100.0, 200.0, spent=False
        )

    def test_at_budget_is_spent(self, fake_state: Path) -> None:
        _state(fake_state, seconds=200)
        assert phase2.budget_today(NOON, is_active=True).spent is True

    def test_unreadable_fails_closed(self) -> None:
        assert phase2.budget_today(NOON, is_active=True) == phase2.Budget(
            None, None, spent=True
        )

    @pytest.mark.parametrize(
        "fields",
        [
            {"seconds": "100"},
            {"seconds": True},
            {"budget_seconds": None},
            {"day_key": 20261020},
        ],
    )
    def test_malformed_fails_closed(
        self, fake_state: Path, fields: dict[str, object]
    ) -> None:
        _state(fake_state, **fields)
        assert phase2.budget_today(NOON, is_active=True).spent is True

    def test_other_day_is_nothing_used_yet(self, fake_state: Path) -> None:
        # Yesterday's record before the enforcer's first 06:00 tick rolls it.
        _state(fake_state, day_key="2026-10-19", seconds=999.0)
        assert phase2.budget_today(NOON, is_active=True) == phase2.Budget(
            0.0, None, spent=False
        )

    def test_explicit_state_path(self, tmp_path: Path) -> None:
        other = tmp_path / "other.json"
        _state(other, seconds=300.0)
        assert phase2.budget_today(NOON, is_active=True, state_path=other).spent


class TestBlockDoc:
    def test_shape(self, fake_switch: Path, fake_state: Path) -> None:
        _switch(fake_switch, "2026-10-20")
        _state(fake_state, seconds=250.0)
        doc = phase2.block_doc(load_allowlist(None), NOON)
        assert doc["active"] is True
        assert doc["spent"] is True
        assert (doc["used_seconds"], doc["budget_seconds"]) == (250.0, 200.0)
        assert doc["day"] == "2026-10-20"
        allow = doc["allow"]
        assert isinstance(allow, list)
        assert "github.com" in allow
        assert allow == sorted(allow)
        hosts, ports = doc["local_hosts"], doc["deny_ports"]
        assert isinstance(hosts, list)
        assert "localhost" in hosts
        assert isinstance(ports, list)
        assert ports
