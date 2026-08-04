import { cn } from '@/lib/cn'

export type DomainKey =
  | 'football'
  | 'basketball'
  | 'baseball'
  | 'table-tennis'
  | 'predictions'
  | 'knowledge-graph'
  | 'learning'
  | 'news'
  | 'community'
  | 'operations'
  | 'infrastructure'
  | 'alerts'
  | 'security'

/** Maps a domain key to its Tailwind color-utility fragment (`infinity-football`, etc.) —
 * the single source of truth every domain-aware component should read from, so the
 * domain→hue mapping never drifts between components. */
export const DOMAIN_COLOR_VAR: Record<DomainKey, string> = {
  football: 'var(--infinity-domain-football)',
  basketball: 'var(--infinity-domain-basketball)',
  baseball: 'var(--infinity-domain-baseball)',
  'table-tennis': 'var(--infinity-domain-table-tennis)',
  predictions: 'var(--infinity-domain-predictions)',
  'knowledge-graph': 'var(--infinity-domain-knowledge-graph)',
  learning: 'var(--infinity-domain-learning)',
  news: 'var(--infinity-domain-news)',
  community: 'var(--infinity-domain-community)',
  operations: 'var(--infinity-domain-operations)',
  infrastructure: 'var(--infinity-domain-infrastructure)',
  alerts: 'var(--infinity-domain-alerts)',
  security: 'var(--infinity-domain-security)',
}

/** Broadcast lower-third style status/domain tag — a colored dot + uppercase tracked
 * label, never a filled pill (filled pills read as legacy-system chrome in this world). */
export function InfinityBadge({
  children,
  tone,
  domain,
  className,
}: {
  children: React.ReactNode
  tone?: string
  domain?: DomainKey
  className?: string
}) {
  const color = domain ? DOMAIN_COLOR_VAR[domain] : (tone ?? 'var(--infinity-text-muted)')
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-infinity-sm border px-1.5 py-0.5',
        'font-infinity-body text-[10px] font-semibold uppercase tracking-[0.06em]',
        className,
      )}
      style={{ color, borderColor: `${color}40`, backgroundColor: `${color}14` }}
    >
      <span aria-hidden="true" className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      {children}
    </span>
  )
}
