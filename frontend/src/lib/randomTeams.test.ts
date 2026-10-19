import { describe, expect, it } from 'vitest'
import { drawTeams, maxTeams, shuffle } from './randomTeams'

// Deterministic [0, 1) sequence (mulberry32), so a draw can be replayed.
function seeded(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const players = Array.from({ length: 11 }, (_, i) => i + 1)

describe('shuffle', () => {
  it('keeps every item once and leaves the input alone', () => {
    const input = [...players]
    const out = shuffle(input, seeded(1))
    expect([...out].sort((a, b) => a - b)).toEqual(players)
    expect(input).toEqual(players)
  })
})

describe('maxTeams', () => {
  it('counts full teams only', () => {
    expect(maxTeams(11, 5)).toBe(2)
    expect(maxTeams(10, 5)).toBe(2)
    expect(maxTeams(4, 5)).toBe(0)
    expect(maxTeams(10, 0)).toBe(0)
  })
})

describe('drawTeams', () => {
  it('makes teams of exactly the size and leaves the rest over', () => {
    const { teams, leftovers } = drawTeams(players, 2, 5, seeded(2))
    expect(teams.map((t) => t.length)).toEqual([5, 5])
    expect(leftovers).toHaveLength(1)
    expect([...teams.flat(), ...leftovers].sort((a, b) => a - b)).toEqual(players)
  })

  it('leaves more players over when fewer teams are asked for', () => {
    const { teams, leftovers } = drawTeams(players, 2, 3, seeded(3))
    expect(teams.map((t) => t.length)).toEqual([3, 3])
    expect(leftovers).toHaveLength(5)
  })

  it('never asks for more teams than the players fill', () => {
    const { teams, leftovers } = drawTeams(players, 9, 5, seeded(4))
    expect(teams).toHaveLength(2)
    expect(leftovers).toHaveLength(1)
  })

  it('draws differently on a redraw', () => {
    const rand = seeded(5)
    const first = drawTeams(players, 2, 5, rand)
    const second = drawTeams(players, 2, 5, rand)
    expect(second.teams).not.toEqual(first.teams)
  })
})
