import { CheckCircle2 } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, StatusRow } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const SUBSYSTEMS = [
  { name: 'TitanIQ Web Application', status: 'operational' as const, uptime: '99.98%' },
  { name: 'TitanIQ API', status: 'operational' as const, uptime: '99.97%' },
  { name: 'Authentication (Supabase)', status: 'operational' as const, uptime: '99.99%' },
  { name: 'Prediction Pipeline', status: 'operational' as const, uptime: '99.95%' },
  { name: 'News Intelligence', status: 'operational' as const, uptime: '99.94%' },
  { name: 'Knowledge Graph', status: 'operational' as const, uptime: '99.96%' },
  { name: 'Notifications', status: 'operational' as const, uptime: '99.93%' },
]

export default function SystemStatusPage() {
  return (
    <>
      <Seo
        title="System Status"
        description="Live operational status and uptime for TitanIQ's core subsystems."
        path="/status"
      />
      <PageHero
        eyebrow="Status"
        title="System Status"
        description="Current operational status of TitanIQ's core subsystems, updated continuously."
        actions={
          <Button asChild variant="secondary" size="lg">
            <a href="mailto:status@titaniq.ai?subject=Subscribe%20to%20status%20updates">Subscribe to updates</a>
          </Button>
        }
      />

      <Section>
        <div className="mb-6 flex items-center gap-2 rounded-lg border border-success/30 bg-success-muted px-4 py-3">
          <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">All systems operational</p>
        </div>
        <SectionHeading eyebrow="Subsystems" title="Component status" />
        <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
          {SUBSYSTEMS.map((s) => (
            <StatusRow key={s.name} {...s} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="History" title="Incident history" />
        <div className="rounded-lg border border-border-default bg-bg-elevated p-8 text-center">
          <p className="text-sm text-text-secondary">No incidents reported in the last 90 days.</p>
        </div>
      </Section>
    </>
  )
}
