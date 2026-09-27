import { Link } from 'react-router-dom'
import type { UserTrophy } from '../../types'
import TrophyIcon from './TrophyIcon'

// A member's showcase on their profile: every trophy they've been awarded,
// newest LAN first. Permanent by design — this is the "souvenir" of each edition.
export default function TrophyCase({ trophies }: { trophies: UserTrophy[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {trophies.map((tr) => (
        <div key={tr.edition_id} className="border border-border bg-card p-4 flex items-start gap-3">
          <TrophyIcon trophy={tr.trophy} className="w-12 h-12 text-4xl" />
          <div className="min-w-0">
            <p className="font-black text-foreground leading-tight">{tr.trophy.name}</p>
            <Link to={`/events/${tr.event_id}`} className="font-mono-label text-accent text-[10px] hover:underline">
              {/* The year, unless the event's title already says it ("LAN Octobre 2026"). */}
              {tr.event_title.includes(tr.event_start_date.slice(0, 4))
                ? tr.event_title
                : `${tr.event_title} · ${tr.event_start_date.slice(0, 4)}`}
            </Link>
            {tr.citation && <p className="text-xs text-muted-foreground italic mt-1">« {tr.citation} »</p>}
          </div>
        </div>
      ))}
    </div>
  )
}
