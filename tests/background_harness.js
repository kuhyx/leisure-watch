// Runs the built extension script (allow.js + background.js) in node against
// a fake browser API, for tests/test_background_js.py.
//
// stdin: {"stored": <status|null>, "status": <doc|null>, "tabs": [{id, url}],
//         "wait_ms": n}. "status" null = the daemon is unreachable.
// stdout: {"updates": [[tabId, url]], "reports": [body], "saved": [obj]}.
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const ext = path.join(__dirname, "..", "extension");
const source = ["allow.js", "background.js"]
  .map((name) => fs.readFileSync(path.join(ext, name), "utf8"))
  .join("")
  .replace(/__BROWSER__/g, "helium")
  .replace(/__PORT__/g, "1");

const out = { updates: [], reports: [], saved: [] };
const noop = { addListener() {} };
const tabs = input.tabs;

globalThis.chrome = {
  windows: {
    getLastFocused: async () => ({ id: 1, focused: true, incognito: false }),
    onFocusChanged: noop,
  },
  tabs: {
    query: async (q) => (q.audible ? [] : q.active ? tabs.slice(0, 1) : tabs),
    update: async (id, change) => {
      out.updates.push([id, change.url]);
    },
    remove: async () => {},
    get: async (id) => tabs.find((t) => t.id === id),
    onActivated: noop,
    onUpdated: noop,
    onRemoved: noop,
  },
  runtime: {
    getURL: (p) => `chrome-extension://self/${p}`,
    getManifest: () => ({ version: "9.9.9" }),
    onStartup: noop,
    onInstalled: noop,
  },
  alarms: { create() {}, onAlarm: noop },
  storage: {
    local: {
      get: async (key) => (input.stored ? { [key]: input.stored } : {}),
      set: async (obj) => {
        out.saved.push(obj);
      },
    },
  },
};

globalThis.fetch = async (url, opts) => {
  if (url.endsWith("/report")) {
    out.reports.push(JSON.parse(opts.body));
    return { ok: true };
  }
  if (input.status === null) {
    throw new TypeError("connection refused");
  }
  return { ok: true, json: async () => input.status };
};

vm.runInThisContext(source);
setTimeout(() => {
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
}, input.wait_ms ?? 200);
