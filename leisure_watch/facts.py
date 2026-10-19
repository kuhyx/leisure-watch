"""The signed ``now.json`` fact file (contract C3), written and read.

The user watcher writes it every 5 s; the root enforcer reads it with
:func:`read_now`. ``None`` from the reader always means "do not trust this"
(missing, stale, from the future, malformed or badly signed), and the
enforcer bills shadow time unless paused -- the reader never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Final

from leisure_watch import _safeio

VERSION: Final = 1
HMAC_KEY_FILE: Final = Path("/etc/workout-locker/hmac.key")
STATES: Final = frozenset({"leisure", "free", "paused"})
DESKTOP_UID: Final = 1000

# A writer clock a little ahead of the reader's is tolerated, no more.
_FUTURE_SKEW: Final = 2.0


@dataclass(frozen=True)
class Reason:
    """One thing that makes this moment leisure."""

    source: str  # focus | media | game | failclosed
    key: str  # app:mpv | domain:youtube.com | steam:1091500 | ...
    pid: int | None
    label: str


@dataclass(frozen=True)
class Focus:
    """What has the keyboard right now."""

    app: str
    title: str
    domain: str | None
    idle: bool


@dataclass(frozen=True)
class Now:
    """One published moment."""

    ts: float
    seq: int
    state: str
    paused_by: str | None
    reasons: tuple[Reason, ...]
    focus: Focus
    extensions: dict[str, float | None] = field(default_factory=dict)
    v: int = VERSION


def default_now_path() -> Path:
    """``$XDG_RUNTIME_DIR/leisure-watch/now.json``; root reads the desktop user's."""
    uid = os.getuid()
    if uid == 0:
        return Path(f"/run/user/{DESKTOP_UID}/leisure-watch/now.json")
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    return Path(runtime) / "leisure-watch" / "now.json"


def read_key(key_file: Path) -> bytes | None:
    """The signing key (stripped, as earned_time reads it), or ``None``."""
    try:
        key = key_file.read_bytes().strip()
    except OSError:
        return None
    return key or None


def to_doc(now: Now) -> dict[str, object]:
    """Serialise *now* without its signature."""
    return {
        "v": now.v,
        "ts": now.ts,
        "seq": now.seq,
        "state": now.state,
        "paused_by": now.paused_by,
        "reasons": [
            {"source": r.source, "key": r.key, "pid": r.pid, "label": r.label}
            for r in now.reasons
        ],
        "focus": {
            "app": now.focus.app,
            "title": now.focus.title,
            "domain": now.focus.domain,
            "idle": now.focus.idle,
        },
        "extensions": dict(now.extensions),
    }


def signature(doc: dict[str, object], key: bytes) -> str:
    """HMAC-SHA256 hex over the canonical JSON of *doc* (minus ``sig``)."""
    body = {k: v for k, v in doc.items() if k != "sig"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def signed_doc(now: Now, key_file: Path = HMAC_KEY_FILE) -> dict[str, object]:
    """*now* as a document with ``sig``; ``""`` when the key is unreadable."""
    doc = to_doc(now)
    key = read_key(key_file)
    doc["sig"] = signature(doc, key) if key is not None else ""
    return doc


def write_now(path: Path, now: Now, key_file: Path = HMAC_KEY_FILE) -> None:
    """Atomically replace *path* with the signed *now*, mode 0644."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(signed_doc(now, key_file), ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".now.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(data)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _reason(raw: object) -> Reason | None:
    if not isinstance(raw, dict):
        return None
    source, key, pid, label = (raw.get(k) for k in ("source", "key", "pid", "label"))
    if not (isinstance(source, str) and isinstance(key, str)):
        return None
    if not isinstance(label, str) or not (pid is None or type(pid) is int):
        return None
    return Reason(source, key, pid, label)


def _focus(raw: object) -> Focus | None:
    if not isinstance(raw, dict):
        return None
    app, title, domain, idle = (raw.get(k) for k in ("app", "title", "domain", "idle"))
    if not (isinstance(app, str) and isinstance(title, str)):
        return None
    if not (domain is None or isinstance(domain, str)) or not isinstance(idle, bool):
        return None
    return Focus(app, title, domain, idle=idle)


def _extensions(raw: object) -> dict[str, float | None] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, float | None] = {}
    for name, seen in raw.items():
        if seen is not None and not isinstance(seen, (int, float)):
            return None
        out[str(name)] = None if seen is None else float(seen)
    return out


def parse_doc(doc: dict[str, object]) -> Now | None:
    """Validate a decoded document (signature already checked) into a :class:`Now`."""
    ts, seq, state, paused_by = (
        doc.get(k) for k in ("ts", "seq", "state", "paused_by")
    )
    if doc.get("v") != VERSION or state not in STATES or type(seq) is not int:
        return None
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return None
    if not (paused_by is None or isinstance(paused_by, str)):
        return None
    raw_reasons = doc.get("reasons")
    if not isinstance(raw_reasons, list):
        return None
    reasons = tuple(_reason(r) for r in raw_reasons)
    focus = _focus(doc.get("focus"))
    extensions = _extensions(doc.get("extensions"))
    if focus is None or extensions is None or None in reasons:
        return None
    return Now(
        ts=float(ts),
        seq=seq,
        state=str(state),
        paused_by=paused_by,
        reasons=tuple(r for r in reasons if r is not None),
        focus=focus,
        extensions=extensions,
    )


def _verified(doc: dict[str, object], key: bytes) -> Now | None:
    sig = doc.get("sig")
    if not isinstance(sig, str) or not hmac.compare_digest(sig, signature(doc, key)):
        return None
    return parse_doc(doc)


def read_now(
    path: Path,
    now: float,
    max_age: float = 15,
    key_file: Path = HMAC_KEY_FILE,
) -> Now | None:
    """The verified fact at *path*, or ``None`` if missing/stale/bad-sig.

    *path* is user-writable and root reads it: a FIFO, symlink, oversized or
    undecodable file is ``None`` too (fail closed), never a hang or a raise.
    """
    key = read_key(key_file)
    doc = _safeio.json_object(_safeio.read_regular(path))
    if key is None or doc is None:
        return None
    try:
        parsed = _verified(doc, key)
    except RecursionError:
        return None
    if parsed is None or not now - max_age <= parsed.ts <= now + _FUTURE_SKEW:
        return None
    return parsed
