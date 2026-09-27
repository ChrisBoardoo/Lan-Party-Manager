import { useTranslation } from 'react-i18next'
import MiniGames from '../components/MiniGames'

/** Standalone page for the same component the Arena tab mounts.
 *
 *  The tab is the discovery path; this exists so /minigames is a shareable link and a
 *  target for the Hub card. Both render one component — there is no second copy of the
 *  game list or the leaderboard to keep in sync. */
export default function MiniGamesPage() {
  const { t } = useTranslation()

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('minigames.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
          {t('minigames.heroLine1')}
          <br />
          <span className="text-accent">{t('minigames.heroLine2')}</span>
        </h1>
      </div>

      <MiniGames />
    </main>
  )
}
