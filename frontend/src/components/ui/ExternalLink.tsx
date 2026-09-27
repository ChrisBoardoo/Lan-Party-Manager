import { AnchorHTMLAttributes } from 'react'
import { isEmbeddedInDesktop, requestOpenExternal } from '../../lib/desktopBridge'

interface ExternalLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'target' | 'rel'> {
  href: string
}

// `<a target="_blank">` has no working new-window target inside the desktop
// app's embedded iframe — Tauri doesn't spawn one, so the click is a silent
// no-op there (see open_external's doc comment in
// desktopapp/src-tauri/src/main.rs). Renders as a real anchor everywhere
// else, and as a button that routes through the shell's system-browser
// opener when embedded in the desktop app.
export default function ExternalLink({
  href,
  className,
  title,
  'aria-label': ariaLabel,
  children,
  ...rest
}: ExternalLinkProps) {
  if (isEmbeddedInDesktop()) {
    return (
      <button
        type="button"
        onClick={() => requestOpenExternal(href)}
        className={className}
        title={title}
        aria-label={ariaLabel}
      >
        {children}
      </button>
    )
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      title={title}
      aria-label={ariaLabel}
      {...rest}
    >
      {children}
    </a>
  )
}
