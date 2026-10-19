// Fills spent.html from its query string (MV3 CSP forbids inline scripts).
// textContent only: the blocked site name is page-controlled text.
"use strict";

function hoursMinutes(raw) {
  const seconds = Number(raw);
  if (raw === null || raw === "" || !Number.isFinite(seconds)) {
    return "?";
  }
  const minutes = Math.floor(seconds / 60);
  return `${Math.floor(minutes / 60)}h${String(minutes % 60).padStart(2, "0")}`;
}

const params = new URLSearchParams(location.search);
document.getElementById("used").textContent = hoursMinutes(params.get("used"));
document.getElementById("budget").textContent = hoursMinutes(params.get("budget"));
document.getElementById("site").textContent = params.get("site") || "this site";
