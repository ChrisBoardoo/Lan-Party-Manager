import { createContext, useCallback, useContext, useRef, useState, ReactNode } from 'react'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'

type ToastVariant = 'success' | 'error' | 'info'

interface Toast {
  id: number
  message: string
  variant: ToastVariant
}

interface ToastContextValue {
  push: (message: string, variant?: ToastVariant) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const VARIANT_STYLES: Record<ToastVariant, { border: string; icon: ReactNode }> = {
  success: { border: 'border-green-700', icon: <CheckCircle2 size={16} className="text-green-400 flex-shrink-0" /> },
  error: { border: 'border-red-700', icon: <XCircle size={16} className="text-red-400 flex-shrink-0" /> },
  info: { border: 'border-border', icon: <Info size={16} className="text-accent flex-shrink-0" /> },
}

const AUTO_DISMISS_MS = 5000

// Hand-rolled rather than a dependency (sonner, react-hot-toast, …) — this app
// otherwise ships zero UI-library dependencies beyond lucide-react's icons, and
// the need here is small: a stacked, auto-dismissing notice matching the
// existing dark/mono-label/one-accent design system.
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback((message: string, variant: ToastVariant = 'success') => {
    const id = nextId.current++
    setToasts((prev) => [...prev, { id, message, variant }])
    setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
  }, [dismiss])

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))]"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={`flex items-start gap-2 bg-card border ${VARIANT_STYLES[toast.variant].border} px-3 py-2.5 shadow-lg animate-toast-in`}
          >
            {VARIANT_STYLES[toast.variant].icon}
            <span className="font-mono-label text-xs text-foreground flex-1 leading-relaxed">{toast.message}</span>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              className="text-muted-foreground hover:text-foreground flex-shrink-0"
              aria-label="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
