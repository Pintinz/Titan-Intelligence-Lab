import { useState } from 'react'
import { Sparkles, PlayCircle, Loader2, WifiOff, TriangleAlert, CircleCheck, MonitorSmartphone } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { usePredictionEntitlement, useInvalidatePredictionEntitlement } from '@/lib/hooks/use-prediction-entitlement'
import { showRewardedPredictionAd, type RewardOutcome } from '@/lib/ads/rewarded-ad-service'
import { isNativePlatform } from '@/lib/capacitor'
import { REWARDED_AD_CREDIT_GRANT } from '@/lib/api/predictions'
import { CDButton } from './primitives/button'
import { CDLabel } from './primitives/panel'

/**
 * Mobile V1 monetization UI (spec Phase 7-9). Two exported pieces, both Command Deck — reusing
 * the existing token system, not a new visual language:
 *   - `PredictionAccessIndicator` — the compact "N remaining" line, meant to sit inline next to a
 *     Generate action, never a dashboard-style metric card.
 *   - `PredictionAccessExhaustedCard` — shown only when a generate attempt actually comes back
 *     402 PREDICTION_CREDIT_REQUIRED (never pre-emptively, so browsing existing intelligence is
 *     never interrupted by a paywall it doesn't need).
 */
export function PredictionAccessIndicator({ className = '' }: { className?: string }) {
  const entitlement = usePredictionEntitlement()
  if (!entitlement.data) return null
  const { available_predictions } = entitlement.data
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.05em] ${className}`}
      style={{ color: available_predictions > 0 ? 'var(--cd-text-muted)' : 'var(--cd-negative)' }}
    >
      <Sparkles className="size-3" aria-hidden="true" />
      {available_predictions} prediction{available_predictions === 1 ? '' : 's'} remaining
    </span>
  )
}

type AdFlowState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'confirming' }
  | { phase: 'rewarded' }
  | { phase: 'confirm_timeout' }
  | { phase: 'outcome'; outcome: Exclude<RewardOutcome['status'], 'rewarded'> | 'account_not_ready' }

/** Polls `/predictions/entitlement` for up to 20s waiting for the balance to actually rise — the
 * AdMob SDK confirming "rewarded" client-side is not the same claim as the backend's SSV callback
 * having landed and actually granted credits (spec Phase 8 rule #8: never tell the user credits
 * arrived until the backend confirms it). Returns `true` only once the balance is observed to
 * increase past `before`. */
async function waitForCreditGrant(before: number, refetch: () => Promise<{ data?: { available_predictions: number } }>): Promise<boolean> {
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    const result = await refetch()
    if ((result.data?.available_predictions ?? before) > before) return true
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  return false
}

export function PredictionAccessExhaustedCard() {
  const profile = useAuthStore((s) => s.profile)
  const entitlement = usePredictionEntitlement()
  const invalidate = useInvalidatePredictionEntitlement()
  const [state, setState] = useState<AdFlowState>({ phase: 'idle' })

  async function handleWatchAd() {
    // `profile` loads asynchronously after sign-in (auth-store.ts's `refreshProfile()` is
    // fire-and-forget) — a bare `return` here on a slow/failed profile fetch left the button
    // silently doing nothing when clicked (no video, no message, no error), reported live as
    // "clicking watch video did not pop up any video." Surfacing it as a real outcome state means
    // the user always sees *something* happened, never silence.
    if (!profile) {
      setState({ phase: 'outcome', outcome: 'account_not_ready' })
      return
    }
    if (!isNativePlatform()) {
      setState({ phase: 'outcome', outcome: 'unavailable_on_web' })
      return
    }
    setState({ phase: 'loading' })
    const before = entitlement.data?.available_predictions ?? 0
    const outcome = await showRewardedPredictionAd(profile.id)

    if (outcome.status !== 'rewarded') {
      setState({ phase: 'outcome', outcome: outcome.status })
      return
    }

    setState({ phase: 'confirming' })
    invalidate()
    const confirmed = await waitForCreditGrant(before, entitlement.refetch)
    setState({ phase: confirmed ? 'rewarded' : 'confirm_timeout' })
  }

  return (
    <div
      className="flex flex-col items-center gap-3 rounded-[var(--cd-radius-2xl)] p-6 text-center backdrop-blur-md"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <CDLabel tone="accent">Prediction access exhausted</CDLabel>
      <p className="font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
        You&apos;ve used your available prediction generations.
        <br />
        Watch a short rewarded video to unlock {REWARDED_AD_CREDIT_GRANT} additional AI predictions.
      </p>

      {state.phase === 'idle' && (
        <CDButton variant="primary" size="md" onClick={handleWatchAd} icon={<PlayCircle className="size-4" aria-hidden="true" />}>
          Watch Video &amp; Unlock {REWARDED_AD_CREDIT_GRANT}
        </CDButton>
      )}

      {state.phase === 'loading' && <StatusLine icon={Loader2} spin label="Preparing your reward…" />}
      {state.phase === 'confirming' && <StatusLine icon={Loader2} spin label="Confirming your reward…" />}

      {state.phase === 'rewarded' && (
        <>
          <StatusLine icon={CircleCheck} tone="positive" label={`${REWARDED_AD_CREDIT_GRANT} predictions unlocked.`} />
          <PredictionAccessIndicator />
        </>
      )}

      {state.phase === 'confirm_timeout' && (
        <>
          <StatusLine icon={TriangleAlert} label="We couldn't confirm your reward yet — it can take a moment to land. Check back shortly." />
          <CDButton variant="secondary" size="sm" onClick={() => invalidate()}>
            Check again
          </CDButton>
        </>
      )}

      {state.phase === 'outcome' && (
        <>
          <OutcomeMessage outcome={state.outcome} />
          {state.outcome !== 'unavailable_on_web' && (
            <CDButton variant="secondary" size="sm" onClick={handleWatchAd}>
              Try again
            </CDButton>
          )}
        </>
      )}
    </div>
  )
}

function StatusLine({
  icon: Icon,
  label,
  spin = false,
  tone,
}: {
  icon: typeof Loader2
  label: string
  spin?: boolean
  tone?: 'positive'
}) {
  return (
    <p className="flex items-center gap-1.5 font-[var(--cd-font-body)] text-[13px]" style={{ color: tone === 'positive' ? 'var(--cd-positive)' : 'var(--cd-text-secondary)' }}>
      <Icon className={`size-4 shrink-0 ${spin ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
      {label}
    </p>
  )
}

function OutcomeMessage({ outcome }: { outcome: Exclude<RewardOutcome['status'], 'rewarded'> | 'account_not_ready' }) {
  switch (outcome) {
    case 'dismissed_without_reward':
      return <StatusLine icon={TriangleAlert} label="Reward not completed." />
    case 'failed_to_load':
    case 'failed_to_show':
      return <StatusLine icon={TriangleAlert} label="Rewarded video unavailable. Please try again." />
    case 'offline':
      return <StatusLine icon={WifiOff} label="An internet connection is required to load the rewarded video." />
    case 'unavailable_on_web':
      return <StatusLine icon={MonitorSmartphone} label="Rewarded unlocks are available in the TitanIQ mobile app." />
    case 'account_not_ready':
      return <StatusLine icon={TriangleAlert} label="Still loading your account — please try again in a moment." />
  }
}
