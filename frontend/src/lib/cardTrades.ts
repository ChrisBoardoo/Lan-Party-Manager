import type { CardCollection, CardItem, CardTypeInfo, TradeSuggestion } from '../types'

// The client side of card trades (backend/card_trades.py decides; this only
// lays out the choice): what each side of an offer can put in, in what
// order, and which card ids go to the server.

/** A card type's key: identical duplicates share it. */
export function typeKey(card: { face_id: number; rarity: string }): string {
  return `${card.face_id}:${card.rarity}`
}

/** One card type someone can give: a card to show, how many they hold, how
 *  many can go, and whether the other side is missing it. */
export interface TradeOption {
  key: string
  card: CardItem
  count: number
  tradable: number
  cardIds: number[]
  /** The other side has no copy of this type. */
  missing: boolean
}

/** Every card type in a collection, keyed, with a card that shows it. */
export function cardsByType(collection: CardCollection | null | undefined): Map<string, CardItem> {
  const out = new Map<string, CardItem>()
  for (const m of collection?.members ?? []) {
    for (const c of m.cards) if (!out.has(typeKey(c))) out.set(typeKey(c), c)
  }
  return out
}

/** How many copies of each type a collection holds. */
export function heldCounts(collection: CardCollection | null | undefined): Map<string, number> {
  const out = new Map<string, number>()
  for (const t of collection?.types ?? []) out.set(typeKey(t), t.count)
  return out
}

/** What the owner of `giver` can give to `receiverId`: their duplicates,
 *  never a card showing the receiver (nobody receives a card of themselves).
 *  The types the receiver is missing come first, then Epics, then by name. */
export function tradeOptions(
  giver: CardCollection | null | undefined,
  receiver: CardCollection | null | undefined,
  receiverId: number,
): TradeOption[] {
  const cards = cardsByType(giver)
  const theirs = heldCounts(receiver)
  const out: TradeOption[] = []
  for (const t of giver?.types ?? []) {
    const card = cards.get(typeKey(t))
    if (!card || t.tradable <= 0 || t.card_ids.length === 0) continue
    if (card.face.user_id === receiverId) continue
    out.push({
      key: typeKey(t),
      card,
      count: t.count,
      tradable: t.tradable,
      cardIds: t.card_ids,
      missing: !theirs.get(typeKey(t)),
    })
  }
  return out.sort(
    (a, b) =>
      Number(b.missing) - Number(a.missing) ||
      Number(b.card.rarity === 'epic') - Number(a.card.rarity === 'epic') ||
      a.card.face.username.localeCompare(b.card.face.username) ||
      (b.card.face.year ?? 0) - (a.card.face.year ?? 0),
  )
}

/** The card ids an offer sends for the chosen types: one copy of each. */
export function idsFor(options: TradeOption[], chosen: Iterable<string>): number[] {
  const byKey = new Map(options.map((o) => [o.key, o]))
  const ids: number[] = []
  for (const key of chosen) {
    const option = byKey.get(key)
    if (option && option.cardIds.length > 0) ids.push(option.cardIds[0])
  }
  return ids
}

/** The types behind some card ids (to preselect what a listing or a
 *  suggestion asks for). Ids that aren't tradable any more are dropped. */
export function keysForIds(types: CardTypeInfo[] | undefined, cardIds: number[]): string[] {
  const keys: string[] = []
  for (const id of cardIds) {
    const t = (types ?? []).find((x) => x.card_ids.includes(id))
    if (t && !keys.includes(typeKey(t))) keys.push(typeKey(t))
  }
  return keys
}

/** A suggestion as a prefilled offer: as many cards on each side, up to `max`. */
export function suggestionPrefill(s: TradeSuggestion, max = 3): { take: number[]; give: number[] } {
  const n = Math.min(max, s.they_give.length, s.i_give.length)
  return { take: s.they_give.slice(0, n).map((c) => c.id), give: s.i_give.slice(0, n).map((c) => c.id) }
}

/** A card received by a trade in the last two days wears "New!". */
export function isRecentlyTraded(card: CardItem, now: number = Date.now(), withinHours = 48): boolean {
  if (!card.acquired_at) return false
  const at = new Date(card.acquired_at.endsWith('Z') ? card.acquired_at : `${card.acquired_at}Z`).getTime()
  return Number.isFinite(at) && now - at < withinHours * 3600 * 1000
}

/** Copies of a member's cards that their owner could give, over every type. */
export function tradableOfMember(collection: CardCollection | null | undefined, cards: CardItem[]): number {
  const keys = new Set(cards.map(typeKey))
  return (collection?.types ?? []).filter((t) => keys.has(typeKey(t))).reduce((n, t) => n + t.tradable, 0)
}
