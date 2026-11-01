"""Shared plumbing for kt-import: server/config resolution and tiny HTTP helpers.

Split out of kt-import.py (250-line cap). Sits next to it, so the script finds it
through sys.path[0] with no path tricks.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.request
from pathlib import Path


def _load_ktconf():
    """Load the shared config module by path -- see cli/ktconf.py. Loading by path keeps
    the import at top-of-file; a sys.path insert would not."""
    spec = importlib.util.spec_from_file_location(
        "ktconf", Path(__file__).resolve().parent.parent / "cli" / "ktconf.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ktconf = _load_ktconf()
KT = ktconf.url()
TOKEN = ktconf.token()


def kt_call(path, method="GET", body=None):
    req = urllib.request.Request(
        KT + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())
