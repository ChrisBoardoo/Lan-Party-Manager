import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getVersion } from "@tauri-apps/api/app";
import { load } from "@tauri-apps/plugin-store";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

// This shell is the permanent top-level page — it never navigates away.
// Once a server URL is confirmed reachable, the real LPM app loads in an
// <iframe>, not via window.location.href. Why: Tauri's IPC bridge
// (window.__TAURI__ / invoke) is only ever granted to a fixed, build-time
// allowlist of origins ("dangerousRemoteDomainIpcAccess") — it can't
// dynamically trust "whatever server URL the user just typed in," which is
// the whole premise of this app. Keeping the shell as the top-level document
// means *it* always has Tauri access, and the embedded LPM app (any origin,
// unknown at build time) talks to it over `postMessage` instead — see
// frontend/src/lib/desktopBridge.ts for the child side of this bridge.
// See desktopplan_windows.md § "Login flow" / M1 notes for the full writeup.

const STORE_FILE = "config.json";
const STORE_KEY = "serverUrl";

const form = document.getElementById("server-form");
const input = document.getElementById("server-url");
const errorEl = document.getElementById("error");
const submitBtn = document.getElementById("submit-btn");
const loadingEl = document.getElementById("loading");
const shellEl = document.querySelector(".shell");
const frameEl = document.getElementById("app-frame");

const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const settingsCloseBtn = document.getElementById("settings-close");
const settingsServerUrlEl = document.getElementById("settings-server-url");
const settingsSwitchServerBtn = document.getElementById("settings-switch-server");
const settingsLaunchMinimized = document.getElementById("settings-launch-minimized");
const settingsAutostart = document.getElementById("settings-autostart");
const settingsLolCapture = document.getElementById("settings-lol-capture");
const settingsLolOutsideLan = document.getElementById("settings-lol-outside-lan");
const settingsVersionEl = document.getElementById("settings-version");
const categoryCheckboxes = Array.from(
  document.querySelectorAll("#settings-panel input[data-category]")
);

let currentServerOrigin = null;

function normalizeUrl(raw) {
  let url = raw.trim();
  if (!url) return null;
  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }
  return url.replace(/\/+$/, "");
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

function showForm() {
  loadingEl.hidden = true;
  form.hidden = false;
  settingsBtn.hidden = true;
  closeSettings();
  input.focus();
}

// Cache-bust: the LPM server's nginx doesn't send Cache-Control on
// index.html (only Last-Modified/ETag), which leaves the browser free to
// serve a stale cached copy via heuristic caching without even a
// revalidation round-trip — self-hosters update their instance over time,
// and the desktop app should always load whatever's actually deployed
// rather than whatever happened to be cached from a previous launch.
function loadApp(url) {
  // The cache-bust query param must land *before* any hash fragment — a
  // naive `url + bust` would otherwise tack `?_t=...` onto the end of a
  // fragment like `#token=...`, silently corrupting it (URLSearchParams
  // doesn't treat `?` specially inside a hash, so it becomes part of the
  // token's value instead of a real query string). Discord sign-in is the
  // one caller that passes a hash — see the `lpm-notification-clicked` and
  // `oauth-auth-complete` listeners below.
  const [base, hash] = url.split("#");
  const bust = (base.includes("?") ? "&" : "?") + "_t=" + Date.now();
  frameEl.src = base + bust + (hash ? "#" + hash : "");
}

function showApp(url) {
  currentServerOrigin = new URL(url).origin;
  shellEl.hidden = true;
  frameEl.hidden = false;
  settingsBtn.hidden = false;
  loadApp(url);
}

async function getStore() {
  return load(STORE_FILE, { autoSave: false });
}

async function init() {
  try {
    const store = await getStore();
    const savedUrl = await store.get(STORE_KEY);
    if (savedUrl) {
      showApp(savedUrl);
      return;
    }
  } catch (err) {
    // No store file yet on first-ever launch, or it failed to read — either
    // way, fall through to asking for a server URL.
    console.warn("Could not read saved server URL:", err);
  }
  showForm();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const url = normalizeUrl(input.value);
  if (!url) {
    showError("Enter your server URL.");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Checking…";

  try {
    // Reachability check runs on the Rust side (see src-tauri/src/main.rs,
    // `check_server`), not via fetch() here — a plain HTTP client isn't
    // subject to the webview's CORS policy, so this works against a stock
    // LPM server with no CORS_ORIGINS changes needed. See desktopplan_windows.md
    // § "Networking detail: call from Rust, not the webview".
    const reachable = await invoke("check_server", { url });
    if (!reachable) {
      showError("Can't reach that server. Check the URL and try again.");
      return;
    }

    const store = await getStore();
    await store.set(STORE_KEY, url);
    await store.save();

    showApp(url);
  } catch (err) {
    console.error("[lpm] submit failed:", err);
    const detail = err && err.message ? err.message : String(err);
    showError(`Error: ${detail}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Continue";
  }
});

// The embedded LPM app posts requests here — see frontend/src/lib/desktopBridge.ts
// for the sending side (`notifyDesktopLogin`/`notifyDesktopLogout`/
// `requestDiscordAuth`/`requestSteamAuth`).
window.addEventListener("message", (event) => {
  if (!currentServerOrigin || event.origin !== currentServerOrigin) return;
  if (event.source !== frameEl.contentWindow) return;

  const data = event.data;
  if (!data || typeof data !== "object") return;

  if (data.type === "lpm-auth-token" && typeof data.token === "string") {
    invoke("set_auth_token", { token: data.token, baseUrl: currentServerOrigin }).catch((err) =>
      console.error("[lpm] set_auth_token failed:", err)
    );
  } else if (data.type === "lpm-auth-logout") {
    invoke("clear_auth_token").catch((err) => console.error("[lpm] clear_auth_token failed:", err));
  } else if (data.type === "lpm-start-discord-auth") {
    // Discord SSO: the embedded app can't complete this itself (refused
    // inside an iframe). Rust opens the system browser and waits on a local
    // loopback listener for the result — see src-tauri/src/main.rs's
    // start_oauth_auth doc comment for why (a native popup window was
    // tried first and never reliably rendered). Rust owns the rest of this
    // flow from here — see the "oauth-auth-complete" listener below.
    invoke("start_oauth_auth", {
      baseUrl: currentServerOrigin,
      provider: "discord",
      kind: data.kind,
      inviteCode: data.inviteCode ?? null,
    }).catch((err) => console.error("[lpm] start_oauth_auth (discord) failed:", err));
  } else if (data.type === "lpm-start-steam-auth") {
    // Steam link — same loopback pattern as Discord, link-only (no
    // login/registration via Steam, see md/Steam_Link.md), so always "link".
    invoke("start_oauth_auth", {
      baseUrl: currentServerOrigin,
      provider: "steam",
      kind: "link",
      inviteCode: null,
    }).catch((err) => console.error("[lpm] start_oauth_auth (steam) failed:", err));
  } else if (data.type === "lpm-open-external" && typeof data.url === "string") {
    // Kiosk/share links: meant for another screen anyway, and `<a
    // target="_blank">` inside the embedded iframe has nothing to open into
    // here — see open_external's doc comment in src-tauri/src/main.rs.
    invoke("open_external", { url: data.url }).catch((err) =>
      console.error("[lpm] open_external failed:", err)
    );
  }
});

// Fired by Rust once the browser's post-sign-in redirect hits the loopback
// listener (Discord or Steam — see start_oauth_auth in src-tauri/src/main.rs).
// `event.payload` is the exact path/fragment/query the backend decided on
// (e.g. `/auth/discord/complete#token=...`, `/profile?discord=linked`, or
// `/profile?steam=linked`) — navigating the main iframe there runs the app's
// own completion page (or just shows the linked-profile page) exactly as it
// would for a normal browser tab.
//
// Resolved as a URL and checked to stay on the server's origin, never pasted
// onto it: `origin + "@evil.example/login"` reads as a URL whose *host* is
// evil.example, which would put a fake LPM login page inside this trusted
// window. Rust already drops callbacks without this attempt's nonce; this is
// the second lock on the same door.
listen("oauth-auth-complete", (event) => {
  if (!currentServerOrigin) return;
  let url;
  try {
    url = new URL(event.payload, currentServerOrigin);
  } catch {
    return;
  }
  if (url.origin !== currentServerOrigin) {
    console.error("[lpm] oauth-auth-complete: refusing a target off the server's origin");
    return;
  }
  loadApp(url.href);
});

// Deep-linking (M2): `/api/activity` rows only carry entity_type/entity_id,
// no parent event id, and most entity types have no per-item page in the
// frontend at all yet (no /gear, no per-media-item page, no per-sponsor
// page) — so this only gets as specific as the nearest real section page.
// Kept here rather than in Rust so the route table can change without
// touching main.rs. See desktopplan_windows.md's M2 notes.
const ROUTE_FOR_ENTITY = {
  tournament: (id) => `/tournaments/${id}/bracket`,
  match: () => "/tournaments",
  media: () => "/media",
  schedule_block: () => "/planning",
  sponsor: () => "/tournaments",
  prize: () => "/prizes",
  live_stream: () => "/streams",
  gear_item: () => "/",
  announcement: () => "/",
  chat_message: () => "/craving-chat",
};

// Fired by Rust (src-tauri/src/main.rs, show_activity_notification) when the
// user clicks a toast rather than dismissing it.
listen("lpm-notification-clicked", (event) => {
  if (!currentServerOrigin) return;
  const { entity_type, entity_id } = event.payload || {};
  const routeFor = ROUTE_FOR_ENTITY[entity_type] || (() => "/");
  loadApp(currentServerOrigin + routeFor(entity_id));
});

// ── Settings panel (M2) ───────────────────────────────────────────────────
//
// Shell-owned UI, not the embedded React app — same reasoning as the
// server-URL form: this is desktop-specific chrome (server switch, tray
// preferences), not something to build into frontend/ and keep in sync.
// Which categories exist lives in the checkboxes' `data-category` attributes
// in index.html, not duplicated here.

function closeSettings() {
  settingsPanel.hidden = true;
}

// __LPM_BUILD_SHA__ is injected by vite.config.js's `define` from the
// LPM_BUILD_SHA env var set by the GitHub Actions release workflow (short
// commit SHA) — see md/desktop_app_CI_github.md. Falls back to "dev" for
// local `tauri dev`/`tauri build` runs where that env var isn't set, so the
// footer never shows a literal unreplaced token.
const BUILD_SHA = typeof __LPM_BUILD_SHA__ !== "undefined" ? __LPM_BUILD_SHA__ : "dev";

let versionLabel = null;

async function getVersionLabel() {
  if (versionLabel) return versionLabel;
  try {
    const appVersion = await getVersion();
    versionLabel = `LAN Party Manager Desktop v${appVersion} (${BUILD_SHA})`;
  } catch (err) {
    console.error("[lpm] getVersion failed:", err);
    versionLabel = `LAN Party Manager Desktop (${BUILD_SHA})`;
  }
  return versionLabel;
}

async function openSettings() {
  settingsServerUrlEl.textContent = currentServerOrigin || "";
  settingsVersionEl.textContent = await getVersionLabel();

  const store = await getStore();
  settingsLaunchMinimized.checked = (await store.get("launchMinimized")) === true;

  const categories = (await store.get("notifyCategories")) || {};
  for (const checkbox of categoryCheckboxes) {
    checkbox.checked = categories[checkbox.dataset.category] !== false;
  }

  // Read by Rust's LoL capture loop (src-tauri/src/lol.rs) on every turn —
  // missing means on, like the notification categories.
  settingsLolCapture.checked = (await store.get("lolCapture")) !== false;
  settingsLolOutsideLan.checked = (await store.get("lolCaptureOutsideLan")) !== false;
  settingsLolOutsideLan.disabled = !settingsLolCapture.checked;

  try {
    settingsAutostart.checked = await invoke("get_autostart_enabled");
  } catch (err) {
    console.error("[lpm] get_autostart_enabled failed:", err);
  }

  settingsPanel.hidden = false;
}

settingsBtn.addEventListener("click", openSettings);
settingsCloseBtn.addEventListener("click", closeSettings);

settingsSwitchServerBtn.addEventListener("click", () => {
  closeSettings();
  window.__lpmSwitchServer();
});

settingsLaunchMinimized.addEventListener("change", async () => {
  const store = await getStore();
  await store.set("launchMinimized", settingsLaunchMinimized.checked);
  await store.save();
});

settingsAutostart.addEventListener("change", async () => {
  const enabled = settingsAutostart.checked;
  try {
    await invoke("set_autostart_enabled", { enabled });
  } catch (err) {
    console.error("[lpm] set_autostart_enabled failed:", err);
    settingsAutostart.checked = !enabled;
  }
});

settingsLolCapture.addEventListener("change", async () => {
  // "Outside a LAN" only means something while sending is on at all.
  settingsLolOutsideLan.disabled = !settingsLolCapture.checked;
  const store = await getStore();
  await store.set("lolCapture", settingsLolCapture.checked);
  await store.save();
});

settingsLolOutsideLan.addEventListener("change", async () => {
  const store = await getStore();
  await store.set("lolCaptureOutsideLan", settingsLolOutsideLan.checked);
  await store.save();
});

for (const checkbox of categoryCheckboxes) {
  checkbox.addEventListener("change", async () => {
    const store = await getStore();
    const categories = (await store.get("notifyCategories")) || {};
    categories[checkbox.dataset.category] = checkbox.checked;
    await store.set("notifyCategories", categories);
    await store.save();
  });
}

// Fired by Rust's tray menu ("Settings…" / "Switch Server…" items) — the
// tray has no DOM of its own, so it asks the shell to do this instead.
listen("lpm-open-settings", () => openSettings());
listen("lpm-switch-server", () => {
  closeSettings();
  window.__lpmSwitchServer();
});

init();

// M3: once per launch (same cadence as AuthContext's own sliding-session
// refresh) — checks the manifest at the endpoint configured in
// tauri.conf.json's plugins.updater.endpoints (lanpartymanager.com's
// `latest.json`, written by scripts/desktop_website_release.py — the repo's
// GitHub releases are private, so apps up to 1.3.1 could never reach
// theirs). Deliberately just a `confirm()` for v1, not a styled
// dialog — this is the shell's own chrome, not something worth building out
// until there's an actual update to react to.
async function checkForUpdates() {
  try {
    const update = await check();
    if (!update) return;
    const install = window.confirm(
      `Lan Party Manager ${update.version} is available (you're on ${update.currentVersion}). Install and restart now?`
    );
    if (!install) return;
    await update.downloadAndInstall();
    await relaunch();
  } catch (err) {
    console.error("[lpm] update check failed:", err);
  }
}
checkForUpdates();

// Exposed for the settings panel's "Switch server" button and the tray
// menu's "Switch Server…" item: clears the saved URL and the embedded app
// so init() falls back to the form again.
window.__lpmSwitchServer = async () => {
  const store = await getStore();
  await store.delete(STORE_KEY);
  await store.save();
  await invoke("clear_auth_token").catch(() => {});
  frameEl.hidden = true;
  frameEl.src = "about:blank";
  currentServerOrigin = null;
  showForm();
};
