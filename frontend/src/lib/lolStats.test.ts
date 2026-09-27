import { describe, it, expect } from 'vitest'
import type { LolPlayerLine } from '../types'
import {
  formatDamage, formatDuration, formatOneDecimal, lolCsvFilename, lolStatsCsv, sortLolLines,
} from './lolStats'
import { csvFormatFor } from './csv'

function line(username: string, over: Partial<LolPlayerLine> = {}): LolPlayerLine {
  return {
    user_id: username.length, username, avatar_url: null, games: 1, wins: 0, losses: 1, win_rate: null,
    kills: 0, deaths: 0, assists: 0, damage: 0, kda: 0,
    avg_kills: 0, avg_deaths: 0, avg_assists: 0, avg_damage: 0,
    ...over,
  }
}

const names = (rows: LolPlayerLine[]) => rows.map((r) => r.username)

describe('sortLolLines', () => {
  const rows = [
    line('bob', { kda: 2.5, avg_deaths: 6, games: 4, win_rate: 0.25 }),
    line('cross', { kda: 4.1, avg_deaths: 2, games: 3, win_rate: 0.66 }),
    line('carol', { kda: 2.5, avg_deaths: 4, games: 1, win_rate: null }),
  ]

  it('sorts descending, ties broken by name', () => {
    expect(names(sortLolLines(rows, 'kda', 'desc'))).toEqual(['cross', 'bob', 'carol'])
  })

  it('sorts ascending', () => {
    expect(names(sortLolLines(rows, 'avg_deaths', 'asc'))).toEqual(['cross', 'carol', 'bob'])
  })

  it('always sinks a missing win rate, whichever the direction', () => {
    expect(names(sortLolLines(rows, 'win_rate', 'desc'))).toEqual(['cross', 'bob', 'carol'])
    expect(names(sortLolLines(rows, 'win_rate', 'asc'))).toEqual(['bob', 'cross', 'carol'])
  })

  it('does not mutate its input', () => {
    const before = names(rows)
    sortLolLines(rows, 'games', 'asc')
    expect(names(rows)).toEqual(before)
  })
})

describe('formatters', () => {
  it('formats averages and KDA to one decimal', () => {
    expect(formatOneDecimal(3)).toBe('3.0')
    expect(formatOneDecimal(2.456)).toBe('2.5')
  })

  it('shortens damage past a thousand', () => {
    expect(formatDamage(950)).toBe('950')
    expect(formatDamage(32400)).toBe('32.4k')
    expect(formatDamage(1000)).toBe('1.0k')
  })

  it('formats a game length as m:ss', () => {
    expect(formatDuration(1934)).toBe('32:14')
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(null)).toBe('—')
  })
})

describe('lolStatsCsv', () => {
  const headers = ['Joueur', 'Parties', 'V', 'D', '%', 'K', 'Mo', 'A', 'KDA', 'Dégâts', 'K/p', 'Mo/p', 'A/p', 'Dégâts/p']
  const rows = [
    line('cross', {
      games: 3, wins: 2, losses: 1, win_rate: 2 / 3, kills: 30, deaths: 6, assists: 42, damage: 90500, kda: 12,
      avg_kills: 10, avg_deaths: 2, avg_assists: 14, avg_damage: 30166.67,
    }),
    line('bob', { games: 1, win_rate: null, kda: 1.5, avg_kills: 1.25 }),
  ]

  it('writes French Excel CSV: BOM, semicolons, decimal commas, empty win % under 3 games', () => {
    const lines = lolStatsCsv(rows, headers, csvFormatFor('fr')).split('\r\n')
    expect(lines[0]).toBe('\uFEFFJoueur;Parties;V;D;%;K;Mo;A;KDA;Dégâts;K/p;Mo/p;A/p;Dégâts/p')
    expect(lines[1]).toBe('cross;3;2;1;67;30;6;42;12,00;90500;10,0;2,0;14,0;30167')
    expect(lines[2]).toBe('bob;1;0;1;;0;0;0;1,50;0;1,3;0,0;0,0;0')
    expect(lines[3]).toBe('')
  })

  it('writes English Excel CSV with commas and decimal points', () => {
    const lines = lolStatsCsv(rows, headers, csvFormatFor('en-GB')).split('\r\n')
    expect(lines[1]).toBe('cross,3,2,1,67,30,6,42,12.00,90500,10.0,2.0,14.0,30167')
  })

  it('quotes a username holding the separator and defuses one Excel would run as a formula', () => {
    const csv = lolStatsCsv([line('a;b "c"'), line('=HYPERLINK("x")'), line('-Kai-')], headers, csvFormatFor('fr'))
    const [, first, second, third] = csv.split('\r\n')
    expect(first.startsWith('"a;b ""c""";')).toBe(true)
    expect(second.startsWith(`"'=HYPERLINK(""x"")";`)).toBe(true)
    expect(third.startsWith(`'-Kai-;`)).toBe(true)
  })
})

describe('lolCsvFilename', () => {
  it('names the scope, the category and the date', () => {
    expect(lolCsvFilename('LAN Party 2026 #2', 'custom', '2026-10-15')).toBe('lol-stats_lan-party-2026-2_custom_2026-10-15.csv')
    expect(lolCsvFilename(undefined, null, '2026-10-15')).toBe('lol-stats_global_2026-10-15.csv')
    expect(lolCsvFilename('Été à Évry', null, '2026-07-01')).toBe('lol-stats_ete-a-evry_2026-07-01.csv')
  })
})
