import { describe, expect, it } from 'vitest'
import type { CardCollection, CardItem, CardTypeInfo } from '../types'
import {
  idsFor, isRecentlyTraded, keysForIds, suggestionPrefill, tradableOfMember, tradeOptions, typeKey,
} from './cardTrades'

let nextId = 1

function card(faceId: number, userId: number, username: string, rarity: 'common' | 'epic' = 'common', extra: Partial<CardItem> = {}): CardItem {
  return {
    id: nextId++,
    face_id: faceId,
    rarity,
    kind: 'pulled',
    slot: 1,
    source_type: 'purchase',
    obtained_at: null,
    face: {
      user_id: userId, username, image_url: null, xp_level: null, event_id: 1, event_title: 'LAN',
      year: 2026, number: null, edition_size: 0, trophies: [], departed: false,
    },
    ...extra,
  }
}

function collection(ownerId: number, cards: CardItem[], types: CardTypeInfo[]): CardCollection {
  return {
    owner_id: ownerId,
    members: [{ user_id: 0, username: '', image_url: null, departed: false, count: cards.length, epic_count: 0, cards }],
    collected: 0, crew_size: 0, total_cards: cards.length, epic_cards: 0, types,
  }
}

function type(c: CardItem, count: number, tradable: number, ids: number[] = []): CardTypeInfo {
  return { face_id: c.face_id, rarity: c.rarity, count, tradable, listed: false, card_ids: ids }
}

// alice (1) and bob (2); faces: bob 20, carol 30, dan 40, eve 50, zed 60.
const carol = card(30, 3, 'carol')
const dan = card(40, 4, 'dan')
const bobFace = card(20, 2, 'bob')
const eveEpic = card(50, 5, 'eve', 'epic')
const lone = card(60, 6, 'zed')
const alice = collection(1, [carol, dan, bobFace, eveEpic, lone], [
  type(carol, 2, 1, [101]),
  type(dan, 3, 2, [102, 103]),
  type(bobFace, 2, 1, [104]),
  type(eveEpic, 2, 1, [105]),
  type(lone, 1, 0),
])
const bob = collection(2, [card(40, 4, 'dan')], [type(card(40, 4, 'dan'), 1, 0)])

describe('tradeOptions', () => {
  it('offers duplicates only, never a card of the receiver', () => {
    const names = tradeOptions(alice, bob, 2).map((o) => o.card.face.username)
    expect(names).not.toContain('bob') // a card of bob can't go to bob
    expect(names).not.toContain('zed') // a single copy isn't a duplicate
    expect(names).toHaveLength(3)
  })

  it('puts what the receiver is missing first, then Epics', () => {
    const options = tradeOptions(alice, bob, 2)
    // bob already has dan: last. carol and eve are missing; eve is an Epic.
    expect(options.map((o) => o.card.face.username)).toEqual(['eve', 'carol', 'dan'])
    expect(options.map((o) => o.missing)).toEqual([true, true, false])
  })

  it('handles an empty side', () => {
    expect(tradeOptions(null, bob, 2)).toEqual([])
  })
})

describe('ids', () => {
  it('sends one copy per chosen type', () => {
    const options = tradeOptions(alice, bob, 2)
    expect(idsFor(options, [typeKey(dan), typeKey(carol)])).toEqual([102, 101])
    expect(idsFor(options, ['999:common'])).toEqual([])
  })

  it('finds the types behind card ids, dropping the gone ones', () => {
    expect(keysForIds(alice.types, [103, 101, 102, 7])).toEqual([typeKey(dan), typeKey(carol)])
  })
})

describe('suggestionPrefill', () => {
  it('balances both sides, three at most', () => {
    const member = { id: 2, username: 'bob', avatar_url: null }
    const four = [card(1, 9, 'a'), card(2, 9, 'b'), card(3, 9, 'c'), card(4, 9, 'd')]
    expect(suggestionPrefill({ member, they_give: four, i_give: four.slice(0, 2) })).toEqual({
      take: [four[0].id, four[1].id], give: [four[0].id, four[1].id],
    })
    expect(suggestionPrefill({ member, they_give: four, i_give: four }).take).toHaveLength(3)
  })
})

describe('collection helpers', () => {
  it('counts what a member stack can give', () => {
    expect(tradableOfMember(alice, [dan, lone])).toBe(2)
  })

  it('marks a card received by a trade in the last two days', () => {
    const now = Date.parse('2026-11-10T12:00:00Z')
    expect(isRecentlyTraded(card(1, 1, 'x', 'common', { acquired_at: '2026-11-09T12:00:00' }), now)).toBe(true)
    expect(isRecentlyTraded(card(1, 1, 'x', 'common', { acquired_at: '2026-11-07T12:00:00' }), now)).toBe(false)
    expect(isRecentlyTraded(card(1, 1, 'x'), now)).toBe(false)
  })
})
