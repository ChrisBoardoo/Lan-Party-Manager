// Optional bridge to the LPM Desktop shell (desktopapp/), a no-op everywhere
// else. The desktop app embeds this exact frontend unmodified, inside an
// <iframe> owned by its own Tauri shell (see desktopapp/ui/src/main.js) —
// this app never knows or cares whether it's embedded, it just always posts
// messages to `window.parent`.
//
// Why postMessage and not a direct Tauri call: Tauri's IPC bridge is only
// ever granted to a fixed, build-time allowlist of origins, which can't
// include "whatever server URL the user typed in" — so this app never has
// direct Tauri access, embedded or not. postMessage works regardless, and
// pinning the target origin means a page that isn't really the desktop shell
// simply never receives the message — the browser only delivers postMessage
// when the destination window's actual origin matches targetOrigin exactly.
// See desktopapp/desktopplan_windows.md's M1 notes for the full writeup.
//
// In a normal browser tab (or when this app IS the top-level page, e.g. the
// Docker-served web app), `window.parent === window` — posting to yourself
// is a harmless no-op since nothing here listens for it.

// A *fixed allowlist*, not a wildcard — postMessage only ever delivers when
// the destination window's real origin matches one of these exactly, so
// listing more candidates doesn't loosen security, it just covers more of
// "what the real shell's origin legitimately is depending on how it's
// running." Two entries: the production origin (Tauri's internal asset
// protocol on Windows WebView2), and the `cargo tauri dev` origin (Tauri's
// `devUrl` config points the shell at Vite's own dev server instead of the
// internal protocol while developing it — see desktopapp/vite.config.js).
// TODO(Linux, desktopapp/v2_plan.md M2+): tauri://localhost in production.
const SHELL_ORIGINS = ['http://tauri.localhost', 'http://localhost:1420']

function postToShell(message: unknown) {
  for (const origin of SHELL_ORIGINS) {
    window.parent.postMessage(message, origin)
  }
}

export function notifyDesktopLogin(token: string) {
  postToShell({ type: 'lpm-auth-token', token })
}

export function notifyDesktopLogout() {
  postToShell({ type: 'lpm-auth-logout' })
}

/** True when this page is running inside the desktop app's embedded iframe. */
export function isEmbeddedInDesktop() {
  return window.top !== window.self
}

/** F5, Ctrl+F5, Shift+F5, Ctrl+R, Ctrl+Shift+R — every "reload" the WebView answers to. */
export function isReloadShortcut(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey'>) {
  if (e.altKey) return false
  if (e.key === 'F5') return true
  return (e.ctrlKey || e.metaKey) && (e.key === 'r' || e.key === 'R')
}

/**
 * Make a reload inside the desktop app reload *this page*, where the member
 * is, instead of the whole window.
 *
 * Left alone, WebView2 applies F5/Ctrl+R to the top-level document — the
 * shell — whose `init()` then loads the server's root URL, so every refresh
 * landed back on the Hub. The shell can't restore the route itself: this app
 * is another origin, so it never sees in-app (pushState) navigation, only the
 * `src` it last set. Catching the key here instead works with shells already
 * installed — no new MSI needed. With focus on the shell's own chrome (its
 * settings panel), the old full-window reload still happens.
 */
export function installDesktopReloadShortcut() {
  if (!isEmbeddedInDesktop()) return
  window.addEventListener('keydown', (e) => {
    if (!isReloadShortcut(e)) return
    e.preventDefault()
    window.location.reload()
  })
}

/**
 * Start a Discord OAuth round-trip (`kind: 'login'` from the Login/Register
 * pages, `'link'` from Profile) when embedded in the desktop app. Discord —
 * like virtually every OAuth provider — refuses to render inside *any*
 * iframe as an anti-clickjacking measure, so this app can't just navigate
 * itself there; only call this when `isEmbeddedInDesktop()` is true (the
 * caller is responsible for falling back to the normal
 * `window.location.href = await discordApi.authorize(...)` redirect
 * otherwise, exactly like a plain browser tab).
 *
 * The shell (`ui/src/main.js`) forwards this to Rust's `start_discord_auth`,
 * which calls the backend itself (this app never fetches the authorize URL
 * for the desktop case), opens the system's default browser for the actual
 * OAuth flow, and waits on a local loopback listener for the result — a
 * native popup window was tried first and never reliably rendered (see
 * `start_discord_auth`'s doc comment in desktopapp/src-tauri/src/main.rs).
 * Once Discord redirects back, Rust reloads this iframe to wherever the
 * backend decided (e.g. back here at `/auth/discord/complete#token=...` for
 * login, or `/profile?discord=linked` for linking) — nothing further needed
 * from this page either way.
 */
export function requestDiscordAuth(kind: 'login' | 'link', inviteCode?: string) {
  postToShell({ type: 'lpm-start-discord-auth', kind, inviteCode: inviteCode ?? null })
}

/**
 * Same idea as `requestDiscordAuth`, for Steam — link-only (see
 * md/2.features/Steam_Link.md), so there's no `kind`/`inviteCode` to pass. The shell
 * forwards this to Rust's `start_steam_auth`, which opens the system browser
 * at Steam's OpenID login page and waits on the same loopback-listener
 * pattern as Discord.
 */
export function requestSteamAuth() {
  postToShell({ type: 'lpm-start-steam-auth' })
}

/**
 * Open a URL in the system's default browser via the shell (Rust's
 * `open_external`), for links meant to be viewed elsewhere — the kiosk/
 * big-screen link, a public share link — or just links that need a working
 * "open" button at all. `<a target="_blank">` has no working new-window
 * target inside the desktop app's embedded iframe (Tauri doesn't spawn a
 * native window for it), so callers should check `isEmbeddedInDesktop()`
 * first and fall back to a normal `window.open(url, '_blank')` otherwise,
 * exactly like `requestDiscordAuth`'s caller convention.
 */
export function requestOpenExternal(url: string) {
  postToShell({ type: 'lpm-open-external', url })
}
