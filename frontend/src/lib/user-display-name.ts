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

/** Real local-clock greeting band — 05:00-11:59 morning, 12:00-17:59 afternoon, everything else
 * (18:00-04:59) evening. Never "good night", per product direction. */
export function getTimeAwareGreeting(now: Date = new Date()): string {
  const hour = now.getHours()
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 18) return 'Good afternoon'
  return 'Good evening'
}
