import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Gamepad2, Swords } from 'lucide-react'
import { useAppConfig } from '../contexts/AppConfigContext'
import GameFinderTab from '../components/GameFinderTab'
import LolTrackerTab from '../components/LolTrackerTab'

type GamesTab = 'lol' | 'finder'

// Games: what the crew plays, as tabs like Arena. The LoL tracker is a game
// followed over the LAN, not a tournament — so it lives here, first and open
// by default when lol_stats is on. The finder needs the games library flag.
// The route is reachable when either flag is on (App.tsx), so a tab always exists.
export default function Games() {
  const { t } = useTranslation()
  const { lolStatsEnabled, gamesEnabled } = useAppConfig()
  const [picked, setPicked] = useState<GamesTab | null>(null)

  const tabs = [
    ...(lolStatsEnabled ? [['lol', t('games.tabLol'), Swords] as const] : []),
    ...(gamesEnabled ? [['finder', t('games.finderTitle'), Gamepad2] as const] : []),
  ]
  // The first tab until one is picked — and again if the picked one's flag goes off.
  const tab = tabs.find(([key]) => key === picked)?.[0] ?? tabs[0]?.[0]

  return (
    <main className="max-w-4xl mx-auto px-6 py-12">
      <div className="mb-12">
        <div className="font-mono-label text-accent mb-3">{t('games.tagline')}</div>
        <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
          {t('games.heroLine1')}
          <br />
          <span className="text-accent">{t('games.heroLine2')}</span>
        </h1>
      </div>

      <div className="flex gap-px border-b border-border mb-8 overflow-x-auto">
        {tabs.map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setPicked(key)}
            className={`flex items-center gap-2 px-4 py-3 font-mono-label border-b-2 -mb-px transition-colors duration-150 whitespace-nowrap ${
              tab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon size={14} strokeWidth={1.5} />
            {label}
          </button>
        ))}
      </div>

      {tab === 'lol' && <LolTrackerTab />}
      {tab === 'finder' && <GameFinderTab />}
    </main>
  )
}
