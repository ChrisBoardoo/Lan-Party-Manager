import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usersApi } from '../lib/api'
import { DeletedUser } from '../types'
import { formatDate } from '../lib/formatDate'
import { UserX } from 'lucide-react'

// Admin-only history of deleted accounts — the one place they're still
// visible at all, since a deleted row never appears in the HUB roster
// (backend/router_users.py::get_all_users filters it out unconditionally).
// Named generically ("removed" rather than just "deleted") because a future
// "banned" state (see md/2.features/ban-feature-idea.md) would belong in this same
// list — not built yet, so this only ever shows deletions for now.
export default function DeletedUsersHistory() {
  const { t } = useTranslation()
  const [users, setUsers] = useState<DeletedUser[] | null>(null)

  useEffect(() => {
    usersApi
      .getDeleted()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [])

  if (users === null) {
    return (
      <div className="border border-border bg-card p-8 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }

  if (users.length === 0) {
    return (
      <div className="border border-border bg-card p-6 text-center">
        <p className="text-sm text-muted-foreground">{t('settings.removedUsersEmpty')}</p>
      </div>
    )
  }

  return (
    <div className="border border-border bg-card divide-y divide-border">
      {users.map((u) => (
        <div key={u.id} className="p-4 flex items-center gap-3">
          <UserX size={16} strokeWidth={1.5} className="text-muted-foreground flex-shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-mono text-sm text-foreground truncate">
              {u.deleted_username ?? `#${u.id}`}
            </p>
            <p className="font-mono-label text-muted-foreground text-[10px]">
              {t('settings.removedUsersDeletedOn', { date: formatDate(u.deleted_at) })}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}
