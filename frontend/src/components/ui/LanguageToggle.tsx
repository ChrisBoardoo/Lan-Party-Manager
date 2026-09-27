import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'

export default function LanguageToggle({ className = 'flex' }: { className?: string }) {
  const { i18n } = useTranslation()
  const current = i18n.language?.startsWith('fr') ? 'fr' : 'en'

  const setLang = (lng: 'en' | 'fr') => {
    i18n.changeLanguage(lng)
  }

  return (
    <div className={`items-center gap-1 flex-shrink-0 ${className}`}>
      <Globe size={12} strokeWidth={1.5} className="text-muted-foreground flex-shrink-0" />
      {(['en', 'fr'] as const).map((lng) => (
        <button
          key={lng}
          type="button"
          onClick={() => setLang(lng)}
          className={`font-mono-label text-[10px] px-1.5 py-0.5 border transition-colors duration-150 ${
            current === lng
              ? 'border-accent text-accent'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          {lng === 'en' ? 'EN' : 'FR'}
        </button>
      ))}
    </div>
  )
}
