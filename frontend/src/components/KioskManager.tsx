import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Copy, Check, ExternalLink, RefreshCw, Trash2, QrCode } from 'lucide-react'
import { kioskApi } from '../lib/api'
import { isEmbeddedInDesktop, requestOpenExternal } from '../lib/desktopBridge'
import Button from './ui/Button'
import QRModal from './ui/QRModal'

// Admin control for the big-screen kiosk token. The enable/disable toggle lives
// in the Settings feature list (kiosk_enabled); this manages the token that
// authorizes the unattended /kiosk display and builds a shareable/QR link.
export default function KioskManager({ appBaseUrl }: { appBaseUrl?: string | null }) {
  const { t } = useTranslation()
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showQR, setShowQR] = useState(false)

  const base = (appBaseUrl && appBaseUrl.replace(/\/$/, '')) || window.location.origin
  const url = token ? `${base}/kiosk?token=${encodeURIComponent(token)}` : ''

  useEffect(() => {
    kioskApi
      .getAdmin()
      .then((d) => setToken(d.token))
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  const mint = async () => {
    setBusy(true)
    try {
      const d = await kioskApi.mintToken()
      setToken(d.token)
    } finally {
      setBusy(false)
    }
  }

  const revoke = async () => {
    setBusy(true)
    try {
      await kioskApi.revokeToken()
      setToken(null)
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (loading) {
    return (
      <div className="border border-border bg-card p-8 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }

  return (
    <div className="border border-border bg-card p-6">
      {!token ? (
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">{t('settings.kioskNoToken')}</p>
          <Button onClick={mint} disabled={busy} className="flex-shrink-0">
            {t('settings.kioskGenerate')}
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <p className="font-mono-label text-foreground mb-2">{t('settings.kioskLinkLabel')}</p>
            <div className="flex items-center gap-2 flex-wrap">
              <code className="font-mono-label text-[11px] text-muted-foreground bg-muted px-3 py-2 break-all flex-1 min-w-0">
                {url}
              </code>
              <button
                onClick={copy}
                className="font-mono-label text-[10px] text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
              >
                {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
                {copied ? t('common.copied') : t('common.copy')}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {isEmbeddedInDesktop() ? (
              <Button className="flex items-center gap-2" onClick={() => requestOpenExternal(url)}>
                <ExternalLink size={14} />
                {t('settings.kioskOpen')}
              </Button>
            ) : (
              <a href={url} target="_blank" rel="noopener noreferrer">
                <Button className="flex items-center gap-2">
                  <ExternalLink size={14} />
                  {t('settings.kioskOpen')}
                </Button>
              </a>
            )}
            <button
              onClick={() => setShowQR(true)}
              className="font-mono-label text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
            >
              <QrCode size={14} />
              {t('common.qrCode')}
            </button>
            <button
              onClick={mint}
              disabled={busy}
              className="font-mono-label text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
            >
              <RefreshCw size={14} />
              {t('settings.kioskRotate')}
            </button>
            <button
              onClick={revoke}
              disabled={busy}
              className="font-mono-label text-xs text-red-400 hover:text-red-300 transition-colors flex items-center gap-1.5"
            >
              <Trash2 size={14} />
              {t('settings.kioskRevoke')}
            </button>
          </div>

          <p className="font-mono-label text-[10px] text-muted-foreground">{t('settings.kioskTokenHint')}</p>
        </div>
      )}

      {showQR && <QRModal value={url} label={t('settings.kioskLinkLabel')} onClose={() => setShowQR(false)} />}
    </div>
  )
}
