import type { LucideIcon } from 'lucide-react'
import { Layers, Trophy, Radio, CalendarDays, TrendingUp, Share2, Network, Gauge, FileCheck2, RefreshCw } from 'lucide-react'
import { Section } from './section-primitives'
import type { PublicPlatformSummaryDto } from '@/lib/api/types'

// Fixed capability facts (docs/architecture.md) — not usage/business metrics, never fabricated.
const CAPABILITIES = [
  { icon: Gauge, value: '9', label: 'Confidence factors scored on every prediction' },
  { icon: FileCheck2, value: '100%', label: 'Predictions shipped with a full explanation bundle' },
  { icon: RefreshCw, value: '6', label: 'Stages in the continuous learning loop' },
]

function Stat({ icon: Icon, value, label }: { icon: LucideIcon; value: string; label: string }) {
  return (
    <div className="rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] p-4 backdrop-blur-[var(--li-glass-2-blur)]">
      <span className="flex size-8 items-center justify-center rounded-[var(--li-radius-sm)] border border-[var(--li-border)] bg-[var(--li-surface-elevated)] text-[var(--li-cyan)]">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <p className="mt-3 font-mono text-2xl font-bold tabular-nums text-[var(--li-text-primary)] lg:text-3xl">{value}</p>
      <p className="mt-1 text-xs text-[var(--li-text-secondary)]">{label}</p>
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
    <Section className="border-b border-[var(--li-border)] py-10 lg:py-12">
      <h2 className="text-xl font-semibold text-[var(--li-text-primary)]">What TitanIQ is tracking right now</h2>

      {loading || !summary ? (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-[var(--li-radius-md)] bg-[var(--li-surface)]" />
          ))}
        </div>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat icon={Layers} value={String(summary.sports_covered)} label="Sports covered" />
            <Stat icon={Trophy} value={String(summary.competitions_tracked)} label="Competitions tracked" />
            <Stat icon={Radio} value={String(summary.live_fixtures)} label="Live right now" />
            <Stat icon={CalendarDays} value={String(summary.today_fixtures)} label="Fixtures today" />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat
              icon={TrendingUp}
              value={summary.published_predictions_sample.toLocaleString()}
              label={`Published in the last ${summary.published_predictions_sample_size.toLocaleString()} predictions`}
            />
            <Stat icon={Share2} value={summary.knowledge_graph.node_count.toLocaleString()} label="Knowledge Graph entities" />
            <Stat icon={Network} value={summary.knowledge_graph.edge_count.toLocaleString()} label="Knowledge Graph relationships" />
          </div>
          {summary.last_synced_at && (
            <p className="mt-4 font-mono text-xs text-[var(--li-text-muted)]">
              Data last synced {new Date(summary.last_synced_at).toLocaleString()}
            </p>
          )}
        </>
      )}

      <div className="mt-8 grid grid-cols-1 gap-4 border-t border-[var(--li-border)] pt-8 sm:grid-cols-3">
        {CAPABILITIES.map((c) => (
          <Stat key={c.label} icon={c.icon} value={c.value} label={c.label} />
        ))}
      </div>
    </Section>
  )
}
