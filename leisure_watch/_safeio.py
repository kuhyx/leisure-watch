"""Read small JSON files from user-writable places without trusting them.

The root enforcer reads ``now.json`` and the gatelock claims from the desktop
user's runtime dir, so whatever sits there is attacker-shaped: a FIFO (a
plain ``open`` blocks forever), a symlink (to anything root can read), a
huge file, or JSON nested deep enough to overflow the decoder. Every reader
here answers ``None`` for all of those instead of hanging or raising.
Stdlib only, root-safe.
"""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

MAX_BYTES: Final = 64 * 1024

# O_NONBLOCK: opening a FIFO returns at once instead of waiting for a writer.
# O_NOFOLLOW: a symlink in the final component fails with ELOOP.
_FLAGS: Final = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC


def open_regular(path: Path) -> int | None:
    """A read-only fd on *path* if it is a regular file (no symlink), else ``None``.

    The caller owns the fd and must close it.
    """
    try:
        fd = os.open(path, _FLAGS)
    except OSError:
        return None
    if stat.S_ISREG(os.fstat(fd).st_mode):
        return fd
    os.close(fd)
    return None


def read_fd(fd: int, limit: int = MAX_BYTES) -> bytes | None:
    """Everything left in *fd*, or ``None`` past *limit* bytes or on error."""
    buf = bytearray()
    try:
        while len(buf) <= limit:
            chunk = os.read(fd, limit + 1 - len(buf))
            if not chunk:
                return bytes(buf)
            buf += chunk
    except OSError:
        return None
    return None


def read_regular(path: Path, limit: int = MAX_BYTES) -> bytes | None:
    """The bytes of the regular file *path* (at most *limit*), else ``None``."""
    fd = open_regular(path)
    if fd is None:
        return None
    try:
        return read_fd(fd, limit)
    finally:
        os.close(fd)


def json_object(data: bytes | None) -> dict[str, object] | None:
    """*data* decoded as a UTF-8 JSON object, or ``None`` for anything else."""
    if data is None:
        return None
    try:
        doc = json.loads(data.decode("utf-8"))
    except RecursionError, ValueError:  # UnicodeDecodeError is a ValueError
        return None
    return doc if isinstance(doc, dict) else None
