import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Landmark, MonitorPlay, PlusCircle, Stethoscope, Wallet } from 'lucide-react'
import { billingApi } from '@/lib/api/billing'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import type { PlanTier, BillingPeriod } from '@/lib/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { OpsPageHeader, SectionCard, HealthPill, BackendPendingState } from '@/components/ops/ops-primitives'
import { CredentialsPanel, statusToHealth, connectionResultTone } from '@/pages/ops/provider-management'
import { toast } from '@/stores/toast-store'

const FLUTTERWAVE_PROVIDER_KEY = 'flutterwave'

function PaymentProvidersSection() {
  const queryClient = useQueryClient()
  const providersQuery = useQuery({ queryKey: ['admin', 'providers'], queryFn: () => adminPlatformApi.listProviders() })
  const flutterwave = (providersQuery.data ?? []).find((p) => p.key === FLUTTERWAVE_PROVIDER_KEY) ?? null

  const invalidateProviders = () => void queryClient.invalidateQueries({ queryKey: ['admin', 'providers'] })

  const register = useMutation({
    mutationFn: () =>
      adminPlatformApi.registerProvider({
        key: FLUTTERWAVE_PROVIDER_KEY,
        name: 'Flutterwave',
        category: 'payment',
        // Flutterwave V4's real OAuth2 token endpoint (verified against developer.flutterwave.com
        // and Flutterwave's own engineering blog, 2026-08-20) — V4 issues short-lived Bearer
        // tokens from a static client_id/client_secret pair rather than accepting one static
        // secret key directly, so "Test connection" exchanges credentials here instead of
        // hitting the payments API itself.
        base_url: 'https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token',
        auth_type: 'oauth2_client_credentials',
      }),
    onSuccess: () => {
      toast.success('Flutterwave registered', 'Add your Secret Key, Public Key, and Webhook Secret Hash below.')
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not register Flutterwave', error instanceof Error ? error.message : undefined),
  })

  const testConnection = useMutation({
    mutationFn: () => adminPlatformApi.testProviderConnection(flutterwave!.id),
    onSuccess: (result) => {
      toast[connectionResultTone(result.status)](`Flutterwave: ${result.status.replace('_', ' ')}`, result.message)
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not test Flutterwave connection', error instanceof Error ? error.message : undefined),
  })

  const activate = useMutation({
    mutationFn: () => adminPlatformApi.activateProvider(flutterwave!.id),
    onSuccess: () => {
      toast.success('Flutterwave activated')
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not activate Flutterwave', error instanceof Error ? error.message : undefined),
  })

  const disable = useMutation({
    mutationFn: () => adminPlatformApi.disableProvider(flutterwave!.id),
    onSuccess: () => {
      toast.success('Flutterwave disabled')
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not disable Flutterwave', error instanceof Error ? error.message : undefined),
  })

  return (
    <SectionCard
      icon={Landmark}
      title="Payment providers"
      description="Flutterwave is TitanIQ's payment provider — subscriptions do not move real money until it's registered here, credentialed, and wired into a checkout flow."
    >
      {providersQuery.isPending && <Skeleton className="h-20" />}
      {providersQuery.isError && <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />}

      {!providersQuery.isPending && !providersQuery.isError && !flutterwave && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border-default bg-bg-elevated p-3">
          <div>
            <p className="text-sm font-medium text-text-primary">Flutterwave is not connected</p>
            <p className="mt-0.5 text-xs text-text-muted">
              Register it, then add your Secret Key, Public Key, and Webhook Secret Hash below.
            </p>
          </div>
          <Button size="sm" onClick={() => register.mutate()} disabled={register.isPending} className="gap-1">
            <PlusCircle className="size-3.5" /> {register.isPending ? 'Registering…' : 'Register Flutterwave'}
          </Button>
        </div>
      )}

      {flutterwave && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <p className="font-display text-sm font-semibold text-text-primary">{flutterwave.name}</p>
              <HealthPill status={statusToHealth(flutterwave.status)} />
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => testConnection.mutate()}
                disabled={testConnection.isPending}
                className="gap-1"
              >
                <Stethoscope className="size-3.5" /> {testConnection.isPending ? 'Testing…' : 'Test connection'}
              </Button>
              {flutterwave.status === 'active' ? (
                <Button size="sm" variant="secondary" onClick={() => disable.mutate()} disabled={disable.isPending}>
                  {disable.isPending ? 'Disabling…' : 'Disable'}
                </Button>
              ) : (
                <Button size="sm" onClick={() => activate.mutate()} disabled={activate.isPending}>
                  {activate.isPending ? 'Activating…' : 'Activate'}
                </Button>
              )}
            </div>
          </div>
          <p className="text-xs text-text-muted">
            V4 API — use credential labels <code className="font-mono">client_id</code> and{' '}
            <code className="font-mono">client_secret</code> (exactly those labels — "Test connection" looks them
            up by name to exchange them for an access token), plus{' '}
            <code className="font-mono">encryption_key</code> for card-field encryption and{' '}
            <code className="font-mono">webhook_secret_hash</code> (the value you set in the Flutterwave dashboard
            under Settings → Webhooks) for verifying inbound webhook events once that handler is built. None of
            these are ever sent to the browser — only used server-side to sign outbound requests.
          </p>
          <CredentialsPanel providerId={flutterwave.id} />
        </div>
      )}
    </SectionCard>
  )
}

const GOOGLE_ADSENSE_PROVIDER_KEY = 'google_adsense'

function GoogleAdSenseSection() {
  const queryClient = useQueryClient()
  const providersQuery = useQuery({ queryKey: ['admin', 'providers'], queryFn: () => adminPlatformApi.listProviders() })
  const adsense = (providersQuery.data ?? []).find((p) => p.key === GOOGLE_ADSENSE_PROVIDER_KEY) ?? null

  const invalidateProviders = () => void queryClient.invalidateQueries({ queryKey: ['admin', 'providers'] })

  const register = useMutation({
    mutationFn: () =>
      adminPlatformApi.registerProvider({
        key: GOOGLE_ADSENSE_PROVIDER_KEY,
        name: 'Google AdSense',
        category: 'advertising',
      }),
    onSuccess: () => {
      toast.success('Google AdSense registered', 'Add your Publisher ID below. Ad slots stay honestly inactive until it is set.')
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not register Google AdSense', error instanceof Error ? error.message : undefined),
  })

  const activate = useMutation({
    mutationFn: () => adminPlatformApi.activateProvider(adsense!.id),
    onSuccess: () => {
      toast.success('Google AdSense activated', 'Ad slots will start rendering on public pages.')
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not activate Google AdSense', error instanceof Error ? error.message : undefined),
  })

  const disable = useMutation({
    mutationFn: () => adminPlatformApi.disableProvider(adsense!.id),
    onSuccess: () => {
      toast.success('Google AdSense disabled')
      invalidateProviders()
    },
    onError: (error) => toast.danger('Could not disable Google AdSense', error instanceof Error ? error.message : undefined),
  })

  return (
    <SectionCard
      icon={MonitorPlay}
      title="Google AdSense"
      description="Ad slots render on free-tier public pages only once a Publisher ID is set here and the provider is activated — never influences predictions, model selection, or explanations."
    >
      {providersQuery.isPending && <Skeleton className="h-20" />}
      {providersQuery.isError && <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />}

      {!providersQuery.isPending && !providersQuery.isError && !adsense && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border-default bg-bg-elevated p-3">
          <div>
            <p className="text-sm font-medium text-text-primary">Google AdSense is not connected</p>
            <p className="mt-0.5 text-xs text-text-muted">
              No ad account, Publisher ID, or revenue endpoint exists yet — register it, then add your Publisher ID below.
            </p>
          </div>
          <Button size="sm" onClick={() => register.mutate()} disabled={register.isPending} className="gap-1">
            <PlusCircle className="size-3.5" /> {register.isPending ? 'Registering…' : 'Register AdSense'}
          </Button>
        </div>
      )}

      {adsense && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <p className="font-display text-sm font-semibold text-text-primary">{adsense.name}</p>
              <HealthPill status={statusToHealth(adsense.status)} />
            </div>
            {adsense.status === 'active' ? (
              <Button size="sm" variant="secondary" onClick={() => disable.mutate()} disabled={disable.isPending}>
                {disable.isPending ? 'Disabling…' : 'Disable'}
              </Button>
            ) : (
              <Button size="sm" onClick={() => activate.mutate()} disabled={activate.isPending}>
                {activate.isPending ? 'Activating…' : 'Activate'}
              </Button>
            )}
          </div>
          <p className="text-xs text-text-muted">
            Use credential label <code className="font-mono">publisher_id</code> for your{' '}
            <code className="font-mono">ca-pub-XXXXXXXXXXXXXXXX</code> AdSense Publisher ID, and{' '}
            <code className="font-mono">admob_app_id</code> if AdMob is also in use. Premium/ad-free plans will bypass
            slot rendering entirely once the entitlement engine is wired up — no ad-serving code path exists in the
            prediction pipeline today or ever will.
          </p>
          <CredentialsPanel providerId={adsense.id} />
          {adsense.status !== 'active' && (
            <p className="text-xs text-warning">Register a Publisher ID, then Activate — ad slots stay dark until both are done.</p>
          )}
        </div>
      )}
    </SectionCard>
  )
}

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
              <SelectContent>
                <SelectItem value="free">Free</SelectItem>
                <SelectItem value="rewarded">Rewarded</SelectItem>
                <SelectItem value="pro">Pro</SelectItem>
                <SelectItem value="premium">Premium</SelectItem>
                <SelectItem value="enterprise">Enterprise</SelectItem>
              </SelectContent>
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

      <PaymentProvidersSection />

      <GoogleAdSenseSection />

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
        </div>
      </SectionCard>
    </div>
  )
}
