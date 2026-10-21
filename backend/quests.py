"""Monthly contract — XP between two LANs.

Each calendar month (instance timezone) has a contract of up to three
objectives; meeting two of them that month is worth `xp.QUEST_XP`, enough for a
booster. Decided by CrossWax on 2026-10-19
(md/2.features/cards/cards_v2_quetes_presence_echanges.md).

Only the choice of objectives is stored (MonthlyContract): drawn among the
objectives available that month, the first time anyone looks at it, and kept.
Availability moves — a chat room opens, the next LAN gets created — and a
contract that moved with it would change what's asked mid-month, and past
months' XP. Progress is computed on read from facts other features own, like
xp.py: there is nothing to claim, and nothing to farm beyond the facts.
"""
import json
import logging
import secrets
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from discord_notify import send_discord_message
from event_utils import _instance_tz, local_day_start_utc, local_today
from models import (
    AppSetting, BlockVote, ChatMessage, EventRSVP, LanEvent, LolMatch, LolMatchPlayer, LolMatchSubmitter,
    MiniGameScore,
    MonthlyContract, ScheduleBlock,
)
from router_settings import get_setting, is_feature_enabled
from xp import CHAT_MIN_CHARS, QUEST_XP

logger = logging.getLogger(__name__)

# Not random.random(): like the boosters, nobody gets to predict the draw.
_rng = secrets.SystemRandom()

# ── Rules: the one place to tune the contract ────────────────────────────────

OBJECTIVES_PER_CONTRACT = 3
# Objectives to meet; fewer when fewer were available that month.
REQUIRED = 2

# What each objective asks for, within the month.
TARGETS = {
    "lol_squad": 5,      # LoL games your own app sent, with another crew member in them
    "minigame": 3,       # mini-game runs that made the leaderboard
    "chat_days": 5,      # days with a Craving Chat message that counts
    "rsvp_next": 1,      # an answer to the next LAN's RSVP
    "planning_vote": 1,  # a vote on a planning slot
}

Window = Tuple[datetime, datetime]


# ── Months ────────────────────────────────────────────────────────────────────

def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def month_days(key: str) -> Tuple[date, date]:
    """(its first day, the first day of the next month)."""
    year, month = (int(part) for part in key.split("-"))
    return date(year, month, 1), date(year + month // 12, month % 12 + 1, 1)


def month_window(db: Session, key: str) -> Window:
    """The month as naive UTC instants, the way the app stores them."""
    first, after = month_days(key)
    return local_day_start_utc(db, first), local_day_start_utc(db, after)


# ── Progress: per member, from the facts ──────────────────────────────────────

def _lol_squad(db: Session, window: Window, objective: dict) -> Dict[int, int]:
    """Games with at least two crew accounts in them, on the same side or not
    (a crew 1v1 counts as much as a premade) — counted for a member only when
    their own app sent the game (lol_match_submitters): a block typed by hand
    can't fill someone else's objective (D-3 of the 2026-10-20 review)."""
    start, end = window
    crew: Dict[int, Set[int]] = defaultdict(set)
    rows = (
        db.query(LolMatchPlayer.match_id, LolMatchPlayer.user_id)
        .join(LolMatch, LolMatch.id == LolMatchPlayer.match_id)
        .filter(LolMatch.created_at >= start, LolMatch.created_at < end, LolMatchPlayer.user_id.isnot(None))
        .all()
    )
    for match_id, uid in rows:
        crew[match_id].add(uid)
    sent: Dict[int, Set[int]] = defaultdict(set)
    if crew:
        for match_id, uid in (
            db.query(LolMatchSubmitter.match_id, LolMatchSubmitter.user_id)
            .filter(LolMatchSubmitter.match_id.in_(list(crew)))
            .all()
        ):
            sent[match_id].add(uid)
    games: Counter = Counter()
    for match_id, members in crew.items():
        if len(members) >= 2:
            games.update(members & sent[match_id])
    return games


def _minigame(db: Session, window: Window, objective: dict) -> Dict[int, int]:
    """Runs that made the leaderboard: a rejected submission stores no score."""
    start, end = window
    return dict(
        db.query(MiniGameScore.user_id, func.count())
        .filter(MiniGameScore.created_at >= start, MiniGameScore.created_at < end)
        .group_by(MiniGameScore.user_id)
        .all()
    )


def _chat_days(db: Session, window: Window, objective: dict) -> Dict[int, int]:
    """Local days with a message that xp.py would count: three characters or
    more, and not the author's previous message again."""
    start, end = window
    tz = _instance_tz(db)
    rows = (
        db.query(ChatMessage.user_id, ChatMessage.created_at, ChatMessage.content)
        .filter(ChatMessage.created_at >= start, ChatMessage.created_at < end)
        .order_by(ChatMessage.user_id, ChatMessage.created_at, ChatMessage.id)
        .all()
    )
    days: Dict[int, Set[date]] = defaultdict(set)
    previous: Dict[int, str] = {}
    for uid, at, content in rows:
        text = " ".join((content or "").split()).casefold()
        repeated = previous.get(uid) == text
        previous[uid] = text
        if len(text) < CHAT_MIN_CHARS or repeated:
            continue
        days[uid].add(at.replace(tzinfo=timezone.utc).astimezone(tz).date())
    return {uid: len(d) for uid, d in days.items()}


def _rsvp_next(db: Session, window: Window, objective: dict) -> Dict[int, int]:
    """Anyone with an answer for that LAN, given during the month or before."""
    rows = db.query(EventRSVP.user_id).filter(EventRSVP.event_id == objective.get("event_id")).all()
    return {uid: 1 for (uid,) in rows}


def _planning_vote(db: Session, window: Window, objective: dict) -> Dict[int, int]:
    start, end = window
    return dict(
        db.query(BlockVote.user_id, func.count())
        .filter(BlockVote.created_at >= start, BlockVote.created_at < end)
        .group_by(BlockVote.user_id)
        .all()
    )


# ── Availability: what can be asked this month ────────────────────────────────
# Each returns the objective's extra parameters ({} for none), or None when it
# can't be asked. Checked once, when the month's contract is drawn.

def _offer_lol_squad(db: Session, today: date) -> Optional[dict]:
    return {} if is_feature_enabled(db, "lol_stats") else None


def _offer_minigame(db: Session, today: date) -> Optional[dict]:
    return {} if is_feature_enabled(db, "minigames") else None


def _offer_chat_days(db: Session, today: date) -> Optional[dict]:
    """Only if some LAN's room is open on enough of the month's remaining days
    (Settings → Craving Chat decides when rooms open and close)."""
    if not is_feature_enabled(db, "craving_chat"):
        return None
    from router_chat import _window_open  # the room rules live there

    events = db.query(LanEvent).all()
    _, after = month_days(month_key(today))
    open_days = 0
    for n in range((after - today).days):
        day = today + timedelta(days=n)
        if any(_window_open(db, e, day) for e in events):
            open_days += 1
            if open_days >= TARGETS["chat_days"]:
                return {}
    return None


def _offer_rsvp_next(db: Session, today: date) -> Optional[dict]:
    """The next LAN, asked once per LAN: a member who answered long ago meets
    it from day one, which is fine once, not every month."""
    upcoming = (
        db.query(LanEvent)
        .filter(LanEvent.start_date > today)
        .order_by(LanEvent.start_date, LanEvent.id)
        .first()
    )
    if upcoming is None:
        return None
    for contract in db.query(MonthlyContract).all():
        if any(o["code"] == "rsvp_next" and o.get("event_id") == upcoming.id for o in objectives(contract)):
            return None
    return {"event_id": upcoming.id}


def _offer_planning_vote(db: Session, today: date) -> Optional[dict]:
    """Only while a slot of a LAN to come (or under way) is up for a vote."""
    if not is_feature_enabled(db, "planning"):
        return None
    slot = (
        db.query(ScheduleBlock.id)
        .join(LanEvent, LanEvent.id == ScheduleBlock.event_id)
        .filter(ScheduleBlock.status == "proposed", LanEvent.end_date >= today)
        .first()
    )
    return {} if slot else None


# code → (availability, progress). The codes are i18n keys on the frontend
# (`quests.objective.<code>`).
CATALOGUE: Dict[str, Tuple[Callable[[Session, date], Optional[dict]], Callable[[Session, Window, dict], Dict[int, int]]]] = {
    "lol_squad": (_offer_lol_squad, _lol_squad),
    "minigame": (_offer_minigame, _minigame),
    "chat_days": (_offer_chat_days, _chat_days),
    "rsvp_next": (_offer_rsvp_next, _rsvp_next),
    "planning_vote": (_offer_planning_vote, _planning_vote),
}


# ── The contract ──────────────────────────────────────────────────────────────

def objectives(contract: Optional[MonthlyContract]) -> List[dict]:
    if contract is None:
        return []
    try:
        drawn = json.loads(contract.objectives)
    except ValueError:
        return []
    return [o for o in drawn if isinstance(o, dict) and o.get("code") in CATALOGUE]


def _draw(db: Session, today: date) -> List[dict]:
    """Up to three of the objectives available, at random — the ones last
    month didn't ask first, so two months in a row differ when they can."""
    first, _ = month_days(month_key(today))
    asked_last_month = {o["code"] for o in objectives(db.get(MonthlyContract, month_key(first - timedelta(days=1))))}
    offered = []
    for code, (offer, _progress) in CATALOGUE.items():
        params = offer(db, today)
        if params is not None:
            offered.append({"code": code, "target": TARGETS[code], **params})
    fresh = [o for o in offered if o["code"] not in asked_last_month]
    again = [o for o in offered if o["code"] in asked_last_month]
    _rng.shuffle(fresh)
    _rng.shuffle(again)
    return (fresh + again)[:OBJECTIVES_PER_CONTRACT]


def current_contract(db: Session, today: Optional[date] = None) -> MonthlyContract:
    """This month's contract, drawn if nobody has looked at it yet. The caller
    commits; two first looks at once race on the primary key — the route rolls
    back and runs it again, which then finds the winner's draw."""
    today = today or local_today(db)
    key = month_key(today)
    contract = db.get(MonthlyContract, key)
    if contract is None:
        drawn = _draw(db, today)
        contract = MonthlyContract(month=key, objectives=json.dumps(drawn), required=min(REQUIRED, len(drawn)))
        db.add(contract)
        db.flush()
    return contract


def _progress(db: Session, contract: MonthlyContract) -> List[Tuple[dict, Dict[int, int]]]:
    window = month_window(db, contract.month)
    return [(o, CATALOGUE[o["code"]][1](db, window, o)) for o in objectives(contract)]


def _met_by(db: Session, contract: MonthlyContract) -> Set[int]:
    if contract.required <= 0:
        return set()
    met: Counter = Counter()
    for objective, progress in _progress(db, contract):
        met.update(uid for uid, n in progress.items() if n >= objective["target"])
    return {uid for uid, n in met.items() if n >= contract.required}


def contracts_met(db: Session) -> Dict[int, int]:
    """How many monthly contracts each member has met — xp.py pays for them.
    The month under way counts as soon as it's met."""
    met: Counter = Counter()
    for contract in db.query(MonthlyContract).all():
        met.update(_met_by(db, contract))
    return dict(met)


def contract_view(db: Session, contract: MonthlyContract, user_id: int, today: Optional[date] = None) -> dict:
    """The contract as one member sees it, with their progress."""
    today = today or local_today(db)
    _, after = month_days(contract.month)
    items = []
    for objective, progress in _progress(db, contract):
        n = progress.get(user_id, 0)
        item = {
            "code": objective["code"],
            "target": objective["target"],
            "progress": min(n, objective["target"]),
            "done": n >= objective["target"],
        }
        if objective.get("event_id"):
            event = db.get(LanEvent, objective["event_id"])
            item["event_title"] = event.title if event else None
        items.append(item)
    return {
        "month": contract.month,
        "ends_on": after - timedelta(days=1),
        "days_left": max((after - today).days, 0),
        "required": contract.required,
        "xp": QUEST_XP,
        "done": contract.required > 0 and sum(i["done"] for i in items) >= contract.required,
        "objectives": items,
    }


# ── The announcement on the 1st ───────────────────────────────────────────────

ANNOUNCED_KEY = "quests_announced_month"  # internal, not an admin setting
FR_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
DISCORD_LINES = {
    "lol_squad": "Joue {target} parties de LoL avec la crew",
    "minigame": "Joue {target} parties de mini-jeu (comptées au classement)",
    "chat_days": "Parle sur le Craving Chat {target} jours différents",
    "rsvp_next": "Réponds à l'inscription de {event}",
    "planning_vote": "Vote dans le planning",
}


def announcement(db: Session, contract: MonthlyContract) -> str:
    """The Discord post, in French (the crew's) with one line of English."""
    drawn = objectives(contract)
    year, month = contract.month.split("-")
    n, required = len(drawn), contract.required
    goal = f"{required} objectif{'s' if required > 1 else ''} sur {n}"
    lines = [f"📜 **Contrat du mois · {FR_MONTHS[int(month) - 1]} {year}** — remplis {goal} : +{QUEST_XP} XP, "
             "de quoi s'offrir un booster."]
    for o in drawn:
        event = db.get(LanEvent, o["event_id"]) if o.get("event_id") else None
        lines.append("• " + DISCORD_LINES[o["code"]].format(
            target=o["target"], event=event.title if event else "la prochaine LAN",
        ))
    lines.append(f"_Monthly contract: meet {required} of {n} objectives this month for +{QUEST_XP} XP._")
    base_url = (get_setting(db, "app_base_url") or "").rstrip("/")
    if base_url:
        lines.append(base_url)
    return "\n".join(lines)


def announce_monthly_contract() -> None:
    """Scheduled job, the 1st of the month: draw the month's contract if nobody
    has yet, and post it on Discord, once a month. Opens its own session, like
    the reminders."""
    db = SessionLocal()
    try:
        if not is_feature_enabled(db, "quests"):
            return
        contract = current_contract(db)
        if not objectives(contract) or get_setting(db, ANNOUNCED_KEY) == contract.month:
            db.commit()
            return
        row = db.query(AppSetting).filter(AppSetting.key == ANNOUNCED_KEY).first()
        if row:
            row.value = contract.month
        else:
            db.add(AppSetting(key=ANNOUNCED_KEY, value=contract.month))
        # Recorded before posting: a crash may skip a post, never send one twice.
        db.commit()
        send_discord_message(db, announcement(db, contract))
    except Exception:
        logger.exception("Monthly contract announcement failed")
        db.rollback()
    finally:
        db.close()
