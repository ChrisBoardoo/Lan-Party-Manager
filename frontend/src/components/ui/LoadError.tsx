import { useTranslation } from 'react-i18next'
import { AlertCircle, RotateCw } from 'lucide-react'
import Button from './Button'

/**
 * What a page shows instead of its content when its load failed (useLoad):
 * the sentence, and a way to try again without F5. Same notice style as the
 * forms' error box.
 */
export default function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="border border-red-800 bg-red-950/20 px-5 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
      <div className="flex items-start gap-3 flex-1 min-w-0">
        <AlertCircle size={18} className="text-red-400 flex-shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="font-mono-label text-red-400">{t('errors.loadFailed')}</p>
          <p className="text-sm text-muted-foreground mt-1 break-words">{message}</p>
        </div>
      </div>
      <Button type="button" variant="outline" onClick={onRetry} className="flex-shrink-0">
        <RotateCw size={14} className="mr-2" />
        {t('common.retry')}
      </Button>
    </div>
  )
}
