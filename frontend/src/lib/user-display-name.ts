/** Real authenticated email -> a human display name — never the raw address, never
 * "undefined"/"null". `local.part@domain` -> the local part, dots become spaces, each word
 * title-cased. Never infers anything from the domain. Returns null for a missing/empty email so
 * callers can fall back to an unaddressed greeting instead of rendering "null". */
export function getDisplayNameFromEmail(email: string | null | undefined): string | null {
  if (!email) return null
  const localPart = email.split('@')[0]?.trim()
  if (!localPart) return null
  const words = localPart.replace(/\./g, ' ').split(/\s+/).filter(Boolean)
  if (words.length === 0) return null
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()).join(' ')
}

/** Minimal shape this reads off a Supabase `User` — narrower than importing the real type so
 * callers can pass `session?.user` (or a test double) without a `@supabase/supabase-js` import. */
interface DisplayNameUser {
  email?: string | null
  app_metadata?: { provider?: string | null } | null
  user_metadata?: Record<string, unknown> | null
}

/** Real display name for the signed-in user, provider-aware. Google (and any other real OAuth
 * provider — anything that isn't Supabase's own "email" provider) hands back an actual name in
 * `user_metadata` (`full_name`, then `name`, then `given_name` — whichever the provider actually
 * populated), so that's shown verbatim rather than mangled from the address. Plain email/password
 * accounts have no such field — Supabase only ever collects email + password for those (see
 * `AuthFlow.handleSignup`) — so those fall back to the email-derived name, same as before. Null
 * only when there's truly nothing to show. */
export function getDisplayNameFromUser(user: DisplayNameUser | null | undefined): string | null {
  const provider = user?.app_metadata?.provider
  if (provider && provider !== 'email') {
    const metadata = user.user_metadata ?? {}
    const providerName = [metadata.full_name, metadata.name, metadata.given_name]
      .find((value): value is string => typeof value === 'string' && value.trim().length > 0)
    if (providerName) return providerName.trim()
  }
  return getDisplayNameFromEmail(user?.email)
}

/** Real local-clock greeting band — 05:00-11:59 morning, 12:00-17:59 afternoon, everything else
 * (18:00-04:59) evening. Never "good night", per product direction. */
export function getTimeAwareGreeting(now: Date = new Date()): string {
  const hour = now.getHours()
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 18) return 'Good afternoon'
  return 'Good evening'
}
