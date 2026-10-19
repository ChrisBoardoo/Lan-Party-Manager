// The random team draw (Tournaments › "Random draw"). Drawn in the browser so the
// organizer can redraw as often as they like before saving; the server only
// stores the result (PUT /tournaments/{id}/teams).

export interface Draw<T> {
  teams: T[][]
  /** Players who didn't fit in a full team: the organizer places them by hand. */
  leftovers: T[]
}

/** Fisher–Yates on a copy. `rand` returns a number in [0, 1); injectable for tests. */
export function shuffle<T>(items: readonly T[], rand: () => number = Math.random): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/** How many full teams of `size` the players make. */
export function maxTeams(playerCount: number, size: number): number {
  return size > 0 ? Math.floor(playerCount / size) : 0
}

/** `teamCount` teams of exactly `size` players, at random; whoever is left over
 * goes to `leftovers` (also at random, so it's never the same person by default). */
export function drawTeams<T>(
  players: readonly T[],
  teamCount: number,
  size: number,
  rand: () => number = Math.random
): Draw<T> {
  const order = shuffle(players, rand)
  const count = Math.max(0, Math.min(teamCount, maxTeams(order.length, size)))
  return {
    teams: Array.from({ length: count }, (_, i) => order.slice(i * size, (i + 1) * size)),
    leftovers: order.slice(count * size),
  }
}
