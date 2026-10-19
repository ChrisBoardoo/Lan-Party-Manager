import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { trophiesApi } from '../../lib/api'
import { useActivityFeed } from '../../hooks/useActivityFeed'
import { useAuth } from '../../contexts/AuthContext'
import { useAppConfig } from '../../contexts/AppConfigContext'
import { useToast } from '../../contexts/ToastContext'
import type { TrophyBallot, TrophyEdition } from '../../types'
import TrophyIcon from './TrophyIcon'

// Trophy night, the crew's side: a modal that opens by itself on any page once
// an admin launches the votes (or sends a reminder), one trophy per screen.
// Mounted once in the app layout. The event page's inline ballot stays — this
// is the same vote, just brought to wherever the member is.

/** Open the vote modal from anywhere (the Hub banner, a feed entry). */
export const OPEN_TROPHY_BALLOT = 'lpm:open-trophy-ballot'
export const openTrophyBallot = () => window.dispatchEvent(new Event(OPEN_TROPHY_BALLOT))
/** Fired with the number of votes still to cast whenever the ballot changes. */
export const TROPHY_BALLOT_PENDING = 'lpm:trophy-ballot-pending'

// Fallback for what the activity socket doesn't announce (a single trophy
// opened from its card, a launch without notification, the vote closing).
const POLL_MS = 30_000
// A beat on the chosen avatar before moving on to the next trophy.
const ADVANCE_MS = 450
const DISMISS_KEY = 'lpm.trophyBallot.dismissed'
const WAKE_ACTIONS = new Set(['trophy_vote_open', 'trophy_vote_nudge'])

const pendingOf = (b: TrophyBallot | null) => (b ? b.editions.filter((e) => e.my_vote == null) : [])

// What the member was asked about when they said "later": the modal comes back
// on its own only once that changes — another trophy opened, or a reminder.
const signatureOf = (b: TrophyBallot) => `${b.event_id}:${b.editions.map((e) => e.id).join(',')}:${b.nudge_id ?? ''}`

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISS_KEY)
  } catch {
    return null
  }
}

function writeDismissed(sig: string) {
  try {
    localStorage.setItem(DISMISS_KEY, sig)
  } catch {
    // Private mode: the modal just comes back on the next poll.
  }
}

function Avatar({ name, url }: { name: string; url: string | null }) {
  return url ? (
    <img src={url} alt="" className="w-14 h-14 object-cover" />
  ) : (
    <span className="w-14 h-14 bg-muted flex items-center justify-center font-black text-xl">
      {name.charAt(0).toUpperCase()}
    </span>
  )
}

export default function TrophyVoteModal() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { trophiesEnabled } = useAppConfig()
  const { push } = useToast()
  const enabled = !!user && trophiesEnabled

  const [ballot, setBallot] = useState<TrophyBallot | null>(null)
  const [open, setOpen] = useState(false)
  // Index into ballot.editions; editions.length = the closing screen.
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const forceOpenRef = useRef(false)
  const openRef = useRef(false)
  openRef.current = open
  const advanceRef = useRef<number | null>(null)

  const firstPending = (b: TrophyBallot) => {
    const i = b.editions.findIndex((e) => e.my_vote == null)
    return i === -1 ? 0 : i
  }

  const refresh = useCallback(async () => {
    if (!enabled) return
    let next: TrophyBallot | null
    try {
      next = await trophiesApi.ballot()
    } catch {
      return // offline or feature off: keep whatever is on screen
    }
    setBallot(next)
    window.dispatchEvent(new CustomEvent(TROPHY_BALLOT_PENDING, { detail: pendingOf(next).length }))
    if (!next || next.editions.length === 0) {
      setOpen(false)
      return
    }
    const wanted = forceOpenRef.current || (pendingOf(next).length > 0 && readDismissed() !== signatureOf(next))
    forceOpenRef.current = false
    if (wanted && !openRef.current) {
      setStep(firstPending(next))
      setOpen(true)
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) return
    refresh()
    const id = window.setInterval(refresh, POLL_MS)
    const onFocus = () => document.visibilityState === 'visible' && refresh()
    const onOpen = () => {
      forceOpenRef.current = true
      refresh()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    window.addEventListener(OPEN_TROPHY_BALLOT, onOpen)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
      window.removeEventListener(OPEN_TROPHY_BALLOT, onOpen)
    }
  }, [enabled, refresh])

  // Votes launched or a reminder sent: the notification arrives on the
  // activity socket within a couple of seconds.
  useActivityFeed(enabled, (items) => {
    if (items.some((i) => WAKE_ACTIONS.has(i.action))) refresh()
  })

  // Keep the page behind still while the modal is up.
  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [open])

  useEffect(() => () => {
    if (advanceRef.current !== null) window.clearTimeout(advanceRef.current)
  }, [])

  const later = useCallback(() => {
    if (ballot) writeDismissed(signatureOf(ballot))
    setOpen(false)
  }, [ballot])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && later()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, later])

  if (!open || !ballot || ballot.editions.length === 0) return null

  const total = ballot.editions.length
  const edition: TrophyEdition | undefined = ballot.editions[step]
  const left = pendingOf(ballot).length

  // After a vote: the next trophy still without one, forward only — a trophy
  // skipped earlier stays skipped, and the closing screen offers to go back.
  const nextStep = (b: TrophyBallot, from: number) => {
    for (let i = from + 1; i < b.editions.length; i++) {
      if (b.editions[i].my_vote == null) return i
    }
    return b.editions.length
  }

  const vote = async (nomineeId: number) => {
    if (!edition || busy) return
    setBusy(true)
    try {
      const updated = await trophiesApi.vote(edition.id, nomineeId)
      const b = { ...ballot, editions: ballot.editions.map((e) => (e.id === updated.id ? updated : e)) }
      setBallot(b)
      window.dispatchEvent(new CustomEvent(TROPHY_BALLOT_PENDING, { detail: pendingOf(b).length }))
      advanceRef.current = window.setTimeout(() => setStep(nextStep(b, step)), ADVANCE_MS)
    } catch {
      push(t('trophies.voteFailed'), 'error')
      refresh() // most likely the vote was closed meanwhile
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-background/90 backdrop-blur-sm flex items-end sm:items-center justify-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={t('trophies.ballot.kicker')}
    >
      <div className="bg-card border border-border w-full sm:max-w-2xl max-h-[100dvh] sm:max-h-[90vh] overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-5 sm:px-6 pt-5">
          <div className="min-w-0">
            <p className="font-mono-label text-accent">// {t('trophies.ballot.kicker')}</p>
            <p className="font-mono-label text-muted-foreground text-[10px] mt-1 truncate">{ballot.event_title}</p>
          </div>
          <button onClick={later} className="text-muted-foreground hover:text-foreground p-1" aria-label={t('trophies.ballot.later')}>
            <X size={16} />
          </button>
        </div>

        {/* Progress: one mark per trophy, filled once voted */}
        <div className="flex gap-1.5 px-5 sm:px-6 mt-4" aria-hidden="true">
          {ballot.editions.map((e, i) => (
            <button
              key={e.id}
              tabIndex={-1}
              onClick={() => setStep(i)}
              className={`h-1.5 flex-1 transition-colors ${
                e.my_vote != null ? 'bg-accent' : 'bg-muted'
              } ${i === step ? 'outline outline-1 outline-offset-2 outline-foreground' : ''}`}
            />
          ))}
        </div>

        {edition ? (
          <div key={edition.id} className="px-5 sm:px-6 py-6 flex-1">
            <p className="font-mono-label text-muted-foreground text-[10px] mb-4">
              {t('trophies.ballot.progress', { current: step + 1, total })}
            </p>
            <div className="flex items-center gap-4 mb-2">
              <TrophyIcon trophy={edition.trophy} className="w-16 h-16 text-5xl" />
              <h2 className="text-3xl font-black tracking-tight leading-none text-foreground">{edition.trophy.name}</h2>
            </div>
            {edition.trophy.description && <p className="text-sm text-muted-foreground mb-2">{edition.trophy.description}</p>}
            <p className="font-mono-label text-foreground text-xs mt-5 mb-3">
              {edition.my_vote != null ? t('trophies.youVoted') : t('trophies.ballot.pickOne')}
            </p>

            {ballot.nominees.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('trophies.ballot.nobody')}</p>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {ballot.nominees.map((n) => {
                  const mine = edition.my_vote === n.user_id
                  return (
                    <button
                      key={n.user_id}
                      disabled={busy}
                      onClick={() => !mine && vote(n.user_id)}
                      aria-pressed={mine}
                      className={`relative flex flex-col items-center gap-2 p-3 border transition-colors disabled:opacity-60 ${
                        mine ? 'border-accent bg-accent/10' : 'border-border hover:border-accent/60'
                      }`}
                    >
                      <Avatar name={n.username} url={n.avatar_url} />
                      <span className={`text-xs font-semibold truncate max-w-full ${mine ? 'text-accent' : 'text-foreground'}`}>
                        {n.username}
                      </span>
                      {mine && (
                        <span className="absolute top-1.5 right-1.5 bg-accent text-accent-foreground p-0.5">
                          <Check size={10} strokeWidth={3} />
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        ) : (
          // Closing screen
          <div className="px-5 sm:px-6 py-10 text-center flex-1">
            {left === 0 ? (
              <>
                <div className="text-6xl mb-4" aria-hidden="true">🗳️</div>
                <h2 className="text-3xl font-black tracking-tight text-foreground mb-3">{t('trophies.ballot.doneTitle')}</h2>
                <p className="text-sm text-muted-foreground max-w-sm mx-auto">{t('trophies.ballot.doneBody')}</p>
              </>
            ) : (
              <>
                <div className="text-6xl mb-4" aria-hidden="true">⏳</div>
                <h2 className="text-2xl font-black tracking-tight text-foreground mb-5">
                  {t('trophies.ballot.leftTitle', { count: left })}
                </h2>
                <button
                  onClick={() => setStep(firstPending(ballot))}
                  className="font-mono-label text-[11px] px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                  {t('trophies.ballot.backToVote')}
                </button>
              </>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center gap-2 px-5 sm:px-6 py-4 border-t border-border">
          {edition ? (
            <>
              <button
                onClick={() => setStep(Math.max(0, step - 1))}
                disabled={step === 0}
                className="font-mono-label text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-30 flex items-center gap-1"
              >
                <ChevronLeft size={12} /> {t('trophies.ballot.previous')}
              </button>
              <button
                onClick={later}
                className="ml-auto font-mono-label text-[11px] text-muted-foreground hover:text-foreground underline"
              >
                {t('trophies.ballot.later')}
              </button>
              <button
                onClick={() => setStep(step + 1)}
                className="font-mono-label text-[11px] px-3 py-1.5 border border-border text-foreground hover:border-accent hover:text-accent transition-colors flex items-center gap-1"
              >
                {edition.my_vote != null ? t('trophies.ballot.next') : t('trophies.ballot.skip')} <ChevronRight size={12} />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setStep(0)}
                className="font-mono-label text-[11px] text-muted-foreground hover:text-foreground underline"
              >
                {t('trophies.ballot.review')}
              </button>
              <button
                onClick={later}
                className="ml-auto font-mono-label text-[11px] px-4 py-1.5 bg-accent text-accent-foreground hover:bg-accent/90"
              >
                {t('trophies.ballot.close')}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
