import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, X } from 'lucide-react'
import { backupApi } from '../lib/api'

// The admin's backups as a game: "SAVING… do not turn off the console" for the
// download, "LOADING…" for the restore. The server streams the archive both
// ways, so the bar measures real bytes. A 200 MB backup used to sit on
// "Preparing…" for minutes with nothing moving, and couldn't be restored at all.

const SEGMENTS = 24
const TIP_MS = 4500
const SPEED_WINDOW_MS = 2500
// After a restore the backend exits and the container brings it back.
const RESTART_FIRST_POLL_MS = 2500
const RESTART_POLL_MS = 1500
const RESTART_SLOW_MS = 90_000

type Look = 'starting' | 'running' | 'done' | 'failed'

function useTick(on: boolean) {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!on) return
    const id = window.setInterval(() => setTick((n) => n + 1), 250)
    return () => window.clearInterval(id)
  }, [on])
}

function clock(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/** Bytes as "19,2 Mo" / "1,40 Go", in the viewer's language. */
function useSize() {
  const { t, i18n } = useTranslation()
  const decimals = (n: number, digits: number) =>
    n.toLocaleString(i18n.language, { minimumFractionDigits: digits, maximumFractionDigits: digits })
  return (bytes: number) =>
    bytes >= 1024 ** 3
      ? t('settings.backupModal.gb', { n: decimals(bytes / 1024 ** 3, 2) })
      : t('settings.backupModal.mb', { n: decimals(bytes / 1024 ** 2, 1) })
}

/** Speed over the last few seconds of progress samples. */
function useSpeed() {
  const samples = useRef<{ at: number; bytes: number }[]>([])
  const push = (bytes: number) => {
    const now = Date.now()
    samples.current.push({ at: now, bytes })
    samples.current = samples.current.filter((s) => now - s.at <= SPEED_WINDOW_MS)
  }
  const reset = () => {
    samples.current = []
  }
  const s = samples.current
  const speed = s.length > 1 ? ((s[s.length - 1].bytes - s[0].bytes) * 1000) / Math.max(1, s[s.length - 1].at - s[0].at) : 0
  return { push, reset, speed }
}

/** The shared screen: save ring, segmented bar, big percentage, stats, tips. */
function SaveScreen({
  look,
  kicker,
  title,
  pct,
  stats,
  body,
  footer,
  actions,
}: {
  look: Look
  kicker: string
  title: string
  /** null: no measurable progress right now — the scanner sweeps the bar. */
  pct: number | null
  stats: ReactNode
  body?: ReactNode
  footer?: string
  actions: ReactNode
}) {
  const { t } = useTranslation()
  const [tip, setTip] = useState(0)
  const tips = t('settings.backupModal.tips', { returnObjects: true }) as string[]
  const running = look === 'starting' || look === 'running'

  useEffect(() => {
    if (!running || tips.length < 2) return
    const id = window.setInterval(() => setTip((n) => (n + 1) % tips.length), TIP_MS)
    return () => window.clearInterval(id)
  }, [running, tips.length])

  const filled = Math.round(((pct ?? 0) / 100) * SEGMENTS)
  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex items-center justify-center p-6" role="dialog" aria-modal="true" aria-label={title}>
      <div className="lpm-save w-full max-w-xl border border-border bg-card p-7 sm:p-9" data-phase={look === 'running' ? 'saving' : look}>
        <div className="flex items-start justify-between gap-6 mb-7">
          <div className="min-w-0">
            <p className="font-mono-label text-accent mb-2">{kicker}</p>
            <h2 className="text-3xl sm:text-4xl font-black tracking-tighter leading-none text-foreground">{title}</h2>
          </div>
          {/* The console's save icon: a ring of ticks lighting up in turn. */}
          <div className="lpm-save__ring shrink-0" aria-hidden="true">
            {look === 'done' ? (
              <Check size={26} className="text-accent" strokeWidth={3} />
            ) : look === 'failed' ? (
              <X size={26} className="text-red-400" strokeWidth={3} />
            ) : (
              Array.from({ length: 12 }, (_, i) => (
                <span key={i} style={{ transform: `rotate(${i * 30}deg)`, animationDelay: `${(i - 12) * 0.08}s` }} />
              ))
            )}
          </div>
        </div>

        <div
          className={`lpm-save__bar ${pct == null && running ? 'lpm-save__bar--scan' : ''}`}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct ?? undefined}
        >
          {Array.from({ length: SEGMENTS }, (_, i) => (
            <span
              key={i}
              className={i < filled ? 'is-on' : i === filled && running && pct != null ? 'is-next' : ''}
              style={{ animationDelay: `${i * 0.05}s` }}
            />
          ))}
        </div>

        <div className="flex items-end justify-between gap-4 mt-4">
          <p className="text-5xl font-black tracking-tighter leading-none tabular-nums text-foreground">
            {pct == null ? (look === 'failed' ? '—' : '…') : `${pct}%`}
          </p>
          {/* Not uppercased like the labels: "Mo" must not read "MO". */}
          <div className="text-right font-mono text-[11px] tracking-wide text-muted-foreground space-y-1">{stats}</div>
        </div>

        <div className="mt-7 min-h-[3.5rem] border-t border-border pt-4">
          {body ?? (running && tips.length > 0 ? (
            <p key={tip} className="lpm-save__tip text-sm text-muted-foreground">
              <span className="font-mono-label text-[10px] text-accent mr-2">{t('settings.backupModal.tipLabel')}</span>
              {tips[tip % tips.length]}
            </p>
          ) : null)}
        </div>

        <div className="flex items-center justify-between gap-4 mt-5">
          <p className={`font-mono-label text-[10px] ${running ? 'text-accent kiosk-pulse' : 'text-muted-foreground'}`}>{running ? footer : ''}</p>
          <div className="flex gap-3">{actions}</div>
        </div>
      </div>
    </div>
  )
}

const secondary =
  'font-mono-label text-[11px] px-4 py-2 border border-border text-muted-foreground hover:text-foreground hover:border-border-hover'
const primary = 'font-mono-label text-[11px] px-4 py-2 bg-accent text-accent-foreground hover:bg-accent/90'

// ── Download ──────────────────────────────────────────────────────────────────

export default function BackupModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const size = useSize()
  const speed = useSpeed()
  const [phase, setPhase] = useState<'starting' | 'saving' | 'done' | 'failed'>('starting')
  const [estimate, setEstimate] = useState(0)
  const [received, setReceived] = useState(0)
  const [result, setResult] = useState<{ name: string; size: number; ms: number } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const started = useRef(Date.now())
  const abort = useRef<AbortController | null>(null)
  const running = phase === 'starting' || phase === 'saving'
  useTick(running)

  useEffect(() => {
    const controller = new AbortController()
    abort.current = controller
    started.current = Date.now()
    speed.reset()
    setPhase('starting')
    setReceived(0)
    backupApi
      .download({
        signal: controller.signal,
        onStart: (bytes) => {
          setEstimate(bytes)
          setPhase('saving')
        },
        onProgress: (bytes) => {
          speed.push(bytes)
          setReceived(bytes)
        },
      })
      .then(({ blob, name, size: bytes }) => {
        backupApi.save(blob, name)
        setResult({ name, size: bytes, ms: Date.now() - started.current })
        setPhase('done')
      })
      .catch(() => {
        if (!controller.signal.aborted) setPhase('failed')
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt])

  // Real bytes against the server's estimate, held under 100 until the archive
  // actually ends — the estimate is close, not exact.
  const pct = phase === 'done' ? 100 : phase === 'saving' && estimate > 0 ? Math.min(99, Math.floor((received / estimate) * 100)) : null
  const eta = speed.speed > 0 && estimate > received ? ((estimate - received) / speed.speed) * 1000 : null

  return (
    <SaveScreen
      look={phase === 'saving' ? 'running' : phase}
      kicker={t(`settings.backupModal.${phase === 'done' ? 'kickerDone' : phase === 'failed' ? 'kickerFailed' : 'kicker'}`)}
      title={t(`settings.backupModal.${phase === 'done' ? 'doneTitle' : phase === 'failed' ? 'failedTitle' : 'title'}`)}
      pct={pct}
      footer={t('settings.backupModal.doNotClose')}
      stats={
        phase === 'done' && result ? (
          <>
            <p className="text-foreground">{size(result.size)}</p>
            <p>{clock(result.ms)}</p>
          </>
        ) : phase === 'failed' ? null : (
          <>
            <p className="text-foreground">
              {phase === 'starting'
                ? t('settings.backupModal.starting')
                : t('settings.backupModal.received', { received: size(received), total: size(estimate) })}
            </p>
            <p>
              {speed.speed > 0 && `${size(speed.speed)}/s · `}
              {eta != null
                ? t('settings.backupModal.eta', { eta: clock(eta) })
                : t('settings.backupModal.elapsed', { elapsed: clock(Date.now() - started.current) })}
            </p>
          </>
        )
      }
      body={
        phase === 'done' && result ? (
          <p className="text-sm text-muted-foreground break-all">{t('settings.backupModal.doneBody', { name: result.name })}</p>
        ) : phase === 'failed' ? (
          <p className="text-sm text-red-400">{t('settings.backupModal.failedBody')}</p>
        ) : undefined
      }
      actions={
        <>
          {phase === 'failed' && (
            <button onClick={() => setAttempt((n) => n + 1)} className={primary}>{t('settings.backupModal.retry')}</button>
          )}
          <button
            onClick={() => {
              if (running) abort.current?.abort()
              onClose()
            }}
            className={secondary}
          >
            {running ? t('settings.backupModal.cancel') : t('common.close')}
          </button>
        </>
      }
    />
  )
}

// ── Restore ───────────────────────────────────────────────────────────────────

type RestorePhase = 'uploading' | 'restoring' | 'restarting' | 'done' | 'failed'

/** Why a restore failed, from the HTTP status: 413 is the proxy in front of LPM
 *  (its own body limit), 507 the server's free space, 400 the archive itself. */
function failureKey(status: number | undefined) {
  if (status === 413) return 'tooLarge'
  if (status === 507) return 'noSpace'
  if (status === 400) return 'invalid'
  if (status === 403 || status === 401) return 'forbidden'
  return 'generic'
}

export function RestoreModal({ file, onClose }: { file: File; onClose: () => void }) {
  const { t } = useTranslation()
  const size = useSize()
  const speed = useSpeed()
  const [phase, setPhase] = useState<RestorePhase>('uploading')
  const [sent, setSent] = useState(0)
  const [failure, setFailure] = useState('generic')
  const [slow, setSlow] = useState(false)
  const started = useRef(Date.now())
  const abort = useRef<AbortController | null>(null)
  const running = phase === 'uploading' || phase === 'restoring' || phase === 'restarting'
  useTick(running)

  useEffect(() => {
    const controller = new AbortController()
    abort.current = controller
    let cancelled = false
    backupApi
      .restore(file, {
        signal: controller.signal,
        onProgress: (bytes) => {
          speed.push(bytes)
          setSent(bytes)
          if (bytes >= file.size) setPhase('restoring') // all sent: the server unpacks it now
        },
      })
      .then(async () => {
        // The backend exits right after answering; wait for the container to
        // bring it back. Any HTTP answer from it (even a 401: the restored
        // database may not know this session) means it's up; nginx answers
        // 502 while it's down.
        setPhase('restarting')
        const back = Date.now()
        await new Promise((r) => window.setTimeout(r, RESTART_FIRST_POLL_MS))
        while (!cancelled) {
          try {
            const res = await fetch('/api/settings/public-config', { cache: 'no-store' })
            if (res.status < 500) break
          } catch {
            // still down
          }
          if (Date.now() - back > RESTART_SLOW_MS) setSlow(true)
          await new Promise((r) => window.setTimeout(r, RESTART_POLL_MS))
        }
        if (cancelled) return
        setPhase('done')
        window.setTimeout(() => window.location.reload(), 1500)
      })
      .catch((e) => {
        if (controller.signal.aborted) return
        setFailure(failureKey(e?.response?.status))
        setPhase('failed')
      })
    return () => {
      cancelled = true
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const pct = phase === 'uploading' ? Math.min(99, Math.floor((sent / Math.max(1, file.size)) * 100)) : phase === 'done' ? 100 : null
  const eta = speed.speed > 0 && file.size > sent ? ((file.size - sent) / speed.speed) * 1000 : null
  const key = phase === 'failed' ? 'failed' : phase === 'done' ? 'done' : phase

  return (
    <SaveScreen
      look={phase === 'done' ? 'done' : phase === 'failed' ? 'failed' : 'running'}
      kicker={t(`settings.restoreModal.kicker.${key}`)}
      title={t(`settings.restoreModal.title.${key}`)}
      pct={pct}
      footer={t('settings.restoreModal.doNotClose')}
      stats={
        phase === 'failed' ? null : phase === 'uploading' ? (
          <>
            <p className="text-foreground">{t('settings.backupModal.received', { received: size(sent), total: size(file.size) })}</p>
            <p>
              {speed.speed > 0 && `${size(speed.speed)}/s · `}
              {eta != null
                ? t('settings.backupModal.eta', { eta: clock(eta) })
                : t('settings.backupModal.elapsed', { elapsed: clock(Date.now() - started.current) })}
            </p>
          </>
        ) : (
          <>
            <p className="text-foreground">{size(file.size)}</p>
            <p>{t('settings.backupModal.elapsed', { elapsed: clock(Date.now() - started.current) })}</p>
          </>
        )
      }
      body={
        phase === 'failed' ? (
          <p className="text-sm text-red-400">{t(`settings.restoreModal.failure.${failure}`)}</p>
        ) : phase === 'uploading' ? undefined : (
          <p className="text-sm text-muted-foreground">
            {slow ? t('settings.restoreModal.slow') : t(`settings.restoreModal.body.${phase}`)}
          </p>
        )
      }
      actions={
        phase === 'uploading' ? (
          <button
            onClick={() => {
              abort.current?.abort()
              onClose()
            }}
            className={secondary}
          >
            {t('settings.backupModal.cancel')}
          </button>
        ) : phase === 'failed' ? (
          <button onClick={onClose} className={secondary}>{t('common.close')}</button>
        ) : null
      }
    />
  )
}
