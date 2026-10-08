// The LPM token: a coin whose finish follows the level band — bronze (1–3),
// silver (4–6), gold (7+, with the app's accent as its rim). Inline SVG rather
// than a bitmap so it stays sharp at 14px in the roster and 56px on a profile.
type Finish = 'bronze' | 'silver' | 'gold'

const FINISHES: Record<Finish, { edge: string; face: string; rim: string; text: string }> = {
  bronze: { edge: '#6E4220', face: '#B87333', rim: '#6E4220', text: '#2A1608' },
  silver: { edge: '#6B717B', face: '#C9CED6', rim: '#6B717B', text: '#1F2328' },
  gold: { edge: '#9A6F0C', face: '#F2C14E', rim: '#FF3D00', text: '#3A2A00' },
}

export function coinFinish(level: number): Finish {
  if (level >= 7) return 'gold'
  if (level >= 4) return 'silver'
  return 'bronze'
}

export default function XpCoin({ level, size = 24, title }: { level: number; size?: number; title?: string }) {
  const f = FINISHES[coinFinish(level)]
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      aria-hidden={title ? undefined : true}
      className="flex-shrink-0"
    >
      {title && <title>{title}</title>}
      <circle cx="16" cy="16" r="15.5" fill={f.edge} />
      <circle cx="16" cy="16" r="13.5" fill={f.face} stroke={f.rim} strokeWidth="1.5" />
      <circle cx="16" cy="16" r="10.75" fill="none" stroke={f.edge} strokeWidth="0.6" strokeDasharray="1.1 1.1" />
      <path d="M8.5 11.5 A9 9 0 0 1 16 7" fill="none" stroke="#FFFFFF" strokeOpacity="0.45" strokeWidth="1.2" strokeLinecap="round" />
      <text
        x="16"
        y="19.1"
        textAnchor="middle"
        fontSize="8.4"
        fontWeight="900"
        letterSpacing="-0.3"
        fill={f.text}
        style={{ fontFamily: 'inherit' }}
      >
        LPM
      </text>
    </svg>
  )
}
