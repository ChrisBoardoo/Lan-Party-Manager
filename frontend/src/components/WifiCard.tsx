import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Wifi, Eye, EyeOff, Copy, Check, QrCode } from 'lucide-react'
import { settingsApi } from '../lib/api'
import { wifiQrPayload } from '../lib/wifiQr'
import type { WifiConfig } from '../types'
import QRModal from './ui/QRModal'

// Guest WiFi for the people who'll be in the room. The backend decides who may
// read it (admins + "in" RSVPs to the current event, 404 for everyone else) and
// which event it belongs to — the card only renders on that event's page.
export default function WifiCard({ eventId }: { eventId: number }) {
  const { t } = useTranslation()
  const [wifi, setWifi] = useState<WifiConfig | null>(null)
  const [reveal, setReveal] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showQR, setShowQR] = useState(false)

  useEffect(() => {
    settingsApi
      .getWifi()
      .then((w) => setWifi(w && w.event_id === eventId ? w : null))
      .catch(() => setWifi(null))
  }, [eventId])

  if (!wifi) return null

  const copy = async () => {
    if (!wifi.password) return
    await navigator.clipboard.writeText(wifi.password)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border border-border bg-card p-6 mb-6">
      <div className="flex items-center justify-between gap-4 mb-4">
        <p className="font-mono-label text-accent flex items-center gap-1.5">
          <Wifi size={12} strokeWidth={1.5} /> {t('eventDetail.wifiTitle')}
        </p>
        <button
          onClick={() => setShowQR(true)}
          className="flex items-center gap-1.5 font-mono-label text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          <QrCode size={12} /> {t('eventDetail.wifiShowQr')}
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="min-w-0">
          <p className="font-mono-label text-muted-foreground text-[10px] mb-1">{t('eventDetail.wifiNetwork')}</p>
          <p className="font-mono text-sm text-foreground break-all">{wifi.ssid}</p>
        </div>
        <div className="min-w-0">
          <p className="font-mono-label text-muted-foreground text-[10px] mb-1">{t('eventDetail.wifiPassword')}</p>
          {wifi.password ? (
            <div className="flex items-center gap-2">
              <code className="font-mono text-sm text-foreground break-all">
                {reveal ? wifi.password : '••••••••••••'}
              </code>
              <button
                onClick={() => setReveal((r) => !r)}
                className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
                aria-label={t('eventDetail.wifiPassword')}
              >
                {reveal ? <EyeOff size={12} /> : <Eye size={12} />}
              </button>
              <button
                onClick={copy}
                className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
                aria-label={t('common.copy')}
              >
                {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
              </button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('eventDetail.wifiOpen')}</p>
          )}
        </div>
      </div>
      <p className="text-xs text-muted-foreground mt-4">{t('eventDetail.wifiHint')}</p>
      {showQR && <QRModal value={wifiQrPayload(wifi)} label={wifi.ssid} onClose={() => setShowQR(false)} hideValue />}
    </div>
  )
}
