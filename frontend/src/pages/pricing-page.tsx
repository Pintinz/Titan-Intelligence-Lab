import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { billingApi } from '@/lib/api/billing'
import { Seo } from '@/components/seo/seo'
import { Section, SectionHeading } from '@/pages/landing/section-primitives'
import { PageHero, PricingTierCard, FaqAccordion } from '@/components/marketing/marketing-primitives'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'

/** Marketing copy per real backend plan key — price/name/billing_period come from
 * `billingApi.listPlans()` so this page can never drift from what checkout actually charges
 * (spec: "Pricing page must obtain plan information from the backend"). Only the persuasive
 * copy (description, feature bullets, CTA) lives here, since the `Plan` domain model doesn't
 * carry marketing text. */
const PLAN_COPY: Record<string, { description: string; features: string[]; cta: string; ctaHref: string; featured?: boolean }> = {
  free: {
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
  pro: {
    description: 'For serious followers of the intelligence — faster data, deeper history, more markets.',
    features: [
      'Everything in Free',
      '50 predictions/day (vs. 5 on Free)',
      'Advanced AI explanations',
      'Historical prediction access',
      'Ad-free experience',
    ],
    cta: 'Get Pro',
    ctaHref: '/app/billing?plan=pro',
    featured: true,
  },
  premium: {
    description: 'The full intelligence stack — unlimited predictions, priority delivery, and data exports.',
    features: [
      'Everything in Pro',
      'Unlimited daily predictions',
      'Priority intelligence delivery',
      'Data exports',
      'API access',
    ],
    cta: 'Get Premium',
    ctaHref: '/app/billing?plan=premium',
  },
}

const ENTERPRISE_TIER = {
  name: 'Enterprise',
  price: 'Custom',
  description: 'API access, custom data feeds, and dedicated support for teams building on TitanIQ.',
  features: [
    'Everything in Premium',
    'TitanIQ API access with elevated rate limits',
    'Custom integrations & data feeds',
    'Dedicated account manager',
    'SLA-backed uptime commitment',
    'Enterprise-grade security review support',
  ],
  cta: 'Talk to sales',
  ctaHref: '/contact',
}

const FAQS = [
  {
    question: 'Is TitanIQ a betting site?',
    answer: 'No. TitanIQ is a sports intelligence platform — we don\'t take wagers or operate betting markets. See our Disclaimer for the full detail.',
  },
  {
    question: 'Can I switch plans or cancel later?',
    answer: 'Contact support to change or cancel your plan — self-service plan management isn\'t available yet. Changes take effect at the end of your current billing period.',
  },
  {
    question: 'Is there a free trial of Pro or Premium?',
    answer: 'No — Pro and Premium are billed as soon as you subscribe. The Free plan itself has no time limit, so you can explore the platform before upgrading.',
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
  const plansQuery = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() })

  const tiers = (plansQuery.data ?? [])
    .filter((plan) => PLAN_COPY[plan.key])
    .sort((a, b) => a.price_cents - b.price_cents)
    .map((plan) => ({
      name: plan.name,
      price: `$${(plan.price_cents / 100).toFixed(plan.price_cents % 100 === 0 ? 0 : 2)}`,
      period: `/${plan.billing_period === 'monthly' ? 'month' : plan.billing_period}`,
      ...PLAN_COPY[plan.key],
    }))

  return (
    <>
      <Seo
        title="Pricing"
        description="TitanIQ pricing — Free, Pro, Premium, and Enterprise plans for explainable sports intelligence across Football, Basketball, Baseball, and Table Tennis."
        path="/pricing"
      />
      <PageHero
        eyebrow="Pricing"
        title="Simple pricing. No hidden odds."
        description="Start free. Upgrade when you want faster data and deeper intelligence. Enterprise API access scales with you."
      />

      <Section>
        {plansQuery.isPending && (
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-96" />
            ))}
          </div>
        )}
        {plansQuery.isError && <ErrorState error={plansQuery.error} onRetry={() => void plansQuery.refetch()} />}
        {!plansQuery.isPending && !plansQuery.isError && (
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
            {tiers.map((tier) => (
              <PricingTierCard key={tier.name} {...tier} />
            ))}
            <PricingTierCard {...ENTERPRISE_TIER} />
          </div>
        )}
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
