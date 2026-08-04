import { Database, Newspaper, Code2, Building2 } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, ValueCard } from '@/components/marketing/marketing-primitives'
import { Button } from '@/components/ui/button'

const PARTNER_TYPES = [
  { icon: Database, title: 'Data Providers', description: 'Sports statistics, live scores, and odds-context providers looking to power TitanIQ\'s prediction pipeline.' },
  { icon: Newspaper, title: 'News & Media', description: 'Licensed news partners whose reporting feeds TitanIQ\'s News Intelligence, always with full attribution.' },
  { icon: Code2, title: 'Technology & Integration', description: 'Platforms and tools that want to embed or consume TitanIQ intelligence via our API.' },
  { icon: Building2, title: 'Enterprise & Distribution', description: 'Media companies and platforms looking to license TitanIQ intelligence for their own audiences.' },
]

export default function PartnersPage() {
  return (
    <>
      <Seo
        title="Partners"
        description="Partner with TitanIQ — data providers, news partners, technology integrations, and enterprise distribution."
        path="/partners"
      />
      <PageHero
        eyebrow="Partners"
        title="Build the intelligence layer with us."
        description="TitanIQ's intelligence is only as good as what feeds it. We partner with data providers, news publishers, and technology platforms who share our standard for evidence."
        actions={
          <Button asChild size="lg">
            <a href="mailto:partners@titaniq.ai">Propose a partnership</a>
          </Button>
        }
      />

      <Section>
        <SectionHeading eyebrow="Partnership types" title="Ways to work with TitanIQ" />
        <div className="grid gap-4 sm:grid-cols-2">
          {PARTNER_TYPES.map((p) => (
            <ValueCard key={p.title} {...p} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Standards" title="What we look for in a partner" />
        <div className="max-w-2xl space-y-3 text-sm leading-relaxed text-text-secondary">
          <p>
            We hold partnerships to the same evidentiary standard as our models: verifiable data quality, clear
            licensing terms, and — for news partners — a commitment to accurate, timely reporting that we can
            attribute properly under our{' '}
            <a href="/editorial-policy" className="text-accent-primary hover:text-accent-primary-hover">Editorial Policy</a>.
          </p>
          <p>
            We do not partner with betting operators or affiliate programs in a way that would compromise the
            editorial independence described in our{' '}
            <a href="/advertising-policy" className="text-accent-primary hover:text-accent-primary-hover">Advertising Policy</a>.
          </p>
        </div>
      </Section>

      <Section className="border-t border-border-subtle text-center">
        <h2 className="font-display text-xl font-semibold text-text-primary">Have a proposal?</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-text-secondary">
          Send an overview of your data, audience, or integration and how it fits TitanIQ, and our partnerships team will follow up.
        </p>
        <Button asChild className="mt-6">
          <a href="mailto:partners@titaniq.ai">partners@titaniq.ai</a>
        </Button>
      </Section>
    </>
  )
}
