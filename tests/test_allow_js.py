"""The extension's URL matcher agrees with the Python allowlist (differential).

``extension/allow.js`` re-implements ``Allowlist.url_allowed`` for the http(s)
URLs the extension may redirect; ``GET /status`` ships it the same lists. One
URL table runs through both, under ``node``.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from leisure_watch import phase2
from leisure_watch.allowlist import load_allowlist

ALLOW_JS = Path(__file__).resolve().parent.parent / "extension" / "allow.js"
NODE = shutil.which("node")

WEB = [
    "https://www.youtube.com/watch?v=x",
    "https://youtube.com/",
    "https://github.com/kuhyx",
    "https://GitHub.com./x",
    "https://gist.github.com/",
    "https://notgithub.com/",
    "https://github.com.evil.com/",
    "https://user:pw@github.com/",
    "http://localhost:3000/",
    "http://localhost:8765/wsg/",
    "http://127.0.0.1:8765/",
    "http://127.0.0.1/",
    "http://localhost:80/",
    "http://100.109.64.41:5600/",
    "http://100.109.64.41:5601/",
    "http://100.109.64.41/",
    "https://mail.google.com/mail/u/0",
    "https://google.com/",
    "https://leetcode.com/problems/two-sum/",
    "http://[::1]:8765/",
    "http://[::1]/",
    "https://pw.edu.pl:443/",
    "https://usosweb.pw.edu.pl/",
    "https://github.com:99999/",
    "http:///nohost",
]
NOT_WEB = [
    "",
    "about:blank",
    "chrome://newtab/",
    "chrome-extension://abc/spent.html",
    "moz-extension://abc/spent.html",
    "file:///home/kuhy/x.html",
    "view-source:https://youtube.com/",
    "data:text/html,hi",
]

_DRIVER = (
    "const a = require(process.argv[1]);"
    "const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
    "process.stdout.write(JSON.stringify(inp.urls.map("
    "(u) => [a.urlAllowed(u, inp.status), a.shouldBlock(u, inp.status)])));"
)


def _node(urls: list[str], status: dict[str, object]) -> list[list[bool]]:
    assert NODE is not None
    done = subprocess.run(
        [NODE, "-e", _DRIVER, str(ALLOW_JS)],
        input=json.dumps({"urls": urls, "status": status}),
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    result: list[list[bool]] = json.loads(done.stdout)
    return result


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_js_matches_python_on_web_urls() -> None:
    allow = load_allowlist(None)
    status = phase2.block_doc(allow, 0.0)
    got = _node(WEB, status)
    expected = [allow.url_allowed(u) for u in WEB]
    assert [g[0] for g in got] == expected
    assert [g[1] for g in got] == [not e for e in expected]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_browser_internal_pages_are_never_blocked() -> None:
    status = phase2.block_doc(load_allowlist(None), 0.0)
    assert [g[1] for g in _node(NOT_WEB, status)] == [False] * len(NOT_WEB)
