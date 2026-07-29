import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Lightbulb } from 'lucide-react'
import { Button } from '@/components/ui/button'

const MODULE_INFO: Record<string, { title: string; description: string }> = {
  users: { title: 'Users & Roles', description: 'User account management, role assignment, and access control.' },
  organizations: { title: 'Organizations', description: 'Multi-tenant organization and team management.' },
  billing: { title: 'Billing & Revenue', description: 'Subscription tiers, revenue reporting, and payment reconciliation.' },
  security: { title: 'Security & Compliance', description: 'Authentication, authorization, audit logs, and compliance tools.' },
  audit: { title: 'Audit Center', description: 'Comprehensive audit trail of all administrative actions.' },
  logs: { title: 'Logs & Debugging', description: 'Application logs, error tracking, and performance diagnostics.' },
  alerts: { title: 'Alerts & Monitoring', description: 'System health alerts, incident management, and on-call routing.' },
}

export default function PlannedModule() {
  const { module } = useParams<{ module: string }>()
  const info = module ? MODULE_INFO[module] : null

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link to="/app/ops" className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary">
        <ArrowLeft className="size-3.5" /> Back to Operations
      </Link>

      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Coming soon
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">{info?.title || 'Planned Module'}</h1>
        <p className="mt-2 text-base text-text-secondary">{info?.description || 'This module is under development.'}</p>
      </div>

      <div className="flex items-start gap-3 rounded-lg border border-border-default bg-bg-elevated p-4">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
        <div className="text-sm">
          <p className="font-medium text-text-primary">Why is this marked "Planned"?</p>
          <p className="mt-1 text-text-secondary">
            The backend work for this module hasn't shipped yet, or it requires a separate admin dashboard that's not in the current roadmap. Rather than show a fake-ready stub, we're honest about what's coming. Check back soon!
          </p>
        </div>
      </div>

      <Button asChild variant="secondary">
        <Link to="/app/ops">Return to Dashboard</Link>
      </Button>
    </div>
  )
}
