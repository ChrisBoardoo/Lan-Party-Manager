import { useEffect, useState } from 'react'

/** Whether a CSS media query matches, kept up to date as the window resizes.
 *  False where matchMedia doesn't exist (tests, very old browsers). */
export function useMediaQuery(query: string): boolean {
  const read = () => (typeof window !== 'undefined' && window.matchMedia?.(query).matches) || false
  const [matches, setMatches] = useState(read)

  useEffect(() => {
    const list = window.matchMedia?.(query)
    if (!list) return
    const onChange = () => setMatches(list.matches)
    onChange()
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])

  return matches
}
