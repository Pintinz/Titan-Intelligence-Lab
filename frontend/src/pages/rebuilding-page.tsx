import { Link } from 'react-router-dom'
import { Hammer } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Placeholder for every route not yet rebuilt under the Milestone 10.2 reconstruction — swapped
 * out for the real page as each phase lands (see the phased plan). Never silently 404s a route
 * that used to work.
 */
export function RebuildingPage({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-accent-primary-muted">
        <Hammer className="size-5 text-accent-primary" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <h1 className="font-display text-lg font-semibold text-text-primary">{title}</h1>
        <p className="max-w-sm text-sm text-text-secondary">
          Being rebuilt under TitanIQ's new visual identity — landing in {phase}.
        </p>
      </div>
      <Button asChild variant="secondary" size="sm">
        <Link to="/app">Back to Home</Link>
      </Button>
    </div>
  )
}
