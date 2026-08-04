import { Link } from 'react-router-dom'
import { SearchX } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-5 bg-bg-primary px-6 text-center">
      <Seo title="Page not found" description="The page you're looking for doesn't exist." noindex />
      <div className="flex size-14 items-center justify-center rounded-full bg-accent-primary-muted">
        <SearchX className="size-6 text-accent-primary" aria-hidden="true" />
      </div>
      <div className="space-y-2">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">Error 404</p>
        <h1 className="font-display text-2xl font-semibold text-text-primary">This match isn't on the board.</h1>
        <p className="max-w-sm text-sm text-text-secondary">
          The page you're looking for doesn't exist, moved, or the link is out of date.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-3">
        <Button asChild>
          <Link to="/">Back to home</Link>
        </Button>
        <Button asChild variant="secondary">
          <Link to="/help">Visit Help Center</Link>
        </Button>
      </div>
    </div>
  )
}
