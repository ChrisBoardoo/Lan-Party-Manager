from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date,
    DateTime, ForeignKey, Index, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # "admin", "treasurer", "user"
    avatar_url = Column(String, nullable=True)
    phone = Column(String, nullable=True)  # optional contact for settling shared costs
    clothing_size = Column(String, nullable=True)
    is_meal_prep_volunteer = Column(Boolean, default=False)
    is_tournament_organizer = Column(Boolean, default=False)
    profile_complete = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    # NULL = never deleted. Set by an admin's full account deletion (which
    # anonymizes rather than removes the row — see alembic 0015). Separate
    # from is_active: deleted implies inactive, but inactive (a reversible
    # deactivation) doesn't imply deleted.
    deleted_at = Column(DateTime, nullable=True)
    # The username as it was *before* deletion scrubbed it — `username`
    # itself gets freed for reuse, so this is the only queryable record of
    # who a deleted row used to be (admin history view — see alembic 0016).
    deleted_username = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    # Last browser heartbeat (POST /api/presence/ping). Drives the "online now"
    # green dot on the HUB roster; NULL until a user's first ping.
    last_seen = Column(DateTime, nullable=True)
    # Planning "Calendar View" display preference — "list" | "calendar". NULL =
    # no preference saved yet, frontend falls back to "list". See md/2.features/calendarview.md.
    planning_schedule_view = Column(String, nullable=True)

    # Discord SSO — set when an account is created via, or linked to, Discord.
    # `discord_id` is the Discord user snowflake (unique); the other two are for display.
    discord_id = Column(String, unique=True, index=True, nullable=True)
    discord_username = Column(String, nullable=True)
    discord_avatar = Column(String, nullable=True)

    # Steam link — link-only (no sign-up via Steam, see md/2.features/Steam_Link.md):
    # `steam_id` is the SteamID64 (unique); the other two are for display, set
    # from GetPlayerSummaries on link. Unlike Discord's avatar (a hash you build
    # a URL from), `steam_avatar` is already a full URL — Steam's API returns
    # one directly.
    steam_id = Column(String, unique=True, index=True, nullable=True)
    steam_username = Column(String, nullable=True)
    steam_avatar = Column(String, nullable=True)

    # Riot ID ("GameName#TAG") — typed on the profile, not OAuth-verified (see
    # riot_id.py). `riot_id` is the display form as the member typed it;
    # `riot_id_key` its case-folded matching form, unique so two members can't
    # claim the same Riot account. Both NULL until set.
    riot_id = Column(String, nullable=True)
    riot_id_key = Column(String, unique=True, index=True, nullable=True)

    # Profile game library filter bar (sort, player range, playable/favorites
    # only), as JSON — saved on the account like planning_schedule_view, so it
    # follows the member between the browser and the desktop app. NULL = never
    # touched, frontend shows the defaults. Shape: schemas.GameLibraryFilters.
    games_library_filters = Column(Text, nullable=True)

    # Copied into every session token (`tv` claim). Bumping it — password
    # change or reset, deactivation, deletion — invalidates every token issued
    # before, see auth.revoke_sessions.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    expenses = relationship("Expense", foreign_keys="Expense.created_by", back_populates="creator")
    tournaments = relationship("Tournament", back_populates="organizer")
    team_memberships = relationship("TeamMember", back_populates="user")
    event_rsvps = relationship("EventRSVP", back_populates="user", cascade="all, delete-orphan")
    game_library = relationship(
        "UserGameLibrary", back_populates="user", cascade="all, delete-orphan"
    )
    game_wishlist = relationship(
        "UserGameWishlist", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_password(self) -> bool:
        """False for Discord-only accounts (stored with the unusable-password
        sentinel). Derived purely from the column, so it's stable per row — read
        by UserOut via getattr. A real bcrypt hash always starts with '$2'."""
        return bool(self.hashed_password) and self.hashed_password.startswith("$2")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, default="general")
    date = Column(Date, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Who actually fronted the money. Nullable for legacy rows (fall back to
    # created_by). Drives the pro-rata who-owes-whom settlement.
    paid_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by], back_populates="expenses")
    payer = relationship("User", foreign_keys=[paid_by])
    event = relationship("LanEvent", foreign_keys=[event_id])


class SettlementPayment(Base):
    """What a debtor declared sending to a creditor for one event ("payment
    sent"). `amount` is the money sent, accumulated over successive marks for
    the same pair (one row per pair, see the unique constraint); it counts in
    the balances, so whatever changes afterwards (a late receipt, new dates)
    shows up as what's still owed. Deleting the row reverses it.

    Rows from before 1.3.4 have no amount: they stay plain "paid" flags on the
    matching line, the way they always worked (see prorata._normalize_payments)."""
    __tablename__ = "settlement_payments"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # debtor
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)    # creditor
    amount = Column(Float, nullable=True)
    marked_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("event_id", "from_user_id", "to_user_id"),)


class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, index=True)
    # Display snapshot, copied from Game.name whenever game_id is set — the
    # kiosk, recap, bracket and activity feed all read this directly.
    game_name = Column(String, nullable=False)
    # The shared catalog entry per-game stats group by. NULL = a legacy
    # tournament the 0028 backfill couldn't match; an admin attaches it from
    # the Arena stats tab. ORM-level FK only (see 0028_tournament_game_id.py).
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True, index=True)
    bracket_type = Column(String, default="single_elimination")
    event_type = Column(String, default="team")  # "team" | "individual"
    organizer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=True)
    status = Column(String, default="pending")
    max_team_size = Column(Integer, default=2)
    created_at = Column(DateTime, server_default=func.now())

    organizer = relationship("User", back_populates="tournaments")
    event = relationship("LanEvent", foreign_keys=[event_id])
    game = relationship("Game", foreign_keys=[game_id])
    teams = relationship("Team", back_populates="tournament", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="tournament", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    team_name = Column(String, nullable=False)
    score = Column(Integer, default=0)
    color = Column(String, nullable=True)
    seed = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    tournament = relationship("Tournament", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    matches_as_a = relationship("Match", foreign_keys="Match.team_a_id", back_populates="team_a")
    matches_as_b = relationship("Match", foreign_keys="Match.team_b_id", back_populates="team_b")


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    player_name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    round = Column(String, nullable=False)
    round_number = Column(Integer, default=1)
    match_number = Column(Integer, default=1)
    team_a_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team_b_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    score_a = Column(Integer, default=0)
    score_b = Column(Integer, default=0)
    winner_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    status = Column(String, default="pending")  # "pending", "in_progress", "completed"
    played_at = Column(DateTime, nullable=True)
    # Self-service score reporting: a participant submits a proposed score that
    # an organizer confirms. These stay set (report pending) until confirm copies
    # them into score_a/score_b, or a reject clears them. The live score/winner/
    # advancement is never touched until confirmation.
    reported_score_a = Column(Integer, nullable=True)
    reported_score_b = Column(Integer, nullable=True)
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    tournament = relationship("Tournament", back_populates="matches")
    team_a = relationship("Team", foreign_keys=[team_a_id], back_populates="matches_as_a")
    team_b = relationship("Team", foreign_keys=[team_b_id], back_populates="matches_as_b")


class LanEvent(Base):
    __tablename__ = "lan_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    capacity = Column(Integer, nullable=True)
    cover_image_url = Column(String, nullable=True)
    # Planning ("Calendar View") per-event overrides of the two toggles. NULL =
    # inherit the global default (app_settings planning_default_can_*). See
    # router_planning._effective_toggles.
    planning_can_propose = Column(Boolean, nullable=True)
    planning_can_vote = Column(Boolean, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    # At most one pinned Craving Chat message per event — NULL (every event
    # by default) means nothing is pinned. See router_chat.py's pin/unpin
    # endpoints. No sa.ForeignKey() enforced at the DB level (see
    # 0027_chat_pinned_message.py), same convention as every other
    # cross-table integer column added post-creation in this app.
    pinned_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])
    rsvps = relationship("EventRSVP", back_populates="event", cascade="all, delete-orphan")
    sponsors = relationship("Sponsor", back_populates="event", cascade="all, delete-orphan")
    prizes = relationship("Prize", back_populates="event", cascade="all, delete-orphan")
    schedule_blocks = relationship("ScheduleBlock", back_populates="event", cascade="all, delete-orphan")
    # Explicit foreign_keys on both sides of this pair of relationships:
    # lan_events and chat_messages are now connected by two independent FK
    # columns in opposite directions (chat_messages.event_id and this
    # pinned_message_id), and SQLAlchemy can't auto-resolve which one a bare
    # relationship() between the two tables means without being told.
    pinned_message = relationship("ChatMessage", foreign_keys=[pinned_message_id])
    trophy_editions = relationship("EventTrophy", back_populates="event", cascade="all, delete-orphan")
    # No delete cascade: deleting an event keeps its captured games, which
    # fall back to the global stats (SQLAlchemy nulls their event_id).
    lol_matches = relationship("LolMatch", back_populates="event")


class Sponsor(Base):
    __tablename__ = "sponsors"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False)
    name = Column(String, nullable=False)
    banner_url = Column(String, nullable=True)
    banner_type = Column(String, nullable=True)  # "image" (png/gif) | "video" (webm)
    link_url = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent", back_populates="sponsors")


class Prize(Base):
    __tablename__ = "prizes"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent", back_populates="prizes")


class Announcement(Base):
    """An admin-posted PA message shown as a dismissible banner across the app
    (and optionally fanned out to Discord). `event_id` is informational context;
    NULL = a global announcement. Expired rows are filtered out at read time."""
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(Text, nullable=False)
    level = Column(String, nullable=False, default="info")  # "info" | "alert"
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=True)  # null = global
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    creator = relationship("User", foreign_keys=[created_by])


class EventRSVP(Base):
    __tablename__ = "event_rsvps"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False)  # "in" or "out"
    arrival_date = Column(Date, nullable=True)
    departure_date = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    event = relationship("LanEvent", back_populates="rsvps")
    user = relationship("User", back_populates="event_rsvps")

    __table_args__ = (UniqueConstraint("event_id", "user_id"),)


class ChatMessage(Base):
    """One message in an event's Craving Chat — a single group room per event,
    open to "in" RSVPs only, from 30 days before start to 15 days after end
    (see router_chat.py's _window_open / _is_attendee). Self-service delete
    only for v1 (a user can remove their own message) — no admin-delete
    column needed for that.

    `updated_at` is a poll watermark, not a display field — bumped by both a
    content edit *and* a reaction change (see router_chat.py's react
    endpoint), so the WS loop can detect "this row changed" without a new row
    being inserted. `edited_at` is the display-facing "(edited)" flag, set
    only by an actual content edit — reactions must not touch it.

    `updated_at` uses a client-side `default=` (evaluated by SQLAlchemy at
    INSERT time), not `server_default=func.now()` — a DB-level default here
    would need adding via an ALTER TABLE ADD COLUMN on any database that
    predates it, and SQLite refuses a non-constant (CURRENT_TIMESTAMP-like)
    default on that specific statement (hit live on a Raspberry Pi's older
    SQLite — see alembic/versions/0024_craving_chat_v2.py). A Python-side
    default sidesteps the DB entirely, so it works the same on a fresh
    install and a migrated one, regardless of SQLite version."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    reply_to_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow)
    edited_at = Column(DateTime, nullable=True)
    # Best-effort Open Graph unfurl of the first link in the message, fetched
    # once server-side in the background (see router_chat.py / link_preview.py)
    # and cached here — never re-fetched per viewer. All null until the
    # background fetch lands, or forever if the link had nothing to show.
    link_preview_url = Column(String, nullable=True)
    link_preview_title = Column(String, nullable=True)
    link_preview_description = Column(Text, nullable=True)
    link_preview_image_url = Column(String, nullable=True)
    link_preview_site_name = Column(String, nullable=True)

    # Explicit foreign_keys: lan_events.pinned_message_id (see LanEvent) is a
    # second, opposite-direction FK between these two tables, so this can't
    # be left to auto-detection.
    event = relationship("LanEvent", foreign_keys=[event_id])
    user = relationship("User")
    reply_to = relationship("ChatMessage", remote_side=[id])
    reactions = relationship(
        "ChatMessageReaction", cascade="all, delete-orphan", passive_deletes=False
    )
    mentions = relationship(
        "ChatMessageMention", cascade="all, delete-orphan", passive_deletes=False
    )


class ChatMessageReaction(Base):
    """One user's single reaction on one message — WhatsApp-style: at most one
    emoji per (message, user); picking a different emoji replaces it, picking
    the same one again removes it (see router_chat.py's react endpoint). Any
    emoji string is accepted (sourced from the OS's own emoji picker on the
    frontend), unlike Media/Activity reactions' fixed REACTION_EMOJI set."""
    __tablename__ = "chat_message_reactions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")

    __table_args__ = (UniqueConstraint("message_id", "user_id"),)


class ChatMessageMention(Base):
    """One (message, mentioned user) pair — who got @-mentioned in a given
    chat message. Populated by router_chat.py by matching @username tokens
    against the event's own attendee list (never a free-form regex token),
    so this table only ever holds mentions the autocomplete itself could
    have proposed. Drives both the frontend's server-confirmed highlighting
    (ChatMessageOut.mentions) and the targeted "you were mentioned" desktop
    notification (a recipient-scoped ActivityLog row — see router_chat.py's
    post_message)."""
    __tablename__ = "chat_message_mentions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")

    __table_args__ = (UniqueConstraint("message_id", "user_id"),)


class EventInvite(Base):
    __tablename__ = "event_invites"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, unique=True)
    code = Column(String, unique=True, index=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent")
    creator = relationship("User", foreign_keys=[created_by])


class ScheduleBlock(Base):
    """A proposed (or locked) game to play at an event — the unit of the Planning
    "Calendar View". Members approval-vote on which *hours* they'd play it
    (BlockVote); an organizer then locks a final window. Hour granularity lives
    only here and in BlockVote — LanEvent/EventRSVP stay day-granular."""
    __tablename__ = "schedule_blocks"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, index=True)
    game = Column(String, nullable=False)  # free text for the MVP (future: FK into a Game Library)
    # Rough proposed window (hour-granular, bounded by the event window). Optional.
    proposed_start = Column(DateTime, nullable=True)
    proposed_end = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="proposed")  # "proposed" | "locked"
    # Set when an organizer locks a final pick; surfaces on the event card / kiosk.
    locked_start = Column(DateTime, nullable=True)
    locked_end = Column(DateTime, nullable=True)
    # Calendar-view palette key (e.g. "peacock"), set at lock time. NULL = not
    # explicitly chosen — the frontend derives a deterministic default from
    # `game` (see calendarColors.ts) so older locked blocks still get a color.
    color = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent", back_populates="schedule_blocks")
    creator = relationship("User", foreign_keys=[created_by])
    votes = relationship("BlockVote", back_populates="block", cascade="all, delete-orphan")


class BlockVote(Base):
    """One member's approval of one hour-slot for one ScheduleBlock. Existence of
    a row = "I'd play this game, this hour". The slot is bounded server-side by
    the voter's own RSVP arrival/departure window (honest slots)."""
    __tablename__ = "block_votes"

    id = Column(Integer, primary_key=True, index=True)
    block_id = Column(Integer, ForeignKey("schedule_blocks.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    slot_start = Column(DateTime, nullable=False)  # top-of-the-hour the voter approves
    created_at = Column(DateTime, server_default=func.now())

    block = relationship("ScheduleBlock", back_populates="votes")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("block_id", "user_id", "slot_start"),)


class GearItem(Base):
    """A piece of BYO kit for an event — either a member's **pledge** ("I'm
    bringing a switch") or an admin **request** ("we need a 4th monitor") that a
    member can claim. Per-event + per-user, mirroring the EventRSVP pattern;
    surfaces on the event card and the kiosk. Gated by the `gear` feature flag.

    `pledged_by` NULL = an open request nobody has committed to yet; claiming a
    request just sets `pledged_by`. `is_request` distinguishes an admin-posted
    need from a member's spontaneous bring. The personal "gear locker" (carryover
    suggestions) is derived by grouping a user's past pledges by name."""
    __tablename__ = "gear_items"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)  # loose: network|power|display|peripheral|consumable|misc
    quantity = Column(Integer, default=1)
    note = Column(String, nullable=True)
    pledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_request = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent")
    pledger = relationship("User", foreign_keys=[pledged_by])
    creator = relationship("User", foreign_keys=[created_by])


class GroceryItem(Base):
    """A food/drink shopping item for an event — a shared, collaborative list any
    attendee can add to (mirrors GearItem's per-event shape, but simpler: no
    claim/request workflow, just a direct "who's buying this" assignment plus a
    bought/not-bought checkbox). Gated by the `groceries` feature flag. No price
    field on purpose — actual cost splitting stays in Treasury, entered by hand
    by the treasurer once the shopping is done.

    `assigned_to` NULL = nobody's picked it up yet. `quantity` is a free-text
    string (not an int) so it can hold units groceries actually need ("2kg",
    "1 pack", "6") rather than just a bare count."""
    __tablename__ = "grocery_items"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, index=True)
    category = Column(String, nullable=True)  # free text, e.g. "Snacks", "Boissons"
    name = Column(String, nullable=False)
    quantity = Column(String, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_bought = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent")
    assignee = relationship("User", foreign_keys=[assigned_to])
    creator = relationship("User", foreign_keys=[created_by])


class EventChecklist(Base):
    """A member's **private** packing checklist for one event — nobody else, not
    even an admin, can read another user's row. One per (event, user).

    The 9 fixed items are columns rather than data, mirroring `UserSetup`: the
    vocabulary is fixed and translated (`checklist.field.computer` etc.), so
    column names ARE the i18n keys. Member-invented extras live in
    `EventChecklistField`, capped at 10 in the router — same split as
    UserSetup/UserSetupField."""
    __tablename__ = "event_checklists"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    computer = Column(Boolean, default=False)
    screen = Column(Boolean, default=False)
    screen_psu = Column(Boolean, default=False)
    keyboard_mouse = Column(Boolean, default=False)
    cables = Column(Boolean, default=False)
    mousepad = Column(Boolean, default=False)
    headset = Column(Boolean, default=False)
    vanity = Column(Boolean, default=False)
    backpack = Column(Boolean, default=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_checklist_event_user"),)

    event = relationship("LanEvent")
    user = relationship("User")
    fields = relationship(
        "EventChecklistField", back_populates="checklist",
        cascade="all, delete-orphan", order_by="EventChecklistField.sort_order",
    )


class EventChecklistField(Base):
    """A member-invented checklist row ("Passport", "Chair") — custom ONLY, same
    split as UserSetupField. Capped in the router, not the schema."""
    __tablename__ = "event_checklist_fields"

    id = Column(Integer, primary_key=True, index=True)
    checklist_id = Column(Integer, ForeignKey("event_checklists.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    checked = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    checklist = relationship("EventChecklist", back_populates="fields")


class LiveStream(Base):
    __tablename__ = "livestreams"

    id = Column(Integer, primary_key=True, index=True)
    channel_name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    stream_type = Column(String, default="channel")  # "channel" or "clip"
    clip_slug = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])


class MediaItem(Base):
    __tablename__ = "media_items"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)   # "image" | "video"
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    caption = Column(String, nullable=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    uploader = relationship("User", foreign_keys=[uploaded_by])
    event = relationship("LanEvent", foreign_keys=[event_id])
    # The cascade is load-bearing, not tidiness: SQLite doesn't enforce foreign
    # keys by default and the delete endpoints call db.delete(item), so without
    # it every deleted photo leaves its reactions behind as orphans.
    #
    # Named reaction_rows, not reactions, deliberately: the router attaches a
    # `reactions` attribute holding the *aggregated* per-emoji counts that
    # MediaItemOut serialises, and that name has to stay free for it.
    reaction_rows = relationship("MediaReaction", back_populates="media", cascade="all, delete-orphan")


class MediaReaction(Base):
    """One member's emoji reaction to one media item. Existence of a row = the
    reaction; re-posting the same emoji removes it (a toggle). Mirrors BlockVote
    — a thin join row with a unique constraint — rather than a score column on
    MediaItem, so "best of" stays derived from the crew's actual votes."""
    __tablename__ = "media_reactions"

    id = Column(Integer, primary_key=True, index=True)
    media_id = Column(Integer, ForeignKey("media_items.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String, nullable=False)  # validated against router_media.REACTION_EMOJI
    created_at = Column(DateTime, server_default=func.now())

    media = relationship("MediaItem", back_populates="reaction_rows")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("media_id", "user_id", "emoji"),)


class RecapShare(Base):
    """A revocable public link to one event's recap. Token-only auth, mirroring
    the kiosk — but per-event, so it lives in a table rather than app_settings.

    The payload served against this token NEVER includes money: a public URL is
    the internet. See router_recap."""
    __tablename__ = "recap_shares"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, unique=True)
    token = Column(String, nullable=False, unique=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent", foreign_keys=[event_id])
    creator = relationship("User", foreign_keys=[created_by])


class UserSetup(Base):
    """One member's gaming PC. 1:1 with the user, created lazily on first save.

    **Why the 14 components are columns and not rows.** A generic
    setup_entries(slot, label, value) table would make "Graphic Card" *data* —
    English forever, on every install, seeded at migration time and unfixable
    without a data migration. This app enforces EN/FR parity in CI. So the fixed
    vocabulary is columns whose names ARE the i18n keys (`setup.field.graphics_card`),
    rendered through t(). Custom fields are user-authored and correctly NOT
    translated — which is exactly why they live in a different table with a
    `label` column. Not on `User`, either: 14 nullable columns on the table every
    auth check and every roster page loads, for a feature that ships off.

    **Why share_token lives here.** RecapShare needed its own table because it
    hangs off lan_events, which another feature owns. This table is already 1:1
    with the owner, so a second 1:1 table would be a join for nothing — and
    having no `created_by` column is what makes owner-mints-own-link structural:
    the owner IS user_id, and no route can name anybody else.
    """
    __tablename__ = "user_setups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    motherboard = Column(String, nullable=True)
    cpu = Column(String, nullable=True)
    cooler = Column(String, nullable=True)
    graphics_card = Column(String, nullable=True)
    ram = Column(String, nullable=True)
    power_supply = Column(String, nullable=True)
    fans = Column(String, nullable=True)
    storage = Column(String, nullable=True)
    pc_case = Column(String, nullable=True)  # `case` is a SQL keyword AND shadows sqlalchemy.case
    display = Column(String, nullable=True)
    keyboard = Column(String, nullable=True)
    mouse = Column(String, nullable=True)
    headset = Column(String, nullable=True)
    mic = Column(String, nullable=True)

    share_token = Column(String, nullable=True, unique=True, index=True)
    share_created_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    # Cascades are load-bearing, not tidiness: SQLite doesn't enforce FKs by
    # default and the routers call db.delete(). Same reason as MediaItem.reaction_rows.
    fields = relationship("UserSetupField", back_populates="setup", cascade="all, delete-orphan")
    photos = relationship("UserSetupPhoto", back_populates="setup", cascade="all, delete-orphan")
    reactions = relationship("SetupReaction", back_populates="setup", cascade="all, delete-orphan")


class UserSetupField(Base):
    """A member-invented field ("Chair", "Deskpad", "Streamdeck"). Custom ONLY —
    the 14 fixed components are columns on UserSetup so their labels can be
    translated. Capped in the router, not the schema."""
    __tablename__ = "user_setup_fields"

    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(Integer, ForeignKey("user_setups.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    value = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)

    setup = relationship("UserSetup", back_populates="fields")


class UserSetupPhoto(Base):
    """A photo of the rig. Rows rather than photo_1_url..photo_5_url: five columns
    would make deletion a shuffle and would bake the cap into the schema, where
    changing it later means a migration. Capped at 5 in the router instead."""
    __tablename__ = "user_setup_photos"

    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(Integer, ForeignKey("user_setups.id"), nullable=False, index=True)
    url = Column(String, nullable=False)
    caption = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    setup = relationship("UserSetup", back_populates="photos")


class SetupReaction(Base):
    """One member's emoji reaction to one member's rig — the MediaReaction shape
    applied to a setup. Row existence = the reaction; the same emoji again is a
    toggle-off. Unlike MediaItem, the relationship can simply be called
    `reactions`: SetupOut is built by hand in router_setup rather than
    from_attributes, so there's no monkey-patch fighting over the name."""
    __tablename__ = "setup_reactions"

    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(Integer, ForeignKey("user_setups.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String, nullable=False)  # validated against router_media.REACTION_EMOJI
    created_at = Column(DateTime, server_default=func.now())

    setup = relationship("UserSetup", back_populates="reactions")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("setup_id", "user_id", "emoji"),)


# NOTE: the old crew-wide `Invite` model was removed here (replaced by the
# per-event `EventInvite` above). Its `invites` table is intentionally left
# orphaned in existing databases — dropping it on SQLite means a table rebuild,
# which we avoid. Nothing maps to it anymore.


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    description = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    # NULL (every entry before this column existed, and every add_activity()
    # call that doesn't pass it) = broadcast, visible to everyone, unchanged
    # behavior. Set = visible only to that one user — router_activity.py's
    # list_activity/activity_ws filter on it. Lets a targeted notification
    # (e.g. a chat @mention) reuse the desktop app's existing activity
    # poll/toast/click pipeline instead of a second, parallel one.
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    # Named reaction_rows, not reactions — same reason as MediaItem: the router
    # attaches a `reactions` attribute holding the aggregated per-emoji counts
    # that ActivityLogOut serialises, and that name has to stay free for it.
    reaction_rows = relationship("ActivityReaction", back_populates="activity", cascade="all, delete-orphan")


class ActivityReaction(Base):
    """One member's emoji reaction to one activity feed entry — the MediaReaction
    shape applied to ActivityLog. Row existence = the reaction; the same emoji
    again removes it (a toggle)."""
    __tablename__ = "activity_reactions"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activity_logs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String, nullable=False)  # validated against router_media.REACTION_EMOJI
    created_at = Column(DateTime, server_default=func.now())

    activity = relationship("ActivityLog", back_populates="reaction_rows")
    user = relationship("User")

    __table_args__ = (UniqueConstraint("activity_id", "user_id", "emoji"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    admin = relationship("User", foreign_keys=[admin_id])


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")


class MiniGameRun(Base):
    """An opened, not-yet-submitted mini-game run.

    Exists only so a submitted score can be tied to a server-issued token with a known
    start time — without it, `score` is just a number a client asserted. `submitted_at`
    makes the token single-use, so replaying the same request can't duplicate a row.
    """

    __tablename__ = "minigame_runs"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    game = Column(String, nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    submitted_at = Column(DateTime, nullable=True)

    user = relationship("User")


class MiniGameScore(Base):
    """One finished, accepted run.

    `score` is deliberately generic: what it counts is defined per game in
    `minigames_registry.py`, because the planned games don't share a metric. `details`
    is that game's extra stats as a JSON object (kills/wave/level for NeonSurvivor) —
    displayed beside the score, never ranked on. Keeping them out of columns is what
    lets a new game ship without a migration.
    """

    __tablename__ = "minigame_scores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    game = Column(String, nullable=False, index=True)
    # Only solo runs are ever stored; the column exists so a future team-based game
    # can share this table instead of needing its own.
    mode = Column(String, nullable=False, default="solo")
    score = Column(Integer, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")

    # The leaderboard query is always "this game, best first".
    __table_args__ = (Index("ix_minigame_scores_game_score", "game", "score"),)


class EventReminderSent(Base):
    __tablename__ = "event_reminders_sent"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("event_id", "user_id"),)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LanCountdownSent(Base):
    """One row per countdown reminder delivered (J-10, J-7, J-1 before an
    event): the daily job's idempotency gate, so a restart or a second run on
    the same day never notifies anyone twice. See lan_reminders.py."""
    __tablename__ = "lan_countdown_sent"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    days_before = Column(Integer, nullable=False)
    sent_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("event_id", "user_id", "days_before"),)


class Game(Base):
    """One entry in the shared game catalog — seeded at install time from a curated
    list (`games_catalog_seed.json`, ~100 LAN-friendly titles) and grown by members
    adding a game the seed doesn't have. `is_custom` distinguishes the two, but both
    live in the same table/namespace on purpose: a member-added game is looked up by
    name (case-insensitive) before creating a new row, so two members typing the same
    title land on the same `Game` and "games in common" matching works on it too —
    the whole point of a *shared* catalog instead of per-user free text like GearItem.

    `default_max_players` is the catalog's own number (from the seed, or unset for a
    custom addition); a member can override it for their own copy via
    `UserGameLibrary.max_players_override` (e.g. they only own 2 controllers for a
    4-player game). `notes` carries the seed's "style/points forts" blurb — stored but
    not surfaced in the UI yet."""
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    genre = Column(String, nullable=True)
    default_max_players = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    is_custom = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])


class UserGameLibrary(Base):
    """A game a member owns/can host for the LAN. `max_players_override` is optional —
    when unset, the effective max is `Game.default_max_players`. `is_favorite` is the
    member's own "we play this at LANs" star, private to their library."""
    __tablename__ = "user_game_library"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    max_players_override = Column(Integer, nullable=True)
    is_favorite = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_game_library_user_game"),)

    user = relationship("User", back_populates="game_library")
    game = relationship("Game")


class UserGameWishlist(Base):
    """A game a member wants to play at the LAN — doesn't need to own it. Kept
    separate from the library (rather than a boolean flag on one table) since the
    two lists are managed and displayed independently, and a game can be in both
    (e.g. wanting more copies/controllers for a game you already own)."""
    __tablename__ = "user_game_wishlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_game_wishlist_user_game"),)

    user = relationship("User", back_populates="game_wishlist")
    game = relationship("Game")

# ── Trophies ─────────────────────────────────────────────────────────────────
# Crew-defined honours awarded per event. Deliberately NOT badges.py: badges are
# facts derivable from other data, recomputed on read and labelled by i18n code.
# A trophy is a human decision (a vote, or an admin's pick) — not derivable from
# anything — so it is stored, and its name/description are free text written by
# the crew in their own language, like an event title.

class Trophy(Base):
    """A trophy definition in the instance's "trophy cabinet". Reusable across
    editions: the same "Golden Rage-Quit" awarded every year builds a lineage of
    winners. Archived (never deleted) once someone has won it."""
    __tablename__ = "trophies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    emoji = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    archived_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    editions = relationship("EventTrophy", back_populates="trophy", cascade="all, delete-orphan")


class EventTrophy(Base):
    """One trophy put in play at one event — an "edition".

    mode:   "vote" (attendees elect the winner) | "direct" (an admin picks)
    status: "draft" (admins only) → "voting" (vote mode) → "closed" (tally in,
            winners proposed, still hidden) → "revealed" (public, permanent).
            Direct mode goes draft → revealed."""
    __tablename__ = "event_trophies"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=False, index=True)
    trophy_id = Column(Integer, ForeignKey("trophies.id"), nullable=False, index=True)
    mode = Column(String, nullable=False, default="vote")
    status = Column(String, nullable=False, default="draft")
    revealed_at = Column(DateTime, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("event_id", "trophy_id", name="uq_event_trophy"),)

    event = relationship("LanEvent", back_populates="trophy_editions")
    trophy = relationship("Trophy", back_populates="editions")
    winners = relationship("EventTrophyWinner", back_populates="edition", cascade="all, delete-orphan")
    votes = relationship("TrophyVote", back_populates="edition", cascade="all, delete-orphan")


class EventTrophyWinner(Base):
    """A winner of one edition. Several rows = co-winners (a tied vote, or an
    admin naming a duo). `vote_count` is set when the winner came from a vote."""
    __tablename__ = "event_trophy_winners"

    id = Column(Integer, primary_key=True, index=True)
    event_trophy_id = Column(Integer, ForeignKey("event_trophies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    citation = Column(String, nullable=True)
    vote_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("event_trophy_id", "user_id", name="uq_event_trophy_winner"),)

    edition = relationship("EventTrophy", back_populates="winners")
    user = relationship("User")


class TrophyVote(Base):
    """One attendee's ballot for one edition — one vote each, changeable until
    the vote closes. Secret: the API never exposes voter → nominee to anyone
    but the voter themself."""
    __tablename__ = "trophy_votes"

    id = Column(Integer, primary_key=True, index=True)
    event_trophy_id = Column(Integer, ForeignKey("event_trophies.id"), nullable=False, index=True)
    voter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nominee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("event_trophy_id", "voter_id", name="uq_trophy_vote"),)

    edition = relationship("EventTrophy", back_populates="votes")


# ── League of Legends LAN stats ──────────────────────────────────────────────
# Every LoL game that ends during a LAN — fun customs, ARAM, tournament
# matches alike — sent by a member's desktop app from the League Client's own
# end-of-game block (see lol_capture.py for the shape, router_lol.py for the
# rules). Stored, unlike tournament stats: a finished game is a fact nothing
# else in the app could re-derive. Aggregates are still computed on read.

class LolMatch(Base):
    """One captured game. `riot_game_id` is Riot's own id, unique, so the same
    game sent by several members' apps is kept once. `event_id` is the LAN it
    was played during, or NULL for a game played outside any LAN (0032)."""
    __tablename__ = "lol_matches"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("lan_events.id"), nullable=True, index=True)
    riot_game_id = Column(String, nullable=False, unique=True, index=True)
    game_mode = Column(String, nullable=True)   # Riot's own: CLASSIC, ARAM, ...
    queue_type = Column(String, nullable=True)
    is_custom = Column(Boolean, default=False, nullable=False)
    duration_s = Column(Integer, nullable=True)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    event = relationship("LanEvent", back_populates="lol_matches")
    submitter = relationship("User", foreign_keys=[submitted_by])
    players = relationship("LolMatchPlayer", back_populates="match", cascade="all, delete-orphan")


class LolMatchPlayer(Base):
    """One player's line in a captured game. `user_id` is resolved from the
    Riot ID at capture time, and back-filled when a member sets their Riot ID
    later (router_users.update_user) — so it's NULL only for a custom-game
    player nobody has claimed yet. Players of a matchmade game who aren't crew
    members are never stored at all."""
    __tablename__ = "lol_match_players"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("lol_matches.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    riot_id = Column(String, nullable=False)
    riot_id_key = Column(String, nullable=False, index=True)
    champion = Column(String, nullable=True)
    team_id = Column(Integer, nullable=True)
    win = Column(Boolean, default=False, nullable=False)
    kills = Column(Integer, default=0, nullable=False)
    deaths = Column(Integer, default=0, nullable=False)
    assists = Column(Integer, default=0, nullable=False)
    damage = Column(Integer, default=0, nullable=False)  # to champions

    __table_args__ = (UniqueConstraint("match_id", "riot_id_key", name="uq_lol_match_player"),)

    match = relationship("LolMatch", back_populates="players")
    user = relationship("User")
