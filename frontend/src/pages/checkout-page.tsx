import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Clock3, CreditCard, ShieldCheck } from 'lucide-react'
import { billingApi } from '@/lib/api/billing'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/stores/toast-store'

// Paid upgrades deliberately switched off pre-launch — real card charges flow through this form,
// and renewal/failed-payment handling and plan-gated entitlements aren't hardened enough yet
// (Production Readiness Audit §7) to put in front of real users. Flip back to `true` once that
// work lands; nothing else about this page needs to change.
const UPGRADES_ENABLED = false

type Step = 'form' | 'processing' | 'succeeded' | 'pending' | 'failed'

const EMPTY_FORM = {
  cardNumber: '',
  expiryMonth: '',
  expiryYear: '',
  cvv: '',
  email: '',
  firstName: '',
  lastName: '',
  phoneCountryCode: '',
  phoneNumber: '',
  addressLine1: '',
  city: '',
  state: '',
  postalCode: '',
  country: '',
}

export default function CheckoutPage() {
  const [searchParams] = useSearchParams()
  const planKey = searchParams.get('plan') ?? ''

  const [form, setForm] = useState(EMPTY_FORM)
  const [step, setStep] = useState<Step>('form')
  const [resultMessage, setResultMessage] = useState('')

  const plansQuery = useQuery({ queryKey: ['billing', 'plans'], queryFn: () => billingApi.listPlans() })
  const plan = (plansQuery.data ?? []).find((p) => p.key === planKey) ?? null

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }))

  const charge = useMutation({
    mutationFn: () =>
      billingApi.checkout({
        plan_key: planKey,
        card: {
          number: form.cardNumber,
          expiry_month: form.expiryMonth,
          expiry_year: form.expiryYear,
          cvv: form.cvv,
        },
        customer: {
          email: form.email,
          first_name: form.firstName,
          last_name: form.lastName,
          phone_country_code: form.phoneCountryCode,
          phone_number: form.phoneNumber,
          address_line1: form.addressLine1,
          city: form.city,
          state: form.state,
          postal_code: form.postalCode,
          country: form.country,
        },
        redirect_url: `${window.location.origin}/app/billing?plan=${planKey}&status=returned`,
      }),
    onSuccess: (result) => {
      // Card fields are never needed again after submission — drop them from memory immediately,
      // whatever the outcome (they were never persisted, and shouldn't linger in component state).
      setForm((prev) => ({ ...prev, cardNumber: '', expiryMonth: '', expiryYear: '', cvv: '' }))
      setResultMessage(result.message)
      if (result.redirect_url) {
        window.location.href = result.redirect_url
        return
      }
      if (result.status === 'succeeded') setStep('succeeded')
      else if (result.status === 'pending') setStep('pending')
      else setStep('failed')
    },
    onError: (error) => {
      setForm((prev) => ({ ...prev, cardNumber: '', expiryMonth: '', expiryYear: '', cvv: '' }))
      setStep('failed')
      setResultMessage(error instanceof Error ? error.message : 'Something went wrong.')
      toast.danger('Payment could not be processed', error instanceof Error ? error.message : undefined)
    },
  })

  if (!UPGRADES_ENABLED) {
    return (
      <div className="mx-auto max-w-lg py-12">
        <Card className="p-6 text-center">
          <Clock3 className="mx-auto size-10 text-accent-primary" aria-hidden="true" />
          <p className="mt-3 font-display text-lg font-semibold text-text-primary">Upgrades aren't open yet</p>
          <p className="mt-1 text-sm text-text-muted">
            Paid plans aren't available for self-service checkout right now — the Free plan already gives you full
            access to explore TitanIQ. Check back soon, or contact us if you need something sooner.
          </p>
        </Card>
      </div>
    )
  }

  if (!planKey) {
    return (
      <div className="mx-auto max-w-lg py-12">
        <ErrorState error={new Error('No plan selected. Pick a plan from Pricing first.')} />
      </div>
    )
  }

  if (step !== 'form') {
    return (
      <div className="mx-auto max-w-lg py-12">
        <Card className="p-6 text-center">
          {step === 'succeeded' && (
            <>
              <ShieldCheck className="mx-auto size-10 text-success" />
              <p className="mt-3 font-display text-lg font-semibold text-text-primary">Payment received</p>
              <p className="mt-1 text-sm text-text-muted">
                Your subscription activates once we've confirmed the payment with our provider — usually within a
                few seconds.
              </p>
            </>
          )}
          {step === 'pending' && (
            <>
              <ShieldCheck className="mx-auto size-10 text-accent-primary" />
              <p className="mt-3 font-display text-lg font-semibold text-text-primary">Processing your payment</p>
              <p className="mt-1 text-sm text-text-muted">{resultMessage || 'This may take a moment. You can leave this page.'}</p>
            </>
          )}
          {step === 'failed' && (
            <>
              <p className="font-display text-lg font-semibold text-danger">Payment failed</p>
              <p className="mt-1 text-sm text-text-muted">{resultMessage || 'The charge could not be completed.'}</p>
              <Button className="mt-4" onClick={() => setStep('form')}>
                Try again
              </Button>
            </>
          )}
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg space-y-6 py-12">
      {plansQuery.isPending && <Skeleton className="h-16" />}
      {plansQuery.isError && <ErrorState error={plansQuery.error} onRetry={() => void plansQuery.refetch()} />}
      {plan && (
        <div className="rounded-md border border-border-default bg-bg-elevated p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Subscribing to</p>
          <p className="mt-1 font-display text-lg font-semibold text-text-primary">
            {plan.name} — ${(plan.price_cents / 100).toFixed(2)} / {plan.billing_period}
          </p>
        </div>
      )}
      {!plansQuery.isPending && !plan && (
        <ErrorState error={new Error(`Unknown plan "${planKey}".`)} />
      )}

      <Card className="space-y-5 p-6">
        <div>
          <p className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-text-primary">
            <CreditCard className="size-4" /> Card details
          </p>
          <div className="space-y-3">
            <div>
              <Label htmlFor="card-number">Card number</Label>
              <Input id="card-number" inputMode="numeric" value={form.cardNumber} onChange={set('cardNumber')} className="mt-1.5" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label htmlFor="expiry-month">Month</Label>
                <Input id="expiry-month" placeholder="MM" value={form.expiryMonth} onChange={set('expiryMonth')} className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="expiry-year">Year</Label>
                <Input id="expiry-year" placeholder="YYYY" value={form.expiryYear} onChange={set('expiryYear')} className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="cvv">CVV</Label>
                <Input id="cvv" inputMode="numeric" value={form.cvv} onChange={set('cvv')} className="mt-1.5" />
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-border-subtle pt-5">
          <p className="mb-3 text-sm font-semibold text-text-primary">Billing contact</p>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="first-name">First name</Label>
                <Input id="first-name" value={form.firstName} onChange={set('firstName')} className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="last-name">Last name</Label>
                <Input id="last-name" value={form.lastName} onChange={set('lastName')} className="mt-1.5" />
              </div>
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={form.email} onChange={set('email')} className="mt-1.5" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label htmlFor="phone-country-code">Country code</Label>
                <Input id="phone-country-code" placeholder="1" value={form.phoneCountryCode} onChange={set('phoneCountryCode')} className="mt-1.5" />
              </div>
              <div className="col-span-2">
                <Label htmlFor="phone-number">Phone number</Label>
                <Input id="phone-number" value={form.phoneNumber} onChange={set('phoneNumber')} className="mt-1.5" />
              </div>
            </div>
            <div>
              <Label htmlFor="address-line1">Address</Label>
              <Input id="address-line1" value={form.addressLine1} onChange={set('addressLine1')} className="mt-1.5" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label htmlFor="city">City</Label>
                <Input id="city" value={form.city} onChange={set('city')} className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="state">State</Label>
                <Input id="state" value={form.state} onChange={set('state')} className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="postal-code">Postal code</Label>
                <Input id="postal-code" value={form.postalCode} onChange={set('postalCode')} className="mt-1.5" />
              </div>
            </div>
            <div>
              <Label htmlFor="country">Country</Label>
              <Select value={form.country} onValueChange={(v) => setForm((prev) => ({ ...prev, country: v }))}>
                <SelectTrigger id="country" className="mt-1.5">
                  <SelectValue placeholder="Select a country" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="US">United States</SelectItem>
                  <SelectItem value="NG">Nigeria</SelectItem>
                  <SelectItem value="GB">United Kingdom</SelectItem>
                  <SelectItem value="GH">Ghana</SelectItem>
                  <SelectItem value="KE">Kenya</SelectItem>
                  <SelectItem value="ZA">South Africa</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <Button className="w-full" disabled={!plan || charge.isPending} onClick={() => charge.mutate()}>
          {charge.isPending ? 'Processing…' : plan ? `Pay $${(plan.price_cents / 100).toFixed(2)}` : 'Pay'}
        </Button>
        <p className="text-center text-[11px] text-text-muted">
          Card details are encrypted before they leave your session and forwarded to our payment processor —
          TitanIQ never stores your card number, expiry, or CVV.
        </p>
      </Card>
    </div>
  )
}
