from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Any, Dict, Literal, Optional, List
from datetime import date, datetime

from riot_id import parse_riot_id


# NIST SP 800-63B's floor for user-chosen passwords (was 6 before 1.3.4).
PASSWORD_MIN_LENGTH = 8


def _check_password_byte_limit(v: str) -> str:
    # bcrypt hard-caps input at 72 bytes; check bytes (not chars) since
    # accented characters can exceed 72 bytes at fewer than 72 characters.
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or less (accented characters count as more than one byte)")
    return v


def _normalize_email(v: str) -> str:
    # Emails are case-insensitive in practice. Login and Discord already match
    # case-insensitively, but registration used to store the raw casing — which
    # let "Bob@x.com" and "bob@x.com" both register and made forgot-password miss
    # on a case mismatch. Normalising on input keeps every path consistent.
    return v.strip().lower()


RESERVED_USERNAME_PREFIX = "deleted_user_"


def _check_username(v: str) -> str:
    # '@' is reserved so login can tell a username apart from an email address
    # (an identifier containing '@' is always treated as an email). Whitespace
    # is rejected for the same disambiguation/robustness reason.
    if "@" in v or any(c.isspace() for c in v):
        raise ValueError("Username cannot contain '@' or spaces")
    # The name given to deleted accounts: a member taking "deleted_user_7"
    # would make deleting account 7 fail on the unique constraint.
    if v.lower().startswith(RESERVED_USERNAME_PREFIX):
        raise ValueError("This username is reserved")
    return v


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH)
    invite_code: Optional[str] = None
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None

    _validate_password = field_validator("password")(_check_password_byte_limit)
    _validate_username = field_validator("username")(_check_username)
    _validate_email = field_validator("email")(_normalize_email)


class UserLogin(BaseModel):
    # Accepts either a username or an email address. The old field name
    # `username` is still honoured via the alias so existing clients keep working.
    model_config = ConfigDict(populate_by_name=True)

    identifier: str = Field(..., validation_alias="username")
    password: str


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH)

    _validate_new_password = field_validator("new_password")(_check_password_byte_limit)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    _validate_email = field_validator("email")(_normalize_email)


class ResetPasswordConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH)

    _validate_new_password = field_validator("new_password")(_check_password_byte_limit)


class DiscordLinkTicketRequest(BaseModel):
    password: str = Field(..., max_length=200)


class Token(BaseModel):
    access_token: str
    token_type: str


# ── Users ─────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    clothing_size: Optional[str] = None
    is_meal_prep_volunteer: bool
    is_tournament_organizer: bool
    profile_complete: bool
    is_active: bool
    deleted_at: Optional[datetime] = None
    created_at: datetime
    discord_username: Optional[str] = None
    steam_username: Optional[str] = None
    riot_id: Optional[str] = None
    has_password: bool = True
    last_seen: Optional[datetime] = None
    is_online: bool = False  # computed (last_seen within the online window); set by the router


class DeletedUserOut(BaseModel):
    """One row of the admin-only deleted-accounts history (Settings). Not
    UserOut — a deleted row's own `username`/`email` are scrubbed, so this
    surfaces `deleted_username` (captured before scrubbing) instead."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    deleted_username: Optional[str] = None
    deleted_at: datetime


class UserPublic(BaseModel):
    """Public view of a user — UserOut WITHOUT email, phone or linked-account
    details. Returned to viewers who are neither the user themselves nor an
    admin, and nested in every response that embeds another member (expenses,
    tournaments, streams, events, the activity feed, mini-game scores), so a
    member's contact details aren't exposed to the whole (invite-only) crew.
    tests/test_contact_privacy.py fails if a response nests UserOut again."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    avatar_url: Optional[str] = None
    clothing_size: Optional[str] = None
    is_meal_prep_volunteer: bool
    is_tournament_organizer: bool
    profile_complete: bool
    is_active: bool
    created_at: datetime
    last_seen: Optional[datetime] = None
    is_online: bool = False  # computed (last_seen within the online window); set by the router


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    clothing_size: Optional[str] = None
    phone: Optional[str] = None
    is_meal_prep_volunteer: Optional[bool] = None
    is_tournament_organizer: Optional[bool] = None
    # "GameName#TAG". null or "" clears it. Uniqueness is checked by the router.
    riot_id: Optional[str] = Field(None, max_length=64)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: Optional[str]) -> Optional[str]:
        return _check_username(v) if v is not None else v

    @field_validator("riot_id")
    @classmethod
    def _validate_riot_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return parse_riot_id(v)[0]


# ── Expenses ──────────────────────────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=300)
    # Finite, at least one cent, at most 100 000 €. `inf` or `1e308` used to be
    # stored as is and break every treasury view (JSON can't carry them back).
    amount: float = Field(..., ge=0.01, le=100_000, allow_inf_nan=False)
    category: str = Field("general", max_length=40)
    date: date
    event_id: Optional[int] = None
    paid_by: Optional[int] = None

    @field_validator("amount", mode="before")
    @classmethod
    def _amount_is_a_number(cls, v):
        if isinstance(v, bool):  # JSON `true` would otherwise become 1.0
            raise ValueError("amount must be a number")
        return v

    @field_validator("amount")
    @classmethod
    def _amount_to_cents(cls, v: float) -> float:
        return round(v, 2)


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    amount: float
    category: str
    date: date
    created_by: int
    paid_by: Optional[int] = None
    event_id: Optional[int] = None
    created_at: datetime
    creator: UserPublic
    payer: Optional[UserPublic] = None


# ── Teams ─────────────────────────────────────────────────────────────────────

class TeamMemberCreate(BaseModel):
    player_name: str
    user_id: Optional[int] = None


class TeamCreate(BaseModel):
    team_name: str = Field(..., min_length=1)
    color: Optional[str] = None
    seed: Optional[int] = None
    members: List[TeamMemberCreate] = []


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_name: str
    user_id: Optional[int] = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_name: str
    score: int
    color: Optional[str] = None
    seed: Optional[int] = None
    members: List[TeamMemberOut] = []


# ── Matches ───────────────────────────────────────────────────────────────────

class MatchUpdate(BaseModel):
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    status: Optional[str] = None
    winner_id: Optional[int] = None


class ReportScore(BaseModel):
    score_a: int = Field(..., ge=0)
    score_b: int = Field(..., ge=0)


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    round: str
    round_number: int
    match_number: int
    team_a_id: Optional[int] = None
    team_b_id: Optional[int] = None
    score_a: int
    score_b: int
    winner_id: Optional[int] = None
    status: str
    team_a: Optional[TeamOut] = None
    team_b: Optional[TeamOut] = None
    # Self-service score reporting — a pending, unconfirmed score (reported_by /
    # reported_at are null when there's no pending report).
    reported_score_a: Optional[int] = None
    reported_score_b: Optional[int] = None
    reported_by: Optional[int] = None


# ── Tournaments ───────────────────────────────────────────────────────────────

class TournamentCreate(BaseModel):
    game_name: str = Field(..., min_length=1)
    # A catalog pick. When absent, game_name is looked up (case-insensitively)
    # or added to the catalog as a custom game — either way the tournament ends
    # up linked, and game_name is rewritten to the catalog's spelling.
    game_id: Optional[int] = None
    bracket_type: str = "single_elimination"
    event_type: str = "team"
    max_team_size: int = Field(default=2, ge=1, le=10)
    event_id: Optional[int] = None


class TournamentUpdate(BaseModel):
    game_name: Optional[str] = None
    game_id: Optional[int] = None
    status: Optional[str] = None


class TournamentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_name: str
    game_id: Optional[int] = None
    bracket_type: str
    event_type: str
    status: str
    max_team_size: int
    organizer_id: int
    event_id: Optional[int] = None
    organizer: UserPublic
    teams: List[TeamOut] = []
    matches: List[MatchOut] = []
    created_at: datetime


class RoundRobinStanding(BaseModel):
    team_id: int
    team_name: str
    color: Optional[str] = None
    seed: Optional[int] = None
    wins: int
    losses: int
    draws: int
    points: int
    played: int


class HallOfFameEntry(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    wins: int
    participations: int


# ── Per-game stats (derived on read — see tournament_stats.player_game_records) ─

class TournamentGameOut(BaseModel):
    """A catalog game for the tournament game picker, with the hints it's
    ordered by: tournaments already played on it, how many of the event's
    attendees own it, and whether it's on the event's planning."""
    id: int
    name: str
    genre: Optional[str] = None
    default_max_players: Optional[int] = None
    is_custom: bool = False
    tournament_count: int = 0
    owner_count: int = 0
    planned: bool = False


class GameStatsLeader(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    wins: int


class GameStatsSummary(BaseModel):
    game_id: int
    name: str
    genre: Optional[str] = None
    tournaments: int
    matches: int
    players: int
    leader: Optional[GameStatsLeader] = None


class PlayerGameStatsLine(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    played: int
    wins: int
    losses: int
    draws: int
    win_rate: Optional[float] = None  # None below MIN_MATCHES_FOR_RATE
    tournaments: int
    titles: int


class GameStatsDetail(BaseModel):
    game_id: int
    name: str
    genre: Optional[str] = None
    tournaments: int
    matches: int
    players: List[PlayerGameStatsLine]


class UserGameStatsLine(BaseModel):
    game_id: int
    name: str
    played: int
    wins: int
    losses: int
    draws: int
    win_rate: Optional[float] = None
    tournaments: int
    titles: int


class UnlinkedTournamentOut(BaseModel):
    id: int
    game_name: str
    event_id: Optional[int] = None
    status: str
    created_at: datetime


# ── Pro-rata ──────────────────────────────────────────────────────────────────

class ProRataShare(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str]
    nights: int
    percentage: float
    amount: float


class SettlementLine(BaseModel):
    from_user_id: int
    from_username: str
    to_user_id: int
    to_username: str
    to_phone: Optional[str] = None  # only populated for the debtor (viewer) of this line
    amount: float
    paid: bool = False


class ProRataResult(BaseModel):
    total_expenses: float
    event_id: Optional[int] = None
    event_title: Optional[str] = None
    event_start: Optional[str]
    event_end: Optional[str]
    total_nights: int
    total_person_nights: int
    shares: List[ProRataShare]
    settlements: List[SettlementLine] = []


# ── Event Invites ─────────────────────────────────────────────────────────────

class EventInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    code: str
    event_title: str
    capacity: Optional[int] = None
    rsvp_count: int
    seats_left: Optional[int] = None
    created_by: int
    created_at: datetime


class EventInviteValidate(BaseModel):
    valid: bool
    full: Optional[bool] = None
    event_id: Optional[int] = None
    event_title: Optional[str] = None
    event_start: Optional[date] = None
    event_end: Optional[date] = None


# ── LiveStreams ────────────────────────────────────────────────────────────────

class LiveStreamCreate(BaseModel):
    channel_name: str = Field(..., min_length=1, max_length=200)
    title: Optional[str] = None
    is_active: bool = True
    stream_type: str = "channel"
    clip_slug: Optional[str] = None


class LiveStreamUpdate(BaseModel):
    channel_name: Optional[str] = None
    title: Optional[str] = None
    is_active: Optional[bool] = None
    stream_type: Optional[str] = None
    clip_slug: Optional[str] = None


class LiveStreamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_name: str
    title: Optional[str] = None
    is_active: bool
    stream_type: str = "channel"
    clip_slug: Optional[str] = None
    created_by: int
    created_at: datetime
    creator: UserPublic


# ── Media ─────────────────────────────────────────────────────────────────────

class MediaReactionCount(BaseModel):
    """One emoji's tally on a media item, plus whether the viewer is in it.

    `users` is who reacted (usernames, oldest first) — the hover/long-press
    tooltip. Populated only for a logged-in viewer: the public recap share
    hydrates with viewer_id=None and its tallies carry counts alone, so
    reactor names never reach a public URL."""
    emoji: str
    count: int
    mine: bool
    users: List[str] = []


class MediaItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    original_name: str
    file_type: str
    mime_type: str
    file_size: int
    url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    event_id: Optional[int] = None
    uploaded_by: int
    created_at: datetime
    # UserPublic, not UserOut: the gallery shows every item to every member (and
    # the recap's photos can reach a public share link), so nesting UserOut here
    # handed out the uploader's email and phone. Only the username is ever read.
    uploader: UserPublic
    # Monkey-patched onto the instance by the router before return — the same
    # convention EventOut uses. Not @property on the model.
    reactions: List[MediaReactionCount] = []
    reaction_total: int = 0


class MediaItemUpdate(BaseModel):
    """Caption / event re-tagging after upload. Both are explicitly nullable —
    clearing a caption and untagging an event are real actions — so the router
    uses model_dump(exclude_unset=True) to tell "set to null" from "not sent"."""
    caption: Optional[str] = Field(None, max_length=500)
    event_id: Optional[int] = None


class MediaReact(BaseModel):
    emoji: str


# ── LAN Events ────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    location: Optional[str] = None
    start_date: date
    end_date: date
    capacity: Optional[int] = None
    # Planning per-event toggle overrides; None = inherit the global default.
    planning_can_propose: Optional[bool] = None
    planning_can_vote: Optional[bool] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    capacity: Optional[int] = None
    planning_can_propose: Optional[bool] = None
    planning_can_vote: Optional[bool] = None


class EventAttendeeOut(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_date: date
    end_date: date
    capacity: Optional[int] = None
    cover_image_url: Optional[str] = None
    planning_can_propose: Optional[bool] = None
    planning_can_vote: Optional[bool] = None
    rsvp_count: int = 0
    my_rsvp: Optional[str] = None
    my_arrival_date: Optional[date] = None
    my_departure_date: Optional[date] = None
    # True from the event's first day (instance timezone): members can no
    # longer change their own attendance, only a treasurer or an admin can.
    attendance_locked: bool = False
    attendees: List[EventAttendeeOut] = []
    created_by: int
    created_at: datetime
    creator: UserPublic


class EventRSVPIn(BaseModel):
    arrival_date: date
    departure_date: date


class EventRSVPAdjust(BaseModel):
    """A treasurer's or admin's correction of a member's attendance."""
    status: Literal["in", "out"]
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None


class EventRSVPOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    user_id: int
    status: str
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None
    created_at: datetime


# ── Activity & Audit ──────────────────────────────────────────────────────────

class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    description: str
    created_at: datetime
    user: UserPublic
    # Populated only for entity_type == "media" (a hydrated MediaItem, attached
    # by the router — see router_activity._hydrate_media). Its reactions are
    # the *real* media_reactions tallies (same ones the gallery shows), mirrored
    # onto this entry's own reactions/reaction_total below — one source of
    # truth per photo, not a second reaction bar per surface it appears on.
    media: Optional[MediaItemOut] = None
    # For a media entry: a mirror of media.reactions/media.reaction_total.
    # For every other activity type (no reaction-bearing entity of its own):
    # this entry's own activity_reactions tally.
    reactions: List[MediaReactionCount] = []
    reaction_total: int = 0


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int
    action: str
    details: Optional[str] = None
    created_at: datetime
    admin: UserOut


# ── Settings ──────────────────────────────────────────────────────────────────

class AppSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Optional[str] = None


class AppSettingUpdate(BaseModel):
    value: Optional[str] = None


# ── Sponsors ──────────────────────────────────────────────────────────────────

class SponsorCreate(BaseModel):
    event_id: int
    name: str = Field(..., min_length=1)
    link_url: Optional[str] = None


class SponsorUpdate(BaseModel):
    name: Optional[str] = None
    link_url: Optional[str] = None
    sort_order: Optional[int] = None


class SponsorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    name: str
    banner_url: Optional[str] = None
    banner_type: Optional[str] = None
    link_url: Optional[str] = None
    sort_order: int
    created_at: datetime


# ── Prizes ────────────────────────────────────────────────────────────────────

class PrizeCreate(BaseModel):
    event_id: int
    title: str = Field(..., min_length=1)
    description: Optional[str] = None


class PrizeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class PrizeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    title: str
    description: Optional[str] = None
    photo_url: Optional[str] = None
    sort_order: int
    created_at: datetime


# ── Planning ("Calendar View") ─────────────────────────────────────────────────

class ScheduleBlockCreate(BaseModel):
    game: str = Field(..., min_length=1, max_length=120)
    proposed_start: Optional[datetime] = None
    proposed_end: Optional[datetime] = None


class BlockVoteSet(BaseModel):
    # The full set of hour-slots the current user approves for this block; this
    # replaces any previous set. Each must be top-of-the-hour.
    slots: List[datetime] = []


class BlockLock(BaseModel):
    locked_start: datetime
    locked_end: datetime
    color: Optional[str] = None   # palette key (e.g. "peacock"); None = derive from game name


class SlotTally(BaseModel):
    slot_start: datetime
    count: int


class ScheduleBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    game: str
    proposed_start: Optional[datetime] = None
    proposed_end: Optional[datetime] = None
    status: str
    locked_start: Optional[datetime] = None
    locked_end: Optional[datetime] = None
    color: Optional[str] = None     # palette key chosen at lock time; None = derive from game name
    created_by: int
    created_at: datetime
    # Computed and monkey-patched onto the ORM instance by the router (read via
    # getattr, like EventOut's rsvp_count) — not columns on the model.
    tallies: List[SlotTally] = []   # approvals per hour-slot across all voters
    my_slots: List[datetime] = []   # hour-slots the current user approved


class ViewPreferenceSet(BaseModel):
    view: str = Field(..., pattern="^(list|calendar)$")


class PlanningEventOut(BaseModel):
    """Everything the PLAN page needs for one event in a single call."""
    event_id: int
    event_start: date
    event_end: date
    can_propose: bool               # effective toggle (event override or global default)
    can_vote: bool
    my_arrival_date: Optional[date] = None
    my_departure_date: Optional[date] = None
    is_attending: bool              # do I have an "in" RSVP? (gates voting)
    my_schedule_view: Optional[str] = None   # "list" | "calendar" — saved account preference
    blocks: List[ScheduleBlockOut] = []


# ── Announcements / PA ─────────────────────────────────────────────────────────

class AnnouncementCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    level: str = "info"                       # "info" | "alert"
    event_id: Optional[int] = None            # informational context; null = global
    expires_at: Optional[datetime] = None
    post_to_discord: bool = False


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    level: str
    event_id: Optional[int] = None
    created_by: int
    created_at: datetime
    expires_at: Optional[datetime] = None


# ── Gear / BYO ("who's bringing what") ─────────────────────────────────────────

class GearItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: Optional[str] = Field(None, max_length=40)
    quantity: int = Field(1, ge=1, le=999)
    note: Optional[str] = Field(None, max_length=300)


class GearItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    category: Optional[str] = Field(None, max_length=40)
    quantity: Optional[int] = Field(None, ge=1, le=999)
    note: Optional[str] = Field(None, max_length=300)


class GearItemOut(BaseModel):
    id: int
    event_id: int
    name: str
    category: Optional[str] = None
    quantity: int
    note: Optional[str] = None
    is_request: bool
    pledged_by: Optional[int] = None
    pledged_username: Optional[str] = None       # populated from the pledger relationship
    pledged_avatar_url: Optional[str] = None
    created_by: int
    created_at: datetime


class GearSuggestion(BaseModel):
    """One entry in a user's personal "gear locker" — an item they've brought
    before, offered pre-ticked for carryover into a new event."""
    name: str
    category: Optional[str] = None
    quantity: int
    times_brought: int
    last_event_title: Optional[str] = None


class GearCarryoverItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: Optional[str] = Field(None, max_length=40)
    quantity: int = Field(1, ge=1, le=999)


class GearCarryover(BaseModel):
    items: List[GearCarryoverItem] = []


class GearEventOut(BaseModel):
    """Everything the gear section needs for one event in a single call."""
    event_id: int
    items: List[GearItemOut] = []
    pledged_count: int            # items someone is actually bringing
    open_request_count: int       # admin requests nobody has claimed yet


# ── Groceries ("courses") ───────────────────────────────────────────────────────

class GroceryItemCreate(BaseModel):
    category: Optional[str] = Field(None, max_length=60)
    name: str = Field(..., min_length=1, max_length=120)
    quantity: Optional[str] = Field(None, max_length=40)
    assigned_to: Optional[int] = None


class GroceryItemUpdate(BaseModel):
    category: Optional[str] = Field(None, max_length=60)
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    quantity: Optional[str] = Field(None, max_length=40)
    assigned_to: Optional[int] = None
    is_bought: Optional[bool] = None


class GroceryItemOut(BaseModel):
    id: int
    event_id: int
    category: Optional[str] = None
    name: str
    quantity: Optional[str] = None
    assigned_to: Optional[int] = None
    assigned_username: Optional[str] = None      # populated from the assignee relationship
    assigned_avatar_url: Optional[str] = None
    is_bought: bool
    created_by: int
    created_at: datetime


class GroceryEventOut(BaseModel):
    """Everything the groceries section needs for one event in a single call."""
    event_id: int
    items: List[GroceryItemOut] = []
    bought_count: int
    total_count: int


class GroceryImportRow(BaseModel):
    category: Optional[str] = Field(None, max_length=60)
    name: str = Field(..., min_length=1, max_length=120)
    quantity: Optional[str] = Field(None, max_length=40)
    assigned_username: Optional[str] = Field(None, max_length=120)
    is_bought: bool = False


class GroceryImport(BaseModel):
    items: List[GroceryImportRow] = Field(..., max_length=500)


class GroceryImportResult(BaseModel):
    imported: int
    unmatched_usernames: List[str] = []


# ── Recap ─────────────────────────────────────────────────────────────────────

class BadgeOut(BaseModel):
    """An earned badge. `code` only — the label and description are i18n keys on
    the frontend (`badges.<code>.label` / `.desc`), so no English lives here."""
    code: str
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    value: Optional[int] = None


class RecapEvent(BaseModel):
    id: int
    title: str
    start_date: date
    end_date: date
    cover_image_url: Optional[str] = None
    nights: int


class RecapAttendance(BaseModel):
    attendee_count: int
    total_person_nights: int
    longest_stay: int
    first_arrival: Optional[date] = None
    last_departure: Optional[date] = None


class RecapChampion(BaseModel):
    team_name: str
    color: Optional[str] = None
    members: List[str] = []


class RecapTournament(BaseModel):
    tournament_id: int
    game_name: str
    bracket_type: str
    match_count: int
    champion: Optional[RecapChampion] = None


class RecapPlayer(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    wins: int


class RecapMedia(BaseModel):
    total: int
    photo_count: int
    video_count: int
    top: List[MediaItemOut] = []


class RecapMoney(BaseModel):
    """Aggregates only — never `shares` or `settlements`. A recap is a highlight
    card, not the ledger; the Treasury page is where the ledger lives."""
    total_expenses: float
    currency: str
    per_person_avg: float
    settled_lines: int
    total_lines: int


class RecapOut(BaseModel):
    event: RecapEvent
    attendance: RecapAttendance
    tournaments: List[RecapTournament] = []
    mvp: Optional[RecapPlayer] = None
    media: RecapMedia
    # None when treasury is off, and ALWAYS None on the public share link.
    money: Optional[RecapMoney] = None
    badges: List[BadgeOut] = []
    # Revealed trophies of this edition (empty when the feature is off). They
    # carry no money, so they ride on the public share link too.
    trophies: List["RecapTrophy"] = []
    generated_at: datetime
    shared: bool = False


class RecapShareOut(BaseModel):
    event_id: int
    token: Optional[str] = None


# ── My Setup ──────────────────────────────────────────────────────────────────

# The fixed component vocabulary. These names are BOTH the UserSetup column names
# and the i18n keys the frontend renders (`setup.field.<name>`) — the two must
# stay identical, which is the point: the label lives in the translation bundle,
# never in the database. Mirrored in frontend/src/types/index.ts as SETUP_FIELDS.
SETUP_FIELDS = (
    "motherboard", "cpu", "cooler", "graphics_card", "ram", "power_supply",
    "fans", "storage", "pc_case", "display", "keyboard", "mouse", "headset", "mic",
)

MAX_SETUP_PHOTOS = 5
MAX_SETUP_CUSTOM_FIELDS = 10


class SetupComponents(BaseModel):
    """The 14 fixed components. All optional — a setup is filled in over time."""
    model_config = ConfigDict(from_attributes=True)

    motherboard: Optional[str] = Field(None, max_length=200)
    cpu: Optional[str] = Field(None, max_length=200)
    cooler: Optional[str] = Field(None, max_length=200)
    graphics_card: Optional[str] = Field(None, max_length=200)
    ram: Optional[str] = Field(None, max_length=200)
    power_supply: Optional[str] = Field(None, max_length=200)
    fans: Optional[str] = Field(None, max_length=200)
    storage: Optional[str] = Field(None, max_length=200)
    pc_case: Optional[str] = Field(None, max_length=200)
    display: Optional[str] = Field(None, max_length=200)
    keyboard: Optional[str] = Field(None, max_length=200)
    mouse: Optional[str] = Field(None, max_length=200)
    headset: Optional[str] = Field(None, max_length=200)
    mic: Optional[str] = Field(None, max_length=200)


class SetupFieldIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=60)
    value: Optional[str] = Field(None, max_length=200)


class SetupFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    value: Optional[str] = None


class SetupPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    caption: Optional[str] = None


class SetupPhotoUpdate(BaseModel):
    caption: Optional[str] = Field(None, max_length=200)


class SetupUpdate(BaseModel):
    """The 14 components and the whole custom-field list in one body, so a save
    can't leave "your CPU saved but your custom fields didn't"."""
    components: SetupComponents = SetupComponents()
    custom_fields: List[SetupFieldIn] = []


class SetupOut(BaseModel):
    """A setup as its owner or another logged-in member sees it."""
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    components: SetupComponents
    custom_fields: List[SetupFieldOut] = []
    photos: List[SetupPhotoOut] = []
    has_content: bool = False
    # Same tally shape as media — MediaReactionCount is just (emoji, count, mine).
    # Deliberately absent from SetupSharedOut: the public link stays minimal.
    reactions: List[MediaReactionCount] = []
    reaction_total: int = 0


class SetupSharedOut(BaseModel):
    """The public, token-authorized view.

    Deliberately NOT UserPublic: that carries `role` (telling a stranger who the
    admin is), plus `is_online` / `last_seen` (publishing "this person is at home
    right now" on an unauthenticated URL), `created_at` and `is_active`. Nor any
    user_id — that's a handle into /api/users/{id}. A public URL is the internet;
    this is the recap's money rule applied to PII.
    """
    username: str
    avatar_url: Optional[str] = None
    components: SetupComponents
    custom_fields: List[SetupFieldOut] = []
    photos: List[SetupPhotoOut] = []


class SetupShareOut(BaseModel):
    token: Optional[str] = None


# ── Event checklist (private packing list) ─────────────────────────────────────

# The fixed item vocabulary — same rule as SETUP_FIELDS: these names are BOTH the
# EventChecklist column names and the i18n keys (`checklist.field.<name>`).
# Mirrored in frontend/src/types/index.ts as CHECKLIST_FIXED_FIELDS.
CHECKLIST_FIXED_FIELDS = (
    "computer", "screen", "screen_psu", "keyboard_mouse", "cables",
    "mousepad", "headset", "vanity", "backpack",
)

MAX_CHECKLIST_CUSTOM_FIELDS = 10


class ChecklistItems(BaseModel):
    """The 9 fixed pack-list items. All default unchecked."""
    model_config = ConfigDict(from_attributes=True)

    computer: bool = False
    screen: bool = False
    screen_psu: bool = False
    keyboard_mouse: bool = False
    cables: bool = False
    mousepad: bool = False
    headset: bool = False
    vanity: bool = False
    backpack: bool = False


class ChecklistFieldIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    checked: bool = False


class ChecklistFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    checked: bool = False


class ChecklistUpdate(BaseModel):
    """The 9 fixed items and the whole custom-field list in one body — same
    whole-state-replace shape as SetupUpdate."""
    items: ChecklistItems = ChecklistItems()
    custom_fields: List[ChecklistFieldIn] = []


class ChecklistOut(BaseModel):
    """The caller's own checklist for one event. Never another user's — there is
    no endpoint that can return anyone else's row."""
    event_id: int
    items: ChecklistItems
    custom_fields: List[ChecklistFieldOut] = []
    started: bool = False
    progress_checked: int = 0
    progress_total: int = 0


class ChecklistSuggestion(BaseModel):
    """The caller's most recent checklist from a *different* event, offered as a
    one-click "copy my usual list" carryover suggestion."""
    source_event_id: int
    source_event_title: str
    items: ChecklistItems
    custom_fields: List[ChecklistFieldOut] = []


# ── Mini-games ────────────────────────────────────────────────────────────────

class MiniGameInfo(BaseModel):
    """One entry of the server-side registry (`minigames_registry.GAMES`).

    The frontend renders its game picker from this rather than keeping its own
    catalogue — with up to 8 games planned, two lists that can disagree is exactly
    the bug we don't want."""
    slug: str
    metric: str
    max_score: int
    higher_is_better: bool
    detail_fields: List[str] = []


class MiniGameRunStart(BaseModel):
    game: str


class MiniGameRunToken(BaseModel):
    token: str
    game: str


class MiniGameSubmit(BaseModel):
    """`score` is the single ranked number; what it counts is per-game (see
    MiniGameInfo.metric). `details` is that game's extra stats — shown next to the
    score, never ranked on, and filtered to the game's declared fields on arrival."""
    score: int
    details: dict = {}


class MiniGameScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game: str
    score: int
    details: dict = {}
    created_at: datetime
    user: UserPublic


class MiniGameSubmitResult(BaseModel):
    """Returned to the game itself, which uses `personal_best` to show a toast."""
    accepted: bool
    personal_best: bool = False
    rank: Optional[int] = None
    score: Optional[MiniGameScoreOut] = None


# ── Games (library / wishlist / finder) ─────────────────────────────────────────

class GameOut(BaseModel):
    """One catalog entry — either seeded from the crew's game list or added by a
    member (`is_custom`). `default_max_players` is the catalog's own number; a
    member's own copy may override it (see GameLibraryEntryOut.max_players)."""
    id: int
    name: str
    genre: Optional[str] = None
    default_max_players: Optional[int] = None
    is_custom: bool = False


class GameLibraryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    max_players_override: Optional[int] = Field(None, ge=1, le=999)


class GameLibraryUpdate(BaseModel):
    max_players_override: Optional[int] = Field(None, ge=1, le=999)


class GameFavoriteUpdate(BaseModel):
    is_favorite: bool


class GameLibraryFilters(BaseModel):
    """The profile library's filter bar, saved on the account (see
    User.games_library_filters). Every field defaults to "no filter", which is
    also what a member who never touched the bar gets back."""
    sort: Optional[Literal["asc", "desc"]] = None
    min_players: Optional[int] = Field(None, ge=1, le=999)
    max_players: Optional[int] = Field(None, ge=1, le=999)
    playable_only: bool = False
    favorites_only: bool = False


class GameWishlistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class GameLibraryEntryOut(BaseModel):
    """A library row with the effective max player count already resolved
    (override if set, else the catalog default) — the frontend never needs to
    do that fallback itself."""
    game_id: int
    name: str
    genre: Optional[str] = None
    max_players: Optional[int] = None
    is_custom: bool = False
    # Only ever true on the member's own library — other members' rows (finder
    # matches/session) always report False, a star being a private preference.
    is_favorite: bool = False


class GameWishlistEntryOut(BaseModel):
    game_id: int
    name: str
    genre: Optional[str] = None


class GameMeOut(BaseModel):
    library: List[GameLibraryEntryOut] = []
    wishlist: List[GameWishlistEntryOut] = []
    filters: GameLibraryFilters = GameLibraryFilters()


class GameMatchOut(BaseModel):
    """One other member ranked by how many library games they share with the
    current user — powers the "players like me" list on the games-finder page."""
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    shared_count: int
    shared_games: List[GameLibraryEntryOut] = []


class GameSessionRequest(BaseModel):
    """"We're these people tonight — what can we all play?" `min_players`
    optionally raises the bar above the selected group's own size (e.g. picking 2
    people but wanting only games that scale to 4+)."""
    user_ids: List[int] = Field(..., min_length=1)
    min_players: Optional[int] = Field(None, ge=1, le=999)


class GameSessionResultOut(BaseModel):
    games: List[GameLibraryEntryOut] = []


class GameImportResultOut(BaseModel):
    """Result of importing a linked Steam account's owned games.
    `games_visible=False` means Steam's game list for this account is private
    — distinct from a successful import that simply found nothing new."""
    games_visible: bool
    imported: int = 0
    already_owned: int = 0
    added_custom: int = 0


# ── Craving Chat ──────────────────────────────────────────────────────────────

class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    reply_to_id: Optional[int] = None


class ChatMessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class ChatReactionIn(BaseModel):
    # Deliberately free text (not a fixed set like Media/Activity's
    # REACTION_EMOJI) — sourced from the OS's own emoji picker on the
    # frontend. Long enough for a ZWJ sequence or a skin-tone modifier
    # (multi-codepoint emoji can run past 4-8 UTF-16 code units).
    emoji: str = Field(..., min_length=1, max_length=16)


class ChatReactionOut(BaseModel):
    emoji: str
    count: int
    mine: bool = False


class ChatMessageReplyPreview(BaseModel):
    id: int
    username: str
    content: str


class ChatMentionOut(BaseModel):
    user_id: int
    username: str


class PinnedMessageOut(BaseModel):
    id: int
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    content: str
    created_at: datetime


class ChatLinkPreviewOut(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    site_name: Optional[str] = None


class ChatMessageOut(BaseModel):
    id: int
    event_id: int
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    is_admin: bool = False
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None
    is_mine: bool = False
    reply_to: Optional[ChatMessageReplyPreview] = None
    reactions: List[ChatReactionOut] = []
    link_preview: Optional[ChatLinkPreviewOut] = None
    mentions: List[ChatMentionOut] = []


# ── Trophies ──────────────────────────────────────────────────────────────────
# Free text by design (name/description/citation are the crew's own words, in
# their own language) — unlike BadgeOut, which carries only an i18n code.

class TrophyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    emoji: Optional[str] = Field(None, max_length=16)
    description: Optional[str] = Field(None, max_length=300)
    sort_order: Optional[int] = None


class TrophyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    emoji: Optional[str] = Field(None, max_length=16)
    description: Optional[str] = Field(None, max_length=300)
    sort_order: Optional[int] = None
    archived: Optional[bool] = None


class TrophyBrief(BaseModel):
    id: int
    name: str
    emoji: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None


class TrophyLastAward(BaseModel):
    username: str
    event_title: str


class TrophyOut(TrophyBrief):
    """A cabinet entry, with how often it's been awarded (revealed editions)."""
    sort_order: int = 0
    archived_at: Optional[datetime] = None
    awarded_count: int = 0
    last_award: Optional[TrophyLastAward] = None


class TrophyEditionCreate(BaseModel):
    trophy_id: int
    mode: str = Field("vote", pattern="^(vote|direct)$")


class TrophyEditionUpdate(BaseModel):
    # Only the transitions that don't need a payload of their own: open/close/
    # reopen a vote, un-reveal. Revealing goes through POST .../reveal.
    status: Optional[str] = Field(None, pattern="^(draft|voting|closed)$")
    mode: Optional[str] = Field(None, pattern="^(vote|direct)$")
    sort_order: Optional[int] = None


class TrophyWinnerIn(BaseModel):
    user_id: int
    citation: Optional[str] = Field(None, max_length=200)


class TrophyWinnersIn(BaseModel):
    winners: List[TrophyWinnerIn] = Field(default_factory=list, max_length=10)


class TrophyVoteIn(BaseModel):
    nominee_id: int


class TrophyRevealIn(BaseModel):
    post_to_discord: bool = False


class TrophyWinnerOut(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    citation: Optional[str] = None
    vote_count: Optional[int] = None


class TrophyTallyLine(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    votes: int


class TrophyEditionOut(BaseModel):
    """One edition as the viewer may see it. For a non-admin: `winners` stays
    empty until revealed and `tally` is always None; `my_vote` is the only
    ballot anyone is ever shown, and only their own."""
    id: int
    event_id: int
    trophy: TrophyBrief
    mode: str
    status: str
    revealed_at: Optional[datetime] = None
    winners: List[TrophyWinnerOut] = []
    voters_count: int = 0
    eligible_count: int = 0
    my_vote: Optional[int] = None
    tally: Optional[List[TrophyTallyLine]] = None


class UserTrophyOut(BaseModel):
    """A trophy in a member's showcase: which edition, and why."""
    edition_id: int
    trophy: TrophyBrief
    event_id: int
    event_title: str
    event_start_date: date
    citation: Optional[str] = None
    revealed_at: Optional[datetime] = None


class RecapTrophyWinner(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    citation: Optional[str] = None


class RecapTrophy(BaseModel):
    trophy: TrophyBrief
    winners: List[RecapTrophyWinner] = []


# RecapOut (above) refers to RecapTrophy by name — resolve it now that it exists.
RecapOut.model_rebuild()


# ── League of Legends LAN stats (router_lol.py) ───────────────────────────────

class LolCaptureIn(BaseModel):
    """What the desktop app sends at the end of a game: the League Client's
    end-of-game block and the game session, both untouched — lol_capture.py
    does the parsing, so a Riot field rename is a server-side fix."""
    eog: Dict[str, Any]
    session: Optional[Dict[str, Any]] = None


class LolCaptureResultOut(BaseModel):
    match_id: int
    created: bool  # False = this game was already sent by another member


class LolCaptureStatusOut(BaseModel):
    enabled: bool          # the crew's lol_stats flag
    lan_in_progress: bool  # a LAN this member RSVP'd "in" to runs today


LolCategory = Literal["custom", "aram", "matchmade"]


class LolPlayerLine(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    games: int
    wins: int
    losses: int
    win_rate: Optional[float] = None  # None below MIN_MATCHES_FOR_RATE
    kills: int
    deaths: int
    assists: int
    damage: int
    kda: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    avg_damage: float


class LolRecordOut(BaseModel):
    """Best single-game line of one kind (kills / assists / damage)."""
    kind: Literal["kills", "assists", "damage"]
    value: int
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    champion: Optional[str] = None
    match_id: int


class LolStatsOut(BaseModel):
    game_id: Optional[int] = None  # the catalog's League of Legends row
    matches: int
    players: List[LolPlayerLine] = []
    records: List[LolRecordOut] = []


class LolMatchPlayerOut(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None  # None = a custom-game player nobody has claimed yet
    riot_id: str
    champion: Optional[str] = None
    team_id: Optional[int] = None
    win: bool
    kills: int
    deaths: int
    assists: int
    damage: int


class LolMatchOut(BaseModel):
    id: int
    event_id: Optional[int] = None  # None: played outside any LAN, global stats only
    category: LolCategory
    game_mode: Optional[str] = None
    duration_s: Optional[int] = None
    played_at: datetime
    submitted_by: Optional[str] = None
    players: List[LolMatchPlayerOut] = []
