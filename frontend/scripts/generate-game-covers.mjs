/* Regenerate the mini-game cover images.
 *
 *   npm run dev            (in another terminal)
 *   node scripts/generate-game-covers.mjs
 *
 * Each cover is a real screenshot of the game's own title screen, written to
 * public/games/<slug>/cover.png. The picker in MiniGames.tsx looks for exactly that
 * path, so adding a game still means "one folder + one registry entry" — there is no
 * cover list to maintain here beyond the settle time a game needs before it looks right.
 *
 * Covers are committed because they are build output of a *game*, not of the app: they
 * only change when a game's look changes, and regenerating them needs a browser.
 */
import { chromium } from 'playwright'
import { mkdirSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const HERE = dirname(fileURLToPath(import.meta.url))
const PUBLIC_GAMES = join(HERE, '..', 'public', 'games')
const ORIGIN = process.env.GAME_ORIGIN || 'http://localhost:5173'

// The page is laid out at 1280x720 so each game renders the way it really does, then
// captured at half scale: 640x360 is already 2x the card's on-screen size, and a
// full-res PNG of an atmospheric scene ran to 400KB+ per game.
const WIDTH = 1280
const HEIGHT = 720
const CAPTURE_SCALE = 0.5

/** settleMs: how long a game needs before its title screen is worth capturing
 *  (font loading, intro animation, first render of an ambient background). */
const GAMES = [
  { slug: 'neon-survivor', settleMs: 1800 },
]

const browser = await chromium.launch()
let failures = 0

for (const { slug, settleMs } of GAMES) {
  const dir = join(PUBLIC_GAMES, slug)
  if (!existsSync(dir)) {
    console.error(`  ${slug}: no folder at ${dir} — skipped`)
    failures++
    continue
  }
  mkdirSync(dir, { recursive: true })

  const page = await browser.newPage({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: CAPTURE_SCALE,
  })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  try {
    await page.goto(`${ORIGIN}/games/${slug}/index.html`, { waitUntil: 'load' })
    await page.waitForTimeout(settleMs)
    await page.screenshot({ path: join(dir, 'cover.png') })
    console.log(`  ${slug}: cover.png written${errors.length ? ` (page errors: ${errors.length})` : ''}`)
    if (errors.length) failures++
  } catch (err) {
    console.error(`  ${slug}: ${err.message}`)
    failures++
  } finally {
    await page.close()
  }
}

await browser.close()
process.exit(failures ? 1 : 0)
