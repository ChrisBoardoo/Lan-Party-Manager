import type { TrophyBrief } from '../../types'

/** A trophy's face: its uploaded image, else its emoji, else 🏆. `className`
 *  sizes the box (e.g. "w-10 h-10 text-3xl"). */
export default function TrophyIcon({
  trophy,
  className = 'w-10 h-10 text-3xl',
}: {
  trophy: Pick<TrophyBrief, 'emoji' | 'image_url' | 'name'>
  className?: string
}) {
  if (trophy.image_url) {
    return <img src={trophy.image_url} alt={trophy.name} className={`${className} object-contain shrink-0`} />
  }
  return (
    <span className={`${className} flex items-center justify-center leading-none shrink-0`} aria-hidden="true">
      {trophy.emoji || '🏆'}
    </span>
  )
}
