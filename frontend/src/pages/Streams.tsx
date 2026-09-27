import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { streamsApi } from '../lib/api'
import { useToast } from '../contexts/ToastContext'
import { LiveStream, LiveStatus } from '../types'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Input from '../components/ui/Input'
import { Plus, X, Radio, Play, Square, Trash2, Pencil, MessageSquare, Users, Clapperboard } from 'lucide-react'

// ── Stream Form Modal ─────────────────────────────────────────────────────────

interface StreamForm {
  channel_name: string
  title: string
  is_active: boolean
}

function StreamModal({
  stream,
  onClose,
  onSave,
}: {
  stream?: LiveStream
  onClose: () => void
  onSave: () => void
}) {
  const { t } = useTranslation()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<StreamForm>({
    defaultValues: stream
      ? { channel_name: stream.channel_name, title: stream.title ?? '', is_active: stream.is_active }
      : { channel_name: '', title: '', is_active: true },
  })

  const onSubmit = async (data: StreamForm) => {
    const payload = {
      channel_name: data.channel_name.trim(),
      title: data.title || undefined,
      is_active: data.is_active,
    }
    if (stream) {
      await streamsApi.update(stream.id, payload)
    } else {
      await streamsApi.create(payload)
    }
    onSave()
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-6">
      <div className="bg-card border border-border w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <p className="font-mono-label text-accent">{stream ? t('streams.editStream') : `+ ${t('streams.addStream')}`}</p>
          <button onClick={onClose}>
            <X size={16} className="text-muted-foreground hover:text-foreground" />
          </button>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <Input
            label={t('streams.channelOrClipLabel')}
            placeholder="channelname · twitch.tv/channel · clips.twitch.tv/ClipSlug"
            {...register('channel_name', { required: t('streams.channelRequired') })}
            error={errors.channel_name?.message}
          />
          <p className="font-mono-label text-muted-foreground text-[10px] -mt-2">
            {t('streams.channelHint')}
          </p>
          <Input
            label={t('streams.titleLabel')}
            placeholder={t('streams.titlePlaceholder')}
            {...register('title')}
          />
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              {...register('is_active')}
              className="w-4 h-4 border border-border bg-input accent-accent"
            />
            <span className="font-mono-label text-muted-foreground">{t('streams.activeVisible')}</span>
          </label>
          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('common.saving') : <><Plus size={14} /> {stream ? t('common.save') : t('streams.addStream')}</>}
            </Button>
            <Button variant="ghost" type="button" onClick={onClose}>{t('common.cancel')}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Stream Card ───────────────────────────────────────────────────────────────

function StreamCard({
  stream,
  isAdmin,
  liveStatus,
  onEdit,
  onDelete,
}: {
  stream: LiveStream
  isAdmin: boolean
  liveStatus?: LiveStatus
  onEdit: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const [watching, setWatching] = useState(false)
  const [showChat, setShowChat] = useState(false)
  const hostname = window.location.hostname

  const isClip = stream.stream_type === 'clip'
  const isLive = liveStatus?.is_live ?? false

  const playerSrc = isClip
    ? `https://clips.twitch.tv/embed?clip=${stream.channel_name}&parent=${hostname}`
    : `https://player.twitch.tv/?channel=${stream.channel_name}&parent=${hostname}&autoplay=true`

  const chatSrc = `https://www.twitch.tv/embed/${stream.channel_name}/chat?parent=${hostname}`

  return (
    <div
      className={`border bg-card group transition-all duration-150 ${
        stream.is_active ? 'border-accent/30' : 'border-border'
      }`}
    >
      <div className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div
              className={`w-10 h-10 flex items-center justify-center border flex-shrink-0 ${
                stream.is_active ? 'border-accent text-accent' : 'border-border text-muted-foreground'
              }`}
            >
              {isClip ? <Clapperboard size={18} strokeWidth={1.5} /> : <Radio size={18} strokeWidth={1.5} />}
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <h3 className="font-black text-lg tracking-tight text-foreground leading-none">
                  {stream.channel_name}
                </h3>
                <Badge variant={stream.is_active ? 'accent' : 'muted'}>
                  {isClip ? t('streams.clip') : stream.is_active ? t('streams.active') : t('streams.inactive')}
                </Badge>
                {isLive && !isClip && (
                  <Badge variant="danger">
                    <span className="inline-block w-1.5 h-1.5 bg-red-400 rounded-full mr-1 animate-pulse" />
                    {t('streams.live')}
                  </Badge>
                )}
              </div>
              {stream.title && (
                <p className="font-mono-label text-muted-foreground text-xs">{stream.title}</p>
              )}
              {isLive && liveStatus && (
                <p className="font-mono-label text-muted-foreground text-[10px] mt-1 flex items-center gap-2">
                  <Users size={9} /> {t('streams.viewers', { count: liveStatus.viewers })}
                  {liveStatus.game && <> · {liveStatus.game}</>}
                </p>
              )}
              {!isClip && (
                <p className="font-mono-label text-muted-foreground text-[10px] mt-1">
                  twitch.tv/{stream.channel_name}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1">
            {isAdmin && (
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={onEdit} className="p-1.5 text-muted-foreground hover:text-foreground transition-colors" title={t('common.edit')}>
                  <Pencil size={12} strokeWidth={1.5} />
                </button>
                <button onClick={onDelete} className="p-1.5 text-muted-foreground hover:text-red-400 transition-colors" title={t('common.delete')}>
                  <Trash2 size={12} strokeWidth={1.5} />
                </button>
              </div>
            )}
            {stream.is_active && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setWatching((w) => !w)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 font-mono-label text-xs transition-colors duration-150 border ${
                    watching
                      ? 'border-accent text-accent'
                      : 'border-border text-muted-foreground hover:border-foreground hover:text-foreground'
                  }`}
                >
                  {watching ? <Square size={10} strokeWidth={1.5} /> : <Play size={10} strokeWidth={1.5} />}
                  {watching ? t('streams.close') : t('streams.watch')}
                </button>
                {watching && !isClip && (
                  <button
                    onClick={() => setShowChat((c) => !c)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 font-mono-label text-xs transition-colors duration-150 border ${
                      showChat
                        ? 'border-accent text-accent'
                        : 'border-border text-muted-foreground hover:border-foreground hover:text-foreground'
                    }`}
                  >
                    <MessageSquare size={10} strokeWidth={1.5} />
                    {t('streams.chat')}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Player + optional chat */}
      {watching && stream.is_active && (
        <div className="border-t border-border">
          <div className={`flex ${showChat ? 'flex-col md:flex-row' : ''}`}>
            <div
              className={`relative w-full ${showChat ? 'md:w-2/3' : 'w-full'}`}
              style={{ paddingBottom: showChat ? undefined : '56.25%', aspectRatio: showChat ? '16/9' : undefined }}
            >
              <iframe
                src={playerSrc}
                title={`${stream.channel_name} on Twitch`}
                allowFullScreen
                className={showChat ? 'w-full h-full' : 'absolute inset-0 w-full h-full'}
                style={{ border: 'none', minHeight: showChat ? '300px' : undefined }}
              />
            </div>
            {showChat && !isClip && (
              <div className="w-full md:w-1/3 border-t md:border-t-0 md:border-l border-border" style={{ minHeight: '400px' }}>
                <iframe
                  src={chatSrc}
                  title={`${stream.channel_name} chat`}
                  className="w-full h-full"
                  style={{ border: 'none', minHeight: '400px' }}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Streams() {
  const { isAdmin } = useAuth()
  const { t } = useTranslation()
  const { push } = useToast()
  const [streams, setStreams] = useState<LiveStream[]>([])
  const [liveStatus, setLiveStatus] = useState<Record<string, LiveStatus>>({})
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingStream, setEditingStream] = useState<LiveStream | undefined>(undefined)

  const load = async () => {
    const data = await streamsApi.getAll()
    setStreams(data)
    setLoading(false)
    // Fetch live status in background (may fail if no Twitch credentials)
    try {
      const status = await streamsApi.getLiveStatus()
      setLiveStatus(status)
    } catch {
      /* no-op: Twitch credentials not configured */
    }
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (stream: LiveStream) => {
    if (!confirm(t('streams.removeConfirm', { name: stream.channel_name }))) return
    await streamsApi.delete(stream.id)
    await load()
    push(t('streams.streamDeleted'))
  }

  const handleSaved = async () => {
    await load()
    push(t('streams.streamSaved'))
  }

  const active = streams.filter((s) => s.is_active)
  const inactive = streams.filter((s) => !s.is_active)

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      <div className="flex items-start justify-between mb-12">
        <div>
          <div className="font-mono-label text-accent mb-3">{t('streams.tagline')}</div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
            {t('streams.heroLine1')}
            <br />
            <span className="text-accent">{t('streams.heroLine2')}</span>
          </h1>
        </div>
        {isAdmin && (
          <Button onClick={() => { setEditingStream(undefined); setShowModal(true) }}>
            <Plus size={14} /> {t('streams.addStream')}
          </Button>
        )}
      </div>

      {loading ? (
        <div className="space-y-4">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-28 bg-muted animate-pulse" />
          ))}
        </div>
      ) : streams.length === 0 ? (
        <div className="border border-border p-16 text-center">
          <Radio size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
          <p className="font-mono-label text-muted-foreground mb-1">{t('streams.noStreamsConfigured')}</p>
          {isAdmin && (
            <p className="text-sm text-muted-foreground">
              {t('streams.addStreamHint', { button: `+ ${t('streams.addStream')}` })}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-10">
          {active.length > 0 && (
            <section>
              <p className="font-mono-label text-accent mb-4">
                {t('streams.activeSection', { count: active.length })}
              </p>
              <div className="space-y-4">
                {active.map((s) => (
                  <StreamCard
                    key={s.id}
                    stream={s}
                    isAdmin={isAdmin}
                    liveStatus={liveStatus[s.channel_name]}
                    onEdit={() => { setEditingStream(s); setShowModal(true) }}
                    onDelete={() => handleDelete(s)}
                  />
                ))}
              </div>
            </section>
          )}

          {isAdmin && inactive.length > 0 && (
            <section>
              <p className="font-mono-label text-muted-foreground mb-4">
                {t('streams.inactiveSection', { count: inactive.length })}
              </p>
              <div className="space-y-4">
                {inactive.map((s) => (
                  <StreamCard
                    key={s.id}
                    stream={s}
                    isAdmin={isAdmin}
                    liveStatus={liveStatus[s.channel_name]}
                    onEdit={() => { setEditingStream(s); setShowModal(true) }}
                    onDelete={() => handleDelete(s)}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {showModal && (
        <StreamModal
          stream={editingStream}
          onClose={() => setShowModal(false)}
          onSave={handleSaved}
        />
      )}
    </main>
  )
}
