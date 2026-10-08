import { describe, it, expect } from 'vitest'
import { coinFinish } from './XpCoin'
import { levelProgress } from './XpCard'

describe('coinFinish', () => {
  it('follows the level bands: bronze 1–3, silver 4–6, gold 7+', () => {
    expect([1, 3, 4, 6, 7, 20].map(coinFinish)).toEqual(['bronze', 'bronze', 'silver', 'silver', 'gold', 'gold'])
  })
})

describe('levelProgress', () => {
  it('is the share of the current level already earned', () => {
    expect(levelProgress({ total: 0, level_floor: 0, next_level_at: 50 })).toBe(0)
    expect(levelProgress({ total: 100, level_floor: 50, next_level_at: 150 })).toBe(50)
    expect(levelProgress({ total: 149, level_floor: 50, next_level_at: 150 })).toBe(99)
  })

  it('stays within 0–100 whatever the server sends', () => {
    expect(levelProgress({ total: 10, level_floor: 50, next_level_at: 150 })).toBe(0)
    expect(levelProgress({ total: 500, level_floor: 50, next_level_at: 150 })).toBe(100)
    expect(levelProgress({ total: 50, level_floor: 50, next_level_at: 50 })).toBe(100)
  })
})
