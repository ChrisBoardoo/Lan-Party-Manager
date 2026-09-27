import { Gift } from 'lucide-react'
import { Prize } from '../types'

/** Read-only responsive grid of prize cards (photo + title + description). */
export default function PrizeGrid({ prizes }: { prizes: Prize[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {prizes.map((p) => (
        <div key={p.id} className="border border-border bg-card overflow-hidden flex flex-col">
          <div className="aspect-video bg-muted border-b border-border flex items-center justify-center overflow-hidden">
            {p.photo_url ? (
              <img src={p.photo_url} alt={p.title} className="w-full h-full object-cover" />
            ) : (
              <Gift size={28} strokeWidth={1} className="text-muted-foreground" />
            )}
          </div>
          <div className="p-4 flex-1">
            <p className="text-sm font-black tracking-tight text-foreground">{p.title}</p>
            {p.description && (
              <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed whitespace-pre-wrap">{p.description}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
