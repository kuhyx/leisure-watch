"""Shared fixtures: every test sees a private, empty /proc and config."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
