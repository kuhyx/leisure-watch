"""The localhost endpoint our browser extension reports to.

Binds 127.0.0.1 only. ``POST /report`` accepts a small JSON body from an
extension origin (``chrome-extension://`` / ``moz-extension://``) -- a web
page cannot forge that header from a browser, so a page cannot fake a
"github" report. ``GET /now`` returns the watcher's current computed
document, so ``leisure-watch status`` sees the live extension data;
``GET /status`` is the cheap Phase-2 document the extension polls (active,
spent, allowlist), readable cross-origin by extension origins only.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading
import time
from typing import TYPE_CHECKING, ClassVar, Final

from leisure_watch._browser import EXTENSION_BROWSERS, ExtReport

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    Route = Callable[[], dict[str, object]]

logger = logging.getLogger(__name__)

PORT: Final = 8775
MAX_BODY: Final = 64 * 1024
_MAX_URL: Final = 8192
_MAX_TITLE: Final = 2048
_MAX_AUDIBLE: Final = 100
_ORIGINS: Final = ("chrome-extension://", "moz-extension://")


def parse_report(body: bytes, received: float) -> ExtReport | None:
    """Validate one report body; ``None`` if anything is off."""
    try:
        raw = json.loads(body)
    except RecursionError, ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    browser, url, title = raw.get("browser"), raw.get("url"), raw.get("title")
    focused, audible = raw.get("focused"), raw.get("audible")
    incognito = raw.get("incognito", False)  # absent from pre-0.1.2 builds
    if not (
        browser in EXTENSION_BROWSERS
        and isinstance(focused, bool)
        and isinstance(incognito, bool)
        and isinstance(url, str)
        and isinstance(title, str)
        and isinstance(audible, list)
    ):
        return None
    urls = [u for u in audible if isinstance(u, str) and len(u) <= _MAX_URL]
    too_big = len(url) > _MAX_URL or len(title) > _MAX_TITLE
    if too_big or len(audible) > _MAX_AUDIBLE or len(urls) != len(audible):
        return None
    return ExtReport(
        str(browser), url, title, focused, tuple(urls), received, incognito
    )


class ReportStore:
    """Latest report per browser, shared between server and watcher threads."""

    def __init__(self) -> None:
        """Start empty."""
        self._lock = threading.Lock()
        self._reports: dict[str, ExtReport] = {}

    def update(self, report: ExtReport) -> None:
        """Keep *report* as its browser's latest."""
        with self._lock:
            self._reports[report.browser] = report

    def snapshot(self) -> dict[str, ExtReport]:
        """A copy of the latest reports."""
        with self._lock:
            return dict(self._reports)


class _Handler(BaseHTTPRequestHandler):
    server_version = "leisure-watch"
    owner: ClassVar[ExtensionServer]

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence per-request logging."""

    def _origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        return origin if origin.startswith(_ORIGINS) else None

    def _reply(self, status: int, body: bytes = b"", origin: str | None = None) -> None:
        self.send_response(status)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """CORS preflight, for extension origins only."""
        origin = self._origin()
        self._reply(204 if origin else 403, origin=origin)

    def do_POST(self) -> None:
        """Accept one extension report."""
        origin = self._origin()
        if self.path != "/report":
            self._reply(404)
            return
        if origin is None:
            self._reply(403)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._reply(411, origin=origin)
            return
        if length > MAX_BODY:
            self._reply(413, origin=origin)
            return
        report = parse_report(self.rfile.read(length), time.time())
        if report is None:
            self._reply(400, origin=origin)
            return
        self.owner.store.update(report)
        self.owner.on_report()
        self._reply(204, origin=origin)

    def do_GET(self) -> None:
        """Serve one computed document (``/now``, ``/status``)."""
        route = self.owner.routes.get(self.path)
        if route is None:
            self._reply(404)
            return
        try:
            body = json.dumps(route(), ensure_ascii=False).encode()
        except Exception:
            logger.exception("%s computation failed", self.path)
            self._reply(500)
            return
        self._reply(200, body, origin=self._origin())


class ExtensionServer:
    """A ThreadingHTTPServer on 127.0.0.1:*port* (0 = any free port)."""

    def __init__(
        self,
        port: int,
        store: ReportStore,
        on_report: Callable[[], None],
        routes: Mapping[str, Route],
    ) -> None:
        """Bind now; serve after :meth:`start`. *routes*: GET path -> doc."""
        self.store = store
        self.on_report = on_report
        self.routes = dict(routes)
        handler = type("Handler", (_Handler,), {"owner": self})
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        """The bound port."""
        return int(self._httpd.server_address[1])

    def start(self) -> None:
        """Serve in a background thread."""
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and close the socket."""
        self._httpd.shutdown()
        self._httpd.server_close()
