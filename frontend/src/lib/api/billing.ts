import { api } from '@/lib/api/client'
import type {
  BillingPeriod,
  ChargeResultDto,
  CheckoutCardInput,
  CheckoutCustomerInput,
  PlanDto,
  PlanTier,
  SubscriptionDto,
} from '@/lib/api/types'

export const billingApi = {
  listPlans: () => api.get<PlanDto[]>('/api/v1/billing/plans'),
  checkout: (input: {
    plan_key: string
    card: CheckoutCardInput
    customer: CheckoutCustomerInput
    redirect_url: string
  }) => api.post<ChargeResultDto>('/api/v1/billing/checkout', input),
  createPlan: (input: { key: string; name: string; tier: PlanTier; billing_period?: BillingPeriod; price_cents?: number }) =>
    api.post<PlanDto>('/api/v1/billing/plans', input),
  setEntitlement: (planKey: string, featureKey: string, limitValue: number | null) =>
    api.post(`/api/v1/billing/plans/${planKey}/entitlements`, { feature_key: featureKey, limit_value: limitValue }),
  subscribe: (subjectType: 'user' | 'organization', subjectId: string, planKey: string) =>
    api.post<SubscriptionDto>('/api/v1/billing/subscriptions', {
      subject_type: subjectType,
      subject_id: subjectId,
      plan_key: planKey,
    }),
  cancelSubscription: (subscriptionId: string) =>
    api.post<SubscriptionDto>(`/api/v1/billing/subscriptions/${subscriptionId}/cancel`),
  hasFeature: (subjectType: 'user' | 'organization', subjectId: string, featureKey: string) =>
    api.get<{ subject_id: string; feature_key: string; has_feature: boolean }>(
      `/api/v1/billing/entitlements/${subjectType}/${subjectId}/${featureKey}`,
    ),
}
