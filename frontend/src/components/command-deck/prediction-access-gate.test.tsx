import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PredictionAccessIndicator, PredictionAccessExhaustedCard } from './prediction-access-gate'
import { useAuthStore } from '@/stores/auth-store'

vi.mock('@/lib/api/predictions', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/predictions')>('@/lib/api/predictions')
  return { ...actual, predictionsApi: { entitlement: vi.fn() } }
})
vi.mock('@/lib/capacitor', () => ({ isNativePlatform: vi.fn() }))
vi.mock('@/lib/ads/rewarded-ad-service', () => ({ showRewardedPredictionAd: vi.fn() }))

const { predictionsApi } = await import('@/lib/api/predictions')
const { isNativePlatform } = await import('@/lib/capacitor')
const { showRewardedPredictionAd } = await import('@/lib/ads/rewarded-ad-service')

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ profile: { id: 'user-1', email: 'a@b.com', role: 'free', status: 'active', email_verified: true, created_at: '', last_login_at: null } })
})

describe('PredictionAccessIndicator', () => {
  it('shows the real remaining-credits count from the backend', async () => {
    vi.mocked(predictionsApi.entitlement).mockResolvedValue({
      available_predictions: 3,
      initial_free_predictions: 5,
      rewarded_predictions_granted: 0,
      requires_rewarded_ad: false,
    })

    renderWithProviders(<PredictionAccessIndicator />)

    expect(await screen.findByText('3 predictions remaining')).toBeInTheDocument()
  })

  it('renders nothing while the entitlement hasn\'t loaded yet — never a fabricated placeholder count', () => {
    vi.mocked(predictionsApi.entitlement).mockReturnValue(new Promise(() => {}))
    const { container } = renderWithProviders(<PredictionAccessIndicator />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('PredictionAccessExhaustedCard', () => {
  it('shows a real "account not ready" message instead of silently doing nothing when profile has not loaded yet', async () => {
    // Live bug (2026-08-23): `profile` loads asynchronously after sign-in (auth-store.ts's
    // fire-and-forget `refreshProfile()`); a bare `if (!profile) return` on click meant a user who
    // reached this card before that resolved saw nothing happen at all — no video, no message —
    // reported as "clicking watch video did not pop up any video."
    useAuthStore.setState({ profile: null })
    vi.mocked(isNativePlatform).mockReturnValue(true)
    vi.mocked(predictionsApi.entitlement).mockResolvedValue({
      available_predictions: 0,
      initial_free_predictions: 5,
      rewarded_predictions_granted: 0,
      requires_rewarded_ad: true,
    })

    renderWithProviders(<PredictionAccessExhaustedCard />)
    await userEvent.click(await screen.findByText(/Watch Video & Unlock/))

    expect(await screen.findByText(/Still loading your account/)).toBeInTheDocument()
    expect(showRewardedPredictionAd).not.toHaveBeenCalled()
  })

  it('shows the web fallback message and never calls the native AdMob SDK — spec Phase 4', async () => {
    vi.mocked(isNativePlatform).mockReturnValue(false)
    vi.mocked(predictionsApi.entitlement).mockResolvedValue({
      available_predictions: 0,
      initial_free_predictions: 5,
      rewarded_predictions_granted: 0,
      requires_rewarded_ad: true,
    })

    renderWithProviders(<PredictionAccessExhaustedCard />)
    await userEvent.click(await screen.findByText(/Watch Video & Unlock/))

    expect(await screen.findByText(/available in the TitanIQ mobile app/)).toBeInTheDocument()
    expect(showRewardedPredictionAd).not.toHaveBeenCalled()
  })

  it('grants nothing and shows "Reward not completed" when the ad is dismissed without a reward', async () => {
    vi.mocked(isNativePlatform).mockReturnValue(true)
    vi.mocked(predictionsApi.entitlement).mockResolvedValue({
      available_predictions: 0,
      initial_free_predictions: 5,
      rewarded_predictions_granted: 0,
      requires_rewarded_ad: true,
    })
    vi.mocked(showRewardedPredictionAd).mockResolvedValue({ status: 'dismissed_without_reward' })

    renderWithProviders(<PredictionAccessExhaustedCard />)
    await userEvent.click(await screen.findByText(/Watch Video & Unlock/))

    expect(await screen.findByText('Reward not completed.')).toBeInTheDocument()
  })

  it('shows "Rewarded video unavailable" and grants nothing when the ad fails to load', async () => {
    vi.mocked(isNativePlatform).mockReturnValue(true)
    vi.mocked(predictionsApi.entitlement).mockResolvedValue({
      available_predictions: 0,
      initial_free_predictions: 5,
      rewarded_predictions_granted: 0,
      requires_rewarded_ad: true,
    })
    vi.mocked(showRewardedPredictionAd).mockResolvedValue({ status: 'failed_to_load', message: 'No fill' })

    renderWithProviders(<PredictionAccessExhaustedCard />)
    await userEvent.click(await screen.findByText(/Watch Video & Unlock/))

    expect(await screen.findByText('Rewarded video unavailable. Please try again.')).toBeInTheDocument()
  })

  it('never claims credits landed until the backend entitlement actually confirms a higher balance (Phase 8 rule #8)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    vi.mocked(isNativePlatform).mockReturnValue(true)
    let call = 0
    vi.mocked(predictionsApi.entitlement).mockImplementation(() => {
      call += 1
      // First read: 0 remaining. After the SDK reports "rewarded", the backend hasn't actually
      // granted anything yet (no real SSV callback exists in this test) — every subsequent poll
      // must keep reporting 0 until this test explicitly proves the UI waits rather than lies.
      return Promise.resolve({ available_predictions: 0, initial_free_predictions: 5, rewarded_predictions_granted: 0, requires_rewarded_ad: true })
    })
    vi.mocked(showRewardedPredictionAd).mockResolvedValue({ status: 'rewarded', amount: 2 })

    try {
      renderWithProviders(<PredictionAccessExhaustedCard />)
      await user.click(await screen.findByText(/Watch Video & Unlock/))
      await vi.advanceTimersByTimeAsync(5_000)

      // The SDK says "rewarded", but the balance never actually increases in this test — the UI
      // must show "confirming", never "unlocked", for as long as that remains true.
      expect(screen.getByText('Confirming your reward…')).toBeInTheDocument()
      expect(screen.queryByText(/predictions unlocked/)).not.toBeInTheDocument()
      expect(call).toBeGreaterThan(1) // proves it actually re-polled, not just read once and gave up
    } finally {
      vi.useRealTimers()
    }
  }, 15_000)
})
