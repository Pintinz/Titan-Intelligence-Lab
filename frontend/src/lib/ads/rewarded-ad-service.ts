import { AdMob, RewardAdPluginEvents, type AdMobRewardItem } from '@capacitor-community/admob'
import { isNativePlatform, nativePlatform } from '@/lib/capacitor'
import { env } from '@/lib/env'

/** Google's official public test rewarded-ad unit IDs — always safe, always return real (test)
 * ads, and are Google's own documented fallback for exactly this situation: no real AdMob
 * account/ad units exist in this environment to issue production IDs from. Per Google's policy,
 * these are the correct thing to ship whenever a real ID isn't genuinely configured — never a
 * placeholder invented locally. https://developers.google.com/admob/android/test-ads */
const TEST_REWARDED_AD_UNIT_ID = {
  android: 'ca-app-pub-3940256099942544/5224354917',
  ios: 'ca-app-pub-3940256099942544/1712485313',
} as const

function rewardedAdUnitId(): string {
  const platform = nativePlatform()
  if (platform === 'android') return env.admobAndroidRewardedAdUnitId || TEST_REWARDED_AD_UNIT_ID.android
  if (platform === 'ios') return env.admobIosRewardedAdUnitId || TEST_REWARDED_AD_UNIT_ID.ios
  return TEST_REWARDED_AD_UNIT_ID.android
}

function usingTestAdUnit(): boolean {
  const platform = nativePlatform()
  if (platform === 'android') return !env.admobAndroidRewardedAdUnitId
  if (platform === 'ios') return !env.admobIosRewardedAdUnitId
  return true
}

let initialized = false

/** Idempotent — `AdMob.initialize()` is safe to no-op-guard rather than calling once at app
 * startup unconditionally, since a free user might never reach a screen that needs ads this
 * session at all (no reason to pay SDK init cost on every native app launch). */
async function ensureInitialized(): Promise<void> {
  if (initialized) return
  await AdMob.initialize({
    initializeForTesting: usingTestAdUnit(),
    // AdMob's own COPPA/under-consent-age flags default to false (spec §12: "do not request
    // tracking permission unnecessarily") — TitanIQ has no children's-content classification and
    // no reason to opt into either, so neither is set here.
  })
  initialized = true
}

export type RewardOutcome =
  | { status: 'rewarded'; amount: number }
  | { status: 'dismissed_without_reward' }
  | { status: 'failed_to_load'; message: string }
  | { status: 'failed_to_show'; message: string }
  | { status: 'unavailable_on_web' }
  | { status: 'offline' }

/**
 * `RewardedAdService` — native-only (spec Phase 4: "Do NOT show native AdMob inside the normal
 * web application"). The actual credit grant never happens here or anywhere else client-side —
 * `showRewardedPredictionAd()` only reports what the AdMob SDK itself observed; the real grant
 * only lands once Google's servers call the backend's SSV callback (see
 * `admob_ssv_verifier.py`/`prediction_router.py`'s `/credits/admob-ssv-callback`) and the caller
 * must re-fetch entitlement afterward rather than trust this function's return value as "credits
 * were added." A `rewarded` outcome here means "the SDK confirms the user watched to completion,"
 * not "the backend confirms it" — those are deliberately different claims (spec Phase 5: "do not
 * trust arbitrary frontend requests").
 */
export async function showRewardedPredictionAd(userId: string): Promise<RewardOutcome> {
  if (!isNativePlatform()) return { status: 'unavailable_on_web' }
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return { status: 'offline' }

  await ensureInitialized()

  try {
    await AdMob.prepareRewardVideoAd({
      adId: rewardedAdUnitId(),
      isTesting: usingTestAdUnit(),
      // Non-personalized ads only, deliberately — a real GDPR/UMP consent-collection flow (spec
      // Phase 12) isn't built in this pass, and requesting personalized ads without real consent
      // in place would be a compliance gap, not just a missing feature. Revisit once a real
      // consent flow exists.
      npa: true,
      // Echoed back verbatim inside Google's signed SSV callback payload — this is how the
      // backend knows which user to credit without trusting anything the client itself asserts.
      ssv: { userId },
    })
  } catch (error) {
    return { status: 'failed_to_load', message: error instanceof Error ? error.message : 'The rewarded video could not be loaded.' }
  }

  // `showRewardVideoAd()` only resolves once the SDK reports `Rewarded` (its own contract), so a
  // dismiss-without-reward or a show failure would otherwise hang this promise forever — racing
  // it against the `Dismissed`/`FailedToShow` events (via the shared `settle` below) is what makes
  // every Phase 8 state reachable. `settle` is assigned before any listener is registered, so
  // there is no window where an event could fire before it's safe to call.
  let settle!: (result: RewardOutcome) => void
  const outcomePromise = new Promise<RewardOutcome>((resolve) => {
    let settled = false
    settle = (result) => {
      if (settled) return
      settled = true
      resolve(result)
    }
  })

  const [rewardListener, dismissedListener, failedToShowListener] = await Promise.all([
    AdMob.addListener(RewardAdPluginEvents.Rewarded, (reward: AdMobRewardItem) => settle({ status: 'rewarded', amount: reward.amount })),
    AdMob.addListener(RewardAdPluginEvents.Dismissed, () => settle({ status: 'dismissed_without_reward' })),
    AdMob.addListener(RewardAdPluginEvents.FailedToShow, (error) =>
      settle({ status: 'failed_to_show', message: error.message || 'The rewarded video could not be shown.' }),
    ),
  ])

  AdMob.showRewardVideoAd().catch((error) => {
    settle({ status: 'failed_to_show', message: error instanceof Error ? error.message : 'The rewarded video could not be shown.' })
  })

  const outcome = await outcomePromise
  await Promise.all([rewardListener.remove(), dismissedListener.remove(), failedToShowListener.remove()])
  return outcome
}
