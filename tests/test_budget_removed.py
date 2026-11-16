"""The gaming/leisure budget is gone (earned_time 0.22.0): nothing may turn on.

``conftest`` pushes ``GAMING_UNLIMITED_FROM`` out so the dormant Phase 2
mechanics stay tested; these tests restore the real date.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from earned_time import _gaming
import pytest

from leisure_watch import golive, phase2
from leisure_watch.allowlist import load_allowlist
from tests.test_golive import Fake, _env, _text

if TYPE_CHECKING:
    from pathlib import Path

AFTER = datetime.fromisoformat("2026-11-17T12:00:00").astimezone().timestamp()


@pytest.fixture(autouse=True)
def budget_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real 0.22.0 switch date."""
    monkeypatch.setattr(_gaming, "GAMING_UNLIMITED_FROM", date(2026, 11, 16))


def test_a_switch_file_no_longer_activates_phase2(fake_switch: Path) -> None:
    fake_switch.parent.mkdir(parents=True)
    fake_switch.write_text("2026-11-09\n", encoding="ascii")
    assert phase2.active(AFTER) is False


def test_the_browser_gets_an_inactive_unspent_status(
    tmp_path: Path, fake_switch: Path
) -> None:
    fake_switch.parent.mkdir(parents=True)
    fake_switch.write_text("2026-11-09\n", encoding="ascii")
    doc = phase2.block_doc(load_allowlist(tmp_path / "none.toml"), AFTER)
    assert (doc["active"], doc["spent"]) == (False, False)


def test_go_live_refuses_and_writes_nothing(tmp_path: Path, fake_switch: Path) -> None:
    fake = Fake()
    assert golive.go_live(_env(tmp_path, fake_switch, fake, AFTER)) == 2
    assert fake.calls == []
    assert not fake_switch.exists()
    assert "budget" in _text(fake)
