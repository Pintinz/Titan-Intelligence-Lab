import { Link } from 'react-router-dom'
import { Target, Eye, Sparkles, Handshake, Newspaper, Palette, ShieldCheck } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading, Hairline } from '@/pages/landing/section-primitives'
import { PageHero, StatCard, TeamPrincipleCard } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const PRINCIPLES = [
  {
    number: '01',
    title: 'Evidence over verdicts',
    description: 'A prediction without its reasoning is just an opinion. Every TitanIQ output ships with the evidence — form, news, community signal — that produced it.',
  },
  {
    number: '02',
    title: 'Confidence is a signal, not a sales pitch',
    description: 'A low-confidence prediction is not a worse prediction — it is an honest one. We calibrate confidence against real outcomes, not vibes.',
  },
  {
    number: '03',
    title: 'Intelligence, not gambling',
    description: 'TitanIQ is a sports intelligence platform. We do not take bets, we do not profit from wagers, and our models are never influenced by betting markets we participate in.',
  },
  {
    number: '04',
    title: 'The model keeps learning',
    description: "Every match result feeds back into recalibration. A model that doesn't improve after being wrong isn't intelligence — it's a static lookup table.",
  },
]

const STATS = [
  { value: '4', label: 'Sport Intelligence Centers' },
  { value: '24/7', label: 'Live match monitoring' },
  { value: '100%', label: 'Predictions with visible evidence' },
  { value: '0', label: 'Betting markets we operate' },
]

export default function AboutPage() {
  return (
    <>
      <Seo
        title="About TitanIQ"
        description="TitanIQ is a sports intelligence platform built on explainable, evidence-backed predictions — not a betting site or score app. Learn our mission and principles."
        path="/about"
      />
      <PageHero
        eyebrow="About TitanIQ"
        title="Sports intelligence, not sports gambling."
        description="TitanIQ exists because the sports prediction category is dominated by black-box tips and betting-adjacent content. We think intelligence should be explainable, and confidence should mean something."
        actions={
          <>
            <Button asChild size="lg">
              <Link to="/signup">Start free</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link to="/methodology">See the methodology</Link>
            </Button>
          </>
        }
      />

      <Section>
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <div className="flex size-9 items-center justify-center rounded-md bg-accent-primary-muted">
              <Target className="size-4 text-accent-primary" aria-hidden="true" />
            </div>
            <h2 className="mt-4 font-display text-xl font-semibold text-text-primary">Our mission</h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              Convert live sports data, structured intelligence, news, and community signal into explainable
              sports intelligence — where every prediction is one output among many, backed by visible evidence,
              not the entire product.
            </p>
          </div>
          <div>
            <div className="flex size-9 items-center justify-center rounded-md bg-accent-primary-muted">
              <Eye className="size-4 text-accent-primary" aria-hidden="true" />
            </div>
            <h2 className="mt-4 font-display text-xl font-semibold text-text-primary">What we're not</h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              We are not a betting site, a tipster service, or a score app with a prediction bolted on. We don't
              take wagers, we don't profit when you lose one, and we say so plainly in our{' '}
              <Link to="/disclaimer" className="text-accent-primary hover:text-accent-primary-hover">Disclaimer</Link>.
            </p>
          </div>
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Principles" title="How we operate" description="Four commitments that shape every product decision." />
        <div className="grid gap-8 sm:grid-cols-2">
          {PRINCIPLES.map((p) => (
            <TeamPrincipleCard key={p.number} {...p} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="By the numbers" title="TitanIQ today" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {STATS.map((stat) => (
            <StatCard key={stat.label} {...stat} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Beyond the product" title="Partnerships, press & brand" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Link
            to="/partners"
            className="flex items-start gap-3 rounded-lg border border-border-default bg-bg-elevated p-4 transition-all duration-200 hover:border-accent-primary/50 hover:shadow-elevation-2"
          >
            <Handshake className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-text-primary">Partners</p>
              <p className="mt-0.5 text-xs text-text-muted">Data, news & technology</p>
            </div>
          </Link>
          <Link
            to="/press-kit"
            className="flex items-start gap-3 rounded-lg border border-border-default bg-bg-elevated p-4 transition-all duration-200 hover:border-accent-primary/50 hover:shadow-elevation-2"
          >
            <Newspaper className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-text-primary">Press Kit</p>
              <p className="mt-0.5 text-xs text-text-muted">Boilerplate & media contact</p>
            </div>
          </Link>
          <Link
            to="/brand-assets"
            className="flex items-start gap-3 rounded-lg border border-border-default bg-bg-elevated p-4 transition-all duration-200 hover:border-accent-primary/50 hover:shadow-elevation-2"
          >
            <Palette className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-text-primary">Brand Assets</p>
              <p className="mt-0.5 text-xs text-text-muted">Logo, color & type</p>
            </div>
          </Link>
          <Link
            to="/trust-center"
            className="flex items-start gap-3 rounded-lg border border-border-default bg-bg-elevated p-4 transition-all duration-200 hover:border-accent-primary/50 hover:shadow-elevation-2"
          >
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-text-primary">Trust Center</p>
              <p className="mt-0.5 text-xs text-text-muted">Security, privacy & compliance</p>
            </div>
          </Link>
        </div>
      </Section>

      <Hairline />

      <Section className="text-center">
        <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-accent-primary-muted">
          <Sparkles className="size-5 text-accent-primary" aria-hidden="true" />
        </div>
        <h2 className="mt-4 font-display text-2xl font-semibold text-text-primary">Built by Titan Intelligence Labs</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-text-secondary">
          TitanIQ is the flagship product of Titan Intelligence Labs, a team focused on applying explainable machine
          learning to domains where a confident wrong answer does real harm. Sport is our first domain — the
          feedback loop is fast, the data is rich, and the stakes teach discipline.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button asChild size="lg">
            <Link to="/careers">View open roles</Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link to="/contact">Get in touch</Link>
          </Button>
        </div>
      </Section>
    </>
  )
}
