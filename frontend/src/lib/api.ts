import axios from 'axios'
import { notifyDesktopLogout } from './desktopBridge'
import type {
  User, DeletedUser, Expense, Tournament, Team, Match, ProRataResult, LanEvent,
  LiveStream, MediaItem, ActivityLogEntry, AuditLogEntry, AppSetting,
  RoundRobinStanding, HallOfFameEntry, LiveStatus, EventInvite, EventInviteValidation,
  TournamentGame, GameStatsSummary, GameStatsDetail, UserGameStatsLine, UnlinkedTournament,
  Sponsor, Prize, PlanningEvent, ScheduleBlock, Announcement,
  KioskSummary, KioskAdmin, GearEvent, GearItem, GearSuggestion,
  Recap, RecapShare, BadgeAward,
  Setup, SetupComponents, SetupShare, SharedSetup,
  Checklist, ChecklistItems, ChecklistSuggestion,
  MiniGameInfo, MiniGameScore, MiniGameSubmitResult,
  Game, GameMe, GameLibraryEntry, GameLibraryFilters, GameWishlistEntry, GameMatch, GameSessionResult, GameImportResult,
  GroceryEvent, GroceryItem, GroceryImportResult,
  ChatMessage, PinnedMessage, WifiConfig,
  Trophy, TrophyEdition, TrophyMode, TrophyStatus, UserTrophy,
  LolCategory, LolMatch, LolStats,
} from '../types'

const client = axios.create({ baseURL: '/api' })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const PUBLIC_PATHS = ['/login', '/register']

client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      notifyDesktopLogout()
      if (!PUBLIC_PATHS.includes(window.location.pathname)) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  register: (data: {
    username: string
    email: string
    password: string
    invite_code?: string
    arrival_date?: string
    departure_date?: string
  }) => client.post<User>('/auth/register', data).then((r) => r.data),

  login: (data: { identifier: string; password: string }) =>
    client
      .post<{ access_token: string; token_type: string; user: User }>('/auth/login', data)
      .then((r) => r.data),

  me: () => client.get<User>('/auth/me').then((r) => r.data),

  refresh: () =>
    client
      .post<{ access_token: string; token_type: string; user: User }>('/auth/refresh')
      .then((r) => r.data),

  forgotPassword: (email: string) =>
    client.post<{ detail: string }>('/auth/forgot-password', { email }).then((r) => r.data),

  resetPassword: (token: string, new_password: string) =>
    client.post<{ ok: boolean }>('/auth/reset-password', { token, new_password }).then((r) => r.data),
}

// ── Discord SSO ─────────────────────────────────────────────────────────────
export const discordApi = {
  // Public: is Discord sign-in configured/enabled?
  config: () => client.get<{ enabled: boolean }>('/auth/discord/config').then((r) => r.data),
  // Start login/registration (optional event invite code); returns the URL to redirect the browser to.
  authorize: (code?: string) =>
    client
      .get<{ authorize_url: string }>('/auth/discord/authorize', { params: code ? { code } : {} })
      .then((r) => r.data.authorize_url),
  // Start linking Discord to the current (logged-in) account.
  link: () => client.get<{ authorize_url: string }>('/auth/discord/link').then((r) => r.data.authorize_url),
  unlink: () => client.delete<{ ok: boolean }>('/auth/discord/link').then((r) => r.data),
}

// Steam is link-only — no `authorize()` here, see md/Steam_Link.md.
export const steamApi = {
  // Public: is Steam linking configured/enabled?
  config: () => client.get<{ enabled: boolean }>('/auth/steam/config').then((r) => r.data),
  // Start linking Steam to the current (logged-in) account.
  link: () => client.get<{ authorize_url: string }>('/auth/steam/link').then((r) => r.data.authorize_url),
  unlink: () => client.delete<{ ok: boolean }>('/auth/steam/link').then((r) => r.data),
}

// ── Users ─────────────────────────────────────────────────────────────────────

export const usersApi = {
  getAll: () => client.get<User[]>('/users/').then((r) => r.data),

  get: (id: number) => client.get<User>(`/users/${id}`).then((r) => r.data),

  update: (
    id: number,
    data: Partial<{
      username: string
      clothing_size: string
      phone: string
      is_meal_prep_volunteer: boolean
      is_tournament_organizer: boolean
      riot_id: string | null  // null clears it; 422 malformed, 409 taken
    }>
  ) => client.put<User>(`/users/${id}`, data).then((r) => r.data),

  uploadAvatar: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<User>(`/users/${id}/avatar`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  updateRole: (id: number, role: string) =>
    client.put<User>(`/users/${id}/role?role=${role}`).then((r) => r.data),

  rotateAvatar: (id: number) =>
    client.post<User>(`/users/${id}/avatar/rotate`).then((r) => r.data),

  deactivate: (id: number) =>
    client.put<User>(`/users/${id}/deactivate`).then((r) => r.data),

  reactivate: (id: number) =>
    client.put<User>(`/users/${id}/reactivate`).then((r) => r.data),

  // Anonymizes rather than removes the row (see backend/router_users.py) —
  // frees the username/email for the same person to register a fresh
  // account, but is otherwise permanent: there is no "undelete."
  deleteAccount: (id: number) => client.delete<User>(`/users/${id}`).then((r) => r.data),

  // Admin-only history of deleted accounts (Settings) — a deleted row never
  // appears in getAll() above, so this is the only way to see who's gone.
  getDeleted: () => client.get<DeletedUser[]>('/users/deleted').then((r) => r.data),

  resetPassword: (id: number) =>
    client.post<{ temp_password: string }>(`/users/${id}/reset-password`).then((r) => r.data),

  changePassword: (id: number, data: { current_password: string; new_password: string }) =>
    client.post<{ ok: boolean }>(`/users/${id}/change-password`, data).then((r) => r.data),

  // Gated by the recap feature — 404 for a member when it's off is a NORMAL
  // response, so callers must load this in its own effect with its own .catch,
  // never inside a page's critical Promise.all.
  badges: (id: number) => client.get<BadgeAward[]>(`/users/${id}/badges`).then((r) => r.data),

  gameStats: (id: number) => client.get<UserGameStatsLine[]>(`/users/${id}/game-stats`).then((r) => r.data),
}

// ── Expenses ──────────────────────────────────────────────────────────────────

export const expensesApi = {
  getAll: (eventId?: number) =>
    client
      .get<Expense[]>('/expenses/', { params: eventId ? { event_id: eventId } : {} })
      .then((r) => r.data),

  getProRata: (eventId?: number) =>
    client
      .get<ProRataResult>('/expenses/prorata', { params: eventId ? { event_id: eventId } : {} })
      .then((r) => r.data),

  getUnassignedCount: () =>
    client.get<{ count: number }>('/expenses/unassigned-count').then((r) => r.data.count),

  create: (data: { description: string; amount: number; category: string; date: string; event_id?: number | null; paid_by?: number | null }) =>
    client.post<Expense>('/expenses/', data).then((r) => r.data),

  update: (
    id: number,
    data: { description: string; amount: number; category: string; date: string; event_id?: number | null; paid_by?: number | null }
  ) => client.put<Expense>(`/expenses/${id}`, data).then((r) => r.data),

  delete: (id: number) => client.delete(`/expenses/${id}`).then((r) => r.data),

  markSettlement: (eventId: number, toUserId: number) =>
    client
      .post<{ ok: boolean; paid: boolean }>('/expenses/settlements/mark', {
        event_id: eventId,
        to_user_id: toUserId,
      })
      .then((r) => r.data),

  unmarkSettlement: (eventId: number, toUserId: number) =>
    client
      .delete<{ ok: boolean; paid: boolean }>('/expenses/settlements/mark', {
        data: { event_id: eventId, to_user_id: toUserId },
      })
      .then((r) => r.data),
}

// ── LAN Events ────────────────────────────────────────────────────────────────

export const eventsApi = {
  getAll: () => client.get<LanEvent[]>('/events/').then((r) => r.data),

  get: (id: number) => client.get<LanEvent>(`/events/${id}`).then((r) => r.data),

  create: (data: {
    title: string
    description?: string
    location?: string
    start_date: string
    end_date: string
    capacity?: number
  }) => client.post<LanEvent>('/events/', data).then((r) => r.data),

  update: (
    id: number,
    data: Partial<{
      title: string
      description: string
      location: string
      start_date: string
      end_date: string
      capacity: number | null
    }>
  ) => client.put<LanEvent>(`/events/${id}`, data).then((r) => r.data),

  delete: (id: number) => client.delete(`/events/${id}`).then((r) => r.data),

  rsvpIn: (id: number, dates: { arrival_date: string; departure_date: string }) =>
    client.post(`/events/${id}/rsvp`, dates).then((r) => r.data),
  rsvpOut: (id: number) => client.delete(`/events/${id}/rsvp`).then((r) => r.data),

  uploadCover: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<LanEvent>(`/events/${id}/cover`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  rotateCover: (id: number) =>
    client.post<LanEvent>(`/events/${id}/cover/rotate`).then((r) => r.data),
}

// ── Event Invite Codes ────────────────────────────────────────────────────────

export const eventInvitesApi = {
  get: (eventId: number) =>
    client.get<EventInvite | null>(`/events/${eventId}/invite`).then((r) => r.data),

  create: (eventId: number) =>
    client.post<EventInvite>(`/events/${eventId}/invite`).then((r) => r.data),

  revoke: (eventId: number) =>
    client.delete(`/events/${eventId}/invite`).then((r) => r.data),

  validate: (code: string) =>
    client.get<EventInviteValidation>(`/events/invite/validate/${code}`).then((r) => r.data),
}

// ── Streams ───────────────────────────────────────────────────────────────────

export const streamsApi = {
  getAll: () => client.get<LiveStream[]>('/streams/').then((r) => r.data),

  create: (data: { channel_name: string; title?: string; is_active?: boolean }) =>
    client.post<LiveStream>('/streams/', data).then((r) => r.data),

  update: (id: number, data: { channel_name?: string; title?: string; is_active?: boolean }) =>
    client.put<LiveStream>(`/streams/${id}`, data).then((r) => r.data),

  delete: (id: number) => client.delete(`/streams/${id}`).then((r) => r.data),

  getLiveStatus: () =>
    client.get<Record<string, LiveStatus>>('/streams/live-status').then((r) => r.data),
}

// ── Media ─────────────────────────────────────────────────────────────────────

export const mediaApi = {
  getAll: (eventId?: number) => {
    const params = eventId != null ? `?event_id=${eventId}` : ''
    return client.get<MediaItem[]>(`/media/${params}`).then((r) => r.data)
  },

  upload: (file: File, caption?: string, eventId?: number) => {
    const form = new FormData()
    form.append('file', file)
    if (caption) form.append('caption', caption)
    if (eventId != null) form.append('event_id', String(eventId))
    return client
      .post<MediaItem>('/media/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  delete: (id: number) => client.delete(`/media/${id}`).then((r) => r.data),

  bulkDelete: (ids: number[]) =>
    client.post('/media/bulk-delete', { ids }).then((r) => r.data),

  // Toggle: the same emoji again removes your reaction. Returns the updated item.
  react: (id: number, emoji: string) =>
    client.post<MediaItem>(`/media/${id}/react`, { emoji }).then((r) => r.data),

  update: (id: number, data: { caption?: string | null; event_id?: number | null }) =>
    client.patch<MediaItem>(`/media/${id}`, data).then((r) => r.data),

  best: (eventId?: number, limit?: number) => {
    const params = new URLSearchParams()
    if (eventId != null) params.set('event_id', String(eventId))
    if (limit != null) params.set('limit', String(limit))
    const qs = params.toString()
    return client.get<MediaItem[]>(`/media/best${qs ? `?${qs}` : ''}`).then((r) => r.data)
  },
}

// ── Recap ─────────────────────────────────────────────────────────────────────

export const recapApi = {
  get: (eventId: number) => client.get<Recap>(`/recap/${eventId}`).then((r) => r.data),

  // The public share view has no user session — it authorizes with the share
  // token via a plain fetch, deliberately bypassing the axios client so a bad
  // token can't wipe an admin's session or bounce them to /login. Header, not a
  // query param, so the token stays out of access logs and browser history.
  getShared: (token: string): Promise<Recap> =>
    fetch('/api/recap/shared', { headers: { 'X-Recap-Token': token } }).then((r) => {
      if (!r.ok) throw new Error(`shared recap ${r.status}`)
      return r.json()
    }),

  getShare: (eventId: number) =>
    client.get<RecapShare>(`/recap/${eventId}/share`).then((r) => r.data),
  mintShare: (eventId: number) =>
    client.post<RecapShare>(`/recap/${eventId}/share`).then((r) => r.data),
  revokeShare: (eventId: number) =>
    client.delete<RecapShare>(`/recap/${eventId}/share`).then((r) => r.data),
}

// ── My Setup ──────────────────────────────────────────────────────────────────

export const setupApi = {
  getMine: () => client.get<Setup>('/setup/me').then((r) => r.data),

  updateMine: (data: {
    components: Partial<SetupComponents>
    custom_fields: { label: string; value: string | null }[]
  }) => client.put<Setup>('/setup/me', data).then((r) => r.data),

  // Another member's setup, in-app. Feature-gated, so a 404 while the feature is
  // off is a NORMAL response — load it in its own effect with its own .catch.
  get: (userId: number) => client.get<Setup>(`/setup/${userId}`).then((r) => r.data),

  // Toggle: the same emoji again removes your reaction. Returns the updated setup.
  react: (userId: number, emoji: string) =>
    client.post<Setup>(`/setup/${userId}/react`, { emoji }).then((r) => r.data),

  uploadPhoto: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<Setup>('/setup/me/photos', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  captionPhoto: (photoId: number, caption: string | null) =>
    client.patch<Setup>(`/setup/me/photos/${photoId}`, { caption }).then((r) => r.data),

  deletePhoto: (photoId: number) =>
    client.delete<Setup>(`/setup/me/photos/${photoId}`).then((r) => r.data),

  // Raw fetch, deliberately bypassing the axios client: its 401 interceptor
  // wipes localStorage and hard-redirects to /login. The whole point of My Setup
  // is showing your PC off, so the owner WILL paste their own share link into
  // their own logged-in browser — a stale token there must not log them out of
  // their own app. Header, not a query param: logs, history, Referer.
  getShared: (token: string): Promise<SharedSetup> =>
    fetch('/api/setup/shared', { headers: { 'X-Setup-Token': token } }).then((r) => {
      if (!r.ok) throw new Error(`shared setup ${r.status}`)
      return r.json()
    }),

  getShare: () => client.get<SetupShare>('/setup/me/share').then((r) => r.data),
  mintShare: () => client.post<SetupShare>('/setup/me/share').then((r) => r.data),
  revokeShare: () => client.delete<SetupShare>('/setup/me/share').then((r) => r.data),
}

// ── Tournaments ───────────────────────────────────────────────────────────────

export const tournamentsApi = {
  getAll: (eventId?: number) =>
    client
      .get<Tournament[]>('/tournaments/', { params: eventId ? { event_id: eventId } : {} })
      .then((r) => r.data),

  get: (id: number) => client.get<Tournament>(`/tournaments/${id}`).then((r) => r.data),

  create: (data: { game_name: string; game_id?: number; bracket_type: string; event_type: string; max_team_size: number; event_id?: number | null }) =>
    client.post<Tournament>('/tournaments/', data).then((r) => r.data),

  update: (id: number, data: { game_name?: string; game_id?: number; status?: string }) =>
    client.put<Tournament>(`/tournaments/${id}`, data).then((r) => r.data),

  // Catalog for the game picker, best candidates first (played, owned, planned).
  games: (eventId?: number) =>
    client
      .get<TournamentGame[]>('/tournaments/games', { params: eventId ? { event_id: eventId } : {} })
      .then((r) => r.data),

  statsOverview: (eventId?: number) =>
    client
      .get<GameStatsSummary[]>('/tournaments/stats/games', { params: eventId ? { event_id: eventId } : {} })
      .then((r) => r.data),

  statsDetail: (gameId: number, eventId?: number) =>
    client
      .get<GameStatsDetail>(`/tournaments/stats/games/${gameId}`, { params: eventId ? { event_id: eventId } : {} })
      .then((r) => r.data),

  // Admin: legacy tournaments the catalog backfill couldn't match.
  unlinked: () => client.get<UnlinkedTournament[]>('/tournaments/stats/unlinked').then((r) => r.data),

  delete: (id: number) => client.delete(`/tournaments/${id}`).then((r) => r.data),

  addTeam: (
    tid: number,
    data: { team_name: string; color?: string; seed?: number; members: { player_name: string; user_id?: number }[] }
  ) => client.post<Team>(`/tournaments/${tid}/teams`, data).then((r) => r.data),

  updateTeam: (
    tid: number,
    teamId: number,
    data: { team_name: string; color?: string; seed?: number; members: { player_name: string; user_id?: number }[] }
  ) => client.put<Team>(`/tournaments/${tid}/teams/${teamId}`, data).then((r) => r.data),

  deleteTeam: (tid: number, teamId: number) =>
    client.delete(`/tournaments/${tid}/teams/${teamId}`).then((r) => r.data),

  generateBrackets: (tid: number) =>
    client.post(`/tournaments/${tid}/generate-brackets`).then((r) => r.data),

  updateMatch: (
    tid: number,
    matchId: number,
    data: { score_a?: number; score_b?: number; status?: string; winner_id?: number }
  ) => client.put<Match>(`/tournaments/${tid}/matches/${matchId}`, data).then((r) => r.data),

  // Self-service score reporting: a participant reports, the organizer confirms.
  reportMatch: (tid: number, matchId: number, data: { score_a: number; score_b: number }) =>
    client.post<Match>(`/tournaments/${tid}/matches/${matchId}/report`, data).then((r) => r.data),

  confirmMatch: (tid: number, matchId: number) =>
    client.post<Match>(`/tournaments/${tid}/matches/${matchId}/confirm`).then((r) => r.data),

  rejectReport: (tid: number, matchId: number) =>
    client.delete<Match>(`/tournaments/${tid}/matches/${matchId}/report`).then((r) => r.data),

  getStandings: (tid: number) =>
    client.get<RoundRobinStanding[]>(`/tournaments/${tid}/standings`).then((r) => r.data),

  getHallOfFame: () =>
    client.get<HallOfFameEntry[]>('/tournaments/hall-of-fame').then((r) => r.data),
}

// ── Settings ──────────────────────────────────────────────────────────────────

export const settingsApi = {
  getAll: () => client.get<AppSetting[]>('/settings/').then((r) => r.data),

  update: (key: string, value: string | null) =>
    client.put<AppSetting>(`/settings/${key}`, { value }).then((r) => r.data),

  getDiscordInvite: () =>
    client.get<{ discord_invite_url: string | null }>('/settings/discord-invite').then((r) => r.data),

  getPublicConfig: () =>
    client
      .get<{
        currency: string
        treasury_enabled: boolean
        sponsors_enabled: boolean
        prizes_enabled: boolean
        planning_enabled: boolean
        planning_default_can_propose: boolean
        planning_default_can_vote: boolean
        gear_enabled: boolean
        groceries_enabled: boolean
        recap_enabled: boolean
        setup_enabled: boolean
        streams_enabled: boolean
        checklist_enabled: boolean
        merch_size_enabled: boolean
        minigames_enabled: boolean
        games_enabled: boolean
        craving_chat_enabled: boolean
        trophies_enabled: boolean
        lol_stats_enabled: boolean
      }>('/settings/public-config')
      .then((r) => r.data),

  // Admins, and members with an "in" RSVP to the current event (404 otherwise).
  // null when no SSID is configured.
  getWifi: () =>
    client
      .get<(WifiConfig & { event_id: number | null }) | null>('/settings/wifi')
      .then((r) => r.data),

  testDiscord: (type: 'announcement' | 'reminder') =>
    client.post<{ ok: boolean }>('/settings/discord-test', { type }).then((r) => r.data),
}

// ── Sponsors ──────────────────────────────────────────────────────────────────

export const sponsorsApi = {
  getForEvent: (eventId: number) =>
    client.get<Sponsor[]>(`/sponsors/?event_id=${eventId}`).then((r) => r.data),

  getActive: () => client.get<Sponsor[]>('/sponsors/active').then((r) => r.data),

  create: (data: { event_id: number; name: string; link_url?: string | null }) =>
    client.post<Sponsor>('/sponsors/', data).then((r) => r.data),

  uploadBanner: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<Sponsor>(`/sponsors/${id}/banner`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  update: (id: number, data: { name?: string; link_url?: string | null; sort_order?: number }) =>
    client.put<Sponsor>(`/sponsors/${id}`, data).then((r) => r.data),

  delete: (id: number) => client.delete(`/sponsors/${id}`).then((r) => r.data),
}

// ── Trophies ──────────────────────────────────────────────────────────────────

export const trophiesApi = {
  // Cabinet (admin)
  list: () => client.get<Trophy[]>('/trophies/').then((r) => r.data),

  create: (data: { name: string; emoji?: string | null; description?: string | null }) =>
    client.post<Trophy>('/trophies/', data).then((r) => r.data),

  update: (id: number, data: { name?: string; emoji?: string | null; description?: string | null; archived?: boolean }) =>
    client.put<Trophy>(`/trophies/${id}`, data).then((r) => r.data),

  remove: (id: number) => client.delete(`/trophies/${id}`).then((r) => r.data),

  uploadImage: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<Trophy>(`/trophies/${id}/image`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data)
  },

  removeImage: (id: number) => client.delete<Trophy>(`/trophies/${id}/image`).then((r) => r.data),

  // Editions (an event's trophies)
  editions: (eventId: number) =>
    client.get<TrophyEdition[]>(`/trophies/events/${eventId}`).then((r) => r.data),

  addEdition: (eventId: number, data: { trophy_id: number; mode: TrophyMode }) =>
    client.post<TrophyEdition>(`/trophies/events/${eventId}`, data).then((r) => r.data),

  updateEdition: (id: number, data: { status?: Exclude<TrophyStatus, 'revealed'>; mode?: TrophyMode }) =>
    client.patch<TrophyEdition>(`/trophies/editions/${id}`, data).then((r) => r.data),

  deleteEdition: (id: number) => client.delete(`/trophies/editions/${id}`).then((r) => r.data),

  setWinners: (id: number, winners: { user_id: number; citation?: string | null }[]) =>
    client.put<TrophyEdition>(`/trophies/editions/${id}/winners`, { winners }).then((r) => r.data),

  vote: (id: number, nomineeId: number) =>
    client.post<TrophyEdition>(`/trophies/editions/${id}/vote`, { nominee_id: nomineeId }).then((r) => r.data),

  reveal: (id: number, postToDiscord: boolean) =>
    client.post<TrophyEdition>(`/trophies/editions/${id}/reveal`, { post_to_discord: postToDiscord }).then((r) => r.data),

  // A member's showcase
  forUser: (userId: number) => client.get<UserTrophy[]>(`/trophies/users/${userId}`).then((r) => r.data),
}

// ── Prizes ────────────────────────────────────────────────────────────────────

export const prizesApi = {
  getForEvent: (eventId: number) =>
    client.get<Prize[]>(`/prizes/?event_id=${eventId}`).then((r) => r.data),

  create: (data: { event_id: number; title: string; description?: string | null }) =>
    client.post<Prize>('/prizes/', data).then((r) => r.data),

  uploadPhoto: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<Prize>(`/prizes/${id}/photo`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  update: (id: number, data: { title?: string; description?: string | null; sort_order?: number }) =>
    client.put<Prize>(`/prizes/${id}`, data).then((r) => r.data),

  delete: (id: number) => client.delete(`/prizes/${id}`).then((r) => r.data),
}

// ── Planning ("Calendar View") ──────────────────────────────────────────────

export const planningApi = {
  getEvent: (eventId: number) =>
    client.get<PlanningEvent>(`/planning/events/${eventId}`).then((r) => r.data),

  proposeBlock: (eventId: number, data: { game: string; proposed_start?: string; proposed_end?: string }) =>
    client.post<ScheduleBlock>(`/planning/events/${eventId}/blocks`, data).then((r) => r.data),

  deleteBlock: (blockId: number) =>
    client.delete(`/planning/blocks/${blockId}`).then((r) => r.data),

  setVotes: (blockId: number, slots: string[]) =>
    client.put<ScheduleBlock>(`/planning/blocks/${blockId}/votes`, { slots }).then((r) => r.data),

  lockBlock: (blockId: number, data: { locked_start: string; locked_end: string; color?: string | null }) =>
    client.post<ScheduleBlock>(`/planning/blocks/${blockId}/lock`, data).then((r) => r.data),

  unlockBlock: (blockId: number) =>
    client.post<ScheduleBlock>(`/planning/blocks/${blockId}/unlock`).then((r) => r.data),

  setViewPreference: (view: 'list' | 'calendar') =>
    client.patch('/planning/view-preference', { view }).then((r) => r.data),
}

// ── Presence ──────────────────────────────────────────────────────────────────

export const presenceApi = {
  ping: () => client.post<{ ok: boolean }>('/presence/ping').then((r) => r.data),
}

// ── Announcements / PA ────────────────────────────────────────────────────────

export const announcementsApi = {
  getActive: () => client.get<Announcement[]>('/announcements/').then((r) => r.data),

  create: (data: { message: string; level?: 'info' | 'alert'; expires_at?: string; post_to_discord?: boolean }) =>
    client.post<Announcement>('/announcements/', data).then((r) => r.data),

  delete: (id: number) => client.delete(`/announcements/${id}`).then((r) => r.data),
}

// ── Kiosk / Big Screen ──────────────────────────────────────────────────────

export const kioskApi = {
  // The projector display has no user session — it authorizes with the kiosk
  // token as a query param via a plain fetch, deliberately bypassing the axios
  // client so a bad token can't wipe an admin's session or redirect to /login.
  getSummary: (token: string): Promise<KioskSummary> =>
    // Send the token as a header, not a query param, so it doesn't get written
    // into server access logs / browser history on every poll.
    fetch('/api/kiosk/summary', { headers: { 'X-Kiosk-Token': token } }).then((r) => {
      if (!r.ok) throw new Error(`kiosk summary ${r.status}`)
      return r.json()
    }),

  // Admin-only token management (uses the authenticated client).
  getAdmin: () => client.get<KioskAdmin>('/kiosk/admin').then((r) => r.data),
  mintToken: () => client.post<KioskAdmin>('/kiosk/admin/token').then((r) => r.data),
  revokeToken: () => client.delete<KioskAdmin>('/kiosk/admin/token').then((r) => r.data),
}

// ── Gear / BYO ("who's bringing what") ────────────────────────────────────────

export const gearApi = {
  getForEvent: (eventId: number) =>
    client.get<GearEvent>(`/gear/events/${eventId}`).then((r) => r.data),

  pledge: (eventId: number, data: { name: string; category?: string | null; quantity?: number; note?: string | null }) =>
    client.post<GearItem>(`/gear/events/${eventId}/items`, data).then((r) => r.data),

  request: (eventId: number, data: { name: string; category?: string | null; quantity?: number; note?: string | null }) =>
    client.post<GearItem>(`/gear/events/${eventId}/requests`, data).then((r) => r.data),

  carryover: (eventId: number, items: { name: string; category?: string | null; quantity?: number }[]) =>
    client.post<GearEvent>(`/gear/events/${eventId}/carryover`, { items }).then((r) => r.data),

  suggestions: () => client.get<GearSuggestion[]>('/gear/suggestions').then((r) => r.data),

  claim: (itemId: number) => client.post<GearItem>(`/gear/items/${itemId}/claim`).then((r) => r.data),
  unclaim: (itemId: number) => client.post<GearItem>(`/gear/items/${itemId}/unclaim`).then((r) => r.data),
  update: (itemId: number, data: { name?: string; category?: string | null; quantity?: number; note?: string | null }) =>
    client.put<GearItem>(`/gear/items/${itemId}`, data).then((r) => r.data),
  delete: (itemId: number) => client.delete(`/gear/items/${itemId}`).then((r) => r.data),
}

// ── Groceries / courses ────────────────────────────────────────────────────────

export const groceriesApi = {
  getForEvent: (eventId: number) =>
    client.get<GroceryEvent>(`/groceries/events/${eventId}`).then((r) => r.data),

  add: (eventId: number, data: { category?: string | null; name: string; quantity?: string | null; assigned_to?: number | null }) =>
    client.post<GroceryItem>(`/groceries/events/${eventId}/items`, data).then((r) => r.data),

  update: (itemId: number, data: { category?: string | null; name?: string; quantity?: string | null; assigned_to?: number | null; is_bought?: boolean }) =>
    client.put<GroceryItem>(`/groceries/items/${itemId}`, data).then((r) => r.data),

  delete: (itemId: number) => client.delete(`/groceries/items/${itemId}`).then((r) => r.data),

  import: (eventId: number, items: { category?: string | null; name: string; quantity?: string | null; assigned_username?: string | null; is_bought?: boolean }[]) =>
    client.post<GroceryImportResult>(`/groceries/events/${eventId}/import`, { items }).then((r) => r.data),
}

export const gamesApi = {
  catalog: () => client.get<Game[]>('/games/catalog').then((r) => r.data),
  getMe: () => client.get<GameMe>('/games/me').then((r) => r.data),

  addToLibrary: (data: { name: string; max_players_override?: number | null }) =>
    client.post<GameLibraryEntry>('/games/me/library', data).then((r) => r.data),
  updateLibraryEntry: (gameId: number, data: { max_players_override: number | null }) =>
    client.put<GameLibraryEntry>(`/games/me/library/${gameId}`, data).then((r) => r.data),
  removeFromLibrary: (gameId: number) =>
    client.delete(`/games/me/library/${gameId}`).then((r) => r.data),
  setFavorite: (gameId: number, isFavorite: boolean) =>
    client.put<GameLibraryEntry>(`/games/me/library/${gameId}/favorite`, { is_favorite: isFavorite })
      .then((r) => r.data),
  saveFilters: (filters: GameLibraryFilters) =>
    client.put<GameLibraryFilters>('/games/me/filters', filters).then((r) => r.data),

  addToWishlist: (data: { name: string }) =>
    client.post<GameWishlistEntry>('/games/me/wishlist', data).then((r) => r.data),
  removeFromWishlist: (gameId: number) =>
    client.delete(`/games/me/wishlist/${gameId}`).then((r) => r.data),

  matches: () => client.get<GameMatch[]>('/games/matches').then((r) => r.data),
  session: (userIds: number[], minPlayers?: number) =>
    client.post<GameSessionResult>('/games/session', { user_ids: userIds, min_players: minPlayers ?? null })
      .then((r) => r.data),

  importSteam: () => client.post<GameImportResult>('/games/me/import-steam').then((r) => r.data),
}

// ── League of Legends LAN stats (games captured by the desktop app) ───────────

export const lolApi = {
  stats: (eventId?: number, category?: LolCategory) =>
    client
      .get<LolStats>('/lol/stats', {
        params: { ...(eventId ? { event_id: eventId } : {}), ...(category ? { category } : {}) },
      })
      .then((r) => r.data),
  matches: (eventId?: number) =>
    client.get<LolMatch[]>('/lol/matches', { params: eventId ? { event_id: eventId } : {} }).then((r) => r.data),
  // Admin only.
  deleteMatch: (matchId: number) => client.delete(`/lol/matches/${matchId}`).then((r) => r.data),
}

// ── Checklist (private per-event packing list) ─────────────────────────────────

export const checklistApi = {
  getForEvent: (eventId: number) =>
    client.get<Checklist>(`/checklist/events/${eventId}`).then((r) => r.data),

  save: (eventId: number, data: { items: Partial<ChecklistItems>; custom_fields: { label: string; checked?: boolean }[] }) =>
    client.put<Checklist>(`/checklist/events/${eventId}`, data).then((r) => r.data),

  suggestions: () => client.get<ChecklistSuggestion | null>('/checklist/suggestions').then((r) => r.data),

  carryover: (eventId: number) =>
    client.post<Checklist>(`/checklist/events/${eventId}/carryover`).then((r) => r.data),
}

// ── Craving Chat (per-event pre-LAN hype chat) ───────────────────────────────

export const chatApi = {
  getMessages: (eventId: number) =>
    client.get<ChatMessage[]>(`/chat/${eventId}/messages`).then((r) => r.data),

  postMessage: (eventId: number, content: string, replyToId?: number | null) =>
    client
      .post<ChatMessage>(`/chat/${eventId}/messages`, { content, reply_to_id: replyToId ?? null })
      .then((r) => r.data),

  editMessage: (eventId: number, messageId: number, content: string) =>
    client.patch<ChatMessage>(`/chat/${eventId}/messages/${messageId}`, { content }).then((r) => r.data),

  react: (eventId: number, messageId: number, emoji: string) =>
    client.post<ChatMessage>(`/chat/${eventId}/messages/${messageId}/react`, { emoji }).then((r) => r.data),

  deleteMessage: (eventId: number, messageId: number) =>
    client.delete(`/chat/${eventId}/messages/${messageId}`).then((r) => r.data),

  getPinned: (eventId: number) =>
    client.get<PinnedMessage | null>(`/chat/${eventId}/pinned`).then((r) => r.data),

  pin: (eventId: number, messageId: number) =>
    client.post<PinnedMessage>(`/chat/${eventId}/pin/${messageId}`).then((r) => r.data),

  unpin: (eventId: number) =>
    client.delete(`/chat/${eventId}/pin`).then((r) => r.data),
}

// ── Mini-games ────────────────────────────────────────────────────────────────

export const miniGamesApi = {
  /** The server-side registry. The game picker renders from this, so shipping a new
   *  game needs no frontend catalogue edit — only its i18n name. */
  listGames: () => client.get<MiniGameInfo[]>('/minigames/games').then((r) => r.data),

  /** Opens a scored run. The token ties the eventual score to a known start time. */
  startRun: (game: string) =>
    client.post<{ token: string; game: string }>('/minigames/runs', { game }).then((r) => r.data),

  submitRun: (token: string, score: number, details: Record<string, number>) =>
    client
      .post<MiniGameSubmitResult>(`/minigames/runs/${token}/submit`, { score, details })
      .then((r) => r.data),

  leaderboard: (game: string, limit = 20) =>
    client
      .get<MiniGameScore[]>(`/minigames/leaderboard?game=${encodeURIComponent(game)}&limit=${limit}`)
      .then((r) => r.data),

  myBest: (game: string) =>
    client
      .get<MiniGameScore | null>(`/minigames/me/best?game=${encodeURIComponent(game)}`)
      .then((r) => r.data),

  deleteScore: (id: number) => client.delete(`/minigames/scores/${id}`).then((r) => r.data),
}

// ── Activity ──────────────────────────────────────────────────────────────────

export const activityApi = {
  getAll: (limit = 30) =>
    client.get<ActivityLogEntry[]>(`/activity/?limit=${limit}`).then((r) => r.data),

  react: (id: number, emoji: string) =>
    client.post<ActivityLogEntry>(`/activity/${id}/react`, { emoji }).then((r) => r.data),
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export const auditApi = {
  getAll: (limit = 100) =>
    client.get<AuditLogEntry[]>(`/audit/?limit=${limit}`).then((r) => r.data),
}

// ── Backup ────────────────────────────────────────────────────────────────────

export const backupApi = {
  download: () => {
    const token = localStorage.getItem('token')
    const a = document.createElement('a')
    a.href = `/api/backup/export`
    // Use fetch with auth header for the download
    fetch('/api/backup/export', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        a.href = url
        a.download = `lanparty_backup_${new Date().toISOString().slice(0, 10)}.tar.gz`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      })
  },

  restore: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<{ ok: boolean; restarting: boolean }>('/backup/import', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  storage: () =>
    client
      .get<{ disk_total: number; disk_used: number; disk_free: number; uploads_size: number }>('/backup/storage')
      .then((r) => r.data),
}
