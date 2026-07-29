import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function CtaSection() {
  return (
    <div className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 opacity-50"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-3xl px-6 py-24 text-center lg:px-10">
        <h2 className="font-display text-3xl font-semibold tracking-tight text-text-primary lg:text-4xl">
          See every match through intelligence.
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-base text-text-secondary">
          Start free. Explainable predictions, real confidence, and a platform that gets smarter
          after every match.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link to="/signup">Start free</Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link to="/methodology">See the methodology</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
