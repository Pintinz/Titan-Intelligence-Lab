import { CDTelemetryValue } from '../primitives/telemetry'
import { CDStatusDot } from '../primitives/status'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '../primitives/domain'
import type { SystemStatusTone } from './mission-hero'

export interface OperationsMetric {
  label: string
  /** `null` while genuinely loading. `undefined` for a tile that intentionally has no numeric
   * value at all (System Health) — distinct from `null` so it never gets stuck showing a
   * permanent loading skeleton for a number that was never coming. */
  value: number | null | undefined
  description: string
  status?: { label: string; tone: SystemStatusTone | 'live' }
  /** Tints this tile's hover glow + label dot with a category hue — omitted for tiles with no
   * single real category (e.g. "Today's fixtures" spans every sport) or ones already carrying
   * their own status color (Live matches' `tone: 'live'` dot). */
  domain?: DomainKey
}

/**
 * AI Operations Overview — eight premium operational tiles, each a real number this page already
 * fetched elsewhere (no internal/engineering metric like Knowledge Graph node counts or raw
 * prediction-record counts — those don't help a user decide what to do next, per the brief).
 * "Trend"/sparkline are dropped rather than faked: no historical snapshot exists to derive a real
 * delta from, so a hover description stands in for "supporting stats" instead of an invented arrow.
 */
export function AiOperationsOverview({ metrics }: { metrics: OperationsMetric[] }) {
  return (
    <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
      {metrics.map((metric) => {
        const glow = metric.domain ? domainTint(metric.domain, 24) : 'var(--cd-accent-muted)'
        const dotColor = metric.domain ? CD_DOMAIN_COLOR_VAR[metric.domain] : null
        return (
        <div
          key={metric.label}
          title={metric.description}
          className="group relative overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
          style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
        >
          <div
            className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-[var(--cd-motion-base)] group-hover:opacity-100"
            style={{ background: `radial-gradient(120% 90% at 0% 0%, ${glow}, transparent 60%)` }}
            aria-hidden="true"
          />
          <div className="relative flex items-start justify-between gap-2">
            <p className="flex items-center gap-1.5 font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              {dotColor && <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: dotColor }} aria-hidden="true" />}
              {metric.label}
            </p>
            {metric.status && <CDStatusDot label={metric.status.label} tone={metric.status.tone} />}
          </div>
          <div className="relative mt-2 min-h-9">
            {metric.value === null && (
              <span className="inline-block h-9 w-12 animate-pulse rounded" style={{ backgroundColor: 'var(--cd-surface-3)' }} />
            )}
            {typeof metric.value === 'number' && <CDTelemetryValue value={metric.value} size="lg" />}
          </div>
          <p className="relative mt-1.5 line-clamp-1 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
            {metric.description}
          </p>
        </div>
        )
      })}
    </div>
  )
}
