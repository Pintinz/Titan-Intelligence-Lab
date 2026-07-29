import { useParams } from 'react-router-dom'
import type { SportCode } from '@/lib/api/sports'

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

/** Resolves the `:sport` route param to a validated SportCode + display label, or null if unknown. */
export function useSportParam(): SportMeta | null {
  const { sport } = useParams<{ sport: string }>()
  return SPORT_SLUGS.find((s) => s.slug === sport) ?? null
}
