"""Daily classification log for the allowlist review.

``~/.local/share/leisure-watch/<YYYY-MM-DD>.jsonl``: one line per
``(state, source, key)`` with the seconds it accounted for that day, plus a
``total``/``wall`` row per state (overlaps bill once there). Days roll at
06:00, the same gaming day the enforcer uses. The file is rewritten
atomically, so a crash loses at most the last unflushed seconds.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from leisure_watch.facts import Now

DEFAULT_DIR: Final = Path.home() / ".local" / "share" / "leisure-watch"
DAY_START: Final = timedelta(hours=6)

Row = tuple[str, str, str]  # state, source, key


def gaming_day(ts: float) -> date:
    """The 06:00-to-06:00 day *ts* falls in."""
    local = datetime.fromtimestamp(ts, tz=UTC).astimezone()
    return (local - DAY_START).date()


def _path(root: Path, day: date) -> Path:
    return root / f"{day.isoformat()}.jsonl"


def _load(path: Path) -> tuple[dict[Row, float], dict[Row, str]]:
    seconds: dict[Row, float] = {}
    labels: dict[Row, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return seconds, labels
    for line in lines:
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        row = (str(raw.get("state")), str(raw.get("source")), str(raw.get("key")))
        value = raw.get("seconds")
        if isinstance(value, (int, float)):
            seconds[row] = float(value)
            labels[row] = str(raw.get("label", ""))
    return seconds, labels


class DayLog:
    """In-memory aggregate for the current gaming day, flushed to disk."""

    def __init__(self, root: Path = DEFAULT_DIR) -> None:
        """Aggregate under *root*; the day's file is loaded lazily."""
        self.root = root
        self._day: date | None = None
        self._seconds: dict[Row, float] = {}
        self._labels: dict[Row, str] = {}

    def _switch(self, day: date) -> None:
        if day == self._day:
            return
        if self._day is not None:
            self.flush()
        self._day = day
        self._seconds, self._labels = _load(_path(self.root, day))

    def _bump(self, row: Row, dt: float, label: str) -> None:
        self._seconds[row] = self._seconds.get(row, 0.0) + dt
        self._labels[row] = label

    def add(self, now: Now, dt: float) -> None:
        """Account *dt* seconds ending at *now* to each reason (or the focus)."""
        self._switch(gaming_day(now.ts))
        for reason in now.reasons:
            self._bump((now.state, reason.source, reason.key), dt, reason.label)
        if not now.reasons:
            focus = now.focus
            key = (
                f"domain:{focus.domain}" if focus.domain else f"app:{focus.app.lower()}"
            )
            self._bump((now.state, "focus", key), dt, focus.app)
        self._bump((now.state, "total", "wall"), dt, "")

    def flush(self) -> None:
        """Atomically rewrite the current day's file."""
        if self._day is None or not self._seconds:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(
                {
                    "state": s,
                    "source": src,
                    "key": k,
                    "label": self._labels.get((s, src, k), ""),
                    "seconds": round(v, 1),
                },
                ensure_ascii=False,
            )
            for (s, src, k), v in sorted(self._seconds.items())
        ]
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".day.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        Path(tmp).replace(_path(self.root, self._day))


def _fmt(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def render_report(root: Path, day: date, top: int = 25) -> str:
    """The top leisure keys of *day*, longest first."""
    seconds, labels = _load(_path(root, day))
    wall = seconds.get(("leisure", "total", "wall"), 0.0)
    rows = sorted(
        (
            (v, row)
            for row, v in seconds.items()
            if row[0] == "leisure" and row[1] != "total"
        ),
        reverse=True,
    )
    if not rows:
        return f"{day.isoformat()}: no leisure recorded"
    out = [f"{day.isoformat()}: leisure {_fmt(wall)} wall-clock (overlaps once)"]
    out.extend(
        f"{_fmt(v):>8}  {src:<10}  {key}  {labels.get((s, src, key), '')}".rstrip()
        for v, (s, src, key) in rows[:top]
    )
    return "\n".join(out)
