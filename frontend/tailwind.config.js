/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      screens: {
        // Custom breakpoint for the Navbar's nav-item text labels: the
        // default 2xl (1536px) isn't enough headroom once every optional
        // feature is on for an admin in French — measured via Playwright,
        // labels only fit cleanly from ~1680px up (see Navbar.tsx).
        '3xl': '1680px',
      },
      colors: {
        background: '#0A0A0A',
        foreground: '#FAFAFA',
        muted: '#1A1A1A',
        'muted-foreground': '#737373',
        accent: '#FF3D00',
        'accent-foreground': '#0A0A0A',
        border: '#262626',
        input: '#1A1A1A',
        card: '#0F0F0F',
        'card-foreground': '#FAFAFA',
        'border-hover': '#404040',
      },
      fontFamily: {
        sans: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['"Playfair Display"', 'Georgia', 'serif'],
      },
      letterSpacing: {
        tighter: '-0.06em',
        tight: '-0.04em',
        normal: '-0.01em',
        wide: '0.05em',
        wider: '0.1em',
        widest: '0.2em',
      },
      lineHeight: {
        none: '1',
        tight: '1.1',
        snug: '1.25',
        normal: '1.6',
        relaxed: '1.75',
      },
      borderRadius: {
        none: '0px',
        DEFAULT: '0px',
        sm: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
        full: '9999px',
      },
      fontSize: {
        '8xl': ['8rem', { lineHeight: '1' }],
        '9xl': ['10rem', { lineHeight: '1' }],
      },
      keyframes: {
        // Online-presence indicator: a gentle green glow that breathes,
        // instead of a hard flash. rgb(34,197,94) == Tailwind green-500.
        'online-pulse': {
          '0%, 100%': { boxShadow: '0 0 4px 1px rgba(34,197,94,0.55)', opacity: '0.9' },
          '50%': { boxShadow: '0 0 8px 3px rgba(34,197,94,0.95)', opacity: '1' },
        },
        // Toast entrance (ToastContext.tsx) — no animation plugin in this
        // project, so this is a small hand-rolled equivalent of
        // tailwindcss-animate's fade-in + slide-in-from-bottom.
        'toast-in': {
          '0%': { opacity: '0', transform: 'translateY(0.5rem)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'online-pulse': 'online-pulse 2.4s ease-in-out infinite',
        'toast-in': 'toast-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
}
