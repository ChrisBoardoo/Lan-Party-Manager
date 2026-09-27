"""Trophies — /api/trophies

Crew-defined honours, awarded per event and kept forever on the winners'
profiles. Two levels, managed in two places:

- The **cabinet** (`/`): trophy definitions — name, emoji or image,
  description — owned by the instance and reusable from one LAN to the next.
  Admin-only, managed from Settings.
- **Editions** (`/events/{event_id}`, `/editions/{id}`): a trophy put in play at
  one event, either voted by the attendees or picked directly by an admin.
  Managed from the event page, since that's where the admin is on the day.

Lifecycle of an edition (every transition is enforced here, not in the UI):

    draft ──(vote mode)──> voting ──> closed ──> revealed
      └──────────(direct mode: winner picked)────────^

Voting is secret: no response ever pairs a voter with a nominee, not even for an
admin. A member sees their own ballot (`my_vote`) and the turnout; an admin sees
the totals once the vote is closed. Winners stay hidden from members until the
reveal — which is what drives the kiosk's ceremony.

Why this isn't badges.py: badges are facts derivable from other data, so they
are recomputed on read. A vote isn't derivable from anything, so it's stored.
"""
from collections import Counter
from datetime import datetime
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from activity import add_activity
from auth import require_admin
from database import get_db
from models import EventRSVP, EventTrophy, EventTrophyWinner, LanEvent, Trophy, TrophyVote, User
from router_settings import require_feature
from schemas import (
    TrophyBrief, TrophyCreate, TrophyEditionCreate, TrophyEditionOut, TrophyEditionUpdate,
    TrophyLastAward, TrophyOut, TrophyRevealIn, TrophyTallyLine, TrophyUpdate, TrophyVoteIn,
    TrophyWinnerOut, TrophyWinnersIn, UserTrophyOut,
)
from uploads import remove_upload, save_image_upload

router = APIRouter()

# (from, to) → the mode that transition requires (None = either). Revealing
# isn't here: it has its own endpoint, because it has side effects.
_TRANSITIONS = {
    ("draft", "voting"): "vote",
    ("voting", "draft"): None,     # pause the vote; ballots are kept
    ("voting", "closed"): None,    # count the ballots, propose the winners
    ("closed", "voting"): None,    # reopen; proposed winners are dropped
    ("revealed", "closed"): "vote",   # un-reveal, to fix a mistake
    ("revealed", "draft"): "direct",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _attendee_ids(db: Session, event_id: int) -> set[int]:
    """Active members with an "in" RSVP — who may vote, and be nominated."""
    rows = (
        db.query(EventRSVP.user_id)
        .join(User, User.id == EventRSVP.user_id)
        .filter(EventRSVP.event_id == event_id, EventRSVP.status == "in", User.is_active == True)  # noqa: E712
        .all()
    )
    return {r[0] for r in rows}


def _brief(t: Trophy) -> TrophyBrief:
    return TrophyBrief(id=t.id, name=t.name, emoji=t.emoji, image_url=t.image_url, description=t.description)


def _trophy_or_404(db: Session, trophy_id: int) -> Trophy:
    t = db.query(Trophy).filter(Trophy.id == trophy_id).first()
    if not t:
        raise HTTPException(404, "Trophy not found")
    return t


def _edition_or_404(db: Session, edition_id: int) -> EventTrophy:
    e = (
        db.query(EventTrophy)
        .options(
            selectinload(EventTrophy.trophy),
            selectinload(EventTrophy.winners).selectinload(EventTrophyWinner.user),
            selectinload(EventTrophy.votes),
        )
        .filter(EventTrophy.id == edition_id)
        .first()
    )
    if not e:
        raise HTTPException(404, "Edition not found")
    return e


def _tally(e: EventTrophy) -> list[tuple[int, int]]:
    """(nominee_id, votes), most voted first."""
    counts = Counter(v.nominee_id for v in e.votes)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _sorted_winners(e: EventTrophy) -> list[EventTrophyWinner]:
    return sorted(e.winners, key=lambda w: (-(w.vote_count or 0), (w.user.username if w.user else "").lower()))


def _edition_out(db: Session, e: EventTrophy, viewer: User, eligible: set[int]) -> TrophyEditionOut:
    is_admin = viewer.role == "admin"
    winners: list[TrophyWinnerOut] = []
    if is_admin or e.status == "revealed":
        winners = [
            TrophyWinnerOut(
                user_id=w.user_id,
                username=w.user.username if w.user else "?",
                avatar_url=w.user.avatar_url if w.user else None,
                citation=w.citation,
                # Vote totals are for the organizers; the room just gets the winner.
                vote_count=w.vote_count if is_admin else None,
            )
            for w in _sorted_winners(e)
        ]
    tally = None
    if is_admin and e.mode == "vote" and e.status in ("closed", "revealed"):
        counts = _tally(e)
        users = {u.id: u for u in db.query(User).filter(User.id.in_([uid for uid, _ in counts])).all()} if counts else {}
        tally = [
            TrophyTallyLine(user_id=uid, username=users[uid].username, avatar_url=users[uid].avatar_url, votes=n)
            for uid, n in counts if uid in users
        ]
    return TrophyEditionOut(
        id=e.id,
        event_id=e.event_id,
        trophy=_brief(e.trophy),
        mode=e.mode,
        status=e.status,
        revealed_at=e.revealed_at,
        winners=winners,
        voters_count=len(e.votes),
        eligible_count=len(eligible),
        my_vote=next((v.nominee_id for v in e.votes if v.voter_id == viewer.id), None),
        tally=tally,
    )


def revealed_editions(db: Session, event_id: int) -> list[EventTrophy]:
    """An event's revealed editions, in reveal order — for the recap and kiosk."""
    return (
        db.query(EventTrophy)
        .options(
            selectinload(EventTrophy.trophy),
            selectinload(EventTrophy.winners).selectinload(EventTrophyWinner.user),
        )
        .filter(EventTrophy.event_id == event_id, EventTrophy.status == "revealed")
        .order_by(EventTrophy.revealed_at, EventTrophy.id)
        .all()
    )


def _trophy_label(t: Trophy) -> str:
    return f"{t.emoji or '🏆'} {t.name}"


# ── Cabinet (admin) ───────────────────────────────────────────────────────────

def _cabinet_out(db: Session, trophies: Iterable[Trophy]) -> list[TrophyOut]:
    out = []
    for t in trophies:
        revealed = [e for e in t.editions if e.status == "revealed"]
        awarded = sum(len(e.winners) for e in revealed)
        last = None
        if revealed:
            latest = max(revealed, key=lambda e: (e.revealed_at or datetime.min, e.id))
            if latest.winners:
                names = ", ".join(w.user.username for w in _sorted_winners(latest) if w.user)
                last = TrophyLastAward(username=names, event_title=latest.event.title if latest.event else "")
        out.append(TrophyOut(
            **_brief(t).model_dump(), sort_order=t.sort_order or 0, archived_at=t.archived_at,
            awarded_count=awarded, last_award=last,
        ))
    return out


def _cabinet_query(db: Session):
    return db.query(Trophy).options(
        selectinload(Trophy.editions).selectinload(EventTrophy.winners).selectinload(EventTrophyWinner.user),
        selectinload(Trophy.editions).selectinload(EventTrophy.event),
    )


@router.get("/", response_model=list[TrophyOut])
def list_trophies(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """The whole cabinet, archived last."""
    trophies = _cabinet_query(db).all()
    trophies.sort(key=lambda t: (t.archived_at is not None, t.sort_order or 0, t.name.lower()))
    return _cabinet_out(db, trophies)


@router.post("/", response_model=TrophyOut, status_code=201)
def create_trophy(data: TrophyCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    t = Trophy(
        name=data.name.strip(),
        emoji=(data.emoji or "").strip() or None,
        description=(data.description or "").strip() or None,
        sort_order=data.sort_order or 0,
        created_by=admin.id,
    )
    db.add(t)
    db.commit()
    return _cabinet_out(db, [_cabinet_query(db).filter(Trophy.id == t.id).one()])[0]


@router.put("/{trophy_id}", response_model=TrophyOut)
def update_trophy(
    trophy_id: int, data: TrophyUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    t = _trophy_or_404(db, trophy_id)
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields and fields["name"]:
        t.name = fields["name"].strip()
    if "emoji" in fields:
        t.emoji = (fields["emoji"] or "").strip() or None
    if "description" in fields:
        t.description = (fields["description"] or "").strip() or None
    if fields.get("sort_order") is not None:
        t.sort_order = fields["sort_order"]
    if fields.get("archived") is not None:
        t.archived_at = (t.archived_at or datetime.utcnow()) if fields["archived"] else None
    db.commit()
    return _cabinet_out(db, [_cabinet_query(db).filter(Trophy.id == t.id).one()])[0]


@router.delete("/{trophy_id}")
def delete_trophy(trophy_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Only a trophy nobody has won yet can be deleted — history is archived,
    never erased."""
    t = _trophy_or_404(db, trophy_id)
    if any(e.status == "revealed" and e.winners for e in t.editions):
        raise HTTPException(409, "This trophy has been awarded — archive it instead")
    remove_upload(t.image_url, "trophies")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/{trophy_id}/image", response_model=TrophyOut)
async def upload_trophy_image(
    trophy_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    t = _trophy_or_404(db, trophy_id)
    t.image_url = await save_image_upload(
        file, subdir="trophies", prefix=f"trophy_{trophy_id}", box=(512, 512), quality=85, replaces=t.image_url,
    )
    db.commit()
    return _cabinet_out(db, [_cabinet_query(db).filter(Trophy.id == t.id).one()])[0]


@router.delete("/{trophy_id}/image", response_model=TrophyOut)
def delete_trophy_image(trophy_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    t = _trophy_or_404(db, trophy_id)
    remove_upload(t.image_url, "trophies")
    t.image_url = None
    db.commit()
    return _cabinet_out(db, [_cabinet_query(db).filter(Trophy.id == t.id).one()])[0]


# ── Editions ──────────────────────────────────────────────────────────────────

@router.get("/events/{event_id}", response_model=list[TrophyEditionOut])
def list_editions(event_id: int, db: Session = Depends(get_db), viewer: User = Depends(require_feature("trophies"))):
    """An event's trophies as the viewer may see them: drafts are admin-only."""
    q = (
        db.query(EventTrophy)
        .options(
            selectinload(EventTrophy.trophy),
            selectinload(EventTrophy.winners).selectinload(EventTrophyWinner.user),
            selectinload(EventTrophy.votes),
        )
        .filter(EventTrophy.event_id == event_id)
    )
    if viewer.role != "admin":
        q = q.filter(EventTrophy.status != "draft")
    editions = sorted(q.all(), key=lambda e: (e.sort_order or 0, e.id))
    eligible = _attendee_ids(db, event_id)
    return [_edition_out(db, e, viewer, eligible) for e in editions]


@router.post("/events/{event_id}", response_model=TrophyEditionOut, status_code=201)
def add_edition(
    event_id: int, data: TrophyEditionCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    if not db.query(LanEvent).filter(LanEvent.id == event_id).first():
        raise HTTPException(404, "Event not found")
    trophy = _trophy_or_404(db, data.trophy_id)
    if trophy.archived_at is not None:
        raise HTTPException(400, "This trophy is archived")
    if db.query(EventTrophy).filter(EventTrophy.event_id == event_id, EventTrophy.trophy_id == trophy.id).first():
        raise HTTPException(409, "This trophy is already in play at this event")
    count = db.query(EventTrophy).filter(EventTrophy.event_id == event_id).count()
    e = EventTrophy(event_id=event_id, trophy_id=trophy.id, mode=data.mode, status="draft", sort_order=count)
    db.add(e)
    db.commit()
    return _edition_out(db, _edition_or_404(db, e.id), admin, _attendee_ids(db, event_id))


@router.patch("/editions/{edition_id}", response_model=TrophyEditionOut)
def update_edition(
    edition_id: int, data: TrophyEditionUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    e = _edition_or_404(db, edition_id)
    fields = data.model_dump(exclude_unset=True)

    if fields.get("mode") and fields["mode"] != e.mode:
        if e.status != "draft":
            raise HTTPException(400, "The mode can only change while the trophy is a draft")
        e.mode = fields["mode"]
        e.winners.clear()  # a direct pick doesn't carry over into a vote, nor back

    target = fields.get("status")
    if target and target != e.status:
        required = _TRANSITIONS.get((e.status, target), "missing")
        if required == "missing" or (required is not None and required != e.mode):
            raise HTTPException(400, f"Can't go from {e.status} to {target}")
        if target == "closed" and e.status == "voting":
            # Most votes wins; a tie makes co-winners (same rule as badges.py).
            e.winners.clear()
            db.flush()
            counts = _tally(e)
            if counts:
                top = counts[0][1]
                for uid, n in counts:
                    if n == top:
                        e.winners.append(EventTrophyWinner(user_id=uid, vote_count=n))
        elif target == "voting" and e.status == "closed":
            e.winners.clear()
        if e.status == "revealed":
            e.revealed_at = None
        e.status = target

    if fields.get("sort_order") is not None:
        e.sort_order = fields["sort_order"]
    db.commit()
    return _edition_out(db, _edition_or_404(db, e.id), admin, _attendee_ids(db, e.event_id))


@router.delete("/editions/{edition_id}")
def delete_edition(edition_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    e = _edition_or_404(db, edition_id)
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.put("/editions/{edition_id}/winners", response_model=TrophyEditionOut)
def set_winners(
    edition_id: int, data: TrophyWinnersIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    """Pick (direct mode) or adjust (after a vote: tie-break, citation) the
    winners. Not while a vote is running — that would pre-empt it."""
    e = _edition_or_404(db, edition_id)
    if e.status == "voting":
        raise HTTPException(400, "Close the vote first")
    ids = list(dict.fromkeys(w.user_id for w in data.winners))
    found = {u.id for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else set()
    if set(ids) - found:
        raise HTTPException(404, "User not found")
    if e.status == "revealed" and not ids:
        raise HTTPException(400, "A revealed trophy needs a winner — un-reveal it first")

    votes = dict(_tally(e)) if e.mode == "vote" else {}
    citations = {w.user_id: (w.citation or "").strip() or None for w in data.winners}
    e.winners.clear()
    db.flush()
    for uid in ids:
        e.winners.append(EventTrophyWinner(user_id=uid, citation=citations[uid], vote_count=votes.get(uid)))
    db.commit()
    return _edition_out(db, _edition_or_404(db, e.id), admin, _attendee_ids(db, e.event_id))


@router.post("/editions/{edition_id}/vote", response_model=TrophyEditionOut)
def vote(
    edition_id: int, data: TrophyVoteIn, db: Session = Depends(get_db), voter: User = Depends(require_feature("trophies"))
):
    """Cast or change a ballot. Attendees only, one each, not for yourself."""
    e = _edition_or_404(db, edition_id)
    if e.status != "voting":
        raise HTTPException(400, "Voting isn't open for this trophy")
    eligible = _attendee_ids(db, e.event_id)
    if voter.id not in eligible:
        raise HTTPException(403, "Only this event's attendees can vote")
    if data.nominee_id == voter.id:
        raise HTTPException(400, "You can't vote for yourself")
    if data.nominee_id not in eligible:
        raise HTTPException(400, "You can only vote for an attendee")
    ballot = next((v for v in e.votes if v.voter_id == voter.id), None)
    if ballot:
        ballot.nominee_id = data.nominee_id
    else:
        e.votes.append(TrophyVote(voter_id=voter.id, nominee_id=data.nominee_id))
    db.commit()
    return _edition_out(db, _edition_or_404(db, e.id), voter, eligible)


@router.post("/editions/{edition_id}/reveal", response_model=TrophyEditionOut)
def reveal(
    edition_id: int, data: TrophyRevealIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    """Make the winner(s) public: profile showcase, recap, the kiosk ceremony
    (it picks up newly revealed editions on its next poll), the activity feed
    (and so desktop notifications), and optionally Discord."""
    e = _edition_or_404(db, edition_id)
    expected = "closed" if e.mode == "vote" else "draft"
    if e.status != expected:
        raise HTTPException(400, "Close the vote first" if e.status == "voting" else f"Can't reveal from {e.status}")
    if not e.winners:
        raise HTTPException(400, "Pick a winner first")
    e.status = "revealed"
    e.revealed_at = datetime.utcnow()
    winners = _sorted_winners(e)
    for w in winners:
        add_activity(
            db, w.user_id, "trophy_awarded",
            f"{_trophy_label(e.trophy)}" + (f" — {w.citation}" if w.citation else ""),
            "trophy_edition", e.id,
        )
    db.commit()

    if data.post_to_discord:
        # Imported here: discord_notify pulls in the mailer and httpx, which
        # nothing else in this module needs.
        from discord_notify import send_discord_message

        event = db.query(LanEvent).filter(LanEvent.id == e.event_id).first()
        lines = [f"{_trophy_label(e.trophy)} → " + ", ".join(f"**{w.user.username}**" for w in winners if w.user)]
        lines += [f"> **{w.user.username}** — {w.citation}" for w in winners if w.user and w.citation]
        if event:
            lines.append(f"_{event.title}_")
        send_discord_message(db, "\n".join(lines))  # best effort — a Discord hiccup doesn't undo the reveal

    return _edition_out(db, _edition_or_404(db, e.id), admin, _attendee_ids(db, e.event_id))


# ── Showcase ──────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}", response_model=list[UserTrophyOut])
def user_trophies(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_feature("trophies"))):
    """A member's revealed trophies, newest event first — their showcase."""
    rows = (
        db.query(EventTrophyWinner)
        .join(EventTrophy, EventTrophy.id == EventTrophyWinner.event_trophy_id)
        .join(LanEvent, LanEvent.id == EventTrophy.event_id)
        .options(
            selectinload(EventTrophyWinner.edition).selectinload(EventTrophy.trophy),
            selectinload(EventTrophyWinner.edition).selectinload(EventTrophy.event),
        )
        .filter(EventTrophyWinner.user_id == user_id, EventTrophy.status == "revealed")
        .order_by(LanEvent.start_date.desc(), EventTrophy.sort_order, EventTrophy.id)
        .all()
    )
    return [
        UserTrophyOut(
            edition_id=w.edition.id,
            trophy=_brief(w.edition.trophy),
            event_id=w.edition.event_id,
            event_title=w.edition.event.title,
            event_start_date=w.edition.event.start_date,
            citation=w.citation,
            revealed_at=w.edition.revealed_at,
        )
        for w in rows
    ]
