import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Class component is the only React-supported way to catch render-time errors — no hook
 * equivalent exists. Scoped around the routed page content in app-shell.tsx so a crash in one
 * page doesn't take down the sidebar/topbar/navigation with it. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-[60vh] items-center justify-center p-6">
          <Card className="max-w-md">
            <CardHeader className="flex-row items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-danger" aria-hidden="true" />
              <CardTitle>Something went wrong</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <p className="text-sm text-text-secondary">
                This page hit an unexpected error. Your session is still active — reloading usually resolves it.
              </p>
              <Button size="sm" onClick={() => window.location.reload()}>
                Reload page
              </Button>
            </CardContent>
          </Card>
        </div>
      )
    }
    return this.props.children
  }
}
