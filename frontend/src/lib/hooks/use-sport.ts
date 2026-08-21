import { useParams } from 'react-router-dom'
import type { SportCode } from '@/lib/api/sports'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'

export interface SportMeta {
  slug: string
  code: SportCode
  label: string
}

// URL slugs use hyphens (table-tennis); the backend's SportCode uses underscores (table_tennis).
export const SPORT_SLUGS: SportMeta[] = [
  { slug: 'football', code: 'football', label: 'Football' },
  { slug: 'basketball', code: 'basketball', label: 'Basketball' },
  { slug: 'baseball', code: 'baseball', label: 'Baseball' },
  { slug: 'table-tennis', code: 'table_tennis', label: 'Table Tennis' },
]

/** Resolves the `:sport` route param to a validated SportCode + display label, or null if unknown.
 * Deliberately resolves ANY of the 4 sports (not just what `useAvailableSports` allows) — callers
 * that need real access control (e.g. `SportShell`) check role themselves so they can render an
 * honest "not available yet" state instead of a generic 404, which needs to know which real sport
 * was requested. */
export function useSportParam(): SportMeta | null {
  const { sport } = useParams<{ sport: string }>()
  return SPORT_SLUGS.find((s) => s.slug === sport) ?? null
}

/** Basketball/Baseball/Table Tennis are still under active development — real users only get
 * Football; every cross-sport surface (Mission Control, Live, AI Picks, the sport switcher, etc.)
 * should iterate this instead of the raw `SPORT_SLUGS` list, matching the same gate the backend
 * now enforces server-side (`sports_router.require_football_or_admin`) so a regular user's
 * dashboard never fires — and 404s against — requests for a sport they can't see. Administrators
 * get the full list so the team can keep building/QA-ing the other sports against the real API. */
export function useAvailableSports(): SportMeta[] {
  const profile = useAuthStore((s) => s.profile)
  const isAdmin = !!profile && isAtLeast(profile.role, 'administrator')
  return isAdmin ? SPORT_SLUGS : SPORT_SLUGS.filter((s) => s.code === 'football')
}
