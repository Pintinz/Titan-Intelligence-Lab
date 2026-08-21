import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { billingApi } from '@/lib/api/billing'
import { PricingTierCard } from '@/components/marketing/marketing-primitives'
import { Section, SectionHeading } from './section-primitives'

// Condensed teaser, not a duplicate of /pricing — one line + one proof-point per plan, price/name
// sourced live from the same billingApi.listPlans() the full Pricing page reads, so this can never
// drift from what checkout actually charges.
const PLAN_TEASER: Record<string, { description: string; features: string[]; cta: string; featured?: boolean }> = {
  free: {
    description: 'Explore explainable intelligence across all four sports.',
    features: ['5 predictions/day, full evidence on every one'],
    cta: 'Start free',
  },
  pro: {
    description: 'Faster data, deeper history, ad-free.',
    features: ['50 predictions/day + advanced explanations'],
    cta: 'Get Pro',
    featured: true,
  },
  premium: {
    description: 'The full intelligence stack, unlimited.',
    features: ['Unlimited predictions + priority delivery'],
    cta: 'Get Premium',
  },
}

export function SubscriptionPlansSection() {
  const plansQuery = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() })

  const tiers = (plansQuery.data ?? [])
    .filter((plan) => PLAN_TEASER[plan.key])
    .sort((a, b) => a.price_cents - b.price_cents)
    .map((plan) => ({
      name: plan.name,
      price: `$${(plan.price_cents / 100).toFixed(plan.price_cents % 100 === 0 ? 0 : 2)}`,
      period: `/${plan.billing_period === 'monthly' ? 'month' : plan.billing_period}`,
      ctaHref: plan.price_cents === 0 ? '/signup' : `/app/billing?plan=${plan.key}`,
      ...PLAN_TEASER[plan.key],
    }))

  if (!plansQuery.isPending && tiers.length === 0) return null

  return (
    <Section className="border-b border-border-subtle">
      <SectionHeading
        eyebrow="Subscription Plans"
        title="Start free. Upgrade for depth and speed."
        description="Every plan traces to the same real intelligence engine — higher tiers unlock more of it, never a different product."
      />

      {plansQuery.isPending ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-56 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          {tiers.map((tier) => (
            <PricingTierCard key={tier.name} {...tier} />
          ))}
        </div>
      )}

      <Link
        to="/pricing"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-text-primary transition-colors hover:text-accent-primary"
      >
        See full plan details <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
