import { describe, expect, it, vi, beforeEach } from 'vitest'

const onAuthStateChangeMock = vi.fn()
const signOutMock = vi.fn().mockResolvedValue(undefined)

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      onAuthStateChange: onAuthStateChangeMock,
      signOut: signOutMock,
    },
  },
}))

vi.mock('@/lib/api/identity', () => ({
  identityApi: { me: vi.fn().mockResolvedValue({ id: 'user-1' }) },
}))

const clearSpy = vi.fn()
vi.mock('@/lib/query-client', () => ({
  queryClient: { clear: clearSpy },
}))

function fakeSession(userId: string) {
  return { user: { id: userId } } as never
}

describe('auth-store', () => {
  beforeEach(async () => {
    vi.resetModules()
    clearSpy.mockClear()
    onAuthStateChangeMock.mockClear()
    // Re-import so the module-level `supabase.auth.onAuthStateChange(...)` registration (and its
    // `lastUserId` closure state) runs fresh for each test.
    await import('./auth-store')
  })

  function listener() {
    return onAuthStateChangeMock.mock.calls[0][0] as (event: string, session: unknown) => void
  }

  it('clears the query cache on the very first sign-in — the module has no prior identity to compare against', () => {
    // Live bug (2026-08-23): React Query's cache is keyed by query shape, not by user
    // (['predictions', 'entitlement'] etc.), so switching accounts in the same tab without a full
    // reload kept serving the previous user's cached prediction credits/watchlist/alerts —
    // reported live as one user's exhausted credits appearing to "affect" another user. Every
    // identity transition (including the first) must invalidate anything cached under no identity.
    listener()('INITIAL_SESSION', fakeSession('user-1'))
    expect(clearSpy).toHaveBeenCalledTimes(1)
  })

  it('clears the query cache when the authenticated user id actually changes (sign-out then a different sign-in)', () => {
    listener()('INITIAL_SESSION', fakeSession('user-1'))
    clearSpy.mockClear()

    listener()('SIGNED_OUT', null)
    expect(clearSpy).toHaveBeenCalledTimes(1)

    clearSpy.mockClear()
    listener()('SIGNED_IN', fakeSession('user-2'))
    expect(clearSpy).toHaveBeenCalledTimes(1)
  })

  it('does NOT clear the query cache on a token refresh for the same user', () => {
    listener()('INITIAL_SESSION', fakeSession('user-1'))
    clearSpy.mockClear()

    listener()('TOKEN_REFRESHED', fakeSession('user-1'))

    expect(clearSpy).not.toHaveBeenCalled()
  })
})
