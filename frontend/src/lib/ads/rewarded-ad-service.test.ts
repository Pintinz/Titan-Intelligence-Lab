import { describe, expect, it, vi, beforeEach } from 'vitest'

const mockIsNativePlatform = vi.fn()
const mockNativePlatform = vi.fn()
vi.mock('@/lib/capacitor', () => ({
  isNativePlatform: () => mockIsNativePlatform(),
  nativePlatform: () => mockNativePlatform(),
}))

const mockInitialize = vi.fn()
const mockPrepareRewardVideoAd = vi.fn()
const mockShowRewardVideoAd = vi.fn()
const mockAddListener = vi.fn()
vi.mock('@capacitor-community/admob', () => ({
  AdMob: {
    initialize: (...args: unknown[]) => mockInitialize(...args),
    prepareRewardVideoAd: (...args: unknown[]) => mockPrepareRewardVideoAd(...args),
    showRewardVideoAd: (...args: unknown[]) => mockShowRewardVideoAd(...args),
    addListener: (...args: unknown[]) => mockAddListener(...args),
  },
  RewardAdPluginEvents: {
    Rewarded: 'onRewardedVideoAdReward',
    Dismissed: 'onRewardedVideoAdDismissed',
    FailedToShow: 'onRewardedVideoAdFailedToShow',
  },
}))

// Imported after the mocks above so the module under test picks up the mocked dependencies.
const { showRewardedPredictionAd } = await import('./rewarded-ad-service')

function mockListenerHandle() {
  return { remove: vi.fn().mockResolvedValue(undefined) }
}

describe('showRewardedPredictionAd', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAddListener.mockResolvedValue(mockListenerHandle())
    mockInitialize.mockResolvedValue(undefined)
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })

  it('never touches the native AdMob SDK on web — spec Phase 4', async () => {
    mockIsNativePlatform.mockReturnValue(false)

    const outcome = await showRewardedPredictionAd('user-1')

    expect(outcome).toEqual({ status: 'unavailable_on_web' })
    expect(mockInitialize).not.toHaveBeenCalled()
    expect(mockPrepareRewardVideoAd).not.toHaveBeenCalled()
    expect(mockShowRewardVideoAd).not.toHaveBeenCalled()
  })

  it('reports offline without ever calling the SDK', async () => {
    mockIsNativePlatform.mockReturnValue(true)
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })

    const outcome = await showRewardedPredictionAd('user-1')

    expect(outcome).toEqual({ status: 'offline' })
    expect(mockPrepareRewardVideoAd).not.toHaveBeenCalled()
  })

  it('on native, prepares the ad with ssv.userId and resolves "rewarded" from the Rewarded event', async () => {
    mockIsNativePlatform.mockReturnValue(true)
    mockNativePlatform.mockReturnValue('android')
    mockPrepareRewardVideoAd.mockResolvedValue({ adUnitId: 'test' })
    let rewardedCallback: ((reward: { type: string; amount: number }) => void) | undefined
    mockAddListener.mockImplementation((event: string, cb: (arg: unknown) => void) => {
      if (event === 'onRewardedVideoAdReward') rewardedCallback = cb as typeof rewardedCallback
      return Promise.resolve(mockListenerHandle())
    })
    mockShowRewardVideoAd.mockImplementation(() => {
      // Simulate the SDK firing the reward event once showRewardVideoAd is invoked.
      queueMicrotask(() => rewardedCallback?.({ type: 'prediction_unlock', amount: 2 }))
      return new Promise(() => {}) // showRewardVideoAd itself never settles in this outcome path
    })

    const outcome = await showRewardedPredictionAd('user-42')

    expect(mockPrepareRewardVideoAd).toHaveBeenCalledWith(expect.objectContaining({ ssv: { userId: 'user-42' } }))
    expect(outcome).toEqual({ status: 'rewarded', amount: 2 })
  })

  it('resolves "dismissed_without_reward" when the ad is closed without earning a reward, granting nothing', async () => {
    mockIsNativePlatform.mockReturnValue(true)
    mockNativePlatform.mockReturnValue('android')
    mockPrepareRewardVideoAd.mockResolvedValue({ adUnitId: 'test' })
    let dismissedCallback: (() => void) | undefined
    mockAddListener.mockImplementation((event: string, cb: () => void) => {
      if (event === 'onRewardedVideoAdDismissed') dismissedCallback = cb
      return Promise.resolve(mockListenerHandle())
    })
    mockShowRewardVideoAd.mockImplementation(() => {
      queueMicrotask(() => dismissedCallback?.())
      return new Promise(() => {})
    })

    const outcome = await showRewardedPredictionAd('user-1')

    expect(outcome).toEqual({ status: 'dismissed_without_reward' })
  })

  it('resolves "failed_to_load" when prepareRewardVideoAd rejects, never calling showRewardVideoAd', async () => {
    mockIsNativePlatform.mockReturnValue(true)
    mockNativePlatform.mockReturnValue('ios')
    mockPrepareRewardVideoAd.mockRejectedValue(new Error('No fill'))

    const outcome = await showRewardedPredictionAd('user-1')

    expect(outcome).toEqual({ status: 'failed_to_load', message: 'No fill' })
    expect(mockShowRewardVideoAd).not.toHaveBeenCalled()
  })

  it('resolves "failed_to_show" when the FailedToShow event fires', async () => {
    mockIsNativePlatform.mockReturnValue(true)
    mockNativePlatform.mockReturnValue('android')
    mockPrepareRewardVideoAd.mockResolvedValue({ adUnitId: 'test' })
    let failedCallback: ((error: { message: string }) => void) | undefined
    mockAddListener.mockImplementation((event: string, cb: (arg: unknown) => void) => {
      if (event === 'onRewardedVideoAdFailedToShow') failedCallback = cb as typeof failedCallback
      return Promise.resolve(mockListenerHandle())
    })
    mockShowRewardVideoAd.mockImplementation(() => {
      queueMicrotask(() => failedCallback?.({ message: 'Ad expired' }))
      return new Promise(() => {})
    })

    const outcome = await showRewardedPredictionAd('user-1')

    expect(outcome).toEqual({ status: 'failed_to_show', message: 'Ad expired' })
  })

  it('uses Google test ad unit IDs when no production ad unit ID is configured', async () => {
    mockIsNativePlatform.mockReturnValue(true)
    mockNativePlatform.mockReturnValue('android')
    mockPrepareRewardVideoAd.mockResolvedValue({ adUnitId: 'test' })
    mockAddListener.mockImplementation(() => Promise.resolve(mockListenerHandle()))
    mockShowRewardVideoAd.mockImplementation(() => new Promise(() => {}))

    void showRewardedPredictionAd('user-1')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mockPrepareRewardVideoAd).toHaveBeenCalledWith(
      expect.objectContaining({ adId: 'ca-app-pub-3940256099942544/5224354917', isTesting: true }),
    )
  })
})
