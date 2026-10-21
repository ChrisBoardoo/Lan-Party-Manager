import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { CardItem } from '../../types'

// A crew card: the member's photo as it was at that LAN (a copy, so a later
// avatar change never touches it), their name, the edition, and — on an Epic —
// the trophies they won there, under a holographic sheen. The look lives in
// index.css (`.lpm-card*`), sized in cqw so the card scales with its width:
// give the wrapper a width, the card fills it.

const TILT_DEG = 14

function reducedMotion() {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export default function PlayerCard({
  card,
  interactive = true,
  className = '',
}: {
  card: CardItem
  /** Tilt and light follow the pointer (mouse; touch only where the page doesn't scroll). */
  interactive?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const { face } = card
  const epic = card.rarity === 'epic'

  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el || !interactive || reducedMotion()) return
    const r = el.getBoundingClientRect()
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
    const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))
    el.style.setProperty('--lpm-mx', `${(x * 100).toFixed(1)}%`)
    el.style.setProperty('--lpm-my', `${(y * 100).toFixed(1)}%`)
    el.style.setProperty('--lpm-rx', `${((0.5 - y) * TILT_DEG).toFixed(2)}deg`)
    el.style.setProperty('--lpm-ry', `${((x - 0.5) * TILT_DEG).toFixed(2)}deg`)
    el.dataset.active = 'true'
  }

  const leave = () => {
    const el = ref.current
    if (!el) return
    for (const v of ['--lpm-mx', '--lpm-my', '--lpm-rx', '--lpm-ry']) el.style.removeProperty(v)
    el.dataset.active = 'false'
  }

  // "C'est La LAN 2026 #2" already says the year: don't print it twice.
  const edition = face.year && !face.event_title.includes(String(face.year)) ? `${face.event_title} · ${face.year}` : face.event_title
  const number = face.number ? `${String(face.number).padStart(2, '0')} / ${String(face.edition_size).padStart(2, '0')}` : ''
  const meta = face.departed
    ? t('cards.departed')
    : card.kind === 'signature'
      ? t('cards.signature')
      : face.xp_level != null
        ? t('cards.level', { level: face.xp_level })
        : face.year ?? ''

  return (
    <div className={`lpm-card-tilt ${className}`}>
      <div
        ref={ref}
        onPointerMove={move}
        onPointerLeave={leave}
        className={`lpm-card ${epic ? 'lpm-card--epic' : ''} ${face.departed ? 'lpm-card--departed' : ''}`}
        data-active="false"
        role="img"
        aria-label={t('cards.ariaLabel', {
          name: face.username,
          edition: face.event_title,
          rarity: t(`cards.rarity.${card.rarity}`),
        })}
      >
        <div className="lpm-card__inner">
          <div className="lpm-card__top">
            <span>{edition}</span>
            <span>{number}</span>
          </div>
          <div className="lpm-card__photo">
            {face.image_url ? (
              <img src={face.image_url} alt="" draggable={false} loading="lazy" decoding="async" />
            ) : (
              <span className="lpm-card__initial" aria-hidden="true">
                {face.username.charAt(0).toUpperCase()}
              </span>
            )}
          </div>
          <div className="lpm-card__name">{face.username}</div>
          <div className="lpm-card__meta">{meta}</div>
          {epic && face.trophies.length > 0 && (
            <div className="lpm-card__meta lpm-card__meta--accent">{face.trophies.join(' · ')}</div>
          )}
          <div className="lpm-card__foot">
            <span>Lan Party Manager</span>
            <span className={epic ? 'lpm-card__rarity' : ''}>{t(`cards.rarity.${card.rarity}`)}</span>
          </div>
        </div>
        {epic && (
          <>
            <div className="lpm-card__holo" aria-hidden="true" />
            <div className="lpm-card__glitter" aria-hidden="true" />
          </>
        )}
        <div className="lpm-card__glare" aria-hidden="true" />
      </div>
    </div>
  )
}

/** The face-down side, for the booster reveal. */
export function CardBack({ label, className = '' }: { label?: string; className?: string }) {
  return (
    <div className={`lpm-card-back ${className}`} aria-hidden="true">
      <span className="lpm-card-back__logo">LPM</span>
      {label && <span className="lpm-card-back__label">{label}</span>}
    </div>
  )
}
