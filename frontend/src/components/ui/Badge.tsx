import { ReactNode } from 'react'

interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'accent' | 'success' | 'warning' | 'danger' | 'muted'
  className?: string
}

export default function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  const variants = {
    default: 'border border-border text-muted-foreground',
    accent: 'bg-accent text-accent-foreground',
    success: 'border border-green-700 text-green-400',
    warning: 'border border-yellow-700 text-yellow-400',
    danger: 'border border-red-700 text-red-400',
    muted: 'bg-muted text-muted-foreground',
  }

  return (
    <span
      className={`inline-block font-mono-label px-2 py-0.5 ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  )
}
