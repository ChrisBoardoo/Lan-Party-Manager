import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Heart } from 'lucide-react'
import ExternalLink from './ExternalLink'

const SPECIAL_THANKS = [
  'HugeP', 'Powet', 'Violent Magicien', 'Chakiboule', 'Byndou',
  'Dastingo', 'SquallMax', 'Alfred', 'Michistratavu',
]

export default function AboutModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border w-full max-w-md max-h-[calc(100dvh-2rem)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-6 border-b border-border flex-shrink-0">
          <p className="font-mono-label text-accent">{t('footer.aboutTitle')}</p>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto">
          <p className="font-mono-label text-muted-foreground text-[11px]">
            <ExternalLink
              href="https://www.lanpartymanager.com"
              className="text-foreground hover:text-accent transition-colors duration-150"
            >
              LAN Party Manager
            </ExternalLink>{' '}
            {t('footer.freeToUse')}
          </p>

          <p className="font-mono-label text-muted-foreground text-[11px] flex items-center flex-wrap gap-1.5">
            <span>{t('footer.madeByPrefix')}</span>
            <ExternalLink
              href="https://www.crosswax.net"
              className="text-foreground hover:text-accent transition-colors duration-150"
            >
              CrossWax
            </ExternalLink>
            <span>{t('footer.madeBySuffix')}</span>
            <Heart size={11} className="text-accent fill-accent flex-shrink-0" aria-hidden="true" />
          </p>

          <div>
            <p className="font-mono-label text-muted-foreground/60 text-[10px] mb-2">
              {t('footer.specialThanks')}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SPECIAL_THANKS.map((name) => (
                <span
                  key={name}
                  className="font-mono-label text-foreground text-[10px] border border-border px-2 py-1"
                >
                  {name}
                </span>
              ))}
            </div>
          </div>

          <p className="font-mono-label text-muted-foreground/50 text-[10px] pt-2 border-t border-border">
            1.3.5
          </p>
        </div>
      </div>
    </div>
  )
}
