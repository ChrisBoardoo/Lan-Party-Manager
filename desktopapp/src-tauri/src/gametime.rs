//! Game time — the desktop half of `backend/router_gametime.py`.
//!
//! When the crew has the `gametime` feature on, this looks at the running
//! processes once a minute — during a LAN the member attends, and outside one
//! only if they ticked that in the shell's settings — recognises the games
//! among them, and sends `POST /api/gametime/heartbeat` with their names. The
//! server turns the heartbeats into sessions on its own clock.
//!
//! What it recognises, and how:
//! - Steam games: the library folders' `appmanifest_*.acf` say which folder
//!   under `steamapps/common` belongs to which game; a process run from there
//!   is that game;
//! - Epic games: the launcher's `.item` manifests, same idea with
//!   `InstallLocation`;
//! - everything else (Riot, Battle.net, Wargaming, RSI...): the executable
//!   names in the list served by `GET /api/gametime/catalog`, so the list grows
//!   with a server update rather than a new MSI.
//!
//! Only "I'm playing X" leaves the machine: never the process list, never a
//! path. With the feature off, or the member's settings saying no, it doesn't
//! look at the processes at all.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use sysinfo::{ProcessRefreshKind, System, UpdateKind};
use tauri::AppHandle;
use tauri_plugin_store::StoreExt;

use crate::{still_current, CONFIG_STORE, USER_AGENT};

/// One heartbeat a minute while a game runs; the server keeps a session open
/// across a few missed ones (router_gametime.SESSION_GAP).
const TICK: Duration = Duration::from_secs(60);
/// How often to re-read the settings while counting is off.
const IDLE_POLL: Duration = Duration::from_secs(15);
/// How often the server is asked again whether counting is on (feature flag +
/// a LAN in progress), and how soon after a failed ask.
const GATE_RECHECK: Duration = Duration::from_secs(10 * 60);
const GATE_RETRY: Duration = Duration::from_secs(60);
/// The served list and the launchers' manifests change rarely: a game
/// installed mid-LAN is picked up within this.
const INDEX_REFRESH: Duration = Duration::from_secs(30 * 60);
/// router_gametime accepts at most 3 games per heartbeat.
const MAX_GAMES: usize = 3;

// ── The member's settings (ui/src/main.js) ───────────────────────────────

fn store_value(app: &AppHandle, key: &str) -> Option<Value> {
    app.store(CONFIG_STORE).ok().and_then(|store| store.get(key))
}

/// Counting at all. Missing = on, like the LoL capture: the crew switched the
/// feature on server-side, and the member can untick it.
fn counting_enabled(app: &AppHandle) -> bool {
    store_value(app, "gametime").and_then(|v| v.as_bool()).unwrap_or(true)
}

/// Outside a LAN too. Missing = off (decided 2026-10-27): game time is a LAN
/// stat first.
fn outside_lan_allowed(app: &AppHandle) -> bool {
    store_value(app, "gametimeOutsideLan").and_then(|v| v.as_bool()).unwrap_or(false)
}

/// "Show what I'm playing" to the crew. Missing = on; the time is counted
/// either way.
fn visible(app: &AppHandle) -> bool {
    store_value(app, "gametimeVisible").and_then(|v| v.as_bool()).unwrap_or(true)
}

// ── Is counting on? (server side) ────────────────────────────────────────

#[derive(Clone, Copy, Debug, PartialEq)]
struct ServerGate {
    enabled: bool,
    lan_in_progress: bool,
}

/// None = couldn't ask (server unreachable, or one without this endpoint).
async fn gate(http: &reqwest::Client, base: &str, token: &str) -> Option<ServerGate> {
    let status: Value = http
        .get(format!("{base}/api/gametime/status"))
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

fn counting_mode(gate: Option<ServerGate>, outside_lan_allowed: bool) -> (bool, &'static str) {
    match gate {
        None => (false, "paused — server unreachable"),
        Some(g) if !g.enabled => (false, "off — game time disabled on the server"),
        Some(g) if g.lan_in_progress => (true, "on — a LAN is in progress"),
        Some(_) if outside_lan_allowed => (true, "on — outside a LAN"),
        Some(_) => (false, "off — no LAN in progress, and outside a LAN is unticked"),
    }
}

// ── What counts as a game ────────────────────────────────────────────────

#[derive(Clone, Debug, PartialEq)]
struct Game {
    key: String,
    name: String,
}

/// Everything needed to recognise a game from a running process: executable
/// names from the served list, and install folders from the launchers.
#[derive(Default)]
struct GameIndex {
    by_exe: HashMap<String, Game>,
    ignore_exes: HashSet<String>,
    /// Lower-cased install folder (with a trailing separator) → game.
    folders: Vec<(String, Game)>,
}

impl GameIndex {
    /// `running_steam`: the Steam game Steam itself says is running, which
    /// settles a folder several games share (Half-Life 2 and its episodes all
    /// live in `common/Half-Life 2`). Without it, the lowest app id wins — the
    /// base game, see build_index.
    fn recognise(&self, exe_name: &str, exe_path: Option<&Path>, running_steam: Option<&str>) -> Option<Game> {
        let name = exe_name.to_lowercase();
        if self.ignore_exes.contains(&name) {
            return None;
        }
        if let Some(game) = self.by_exe.get(&name) {
            return Some(game.clone());
        }
        let path = folder_key(exe_path?);
        let (best_folder, best) = self.folders.iter().find(|(folder, _)| path.starts_with(folder.as_str()))?;
        let preferred = running_steam.and_then(|key| {
            self.folders.iter().find(|(folder, game)| folder == best_folder && game.key == key)
        });
        Some(preferred.map_or(best, |(_, game)| game).clone())
    }
}

fn app_number(key: &str) -> u64 {
    key.rsplit(':').next().and_then(|n| n.parse().ok()).unwrap_or(u64::MAX)
}

/// Longest folder first, so a game nested in another's folder wins; for a
/// shared folder, the lowest app id (the base game) first.
fn sort_folders(folders: &mut [(String, Game)]) {
    folders.sort_by(|a, b| b.0.len().cmp(&a.0.len()).then_with(|| app_number(&a.1.key).cmp(&app_number(&b.1.key))));
}

fn folder_key(path: &Path) -> String {
    path.to_string_lossy().replace('/', "\\").to_lowercase()
}

fn folder_entry(path: &Path) -> String {
    let mut key = folder_key(path);
    if !key.ends_with('\\') {
        key.push('\\');
    }
    key
}

/// The server's key rule (`^[a-z0-9][a-z0-9:._-]{0,63}$`) for a launcher's own
/// id, which may hold anything.
fn key_part(raw: &str) -> String {
    raw.to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() || "._-".contains(c) { c } else { '-' })
        .take(56)
        .collect()
}

async fn served_list(http: &reqwest::Client, base: &str, token: &str) -> Option<Value> {
    http.get(format!("{base}/api/gametime/catalog"))
        .bearer_auth(token)
        .send()
        .await
        .ok()?
        .error_for_status()
        .ok()?
        .json()
        .await
        .ok()
}

fn build_index(list: &Value) -> GameIndex {
    let mut index = GameIndex::default();
    for game in list.get("games").and_then(Value::as_array).into_iter().flatten() {
        let (Some(key), Some(name)) = (
            game.get("key").and_then(Value::as_str),
            game.get("name").and_then(Value::as_str),
        ) else {
            continue;
        };
        for exe in game.get("exes").and_then(Value::as_array).into_iter().flatten() {
            if let Some(exe) = exe.as_str() {
                index.by_exe.insert(exe.to_lowercase(), Game { key: key.into(), name: name.into() });
            }
        }
    }
    for exe in list.get("ignore_exes").and_then(Value::as_array).into_iter().flatten() {
        if let Some(exe) = exe.as_str() {
            index.ignore_exes.insert(exe.to_lowercase());
        }
    }
    let ignore_steam: HashSet<u64> = list
        .get("ignore_steam_apps")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_u64)
        .collect();
    index.folders.extend(steam_games(&ignore_steam));
    index.folders.extend(epic_games());
    sort_folders(&mut index.folders);
    index
}

// ── Steam ────────────────────────────────────────────────────────────────

#[cfg(windows)]
fn steam_root() -> Option<PathBuf> {
    use winreg::enums::HKEY_CURRENT_USER;
    use winreg::RegKey;
    let key = RegKey::predef(HKEY_CURRENT_USER).open_subkey(r"Software\Valve\Steam").ok();
    let from_registry = key.and_then(|k| k.get_value::<String, _>("SteamPath").ok()).map(PathBuf::from);
    from_registry
        .into_iter()
        .chain([PathBuf::from(r"C:\Program Files (x86)\Steam")])
        .find(|p| p.join("steamapps").is_dir())
}

/// `steam:<id>` of the game Steam says is running, if any.
#[cfg(windows)]
fn running_steam_game() -> Option<String> {
    use winreg::enums::HKEY_CURRENT_USER;
    use winreg::RegKey;
    let id: u32 = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey(r"Software\Valve\Steam")
        .ok()?
        .get_value("RunningAppID")
        .ok()?;
    (id != 0).then(|| format!("steam:{id}"))
}

#[cfg(not(windows))]
fn running_steam_game() -> Option<String> {
    None
}

#[cfg(not(windows))]
fn steam_root() -> Option<PathBuf> {
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    [home.join(".steam/steam"), home.join(".local/share/Steam")]
        .into_iter()
        .find(|p| p.join("steamapps").is_dir())
}

/// The `"key"  "value"` pairs of a Valve KeyValues text file (.vdf/.acf),
/// flattened — enough for `path`, `appid`, `name` and `installdir`.
fn vdf_pairs(text: &str) -> Vec<(String, String)> {
    let mut pairs = Vec::new();
    for line in text.lines() {
        let parts: Vec<&str> = line.split('"').collect();
        // `"key"<tab><tab>"value"` splits into ["", key, ws, value, ""].
        if parts.len() >= 5 && parts[2].trim().is_empty() {
            pairs.push((parts[1].to_lowercase(), parts[3].replace("\\\\", "\\")));
        }
    }
    pairs
}

fn steam_games(ignore: &HashSet<u64>) -> Vec<(String, Game)> {
    let Some(root) = steam_root() else {
        return Vec::new();
    };
    let mut libraries = vec![root.clone()];
    if let Ok(text) = std::fs::read_to_string(root.join("steamapps").join("libraryfolders.vdf")) {
        for (key, value) in vdf_pairs(&text) {
            if key == "path" {
                let path = PathBuf::from(value);
                if !libraries.contains(&path) {
                    libraries.push(path);
                }
            }
        }
    }
    let mut games = Vec::new();
    for library in libraries {
        let apps = library.join("steamapps");
        let Ok(entries) = std::fs::read_dir(&apps) else {
            continue;
        };
        for entry in entries.flatten() {
            let file_name = entry.file_name().to_string_lossy().to_lowercase();
            if !(file_name.starts_with("appmanifest_") && file_name.ends_with(".acf")) {
                continue;
            }
            let Ok(text) = std::fs::read_to_string(entry.path()) else {
                continue;
            };
            let pairs: HashMap<String, String> = vdf_pairs(&text).into_iter().rev().collect();
            let (Some(appid), Some(name), Some(dir)) = (pairs.get("appid"), pairs.get("name"), pairs.get("installdir"))
            else {
                continue;
            };
            let Ok(appid_num) = appid.parse::<u64>() else {
                continue;
            };
            if ignore.contains(&appid_num) || dir.is_empty() {
                continue;
            }
            games.push((
                folder_entry(&apps.join("common").join(dir)),
                Game { key: format!("steam:{appid_num}"), name: name.clone() },
            ));
        }
    }
    games
}

// ── Epic ─────────────────────────────────────────────────────────────────

#[cfg(windows)]
fn epic_games() -> Vec<(String, Game)> {
    let manifests = Path::new(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests");
    let Ok(entries) = std::fs::read_dir(manifests) else {
        return Vec::new();
    };
    let mut games = Vec::new();
    for entry in entries.flatten() {
        if entry.path().extension().and_then(|e| e.to_str()) != Some("item") {
            continue;
        }
        let Some(item) = std::fs::read_to_string(entry.path())
            .ok()
            .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        else {
            continue;
        };
        // Unreal Engine, Quixel Bridge and other tools sit among the same
        // manifests; only "games" are games.
        let is_game = item
            .get("AppCategories")
            .and_then(Value::as_array)
            .is_some_and(|cats| cats.iter().any(|c| c.as_str() == Some("games")));
        if !is_game {
            continue;
        }
        let field = |name: &str| item.get(name).and_then(Value::as_str).unwrap_or("").to_string();
        let (location, name, app) = (field("InstallLocation"), field("DisplayName"), field("AppName"));
        if location.is_empty() || name.is_empty() || app.is_empty() {
            continue;
        }
        games.push((
            folder_entry(Path::new(&location)),
            Game { key: format!("epic:{}", key_part(&app)), name },
        ));
    }
    games
}

#[cfg(not(windows))]
fn epic_games() -> Vec<(String, Game)> {
    Vec::new()
}

// ── The loop ─────────────────────────────────────────────────────────────

/// The games among the running processes, at most MAX_GAMES, each once.
fn running_games(system: &mut System, index: &GameIndex) -> Vec<Game> {
    system.refresh_processes_specifics(ProcessRefreshKind::new().with_exe(UpdateKind::OnlyIfNotSet));
    let running_steam = running_steam_game();
    let mut found: Vec<Game> = Vec::new();
    for process in system.processes().values() {
        if let Some(game) = index.recognise(process.name(), process.exe(), running_steam.as_deref()) {
            if !found.iter().any(|g| g.key == game.key) {
                found.push(game);
            }
        }
    }
    found.sort_by(|a, b| a.key.cmp(&b.key));
    found.truncate(MAX_GAMES);
    found
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

/// Spawned next to `poll_activity` and `lol::watch` for the same login, under
/// the same generation — so it stops on logout or token change like them.
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

    let mut server_gate: Option<ServerGate> = None;
    let mut gate_checked: Option<Instant> = None;
    let mut last_mode: Option<&'static str> = None;
    // Built on first need and dropped when counting stops, so an idle app
    // holds neither the process table nor the index.
    let mut system: Option<System> = None;
    let mut index: Option<(GameIndex, Instant)> = None;
    let mut last_sent: Vec<String> = Vec::new();

    loop {
        if !still_current(&generation, my_generation) {
            return;
        }

        if !counting_enabled(&app) {
            if system.take().is_some() {
                eprintln!("[lpm] gametime: counting turned off in settings");
            }
            index = None;
            last_mode = None;
            if !nap(IDLE_POLL, &generation, my_generation).await {
                return;
            }
            continue;
        }

        let due = match gate_checked {
            None => true,
            Some(at) => at.elapsed() >= if server_gate.is_some() { GATE_RECHECK } else { GATE_RETRY },
        };
        if due {
            server_gate = gate(&http, &base, &token).await;
            gate_checked = Some(Instant::now());
        }
        let (active, why) = counting_mode(server_gate, outside_lan_allowed(&app));
        if last_mode != Some(why) {
            eprintln!("[lpm] gametime: counting {why}");
            last_mode = Some(why);
        }

        if !active {
            system = None;
            index = None;
            if !nap(IDLE_POLL, &generation, my_generation).await {
                return;
            }
            continue;
        }

        let stale = index.as_ref().is_none_or(|(_, at)| at.elapsed() >= INDEX_REFRESH);
        if stale {
            match served_list(&http, &base, &token).await {
                Some(list) => {
                    let built = build_index(&list);
                    eprintln!(
                        "[lpm] gametime: {} known executables, {} installed games found",
                        built.by_exe.len(),
                        built.folders.len()
                    );
                    index = Some((built, Instant::now()));
                }
                // Keep the old index if there is one; retry on the next tick.
                None if index.is_none() => {
                    if !nap(GATE_RETRY, &generation, my_generation).await {
                        return;
                    }
                    continue;
                }
                None => {}
            }
        }

        let system = system.get_or_insert_with(System::new);
        let games = index.as_ref().map(|(idx, _)| running_games(system, idx)).unwrap_or_default();
        let keys: Vec<String> = games.iter().map(|g| g.key.clone()).collect();
        if keys != last_sent {
            let names: Vec<&str> = games.iter().map(|g| g.name.as_str()).collect();
            eprintln!("[lpm] gametime: playing {names:?}");
        }
        if !games.is_empty() {
            let body = json!({
                "games": games.iter().map(|g| json!({ "key": g.key, "name": g.name })).collect::<Vec<_>>(),
                "visible": visible(&app),
            });
            match http.post(format!("{base}/api/gametime/heartbeat")).bearer_auth(&token).json(&body).send().await {
                Err(e) => eprintln!("[lpm] gametime: heartbeat failed: {e}"),
                Ok(resp) if resp.status() == reqwest::StatusCode::NOT_FOUND => {
                    // The feature was switched off since the last check.
                    gate_checked = None;
                }
                Ok(resp) if !resp.status().is_success() => {
                    let status = resp.status();
                    let detail = resp.text().await.unwrap_or_default();
                    eprintln!("[lpm] gametime: heartbeat refused ({status}): {detail}");
                }
                Ok(_) => {}
            }
        }
        last_sent = keys;

        if !nap(TICK, &generation, my_generation).await {
            return;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn index() -> GameIndex {
        build_index(&json!({
            "games": [{ "key": "exe:cs2", "name": "Counter-Strike 2", "exes": ["cs2.exe"] }],
            "ignore_exes": ["UnityCrashHandler64.exe"],
            "ignore_steam_apps": [],
        }))
    }

    #[test]
    fn served_executables_match_whatever_the_case() {
        let idx = index();
        assert_eq!(idx.recognise("CS2.EXE", None, None).map(|g| g.key), Some("exe:cs2".into()));
        assert_eq!(idx.recognise("notepad.exe", None, None), None);
    }

    #[test]
    fn a_process_inside_an_install_folder_is_that_game() {
        let mut idx = index();
        idx.folders.push((
            folder_entry(Path::new(r"D:\SteamLibrary\steamapps\common\V Rising")),
            Game { key: "steam:1604030".into(), name: "V Rising".into() },
        ));
        let exe = Path::new(r"D:\SteamLibrary\steamapps\common\V Rising\VRising.exe");
        assert_eq!(idx.recognise("VRising.exe", Some(exe), None).map(|g| g.name), Some("V Rising".into()));
        // A sibling folder whose name starts the same is another game.
        let other = Path::new(r"D:\SteamLibrary\steamapps\common\V Rising Dedicated Server\x.exe");
        assert_eq!(idx.recognise("x.exe", Some(other), None), None);
    }

    #[test]
    fn ignored_executables_never_count() {
        let mut idx = index();
        idx.folders.push((folder_entry(Path::new(r"C:\Games\G")), Game { key: "steam:1".into(), name: "G".into() }));
        assert_eq!(idx.recognise("UnityCrashHandler64.exe", Some(Path::new(r"C:\Games\G\UnityCrashHandler64.exe")), None), None);
    }

    #[test]
    fn a_shared_folder_is_the_running_game_or_the_base_game() {
        let mut idx = index();
        let hl2 = folder_entry(Path::new(r"D:\Steam\steamapps\common\Half-Life 2"));
        for (id, name) in [(380, "Episode One"), (220, "Half-Life 2"), (420, "Episode Two")] {
            idx.folders.push((hl2.clone(), Game { key: format!("steam:{id}"), name: name.into() }));
        }
        sort_folders(&mut idx.folders);
        let exe = Path::new(r"D:\Steam\steamapps\common\Half-Life 2\hl2.exe");
        assert_eq!(idx.recognise("hl2.exe", Some(exe), None).map(|g| g.key), Some("steam:220".into()));
        assert_eq!(idx.recognise("hl2.exe", Some(exe), Some("steam:420")).map(|g| g.key), Some("steam:420".into()));
        // Steam running a game from another folder doesn't change this one's.
        assert_eq!(idx.recognise("hl2.exe", Some(exe), Some("steam:730")).map(|g| g.key), Some("steam:220".into()));
    }

    #[test]
    fn vdf_pairs_read_paths_and_manifests() {
        let library = "\"libraryfolders\"\n{\n\t\"1\"\n\t{\n\t\t\"path\"\t\t\"D:\\\\SteamLibrary\"\n\t}\n}\n";
        assert_eq!(vdf_pairs(library), vec![("path".to_string(), r"D:\SteamLibrary".to_string())]);
        let manifest = "\"AppState\"\n{\n\t\"appid\"\t\t\"730\"\n\t\"name\"\t\t\"Counter-Strike 2\"\n\t\"installdir\"\t\t\"Counter-Strike Global Offensive\"\n}\n";
        let pairs: HashMap<_, _> = vdf_pairs(manifest).into_iter().collect();
        assert_eq!(pairs["appid"], "730");
        assert_eq!(pairs["installdir"], "Counter-Strike Global Offensive");
    }

    #[test]
    fn launcher_ids_fit_the_server_key_rule() {
        assert_eq!(key_part("Fortnite"), "fortnite");
        assert_eq!(key_part("a b/c:d"), "a-b-c-d");
        assert!(key_part(&"x".repeat(100)).len() <= 56);
    }

    /// Not a check: what this machine's launchers and processes give, to look
    /// at by hand (`cargo test gametime -- --ignored --nocapture`).
    #[test]
    #[ignore]
    fn print_this_machines_games() {
        let idx = build_index(&json!({ "games": [], "ignore_exes": [], "ignore_steam_apps": [228980, 250820, 431960] }));
        for (folder, game) in &idx.folders {
            println!("{:<20} {:<40} {folder}", game.key, game.name);
        }
        println!("running now: {:?}", running_games(&mut System::new(), &idx));
    }

    #[test]
    fn counting_follows_the_gate_and_the_outside_lan_box() {
        let on = |lan| Some(ServerGate { enabled: true, lan_in_progress: lan });
        assert!(counting_mode(on(true), false).0);
        assert!(!counting_mode(on(false), false).0);
        assert!(counting_mode(on(false), true).0);
        assert!(!counting_mode(Some(ServerGate { enabled: false, lan_in_progress: true }), true).0);
        assert!(!counting_mode(None, true).0);
    }
}
