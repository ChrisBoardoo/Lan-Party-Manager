import { Component, ErrorInfo, ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

// Class component is required here — React has no hook equivalent of
// componentDidCatch/getDerivedStateFromError yet. Without this, any unhandled
// render error anywhere in the tree unmounts the whole app to a blank white
// screen with nothing but a console stack trace.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-background flex items-center justify-center px-6">
          <div className="max-w-md w-full border border-border bg-card p-8 text-center">
            <AlertTriangle className="mx-auto mb-4 text-accent" size={32} />
            <p className="font-mono-label text-foreground mb-2">Something went wrong</p>
            <p className="text-sm text-muted-foreground mb-6">
              {this.state.error.message || 'An unexpected error occurred.'}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="font-mono-label px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
