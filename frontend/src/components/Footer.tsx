import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Info } from 'lucide-react'
import AboutModal from './ui/AboutModal'
import LanguageToggle from './ui/LanguageToggle'
import ExternalLink from './ui/ExternalLink'

const DockerIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5" aria-hidden="true">
    <path d="M13.983 11.078h2.119a.186.186 0 0 0 .186-.185V9.006a.186.186 0 0 0-.186-.186h-2.119a.185.185 0 0 0-.185.185v1.888c0 .102.083.185.185.185m-2.954-5.43h2.118a.186.186 0 0 0 .186-.186V3.574a.186.186 0 0 0-.186-.185h-2.118a.185.185 0 0 0-.185.185v1.888c0 .102.082.185.185.185m0 2.716h2.118a.187.187 0 0 0 .186-.186V6.29a.186.186 0 0 0-.186-.185h-2.118a.185.185 0 0 0-.185.185v1.887c0 .102.082.185.185.186m-2.93 0h2.12a.186.186 0 0 0 .184-.186V6.29a.185.185 0 0 0-.185-.185H8.1a.185.185 0 0 0-.185.185v1.887c0 .102.083.185.185.186m-2.964 0h2.119a.186.186 0 0 0 .185-.186V6.29a.185.185 0 0 0-.185-.185H5.136a.186.186 0 0 0-.186.185v1.887c0 .102.084.185.186.186m5.893 2.715h2.118a.186.186 0 0 0 .186-.185V9.006a.186.186 0 0 0-.186-.186h-2.118a.185.185 0 0 0-.185.185v1.888c0 .102.082.185.185.185m-2.93 0h2.12a.185.185 0 0 0 .184-.185V9.006a.185.185 0 0 0-.184-.186h-2.12a.185.185 0 0 0-.184.185v1.888c0 .102.083.185.185.185m-2.964 0h2.119a.185.185 0 0 0 .185-.185V9.006a.185.185 0 0 0-.184-.186h-2.12a.186.186 0 0 0-.186.186v1.887c0 .102.084.185.186.185m-2.92 0h2.12a.185.185 0 0 0 .184-.185V9.006a.185.185 0 0 0-.184-.186h-2.12a.185.185 0 0 0-.185.185v1.888c0 .102.082.185.185.185M23.763 9.89c-.065-.051-.672-.51-1.954-.51-.338.001-.676.03-1.01.087-.248-1.7-1.653-2.53-1.716-2.566l-.344-.199-.226.327c-.284.438-.49.922-.612 1.43-.23.97-.09 1.882.403 2.661-.595.332-1.55.413-1.744.42H.751a.751.751 0 0 0-.75.748 11.376 11.376 0 0 0 .692 4.062c.545 1.428 1.355 2.483 2.41 3.138 1.18.737 3.1 1.161 5.275 1.161 1.06.001 2.12-.095 3.164-.289a13.901 13.901 0 0 0 3.771-1.528 10.253 10.253 0 0 0 2.5-2.164c1.2-1.382 1.907-2.912 2.434-4.482 3.779.008 5.92-1.509 6.067-1.61l.19-.132-.123-.189z" />
  </svg>
)

export default function Footer() {
  const { t } = useTranslation()
  const [showAbout, setShowAbout] = useState(false)

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

        <span className="font-mono-label text-muted-foreground/50 text-[11px]">1.3.5</span>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <ExternalLink
          href="https://www.lanpartymanager.com"
          className="flex items-center gap-1.5 text-muted-foreground hover:text-accent transition-colors duration-150"
          title="LAN Party Manager"
        >
          <span className="font-mono-label text-[11px]">2026 - LANPARTYMANAGER</span>
        </ExternalLink>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <ExternalLink
          href="https://hub.docker.com/r/crosswax"
          className="flex items-center gap-1.5 text-muted-foreground hover:text-[#2496ED] transition-colors duration-150"
          title={t('footer.dockerTitle')}
        >
          <DockerIcon />
          <span className="font-mono-label text-[11px]">{t('footer.dockerLabel')}</span>
        </ExternalLink>

        <span className="w-px h-3 bg-border hidden sm:block" />

        <LanguageToggle />
      </div>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}
    </footer>
  )
}
