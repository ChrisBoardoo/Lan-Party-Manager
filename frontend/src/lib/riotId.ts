// Mirrors backend/riot_id.py's parse_riot_id, so the profile can flag a
// malformed Riot ID without a round-trip. The backend stays the authority: it
// re-validates, and it alone knows whether the id is already taken.
//
// Riot's rules: game name 3–16 characters, tag 3–5 letters or digits.
// Returns the display form (trimmed around the '#'), or null when malformed.
export function normalizeRiotId(raw: string): string | null {
  const trimmed = raw.trim()
  const hash = trimmed.lastIndexOf('#')
  if (hash < 0) return null
  const name = trimmed.slice(0, hash).trim()
  const tag = trimmed.slice(hash + 1).trim()
  // Spread, not .length: count characters the way Python's len() does, so an
  // accented or emoji name gets the same verdict on both sides.
  const nameLength = [...name].length
  if (name.includes('#') || nameLength < 3 || nameLength > 16) return null
  if (!/^[\p{L}\p{N}]{3,5}$/u.test(tag)) return null
  return `${name}#${tag}`
}
