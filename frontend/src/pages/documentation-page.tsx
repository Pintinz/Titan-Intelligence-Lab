import { Link } from 'react-router-dom'
import { BookOpen, Layers, TrendingUp, Newspaper, Network, GraduationCap, Settings, Shield } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, DocCard } from '@/components/marketing/marketing-primitives'

const GUIDES = [
  { icon: BookOpen, title: 'Getting started', description: 'Create your account and take your first tour of a Sport Intelligence Center.', href: '/signup' },
  { icon: Layers, title: 'Sport Intelligence Centers', description: 'How Football, Basketball, Baseball, and Table Tennis are each structured — matches, teams, players, competitions.', href: '/app' },
  { icon: TrendingUp, title: 'Reading predictions & confidence', description: 'What a confidence score means, how it\'s calibrated, and how to read the evidence behind a pick.', href: '/methodology' },
  { icon: Newspaper, title: 'News Intelligence', description: 'How TitanIQ summarizes news and shows its prediction and confidence impact.', href: '/editorial-policy' },
  { icon: Network, title: 'Knowledge Graph', description: 'Exploring the relationships between teams, players, competitions, and venues.', href: '/app/graph' },
  { icon: GraduationCap, title: 'Learning Intelligence', description: 'How the model retrains itself from real outcomes — the pipeline, visualized.', href: '/app/learning' },
  { icon: Settings, title: 'Account & settings', description: 'Managing your profile, notification preferences, and subscription.', href: '/app/settings' },
  { icon: Shield, title: 'Security & privacy', description: 'How your data is protected, and your privacy rights.', href: '/trust-center' },
]

export default function DocumentationPage() {
  return (
    <>
      <Seo
        title="Documentation"
        description="Guides for using TitanIQ — Sport Intelligence Centers, predictions, confidence scoring, News Intelligence, and the Knowledge Graph."
        path="/docs"
      />
      <PageHero
        eyebrow="Documentation"
        title="Everything you need to use TitanIQ well."
        description="Guides for getting the most out of every Sport Intelligence Center. Building an integration instead? Visit the Developer Portal."
      />

      <Section>
        <SectionHeading eyebrow="Guides" title="Start here" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {GUIDES.map((g) => (
            <DocCard key={g.title} {...g} />
          ))}
        </div>
      </Section>

      <Section className="border-t border-border-subtle text-center">
        <h2 className="font-display text-xl font-semibold text-text-primary">Building on TitanIQ?</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-text-secondary">
          The <Link to="/developers" className="text-accent-primary hover:text-accent-primary-hover">Developer Portal</Link> and{' '}
          <Link to="/api-reference" className="text-accent-primary hover:text-accent-primary-hover">API Reference</Link> cover authentication, endpoints, and
          rate limits for programmatic access.
        </p>
      </Section>
    </>
  )
}
