// Prevents an extra console window from popping up alongside the app window
// on Windows release builds. Debug builds keep the console so `cargo tauri
// dev` output stays visible.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod lol;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use notify_rust::{Notification as OsNotification, NotificationResponse};
use serde::{Deserialize, Serialize};
use tauri::{
    menu::MenuBuilder,
    tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WindowEvent,
};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_store::StoreExt;

/// `reqwest`'s default User-Agent (`reqwest/x.y.z`) reads as a generic
/// scripted-HTTP-client signature to some reverse proxies/WAFs/CDNs —
/// confirmed live that a self-hosted instance's `/api/activity` poll got a
/// bare 403 from every Rust-side request while the exact same endpoint
/// worked fine from the embedded webview (a real browser engine). FastAPI's
/// own auth dependency (`get_current_user`/`HTTPBearer`) can't produce a 403
/// for a missing/invalid token — only a 401 (see `backend/auth.py`) — so a
/// 403 specifically means something in front of the app (not the app
/// itself) is rejecting the request before it ever gets there, most likely
/// on User-Agent. Every outgoing request in this file goes through this
/// UA so it doesn't stand out from a normal browser.
const USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0";

/// Reachability check for the "enter your server URL" screen (index.html /
/// src/main.js). Deliberately implemented here, not as a `fetch()` call from
/// the webview: a native HTTP client isn't subject to the browser CORS
/// policy the webview would be, so this works against a stock LPM server —
/// no `CORS_ORIGINS` env var change required on the user's instance. See
/// desktopplan_windows.md § "Networking detail: call from Rust, not the webview".
///
/// Hits the existing, unauthenticated `GET /api/auth/invite-required` route
/// (backend/router_auth.py) purely as a "does something LPM-shaped answer at
/// this URL" probe — the response body isn't inspected, only that it came
/// back successfully.
/// Opens a URL in the user's system default browser. Used for things like the
/// kiosk/big-screen link and the "my setup" share link: both are meant to be
/// viewed on a *different* screen/device (a projector, a phone), and even for
/// same-machine viewing, `<a target="_blank">` inside the embedded app's
/// iframe has no working new-window target here — Tauri doesn't spawn a
/// native window for it, so the click was previously a silent no-op. Routed
/// through Rust (like Discord's OAuth `open::that` call above) rather than
/// `window.open()` in the webview for the same reason: consistent, working
/// behavior regardless of which webview/origin the click originated in.
#[tauri::command]
fn open_external(url: String) -> Result<(), String> {
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("Only http/https URLs can be opened".into());
    }
    open::that(&url).map_err(|e| e.to_string())
}

#[tauri::command]
async fn check_server(url: String) -> Result<bool, String> {
    let probe_url = format!("{}/api/auth/invite-required", url.trim_end_matches('/'));

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(8))
        .user_agent(USER_AGENT)
        .build()
        .map_err(|e| e.to_string())?;

    match client.get(&probe_url).send().await {
        Ok(response) => Ok(response.status().is_success()),
        Err(_) => Ok(false),
    }
}

// ── Tray icon, minimize-to-tray, unseen-activity indicator (M2) ──────────
//
// The window declared in tauri.conf.json is left as a normal window; the
// tray/close-to-hide behavior is all wired up here in `.setup()` instead
// (see `setup_tray_and_window`). Both the tray icon and an in-memory unseen
// counter are stashed in Tauri's managed state so the poll loop (which fires
// notifications) and the window's own event handlers (which clear the
// counter on focus) can both reach them without threading extra channels
// through `PollState`.
const CONFIG_STORE: &str = "config.json";

struct UnseenCount(Mutex<u32>);

/// Shows, un-minimizes and focuses the main window, and clears the
/// unseen-activity indicator — the single "bring the app to the front"
/// action used by the tray's left-click, the tray menu's "Open" item, and a
/// clicked notification.
fn show_and_focus(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    reset_unseen(app);
}

fn reset_unseen(app: &AppHandle) {
    if let Some(unseen) = app.try_state::<UnseenCount>() {
        *unseen.0.lock().unwrap() = 0;
    }
    if let Some(tray) = app.try_state::<TrayIcon>() {
        let _ = tray.set_tooltip(Some("Lan Party Manager"));
    }
}

/// Bumps the unseen-activity counter and reflects it in the tray tooltip —
/// there's no icon-overlay/badge asset, so the tooltip text ("N new") is the
/// indicator. Only counts while the main window is genuinely not focused;
/// `reset_unseen` (wired to the window's `Focused(true)` event) clears it.
fn bump_unseen(app: &AppHandle) {
    let focused = app
        .get_webview_window("main")
        .and_then(|w| w.is_focused().ok())
        .unwrap_or(false);
    if focused {
        return;
    }
    let Some(unseen) = app.try_state::<UnseenCount>() else { return };
    let mut count = unseen.0.lock().unwrap();
    *count += 1;
    if let Some(tray) = app.try_state::<TrayIcon>() {
        let _ = tray.set_tooltip(Some(format!("Lan Party Manager — {} new", *count)));
    }
}

fn launch_minimized(app: &AppHandle) -> bool {
    app.store(CONFIG_STORE)
        .ok()
        .and_then(|store| store.get("launchMinimized"))
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
}

/// Builds the tray icon + context menu and wires up the main window's
/// close-to-tray behavior. Called once from `.setup()`.
fn setup_tray_and_window(app: &tauri::App) -> tauri::Result<()> {
    app.manage(UnseenCount(Mutex::new(0)));

    let window = app
        .get_webview_window("main")
        .expect("the \"main\" window is declared in tauri.conf.json");

    // Minimize-to-tray, Slack-style: closing the window just hides it. Only
    // the tray menu's "Quit" (below) actually exits the process.
    let hide_target = window.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            let _ = hide_target.hide();
        }
        WindowEvent::Focused(true) => {
            reset_unseen(&hide_target.app_handle());
        }
        _ => {}
    });

    let menu = MenuBuilder::new(app)
        .text("open", "Open Lan Party Manager")
        .separator()
        .text("settings", "Settings…")
        .text("switch-server", "Switch Server…")
        .separator()
        .text("quit", "Quit")
        .build()?;

    let icon = app
        .default_window_icon()
        .expect("bundle.icon is configured in tauri.conf.json")
        .clone();

    let tray = TrayIconBuilder::new()
        .icon(icon)
        .tooltip("Lan Party Manager")
        .menu(&menu)
        // Left-click restores the window (Slack/Discord/Teams convention);
        // right-click still shows the menu built above regardless of this
        // setting. Unsupported on Linux — see `on_tray_icon_event` below.
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show_and_focus(app),
            "settings" => {
                show_and_focus(app);
                let _ = app.emit("lpm-open-settings", ());
            }
            "switch-server" => {
                show_and_focus(app);
                let _ = app.emit("lpm-switch-server", ());
            }
            "quit" => app.exit(0),
            _ => {}
        })
        // Platform-specific: `TrayIconEvent` is never emitted on Linux (the
        // icon still shows and right-click still opens the menu built above,
        // but there is no way to distinguish a left-click there — see
        // desktopapp/v2_plan.md for the Linux tracking item). Windows-only
        // for now, which matches this plan's Windows-first scope.
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_and_focus(tray.app_handle());
            }
        })
        .build(app)?;
    app.manage(tray);

    if launch_minimized(&app.handle().clone()) {
        let _ = window.hide();
    }

    Ok(())
}

// ── Notification polling (M1, extended in M2 with click deep-linking) ────
//
// The embedded LPM app (any origin, unknown at build time) can't hold direct
// Tauri IPC access, so it posts its auth token to the shell via
// `postMessage`, which forwards it here via `set_auth_token` — see
// ui/src/main.js and frontend/src/lib/desktopBridge.ts for the two ends of
// that bridge, and desktopplan_windows.md's M1 notes for why.
//
// `generation` is a poor-man's cancellation token: every call to
// `set_auth_token`/`clear_auth_token` bumps it, and the currently-running
// poll loop (if any) checks it after every sleep tick and exits the moment
// it no longer matches the generation it was spawned with. This avoids
// pulling in a cancellation-token crate for what's otherwise a single
// background loop.
struct PollState {
    generation: Arc<Mutex<u64>>,
    // The current session's JWT, mirrored here from `set_auth_token` so
    // commands other than the poll loop (namely `start_oauth_auth`'s
    // "link" flow, which calls an authenticated backend endpoint) have
    // something to attach as a Bearer token. The embedded webview never has
    // direct Tauri IPC access (see the module-level doc comment), so this is
    // the only place in the desktop app that ever sees the token outside of
    // `poll_activity`'s own copy.
    auth_token: Arc<Mutex<Option<String>>>,
}

#[derive(Deserialize)]
struct ActivityUser {
    username: String,
}

#[derive(Deserialize)]
struct ActivityItem {
    id: i64,
    action: String,
    description: String,
    entity_type: Option<String>,
    entity_id: Option<i64>,
    user: ActivityUser,
}

/// The payload for the `lpm-notification-clicked` event — the shell
/// (ui/src/main.js) turns this into a route via its own entity-type table
/// and navigates the embedded iframe there. Deliberately just the raw
/// entity_type/entity_id: `/api/activity` rows don't carry a parent event id
/// or enough context for anything finer than section-level routing (see
/// desktopplan_windows.md's M2 notes), and keeping the actual route table in
/// JS means it can change without touching Rust.
#[derive(Serialize, Clone)]
struct DeepLinkPayload {
    entity_type: Option<String>,
    entity_id: Option<i64>,
}

/// The doc's 5 notification categories, mapped from the `action` strings
/// already logged by the backend (see backend/activity.py callers).
/// `sponsor_added`/`prize_added`/`stream_added` postdate this list (added
/// while closing M1's activity-logging gaps) and have no toggle yet — they
/// return `None` here, which `category_enabled` treats as "always notify."
fn category_for_action(action: &str) -> Option<&'static str> {
    match action {
        "tournament_created" | "match_completed" | "score_reported" => Some("tournaments"),
        "media_upload" => Some("media"),
        "block_proposed" | "block_locked" => Some("planning"),
        "gear_pledged" | "gear_carryover" | "gear_claimed" => Some("gear"),
        "announcement_posted" => Some("announcements"),
        _ => None,
    }
}

/// Reads `notifyCategories` (a `{tournaments, media, planning, gear,
/// announcements: bool}` object written by the settings panel in
/// ui/src/main.js) from the same store the server URL lives in. Missing
/// keys — including a missing `action` category — default to `true`
/// (opt-out, not opt-in), so a crew that never opens Settings keeps getting
/// every notification.
fn category_enabled(app: &AppHandle, action: &str) -> bool {
    let Some(category) = category_for_action(action) else {
        return true;
    };
    app.store(CONFIG_STORE)
        .ok()
        .and_then(|store| store.get("notifyCategories"))
        .and_then(|prefs| prefs.get(category).and_then(|v| v.as_bool()))
        .unwrap_or(true)
}

const POLL_INTERVAL: Duration = Duration::from_secs(30);

/// Bumps `generation` and spawns a fresh poll loop under it — the one place
/// that actually starts polling, called from `set_auth_token` whenever the
/// main iframe reports a login (normal password login or Discord SSO, both
/// forwarded through the same postMessage bridge — see `start_oauth_auth`'s
/// doc comment for why Discord's completion also lands here rather than
/// calling this directly).
///
/// Also starts the League of Legends capture loop (lol.rs) under the same
/// generation, so a logout or token change stops both together.
fn start_polling(app: tauri::AppHandle, token: String, base_url: String, generation: Arc<Mutex<u64>>) {
    let my_generation = {
        let mut g = generation.lock().unwrap();
        *g += 1;
        *g
    };
    tauri::async_runtime::spawn(lol::watch(
        app.clone(),
        token.clone(),
        base_url.clone(),
        my_generation,
        generation.clone(),
    ));
    tauri::async_runtime::spawn(poll_activity(app, token, base_url, my_generation, generation));
}

#[tauri::command]
async fn set_auth_token(
    token: String,
    base_url: String,
    app: tauri::AppHandle,
    state: tauri::State<'_, PollState>,
) -> Result<(), String> {
    eprintln!("[lpm] set_auth_token: base_url={base_url} token_len={}", token.len());
    *state.auth_token.lock().unwrap() = Some(token.clone());
    start_polling(app, token, base_url, state.generation.clone());
    Ok(())
}

#[tauri::command]
fn clear_auth_token(state: tauri::State<'_, PollState>) {
    // Bumping the generation is enough — the running loop (if any) sees the
    // mismatch on its next tick and exits. Nothing else to tear down.
    let mut g = state.generation.lock().unwrap();
    *g += 1;
    *state.auth_token.lock().unwrap() = None;
    eprintln!("[lpm] clear_auth_token (generation now {g})");
}

// ── Start-on-boot (M2) ────────────────────────────────────────────────────
//
// Plain app commands, not routed through the autostart plugin's own JS
// bindings — same reasoning as check_server/set_auth_token above: the
// settings panel (ui/src/main.js) just calls `invoke()`, no capability entry
// needed since these are app-defined commands, not plugin-provided ones.
#[tauri::command]
fn get_autostart_enabled(app: tauri::AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
fn set_autostart_enabled(enabled: bool, app: tauri::AppHandle) -> Result<(), String> {
    let manager = app.autolaunch();
    let result = if enabled { manager.enable() } else { manager.disable() };
    result.map_err(|e| e.to_string())
}

// ── OAuth/OpenID linking (system browser + loopback listener) ────────────
//
// Discord refuses to render inside the main window's <iframe> at all
// (anti-clickjacking), and five rounds of trying to work around that with a
// native `WebviewWindowBuilder` popup each fixed a real bug (a synchronous-
// command deadlock, a stale-window-handle race, a genuine double-invocation
// from one click) without ever getting the popup to actually render —
// confirmed live that a built popup produced *zero* further Tauri-level
// events afterward (no navigation, no close, no focus change), pointing at
// a failure below where Tauri's Rust bindings can observe anything at all.
//
// This opens the sign-in URL in the user's default system browser instead —
// the RFC 8252-recommended pattern for native-app OAuth generally, not just
// a workaround here — and gets the result back via a one-shot local HTTP
// listener on `127.0.0.1`, the standard "loopback redirect" approach for
// exactly this case. `backend/router_auth.py`'s `discord_authorize` /
// `discord_link` / `discord_callback` (and Steam's `steam_link` /
// `steam_callback` — see md/2.features/Steam_Link.md, link-only, no `steam_authorize`)
// all accept an optional `desktop_port` that threads through the existing
// signed state; when present, the callback redirects the browser straight to
// our loopback listener (`_complete_redirect` in router_auth.py) instead of
// the normal frontend URL. Each attempt owns its own independent socket, so
// there's no shared window/label state to race over between attempts at all.
//
// `start_oauth_auth` was originally `start_discord_auth`, hardcoded to
// Discord's endpoints; generalized to take a `provider` ("discord" | "steam")
// when Steam linking was added, since the loopback-listener mechanics are
// identical between the two and duplicating a function this size (and this
// easy to get subtly wrong — the deadlock/race/double-invocation bugs above
// were all found the hard way) risked the same bugs needing to be re-found
// twice. Steam only ever calls this with `kind: "link"` (there's no
// `steam_authorize`/login-via-Steam endpoint), so `endpoint` still resolves
// the same way for both providers.
//
// The `target` this hands to the shell (a path/fragment straight from the
// backend, e.g. `/auth/discord/complete#token=...` or
// `/profile?discord=linked`/`/profile?steam=linked`) gets forwarded to the
// **main iframe**, not a popup — reusing the fix from the popup era: the
// actual login page needs to run in the main iframe, since that's the only
// context that can reach the shell via postMessage and has the frontend's
// own localStorage/AuthContext.
#[tauri::command]
async fn start_oauth_auth(
    base_url: String,
    provider: String,
    kind: String,
    invite_code: Option<String>,
    app: tauri::AppHandle,
    state: tauri::State<'_, PollState>,
) -> Result<(), String> {
    let endpoint = match kind.as_str() {
        "link" => "link",
        _ => "authorize",
    };

    // The "link" flow attaches the provider account to the *currently
    // signed-in* user (`backend/router_auth.py`'s `discord_link`/`steam_link`
    // are both behind `get_current_user`), unlike Discord's "login"/
    // "authorize" which is anonymous. This Rust-side request needs the
    // session JWT as a Bearer token for that reason — without it, the link
    // endpoint 401s and the click silently does nothing (no error surfaces
    // past this function's own `eprintln!`/the JS `.catch()` in
    // ui/src/main.js), which looks identical to a dead button. Checked before
    // binding the loopback listener below since there's no OAuth flow to
    // receive a callback for if this is going to fail anyway.
    let auth_token = state.auth_token.lock().unwrap().clone();
    if endpoint == "link" && auth_token.is_none() {
        return Err("Not signed in".into());
    }

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    eprintln!("[lpm] start_oauth_auth: provider={provider} kind={kind} loopback port={port}");

    // A fresh secret per attempt: the server signs it into the OAuth state and
    // hands it back on the callback — see wait_for_oauth_callback.
    let nonce = new_nonce()?;
    let mut query: Vec<(&str, String)> = vec![
        ("desktop_port", port.to_string()),
        ("desktop_nonce", nonce.clone()),
    ];
    if let Some(code) = &invite_code {
        query.push(("code", code.clone()));
    }

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .user_agent(USER_AGENT)
        .build()
        .map_err(|e| e.to_string())?;
    let authorize_endpoint = format!(
        "{}/api/auth/{provider}/{endpoint}",
        base_url.trim_end_matches('/')
    );
    let mut req = client.get(&authorize_endpoint).query(&query);
    if let Some(token) = &auth_token {
        req = req.bearer_auth(token);
    }
    let resp = req.send().await.map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        let status = resp.status();
        eprintln!("[lpm] start_oauth_auth: {authorize_endpoint} -> {status}");
        return Err(format!("{provider} authorize request failed ({status})"));
    }

    #[derive(Deserialize)]
    struct AuthorizeResponse {
        authorize_url: String,
    }
    let body: AuthorizeResponse = resp.json().await.map_err(|e| e.to_string())?;

    if !is_expected_authorize_url(&provider, &body.authorize_url) {
        eprintln!("[lpm] start_oauth_auth: refusing unexpected {provider} authorize URL");
        return Err(format!("{provider} returned an unexpected sign-in URL"));
    }

    eprintln!("[lpm] start_oauth_auth: opening system browser");
    open::that(&body.authorize_url).map_err(|e| e.to_string())?;

    tauri::async_runtime::spawn(async move {
        match tokio::time::timeout(Duration::from_secs(300), wait_for_oauth_callback(listener, nonce)).await {
            Ok(Ok(Some(target))) => {
                eprintln!("[lpm] start_oauth_auth: got callback, forwarding to shell");
                show_and_focus(&app);
                let _ = app.emit("oauth-auth-complete", target);
            }
            Ok(Ok(None)) => eprintln!("[lpm] start_oauth_auth: callback had no target in its query string"),
            Ok(Err(e)) => eprintln!("[lpm] start_oauth_auth: loopback error: {e}"),
            Err(_) => eprintln!("[lpm] start_oauth_auth: timed out waiting for the browser sign-in"),
        }
    });

    Ok(())
}

/// The authorize URL comes from the LPM server, and `open::that` hands it to
/// the Windows shell as-is. A compromised or spoofed server (on a LAN, the
/// attacker is on the same network) answering `\\10.0.0.66\s\x.exe` would
/// make Windows open an SMB share, leaking the player's NTLM hash with no
/// click, then offer to run the file. So only the provider's own sign-in page
/// is ever opened — see `oauth_discord.AUTHORIZE_URL` and
/// `oauth_steam.STEAM_OPENID_URL` in the backend.
///
/// A fixed scheme + host + path prefix is as strict as parsing the URL and
/// checking its host: the `/` right after the host rules out
/// `discord.com.evil.net` and `discord.com@evil.net`. Same trade-off as
/// `urlencoding_decode` below — no URL crate for one check.
fn is_expected_authorize_url(provider: &str, url: &str) -> bool {
    let prefix = match provider {
        "discord" => "https://discord.com/oauth2/authorize?",
        "steam" => "https://steamcommunity.com/openid/login?",
        _ => return false,
    };
    url.starts_with(prefix) && !url.chars().any(|c| c.is_whitespace() || c.is_control())
}

/// 32 bytes from the OS RNG, hex-encoded (64 chars) — the shape the backend's
/// `DESKTOP_NONCE_PATTERN` (router_auth.py) accepts.
fn new_nonce() -> Result<String, String> {
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).map_err(|e| e.to_string())?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

/// Waits on the loopback listener for the browser hitting
/// `http://127.0.0.1:{port}/callback?target=...&nonce=...` after
/// `backend/router_auth.py`'s `_complete_redirect`, and returns `target`.
///
/// Only a request carrying this attempt's `nonce` counts. The listener is
/// open to every program on the machine for up to 5 minutes, and it used to
/// take the first connection that arrived: any local process could hand the
/// shell a `target` of its choosing, such as a sign-in token for its own
/// account — the player then ends up signed in as someone else without
/// noticing. Anything else gets a 403 and the wait goes on. A connection that
/// sends nothing is dropped after a few seconds so it can't hold the listener;
/// the 5-minute timeout in `start_oauth_auth` bounds the whole wait.
/// Provider-agnostic — Discord and Steam both funnel through the same
/// `_complete_redirect` shape on the backend.
async fn wait_for_oauth_callback(
    listener: tokio::net::TcpListener,
    nonce: String,
) -> std::io::Result<Option<String>> {
    use tokio::io::AsyncReadExt;

    loop {
        let (mut stream, _) = listener.accept().await?;
        let mut buf = [0u8; 4096];
        let n = match tokio::time::timeout(Duration::from_secs(5), stream.read(&mut buf)).await {
            Ok(Ok(n)) => n,
            _ => continue,
        };
        let (target, got_nonce) = parse_callback_request(&String::from_utf8_lossy(&buf[..n]));

        if !got_nonce.as_deref().is_some_and(|got| nonce_matches(got, &nonce)) {
            eprintln!(
                "[lpm] start_oauth_auth: ignored a loopback request without this attempt's nonce{}",
                if got_nonce.is_none() { " (none at all — server older than 1.3.2?)" } else { "" }
            );
            respond_html(
                &mut stream,
                "403 Forbidden",
                "This sign-in link isn't for this app. Go back to LAN Party Manager and try again.",
            )
            .await;
            continue;
        }

        respond_html(
            &mut stream,
            "200 OK",
            "Signed in \u{2014} you can close this tab and return to LAN Party Manager.",
        )
        .await;
        return Ok(target);
    }
}

/// `(target, nonce)` off the request line of a loopback callback
/// (`GET /callback?target=...&nonce=... HTTP/1.1`), percent-decoded.
fn parse_callback_request(request: &str) -> (Option<String>, Option<String>) {
    let query = request
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|path_and_query| path_and_query.split_once('?'))
        .map(|(_, query)| query)
        .unwrap_or("");
    let param = |name: &str| {
        query
            .split('&')
            .find_map(|kv| kv.strip_prefix(name)?.strip_prefix('='))
            .map(urlencoding_decode)
    };
    (param("target"), param("nonce"))
}

/// Compares every byte whatever the first mismatch, so response timing
/// doesn't reveal how much of a guessed nonce was right.
fn nonce_matches(got: &str, expected: &str) -> bool {
    !expected.is_empty()
        && got.len() == expected.len()
        && got.bytes().zip(expected.bytes()).fold(0u8, |acc, (a, b)| acc | (a ^ b)) == 0
}

async fn respond_html(stream: &mut tokio::net::TcpStream, status: &str, message: &str) {
    use tokio::io::AsyncWriteExt;

    let body = format!(
        "<html><body style=\"font-family:sans-serif;text-align:center;padding-top:4rem\">{message}</body></html>"
    );
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes()).await;
    let _ = stream.shutdown().await;
}

/// Minimal percent-decoding for the two query values we need — avoids pulling
/// in a full URL-parsing crate just to decode `%23`/`%3D` etc. out of the
/// `target` and `nonce` query params.
fn urlencoding_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'%' => {
                // `.get()`, not indexing: bytes[i+1..i+3] could land on a
                // UTF-8 character boundary that isn't valid to slice at if
                // the input isn't well-formed percent-encoding.
                let hex = s.get(i + 1..i + 3).and_then(|h| u8::from_str_radix(h, 16).ok());
                match hex {
                    Some(byte) => {
                        out.push(byte);
                        i += 3;
                    }
                    None => {
                        out.push(bytes[i]);
                        i += 1;
                    }
                }
            }
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            b => {
                out.push(b);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn still_current(generation: &Mutex<u64>, my_generation: u64) -> bool {
    *generation.lock().unwrap() == my_generation
}

/// Shows a native OS toast for one activity item and, if the user clicks it
/// (as opposed to it timing out/being dismissed), brings the window to the
/// front and asks the shell to deep-link to it.
///
/// This calls `notify-rust` directly instead of going through
/// `tauri-plugin-notification`: that plugin's `show()` discards the
/// notification handle internally, so there is no way to learn a toast was
/// clicked through it. `notify-rust` is already a transitive dependency of
/// the (now-removed) plugin; using it directly just exposes what was already
/// there. `wait_for_response` blocks until the toast resolves, so it needs
/// its own thread — this is the crate's intended usage pattern (its own
/// doctests block the calling thread the same way), not a workaround.
fn show_activity_notification(app: &AppHandle, item: &ActivityItem) {
    // chat_mention is the one action type with dedicated wording: a mention
    // is addressed to this specific person (see router_chat.py's
    // post_message / recipient_user_id-scoped add_activity call), not a
    // broadcast like every other activity type, so the generic
    // "{username}: {description}" template reads oddly for it.
    let body = if item.action == "chat_mention" {
        format!("Vous avez été mentionné par {}", item.user.username)
    } else {
        format!("{}: {}", item.user.username, item.description)
    };
    let app_id = app.config().identifier.clone();

    let mut notification = OsNotification::new();
    notification.summary("LAN Party Manager").body(&body).app_id(&app_id);

    match notification.show() {
        Ok(handle) => {
            bump_unseen(app);
            let click_app = app.clone();
            let payload = DeepLinkPayload {
                entity_type: item.entity_type.clone(),
                entity_id: item.entity_id,
            };
            std::thread::spawn(move || {
                let _ = handle.wait_for_response(move |response: &NotificationResponse| {
                    if response.is_default_action() {
                        show_and_focus(&click_app);
                        let _ = click_app.emit("lpm-notification-clicked", payload);
                    }
                });
            });
        }
        Err(e) => eprintln!("[lpm] notification show failed: {e}"),
    }
}

async fn poll_activity(
    app: tauri::AppHandle,
    token: String,
    base_url: String,
    my_generation: u64,
    generation: Arc<Mutex<u64>>,
) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .user_agent(USER_AGENT)
        .build()
    {
        Ok(c) => c,
        Err(_) => return,
    };
    // Trailing slash is required: `/api/activity` (no slash) hits Starlette's
    // redirect_slashes 307, and self-hosted reverse proxies don't always
    // forward/trust X-Forwarded-Proto, so the Location header can come back
    // as http:// even for an https:// request. reqwest then (correctly)
    // strips the Authorization header on that scheme downgrade, and the
    // retried request 403s as "no credentials" rather than 401 "bad token" —
    // silently breaking notification polling. Hitting the exact route
    // (trailing slash) skips the redirect, and the proxy config, entirely.
    let activity_url = format!("{}/api/activity/?limit=20", base_url.trim_end_matches('/'));

    // None until the first successful poll — that first poll only records
    // the current newest id as a baseline and fires no notifications, so
    // logging in doesn't dump every pre-existing activity item as "new."
    let mut last_seen_id: Option<i64> = None;

    loop {
        if !still_current(&generation, my_generation) {
            return;
        }

        match client.get(&activity_url).bearer_auth(&token).send().await {
            Ok(resp) => {
                let status = resp.status();
                eprintln!("[lpm] poll {activity_url} -> {status}");
                if status.is_success() {
                    match resp.json::<Vec<ActivityItem>>().await {
                        Ok(items) => {
                            // Backend returns newest-first (router_activity.py).
                            if let Some(newest) = items.first() {
                                if let Some(last) = last_seen_id {
                                    let mut new_items: Vec<&ActivityItem> =
                                        items.iter().filter(|i| i.id > last).collect();
                                    new_items.reverse(); // oldest-of-the-new-batch first
                                    eprintln!("[lpm] {} new activity item(s)", new_items.len());
                                    for item in new_items {
                                        if !category_enabled(&app, &item.action) {
                                            continue;
                                        }
                                        eprintln!("[lpm] notifying: {} ({})", item.description, item.action);
                                        show_activity_notification(&app, item);
                                    }
                                } else {
                                    eprintln!("[lpm] baseline set at id={}", newest.id);
                                }
                                last_seen_id = Some(newest.id);
                            }
                        }
                        Err(e) => eprintln!("[lpm] poll: bad JSON: {e}"),
                    }
                }
            }
            Err(e) => eprintln!("[lpm] poll: request failed: {e}"),
        }
        // A network error, a 401 (revoked token), or a decode failure just
        // means this cycle contributes nothing — try again next tick rather
        // than tearing down the loop over a transient blip.

        let mut elapsed = Duration::ZERO;
        while elapsed < POLL_INTERVAL {
            if !still_current(&generation, my_generation) {
                return;
            }
            let step = Duration::from_secs(1);
            tokio::time::sleep(step).await;
            elapsed += step;
        }
    }
}

fn main() {
    tauri::Builder::default()
        // Must be the first plugin registered (Tauri's own recommendation,
        // strongest on Windows): launching LPM again from the Start Menu
        // while it's already running (even minimized to tray) previously
        // spawned a second full process/window instead of reusing the
        // existing one. This plugin intercepts that second launch, forwards
        // its argv/cwd to the *first* instance via this callback, and exits
        // the second process on its own — so the callback just needs to
        // bring the existing window to the front, reusing the same
        // show/unminimize/focus path the tray's "Open" item uses.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_and_focus(app);
        }))
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_autostart::Builder::new().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(PollState {
            generation: Arc::new(Mutex::new(0)),
            auth_token: Arc::new(Mutex::new(None)),
        })
        .setup(|app| Ok(setup_tray_and_window(app)?))
        .invoke_handler(tauri::generate_handler![
            check_server,
            set_auth_token,
            clear_auth_token,
            start_oauth_auth,
            get_autostart_enabled,
            set_autostart_enabled,
            open_external
        ])
        .run(tauri::generate_context!())
        .expect("error while running Lan Party Manager");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opens_the_providers_own_sign_in_pages() {
        assert!(is_expected_authorize_url(
            "discord",
            "https://discord.com/oauth2/authorize?client_id=1&redirect_uri=https%3A%2F%2Flan.example%2Fapi%2Fauth%2Fdiscord%2Fcallback&state=x"
        ));
        assert!(is_expected_authorize_url(
            "steam",
            "https://steamcommunity.com/openid/login?openid.mode=checkid_setup&openid.return_to=https%3A%2F%2Flan.example"
        ));
    }

    #[test]
    fn refuses_anything_a_rogue_server_could_send() {
        for url in [
            r"\\10.0.0.66\s\x.exe",
            "file:///C:/Windows/System32/cmd.exe",
            "http://discord.com/oauth2/authorize?client_id=1",
            "https://discord.com.evil.net/oauth2/authorize?client_id=1",
            "https://discord.com@evil.net/oauth2/authorize?client_id=1",
            "https://evil.net/?https://discord.com/oauth2/authorize?",
            r"https://discord.com/oauth2/authorize? \\10.0.0.66\s",
            "https://discord.com/oauth2/authorize?a=1\nb",
            "",
        ] {
            assert!(!is_expected_authorize_url("discord", url), "accepted {url:?}");
        }
    }

    #[test]
    fn each_provider_only_opens_its_own_page() {
        let steam = "https://steamcommunity.com/openid/login?openid.mode=checkid_setup";
        assert!(!is_expected_authorize_url("discord", steam));
        assert!(!is_expected_authorize_url("github", steam));
    }

    #[test]
    fn reads_target_and_nonce_off_the_callback() {
        let (target, nonce) = parse_callback_request(
            "GET /callback?target=%2Fauth%2Fdiscord%2Fcomplete%23token%3Dabc&nonce=f00d HTTP/1.1\r\nHost: x\r\n\r\n",
        );
        assert_eq!(target.as_deref(), Some("/auth/discord/complete#token=abc"));
        assert_eq!(nonce.as_deref(), Some("f00d"));

        // An older server sends no nonce at all.
        let (target, nonce) = parse_callback_request("GET /callback?target=%2Fprofile HTTP/1.1\r\n");
        assert_eq!(target.as_deref(), Some("/profile"));
        assert_eq!(nonce, None);

        // A lookalike parameter name isn't the real one.
        let (target, nonce) = parse_callback_request("GET /callback?targetx=%2Fa&noncex=1 HTTP/1.1\r\n");
        assert_eq!((target, nonce), (None, None));
        assert_eq!(parse_callback_request(""), (None, None));
    }

    #[test]
    fn nonce_must_match_exactly() {
        assert!(nonce_matches("abc123", "abc123"));
        assert!(!nonce_matches("abc124", "abc123"));
        assert!(!nonce_matches("abc12", "abc123"));
        assert!(!nonce_matches("abc1234", "abc123"));
        assert!(!nonce_matches("", ""));
    }

    #[test]
    fn nonces_are_fresh_64_char_hex() {
        let (a, b) = (new_nonce().unwrap(), new_nonce().unwrap());
        assert_eq!(a.len(), 64);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    #[test]
    fn listener_only_accepts_the_callback_carrying_its_nonce() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};

        async fn hit(port: u16, path: &str) -> String {
            let mut stream = tokio::net::TcpStream::connect(("127.0.0.1", port)).await.unwrap();
            stream
                .write_all(format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n").as_bytes())
                .await
                .unwrap();
            let mut response = String::new();
            stream.read_to_string(&mut response).await.unwrap();
            response
        }

        tauri::async_runtime::block_on(async {
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let port = listener.local_addr().unwrap().port();
            let waiting = tauri::async_runtime::spawn(wait_for_oauth_callback(listener, "good".into()));

            // A local program forging a callback, with a wrong nonce or none at all.
            assert!(hit(port, "/callback?target=%2Fevil&nonce=bad").await.starts_with("HTTP/1.1 403"));
            assert!(hit(port, "/callback?target=%2Fevil").await.starts_with("HTTP/1.1 403"));

            // The real one still gets through afterwards.
            assert!(hit(port, "/callback?target=%2Fprofile%3Fsteam%3Dlinked&nonce=good").await.starts_with("HTTP/1.1 200"));
            let target = waiting.await.unwrap().unwrap();
            assert_eq!(target.as_deref(), Some("/profile?steam=linked"));
        });
    }
}
