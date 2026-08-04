import { Link } from 'react-router-dom'
import { ServerCrash } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Button } from '@/components/ui/button'

export default function ServerErrorPage({ message }: { message?: string }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-5 bg-bg-primary px-6 text-center">
      <Seo title="Something went wrong" description="TitanIQ hit an unexpected error." noindex />
      <div className="flex size-14 items-center justify-center rounded-full bg-danger-muted">
        <ServerCrash className="size-6 text-danger" aria-hidden="true" />
      </div>
      <div className="space-y-2">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-danger">Error 500</p>
        <h1 className="font-display text-2xl font-semibold text-text-primary">Something went wrong on our end.</h1>
        <p className="max-w-sm text-sm text-text-secondary">
          {message ?? "We've logged the issue and our team has been notified. Try again in a moment."}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-3">
        <Button onClick={() => window.location.reload()}>Try again</Button>
        <Button asChild variant="secondary">
          <Link to="/">Back to home</Link>
        </Button>
      </div>
      <Link to="/status" className="text-xs text-text-muted hover:text-text-secondary">
        Check System Status →
      </Link>
    </div>
  )
}
