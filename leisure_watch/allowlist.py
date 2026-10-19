"""The app and domain allowlists: what does NOT count as leisure."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from importlib import resources
import logging
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

USER_ALLOWLIST = Path.home() / ".config" / "leisure-watch" / "allowlist.toml"

_LISTS = (
    ("domains", "allow"),
    ("localhost", "hosts"),
    ("localhost", "deny_ports"),
    ("internal", "schemes"),
    ("apps", "classes"),
    ("apps", "titles"),
)


@dataclass(frozen=True)
class Allowlist:
    """Everything the classifier treats as productive (free)."""

    domains: frozenset[str]
    local_hosts: frozenset[str]
    deny_ports: frozenset[int]
    internal_schemes: frozenset[str]
    app_globs: tuple[str, ...]
    titles: tuple[str, ...]

    def url_allowed(self, url: str) -> bool:
        """Whether a browser tab on *url* is free."""
        if not url:
            return True
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return False
        scheme = parts.scheme.lower()
        if scheme in self.internal_schemes:
            return True
        if scheme not in {"http", "https"}:
            return False
        return self._host_allowed((parts.hostname or "").rstrip("."), port)

    def _host_allowed(self, host: str, port: int | None) -> bool:
        if host in self.local_hosts:
            return port not in self.deny_ports
        if port is not None and f"{host}:{port}" in self.domains:
            return True
        return any(host == d or host.endswith("." + d) for d in self.domains)

    def class_allowed(self, instance: str, cls: str) -> bool:
        """Whether a WM_CLASS instance or class matches an app glob."""
        names = (instance.lower(), cls.lower())
        return any(fnmatchcase(n, g) for n in names for g in self.app_globs)

    def title_allowed(self, title: str) -> bool:
        """Whether a window title starts with an allowlisted title."""
        lowered = title.lower()
        return any(lowered.startswith(t) for t in self.titles)

    def app_allowed(self, instance: str, cls: str, title: str) -> bool:
        """Whether a focused window (WM_CLASS + title) is free."""
        return self.class_allowed(instance, cls) or self.title_allowed(title)

    def binary_allowed(self, binary: str) -> bool:
        """Whether audio from a process binary (pipewire) is free."""
        return self.app_allowed(binary, binary, "")


def host_key(url: str) -> str:
    """Return the ``domain:`` key for *url*: lowercase host minus ``www.``.

    URLs without a host (``about:blank``) or that do not parse are keyed by
    the URL itself, so they still show up in the review log.
    """
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return url
    if not host:
        return url
    return host.rstrip(".").removeprefix("www.")


def _read_toml(text: str, origin: str) -> dict[str, object]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        logger.warning("allowlist %s is not valid TOML; ignoring it", origin)
        return {}


def _items(doc: dict[str, object], table: str, key: str) -> list[object]:
    section = doc.get(table)
    if not isinstance(section, dict):
        return []
    value = section.get(key)
    return list(value) if isinstance(value, list) else []


def _strings(values: Iterable[object]) -> list[str]:
    return [v.lower() for v in values if isinstance(v, str) and v]


def load_allowlist(user_file: Path | None = USER_ALLOWLIST) -> Allowlist:
    """Load the packaged defaults, extended by *user_file* if it exists."""
    default_text = (
        resources.files("leisure_watch")
        .joinpath("default_allowlist.toml")
        .read_text(encoding="utf-8")
    )
    docs = [_read_toml(default_text, "default")]
    if user_file is not None and user_file.is_file():
        docs.append(_read_toml(user_file.read_text(encoding="utf-8"), str(user_file)))
    merged = {f"{t}.{k}": [v for d in docs for v in _items(d, t, k)] for t, k in _LISTS}
    return Allowlist(
        domains=frozenset(_strings(merged["domains.allow"])),
        local_hosts=frozenset(_strings(merged["localhost.hosts"])),
        deny_ports=frozenset(
            p for p in merged["localhost.deny_ports"] if isinstance(p, int)
        ),
        internal_schemes=frozenset(_strings(merged["internal.schemes"])),
        app_globs=tuple(_strings(merged["apps.classes"])),
        titles=tuple(_strings(merged["apps.titles"])),
    )
