import { Link } from 'react-router-dom'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, PricingTierCard, FaqAccordion } from '@/components/marketing/marketing-primitives'

const TIERS = [
  {
    name: 'Free',
    price: '$0',
    period: '/month',
    description: 'Explore explainable sports intelligence across all four Sport Intelligence Centers.',
    features: [
      'Live match intelligence for Football, Basketball, Baseball & Table Tennis',
      'Confidence-scored predictions with visible evidence',
      'News Intelligence summaries',
      'Community Pulse sentiment',
      'Standard refresh rate',
    ],
    cta: 'Start free',
    ctaHref: '/signup',
  },
  {
    name: 'Pro',
    price: '$24',
    period: '/month',
    description: 'For serious follower of the intelligence — faster data, deeper history, more markets.',
    features: [
      'Everything in Free',
      'Real-time refresh on live matches',
      'Full Knowledge Graph access',
      'Learning Intelligence pipeline visibility',
      'Historical prediction accuracy & calibration reports',
      'Priority support',
    ],
    cta: 'Start Pro trial',
    ctaHref: '/signup',
    featured: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    description: 'API access, custom data feeds, and dedicated support for teams building on TitanIQ.',
    features: [
      'Everything in Pro',
      'TitanIQ API access with elevated rate limits',
      'Custom integrations & data feeds',
      'Dedicated account manager',
      'SLA-backed uptime commitment',
      'Enterprise-grade security review support',
    ],
    cta: 'Talk to sales',
    ctaHref: '/contact',
  },
]

const FAQS = [
  {
    question: 'Is TitanIQ a betting site?',
    answer: 'No. TitanIQ is a sports intelligence platform — we don\'t take wagers or operate betting markets. See our Disclaimer for the full detail.',
  },
  {
    question: 'Can I switch plans later?',
    answer: 'Yes. You can upgrade, downgrade, or cancel at any time from account settings — changes to a lower tier take effect at the end of your current billing period.',
  },
  {
    question: 'Do you offer a free trial of Pro?',
    answer: 'Yes, new accounts get a Pro trial when they upgrade. No credit card is charged until the trial ends, and you can cancel any time before then.',
  },
  {
    question: 'How does Enterprise API pricing work?',
    answer: 'Enterprise pricing is usage- and integration-based. Contact our Enterprise Sales team via the Contact page and we\'ll scope a plan for your request volume.',
  },
  {
    question: 'Do you offer refunds?',
    answer: 'Subscription fees already paid are generally non-refundable except where required by law — see our Terms of Service for the complete billing terms.',
  },
]

export default function PricingPage() {
  return (
    <>
      <Seo
        title="Pricing"
        description="TitanIQ pricing — Free, Pro, and Enterprise plans for explainable sports intelligence across Football, Basketball, Baseball, and Table Tennis."
        path="/pricing"
      />
      <PageHero
        eyebrow="Pricing"
        title="Simple pricing. No hidden odds."
        description="Start free. Upgrade when you want faster data and deeper intelligence. Enterprise API access scales with you."
      />

      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          {TIERS.map((tier) => (
            <PricingTierCard key={tier.name} {...tier} />
          ))}
        </div>
        <p className="mt-8 text-center text-sm text-text-secondary">
          Need something custom? <Link to="/contact" className="text-accent-primary hover:text-accent-primary-hover">Talk to our Enterprise Sales team</Link>{' '}
          or explore the <Link to="/api-reference" className="text-accent-primary hover:text-accent-primary-hover">API Reference</Link>.
        </p>
      </Section>

      <Section className="border-t border-border-subtle">
        <SectionHeading eyebrow="Questions" title="Pricing FAQ" />
        <div className="max-w-2xl">
          <FaqAccordion items={FAQS} />
        </div>
      </Section>
    </>
  )
}
