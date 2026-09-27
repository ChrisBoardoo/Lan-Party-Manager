import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { notifyDesktopLogin, notifyDesktopLogout } from '../lib/desktopBridge'

/**
 * Landing page for the Discord OAuth round-trip. The backend redirects here with
 * the freshly-minted JWT in the URL *fragment* (`#token=…`) — the fragment never
 * reaches the server, so the token can't leak into access logs. We read it,
 * store it, hydrate the user, then bounce to the hub.
 */
export default function DiscordComplete() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { refreshUser } = useAuth()
  const [failed, setFailed] = useState(false)
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const token = params.get('token')
    if (!token) {
      setFailed(true)
      return
    }
    localStorage.setItem('token', token)
    notifyDesktopLogin(token)
    // Clear the token from the address bar before anything else renders.
    window.history.replaceState(null, '', '/auth/discord/complete')
    refreshUser()
      .then(() => navigate('/', { replace: true }))
      .catch(() => {
        localStorage.removeItem('token')
        notifyDesktopLogout()
        setFailed(true)
      })
  }, [navigate, refreshUser])

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      {failed ? (
        <div className="text-center">
          <p className="font-mono-label text-red-400 mb-3">{t('discord.signInFailed')}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="font-mono-label text-accent hover:text-accent/80"
          >
            {t('discord.backToLogin')} →
          </button>
        </div>
      ) : (
        <span className="font-mono-label text-muted-foreground animate-pulse">
          {t('discord.signingIn')}
        </span>
      )}
    </div>
  )
}
