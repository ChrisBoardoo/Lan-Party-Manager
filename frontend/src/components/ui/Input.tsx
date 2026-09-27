import { InputHTMLAttributes, forwardRef, ReactNode } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  suffix?: ReactNode
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, suffix, className = '', ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label className="font-mono-label text-muted-foreground">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          <input
            ref={ref}
            className={`w-full h-12 px-4 bg-input border border-border text-foreground text-base placeholder:text-muted-foreground focus:border-accent outline-none transition-colors duration-150 ${suffix ? 'pr-12' : ''} ${className}`}
            {...props}
          />
          {suffix && (
            <div className="absolute right-4 text-muted-foreground">{suffix}</div>
          )}
        </div>
        {error && (
          <span className="font-mono-label text-red-500">{error}</span>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'
export default Input
