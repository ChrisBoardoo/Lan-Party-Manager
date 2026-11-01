import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeftRight, ChevronRight, Layers, PackageOpen } from 'lucide-react'
import { cardsApi } from '../../lib/api'
import { useAppConfig } from '../../contexts/AppConfigContext'

// The ways into the collection: the Hub's "boosters to open" banner, and a
// link on profiles. The nav has no room left for one more item (see
// CLAUDE.md, "Navbar"). Each loads itself and stays silent on error — the
// cards endpoints are gated by the feature, and a 404 must never blank a page.

/** Hub nudge while the viewer has unopened boosters, or trade offers waiting
 *  for their answer (the nav has no room for a badge). GET /cards/me also
 *  grants what they've earned since their last visit, so visiting the Hub is
 *  enough. */
export function BoosterBanner() {
  const { t } = useTranslation()
  const { cardsEnabled } = useAppConfig()
  const [count, setCount] = useState(0)
  const [offers, setOffers] = useState(0)

  useEffect(() => {
    if (!cardsEnabled) return
    cardsApi
      .me()
      .then((me) => {
        setCount(me.boosters.length)
        setOffers(me.trades_pending ?? 0)
      })
      .catch(() => {
        setCount(0)
        setOffers(0)
      })
  }, [cardsEnabled])

  if (!cardsEnabled || (count === 0 && offers === 0)) return null
  const banner = 'border border-accent bg-accent/10 p-4 flex items-center justify-between gap-4 hover:bg-accent/20 transition-colors'
  return (
    <div className="mb-12 -mt-8 flex flex-col gap-3">
      {count > 0 && (
        <Link to="/collection#open" className={banner}>
          <span className="flex items-center gap-3">
            <PackageOpen size={18} strokeWidth={1.5} className="text-accent shrink-0" />
            <span className="font-mono-label text-foreground">{t('cards.boostersBanner', { count })}</span>
          </span>
          <ChevronRight size={16} className="text-accent shrink-0" />
        </Link>
      )}
      {offers > 0 && (
        <Link to="/collection#trades" className={banner}>
          <span className="flex items-center gap-3">
            <ArrowLeftRight size={18} strokeWidth={1.5} className="text-accent shrink-0" />
            <span className="font-mono-label text-foreground">{t('cards.trade.banner', { count: offers })}</span>
          </span>
          <ChevronRight size={16} className="text-accent shrink-0" />
        </Link>
      )}
    </div>
  )
}

/** "Collection" link for a profile page. */
export function CollectionLink({ userId, isSelf = false }: { userId: number; isSelf?: boolean }) {
  const { t } = useTranslation()
  const { cardsEnabled } = useAppConfig()
  if (!cardsEnabled) return null
  return (
    <Link
      to={isSelf ? '/collection' : `/collection/${userId}`}
      className="border border-border bg-card p-5 flex items-center justify-between gap-4 hover:border-border-hover transition-colors"
    >
      <span className="flex items-center gap-3">
        <Layers size={18} strokeWidth={1.5} className="text-accent shrink-0" />
        <span>
          <span className="font-mono-label text-accent block">{t('cards.tagline')}</span>
          <span className="text-sm text-foreground">{isSelf ? t('cards.seeMine') : t('cards.seeTheirs')}</span>
        </span>
      </span>
      <ChevronRight size={16} className="text-muted-foreground shrink-0" />
    </Link>
  )
}
