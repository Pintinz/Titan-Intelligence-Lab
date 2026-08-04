import { Rocket, CreditCard, Shield, Code2, Trophy, Settings } from 'lucide-react'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, DocCard } from '@/components/marketing/marketing-primitives'

const TOPICS = [
  { icon: Rocket, title: 'Getting started', description: 'Creating an account, navigating your first Sport Intelligence Center, and understanding predictions.', href: '/docs' },
  { icon: Trophy, title: 'Sports & predictions', description: 'How each sport is covered, reading confidence scores, and understanding evidence.', href: '/methodology' },
  { icon: CreditCard, title: 'Billing & subscriptions', description: 'Plans, upgrades, cancellations, and billing questions.', href: '/pricing' },
  { icon: Settings, title: 'Account & settings', description: 'Managing your profile, notifications, and preferences.', href: '/app/settings' },
  { icon: Shield, title: 'Privacy & security', description: 'How your data is handled, and your privacy rights.', href: '/trust-center' },
  { icon: Code2, title: 'API & developers', description: 'Authentication, endpoints, and rate limits for building on TitanIQ.', href: '/developers' },
]

export default function HelpCenterPage() {
  return (
    <>
      <Seo
        title="Help Center"
        description="Browse TitanIQ help topics — getting started, predictions, billing, account settings, privacy, and the API."
        path="/help"
      />
      <PageHero
        eyebrow="Help Center"
        title="How can we help?"
        description="Browse topics below, check our FAQ, or contact Support directly if you can't find what you need."
      />

      <Section>
        <SectionHeading eyebrow="Browse" title="Help topics" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TOPICS.map((topic) => (
            <DocCard key={topic.title} {...topic} />
          ))}
        </div>
      </Section>
    </>
  )
}
