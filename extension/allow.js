// The allowlist matcher, mirroring leisure_watch.allowlist.Allowlist.url_allowed
// for the web (http/https) URLs the extension may redirect. The lists come
// from the daemon's GET /status, never from this file, so the Python and JS
// sides cannot drift apart (tests/test_allow_js.py runs both on one table).
//
// The build prepends this file to background.js; node loads it directly.
"use strict";

// Python's urlsplit().port: the explicit port as written (80 stays 80, where
// URL.port would say ""), null when absent.
function rawPort(url) {
  const authority = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/([^/?#]*)/.exec(url);
  if (!authority) {
    return null;
  }
  const hostPort = authority[1].slice(authority[1].lastIndexOf("@") + 1);
  const port = /:(\d+)$/.exec(hostPort);
  return port ? Number(port[1]) : null;
}

function isWeb(url) {
  return /^https?:\/\//i.test(url);
}

function hostAllowed(status, host, port) {
  if (status.local_hosts.includes(host)) {
    return !status.deny_ports.includes(port);
  }
  if (port !== null && status.allow.includes(`${host}:${port}`)) {
    return true;
  }
  return status.allow.some((d) => host === d || host.endsWith(`.${d}`));
}

// Whether a web URL is free (productive). Non-web URLs are not judged here.
function urlAllowed(url, status) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch (_err) {
    return false;
  }
  const port = rawPort(url);
  if (port !== null && port > 65535) {
    return false;
  }
  const host = parsed.hostname.replace(/^\[|\]$/g, "").replace(/\.+$/, "");
  return hostAllowed(status, host, port);
}

// Redirect only web pages that are not allowlisted; browser-internal pages
// (new tab, chrome://, about:, extension pages, file:, data:) stay untouched.
function shouldBlock(url, status) {
  return Boolean(url) && isWeb(url) && !urlAllowed(url, status);
}

if (typeof module !== "undefined") {
  module.exports = { urlAllowed, shouldBlock };
}
