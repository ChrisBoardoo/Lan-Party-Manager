import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Gamepad2, Trash2, Trophy } from 'lucide-react'

import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import { miniGamesApi } from '../lib/api'
import { formatDate } from '../lib/formatDate'
import { MiniGameInfo, MiniGameScore } from '../types'

/** Format a raw score for display, driven by the game's declared metric rather
 *  than by its slug — so a second game that also ranks on time gets the right
 *  formatting for free, and an unknown metric still renders as a plain number. */
export function formatMiniGameScore(metric: string, value: number): string {
  if (metric === 'seconds_survived' || metric === 'duration_seconds') {
    const minutes = Math.floor(value / 60)
    const seconds = value % 60
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }
  return value.toLocaleString()
}

/** Detail values are plain integers because the backend drops booleans from the blob
 *  (they'd be ambiguous once coerced), so a game sends a yes/no as 1/0. Rendering that
 *  raw gives a column reading "GAGNÉ 0", which nobody parses as "lost". Fields whose
 *  name reads as a yes/no get a tick instead. */
const BOOLEAN_DETAILS = new Set(['won', 'perfect', 'flawless'])

export function formatDetail(field: string, value: number | undefined): string {
  if (value === undefined) return '—'
  if (BOOLEAN_DETAILS.has(field)) return value ? '✓' : '—'
  return value.toLocaleString()
}

/** Games live at frontend/public/games/<slug>/index.html — the slug in the backend
 *  registry IS the folder name, which is what keeps adding a game to one entry there
 *  plus one folder here. */
const gameUrl = (slug: string) => `/games/${slug}/index.html`

export default function MiniGames() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { push } = useToast()

  const [games, setGames] = useState<MiniGameInfo[]>([])
  const [active, setActive] = useState<MiniGameInfo | null>(null)
  const [board, setBoard] = useState<MiniGameScore[]>([])
  const [myBest, setMyBest] = useState<MiniGameScore | null>(null)
  const [loading, setLoading] = useState(true)

  const iframeRef = useRef<HTMLIFrameElement>(null)
  // The postMessage listener is registered once, but needs the *current* game to
  // refresh the right board. A ref avoids tearing down and rebuilding the listener
  // (and with it the iframe's in-flight replies) every time the selection changes.
  const activeRef = useRef<MiniGameInfo | null>(null)
  activeRef.current = active

  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    miniGamesApi
      .listGames()
      .then((list) => {
        setGames(list)
        setActive((current) => current ?? list[0] ?? null)
      })
      .catch(() => setGames([]))
      .finally(() => setLoading(false))
  }, [])

  const refreshBoard = useCallback(async (slug: string) => {
    const [rows, best] = await Promise.all([
      miniGamesApi.leaderboard(slug),
      miniGamesApi.myBest(slug),
    ])
    setBoard(rows)
    setMyBest(best)
  }, [])

  useEffect(() => {
    if (!active) return
    refreshBoard(active.slug).catch(() => {
      setBoard([])
      setMyBest(null)
    })
  }, [active, refreshBoard])

  // ── Bridge to the embedded game ────────────────────────────────────────────
  // The game never calls the API itself; it posts here and this component — which
  // holds the auth token — does the real request. See public/games/lpm-bridge.js.
  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return

      const data = event.data
      if (!data || data.source !== 'lpm-minigame') return

      // Only accept messages from the iframe we actually mounted, never from some
      // other frame that happens to share our origin.
      const frame = iframeRef.current
      if (!frame || event.source !== frame.contentWindow) return

      const reply = (payload: unknown) => {
        frame.contentWindow?.postMessage(
          { source: 'lpm-host', id: data.id, payload },
          window.location.origin,
        )
      }

      if (data.type === 'run-start') {
        try {
          const run = await miniGamesApi.startRun(String(data.game))
          reply({ token: run.token })
        } catch {
          // Unscored rather than broken: the game carries on, the run just doesn't count.
          reply(null)
        }
        return
      }

      if (data.type === 'run-end') {
        try {
          const result = await miniGamesApi.submitRun(
            String(data.token),
            Number(data.score),
            (data.details ?? {}) as Record<string, number>,
          )
          reply({ personal_best: result.personal_best, rank: result.rank })

          const slug = activeRef.current?.slug
          if (slug) await refreshBoard(slug)

          if (result.personal_best) {
            push(
              result.rank
                ? t('minigames.newBestRanked', { rank: result.rank })
                : t('minigames.newBest'),
              'success',
            )
          }
        } catch (err: any) {
          reply(null)
          // A rejected run is the anti-cheat validation doing its job, or a genuine
          // network failure — either way the player deserves to know it didn't count.
          push(err?.response?.data?.detail || t('minigames.submitFailed'), 'error')
        }
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [push, refreshBoard, t])

  const handleDelete = async (score: MiniGameScore) => {
    if (!active) return
    if (!confirm(t('minigames.deleteConfirm', { username: score.user.username }))) return
    await miniGamesApi.deleteScore(score.id)
    await refreshBoard(active.slug)
  }

  const gameName = (slug: string) => t(`minigames.game.${slug}.name`, slug)
  const gameTagline = (slug: string) => t(`minigames.game.${slug}.tagline`, '')

  if (loading) {
    return <div className="h-96 border border-border animate-pulse" />
  }

  if (!active) {
    return (
      <div className="border border-border p-8 text-center">
        <Gamepad2 size={24} strokeWidth={1} className="text-muted-foreground mx-auto mb-3" />
        <p className="font-mono-label text-muted-foreground">{t('minigames.noGames')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Game picker. Rendered from the server registry, so it grows on its own as
          games are added — no catalogue to keep in sync here. Hidden while there's
          only one game, where a one-item picker is just noise. */}
      {games.length > 1 && (
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
          {games.map((game) => (
            <button
              key={game.slug}
              onClick={() => setActive(game)}
              className={`border text-left transition-all duration-150 overflow-hidden group ${
                game.slug === active.slug
                  ? 'border-accent'
                  : 'border-border hover:border-border-hover'
              }`}
            >
              {/* Cover art is a real screenshot of the game's title screen, regenerated
                  by scripts/generate-game-covers.mjs. Found by convention at
                  /games/<slug>/cover.png so a new game needs no entry here — and a game
                  shipped without one just falls back to the label block below. */}
              <div className="aspect-video bg-muted overflow-hidden">
                <img
                  src={`/games/${game.slug}/cover.png`}
                  alt=""
                  loading="lazy"
                  className={`w-full h-full object-cover transition-opacity duration-150 ${
                    game.slug === active.slug ? '' : 'opacity-60 group-hover:opacity-100'
                  }`}
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                />
              </div>
              <div className="px-3 py-2">
                <div className="font-bold text-sm text-foreground truncate">
                  {gameName(game.slug)}
                </div>
                <div className="font-mono-label text-muted-foreground text-[10px] mt-0.5 truncate">
                  {t(`minigames.metric.${game.metric}`, game.metric)}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      <div>
        <div className="flex items-baseline justify-between mb-3 gap-4">
          <div className="min-w-0">
            <h3 className="font-bold text-foreground">{gameName(active.slug)}</h3>
            {gameTagline(active.slug) && (
              <p className="font-mono-label text-muted-foreground text-[10px] mt-1">
                {gameTagline(active.slug)}
              </p>
            )}
          </div>
          <span className="font-mono-label text-muted-foreground text-[10px] flex-shrink-0">
            {t('minigames.soloOnly')}
          </span>
        </div>

        {/* key on the slug so switching games remounts the frame — otherwise the
            previous game keeps running (and its audio playing) behind the new src. */}
        <iframe
          key={active.slug}
          ref={iframeRef}
          src={gameUrl(active.slug)}
          title={gameName(active.slug)}
          className="w-full border border-border bg-black block"
          style={{ aspectRatio: '16 / 9', minHeight: 420 }}
          // The game is same-origin and needs scripts; it never needs to navigate
          // the top window or open popups.
          sandbox="allow-scripts allow-same-origin"
        />
      </div>

      {/* ── Leaderboard ──────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Trophy size={14} strokeWidth={1.5} className="text-accent" />
          <h3 className="font-mono-label text-muted-foreground">
            {t('minigames.leaderboard')}
          </h3>
          {myBest && (
            <span className="font-mono-label text-muted-foreground text-[10px] ml-auto tabular-nums">
              {t('minigames.yourBest')}{' '}
              <span className="text-accent">
                {formatMiniGameScore(active.metric, myBest.score)}
              </span>
            </span>
          )}
        </div>

        {board.length === 0 ? (
          <div className="border border-border p-8 text-center">
            <Gamepad2 size={24} strokeWidth={1} className="text-muted-foreground mx-auto mb-3" />
            <p className="font-mono-label text-muted-foreground">{t('minigames.noScoresYet')}</p>
          </div>
        ) : (
          <div className="border border-border overflow-x-auto">
            <table className="w-full text-sm min-w-[34rem]">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-2 text-left font-mono-label text-muted-foreground w-12">#</th>
                  <th className="px-4 py-2 text-left font-mono-label text-muted-foreground">
                    {t('minigames.player')}
                  </th>
                  <th className="px-4 py-2 text-right font-mono-label text-muted-foreground">
                    {t(`minigames.metric.${active.metric}`, active.metric)}
                  </th>
                  {active.detail_fields.map((field) => (
                    <th
                      key={field}
                      className="px-4 py-2 text-right font-mono-label text-muted-foreground hidden sm:table-cell"
                    >
                      {t(`minigames.detail.${field}`, field)}
                    </th>
                  ))}
                  <th className="px-4 py-2 text-right font-mono-label text-muted-foreground hidden md:table-cell">
                    {t('minigames.when')}
                  </th>
                  {isAdmin && <th className="w-10" />}
                </tr>
              </thead>
              <tbody>
                {board.map((row, index) => {
                  const isMe = row.user.id === user?.id
                  return (
                    <tr
                      key={row.id}
                      className={`border-b border-border last:border-b-0 ${
                        isMe ? 'bg-accent/5' : ''
                      }`}
                    >
                      <td className="px-4 py-3 font-mono-label text-muted-foreground tabular-nums">
                        {index + 1}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          to={`/players/${row.user.id}`}
                          className="flex items-center gap-2 group min-w-0"
                        >
                          {row.user.avatar_url ? (
                            <img
                              src={row.user.avatar_url}
                              alt=""
                              className="w-6 h-6 object-cover border border-border flex-shrink-0"
                            />
                          ) : (
                            <div className="w-6 h-6 bg-muted border border-border flex items-center justify-center flex-shrink-0">
                              <span className="text-[10px] font-bold text-muted-foreground">
                                {row.user.username[0].toUpperCase()}
                              </span>
                            </div>
                          )}
                          <span
                            className={`truncate group-hover:text-accent transition-colors duration-150 ${
                              isMe ? 'text-accent' : 'text-foreground'
                            }`}
                          >
                            {row.user.username}
                          </span>
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-foreground tabular-nums">
                        {formatMiniGameScore(active.metric, row.score)}
                      </td>
                      {active.detail_fields.map((field) => (
                        <td
                          key={field}
                          className="px-4 py-3 text-right text-muted-foreground tabular-nums hidden sm:table-cell"
                        >
                          {formatDetail(field, row.details[field])}
                        </td>
                      ))}
                      <td className="px-4 py-3 text-right font-mono-label text-muted-foreground text-[10px] hidden md:table-cell">
                        {formatDate(row.created_at)}
                      </td>
                      {isAdmin && (
                        <td className="px-2 py-3 text-right">
                          <button
                            onClick={() => handleDelete(row)}
                            className="text-muted-foreground hover:text-red-400 transition-colors duration-150"
                            title={t('minigames.deleteScore')}
                            aria-label={t('minigames.deleteScore')}
                          >
                            <Trash2 size={13} strokeWidth={1.5} />
                          </button>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
