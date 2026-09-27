import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { discordApi } from '../../lib/api'
import { isEmbeddedInDesktop, requestDiscordAuth } from '../../lib/desktopBridge'

function DiscordMark({ size = 18 }: { size?: number }) {
  // Official Discord "Clyde" mark (single path), inherits currentColor.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M20.317 4.369A19.79 19.79 0 0 0 16.558 3c-.2.36-.43.845-.588 1.23a18.27 18.27 0 0 0-3.94 0A12.6 12.6 0 0 0 11.44 3a19.74 19.74 0 0 0-3.762 1.369C3.61 8.09 2.88 11.71 3.15 15.28a19.9 19.9 0 0 0 4.885 2.46 15.1 15.1 0 0 0 1.05-1.71 12.9 12.9 0 0 1-1.652-.79c.14-.1.276-.207.406-.316a13.9 13.9 0 0 0 11.923 0c.132.11.267.216.406.316-.53.31-1.084.575-1.654.79.31.6.66 1.172 1.05 1.71a19.83 19.83 0 0 0 4.888-2.46c.317-4.14-.816-7.727-3.988-10.911ZM9.68 13.417c-.95 0-1.73-.87-1.73-1.94 0-1.07.766-1.94 1.73-1.94.972 0 1.746.878 1.73 1.94 0 1.07-.766 1.94-1.73 1.94Zm4.64 0c-.95 0-1.73-.87-1.73-1.94 0-1.07.766-1.94 1.73-1.94.972 0 1.746.878 1.73 1.94 0 1.07-.758 1.94-1.73 1.94Z" />
    </svg>
  )
}

/**
 * "Continue with Discord" button. Self-hides when Discord SSO isn't configured,
 * so callers can drop it in unconditionally. `inviteCode` is forwarded to the
 * backend so a fresh Discord account can be gated on (and RSVP'd into) an event.
 */
export default function DiscordButton({
  inviteCode,
  disabled,
  withDivider,
}: {
  inviteCode?: string
  disabled?: boolean
  withDivider?: boolean
}) {
  const { t } = useTranslation()
  const [enabled, setEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  // `busy` (React state) isn't enough on its own to stop a second
  // invocation of `go()` — it's applied to the button's `disabled` attribute
  // on the next render, which is too late if two click events land in the
  // same tick. Confirmed live in the desktop app: WebView2 can deliver a
  // duplicate click event for a single real click, and `go()` running twice
  // opens two separate Discord OAuth attempts (two different `state`
  // tokens), racing each other's native popups. `busyRef` is a plain
  // mutable flag checked synchronously at the top of `go()`, so the second
  // call bails out immediately regardless of React's render timing.
  const busyRef = useRef(false)

  useEffect(() => {
    let alive = true
    discordApi
      .config()
      .then((c) => alive && setEnabled(c.enabled))
      .catch(() => alive && setEnabled(false))
    return () => {
      alive = false
    }
  }, [])

  if (!enabled) return null

  const go = async () => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      if (isEmbeddedInDesktop()) {
        requestDiscordAuth('login', inviteCode)
      } else {
        window.location.href = await discordApi.authorize(inviteCode)
      }
    } finally {
      // A plain top-level redirect navigates this page away before this
      // ever runs. The desktop app's case doesn't (it hands off to the
      // system browser and this page stays mounted), so `busy` needs
      // resetting or the button would be stuck on "redirecting…" forever.
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <>
      {withDivider && (
        <div className="flex items-center gap-3 my-6">
          <div className="flex-1 h-px bg-border" />
          <span className="font-mono-label text-muted-foreground text-[10px]">{t('discord.or')}</span>
          <div className="flex-1 h-px bg-border" />
        </div>
      )}
      <button
        type="button"
        onClick={go}
        disabled={disabled || busy}
        className="w-full h-12 flex items-center justify-center gap-2.5 bg-[#5865F2] text-white font-mono-label hover:bg-[#4752c4] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <DiscordMark />
        {busy ? t('discord.redirecting') : t('discord.continueWith')}
      </button>
    </>
  )
}
