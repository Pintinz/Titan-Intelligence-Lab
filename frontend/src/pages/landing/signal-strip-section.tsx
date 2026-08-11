import { Section } from './section-primitives'
import type { PublicPlatformSummaryDto } from '@/lib/api/types'

// Fixed capability facts (docs/architecture.md) — not usage/business metrics, never fabricated.
const CAPABILITIES = [
  { value: '9', label: 'Confidence factors scored on every prediction' },
  { value: '100%', label: 'Predictions shipped with a full explanation bundle' },
  { value: '6', label: 'Stages in the continuous learning loop' },
]

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="border-t-2 border-accent-primary pt-4">
      <span className="font-telemetry text-3xl font-medium tabular-nums text-text-primary lg:text-4xl">{value}</span>
      <p className="mt-2 text-sm text-text-secondary">{label}</p>
    </div>
  )
}

/**
 * "Real-Time Platform Signal Strip" (shape brief §9) — every count here is read straight off
 * `platform-summary`; nothing is shown unless the backend actually returned it. Loading renders a
 * skeleton rather than a guessed number.
 */
export function SignalStripSection({
  loading,
  summary,
}: {
  loading: boolean
  summary: PublicPlatformSummaryDto | null
}) {
  return (
    <Section className="border-b border-border-subtle py-10 lg:py-12">
      <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
        Platform Signal
      </p>
      <h2 className="mt-1 font-display text-xl font-semibold text-text-primary">What TitanIQ is tracking right now</h2>

      {loading || !summary ? (
        <dl className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded bg-bg-secondary" />
          ))}
        </dl>
      ) : (
        <>
          <dl className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
            <Stat value={String(summary.sports_covered)} label="Sports covered" />
            <Stat value={String(summary.competitions_tracked)} label="Competitions tracked" />
            <Stat value={String(summary.live_fixtures)} label="Live right now" />
            <Stat value={String(summary.today_fixtures)} label="Fixtures today" />
          </dl>
          <dl className="mt-6 grid grid-cols-2 gap-8 border-t border-border-subtle pt-6 lg:grid-cols-3">
            <Stat
              value={summary.published_predictions_sample.toLocaleString()}
              label={`Published in the last ${summary.published_predictions_sample_size.toLocaleString()} predictions`}
            />
            <Stat value={summary.knowledge_graph.node_count.toLocaleString()} label="Knowledge Graph entities" />
            <Stat value={summary.knowledge_graph.edge_count.toLocaleString()} label="Knowledge Graph relationships" />
          </dl>
          {summary.last_synced_at && (
            <p className="mt-4 text-xs text-text-muted">
              Data last synced {new Date(summary.last_synced_at).toLocaleString()}
            </p>
          )}
        </>
      )}

      <dl className="mt-10 grid grid-cols-1 gap-8 border-t border-border-subtle pt-8 sm:grid-cols-3">
        {CAPABILITIES.map((c) => (
          <Stat key={c.label} value={c.value} label={c.label} />
        ))}
      </dl>
    </Section>
  )
}
