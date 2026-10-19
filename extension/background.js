// leisure-watch reporter (Phase 1: observe only, never blocks).
//
// Shared by the Chromium (Helium, service worker) and Firefox (LibreWolf,
// background script) builds; the build substitutes BROWSER and PORT.
//
// Liveness matters more than anything else here: the daemon treats a
// focused browser whose report is older than 15 s as leisure (fail closed).
// So every 5 s tick calls tabs.query (an extension API call, which keeps a
// Chromium service worker alive), and a 30 s alarm restarts the loop if the
// worker or event page was suspended anyway.
"use strict";

const BROWSER = "__BROWSER__";
const ENDPOINT = "http://127.0.0.1:__PORT__/report";
const HEARTBEAT_MS = 5000;
const api = globalThis.browser ?? globalThis.chrome;

let timer = null;

async function activeTab() {
  let win = null;
  try {
    win = await api.windows.getLastFocused({ windowTypes: ["normal"] });
  } catch (_err) {
    win = null;
  }
  if (!win) {
    return { tab: {}, focused: false };
  }
  const tabs = await api.tabs.query({ active: true, windowId: win.id });
  return { tab: tabs[0] ?? {}, focused: Boolean(win.focused) };
}

async function snapshot() {
  const { tab, focused } = await activeTab();
  const audible = await api.tabs.query({ audible: true });
  return {
    browser: BROWSER,
    url: tab.url ?? "",
    title: tab.title ?? "",
    focused,
    audible: audible
      .filter((t) => !(t.mutedInfo && t.mutedInfo.muted))
      .map((t) => t.url ?? ""),
    ts: Date.now() / 1000,
  };
}

async function report() {
  try {
    const body = JSON.stringify(await snapshot());
    // text/plain keeps this a "simple" request: no CORS preflight needed.
    await fetch(ENDPOINT, {
      method: "POST",
      body,
      headers: { "Content-Type": "text/plain" },
    });
  } catch (_err) {
    // Daemon down or restarting: the next heartbeat retries.
  }
}

function ensureHeartbeat() {
  if (timer === null) {
    timer = setInterval(report, HEARTBEAT_MS);
  }
  report();
}

api.tabs.onActivated.addListener(report);
api.tabs.onUpdated.addListener((_id, change) => {
  if ("url" in change || "title" in change || "audible" in change) {
    report();
  }
});
api.tabs.onRemoved.addListener(report);
api.windows.onFocusChanged.addListener(report);
api.runtime.onStartup.addListener(ensureHeartbeat);
api.runtime.onInstalled.addListener(ensureHeartbeat);
api.alarms.onAlarm.addListener(ensureHeartbeat);
api.alarms.create("leisure-watch-heartbeat", { periodInMinutes: 0.5 });
ensureHeartbeat();
