"""Games — /api/games

Profile "game library" (owned, with a max-player count) and "wishlist" (wanted),
backed by a shared catalog seeded from `games_catalog_seed.json`. A member adding a
game the catalog doesn't have creates a new catalog row (case-insensitive lookup
first, so two members typing the same title land on the same row) rather than a
private free-text entry — that's what lets `/matches` and `/session` compare
libraries by `game_id` instead of fuzzy-matching strings.

`/matches` answers "who shares my games"; `/session` answers "we're these N people
tonight, what can we all play" (MVP: library ∩ library only, no wishlist crossover
yet — see the profile.md planning notes for that as a V2 idea).

A member can star library games as favorites (`is_favorite`, private to their own
library) and the profile's filter bar is saved on the account (`/me/filters`) so it
survives a reload.

All endpoints are gated by the `games` feature flag (non-admins get 404 when it's
off; admins always pass so they can configure it first), mirroring Gear/Setup.
"""
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models import Game, User, UserGameLibrary, UserGameWishlist
from schemas import (
    GameOut, GameLibraryCreate, GameLibraryUpdate, GameFavoriteUpdate, GameLibraryFilters,
    GameWishlistCreate, GameLibraryEntryOut, GameWishlistEntryOut, GameMeOut,
    GameMatchOut, GameSessionRequest, GameSessionResultOut, GameImportResultOut,
)
from router_settings import require_feature, get_setting
from games_catalog import resolve_game
import oauth_steam

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _library_entry(row: UserGameLibrary, *, own: bool = True) -> GameLibraryEntryOut:
    """`own=False` for another member's row (finder matches/session): their
    favorite star is a private preference, so it's never reported there."""
    return GameLibraryEntryOut(
        game_id=row.game_id,
        name=row.game.name,
        genre=row.game.genre,
        max_players=row.max_players_override or row.game.default_max_players,
        is_custom=row.game.is_custom,
        is_favorite=bool(row.is_favorite) if own else False,
    )


def _saved_filters(user: User) -> GameLibraryFilters:
    """The member's saved filter bar, or the defaults when there's none yet — or
    when what's stored no longer validates (a shape from an older version), so a
    stale preference can never break the profile page."""
    if not user.games_library_filters:
        return GameLibraryFilters()
    try:
        return GameLibraryFilters.model_validate_json(user.games_library_filters)
    except ValidationError:
        return GameLibraryFilters()


def _wishlist_entry(row: UserGameWishlist) -> GameWishlistEntryOut:
    return GameWishlistEntryOut(game_id=row.game_id, name=row.game.name, genre=row.game.genre)


def _library_rows(db: Session, user_id: int) -> list[UserGameLibrary]:
    return (
        db.query(UserGameLibrary)
        .options(selectinload(UserGameLibrary.game))
        .filter(UserGameLibrary.user_id == user_id)
        .all()
    )


# ── Catalog ─────────────────────────────────────────────────────────────────────

@router.get("/catalog", response_model=list[GameOut])
def get_catalog(
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("games")),
):
    """The whole shared catalog (seed + every custom addition), for client-side
    autocomplete — small enough (~100 seeded, plus customs) to not need a server
    search endpoint."""
    games = db.query(Game).order_by(Game.name).all()
    return [GameOut(id=g.id, name=g.name, genre=g.genre,
                     default_max_players=g.default_max_players, is_custom=g.is_custom)
            for g in games]


# ── My library / wishlist ────────────────────────────────────────────────────────

@router.get("/me", response_model=GameMeOut)
def get_my_games(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    library = _library_rows(db, user.id)
    wishlist = (
        db.query(UserGameWishlist)
        .options(selectinload(UserGameWishlist.game))
        .filter(UserGameWishlist.user_id == user.id)
        .all()
    )
    return GameMeOut(
        library=[_library_entry(r) for r in library],
        wishlist=[_wishlist_entry(r) for r in wishlist],
        filters=_saved_filters(user),
    )


@router.put("/me/filters", response_model=GameLibraryFilters)
def save_my_filters(
    data: GameLibraryFilters,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    user.games_library_filters = data.model_dump_json()
    db.commit()
    return data


@router.post("/me/library", response_model=GameLibraryEntryOut, status_code=201)
def add_to_library(
    data: GameLibraryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    game = resolve_game(db, data.name, user.id)
    row = db.query(UserGameLibrary).filter(
        UserGameLibrary.user_id == user.id, UserGameLibrary.game_id == game.id
    ).first()
    if not row:
        row = UserGameLibrary(user_id=user.id, game_id=game.id)
        db.add(row)
    row.max_players_override = data.max_players_override
    db.commit()
    db.refresh(row)
    return _library_entry(row)


@router.put("/me/library/{game_id}", response_model=GameLibraryEntryOut)
def update_library_entry(
    game_id: int,
    data: GameLibraryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    row = db.query(UserGameLibrary).filter(
        UserGameLibrary.user_id == user.id, UserGameLibrary.game_id == game_id
    ).first()
    if not row:
        raise HTTPException(404, "Not in your library")
    row.max_players_override = data.max_players_override
    db.commit()
    db.refresh(row)
    return _library_entry(row)


@router.put("/me/library/{game_id}/favorite", response_model=GameLibraryEntryOut)
def set_library_favorite(
    game_id: int,
    data: GameFavoriteUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    """Its own route rather than a field on PUT /me/library/{game_id}: that one
    always writes `max_players_override`, so a star toggle sent through it would
    wipe the member's player count."""
    row = db.query(UserGameLibrary).filter(
        UserGameLibrary.user_id == user.id, UserGameLibrary.game_id == game_id
    ).first()
    if not row:
        raise HTTPException(404, "Not in your library")
    row.is_favorite = data.is_favorite
    db.commit()
    db.refresh(row)
    return _library_entry(row)


@router.delete("/me/library/{game_id}")
def remove_from_library(
    game_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    row = db.query(UserGameLibrary).filter(
        UserGameLibrary.user_id == user.id, UserGameLibrary.game_id == game_id
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.post("/me/wishlist", response_model=GameWishlistEntryOut, status_code=201)
def add_to_wishlist(
    data: GameWishlistCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    game = resolve_game(db, data.name, user.id)
    row = db.query(UserGameWishlist).filter(
        UserGameWishlist.user_id == user.id, UserGameWishlist.game_id == game.id
    ).first()
    if not row:
        row = UserGameWishlist(user_id=user.id, game_id=game.id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return _wishlist_entry(row)


@router.delete("/me/wishlist/{game_id}")
def remove_from_wishlist(
    game_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    row = db.query(UserGameWishlist).filter(
        UserGameWishlist.user_id == user.id, UserGameWishlist.game_id == game_id
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


# ── Finder: matches & session ────────────────────────────────────────────────────

@router.get("/matches", response_model=list[GameMatchOut])
def get_matches(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    """Every other active member, ranked by how many library games they share
    with the current user (desc), with the shared games listed."""
    my_games = {r.game_id: r for r in _library_rows(db, user.id)}
    if not my_games:
        return []

    others = (
        db.query(User)
        .filter(User.id != user.id, User.is_active.is_(True), User.deleted_at.is_(None))
        .all()
    )

    results = []
    for other in others:
        other_rows = _library_rows(db, other.id)
        shared = [r for r in other_rows if r.game_id in my_games]
        if not shared:
            continue
        results.append(GameMatchOut(
            user_id=other.id,
            username=other.username,
            avatar_url=other.avatar_url,
            shared_count=len(shared),
            shared_games=[_library_entry(r, own=False) for r in shared],
        ))
    results.sort(key=lambda m: (-m.shared_count, m.username.lower()))
    return results


@router.post("/session", response_model=GameSessionResultOut)
def build_session(
    data: GameSessionRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("games")),
):
    """Games owned by EVERY listed user, with an effective max player count
    covering the group (or the given `min_players`, if higher)."""
    target = max(len(data.user_ids), data.min_players or 0)

    per_user_rows = [_library_rows(db, uid) for uid in data.user_ids]
    if not per_user_rows or any(not rows for rows in per_user_rows):
        return GameSessionResultOut(games=[])

    common_ids = set(r.game_id for r in per_user_rows[0])
    for rows in per_user_rows[1:]:
        common_ids &= set(r.game_id for r in rows)
    if not common_ids:
        return GameSessionResultOut(games=[])

    # Effective max is the same for a given game_id regardless of whose row we
    # read it from *unless* players have set different overrides — use the
    # smallest effective max across the group (the group can't exceed what the
    # most-constrained owner supports).
    effective_max: dict[int, int | None] = {}
    entry_by_game: dict[int, GameLibraryEntryOut] = {}
    for rows in per_user_rows:
        for r in rows:
            if r.game_id not in common_ids:
                continue
            eff = r.max_players_override or r.game.default_max_players
            if r.game_id not in effective_max or (eff is not None and (effective_max[r.game_id] is None or eff < effective_max[r.game_id])):
                effective_max[r.game_id] = eff
                entry_by_game[r.game_id] = _library_entry(r, own=False)

    games = [
        entry_by_game[gid]
        for gid, max_players in effective_max.items()
        if max_players is None or max_players >= target
    ]
    games.sort(key=lambda e: ((e.max_players is None) * 10**6 + (e.max_players or 0), e.name.lower()))
    return GameSessionResultOut(games=games)


# ── Steam import ─────────────────────────────────────────────────────────────

@router.post("/me/import-steam", response_model=GameImportResultOut)
def import_from_steam(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("games")),
):
    """Bulk-adds the current user's Steam-owned games to their library, via
    the account linked in Profile (see md/2.features/Steam_Link.md). Steam doesn't give a
    max-player count, so an imported game's `max_players_override` is left
    unset — the catalog's own default (if any) still applies, and a member can
    always set their own override afterward exactly like a manually-added
    game."""
    if not user.steam_id:
        raise HTTPException(400, "Link your Steam account first")
    api_key = get_setting(db, "steam_web_api_key")
    if get_setting(db, "steam_link_enabled") != "true" or not api_key:
        raise HTTPException(404, "Steam linking is not enabled")

    try:
        steam_games = oauth_steam.fetch_owned_games(user.steam_id, api_key)
    except oauth_steam.SteamOAuthError:
        raise HTTPException(502, "Could not reach Steam")

    if steam_games is None:
        return GameImportResultOut(games_visible=False)

    existing_game_ids = {r.game_id for r in _library_rows(db, user.id)}
    imported = already_owned = added_custom = 0
    for g in steam_games:
        name = (g.get("name") or "").strip()
        if not name:
            continue
        game = db.query(Game).filter(func.lower(Game.name) == name.lower()).first()
        if not game:
            game = Game(name=name, is_custom=True, created_by=user.id)
            db.add(game)
            db.flush()
            added_custom += 1
        if game.id in existing_game_ids:
            already_owned += 1
            continue
        db.add(UserGameLibrary(user_id=user.id, game_id=game.id))
        existing_game_ids.add(game.id)
        imported += 1

    db.commit()
    return GameImportResultOut(
        games_visible=True, imported=imported, already_owned=already_owned, added_custom=added_custom,
    )
