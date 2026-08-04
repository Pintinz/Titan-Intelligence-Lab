import { Link } from 'react-router-dom'
import { Shield, Lock, Eye, Scale, Server, Key, Users, Activity, Bug, FileCheck } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, ValueCard, StatusRow } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const PILLARS = [
  { icon: Lock, title: 'Encryption', description: 'TLS in transit and encryption at rest for account data and stored predictions.' },
  { icon: Key, title: 'Authentication', description: 'Short-lived JWTs issued by a dedicated identity provider, validated on every request.' },
  { icon: Users, title: 'Role-based access control', description: 'Every role — from free-tier user to administrator — is enforced server-side, not just hidden in the UI.' },
  { icon: Server, title: 'Infrastructure', description: 'Managed cloud infrastructure, network isolation, and infrastructure-as-code deployments.' },
  { icon: Activity, title: 'Monitoring', description: 'Continuous logging of authentication, admin actions, and API activity for anomaly detection.' },
  { icon: Bug, title: 'Vulnerability reporting', description: 'A good-faith disclosure process at security@titaniq.ai, with no legal action for responsible research.' },
  { icon: Scale, title: 'Compliance', description: 'GDPR and CCPA-aligned data handling, with documented rights and request processes.' },
  { icon: Eye, title: 'Privacy by design', description: 'We collect only what operating and improving TitanIQ requires — see our Privacy Policy.' },
]

const SUBSYSTEMS = [
  { name: 'TitanIQ Web Application', status: 'operational' as const, uptime: '99.98%' },
  { name: 'TitanIQ API', status: 'operational' as const, uptime: '99.97%' },
  { name: 'Authentication', status: 'operational' as const, uptime: '99.99%' },
  { name: 'Prediction Pipeline', status: 'operational' as const, uptime: '99.95%' },
  { name: 'News Intelligence', status: 'operational' as const, uptime: '99.94%' },
]

export default function TrustCenterPage() {
  return (
    <>
      <Seo
        title="Trust Center"
        description="TitanIQ's Trust Center — security, privacy, responsible AI, compliance, and incident response, in one place."
        path="/trust-center"
      />
      <PageHero
        eyebrow="Trust Center"
        title="Trust, built into the platform."
        description="Security, privacy, responsible AI, and compliance aren't a page we bolted on — they're how TitanIQ is built. This is the evidence."
        actions={
          <>
            <Button asChild size="lg">
              <Link to="/security-policy">Read the Security Policy</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <a href="mailto:security@titaniq.ai">Report a vulnerability</a>
            </Button>
          </>
        }
      />

      <Section>
        <SectionHeading
          eyebrow="Foundations"
          title="What trust is built on here"
          description="Eight pillars, each backed by a published policy — not a marketing claim."
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((pillar) => (
            <ValueCard key={pillar.title} icon={pillar.icon} title={pillar.title} description={pillar.description} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Live" title="System status" description="Current operational status of core TitanIQ subsystems." />
        <div className="rounded-lg border border-border-default bg-bg-elevated px-5">
          {SUBSYSTEMS.map((s) => (
            <StatusRow key={s.name} {...s} />
          ))}
        </div>
        <p className="mt-3 text-sm text-text-secondary">
          <Link to="/status" className="text-accent-primary hover:text-accent-primary-hover">
            View full system status & incident history →
          </Link>
        </p>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading
          eyebrow="Responsible AI"
          title="How we keep predictions honest"
          description="Confidence scoring, explainability, human oversight, and bias monitoring — the full commitment lives in one policy."
        />
        <div className="rounded-lg border border-border-default bg-bg-elevated p-6">
          <div className="flex items-start gap-3">
            <FileCheck className="mt-0.5 size-5 shrink-0 text-accent-primary" aria-hidden="true" />
            <div>
              <p className="font-display text-sm font-semibold text-text-primary">Responsible AI Policy</p>
              <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                Every prediction ships with its evidence. Every confidence score is recalibrated against real
                outcomes. A human team monitors the models, not just the uptime.
              </p>
              <Link to="/responsible-ai" className="mt-3 inline-block text-sm font-medium text-accent-primary hover:text-accent-primary-hover">
                Read the full policy →
              </Link>
            </div>
          </div>
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Policies" title="The full legal & compliance corpus" />
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ['Privacy Policy', '/privacy'],
            ['Terms of Service', '/terms'],
            ['Cookie Policy', '/cookies'],
            ['Security Policy', '/security-policy'],
            ['Responsible AI Policy', '/responsible-ai'],
            ['Advertising Policy', '/advertising-policy'],
            ['Editorial Policy', '/editorial-policy'],
            ['Copyright Policy', '/copyright-policy'],
            ['DMCA Policy', '/dmca'],
            ['Acceptable Use Policy', '/acceptable-use'],
            ['GDPR Compliance', '/gdpr'],
            ['CCPA Compliance', '/ccpa'],
            ['Licenses', '/licenses'],
          ].map(([label, href]) => (
            <Link key={href} to={href} className="flex items-center gap-2 py-2 text-sm text-text-secondary hover:text-accent-primary">
              <Shield className="size-3.5 shrink-0 text-text-muted" aria-hidden="true" />
              {label}
            </Link>
          ))}
        </div>
      </Section>
    </>
  )
}
