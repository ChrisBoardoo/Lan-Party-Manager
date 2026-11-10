import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Info, Gamepad2 } from 'lucide-react'
import AboutModal from './ui/AboutModal'
import LanguageToggle from './ui/LanguageToggle'
import ExternalLink from './ui/ExternalLink'
import LanGamesModal from './ui/LanGamesModal'

export default function Footer() {
  const { t } = useTranslation()
  const [showAbout, setShowAbout] = useState(false)
  const [showGames, setShowGames] = useState(false)

  return (
    <footer className="border-t border-border mt-16 py-6 px-6">
      <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
        <button
          onClick={() => setShowAbout(true)}
          className="flex items-center gap-1.5 text-muted-foreground hover:text-accent transition-colors duration-150"
          title={t('footer.aboutTitle')}
        >
          <Info size={12} strokeWidth={1.5} />
          <span className="font-mono-label text-[11px]">{t('footer.aboutTitle')}</span>
        </button>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <span className="font-mono-label text-muted-foreground text-[11px]">1.5.3</span>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <ExternalLink
          href="https://www.lanpartymanager.com"
          className="flex items-center gap-1.5 text-muted-foreground hover:text-accent transition-colors duration-150"
          title="LAN Party Manager"
        >
          <span className="font-mono-label text-[11px]">2026 - LANPARTYMANAGER</span>
        </ExternalLink>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <button
          type="button"
          onClick={() => setShowGames(true)}
          className="flex items-center gap-1.5 text-muted-foreground hover:text-accent transition-colors duration-150"
          title={t('footer.lanGamesTitle')}
        >
          <Gamepad2 size={12} strokeWidth={1.5} />
          <span className="font-mono-label text-[11px]">{t('footer.lanGamesLabel')}</span>
        </button>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <LanguageToggle />
      </div>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}
      {showGames && <LanGamesModal onClose={() => setShowGames(false)} />}
    </footer>
  )
}
