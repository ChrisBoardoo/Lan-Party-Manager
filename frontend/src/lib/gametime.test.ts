import { describe, it, expect } from 'vitest'
import { barPercent, formatPlayTime, heatGrid } from './gametime'

describe('formatPlayTime', () => {
  it('writes minutes under an hour', () => {
    expect(formatPlayTime(0)).toBe('0 min')
    expect(formatPlayTime(59)).toBe('0 min')
    expect(formatPlayTime(45 * 60)).toBe('45 min')
  })

  it('writes hours like the LAN scoreboard: 4h, 2h33', () => {
    expect(formatPlayTime(4 * 3600)).toBe('4h')
    expect(formatPlayTime(2 * 3600 + 33 * 60)).toBe('2h33')
    expect(formatPlayTime(5 * 3600 + 6 * 60 + 59)).toBe('5h06')
  })

  it('never goes negative', () => {
    expect(formatPlayTime(-30)).toBe('0 min')
  })
})

describe('barPercent', () => {
  it('scales on the longest bar', () => {
    expect(barPercent(50, 100)).toBe(50)
    expect(barPercent(100, 100)).toBe(100)
  })

  it('keeps a sliver for a game barely played, nothing for none', () => {
    expect(barPercent(1, 10_000)).toBe(2)
    expect(barPercent(0, 100)).toBe(0)
    expect(barPercent(10, 0)).toBe(0)
  })
})

describe('heatGrid', () => {
  it('is empty without cells', () => {
    expect(heatGrid([])).toEqual({ days: [], rows: [], max: 0 })
  })

  it('fills every day between the first and the last, gaps included', () => {
    const grid = heatGrid([
      { day: '2026-10-16', hour: 1, seconds: 600 },
      { day: '2026-10-14', hour: 22, seconds: 3600 },
    ])
    expect(grid.days).toEqual(['2026-10-14', '2026-10-15', '2026-10-16'])
    expect(grid.rows[0][22]).toBe(3600)
    expect(grid.rows[1].every((s) => s === 0)).toBe(true)
    expect(grid.rows[2][1]).toBe(600)
    expect(grid.max).toBe(3600)
  })

  it('crosses a month end', () => {
    const grid = heatGrid([
      { day: '2026-10-31', hour: 23, seconds: 60 },
      { day: '2026-11-01', hour: 0, seconds: 60 },
    ])
    expect(grid.days).toEqual(['2026-10-31', '2026-11-01'])
  })
})
