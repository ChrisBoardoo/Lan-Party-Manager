import { useEffect } from 'react'

/**
 * Ask crawlers not to index the current page.
 *
 * nginx sets `X-Robots-Tag` on the public share routes, which is the
 * authoritative mechanism — it works on crawlers that don't execute JS, and it
 * needs nothing rendered. This hook is the belt to that braces: it covers
 * `vite dev` and any deployment that isn't fronted by our nginx config.
 *
 * The cleanup is not optional. Without it, navigating from a shared page into
 * the app leaves the whole SPA marked noindex for the rest of the session.
 *
 * Note we deliberately do NOT add a robots.txt Disallow: that prevents
 * *crawling*, so the crawler never fetches the page and therefore never sees
 * this tag — and a disallowed URL can still be indexed URL-only if someone links
 * to it. The two mechanisms are in direct tension; letting the crawler in and
 * telling it "no" is the one that works.
 */
export function useNoindex() {
  useEffect(() => {
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex, nofollow, noarchive'
    document.head.appendChild(meta)
    return () => {
      document.head.removeChild(meta)
    }
  }, [])
}
