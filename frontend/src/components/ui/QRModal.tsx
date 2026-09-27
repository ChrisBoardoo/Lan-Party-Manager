import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import QRCode from 'react-qr-code'
import { X } from 'lucide-react'

export default function QRModal({
  value,
  label,
  onClose,
  hideValue,
}: {
  value: string
  label: string
  onClose: () => void
  /** Don't print the raw payload under the code (e.g. a WIFI: string with its password). */
  hideValue?: boolean
}) {
  const { t } = useTranslation()
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border p-8 flex flex-col items-center gap-6 max-w-xs w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between w-full">
          <p className="font-mono-label text-accent">{t('common.qrCode')}</p>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={14} />
          </button>
        </div>
        <div className="bg-white p-4">
          <QRCode value={value} size={180} />
        </div>
        <div className="text-center">
          <p className="font-mono-label text-foreground text-sm mb-1">{label}</p>
          {!hideValue && <p className="font-mono-label text-muted-foreground text-[10px] break-all">{value}</p>}
        </div>
        <button onClick={onClose} className="font-mono-label text-muted-foreground hover:text-foreground text-xs">
          {t('common.close')}
        </button>
      </div>
    </div>
  )
}
