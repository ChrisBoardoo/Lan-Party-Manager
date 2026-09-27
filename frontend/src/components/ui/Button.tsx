import { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'outline' | 'ghost' | 'danger'
  size?: 'sm' | 'default' | 'lg'
  children: ReactNode
}

export default function Button({
  variant = 'primary',
  size = 'default',
  className = '',
  children,
  disabled,
  ...props
}: ButtonProps) {
  const base =
    'relative inline-flex items-center justify-center gap-2 font-sans font-semibold uppercase tracking-wider whitespace-nowrap transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-40 active:translate-y-px'

  const sizes = {
    sm: 'text-xs py-2 px-4',
    default: 'text-sm py-3 px-6',
    lg: 'text-base py-4 px-8',
  }

  const variants = {
    primary:
      'bg-accent text-accent-foreground hover:bg-accent/90',
    outline:
      'border border-foreground text-foreground bg-transparent hover:bg-foreground hover:text-background',
    ghost:
      'text-muted-foreground bg-transparent hover:text-foreground border border-transparent hover:border-border',
    danger:
      'border border-red-600 text-red-500 bg-transparent hover:bg-red-600 hover:text-white',
  }

  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  )
}
