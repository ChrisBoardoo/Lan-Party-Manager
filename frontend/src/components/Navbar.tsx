import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { useUpcomingEvent } from '../contexts/UpcomingEventContext'
import { settingsApi } from '../lib/api'
import ExternalLink from './ui/ExternalLink'
import {
  LogOut, User, DollarSign, Trophy, LayoutDashboard,
  CalendarDays, CalendarClock, Radio, ImageIcon, Menu, X, Settings, ShieldAlert, Gift, Gamepad2, MessageCircle,
} from 'lucide-react'

const DiscordIcon = ({ className = 'w-3.5 h-3.5' }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.073.073 0 0 1 .078.01c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.892.076.076 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.955 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.947 2.418-2.157 2.418z" />
  </svg>
)

export default function Navbar() {
  const { user, logout } = useAuth()
  const { treasuryEnabled, prizesEnabled, planningEnabled, streamsEnabled, gamesEnabled, lolStatsEnabled } = useAppConfig()
  const { chatEvent } = useUpcomingEvent()
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [discordInvite, setDiscordInvite] = useState<string | null>(null)

  // Close on route change
  useEffect(() => { setMenuOpen(false) }, [pathname])

  useEffect(() => {
    if (!user) return
    settingsApi.getDiscordInvite().then((d) => setDiscordInvite(d.discord_invite_url)).catch(() => {})
  }, [user])

  const isAdmin = user?.role === 'admin'

  const navItems = [
    { to: '/', label: t('nav.hub'), icon: LayoutDashboard, adminOnly: false, show: true },
    // Temporary on purpose — only exists while a Craving Chat is actually
    // reachable (30 days before an event through 15 days after), so it never
    // permanently eats space in a nav that's already tight at the desktop
    // app's default width — see md/Craving_chat_v2.md's follow-up feedback.
    // A real page (CravingChatPage.tsx), not an anchor scroll on the Hub —
    // the scroll version felt unsatisfying as a nav destination reachable
    // from any page in the app.
    { to: '/craving-chat', label: t('nav.cravingChat'), icon: MessageCircle, adminOnly: false, show: !!chatEvent },
    { to: '/profile', label: t('nav.player'), icon: User, adminOnly: false, show: true },
    { to: '/events', label: t('nav.lanParty'), icon: CalendarDays, adminOnly: false, show: true },
    { to: '/finances', label: t('nav.treasury'), icon: DollarSign, adminOnly: false, show: treasuryEnabled },
    { to: '/prizes', label: t('nav.prizes'), icon: Gift, adminOnly: false, show: prizesEnabled },
    { to: '/planning', label: t('nav.planning'), icon: CalendarClock, adminOnly: false, show: planningEnabled },
    { to: '/tournaments', label: t('nav.arena'), icon: Trophy, adminOnly: false, show: true },
    { to: '/streams', label: t('nav.live'), icon: Radio, adminOnly: false, show: streamsEnabled },
    { to: '/media', label: t('nav.media'), icon: ImageIcon, adminOnly: false, show: true },
    { to: '/games-finder', label: t('nav.games'), icon: Gamepad2, adminOnly: false, show: gamesEnabled || lolStatsEnabled },
    { to: '/settings', label: t('nav.settings'), icon: Settings, adminOnly: true, show: true },
    { to: '/audit', label: t('nav.audit'), icon: ShieldAlert, adminOnly: true, show: true },
  ].filter((item) => item.show && (!item.adminOnly || isAdmin))

  const roleLabel = (role: string) => t(`nav.role.${role}`, role)

  return (
    <>
      <nav className="sticky top-0 z-50 bg-background/95 backdrop-blur border-b border-border">
        {/* Full-bleed, not max-w-6xl mx-auto: the logo needs to sit flush at
            the window's true top-left corner, and — just as importantly —
            the nav needs every available px of window width to fit Hub
            through Disconnect without scrolling (a centered max-w-6xl column
            was capping the flex row at 1152px even in a 1456px-wide window,
            ~300px it didn't need to give up). EN/FR moved to the footer
            instead of trying to also fit it here — see Footer.tsx.

            No justify-between/gap on this row either: Hub needs to line up
            with page content's own left edge (e.g. Dashboard's "// War
            room" tagline, at `max-w-6xl mx-auto px-6`'s computed inset —
            24px + (window - 1152px)/2 once the window is wide enough to
            center that column), not just sit some fixed gap after the logo.
            The logo (167px wide, brand text is identical in EN/FR) is
            handled separately below via a calc()'d margin-left on the items
            row: it clamps to "right after the logo" on narrower windows
            (where the content column isn't offset far enough yet to clear
            the logo without overlapping it) and converges to an exact match
            with the content inset as the window widens past ~1518px — a
            deliberate compromise, since at the desktop app's exact 1456px
            default the content inset (176px) actually falls a few px
            *inside* the logo's own footprint (ends at 191px), so pixel-
            perfect equality right at that width isn't physically possible
            without the two overlapping. Measured/verified via Playwright. */}
        <div className="w-full px-4 sm:px-6 h-14 flex items-center">
          <Link to="/" className="flex items-center gap-3 flex-shrink-0">
            <span className="text-accent font-sans font-black text-lg tracking-tighter leading-none">
              {t('nav.brandTop')}
            </span>
            <span className="w-px h-4 bg-border" />
            <span className="font-mono-label text-muted-foreground whitespace-nowrap">{t('nav.brandBottom')}</span>
          </Link>

          {/* Desktop nav. min-w-0 + overflow-x-auto stay as a last-resort
              safety net (e.g. an unusually narrow custom zoom level), not the
              primary fix — the primary fix is fitting everything, which the
              full-bleed width above plus icon-only labels below achieve at
              the desktop app's 1456px default width. flex-1 makes this row
              claim all the space the logo doesn't need, so the spacer below
              has room to push the user block to the right edge; the
              ml-[max(...)] is the Hub/content-alignment calc described
              above. */}
          <div className="hidden sm:flex items-center gap-1 min-w-0 overflow-x-auto flex-1 ml-[max(16px,calc((100vw-1152px)/2-167px))]">
            {navItems.map(({ to, label, icon: Icon }) => {
              const active = pathname === to
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-1.5 px-2 py-2 font-mono-label-nav transition-colors duration-150 ${
                    active ? 'text-accent' : 'text-[#9e9e9e] hover:text-foreground'
                  }`}
                  title={label}
                >
                  <Icon size={16} strokeWidth={1.5} />
                  <span className="hidden 3xl:inline">{label}</span>
                </Link>
              )
            })}

            <div className="flex-1" />

            <div className="w-px h-4 bg-border mx-2 flex-shrink-0" />

            {user && (
              <div className="flex items-center gap-3 flex-shrink-0">
                <div className="hidden xl:flex items-center gap-2 whitespace-nowrap">
                  {user.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt={user.username}
                      className="w-6 h-6 object-cover border border-border flex-shrink-0"
                    />
                  ) : (
                    <div className="w-6 h-6 bg-muted border border-border flex items-center justify-center flex-shrink-0">
                      <span className="text-xs font-bold text-muted-foreground">
                        {user.username[0].toUpperCase()}
                      </span>
                    </div>
                  )}
                  <span className="font-mono-label-nav text-[#9e9e9e]">{user.username}</span>
                  {user.role !== 'user' && (
                    <span className="font-mono-label text-accent text-[10px] flex-shrink-0">
                      [{roleLabel(user.role)}]
                    </span>
                  )}
                </div>

                {discordInvite && (
                  <ExternalLink
                    href={discordInvite}
                    className="hidden lg:flex items-center text-muted-foreground hover:text-accent transition-colors duration-150 flex-shrink-0"
                    title={t('nav.discordInvite')}
                    aria-label={t('nav.discordInvite')}
                  >
                    <DiscordIcon />
                  </ExternalLink>
                )}

                <button
                  onClick={logout}
                  className="flex items-center gap-1.5 px-2 py-2 text-muted-foreground hover:text-foreground transition-colors duration-150 flex-shrink-0"
                  title={t('nav.logout')}
                  aria-label={t('nav.logout')}
                >
                  <LogOut size={14} strokeWidth={1.5} />
                </button>
              </div>
            )}
          </div>

          {/* Mobile hamburger. ml-auto: itemsDiv is display:none below sm
              (doesn't participate in the row), so without this the button
              would sit right next to the logo instead of the right edge —
              there's no justify-between on the row anymore to do that for
              free (see comment above). */}
          <button
            className="sm:hidden ml-auto flex items-center justify-center p-2 text-muted-foreground hover:text-foreground transition-colors duration-150"
            onClick={() => setMenuOpen(prev => !prev)}
            aria-label={menuOpen ? t('nav.closeMenu') : t('nav.openMenu')}
          >
            {menuOpen ? <X size={18} strokeWidth={1.5} /> : <Menu size={18} strokeWidth={1.5} />}
          </button>
        </div>
      </nav>

      {/* Mobile full-screen menu */}
      {menuOpen && (
        <div className="sm:hidden fixed inset-0 top-14 z-40 bg-background flex flex-col overflow-y-auto">
          <div className="flex flex-col">
            {navItems.map(({ to, label, icon: Icon }) => {
              const active = pathname === to
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-4 px-6 py-4 font-mono-label-nav border-b border-border transition-colors duration-150 ${
                    active
                      ? 'text-accent border-l-2 border-l-accent pl-[22px]'
                      : 'text-[#9e9e9e] hover:text-foreground hover:bg-white/5'
                  }`}
                >
                  <Icon size={16} strokeWidth={1.5} />
                  {label}
                </Link>
              )
            })}
          </div>

          {user && (
            <div className="mt-auto border-t border-border px-6 py-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.username}
                    className="w-8 h-8 object-cover border border-border"
                  />
                ) : (
                  <div className="w-8 h-8 bg-muted border border-border flex items-center justify-center">
                    <span className="text-sm font-bold text-muted-foreground">
                      {user.username[0].toUpperCase()}
                    </span>
                  </div>
                )}
                <div>
                  <div className="font-mono-label text-foreground">{user.username}</div>
                  {user.role !== 'user' && (
                    <div className="font-mono-label text-accent text-[10px]">
                      [{roleLabel(user.role)}]
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3">
                {discordInvite && (
                  <ExternalLink
                    href={discordInvite}
                    className="flex items-center justify-center p-2 text-muted-foreground hover:text-accent transition-colors duration-150"
                    title={t('nav.discordInvite')}
                    aria-label={t('nav.discordInvite')}
                  >
                    <DiscordIcon className="w-5 h-5" />
                  </ExternalLink>
                )}
                <button
                  onClick={() => { logout(); setMenuOpen(false) }}
                  className="flex items-center gap-2 px-3 py-2 font-mono-label text-muted-foreground hover:text-foreground transition-colors duration-150"
                >
                  <LogOut size={14} strokeWidth={1.5} />
                  {t('nav.logout')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}
