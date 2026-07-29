import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { billingApi } from '@/lib/api/billing'

/**
 * Live plan data from GET /api/v1/billing/plans (no auth dependency server-side — confirmed in
 * backend/apps/api/routers/billing_router.py — safe to call from this unauthenticated page).
 * Renders ONLY name/tier/price/period, the fields the endpoint actually returns — there is no
 * bulk "list entitlements by plan" endpoint yet, so no "what's included" bullet list is shown
 * (would otherwise require inventing feature labels).
 */
export function PricingSection() {
  const plansQuery = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() })

  return (
    <section id="pricing" className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Pricing</h2>
        <p className="mt-3 text-text-secondary">Plans as configured on the live platform.</p>
      </div>

      {plansQuery.isLoading && (
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {plansQuery.data && plansQuery.data.length === 0 && (
        <p className="mt-10 text-center text-sm text-text-muted">No plans configured yet.</p>
      )}

      {plansQuery.data && plansQuery.data.length > 0 && (
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {plansQuery.data.map((plan) => (
            <Card key={plan.id} className="flex flex-col">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  {plan.name}
                  <Badge variant="accent">{plan.tier}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col justify-between gap-6">
                <p className="font-mono text-3xl font-semibold text-text-primary">
                  ${(plan.price_cents / 100).toFixed(2)}
                  <span className="text-sm font-normal text-text-muted"> /{plan.billing_period}</span>
                </p>
                <Button asChild variant="secondary" className="w-full">
                  <Link to="/signup">Get started</Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
