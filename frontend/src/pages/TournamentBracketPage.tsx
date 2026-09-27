import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { tournamentsApi } from '../lib/api'
import { Tournament } from '../types'
import TournamentBracket from '../components/TournamentBracket'
import SponsorStrip from '../components/SponsorStrip'
import { ArrowLeft, RefreshCw, Trophy } from 'lucide-react'

export default function TournamentBracketPage() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation()
  const [tournament, setTournament] = useState<Tournament | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    if (!id) return
    try {
      const data = await tournamentsApi.get(Number(id))
      setTournament(data)
    } catch {
      setTournament(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  return (
    <main className="max-w-[1600px] mx-auto px-6 py-12">
      <div className="flex items-center justify-between mb-8">
        <Link
          to="/tournaments"
          className="flex items-center gap-2 font-mono-label text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft size={12} /> {t('tournaments.backToArena')}
        </Link>
        {tournament && (
          <button
            onClick={load}
            className="font-mono-label text-muted-foreground hover:text-foreground flex items-center gap-1 text-[10px]"
          >
            <RefreshCw size={10} /> {t('tournaments.refresh')}
          </button>
        )}
      </div>

      {loading ? (
        <div className="h-64 bg-muted animate-pulse" />
      ) : !tournament ? (
        <div className="border border-border p-16 text-center">
          <Trophy size={24} strokeWidth={1} className="text-muted-foreground mx-auto mb-3" />
          <p className="font-mono-label text-muted-foreground">{t('tournaments.notFound')}</p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 mb-8 flex-wrap">
            <Trophy size={20} strokeWidth={1.5} className="text-accent" />
            <h1 className="text-3xl font-black tracking-tight text-foreground">{tournament.game_name}</h1>
          </div>
          <TournamentBracket tournament={tournament} onUpdate={load} />
          <div className="mt-8">
            <SponsorStrip eventId={tournament.event_id ?? undefined} />
          </div>
        </>
      )}
    </main>
  )
}
