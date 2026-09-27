import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { AppConfigProvider, useAppConfig } from './contexts/AppConfigContext'
import { UpcomingEventProvider } from './contexts/UpcomingEventContext'
import { ToastProvider } from './contexts/ToastContext'
import { usePresenceHeartbeat } from './hooks/usePresenceHeartbeat'
import { ReactNode } from 'react'

import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import DiscordComplete from './pages/DiscordComplete'
import Dashboard from './pages/Dashboard'
import CravingChatPage from './pages/CravingChatPage'
import Profile from './pages/Profile'
import PlayerProfile from './pages/PlayerProfile'
import Finances from './pages/Finances'
import Prizes from './pages/Prizes'
import Tournaments from './pages/Tournaments'
import TournamentBracketPage from './pages/TournamentBracketPage'
import Planning from './pages/Planning'
import Events from './pages/Events'
import EventDetailPage from './pages/EventDetailPage'
import Streams from './pages/Streams'
import Media from './pages/Media'
import Settings from './pages/Settings'
import AuditLog from './pages/AuditLog'
import Kiosk from './pages/Kiosk'
import RecapPage, { SharedRecapPage } from './pages/RecapPage'
import SharedSetupPage from './pages/SharedSetupPage'
import MiniGamesPage from './pages/MiniGamesPage'
import Games from './pages/Games'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import AnnouncementBanner from './components/AnnouncementBanner'

function Protected({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="font-mono-label text-muted-foreground animate-pulse">
          {t('common.loading')}
        </span>
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

// Guards the Treasury page: if an admin has hidden the feature, deep-linking
// to /finances bounces back to the hub instead of rendering it.
function TreasuryOnly({ children }: { children: ReactNode }) {
  const { treasuryEnabled } = useAppConfig()
  if (!treasuryEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

// Same idea for the Prizes page, which is only present when the feature is on.
// Waits for /public-config first — same fix as MiniGamesOnly/GamesOnly below: the
// flag starts false, so judging on a cold load (a pasted link, a hard refresh)
// would bounce a perfectly valid URL back to the hub before the real value arrives.
function PrizesOnly({ children }: { children: ReactNode }) {
  const { prizesEnabled, configLoaded } = useAppConfig()
  if (!configLoaded) return <ConfigGate />
  if (!prizesEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

// Planning ("Calendar View") is opt-in; deep-linking to /planning while it's off
// bounces back to the hub. Same configLoaded fix as PrizesOnly above.
function PlanningOnly({ children }: { children: ReactNode }) {
  const { planningEnabled, configLoaded } = useAppConfig()
  if (!configLoaded) return <ConfigGate />
  if (!planningEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

// The post-event recap is opt-in; deep-linking to a recap while it's off bounces
// back to the hub. Same configLoaded fix as PrizesOnly above.
function RecapOnly({ children }: { children: ReactNode }) {
  const { recapEnabled, configLoaded } = useAppConfig()
  if (!configLoaded) return <ConfigGate />
  if (!recapEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

// Live (Twitch) is on by default; an admin without a streamer in their ranks can
// opt out, which bounces deep-links to /streams back to the hub same as Treasury.
function StreamsOnly({ children }: { children: ReactNode }) {
  const { streamsEnabled } = useAppConfig()
  if (!streamsEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

// Mini-games are opt-in. The feature's main entry point is a tab under Arena, but
// /minigames stays a real route (shareable link, Hub card target) and so needs the
// same deep-link guard as every other optional feature.
function MiniGamesOnly({ children }: { children: ReactNode }) {
  const { minigamesEnabled, configLoaded } = useAppConfig()
  // Wait for /public-config before deciding. The flag starts false, so judging on a
  // cold load — a pasted link, a hard refresh — would bounce a perfectly valid URL
  // back to the hub before the real value ever arrived.
  if (!configLoaded) return <ConfigGate />
  if (!minigamesEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

// The Games page is opt-in, same guard shape as MiniGamesOnly (waits for
// /public-config since the flags start false, so a fresh deep-link isn't
// bounced before the real value arrives). Either of its two features opens
// it: the finder (games library) or the League of Legends tracker.
function GamesOnly({ children }: { children: ReactNode }) {
  const { gamesEnabled, lolStatsEnabled, configLoaded } = useAppConfig()
  if (!configLoaded) return <ConfigGate />
  if (!gamesEnabled && !lolStatsEnabled) return <Navigate to="/" replace />
  return <>{children}</>
}

function ConfigGate() {
  const { t } = useTranslation()
  return (
    <div className="min-h-[50vh] flex items-center justify-center">
      <span className="font-mono-label text-muted-foreground animate-pulse">
        {t('common.loading')}
      </span>
    </div>
  )
}

function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />
      <AnnouncementBanner />
      <div className="flex-1">{children}</div>
      <Footer />
    </div>
  )
}

function AppRoutes() {
  const { user, isLoading } = useAuth()
  const { t } = useTranslation()
  usePresenceHeartbeat(!!user)

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <span className="font-mono-label text-muted-foreground animate-pulse">
          {t('common.loading')}
        </span>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/" replace /> : <Register />} />
      <Route path="/forgot-password" element={user ? <Navigate to="/" replace /> : <ForgotPassword />} />
      <Route path="/reset-password" element={user ? <Navigate to="/" replace /> : <ResetPassword />} />
      <Route path="/auth/discord/complete" element={<DiscordComplete />} />

      {/* Big-screen kiosk: fullscreen, no Navbar/Layout, token-authorized (no
          user session). Renders unattended on the projector all weekend. */}
      <Route path="/kiosk" element={<Kiosk />} />

      {/* Public recap: like the kiosk, no Navbar/Layout and no user session —
          authorized by its share token alone. Never carries money. */}
      <Route path="/recap/shared" element={<SharedRecapPage />} />

      {/* Public setup share: same shape — no Navbar/Layout, no user session,
          authorized by its share token alone. Username, avatar, components and
          photos only: never an email, never a phone. No SetupOnly guard, because
          the token dependency already 404s when the feature is off and a guard
          would need AppConfigContext, which requires a logged-in user. */}
      <Route path="/setup/shared" element={<SharedSetupPage />} />

      <Route path="/" element={<Protected><Layout><Dashboard /></Layout></Protected>} />
      <Route path="/craving-chat" element={<Protected><Layout><CravingChatPage /></Layout></Protected>} />
      <Route path="/profile" element={<Protected><Layout><Profile /></Layout></Protected>} />
      <Route path="/players/:userId" element={<Protected><Layout><PlayerProfile /></Layout></Protected>} />
      <Route path="/events" element={<Protected><Layout><Events /></Layout></Protected>} />
      <Route path="/events/:id" element={<Protected><Layout><EventDetailPage /></Layout></Protected>} />
      <Route path="/events/:eventId/recap" element={<Protected><Layout><RecapOnly><RecapPage /></RecapOnly></Layout></Protected>} />
      <Route path="/finances" element={<Protected><Layout><TreasuryOnly><Finances /></TreasuryOnly></Layout></Protected>} />
      <Route path="/prizes" element={<Protected><Layout><PrizesOnly><Prizes /></PrizesOnly></Layout></Protected>} />
      <Route path="/planning" element={<Protected><Layout><PlanningOnly><Planning /></PlanningOnly></Layout></Protected>} />
      <Route path="/tournaments" element={<Protected><Layout><Tournaments /></Layout></Protected>} />
      <Route path="/tournaments/:id/bracket" element={<Protected><Layout><TournamentBracketPage /></Layout></Protected>} />
      <Route path="/streams" element={<Protected><Layout><StreamsOnly><Streams /></StreamsOnly></Layout></Protected>} />
      <Route path="/media" element={<Protected><Layout><Media /></Layout></Protected>} />
      <Route path="/minigames" element={<Protected><Layout><MiniGamesOnly><MiniGamesPage /></MiniGamesOnly></Layout></Protected>} />
      <Route path="/games-finder" element={<Protected><Layout><GamesOnly><Games /></GamesOnly></Layout></Protected>} />
      <Route path="/settings" element={<Protected><Layout><Settings /></Layout></Protected>} />
      <Route path="/audit" element={<Protected><Layout><AuditLog /></Layout></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <AppConfigProvider>
            <UpcomingEventProvider>
              <AppRoutes />
            </UpcomingEventProvider>
          </AppConfigProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
