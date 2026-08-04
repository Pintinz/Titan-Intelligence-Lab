import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { CreditCard, PlusCircle, Wallet } from 'lucide-react'
import { billingApi } from '@/lib/api/billing'
import type { PlanTier, BillingPeriod } from '@/lib/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

export default function BillingPage() {
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [tier, setTier] = useState<PlanTier>('free')
  const [period, setPeriod] = useState<BillingPeriod>('monthly')
  const [priceCents, setPriceCents] = useState('0')

  const [subjectId, setSubjectId] = useState('')
  const [subscribePlanKey, setSubscribePlanKey] = useState('')

  const plansQuery = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() })

  const createPlan = useMutation({
    mutationFn: () =>
      billingApi.createPlan({ key, name, tier, billing_period: period, price_cents: Number(priceCents) || 0 }),
    onSuccess: () => {
      toast.success('Plan created', name)
      setKey('')
      setName('')
      void plansQuery.refetch()
    },
    onError: (error) => toast.danger('Could not create plan', error instanceof Error ? error.message : undefined),
  })

  const subscribe = useMutation({
    mutationFn: () => billingApi.subscribe('user', subjectId, subscribePlanKey),
    onSuccess: (sub) => toast.success('Subscription created', `${sub.plan_key} — ${sub.status}`),
    onError: (error) => toast.danger('Could not create subscription', error instanceof Error ? error.message : undefined),
  })

  const plans = plansQuery.data ?? []

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Business"
        title="Billing & Revenue"
        description="Plans, subscriptions, and entitlements are live. Revenue reporting, invoices, coupons, trials, and ad monetization are backend-pending — shown honestly below, not faked."
      />

      <SectionCard icon={CreditCard} title="Plans">
        {plansQuery.isPending && <Skeleton className="h-24" />}
        {plansQuery.isError && <ErrorState error={plansQuery.error} onRetry={() => void plansQuery.refetch()} />}
        {plans.length === 0 && !plansQuery.isPending && <EmptyState variant="minimal" title="No plans configured yet" />}
        {plans.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-3">
            {plans.map((plan) => (
              <div key={plan.id} className="rounded-md border border-border-default p-3">
                <div className="flex items-center justify-between">
                  <p className="font-display text-sm font-semibold text-text-primary">{plan.name}</p>
                  <Badge variant="accent" className="capitalize">{plan.tier}</Badge>
                </div>
                <p className="mt-1 font-mono text-xs text-text-muted">{plan.key}</p>
                <p className="mt-2 font-telemetry text-lg text-text-primary">
                  ${(plan.price_cents / 100).toFixed(2)}
                  <span className="text-xs text-text-muted"> / {plan.billing_period}</span>
                </p>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-border-subtle pt-4">
          <div><Label htmlFor="plan-key">Key</Label><Input id="plan-key" value={key} onChange={(e) => setKey(e.target.value)} className="mt-1.5 w-32" /></div>
          <div><Label htmlFor="plan-name">Name</Label><Input id="plan-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 w-40" /></div>
          <div>
            <Label htmlFor="plan-tier">Tier</Label>
            <Select value={tier} onValueChange={(v) => setTier(v as PlanTier)}>
              <SelectTrigger id="plan-tier" className="mt-1.5 w-28"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="free">Free</SelectItem><SelectItem value="rewarded">Rewarded</SelectItem><SelectItem value="premium">Premium</SelectItem></SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="plan-period">Period</Label>
            <Select value={period} onValueChange={(v) => setPeriod(v as BillingPeriod)}>
              <SelectTrigger id="plan-period" className="mt-1.5 w-28"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="monthly">Monthly</SelectItem><SelectItem value="annual">Annual</SelectItem></SelectContent>
            </Select>
          </div>
          <div><Label htmlFor="plan-price">Price (cents)</Label><Input id="plan-price" type="number" value={priceCents} onChange={(e) => setPriceCents(e.target.value)} className="mt-1.5 w-24" /></div>
          <Button size="sm" onClick={() => createPlan.mutate()} disabled={!key || !name || createPlan.isPending} className="gap-1">
            <PlusCircle className="size-3.5" /> {createPlan.isPending ? 'Creating…' : 'Create plan'}
          </Button>
        </div>
      </SectionCard>

      <SectionCard icon={Wallet} title="Manage a subscription" description="Subscribe a known user ID to a plan by key.">
        <div className="flex flex-wrap items-end gap-2">
          <div><Label htmlFor="subject-id">User ID</Label><Input id="subject-id" value={subjectId} onChange={(e) => setSubjectId(e.target.value)} className="mt-1.5 w-64 font-mono text-xs" /></div>
          <div><Label htmlFor="subscribe-plan">Plan key</Label><Input id="subscribe-plan" value={subscribePlanKey} onChange={(e) => setSubscribePlanKey(e.target.value)} className="mt-1.5 w-40" /></div>
          <Button size="sm" onClick={() => subscribe.mutate()} disabled={!subjectId || !subscribePlanKey || subscribe.isPending}>
            {subscribe.isPending ? 'Subscribing…' : 'Subscribe'}
          </Button>
        </div>
      </SectionCard>

      <SectionCard title="Backend Pending">
        <div className="space-y-4">
          <BackendPendingState
            title="Revenue & invoices"
            description="No revenue aggregation or invoice-history endpoint exists yet — subscriptions carry a plan key and status, not a billed-amount ledger."
            recommendedEndpoint="GET /api/v1/admin/billing/revenue · GET /api/v1/admin/billing/invoices"
          />
          <BackendPendingState
            title="Coupons & trials"
            description="No coupon or trial-period model exists in the billing domain yet."
            recommendedEndpoint="POST /api/v1/admin/billing/coupons"
          />
          <BackendPendingState
            title="Google AdSense & AdMob status"
            description="TitanIQ's public pages are AdSense-ready (see the Trust Center and Advertising Policy), but no ad account connection, approval status, or revenue endpoint exists in the backend — this is a future integration, not yet started."
            recommendedEndpoint="GET /api/v1/admin/billing/adsense-status · GET /api/v1/admin/billing/admob-status"
          />
          <BackendPendingState
            title="Payment providers"
            description="No payment-processor (Stripe or similar) integration exists yet — subscriptions today do not move money."
            recommendedEndpoint="GET /api/v1/admin/billing/payment-providers"
          />
        </div>
      </SectionCard>
    </div>
  )
}
