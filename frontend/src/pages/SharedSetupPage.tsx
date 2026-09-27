import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { setupApi } from '../lib/api'
import type { SharedSetup } from '../types'
import { useNoindex } from '../hooks/useNoindex'
import SetupView from '../components/SetupView'
import Logo from '../components/ui/Logo'

/**
 * The public, token-authorized setup at /setup/shared?token=… — no login, no
 * Navbar/Layout, exactly like the kiosk and the shared recap.
 *
 * Its payload carries a username, an avatar, the parts list and the photos, and
 * nothing else: no email, no phone, no role, no presence. See SetupSharedOut.
 */
export default function SharedSetupPage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const token = params.get('token')
  const [setup, setSetup] = useState<SharedSetup | null>(null)
  const [loading, setLoading] = useState(true)

  // Someone's rig and their room shouldn't turn up in image search.
  useNoindex()

  useEffect(() => {
    const load = async () => {
      if (!token) {
        setLoading(false)
        return
      }
      // try/catch/finally: a revoked or bad token must reach the not-found state
      // below, not spin on the skeleton forever.
      try {
        setSetup(await setupApi.getShared(token))
      } catch {
        setSetup(null)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [token])

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header: the brand lockup, linking out to the project site. This is a
          public page with no Navbar, so the logo is how a visitor knows what
          they're looking at — and the way back to lanpartymanager.com. */}
      <header className="border-b border-border">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center">
          <Logo size="md" linkTo="website" />
        </div>
      </header>

      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-12">
        {loading ? (
          <>
            <div className="h-10 w-1/2 bg-muted animate-pulse mb-8" />
            <div className="h-64 bg-muted animate-pulse" />
          </>
        ) : !setup ? (
          <p className="font-mono-label text-muted-foreground">{t('setup.shareNotFound')}</p>
        ) : (
          <>
            <div className="flex items-center gap-4 mb-12">
              {setup.avatar_url ? (
                <img
                  src={setup.avatar_url}
                  alt=""
                  className="w-16 h-16 object-cover border border-border shrink-0"
                />
              ) : (
                <div className="w-16 h-16 bg-muted flex items-center justify-center font-black text-2xl text-muted-foreground shrink-0">
                  {setup.username.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="min-w-0">
                <div className="font-mono-label text-accent mb-1">{t('setup.publicTagline')}</div>
                <h1 className="text-4xl lg:text-5xl font-black tracking-tighter text-foreground leading-none truncate">
                  {t('setup.publicHeading', { username: setup.username })}
                </h1>
              </div>
            </div>

            <SetupView
              components={setup.components}
              customFields={setup.custom_fields}
              photos={setup.photos}
            />
          </>
        )}
      </main>

      {/* "Powered by" sign-off. The brand also sits in the header (the primary
          placement); this is the quieter footer echo, smaller so it doesn't
          compete. The lockup is itself the link out. */}
      <footer className="border-t border-border">
        <div className="max-w-4xl mx-auto px-6 py-6 flex items-center justify-center gap-3">
          <span className="font-mono-label text-muted-foreground text-[10px]">
            {t('setup.poweredBy')}
          </span>
          <Logo size="sm" linkTo="website" />
        </div>
      </footer>
    </div>
  )
}
