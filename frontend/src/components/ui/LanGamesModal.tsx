import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, ExternalLink as ExternalLinkIcon } from 'lucide-react'
import ExternalLink from './ExternalLink'

// The website's LAN games list (Websites/Website_v4_src/games.html), in the
// app's language. Framed, the page hides its own menu, pitch and footer.
export function lanGamesUrl(language: string): string {
  return language.startsWith('fr')
    ? 'https://lanpartymanager.com/fr/games/'
    : 'https://lanpartymanager.com/games/'
}

export default function LanGamesModal({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const [loaded, setLoaded] = useState(false)
  const url = lanGamesUrl(i18n.language)
  const frameRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Listened here rather than through onLoad, which jsx-a11y reads as a
  // mouse/keyboard handler on a non-interactive element.
  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    const done = () => setLoaded(true)
    frame.addEventListener('load', done)
    return () => frame.removeEventListener('load', done)
  }, [url])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center sm:p-6">
      {/* The backdrop is its own button, so a click outside closes without the
          dialog having to stop its clicks from bubbling. */}
      <button
        type="button"
        tabIndex={-1}
        aria-label={t('common.close')}
        onClick={onClose}
        className="absolute inset-0 bg-background/90 cursor-default"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('footer.lanGamesLabel')}
        className="relative bg-card sm:border border-border w-full h-[100dvh] sm:h-[calc(100dvh-3rem)] max-w-[1400px] flex flex-col"
      >
        <div className="flex items-center justify-between gap-4 px-4 sm:px-6 py-4 border-b border-border flex-shrink-0">
          <p className="font-mono-label text-accent">{t('footer.lanGamesLabel')}</p>
          <div className="flex items-center gap-4 min-w-0">
            <ExternalLink
              href={url}
              className="flex items-center gap-1.5 min-w-0 text-muted-foreground hover:text-accent transition-colors duration-150"
              title={t('footer.lanGamesOpenSite')}
            >
              <ExternalLinkIcon size={12} strokeWidth={1.5} className="flex-shrink-0" />
              <span className="font-mono-label text-[11px] truncate">{t('footer.lanGamesOpenSite')}</span>
            </ExternalLink>
            <button
              type="button"
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground flex-shrink-0"
              aria-label={t('common.close')}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="relative flex-1 min-h-0 bg-background">
          {!loaded && (
            <p className="absolute inset-0 flex items-center justify-center font-mono-label text-muted-foreground animate-pulse">
              {t('common.loading')}
            </p>
          )}
          {/* No referrer: the site doesn't learn which instance opened it.
              No allow-top-navigation: nothing in the frame can move the app. */}
          <iframe
            ref={frameRef}
            src={url}
            title={t('footer.lanGamesLabel')}
            referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
            className="absolute inset-0 w-full h-full border-0"
          />
        </div>
      </div>
    </div>
  )
}
