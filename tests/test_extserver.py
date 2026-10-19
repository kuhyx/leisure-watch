"""Tests for the localhost extension endpoint."""

from __future__ import annotations

import http.client
import json
from typing import TYPE_CHECKING

import pytest

from leisure_watch.extserver import ExtensionServer, ReportStore, parse_report

if TYPE_CHECKING:
    from collections.abc import Iterator

ORIGIN = "chrome-extension://abcdef"
GOOD = {
    "browser": "helium",
    "url": "https://github.com/",
    "title": "GitHub",
    "focused": True,
    "audible": ["https://youtube.com/"],
    "ts": 1.0,
}


@pytest.fixture
def server() -> Iterator[tuple[ExtensionServer, list[int]]]:
    calls: list[int] = []
    srv = ExtensionServer(
        0, ReportStore(), lambda: calls.append(1), lambda: {"state": "free"}
    )
    srv.start()
    yield srv, calls
    srv.stop()


def _request(
    srv: ExtensionServer,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    out = (resp.status, dict(resp.getheaders()), resp.read())
    conn.close()
    return out


class TestParse:
    def test_good(self) -> None:
        report = parse_report(json.dumps(GOOD).encode(), 5.0)
        assert report is not None
        assert (report.browser, report.audible, report.received) == (
            "helium",
            ("https://youtube.com/",),
            5.0,
        )

    @pytest.mark.parametrize(
        "change",
        [
            {"browser": "chrome"},
            {"url": 3},
            {"title": None},
            {"focused": "yes"},
            {"audible": "x"},
            {"audible": [1]},
            {"audible": ["u"] * 101},
            {"url": "x" * 9000},
            {"incognito": "yes"},
        ],
    )
    def test_rejects(self, change: dict[str, object]) -> None:
        assert parse_report(json.dumps({**GOOD, **change}).encode(), 1.0) is None

    def test_incognito_flag(self) -> None:
        old = parse_report(json.dumps(GOOD).encode(), 1.0)
        new = parse_report(json.dumps({**GOOD, "incognito": True}).encode(), 1.0)
        assert old is not None
        assert new is not None
        assert (old.incognito, new.incognito) == (False, True)

    @pytest.mark.parametrize(
        "body", [b"{bad", b"[1]", b"\xff", b"[" * 100_000 + b"]" * 100_000]
    )
    def test_rejects_non_objects(self, body: bytes) -> None:
        assert parse_report(body, 1.0) is None


class TestServer:
    def test_report_is_stored_and_wakes_the_watcher(
        self, server: tuple[ExtensionServer, list[int]]
    ) -> None:
        srv, calls = server
        status, headers, _ = _request(
            srv,
            "POST",
            "/report",
            json.dumps(GOOD).encode(),
            {"Origin": ORIGIN, "Content-Type": "text/plain"},
        )
        assert status == 204
        assert headers["Access-Control-Allow-Origin"] == ORIGIN
        assert srv.store.snapshot()["helium"].url == "https://github.com/"
        assert calls == [1]

    def test_web_pages_are_refused(
        self, server: tuple[ExtensionServer, list[int]]
    ) -> None:
        srv, _ = server
        for headers in ({"Origin": "https://evil.example"}, {}):
            status, _, _ = _request(
                srv, "POST", "/report", json.dumps(GOOD).encode(), headers
            )
            assert status == 403
        assert srv.store.snapshot() == {}

    def test_size_limit_and_bad_payload(
        self, server: tuple[ExtensionServer, list[int]]
    ) -> None:
        srv, _ = server
        big = b"x" * (65 * 1024)
        assert _request(srv, "POST", "/report", big, {"Origin": ORIGIN})[0] == 413
        assert _request(srv, "POST", "/report", b"{}", {"Origin": ORIGIN})[0] == 400
        assert _request(srv, "POST", "/nope", b"{}", {"Origin": ORIGIN})[0] == 404

    def test_bad_content_length(
        self, server: tuple[ExtensionServer, list[int]]
    ) -> None:
        srv, _ = server
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
        conn.putrequest("POST", "/report")
        conn.putheader("Origin", ORIGIN)
        conn.putheader("Content-Length", "abc")
        conn.endheaders()
        assert conn.getresponse().status == 411
        conn.close()

    def test_preflight(self, server: tuple[ExtensionServer, list[int]]) -> None:
        srv, _ = server
        status, headers, _ = _request(
            srv, "OPTIONS", "/report", headers={"Origin": ORIGIN}
        )
        assert status == 204
        assert "POST" in headers["Access-Control-Allow-Methods"]
        assert (
            _request(srv, "OPTIONS", "/report", headers={"Origin": "https://x"})[0]
            == 403
        )

    def test_status(self, server: tuple[ExtensionServer, list[int]]) -> None:
        srv, _ = server
        status, _, body = _request(srv, "GET", "/status")
        assert (status, json.loads(body)) == (200, {"state": "free"})
        assert _request(srv, "GET", "/other")[0] == 404

    def test_status_error_is_500(self) -> None:
        def boom() -> dict[str, object]:
            raise RuntimeError

        srv = ExtensionServer(0, ReportStore(), lambda: None, boom)
        srv.start()
        try:
            assert _request(srv, "GET", "/status")[0] == 500
        finally:
            srv.stop()
