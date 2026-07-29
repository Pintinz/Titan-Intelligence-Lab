import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { billingApi } from '@/lib/api/billing'

export default function BillingPage() {
  const plansQuery = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Billing' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Billing</h1>
      </div>

      {plansQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {plansQuery.data?.map((plan) => (
          <Card key={plan.id}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                {plan.name}
                <Badge variant="accent">{plan.tier}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="font-mono text-2xl font-semibold text-text-primary">
                ${(plan.price_cents / 100).toFixed(2)}
                <span className="text-sm text-text-muted"> /{plan.billing_period}</span>
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
