"""Shared game-catalog helpers — used by both the profile game library
(router_games.py) and tournaments (router_tournaments.py), so a game typed in
either place lands on the same `Game` row.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Game


def resolve_game(db: Session, name: str, user_id: int) -> Game:
    """Case-insensitive lookup-or-create against the shared catalog. A new row
    is flagged `is_custom` and flushed (not committed) so the caller gets an id
    inside its own transaction."""
    name = name.strip()
    game = db.query(Game).filter(func.lower(Game.name) == name.lower()).first()
    if game:
        return game
    game = Game(name=name, is_custom=True, created_by=user_id)
    db.add(game)
    db.flush()
    return game
