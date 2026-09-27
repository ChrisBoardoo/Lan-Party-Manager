//! League of Legends stats capture — the desktop half of
//! `backend/router_lol.py`.
//!
//! When the crew has the `lol_stats` feature on, this watches the League
//! Client's own local API (the "LCU") — during a LAN the member attends, and
//! outside one too unless they unticked that in the shell's settings — and,
//! when a game reaches its end-of-game screen, forwards the
//! client's end-of-game block untouched to `POST /api/lol/matches`. All the
//! parsing happens server-side (`backend/lol_capture.py`) on purpose: the LCU
//! is unofficial, and a Riot field rename should be one server redeploy, not
//! a desktop release every member has to install.
//!
//! Towards the game this is read-only and minimal: GET requests to
//! `https://127.0.0.1:<port>`, with the port and password the client itself
//! writes to its `lockfile`. No process inspection, no memory reading — the
//! same channel every LoL companion app uses. With the feature off, or the
//! member's settings saying no, it doesn't touch the League client at all.

use std::collections::{HashSet, VecDeque};
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use notify_rust::Notification as OsNotification;
use serde_json::{json, Value};
use tauri::AppHandle;
use tauri_plugin_store::StoreExt;

use crate::{still_current, CONFIG_STORE, USER_AGENT};

/// How often the game phase is read while the client is running.
const CLIENT_POLL: Duration = Duration::from_secs(5);
/// How often to look for the client (or re-read the settings) otherwise.
const IDLE_POLL: Duration = Duration::from_secs(15);
/// How often the server is asked again whether capture is on (feature flag +
/// a LAN in progress) — a LAN starting mid-session is picked up within this.
const GATE_RECHECK: Duration = Duration::from_secs(10 * 60);
/// A gate check that failed (server unreachable) is retried sooner.
const GATE_RETRY: Duration = Duration::from_secs(60);
/// A send that failed on a network/server error is retried once per loop
/// turn, this many times, before being given up on.
const MAX_SEND_ATTEMPTS: u32 = 60;
/// Games waiting for a retry. More than a LAN night's worth would mean the
/// server has been down for hours — the oldest are dropped first.
const MAX_PENDING: usize = 10;

/// Riot's own index of installed games, which knows where League lives.
const RIOT_CLIENT_INSTALLS: &str = r"C:\ProgramData\Riot Games\RiotClientInstalls.json";
const DEFAULT_LEAGUE_DIR: &str = r"C:\Riot Games\League of Legends";

/// Phases during which a game session read at `InProgress` is still this
/// game's. Anything else (lobby, champ select, none) starts a new game.
const IN_GAME_PHASES: &[&str] = &["InProgress", "Reconnect", "WaitingForStats", "PreEndOfGame", "EndOfGame"];

/// The member's own switch, in the shell's settings panel (ui/src/main.js).
/// Missing = on, like the notification categories: the crew enabled the
/// feature server-side, and the member chose to set a Riot ID.
fn capture_enabled_locally(app: &AppHandle) -> bool {
    store_flag(app, "lolCapture")
}

/// The member's second switch: also send games played outside a LAN (at
/// home, between LANs). Missing = on, the crew's default; unticking it keeps
/// only LAN games flowing.
fn capture_outside_lan_locally(app: &AppHandle) -> bool {
    store_flag(app, "lolCaptureOutsideLan")
}

fn store_flag(app: &AppHandle, key: &str) -> bool {
    app.store(CONFIG_STORE)
        .ok()
        .and_then(|store| store.get(key))
        .and_then(|v| v.as_bool())
        .unwrap_or(true)
}

// ── Finding the League client ────────────────────────────────────────────

#[derive(Clone, Debug, PartialEq)]
struct Lcu {
    port: u16,
    password: String,
}

/// `LeagueClient:<pid>:<port>:<password>:<protocol>` — present only while
/// the client runs, rewritten with a fresh port/password on every start.
fn parse_lockfile(content: &str) -> Option<Lcu> {
    let parts: Vec<&str> = content.trim().split(':').collect();
    if parts.len() < 5 || parts[3].is_empty() {
        return None;
    }
    Some(Lcu { port: parts[2].parse().ok()?, password: parts[3].to_string() })
}

/// League install folders listed in RiotClientInstalls.json's
/// `associated_client` map (keyed by install folder).
fn league_dirs_from_installs(json_text: &str) -> Vec<PathBuf> {
    let Ok(v) = serde_json::from_str::<Value>(json_text) else {
        return Vec::new();
    };
    v.get("associated_client")
        .and_then(|a| a.as_object())
        .map(|map| {
            map.keys()
                .filter(|dir| dir.to_lowercase().contains("league of legends"))
                .map(PathBuf::from)
                .collect()
        })
        .unwrap_or_default()
}

fn find_client() -> Option<Lcu> {
    let mut dirs = std::fs::read_to_string(RIOT_CLIENT_INSTALLS)
        .map(|text| league_dirs_from_installs(&text))
        .unwrap_or_default();
    dirs.push(PathBuf::from(DEFAULT_LEAGUE_DIR));
    dirs.into_iter()
        .find_map(|dir| std::fs::read_to_string(dir.join("lockfile")).ok())
        .and_then(|content| parse_lockfile(&content))
}

enum LcuReply {
    Json(Value),
    /// Answered, but not with what we asked for (e.g. no end-of-game block yet).
    NotAvailable,
    /// Unreachable or refusing our password — the client closed or restarted.
    Gone,
}

/// The League client serves its local API with a certificate Riot signs
/// itself, and this client only ever talks to 127.0.0.1 — skipping
/// verification for it can't expose anything a local process couldn't
/// already read from the lockfile. `no_proxy`: a system proxy has no business
/// seeing localhost traffic.
fn lcu_http_client() -> reqwest::Result<reqwest::Client> {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .danger_accept_invalid_certs(true)
        .danger_accept_invalid_hostnames(true)
        .no_proxy()
        .build()
}

async fn lcu_get(client: &reqwest::Client, lcu: &Lcu, path: &str) -> LcuReply {
    let url = format!("https://127.0.0.1:{}{}", lcu.port, path);
    match client.get(&url).basic_auth("riot", Some(&lcu.password)).send().await {
        Err(_) => LcuReply::Gone,
        Ok(resp) => {
            let status = resp.status();
            if status == reqwest::StatusCode::UNAUTHORIZED || status == reqwest::StatusCode::FORBIDDEN {
                LcuReply::Gone
            } else if status.is_success() {
                resp.json::<Value>().await.map(LcuReply::Json).unwrap_or(LcuReply::NotAvailable)
            } else {
                LcuReply::NotAvailable
            }
        }
    }
}

// ── The end-of-game block ────────────────────────────────────────────────

fn id_string(v: &Value) -> Option<String> {
    let id = v.as_u64().map(|n| n.to_string()).or_else(|| v.as_str().map(str::to_string))?;
    (!id.is_empty() && id != "0").then_some(id)
}

fn game_id(eog: &Value) -> Option<String> {
    eog.get("gameId").and_then(id_string)
}

/// A session with no game id of its own is trusted: it was read at this
/// game's `InProgress`, and is dropped whenever a new game starts.
fn session_belongs_to(session: &Value, game_id: &str) -> bool {
    match session.get("gameData").and_then(|g| g.get("gameId")).and_then(id_string) {
        Some(id) => id == game_id,
        None => true,
    }
}

// ── Is capture on? (server side) ─────────────────────────────────────────

/// What the server says (`GET /api/lol/capture-status`): the crew's feature
/// flag, and whether a LAN this member RSVP'd "in" to is running — decided
/// server-side, in the app's own timezone, so the desktop does no date
/// arithmetic of its own.
#[derive(Clone, Copy, Debug, PartialEq)]
struct ServerGate {
    enabled: bool,
    lan_in_progress: bool,
}

/// None = couldn't ask (server unreachable, or one without this endpoint).
async fn capture_gate(http: &reqwest::Client, base: &str, token: &str) -> Option<ServerGate> {
    let status: Value = http
        .get(format!("{base}/api/lol/capture-status"))
        .bearer_auth(token)
        .send()
        .await
        .ok()?
        .error_for_status()
        .ok()?
        .json()
        .await
        .ok()?;
    Some(ServerGate {
        enabled: status.get("enabled").and_then(Value::as_bool)?,
        lan_in_progress: status.get("lan_in_progress").and_then(Value::as_bool)?,
    })
}

/// Whether to watch the League client right now, with the reason for the
/// `[lpm] lol:` trace. Games are sent at any time; outside a LAN only if the
/// member left "outside a LAN" ticked (the server files those under no event,
/// global stats only).
fn capture_mode(gate: Option<ServerGate>, outside_lan_allowed: bool) -> (bool, &'static str) {
    match gate {
        None => (false, "paused — server unreachable"),
        Some(g) if !g.enabled => (false, "off — LoL stats disabled on the server"),
        Some(g) if g.lan_in_progress => (true, "on — a LAN is in progress"),
        Some(_) if outside_lan_allowed => (true, "on — outside a LAN"),
        Some(_) => (false, "off — no LAN in progress, and games outside a LAN are unticked"),
    }
}

// ── Sending to LPM ───────────────────────────────────────────────────────

enum SendOutcome {
    Stored,
    /// A 4xx: retrying the same request can't change the answer.
    Rejected,
    /// Network error or 5xx: worth another try.
    Retry,
}

async fn send_game(http: &reqwest::Client, base: &str, token: &str, eog: &Value, session: Option<&Value>) -> SendOutcome {
    let body = json!({ "eog": eog, "session": session });
    match http.post(format!("{base}/api/lol/matches")).bearer_auth(token).json(&body).send().await {
        Err(e) => {
            eprintln!("[lpm] lol: send failed: {e}");
            SendOutcome::Retry
        }
        Ok(resp) => {
            let status = resp.status();
            if status.is_success() {
                SendOutcome::Stored
            } else if status.is_client_error() {
                let detail = resp.text().await.unwrap_or_default();
                eprintln!("[lpm] lol: server refused the game ({status}): {detail}");
                SendOutcome::Rejected
            } else {
                eprintln!("[lpm] lol: server error ({status}), will retry");
                SendOutcome::Retry
            }
        }
    }
}

fn notify_saved(app: &AppHandle) {
    let app_id = app.config().identifier.clone();
    let mut notification = OsNotification::new();
    notification
        .summary("LAN Party Manager")
        .body("Partie League of Legends enregistrée dans les stats de la LAN")
        .app_id(&app_id);
    if let Err(e) = notification.show() {
        eprintln!("[lpm] lol: notification failed: {e}");
    }
}

struct Pending {
    game_id: String,
    eog: Value,
    session: Option<Value>,
    attempts: u32,
}

/// Games already sent (or refused), and sends waiting for a retry — kept for
/// the whole process, not per loop: a new login or token (every full reload
/// of the embedded app) restarts `watch`, and neither a game still on its end
/// screen nor a pending retry should be lost or sent twice because of it. A
/// retry then goes out with the new token.
fn handled_games() -> &'static Mutex<HashSet<String>> {
    static HANDLED: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    HANDLED.get_or_init(|| Mutex::new(HashSet::new()))
}

fn pending_sends() -> &'static Mutex<VecDeque<Pending>> {
    static PENDING: OnceLock<Mutex<VecDeque<Pending>>> = OnceLock::new();
    PENDING.get_or_init(|| Mutex::new(VecDeque::new()))
}

fn queue_retry(p: Pending) {
    let mut pending = pending_sends().lock().unwrap();
    if pending.len() >= MAX_PENDING {
        pending.pop_front();
    }
    pending.push_back(p);
}

/// Sleeps in 1 s steps so a logout/token change stops the loop promptly.
/// False once this loop's generation is stale.
async fn nap(total: Duration, generation: &Mutex<u64>, my_generation: u64) -> bool {
    let step = Duration::from_secs(1);
    let mut elapsed = Duration::ZERO;
    while elapsed < total {
        if !still_current(generation, my_generation) {
            return false;
        }
        tokio::time::sleep(step).await;
        elapsed += step;
    }
    still_current(generation, my_generation)
}

/// Spawned next to `poll_activity` for the same login, under the same
/// generation — so it stops on logout or token change exactly like it.
pub async fn watch(
    app: AppHandle,
    token: String,
    base_url: String,
    my_generation: u64,
    generation: Arc<Mutex<u64>>,
) {
    let base = base_url.trim_end_matches('/').to_string();
    let Ok(http) = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .user_agent(USER_AGENT)
        .build()
    else {
        return;
    };
    let Ok(lcu_http) = lcu_http_client() else {
        return;
    };

    let mut gate: Option<ServerGate> = None;
    let mut gate_checked: Option<Instant> = None;
    let mut last_mode: Option<&'static str> = None;
    let mut lcu: Option<Lcu> = None;
    let mut phase: Option<String> = None;
    let mut session: Option<Value> = None;

    loop {
        if !still_current(&generation, my_generation) {
            return;
        }

        if !capture_enabled_locally(&app) {
            if lcu.take().is_some() {
                eprintln!("[lpm] lol: capture turned off in settings");
            }
            last_mode = None; // so ticking it again traces the state afresh
            phase = None;
            session = None;
            if !nap(IDLE_POLL, &generation, my_generation).await {
                return;
            }
            continue;
        }

        let due = match gate_checked {
            None => true,
            Some(at) => at.elapsed() >= if gate.is_some() { GATE_RECHECK } else { GATE_RETRY },
        };
        if due {
            gate = capture_gate(&http, &base, &token).await;
            gate_checked = Some(Instant::now());
        }
        // Re-read every turn: the member's "outside a LAN" box takes effect
        // right away, without waiting for the next server check.
        let (active, why) = capture_mode(gate, capture_outside_lan_locally(&app));
        if last_mode != Some(why) {
            eprintln!("[lpm] lol: capture {why}");
            last_mode = Some(why);
        }

        // Retries first — they still go out after a LAN ends (the server
        // answers "already have it" or refuses; either way it's settled).
        // Taken out of the shared queue, never awaited while it's locked.
        let due_retries: Vec<Pending> = pending_sends().lock().unwrap().drain(..).collect();
        for mut p in due_retries {
            match send_game(&http, &base, &token, &p.eog, p.session.as_ref()).await {
                SendOutcome::Stored => {
                    eprintln!("[lpm] lol: game {} sent (retry {})", p.game_id, p.attempts);
                    notify_saved(&app);
                }
                SendOutcome::Rejected => {}
                SendOutcome::Retry => {
                    p.attempts += 1;
                    if p.attempts < MAX_SEND_ATTEMPTS {
                        queue_retry(p);
                    } else {
                        eprintln!("[lpm] lol: giving up on game {}", p.game_id);
                    }
                }
            }
        }

        if !active {
            // LoL stats off, or no LAN and the member keeps home games to
            // themselves: leave the League client alone.
            lcu = None;
            phase = None;
            session = None;
        } else {
            if lcu.is_none() {
                lcu = find_client();
                if let Some(found) = &lcu {
                    eprintln!("[lpm] lol: League client found (port {})", found.port);
                }
            }
            if let Some(client) = lcu.clone() {
                match lcu_get(&lcu_http, &client, "/lol-gameflow/v1/gameflow-phase").await {
                    LcuReply::Gone => {
                        eprintln!("[lpm] lol: League client closed");
                        lcu = None;
                        phase = None;
                        session = None;
                    }
                    LcuReply::NotAvailable => {}
                    LcuReply::Json(v) => {
                        let now = v.as_str().unwrap_or_default().to_string();
                        if phase.as_deref() != Some(now.as_str()) {
                            eprintln!("[lpm] lol: phase {} -> {now}", phase.as_deref().unwrap_or("-"));
                            if !IN_GAME_PHASES.contains(&now.as_str()) {
                                session = None;
                            }
                            if now == "InProgress" {
                                if let LcuReply::Json(s) = lcu_get(&lcu_http, &client, "/lol-gameflow/v1/session").await {
                                    session = Some(s);
                                }
                            }
                            phase = Some(now.clone());
                        }
                        if now == "PreEndOfGame" || now == "EndOfGame" {
                            if let LcuReply::Json(eog) =
                                lcu_get(&lcu_http, &client, "/lol-end-of-game/v1/eog-stats-block").await
                            {
                                if let Some(id) = game_id(&eog) {
                                    // `insert` is false for a game already sent (or refused) —
                                    // the end screen stays up for a while, polled every 5 s.
                                    let first_time = handled_games().lock().unwrap().insert(id.clone());
                                    if first_time {
                                        let game_session = session.clone().filter(|s| session_belongs_to(s, &id));
                                        match send_game(&http, &base, &token, &eog, game_session.as_ref()).await {
                                            SendOutcome::Stored => {
                                                eprintln!("[lpm] lol: game {id} sent");
                                                notify_saved(&app);
                                            }
                                            SendOutcome::Rejected => {}
                                            SendOutcome::Retry => {
                                                queue_retry(Pending { game_id: id, eog, session: game_session, attempts: 1 });
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        let wait = if lcu.is_some() { CLIENT_POLL } else { IDLE_POLL };
        if !nap(wait, &generation, my_generation).await {
            return;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_the_lockfile() {
        assert_eq!(
            parse_lockfile("LeagueClient:12345:54321:aBc-d_9Ef:https\n"),
            Some(Lcu { port: 54321, password: "aBc-d_9Ef".into() })
        );
        assert_eq!(parse_lockfile(""), None);
        assert_eq!(parse_lockfile("LeagueClient:1:notaport:pw:https"), None);
        assert_eq!(parse_lockfile("LeagueClient:1:54321::https"), None);
    }

    #[test]
    fn finds_league_in_riot_client_installs() {
        let json = r#"{
            "associated_client": {
                "D:/Games/Riot Games/League of Legends/": "D:/Games/Riot Games/Riot Client/RiotClientServices.exe",
                "D:/Games/Riot Games/VALORANT/live/": "D:/Games/Riot Games/Riot Client/RiotClientServices.exe"
            },
            "rc_default": "D:/Games/Riot Games/Riot Client/RiotClientServices.exe"
        }"#;
        assert_eq!(league_dirs_from_installs(json), vec![PathBuf::from("D:/Games/Riot Games/League of Legends/")]);
        assert!(league_dirs_from_installs("not json").is_empty());
        assert!(league_dirs_from_installs("{}").is_empty());
    }

    #[test]
    fn capture_modes() {
        let gate = |enabled, lan_in_progress| Some(ServerGate { enabled, lan_in_progress });
        // During a LAN: always, whatever the "outside a LAN" box says.
        assert!(capture_mode(gate(true, true), false).0);
        assert!(capture_mode(gate(true, true), true).0);
        // Outside a LAN: only if the member left that box ticked.
        assert!(capture_mode(gate(true, false), true).0);
        assert!(!capture_mode(gate(true, false), false).0);
        // Feature off, or no answer from the server: never.
        assert!(!capture_mode(gate(false, true), true).0);
        assert!(!capture_mode(None, true).0);
    }

    #[test]
    fn game_ids() {
        assert_eq!(game_id(&json!({ "gameId": 7212345678u64 })), Some("7212345678".into()));
        assert_eq!(game_id(&json!({ "gameId": "7212345678" })), Some("7212345678".into()));
        assert_eq!(game_id(&json!({ "gameId": 0 })), None);
        assert_eq!(game_id(&json!({})), None);
    }

    /// Against the real thing: `cargo test live_league_client -- --ignored --nocapture`
    /// with the League client open (a game's end screen shows the most).
    #[test]
    #[ignore = "needs a running League client"]
    fn live_league_client() {
        tauri::async_runtime::block_on(async {
            let lcu = find_client().expect("no League lockfile found (is the client running?)");
            let http = lcu_http_client().unwrap();
            match lcu_get(&http, &lcu, "/lol-gameflow/v1/gameflow-phase").await {
                LcuReply::Json(v) => eprintln!("phase: {v}"),
                LcuReply::NotAvailable => panic!("client answered without a phase"),
                LcuReply::Gone => panic!("client unreachable — TLS or password problem"),
            }
            match lcu_get(&http, &lcu, "/lol-end-of-game/v1/eog-stats-block").await {
                LcuReply::Json(v) => eprintln!("end-of-game block for game {:?}", game_id(&v)),
                LcuReply::NotAvailable => eprintln!("no end-of-game block right now"),
                LcuReply::Gone => panic!("client unreachable on the end-of-game route"),
            }
        });
    }

    #[test]
    fn session_pairing() {
        assert!(session_belongs_to(&json!({ "gameData": { "gameId": 42 } }), "42"));
        assert!(!session_belongs_to(&json!({ "gameData": { "gameId": 41 } }), "42"));
        assert!(session_belongs_to(&json!({ "gameData": { "isCustomGame": true } }), "42"));
    }
}
