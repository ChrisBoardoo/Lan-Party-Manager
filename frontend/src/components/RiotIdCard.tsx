import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Link2, Pencil, Trash2, X } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usersApi } from '../lib/api'
import { normalizeRiotId } from '../lib/riotId'
import Button from './ui/Button'
import Input from './ui/Input'

// The profile "Riot ID" card — the GameName#TAG League of Legends end-of-game
// captures will be matched against (see backend/riot_id.py). Typed rather than
// OAuth-linked like Discord/Steam: Riot's sign-in needs an approved production
// key. Self-contained like GamesLibraryCard, saved through PUT /users/{id}.
export default function RiotIdCard() {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const startEdit = () => {
    setDraft(user?.riot_id ?? '')
    setError('')
    setEditing(true)
  }

  // `null` clears it — also what saving an emptied field means.
  const save = async (raw: string | null) => {
    if (!user) return
    let value: string | null = null
    if (raw !== null && raw.trim()) {
      value = normalizeRiotId(raw)
      if (!value) {
        setError(t('profile.riotIdInvalid'))
        return
      }
    }
    if (value === (user.riot_id ?? null)) {
      setEditing(false)
      return
    }
    setSaving(true)
    setError('')
    try {
      await usersApi.update(user.id, { riot_id: value })
      await refreshUser()
      setEditing(false)
    } catch (e: any) {
      const status = e.response?.status
      setError(
        status === 409 ? t('profile.riotIdTaken')
          : status === 422 ? t('profile.riotIdInvalid')
            : t('profile.riotIdSaveFailed'),
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border border-border bg-card p-6 space-y-3">
      <p className="font-mono-label text-muted-foreground flex items-center gap-1.5">
        <Link2 size={12} strokeWidth={1.5} /> {t('profile.riotIdTitle')}
      </p>
      <p className="text-xs text-muted-foreground">{t('profile.riotIdHint')}</p>

      {editing ? (
        // Labelled buttons, not bare ✓/✗ icons: a member typed their Riot ID,
        // clicked elsewhere and never saved it — nothing told them it was lost.
        <div className="flex flex-wrap items-center gap-2">
          <div className="w-full max-w-xs">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t('profile.riotIdPlaceholder')}
              autoFocus
              maxLength={64}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); save(draft) }
                if (e.key === 'Escape') setEditing(false)
              }}
              className="h-9"
            />
          </div>
          <Button type="button" size="sm" onClick={() => save(draft)} disabled={saving}>
            <Check size={14} strokeWidth={2} />
            {saving ? t('common.saving') : t('common.save')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={saving}>
            <X size={14} strokeWidth={2} />
            {t('common.cancel')}
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          {user?.riot_id ? (
            <p className="font-semibold text-foreground">{user.riot_id}</p>
          ) : (
            <p className="text-sm text-muted-foreground">{t('profile.riotIdNotSet')}</p>
          )}
          <button
            type="button"
            onClick={startEdit}
            className="text-muted-foreground hover:text-accent transition-colors"
            title={t('profile.riotIdEdit')}
          >
            <Pencil size={12} strokeWidth={1.5} />
          </button>
          {user?.riot_id && (
            <button
              type="button"
              onClick={() => save(null)}
              disabled={saving}
              className="text-muted-foreground hover:text-red-400 transition-colors disabled:opacity-50"
              title={t('profile.riotIdRemove')}
            >
              <Trash2 size={12} strokeWidth={1.5} />
            </button>
          )}
        </div>
      )}

      {error && <p className="font-mono-label text-red-500 text-[10px]">{error}</p>}
    </div>
  )
}
