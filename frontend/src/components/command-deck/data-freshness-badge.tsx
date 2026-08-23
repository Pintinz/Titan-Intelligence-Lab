import type { DataFreshness } from '@/lib/hooks/use-data-freshness'

/** A small status dot + label — reused wherever a page reports real sync freshness. Never renders
 * "Live" (this reflects batch sync recency, not a streaming connection) and never invents a value
 * while `status === 'loading'`/`'unavailable'`. */
export function DataFreshnessBadge({ freshness }: { freshness: DataFreshness }) {
  if (freshness.status === 'loading') return null
  const tone =
    freshness.status === 'stale' ? 'var(--cd-negative)' : freshness.status === 'fresh' ? 'var(--cd-positive)' : 'var(--cd-text-muted)'
  return (
    <span className="inline-flex items-center gap-1.5 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: tone }}>
      <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: tone }} />
      {freshness.label}
    </span>
  )
}
