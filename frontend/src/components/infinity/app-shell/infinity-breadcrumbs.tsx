import { useLocation } from 'react-router-dom'
import { ALL_NAV_ITEMS } from '@/components/layout/nav-config'
import { InfinityBreadcrumbs } from '@/components/infinity/nav/nav-primitives'

/**
 * Route-aware wrapper around the presentational `InfinityBreadcrumbs` (Phase 11.0).
 * Deliberately shallow: resolves only the current route's top-level `NAV_GROUPS` match
 * (longest `href` prefix), never fabricates sub-page crumbs (e.g. a specific match or
 * provider name) — those pages own their own detail titles, and inventing a deeper
 * trail here would mean guessing at structure that belongs to pages this phase doesn't
 * touch.
 */
export function InfinityAppBreadcrumbs() {
  const location = useLocation()
  const match = [...ALL_NAV_ITEMS]
    .filter((item) => location.pathname === item.href || location.pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]

  if (!match || match.href === '/app') return null

  return <InfinityBreadcrumbs items={['Home', match.label]} />
}
