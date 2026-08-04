import { Link } from 'react-router-dom'
import { KeyRound, Webhook, Cpu, Code } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, ValueCard } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const CAPABILITIES = [
  { icon: KeyRound, title: 'API key authentication', description: 'Scoped keys per environment, rotated from your account settings.' },
  { icon: Webhook, title: 'Structured JSON responses', description: 'Predictions, confidence scores, and evidence returned as clean, typed JSON.' },
  { icon: Cpu, title: 'Real-time & polling access', description: 'Poll for updates or subscribe to live match state depending on your plan.' },
  { icon: Code, title: 'Consistent resource model', description: 'Matches, teams, players, and competitions follow one predictable schema across all four sports.' },
]

const QUICKSTART = `curl https://api.titaniq.ai/v1/football/matches/live \\
  -H "Authorization: Bearer YOUR_API_KEY"`

export default function DeveloperPortalPage() {
  return (
    <>
      <Seo
        title="Developer Portal"
        description="Build on the TitanIQ API — authentication, quickstart, and integration patterns for developers."
        path="/developers"
      />
      <PageHero
        eyebrow="Developers"
        title="Build on TitanIQ."
        description="A structured, explainable sports-intelligence API — predictions, confidence scores, and the evidence behind them, across four sports."
        actions={
          <>
            <Button asChild size="lg">
              <Link to="/api-reference">Read the API Reference</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link to="/contact">Talk to Enterprise Sales</Link>
            </Button>
          </>
        }
      />

      <Section>
        <SectionHeading eyebrow="Capabilities" title="What you get" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map((c) => (
            <ValueCard key={c.title} {...c} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Quickstart" title="Your first request" />
        <div className="max-w-2xl overflow-hidden rounded-lg border border-border-default bg-bg-primary">
          <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2">
            <span className="font-mono text-xs text-text-muted">Terminal</span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm">
            <code className="font-mono text-text-primary">{QUICKSTART}</code>
          </pre>
        </div>
        <p className="mt-4 max-w-2xl text-sm text-text-secondary">
          Generate an API key from your account settings once signed in. Free-tier keys are rate-limited; see the{' '}
          <Link to="/api-reference" className="text-accent-primary hover:text-accent-primary-hover">API Reference</Link> for limits per plan and the full
          endpoint catalog.
        </p>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Fair use" title="Before you build" />
        <p className="max-w-2xl text-sm leading-relaxed text-text-secondary">
          API access is governed by our{' '}
          <Link to="/acceptable-use" className="text-accent-primary hover:text-accent-primary-hover">Acceptable Use Policy</Link> — in short: build real
          applications, respect documented rate limits, and don't redistribute raw API responses wholesale outside
          an Enterprise agreement.
        </p>
      </Section>
    </>
  )
}
