// The allowlist matcher, mirroring leisure_watch.allowlist.Allowlist.url_allowed
// for every URL a tab can show. The lists come from the daemon's GET /status,
// never from this file, so the Python and JS sides cannot drift apart
// (tests/test_allow_js.py runs both on one table).
//
// The build prepends this file to background.js; node loads it directly.
"use strict";

// urlsplit's scheme: letters first, then letters, digits, "+", "-", ".".
function schemeOf(url) {
  const match = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(url);
  return match ? match[1].toLowerCase() : "";
}

// Python's urlsplit().port: the explicit port as written (80 stays 80, where
// URL.port would say ""), null when absent, NaN when it would raise.
function rawPort(url) {
  const authority = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/([^/?#]*)/.exec(url);
  if (!authority) {
    return null;
  }
  const hostPort = authority[1].slice(authority[1].lastIndexOf("@") + 1);
  const bracket = hostPort.indexOf("[");
  const tail =
    bracket >= 0 ? hostPort.slice(hostPort.indexOf("]", bracket) + 1) : hostPort;
  const colon = tail.indexOf(":");
  const port = colon >= 0 ? tail.slice(colon + 1) : "";
  if (!port) {
    return null;
  }
  return /^[0-9]+$/.test(port) && Number(port) <= 65535 ? Number(port) : NaN;
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

// Whether a tab on *url* is free (productive): browser-internal pages are,
// other non-web schemes (file:, view-source:, blob:, data:, ftp:) are not.
function urlAllowed(url, status) {
  if (!url) {
    return true;
  }
  const port = rawPort(url);
  if (Number.isNaN(port)) {
    return false;
  }
  const scheme = schemeOf(url);
  if (status.internal_schemes.includes(scheme)) {
    return true;
  }
  if (scheme !== "http" && scheme !== "https") {
    return false;
  }
  let parsed;
  try {
    parsed = new URL(url);
  } catch (_err) {
    return false;
  }
  const host = parsed.hostname.replace(/^\[|\]$/g, "").replace(/\.+$/, "");
  return hostAllowed(status, host, port);
}

// Redirect every tab that is not free, except browser-internal pages (new
// tab, chrome://, about:, extension pages -- our spent.html among them).
function shouldBlock(url, status) {
  return (
    Boolean(url) &&
    !status.internal_schemes.includes(schemeOf(url)) &&
    !urlAllowed(url, status)
  );
}

if (typeof module !== "undefined") {
  module.exports = { urlAllowed, shouldBlock };
}
