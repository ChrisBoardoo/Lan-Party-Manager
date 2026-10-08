export interface User {
  id: number
  username: string
  email?: string  // omitted by the API for non-self/non-admin viewers (privacy)
  role: 'admin' | 'treasurer' | 'user'
  avatar_url: string | null
  phone?: string | null  // optional contact for settling shared costs; self/admin only
  clothing_size: string | null
  is_meal_prep_volunteer: boolean
  is_tournament_organizer: boolean
  profile_complete: boolean
  is_active: boolean
  deleted_at?: string | null  // set by admin full-deletion; distinct from is_active — see backend/router_users.py
  created_at: string
  discord_username?: string | null  // set when a Discord account is linked (self/admin only)
  steam_username?: string | null  // set when a Steam account is linked (self/admin only) — link-only, see md/2.features/Steam_Link.md
  riot_id?: string | null  // "GameName#TAG", typed on the profile (self/admin only) — see backend/riot_id.py
  has_password?: boolean  // false for Discord-only accounts; gates the unlink action
  last_seen?: string | null  // last presence heartbeat (server UTC)
  is_online?: boolean  // computed server-side: heartbeat within the online window
}

// One row of the admin-only deleted-accounts history (Settings). Not a User —
// a deleted row's own username/email are scrubbed, so this surfaces
// deleted_username (captured before scrubbing) instead. See backend/schemas.py.
export interface DeletedUser {
  id: number
  deleted_username: string | null
  deleted_at: string
}

export interface Expense {
  id: number
  description: string
  amount: number
  category: string
  date: string
  created_by: number
  paid_by?: number | null
  event_id: number | null
  created_at: string
  creator: User
  payer?: User | null
}

export interface TeamMember {
  id: number
  player_name: string
  user_id: number | null
}

export interface Team {
  id: number
  team_name: string
  score: number
  color: string | null
  seed: number | null
  members: TeamMember[]
}

export interface Match {
  id: number
  round: string
  round_number: number
  match_number: number
  team_a_id: number | null
  team_b_id: number | null
  score_a: number
  score_b: number
  winner_id: number | null
  status: 'pending' | 'in_progress' | 'completed'
  team_a: Team | null
  team_b: Team | null
  reported_score_a: number | null   // pending self-service report (null = none)
  reported_score_b: number | null
  reported_by: number | null
}

export interface Tournament {
  id: number
  game_name: string
  /** Shared-catalog game; null for a legacy tournament not yet attached. */
  game_id: number | null
  bracket_type: string
  event_type: 'team' | 'individual'
  status: string
  max_team_size: number
  organizer_id: number
  event_id: number | null
  organizer: User
  teams: Team[]
  matches: Match[]
  created_at: string
}

export interface RoundRobinStanding {
  team_id: number
  team_name: string
  color: string | null
  seed: number | null
  wins: number
  losses: number
  draws: number
  points: number
  played: number
}

export interface HallOfFameEntry {
  user_id: number
  username: string
  avatar_url: string | null
  wins: number
  participations: number
}

// ── Per-game stats (derived server-side from completed matches) ──────────────

/** A catalog game for the tournament picker, with the hints it's ordered by. */
export interface TournamentGame {
  id: number
  name: string
  genre: string | null
  default_max_players: number | null
  is_custom: boolean
  tournament_count: number
  owner_count: number
  planned: boolean
}

export interface GameStatsSummary {
  game_id: number
  name: string
  genre: string | null
  tournaments: number
  matches: number
  players: number
  leader: { user_id: number; username: string; avatar_url: string | null; wins: number } | null
}

export interface PlayerGameStatsLine {
  user_id: number
  username: string
  avatar_url: string | null
  played: number
  wins: number
  losses: number
  draws: number
  /** null below 3 matches played — too few to rank on. */
  win_rate: number | null
  tournaments: number
  titles: number
}

export interface GameStatsDetail {
  game_id: number
  name: string
  genre: string | null
  tournaments: number
  matches: number
  players: PlayerGameStatsLine[]
}

export interface UserGameStatsLine {
  game_id: number
  name: string
  played: number
  wins: number
  losses: number
  draws: number
  win_rate: number | null
  tournaments: number
  titles: number
}

export interface UnlinkedTournament {
  id: number
  game_name: string
  event_id: number | null
  status: string
  created_at: string
}

export interface LanEvent {
  id: number
  title: string
  description: string | null
  location: string | null
  start_date: string
  end_date: string
  capacity: number | null
  cover_image_url: string | null
  rsvp_count: number
  my_rsvp: 'in' | 'out' | null
  my_arrival_date: string | null
  my_departure_date: string | null
  // From the event's first day: a member can't change their own stay any
  // more, only a treasurer or an admin can (it moves everyone's share).
  attendance_locked: boolean
  attendees: EventAttendee[]
  created_by: number
  created_at: string
  creator: User
}

export interface EventAttendee {
  user_id: number
  username: string
  avatar_url: string | null
  arrival_date: string | null
  departure_date: string | null
}

export interface EventInvite {
  id: number
  event_id: number
  code: string
  event_title: string
  capacity: number | null
  rsvp_count: number
  seats_left: number | null
  created_by: number
  created_at: string
}

export interface EventInviteValidation {
  valid: boolean
  full: boolean | null
  event_id: number | null
  event_title: string | null
  event_start: string | null
  event_end: string | null
}

export interface ProRataShare {
  user_id: number
  username: string
  avatar_url: string | null
  nights: number
  arrival_date?: string
  departure_date?: string
  percentage: number
  amount: number
}

export interface SettlementLine {
  from_user_id: number
  from_username: string
  to_user_id: number
  to_username: string
  to_phone?: string | null  // only present for the debtor (viewer) of this line
  amount: number
  // true = a payment the debtor recorded (amount = what was sent); false =
  // still owed. A paid line no longer counts as debt.
  paid: boolean
  payment_id?: number | null
}

export interface ProRataResult {
  total_expenses: number
  event_id: number | null
  event_title: string | null
  event_start: string | null
  event_end: string | null
  total_nights: number
  total_person_nights: number
  shares: ProRataShare[]
  settlements: SettlementLine[]
}

export interface LiveStream {
  id: number
  channel_name: string
  title: string | null
  is_active: boolean
  stream_type: 'channel' | 'clip'
  clip_slug: string | null
  created_by: number
  created_at: string
  creator: User
}

export interface LiveStatus {
  is_live: boolean
  game: string
  viewers: number
  title: string
}

export interface MediaReactionCount {
  emoji: string
  count: number
  mine: boolean
  /** Who reacted, oldest first — feeds the hover/long-press tooltip. Empty on
   *  the public recap share, where reactor names are deliberately dropped. */
  users: string[]
}

export interface MediaItem {
  id: number
  filename: string
  original_name: string
  file_type: 'image' | 'video'
  mime_type: string
  file_size: number
  url: string
  thumbnail_url: string | null
  caption: string | null
  event_id: number | null
  uploaded_by: number
  created_at: string
  uploader: User
  reactions: MediaReactionCount[]
  reaction_total: number
}

// ── Recap ─────────────────────────────────────────────────────────────────────

export interface BadgeAward {
  // A code, not a label — the strings live in i18n under badges.<code>.label/.desc
  code: string
  user_id: number
  username: string
  avatar_url: string | null
  value: number | null
}

// Crew XP — derived on read server-side (backend/xp.py). Codes, not labels:
// sources are i18n `xp.source.<code>`, titles `xp.title.<title>`.
export interface XpLine {
  code: string
  count: number
  xp: number
}

export interface XpSummary {
  user_id: number
  total: number
  level: number
  level_floor: number
  next_level_at: number
  title: string
  breakdown: XpLine[]
}

export interface XpCrewEntry {
  user_id: number
  username: string
  avatar_url: string | null
  total: number
  level: number
  title: string
}

export interface RecapChampion {
  team_name: string
  color: string | null
  members: string[]
}

export interface RecapTournament {
  tournament_id: number
  game_name: string
  bracket_type: string
  match_count: number
  champion: RecapChampion | null
}

export interface RecapMoney {
  total_expenses: number
  currency: string
  per_person_avg: number
  settled_lines: number
  total_lines: number
}

export interface Recap {
  event: {
    id: number
    title: string
    start_date: string
    end_date: string
    cover_image_url: string | null
    nights: number
  }
  attendance: {
    attendee_count: number
    total_person_nights: number
    longest_stay: number
    first_arrival: string | null
    last_departure: string | null
  }
  tournaments: RecapTournament[]
  mvp: { user_id: number; username: string; avatar_url: string | null; wins: number } | null
  media: {
    total: number
    photo_count: number
    video_count: number
    top: MediaItem[]
  }
  // null when treasury is off — and ALWAYS null on a public share link.
  money: RecapMoney | null
  badges: BadgeAward[]
  /** Revealed trophies of this edition (empty when the feature is off). */
  trophies: RecapTrophy[]
  generated_at: string
  shared: boolean
}

// ── Trophies ──────────────────────────────────────────────────────────────────
// Crew-defined honours. Name/description/citation are free text in the crew's
// own words — unlike BadgeAward, which is an i18n code.

export interface TrophyBrief {
  id: number
  name: string
  emoji: string | null
  image_url: string | null
  description: string | null
}

/** A cabinet entry (admin). */
export interface Trophy extends TrophyBrief {
  sort_order: number
  archived_at: string | null
  awarded_count: number
  last_award: { username: string; event_title: string } | null
}

export type TrophyMode = 'vote' | 'direct'
export type TrophyStatus = 'draft' | 'voting' | 'closed' | 'revealed'

export interface TrophyWinner {
  user_id: number
  username: string
  avatar_url: string | null
  citation: string | null
  /** Admins only. */
  vote_count: number | null
}

/** One trophy in play at one event. Members get no winners before the reveal
 *  and never a tally; `my_vote` is only ever the viewer's own ballot. */
export interface TrophyEdition {
  id: number
  event_id: number
  trophy: TrophyBrief
  mode: TrophyMode
  status: TrophyStatus
  revealed_at: string | null
  winners: TrophyWinner[]
  voters_count: number
  eligible_count: number
  my_vote: number | null
  tally: { user_id: number; username: string; avatar_url: string | null; votes: number }[] | null
}

export interface UserTrophy {
  edition_id: number
  trophy: TrophyBrief
  event_id: number
  event_title: string
  event_start_date: string
  citation: string | null
  revealed_at: string | null
}

export interface RecapTrophy {
  trophy: TrophyBrief
  winners: { user_id: number; username: string; avatar_url: string | null; citation: string | null }[]
}

export interface KioskTrophy {
  edition_id: number
  name: string
  emoji: string | null
  image_url: string | null
  winners: { username: string; avatar_url: string | null; citation: string | null }[]
  revealed_at: string | null
}

export interface RecapShare {
  event_id: number
  token: string | null
}

// ── My Setup ──────────────────────────────────────────────────────────────────

/** The fixed component vocabulary. These are simultaneously the UserSetup column
 *  names and the i18n keys (`setup.field.<key>`) — mirrored from SETUP_FIELDS in
 *  backend/schemas.py. Keep the two in step; the label lives in the translation
 *  bundle, never in the database. */
export const SETUP_FIELDS = [
  'motherboard', 'cpu', 'cooler', 'graphics_card', 'ram', 'power_supply',
  'fans', 'storage', 'pc_case', 'display', 'keyboard', 'mouse', 'headset', 'mic',
] as const
export type SetupFieldKey = typeof SETUP_FIELDS[number]

export const MAX_SETUP_PHOTOS = 5
export const MAX_SETUP_CUSTOM_FIELDS = 10

export type SetupComponents = Record<SetupFieldKey, string | null>

export interface SetupCustomField {
  id: number
  label: string
  value: string | null
}

export interface SetupPhoto {
  id: number
  url: string
  caption: string | null
}

export interface Setup {
  user_id: number
  username: string
  avatar_url: string | null
  components: SetupComponents
  custom_fields: SetupCustomField[]
  photos: SetupPhoto[]
  has_content: boolean
  reactions: MediaReactionCount[]
  reaction_total: number
}

/** The public view. Deliberately has no user_id, role, or presence fields —
 *  see SetupSharedOut in backend/schemas.py. */
export interface SharedSetup {
  username: string
  avatar_url: string | null
  components: SetupComponents
  custom_fields: SetupCustomField[]
  photos: SetupPhoto[]
}

export interface SetupShare {
  token: string | null
}

export interface ActivityLogEntry {
  id: number
  user_id: number
  action: string
  entity_type: string | null
  entity_id: number | null
  description: string
  created_at: string
  user: User
  /** Hydrated only when entity_type is "media" — lets the Hub feed show a
   *  thumbnail and open it in the same Lightbox as the gallery. */
  media: MediaItem | null
  reactions: MediaReactionCount[]
  reaction_total: number
}

export interface AuditLogEntry {
  id: number
  admin_id: number
  action: string
  details: string | null
  created_at: string
  admin: User
}

export interface AppSetting {
  key: string
  value: string | null
}

export interface Sponsor {
  id: number
  event_id: number
  name: string
  banner_url: string | null
  banner_type: 'image' | 'video' | null
  link_url: string | null
  sort_order: number
  created_at: string
}

export interface Prize {
  id: number
  event_id: number
  title: string
  description: string | null
  photo_url: string | null
  sort_order: number
  created_at: string
}

// ── Planning ("Calendar View") ──────────────────────────────────────────────

export interface SlotTally {
  slot_start: string   // ISO datetime, top-of-the-hour
  count: number
}

export interface ScheduleBlock {
  id: number
  event_id: number
  game: string
  proposed_start: string | null
  proposed_end: string | null
  status: 'proposed' | 'locked'
  locked_start: string | null
  locked_end: string | null
  color: string | null   // palette key chosen at lock time; null = derive from game name
  created_by: number
  created_at: string
  tallies: SlotTally[]   // approvals per hour-slot across all voters
  my_slots: string[]     // hour-slots the current user approved
}

export type PlanningScheduleView = 'list' | 'calendar'

export interface PlanningEvent {
  event_id: number
  event_start: string    // ISO date
  event_end: string      // ISO date
  can_propose: boolean   // effective toggle (event override or global default)
  can_vote: boolean
  my_arrival_date: string | null
  my_departure_date: string | null
  is_attending: boolean  // do I have an "in" RSVP? (gates voting)
  my_schedule_view: PlanningScheduleView | null   // saved account preference
  blocks: ScheduleBlock[]
}

export interface Announcement {
  id: number
  message: string
  level: 'info' | 'alert'
  event_id: number | null
  created_by: number
  created_at: string
  expires_at: string | null
}

export type ClothingSize = 'XS' | 'S' | 'M' | 'L' | 'XL' | 'XXL' | 'XXXL'

// ── Kiosk / Big Screen ─────────────────────────────────────────────────────────

export interface KioskTeamSide {
  name: string | null
  color: string | null
  score: number
}

export interface KioskMatch {
  tournament: string
  round: string
  status: 'in_progress' | 'pending'
  team_a: KioskTeamSide
  team_b: KioskTeamSide
}

export interface KioskStanding {
  rank: number
  team_name: string
  color: string | null
  wins: number
  losses: number
  draws: number
  points: number
  played: number
}

export interface KioskAttendee {
  username: string
  avatar_url: string | null
  online: boolean
}

export interface KioskChampion {
  tournament_id: number
  game_name: string
  team_name: string
  color: string | null
  members: string[]
  decided_at: string | null
}

/** One #LoveWall item. Reactions are counts only — who reacted never reaches
 *  the shared screen. `love_pick` marks the most-reacted item in scope. */
export interface KioskMedia {
  id: number
  url: string
  caption: string | null
  file_type: 'image' | 'video'
  thumbnail_url: string | null
  uploader: string | null
  uploader_avatar_url: string | null
  created_at: string | null
  reactions: { emoji: string; count: number }[]
  reaction_total: number
  love_pick: boolean
}

export interface KioskSummary {
  server_time: string
  event: {
    id: number
    title: string
    location: string | null
    start_date: string
    end_date: string
    cover_image_url: string | null
  } | null
  countdown: { label: string; target: string } | null
  matches: KioskMatch[]
  standings: KioskStanding[]
  arrivals: { expected: number; online: number; attendees: KioskAttendee[] }
  up_next: { game: string; locked_start: string; locked_end: string }[]
  media: KioskMedia[]
  media_total: number
  media_reactions_total: number
  /** Whether a post made while the display runs interrupts it with a drop. */
  live_drop: boolean
  announcements: { id: number; message: string; level: 'info' | 'alert'; created_at: string }[]
  gear: {
    pledged_count: number
    open_request_count: number
    bringing: { name: string; by: string | null }[]
    needs: string[]
  } | null
  champion: KioskChampion | null
  wifi: WifiConfig | null
  join_url: string | null
  trophies: KioskTrophy[]
}

/** Guest WiFi. `security` is the WIFI: QR payload's T: value. */
export interface WifiConfig {
  ssid: string
  password: string | null
  security: 'WPA' | 'WEP' | 'nopass'
  hidden: boolean
}

export interface KioskAdmin {
  enabled: boolean
  token: string | null
}

// ── Gear / BYO ("who's bringing what") ─────────────────────────────────────────

export interface GearItem {
  id: number
  event_id: number
  name: string
  category: string | null
  quantity: number
  note: string | null
  is_request: boolean
  pledged_by: number | null
  pledged_username: string | null
  pledged_avatar_url: string | null
  created_by: number
  created_at: string
}

export interface GearEvent {
  event_id: number
  items: GearItem[]
  pledged_count: number
  open_request_count: number
}

export interface GearSuggestion {
  name: string
  category: string | null
  quantity: number
  times_brought: number
  last_event_title: string | null
}

// ── Event checklist (private packing list) ─────────────────────────────────────
// Fixed vocabulary — these names are BOTH the ChecklistItems keys and the i18n
// keys (`checklist.field.<key>`), mirrored from CHECKLIST_FIXED_FIELDS in
// backend/schemas.py. Keep the two in step; the label lives in the translation
// bundle, never in the database.
export const CHECKLIST_FIXED_FIELDS = [
  'computer', 'screen', 'screen_psu', 'keyboard_mouse', 'cables',
  'mousepad', 'headset', 'vanity', 'backpack',
] as const
export type ChecklistFieldKey = typeof CHECKLIST_FIXED_FIELDS[number]

export const MAX_CHECKLIST_CUSTOM_FIELDS = 10

export type ChecklistItems = Record<ChecklistFieldKey, boolean>

export interface ChecklistCustomField {
  id: number
  label: string
  checked: boolean
}

export interface Checklist {
  event_id: number
  items: ChecklistItems
  custom_fields: ChecklistCustomField[]
  started: boolean
  progress_checked: number
  progress_total: number
}

export interface ChecklistSuggestion {
  source_event_id: number
  source_event_title: string
  items: ChecklistItems
  custom_fields: ChecklistCustomField[]
}

// ── Mini-games ────────────────────────────────────────────────────────────────

/** One entry of the backend registry (`minigames_registry.GAMES`), fetched rather
 *  than duplicated here — with up to 8 games planned, two catalogues that can
 *  disagree is exactly the bug to avoid. */
export interface MiniGameInfo {
  slug: string
  /** What `score` counts. Drives formatting — see formatMiniGameScore(). */
  metric: string
  max_score: number
  higher_is_better: boolean
  detail_fields: string[]
}

export interface MiniGameScore {
  id: number
  game: string
  score: number
  /** Per-game extra stats, shown beside the score but never ranked on. */
  details: Record<string, number>
  created_at: string
  user: User
}

export interface MiniGameSubmitResult {
  accepted: boolean
  personal_best: boolean
  rank: number | null
  score: MiniGameScore | null
}

// ── Games (library / wishlist / finder) ─────────────────────────────────────────

export interface Game {
  id: number
  name: string
  genre: string | null
  default_max_players: number | null
  is_custom: boolean
}

// A library/session-result row already has its effective max player count
// resolved server-side (override if the member set one, else the catalog default).
export interface GameLibraryEntry {
  game_id: number
  name: string
  genre: string | null
  max_players: number | null
  is_custom: boolean
  is_favorite: boolean  // own library only — always false on other members' rows (finder)
}

export interface GameWishlistEntry {
  game_id: number
  name: string
  genre: string | null
}

// The profile library's filter bar, saved on the account (PUT /games/me/filters).
export interface GameLibraryFilters {
  sort: 'asc' | 'desc' | null
  min_players: number | null
  max_players: number | null
  playable_only: boolean
  favorites_only: boolean
}

export interface GameMe {
  library: GameLibraryEntry[]
  wishlist: GameWishlistEntry[]
  filters: GameLibraryFilters
}

export interface GameMatch {
  user_id: number
  username: string
  avatar_url: string | null
  shared_count: number
  shared_games: GameLibraryEntry[]
}

// ── Groceries ("courses") ────────────────────────────────────────────────────

export interface GroceryItem {
  id: number
  event_id: number
  category: string | null
  name: string
  quantity: string | null
  assigned_to: number | null
  assigned_username: string | null
  assigned_avatar_url: string | null
  is_bought: boolean
  created_by: number
  created_at: string
}

export interface GroceryEvent {
  event_id: number
  items: GroceryItem[]
  bought_count: number
  total_count: number
}

export interface GroceryImportResult {
  imported: number
  unmatched_usernames: string[]
}

export interface GameSessionResult {
  games: GameLibraryEntry[]
}

// `games_visible: false` means the linked Steam account's game list is
// private — distinct from a successful import that simply found nothing new.
export interface GameImportResult {
  games_visible: boolean
  imported: number
  already_owned: number
  added_custom: number
}

// ── League of Legends stats (/api/lol — see backend/router_lol.py) ──────────
// Games captured by the members' desktop apps, during a LAN or not.

export type LolCategory = 'custom' | 'aram' | 'aram_chaos' | 'matchmade'

export interface LolPlayerLine {
  user_id: number
  username: string
  avatar_url: string | null
  games: number
  wins: number
  losses: number
  win_rate: number | null  // null below 3 games, like tournament stats
  kills: number
  deaths: number
  assists: number
  damage: number
  kda: number  // (K + A) / max(D, 1)
  avg_kills: number
  avg_deaths: number
  avg_assists: number
  avg_damage: number
}

export interface LolRecord {
  kind: 'kills' | 'assists' | 'damage'
  value: number
  user_id: number
  username: string
  avatar_url: string | null
  champion: string | null
  match_id: number
}

export interface LolStats {
  game_id: number | null  // the catalog's League of Legends row
  matches: number
  players: LolPlayerLine[]
  records: LolRecord[]
}

export interface LolMatchPlayer {
  user_id: number | null
  username: string | null  // null = a custom-game player nobody has claimed yet
  riot_id: string
  champion: string | null
  team_id: number | null
  win: boolean
  kills: number
  deaths: number
  assists: number
  damage: number
}

export interface LolMatch {
  id: number
  event_id: number | null  // null: played outside any LAN, counts in Global only
  category: LolCategory
  game_mode: string | null
  duration_s: number | null
  played_at: string
  submitted_by: string | null
  players: LolMatchPlayer[]
}

export const CLOTHING_SIZES: ClothingSize[] = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']

// ── Craving Chat (per-event pre-LAN hype chat) ──────────────────────────────

export interface ChatReaction {
  emoji: string
  count: number
  mine: boolean
}

export interface ChatMessageReplyPreview {
  id: number
  username: string
  content: string
}

export interface ChatLinkPreview {
  url: string
  title: string | null
  description: string | null
  image_url: string | null
  site_name: string | null
}

export interface ChatMessage {
  id: number
  event_id: number
  user_id: number
  username: string
  avatar_url: string | null
  is_admin: boolean
  content: string
  created_at: string
  edited_at: string | null
  is_mine: boolean
  reply_to: ChatMessageReplyPreview | null
  reactions: ChatReaction[]
  link_preview: ChatLinkPreview | null
  mentions: ChatMention[]
}

export interface ChatMention {
  user_id: number
  username: string
}

export interface PinnedMessage {
  id: number
  user_id: number
  username: string
  avatar_url: string | null
  content: string
  created_at: string
}

export const EXPENSE_CATEGORIES = [
  'general',
  'food',
  'drinks',
  'equipment',
  'accommodation',
  'transport',
  'games',
  'prizes',
]

