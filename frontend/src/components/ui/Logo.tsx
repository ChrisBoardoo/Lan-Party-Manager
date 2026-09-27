import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import ExternalLink from './ExternalLink'

/** The brand lockup: "LAN" in accent, a hairline rule, then "Party Manager".
 *
 *  This is the same mark the app's Navbar renders and the same one the marketing
 *  site uses in its own nav (`.nav-logo-lan` / `.nav-logo-divider` /
 *  `.nav-logo-sub` in Website/index.html) — accent Inter Tight black, a 1px
 *  divider, muted uppercase mono. Text rather than an image, so it inherits the
 *  theme, stays sharp at any size, costs no bytes, and reads the same on the
 *  public share page as it does everywhere else.
 *
 *  The words come from the `nav.brandTop` / `nav.brandBottom` i18n keys, so
 *  there's exactly one place to change them.
 */
const WEBSITE = 'https://www.lanpartymanager.com'

const SIZES = {
  sm: { top: 'text-base', rule: 'h-3', gap: 'gap-2' },
  md: { top: 'text-lg', rule: 'h-4', gap: 'gap-3' },   // matches the Navbar exactly
  lg: { top: 'text-3xl', rule: 'h-7', gap: 'gap-4' },
} as const

interface LogoProps {
  size?: keyof typeof SIZES
  /** 'website' links out to lanpartymanager.com; 'home' to the app root. */
  linkTo?: 'home' | 'website' | 'none'
  className?: string
}

export default function Logo({ size = 'md', linkTo = 'none', className = '' }: LogoProps) {
  const { t } = useTranslation()
  const s = SIZES[size]

  const mark = (
    <span className={`inline-flex items-center ${s.gap} ${className}`}>
      <span className={`text-accent font-sans font-black ${s.top} tracking-tighter leading-none`}>
        {t('nav.brandTop')}
      </span>
      <span className={`w-px ${s.rule} bg-border`} />
      <span className="font-mono-label text-muted-foreground">{t('nav.brandBottom')}</span>
    </span>
  )

  if (linkTo === 'website') {
    return (
      <ExternalLink href={WEBSITE} title="LAN Party Manager" className="inline-block hover:opacity-80 transition-opacity">
        {mark}
      </ExternalLink>
    )
  }

  if (linkTo === 'home') {
    return (
      <Link to="/" title="LAN Party Manager" className="inline-block hover:opacity-80 transition-opacity">
        {mark}
      </Link>
    )
  }

  return mark
}
