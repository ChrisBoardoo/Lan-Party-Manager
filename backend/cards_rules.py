"""Cards & boosters — the one place to tune the rules (see cards.py).

Decided by CrossWax on 2026-10-17 (md/2.features/card_features_2026-brainstorming.md).
"""

# Cards per booster, by the size of the pool it's drawn from: the attendees of
# the booster's LAN, the owner excluded. (largest pool, cards) — the first band
# the pool fits in wins. A booster never holds the same member twice, so its
# size is also capped at the pool.
BOOSTER_SIZE_BANDS = (
    (1, 1),
    (10, 2),
    (19, 3),
    (29, 4),
    (49, 5),
    (99, 8),
)
BOOSTER_SIZE_MAX = 10  # pool of 100 and more

# Chance that a booster's last card is Epic, by where the booster came from.
# At most one Epic per booster, always the last slot. Raised on 2026-10-19: a
# small crew with two LANs a year saw almost none at 1–3 %; the aim is about
# one Epic per LAN, opened together on site — hence attendance above purchase,
# which drives the volume between LANs. A booster keeps the rate it was drawn
# with.
EPIC_RATES = {
    "attendance": 0.08,  # one booster per attendee, from the LAN's first day
    "xp_level": 0.06,    # one per XP level reached
    "trophy": 0.10,      # one per trophy won, from its reveal
    "purchase": 0.05,    # bought with spendable XP
}

# A booster bought with XP. Spending never lowers the member's level: the level
# follows the XP earned, purchases come out of a separate balance
# (earned - spent).
BOOSTER_PRICE_XP = 100

# At most this many boosters bought per rolling week: a member who'd farm XP
# anyway gets two boosters a week out of it, not a stack.
PURCHASES_PER_WEEK = 2
PURCHASE_WINDOW_DAYS = 7


# Trades (card_trades.py), decided by CrossWax on 2026-10-19
# (md/2.features/cards/cards_v2_quetes_presence_echanges.md, lot C).
# Cards on each side of an offer: at least one (no gifts), at most this many —
# enough for "two commons for one Epic".
TRADE_MAX_CARDS_PER_SIDE = 3
# An offer nobody answered lapses after this many days (computed on read).
TRADE_EXPIRY_DAYS = 7
# Pending offers one member may have sent at once, and open listings they may
# have in the market.
TRADE_PENDING_MAX = 10
LISTINGS_OPEN_MAX = 20
# Free text on an offer or a listing.
TRADE_NOTE_MAX_CHARS = 200


def booster_size(pool: int) -> int:
    """Cards in a booster drawn from `pool` members (0 = no booster)."""
    if pool <= 0:
        return 0
    for largest, size in BOOSTER_SIZE_BANDS:
        if pool <= largest:
            return min(size, pool)
    return min(BOOSTER_SIZE_MAX, pool)
