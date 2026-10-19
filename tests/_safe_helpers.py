"""Run a call that must not block (the FIFO regression tests)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def call_within[T](fn: Callable[[], T], seconds: float = 2.0) -> T:
    """Return ``fn()``; fail the test if it has not returned within *seconds*.

    A blocked reader stays parked in a daemon thread, so a regression shows
    up as a failed assertion instead of a hung test run.
    """
    box: list[T] = []
    worker = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    worker.start()
    worker.join(seconds)
    assert box, f"call blocked or raised within {seconds} s"
    return box[0]
