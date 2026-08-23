import { describe, expect, it } from 'vitest'
import { getDisplayNameFromEmail, getDisplayNameFromUser } from '@/lib/user-display-name'

describe('getDisplayNameFromEmail', () => {
  it('title-cases the local part of the email', () => {
    expect(getDisplayNameFromEmail('info.autotechub@gmail.com')).toBe('Info Autotechub')
  })

  it('returns null for a missing email', () => {
    expect(getDisplayNameFromEmail(null)).toBeNull()
    expect(getDisplayNameFromEmail(undefined)).toBeNull()
  })
})

describe('getDisplayNameFromUser', () => {
  it('uses the email-derived name for a plain email/password account', () => {
    const user = { email: 'info.autotechub@gmail.com', app_metadata: { provider: 'email' }, user_metadata: {} }
    expect(getDisplayNameFromUser(user)).toBe('Info Autotechub')
  })

  it('prefers the real Google name over the email-derived one', () => {
    const user = {
      email: 'info.autotechub@gmail.com',
      app_metadata: { provider: 'google' },
      user_metadata: { full_name: 'Jordan Rivera', name: 'jrivera' },
    }
    expect(getDisplayNameFromUser(user)).toBe('Jordan Rivera')
  })

  it('falls back through name then given_name when full_name is missing', () => {
    const user = { email: 'x@gmail.com', app_metadata: { provider: 'google' }, user_metadata: { given_name: 'Jordan' } }
    expect(getDisplayNameFromUser(user)).toBe('Jordan')
  })

  it('falls back to the email-derived name when a Google account has no usable metadata', () => {
    const user = { email: 'info.autotechub@gmail.com', app_metadata: { provider: 'google' }, user_metadata: {} }
    expect(getDisplayNameFromUser(user)).toBe('Info Autotechub')
  })

  it('returns null for no user at all', () => {
    expect(getDisplayNameFromUser(null)).toBeNull()
    expect(getDisplayNameFromUser(undefined)).toBeNull()
  })
})
