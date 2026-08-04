import { Wrench } from 'lucide-react'
import { Seo } from '@/components/seo/seo'

export default function MaintenancePage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-5 bg-bg-primary px-6 text-center">
      <Seo title="Scheduled maintenance" description="TitanIQ is undergoing scheduled maintenance." noindex />
      <div className="flex size-14 items-center justify-center rounded-full bg-accent-primary-muted">
        <Wrench className="size-6 text-accent-primary" aria-hidden="true" />
      </div>
      <div className="space-y-2">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">Maintenance</p>
        <h1 className="font-display text-2xl font-semibold text-text-primary">TitanIQ is recalibrating.</h1>
        <p className="max-w-sm text-sm text-text-secondary">
          We're performing scheduled maintenance to keep the intelligence pipeline running smoothly. We'll be back
          shortly — thanks for your patience.
        </p>
      </div>
      <a href="/status" className="text-xs text-text-muted hover:text-text-secondary">
        Follow progress on System Status →
      </a>
    </div>
  )
}
