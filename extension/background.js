// leisure-watch reporter + Phase-2 blocker.
//
// Shared by the Chromium (Helium, service worker) and Firefox (LibreWolf,
// background script) builds; the build substitutes BROWSER and PORT and
// prepends allow.js (urlAllowed / shouldBlock).
//
// Blocking: every heartbeat and every tab event re-reads GET /status. Only
// when it says active && spent is any tab that is not free (a non-allowlisted
// web page, file:, view-source:, blob:, data:, ftp:) sent to the bundled
// spent.html (no bypass). Dormant until go-live's day. The last answer is
// persisted: while the daemon is unreachable (cold start included), a
// last-known ACTIVE status blocks as if spent (fail closed) until it answers.
//
// Liveness matters more than anything else here: the daemon treats a
// focused browser whose report is older than 15 s as leisure (fail closed).
// So every 5 s tick calls tabs.query (an extension API call, which keeps a
// Chromium service worker alive), and a 30 s alarm restarts the loop if the
// worker or event page was suspended anyway.
"use strict";

const BROWSER = "__BROWSER__";
const ENDPOINT = "http://127.0.0.1:__PORT__/report";
const STATUS = "http://127.0.0.1:__PORT__/status";
const HEARTBEAT_MS = 5000;
const api = globalThis.browser ?? globalThis.chrome;

// Every window type, so the report describes the window that REALLY has
// focus (a popup, an app window, a private window when the browser grants
// this extension private access -- manifest "incognito": "spanning").
// Without that grant a private window stays invisible here and the last
// visible window is reported with focused: false; the daemon fails closed.
const WINDOW_FILTERS = [
  { windowTypes: ["normal", "popup", "panel", "app", "devtools"] },
  {}, // a browser that rejects one of those types: its default filter
];

let timer = null;
const STORE_KEY = "leisureStatus";
const SELF = api.runtime.getURL("");
// The last good /status (memory, else storage); null = never seen one, i.e.
// nothing is known to be active and nothing is blocked.
let status = null;
let reachable = false;
let loaded = null;

async function lastFocusedWindow() {
  for (const filter of WINDOW_FILTERS) {
    try {
      return await api.windows.getLastFocused(filter);
    } catch (_err) {
      // try the next filter
    }
  }
  return null;
}

async function activeTab() {
  const win = await lastFocusedWindow();
  if (!win) {
    return { tab: {}, focused: false, incognito: false };
  }
  const tabs = await api.tabs.query({ active: true, windowId: win.id });
  return {
    tab: tabs[0] ?? {},
    focused: Boolean(win.focused),
    incognito: Boolean(win.incognito),
  };
}

async function snapshot() {
  const { tab, focused, incognito } = await activeTab();
  const audible = await api.tabs.query({ audible: true });
  return {
    browser: BROWSER,
    url: tab.url ?? "",
    title: tab.title ?? "",
    focused,
    incognito,
    audible: audible
      .filter((t) => !(t.mutedInfo && t.mutedInfo.muted))
      .map((t) => t.url ?? ""),
    version: api.runtime.getManifest().version,
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

function validStatus(doc) {
  return (
    doc !== null &&
    typeof doc === "object" &&
    typeof doc.active === "boolean" &&
    typeof doc.spent === "boolean" &&
    Array.isArray(doc.allow) &&
    Array.isArray(doc.local_hosts) &&
    Array.isArray(doc.deny_ports) &&
    Array.isArray(doc.internal_schemes)
  );
}

function loadStored() {
  loaded ??= api.storage.local
    .get(STORE_KEY)
    .then((saved) => {
      if (status === null && validStatus(saved[STORE_KEY] ?? null)) {
        status = saved[STORE_KEY];
      }
    })
    .catch(() => {});
  return loaded;
}

async function refreshStatus() {
  await loadStored();
  let doc = null;
  try {
    const resp = await fetch(STATUS, { cache: "no-store" });
    doc = resp.ok ? await resp.json() : null;
  } catch (_err) {
    // Daemon down or restarting: the last known state, failing closed.
  }
  reachable = validStatus(doc);
  if (reachable && JSON.stringify(doc) !== JSON.stringify(status)) {
    status = doc;
    api.storage.local.set({ [STORE_KEY]: doc }).catch(() => {});
  }
}

function blocking() {
  return status !== null && status.active && (status.spent || !reachable);
}

function spentPage(url) {
  let site = url;
  try {
    site = new URL(url).hostname;
  } catch (_err) {
    // keep the raw URL
  }
  const query = new URLSearchParams({
    site,
    used: String(status.used_seconds ?? ""),
    budget: String(status.budget_seconds ?? ""),
  });
  return api.runtime.getURL(`spent.html?${query}`);
}

async function enforceTab(tab) {
  if (!blocking() || !tab || tab.id === undefined) {
    return;
  }
  // pendingUrl (Chromium): a navigation that has not committed yet.
  const target = [tab.pendingUrl, tab.url].find(
    (u) => u && !u.startsWith(SELF) && shouldBlock(u, status),
  );
  if (target) {
    try {
      await api.tabs.update(tab.id, { url: spentPage(target) });
    } catch (_err) {
      // Chromium "spanning" incognito cannot show extension pages: close
      // the private tab instead. Otherwise the tab closed meanwhile.
      if (tab.incognito) {
        await api.tabs.remove(tab.id).catch(() => {});
      }
    }
  }
}

async function enforceAll() {
  await refreshStatus();
  if (blocking()) {
    for (const tab of await api.tabs.query({})) {
      await enforceTab(tab);
    }
  }
}

async function onTabEvent(tab) {
  await refreshStatus();
  await enforceTab(tab);
}

function tick() {
  report();
  enforceAll();
}

function ensureHeartbeat() {
  if (timer === null) {
    timer = setInterval(tick, HEARTBEAT_MS);
  }
  tick();
}

api.tabs.onActivated.addListener(async (info) => {
  report();
  try {
    await onTabEvent(await api.tabs.get(info.tabId));
  } catch (_err) {
    // the tab closed meanwhile
  }
});
api.tabs.onUpdated.addListener((_id, change, tab) => {
  if ("url" in change || "title" in change || "audible" in change) {
    report();
  }
  if ("url" in change || change.status === "loading") {
    onTabEvent(tab);
  }
});
api.tabs.onRemoved.addListener(report);
api.windows.onFocusChanged.addListener(report);
api.runtime.onStartup.addListener(ensureHeartbeat);
api.runtime.onInstalled.addListener(ensureHeartbeat);
api.alarms.onAlarm.addListener(ensureHeartbeat);
api.alarms.create("leisure-watch-heartbeat", { periodInMinutes: 0.5 });
ensureHeartbeat();
