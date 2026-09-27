import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, MessageCircle } from 'lucide-react'
import { useUpcomingEvent } from '../contexts/UpcomingEventContext'
import CravingChatSection from '../components/CravingChatSection'
import EventCountdown from '../components/ui/EventCountdown'
import { formatDate } from '../lib/formatDate'

// A real standalone page (not just an anchor scroll on the Hub) so the
// Navbar's temporary chat icon has an actual destination reachable from any
// page in the app, with its own back button — crew feedback found the
// scroll-to-anchor version unsatisfying. The Hub keeps its own inline copy
// of the chat right under the roster for zero-click access while already
// there; this page is for the "I'm three pages deep and want to check the
// chat" case the Navbar icon exists for.
export default function CravingChatPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { chatEvent } = useUpcomingEvent()

  return (
    // No max-w cap here on purpose — the chat is meant to fill most of the
    // screen on web/desktop now, bounded only by a 10% side margin (crew
    // feedback: "carrément grossir le chat"). Mobile keeps a plain px-6
    // instead of 10% (which would pinch a narrow screen) — sm: and up is
    // "web & desktop", matching how the rest of the ask was scoped.
    <main className="px-6 sm:px-[10%] pt-12 pb-12 sm:pb-[10vh]">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 font-mono-label text-muted-foreground hover:text-foreground transition-colors mb-8"
      >
        <ArrowLeft size={12} /> {t('common.back')}
      </button>

      <div className="flex items-center gap-2 mb-1">
        <MessageCircle size={18} strokeWidth={1.5} className="text-accent" />
        <h1 className="text-2xl font-black tracking-tight text-foreground">{t('cravingChat.blockTitle')}</h1>
      </div>

      {chatEvent ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-6">
            <p className="text-sm text-muted-foreground">
              {chatEvent.title} · {formatDate(chatEvent.start_date)}
              {chatEvent.start_date !== chatEvent.end_date && <> → {formatDate(chatEvent.end_date)}</>}
            </p>
            <EventCountdown startDate={chatEvent.start_date} format="full" />
          </div>
          <CravingChatSection eventId={chatEvent.id} attendees={chatEvent.attendees} heightClassName="h-[460px] sm:h-[70vh]" />
        </>
      ) : (
        <div className="border border-border bg-card p-6 text-center mt-6">
          <p className="font-mono-label text-muted-foreground text-xs">{t('cravingChat.closed')}</p>
        </div>
      )}
    </main>
  )
}
