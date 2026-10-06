// Must match INVITE_CODE_LENGTH in backend/router_events.py (codes made before
// 1.3.4 had 6 characters and still work).
export const INVITE_CODE_LENGTH = 10

// Guests paste the code from a chat message, often with a space around it.
// Trim and cap here rather than with `maxLength`: the browser truncates a paste
// to `maxLength` *before* any cleanup, so " ZNV7GKAXB5" would lose its last
// character.
export function normalizeInviteCode(raw: string): string {
  return raw.replace(/\s/g, '').toUpperCase().slice(0, INVITE_CODE_LENGTH)
}
