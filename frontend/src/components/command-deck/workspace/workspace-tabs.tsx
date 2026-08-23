import { useQuery, useQueries } from '@tanstack/react-query'
import { CircleCheck, TriangleAlert, GitCompare, Sparkles, Waypoints } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { graphApi } from '@/lib/api/graph'
import { ErrorState } from '@/components/ui/error-state'
import { ApiError } from '@/lib/api/client'
import { CDPanel, CDLabel } from '../primitives/panel'
import { CDConfidenceGauge } from '../primitives/gauge'
import { CDTelemetryValue } from '../primitives/telemetry'
import { PredictionLaboratory } from '../prediction-laboratory'
import { PredictionAccessExhaustedCard } from '../prediction-access-gate'
import { resolveOutcomeLabel, resolveVerdict, humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import type { PredictionMarketDto, PredictionSummaryDto, PredictionDto } from '@/lib/api/types'
import type { WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'

export const CANVAS_TABS = ['mission-brief', 'predictions', 'evidence', 'comparison', 'timeline', 'related', 'insights'] as const
export type CanvasTab = (typeof CANVAS_TABS)[number]

const TAB_LABELS: Record<CanvasTab, string> = {
  'mission-brief': 'Mission Brief',
  predictions: 'Predictions',
  evidence: 'Evidence',
  comparison: 'Comparison',
  timeline: 'Timeline',
  related: 'Related',
  insights: 'Decision Intelligence',
}

export function WorkspaceTabBar({ active, onChange, compareCount }: { active: CanvasTab; onChange: (tab: CanvasTab) => void; compareCount: number }) {
  return (
    <div className="-mx-1 flex gap-1 overflow-x-auto rounded-[var(--cd-radius-md)] border p-1" style={{ borderColor: 'var(--cd-border-default)' }}>
      {CANVAS_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          onClick={() => onChange(tab)}
          className="shrink-0 whitespace-nowrap rounded-[var(--cd-radius-sm)] px-3 py-1.5 font-[var(--cd-font-body)] text-[12.5px] font-medium transition-colors duration-[var(--cd-motion-snap)]"
          style={{ backgroundColor: active === tab ? 'var(--cd-accent-muted)' : 'transparent', color: active === tab ? 'var(--cd-accent)' : 'var(--cd-text-secondary)' }}
        >
          {TAB_LABELS[tab]}
          {tab === 'comparison' && compareCount > 0 ? ` (${compareCount})` : ''}
        </button>
      ))}
    </div>
  )
}

function skeletonBlock(h: string) {
  return <div className={`${h} animate-pulse rounded-[var(--cd-radius-md)] motion-reduce:animate-none`} style={{ backgroundColor: 'var(--cd-surface-2)' }} />
}

/** Descriptive loading state — states what's actually in flight rather than a bare pulse, and
 * never implies intelligence has already been generated while it's still loading. */
function LoadingState({ label, height = 'h-32' }: { label: string; height?: string }) {
  return (
    <div className="space-y-2">
      <p className="font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
      {skeletonBlock(height)}
    </div>
  )
}

/** Latest real Prediction per market for this subject — a pure client-side reduction over
 * `predictionsApi.history` (already-fetched real rows), never a fabricated "current" value. */
export function latestByMarket(history: PredictionSummaryDto[]): Map<string, PredictionSummaryDto> {
  const latest = new Map<string, PredictionSummaryDto>()
  for (const p of history) {
    const existing = latest.get(p.market_id)
    if (!existing || (p.generated_at ?? '') > (existing.generated_at ?? '')) latest.set(p.market_id, p)
  }
  return latest
}

// -- Mission Brief ---------------------------------------------------------------------------

export function MissionBriefTab({
  entity,
  history,
  markets,
  isLoading,
  newsCount,
  kgLinked,
  pinnedCount,
}: {
  entity: WorkspaceEntity
  history: PredictionSummaryDto[]
  markets: PredictionMarketDto[]
  isLoading: boolean
  newsCount: number | null
  kgLinked: boolean | null
  pinnedCount: number
}) {
  if (isLoading) return <LoadingState label="Analyzing fixture context…" height="h-40" />

  const generatedMarketIds = new Set(history.map((p) => p.market_id))
  const generatedCount = markets.filter((m) => generatedMarketIds.has(m.id)).length
  const latestTimestamp = history.reduce<string | null>((max, p) => (p.generated_at && (!max || p.generated_at > max) ? p.generated_at : max), null)

  return (
    <div className="space-y-4">
      <CDPanel>
        <CDLabel>Executive summary</CDLabel>
        <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Stat label="Prediction coverage" value={markets.length > 0 ? `${generatedCount}/${markets.length}` : '—'} />
          <Stat label="Workspace status" value={entity.kind === 'fixture' ? (generatedCount > 0 ? 'AI ready' : 'Coverage building') : 'Investigating'} />
          <Stat label="AI readiness" value={generatedCount > 0 ? 'Ready' : 'Pending'} />
          <Stat label="Pinned entities" value={String(pinnedCount)} />
          <Stat label="News signals" value={newsCount === null ? '—' : String(newsCount)} />
          <Stat label="Knowledge Graph" value={kgLinked === null ? '—' : kgLinked ? 'Linked' : 'Not yet linked'} />
        </dl>
        {latestTimestamp && (
          <p className="mt-4 border-t pt-3 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
            Latest intelligence generated {new Date(latestTimestamp).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
        )}
      </CDPanel>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </dt>
      <dd className="mt-0.5 font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
        {value}
      </dd>
    </div>
  )
}

// -- Predictions -------------------------------------------------------------------------------

/** One compact result card per generated market. Probability/confidence/status come straight off
 * `PredictionSummaryDto` (already fetched via history — no extra request); the full evidence
 * payload (feature drivers, distribution, evidence count) is only fetched once the user actually
 * opens the Evidence Inspector for a specific prediction, so this tab never fans out one request
 * per market just to populate a headline number. */
export function PredictionIntelligenceTab({
  entity,
  markets,
  history,
  homeTeam,
  awayTeam,
  onFocusPrediction,
  selectedMarketKey,
  onSelectMarket,
  onGenerateSelected,
  generating,
  generateError,
  compareSelectedIds,
  onToggleCompare,
}: {
  entity: WorkspaceEntity
  markets: PredictionMarketDto[]
  history: PredictionSummaryDto[]
  homeTeam?: TeamRef
  awayTeam?: TeamRef
  onFocusPrediction: (id: string) => void
  selectedMarketKey?: string | null
  onSelectMarket?: (marketKey: string) => void
  onGenerateSelected?: () => void
  generating?: boolean
  generateError?: unknown
  compareSelectedIds?: string[]
  onToggleCompare?: (predictionId: string, label: string) => void
}) {
  const latest = latestByMarket(history)
  const generated = markets.filter((m) => latest.has(m.id))
  const ungenerated = markets.filter((m) => !latest.has(m.id))

  /** Alternative probability and evidence count only exist on the full `PredictionDto`, not the
   * `PredictionSummaryDto` history already holds — a bounded fan-out (markets per fixture are a
   * small, fixed set, already proven cheap for a single card via the Evidence Inspector) rather
   * than fabricating these numbers or omitting them again. */
  const detailQueries = useQueries({
    queries: generated.map((m) => {
      const id = latest.get(m.id)!.id
      return { queryKey: ['predictions', id], queryFn: () => predictionsApi.get(id) }
    }),
  })
  const detailByMarketId = new Map(generated.map((m, i) => [m.id, detailQueries[i]?.data]))

  if (markets.length === 0 && history.length === 0) {
    return (
      <CDPanel>
        <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
          No markets configured for this sport yet.
        </p>
      </CDPanel>
    )
  }

  return (
    <div className="space-y-4">
      {generated.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {generated.map((market) => {
            const prediction = latest.get(market.id)!
            const verdict = homeTeam && awayTeam ? resolveVerdict(prediction.value, homeTeam, awayTeam) : { text: String(prediction.value), team: null }
            const compareChecked = compareSelectedIds?.includes(prediction.id) ?? false
            const detail = detailByMarketId.get(market.id)
            const alternative = detail
              ? Object.entries(detail.probability_distribution ?? {})
                  .filter(([key]) => key !== String(detail.value))
                  .sort(([, a], [, b]) => b - a)[0]
              : null
            const evidenceCount = detail ? detail.explanation.top_positive_features.length + detail.explanation.top_negative_features.length : null
            return (
              <div
                key={market.id}
                className="relative min-w-0 rounded-[var(--cd-radius-lg)] border p-4 transition-colors duration-[var(--cd-motion-snap)] hover:border-[var(--cd-accent)]"
                style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}
              >
                {onToggleCompare && (
                  <label className="absolute right-3 top-3 z-10 flex items-center gap-1" title="Add to comparison">
                    <input
                      type="checkbox"
                      checked={compareChecked}
                      onChange={() => onToggleCompare(prediction.id, market.name)}
                      aria-label={`Compare ${market.name}`}
                      className="size-3.5 accent-[var(--cd-accent)]"
                    />
                  </label>
                )}
                <button type="button" onClick={() => onFocusPrediction(prediction.id)} className="block w-full text-left">
                  <div className="flex items-start justify-between gap-3 pr-5">
                    <div className="min-w-0">
                      <p className="truncate font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                        {market.name}
                      </p>
                      <p className="mt-1 flex items-center gap-2 font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                        {verdict.team?.logoUrl && <img src={verdict.team.logoUrl} alt="" className="size-5 object-contain" loading="lazy" />}
                        {verdict.text}
                      </p>
                      <p className="mt-1 font-[var(--cd-font-tabular)] text-[12px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                        {(prediction.probability * 100).toFixed(1)}% probability
                      </p>
                      {alternative && (
                        <p className="mt-0.5 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                          Alternative — {resolveOutcomeLabel(alternative[0], homeTeam, awayTeam)} {(alternative[1] * 100).toFixed(0)}%
                        </p>
                      )}
                    </div>
                    <CDConfidenceGauge value={prediction.confidence_composite} size={56} />
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <p className="font-[var(--cd-font-body)] text-[11px] font-medium" style={{ color: 'var(--cd-accent)' }}>
                      View evidence →
                    </p>
                    {evidenceCount !== null && (
                      <span className="font-[var(--cd-font-tabular)] text-[10.5px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                        {evidenceCount} signal{evidenceCount === 1 ? '' : 's'}
                      </span>
                    )}
                  </div>
                </button>
              </div>
            )
          })}
        </div>
      )}

      {entity.kind === 'fixture' && onSelectMarket && onGenerateSelected && ungenerated.length > 0 && (
        <PredictionLaboratory
          markets={ungenerated}
          selectedMarketKey={selectedMarketKey ?? null}
          onSelect={onSelectMarket}
          onGenerate={onGenerateSelected}
          generating={!!generating}
          hasGenerated={false}
        />
      )}

      {entity.kind !== 'fixture' && ungenerated.length > 0 && (
        <CDPanel padding="tight">
          <p className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            {ungenerated.length} more market{ungenerated.length === 1 ? '' : 's'} have no prediction history for {entity.label} yet.
          </p>
        </CDPanel>
      )}

      {generateError != null &&
        (generateError instanceof ApiError && generateError.status === 402 && generateError.reasonCode === 'PREDICTION_CREDIT_REQUIRED' ? (
          <PredictionAccessExhaustedCard />
        ) : (
          <CDPanel padding="tight">
            <ErrorState error={generateError} />
          </CDPanel>
        ))}

      {markets.length > 0 && generated.length === 0 && entity.kind !== 'fixture' && (
        <CDPanel>
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
            TitanIQ hasn't generated a prediction for {entity.label} yet.
          </p>
        </CDPanel>
      )}
    </div>
  )
}

// -- Comparison ----------------------------------------------------------------------------------

export function ComparisonTab({
  selectedIds,
  labels,
  onFocusPrediction,
  onClearSelection,
}: {
  selectedIds: string[]
  labels: Record<string, string>
  onFocusPrediction: (id: string) => void
  onClearSelection: () => void
}) {
  const compareQuery = useQuery({
    queryKey: ['predictions', 'compare', ...selectedIds],
    queryFn: () => predictionsApi.compare(selectedIds),
    enabled: selectedIds.length >= 2,
  })

  if (selectedIds.length < 2) {
    return (
      <CDPanel>
        <div className="flex items-center gap-2">
          <GitCompare className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
            Select two or more predictions from the Predictions tab to compare them here.
          </p>
        </div>
      </CDPanel>
    )
  }

  return (
    <CDPanel accent>
      <div className="flex items-center justify-between gap-2">
        <CDLabel tone="accent">Comparing {selectedIds.length} predictions</CDLabel>
        <button type="button" onClick={onClearSelection} className="font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          Clear
        </button>
      </div>

      {compareQuery.isPending && <div className="mt-3"><LoadingState label="Comparing predictions…" height="h-24" /></div>}
      {compareQuery.isError && <div className="mt-3"><ErrorState error={compareQuery.error} onRetry={() => void compareQuery.refetch()} /></div>}
      {compareQuery.data && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
                <th className="pb-2 pr-4 font-medium">Subject</th>
                <th className="pb-2 pr-4 font-medium">Value</th>
                <th className="pb-2 pr-4 font-medium">Probability</th>
                <th className="pb-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {compareQuery.data.map((p) => (
                <tr key={p.id} className="border-t" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                  <td className="py-2.5 pr-4 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    {labels[p.id] ?? p.subject_ref}
                  </td>
                  <td className="py-2.5 pr-4">
                    <button type="button" onClick={() => onFocusPrediction(p.id)} className="font-[var(--cd-font-display)] text-[13px] font-semibold underline-offset-2 hover:underline" style={{ color: 'var(--cd-text-primary)' }}>
                      {String(p.value)}
                    </button>
                  </td>
                  <td className="py-2.5 pr-4 font-[var(--cd-font-tabular)] text-[12px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                    {(p.probability * 100).toFixed(1)}%
                  </td>
                  <td className="py-2.5">
                    <CDTelemetryValue value={Math.round(p.confidence_composite * 100)} unit="%" size="sm" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CDPanel>
  )
}

// -- Prediction Timeline ----------------------------------------------------------------------

/** Chronological, per-market prediction history. Deltas are plain computed facts — no backend
 * field names a change *reason*, so this never renders a causal label ("Injury Update" etc.); it
 * only ever states what changed, exactly as the shaped brief requires. */
export function PredictionTimelineTab({ history, markets, onFocusPrediction }: { history: PredictionSummaryDto[]; markets: PredictionMarketDto[]; onFocusPrediction: (id: string) => void }) {
  const marketName = new Map(markets.map((m) => [m.id, m.name]))
  const byMarket = new Map<string, PredictionSummaryDto[]>()
  for (const p of history) {
    const list = byMarket.get(p.market_id) ?? []
    list.push(p)
    byMarket.set(p.market_id, list)
  }
  for (const list of byMarket.values()) list.sort((a, b) => (a.generated_at ?? '').localeCompare(b.generated_at ?? ''))

  const entries = [...byMarket.entries()].filter(([, list]) => list.length > 0)

  if (entries.length === 0) {
    return (
      <CDPanel>
        <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
          No prediction history recorded yet.
        </p>
      </CDPanel>
    )
  }

  return (
    <div className="space-y-4">
      {entries.map(([marketId, list]) => (
        <CDPanel key={marketId} padding="tight">
          <CDLabel>{marketName.get(marketId) ?? 'Market'}</CDLabel>
          <ol className="mt-3 space-y-3">
            {list.map((p, i) => {
              const prev = list[i - 1]
              const confidenceDelta = prev ? Math.round((p.confidence_composite - prev.confidence_composite) * 100) : null
              const probabilityDelta = prev ? Math.round((p.probability - prev.probability) * 100) : null
              return (
                <li key={p.id} className="flex items-start gap-3 border-t pt-3 first:border-t-0 first:pt-0" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                  <span className="mt-1 size-1.5 shrink-0 rounded-full" style={{ backgroundColor: 'var(--cd-accent)' }} aria-hidden="true" />
                  <button type="button" onClick={() => onFocusPrediction(p.id)} className="min-w-0 flex-1 text-left">
                    <p className="font-[var(--cd-font-tabular)] text-[10.5px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                      {p.generated_at ? new Date(p.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'undated'}
                    </p>
                    <p className="mt-0.5 font-[var(--cd-font-display)] text-[13.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                      {String(p.value)} · {(p.probability * 100).toFixed(1)}%
                    </p>
                    {(confidenceDelta !== null || probabilityDelta !== null) && (
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                        {probabilityDelta !== null && probabilityDelta !== 0 && (
                          <span>
                            Probability {(prev!.probability * 100).toFixed(0)}% → {(p.probability * 100).toFixed(0)}%
                          </span>
                        )}
                        {confidenceDelta !== null && confidenceDelta !== 0 && (
                          <span style={{ color: confidenceDelta > 0 ? 'var(--cd-positive)' : 'var(--cd-negative)' }}>
                            Confidence {confidenceDelta > 0 ? '+' : ''}
                            {confidenceDelta}pts
                          </span>
                        )}
                        {confidenceDelta === 0 && probabilityDelta === 0 && <span>Prediction re-published, unchanged</span>}
                      </div>
                    )}
                  </button>
                </li>
              )
            })}
          </ol>
        </CDPanel>
      ))}
    </div>
  )
}

// -- Decision Intelligence (Insights) -----------------------------------------------------------

export function DecisionIntelligenceTab({ prediction, isLoading }: { prediction: PredictionDto | null; isLoading: boolean }) {
  if (isLoading) return <LoadingState label="Loading prediction…" height="h-40" />

  if (!prediction) {
    return (
      <CDPanel>
        <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
          Open a prediction from the Predictions tab to see its decision-support signals here.
        </p>
      </CDPanel>
    )
  }

  const stability = prediction.confidence.prediction_stability
  const risk = prediction.confidence.composite >= 0.75 ? 'Low' : prediction.confidence.composite >= 0.5 ? 'Moderate' : 'High'
  const alternatives = Object.entries(prediction.probability_distribution ?? {})
    .filter(([key]) => key !== String(prediction.value))
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3)

  return (
    <div className="space-y-4">
      <CDPanel>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Prediction stability" value={`${Math.round(stability * 100)}%`} />
          <Stat label="Risk level" value={risk} />
          <Stat label="Confidence" value={`${Math.round(prediction.confidence.composite * 100)}%`} />
          <Stat label="Evidence quality" value={`${Math.round(prediction.confidence.data_completeness * 100)}%`} />
        </dl>
      </CDPanel>

      {(prediction.explanation.top_positive_features.length > 0 || prediction.explanation.top_negative_features.length > 0) && (
        <CDPanel>
          <CDLabel>Most influential signals</CDLabel>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {prediction.explanation.top_positive_features.slice(0, 4).map(([key, contribution]) => (
              <li key={key} className="flex items-start gap-2">
                <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {humanizeFactorKey(key)}{' '}
                  <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-positive)' }}>
                    +{contribution.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
            {prediction.explanation.top_negative_features.slice(0, 4).map(([key, contribution]) => (
              <li key={key} className="flex items-start gap-2">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {humanizeFactorKey(key)}{' '}
                  <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-negative)' }}>
                    {contribution.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </CDPanel>
      )}

      {alternatives.length > 0 && (
        <CDPanel>
          <CDLabel>Alternative outcomes</CDLabel>
          <ul className="mt-3 space-y-2">
            {alternatives.map(([key, probability]) => (
              <li key={key} className="flex items-center justify-between font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                <span>{resolveOutcomeLabel(key)}</span>
                <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                  <Sparkles className="mr-1 inline size-3" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
                  {(probability * 100).toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        </CDPanel>
      )}
    </div>
  )
}

// -- Related Fixtures -----------------------------------------------------------------------

/**
 * RelatedFixturesTab — real graph-structural similarity (`/graph/similar`, Jaccard overlap of
 * shared graph neighbors — same teams/opponents/competition), never a statistical outcome-
 * similarity claim the backend doesn't make. Only meaningful for a fixture focus, since match
 * nodes are the only kind this similarity metric was built for in practice here; other kinds show
 * an honest explanation instead of a fabricated result.
 */
export function RelatedFixturesTab({ entity, onFocusFixture }: { entity: WorkspaceEntity; onFocusFixture: (fixture: { id: string; label: string; meta?: string; logoUrl?: string | null }) => void }) {
  const nodeQuery = useQuery({
    queryKey: ['graph', 'entity', 'match', entity.id],
    queryFn: () => graphApi.getEntity('match', entity.id),
    enabled: entity.kind === 'fixture',
    retry: false,
  })

  const similarQuery = useQuery({
    queryKey: ['graph', 'similar', nodeQuery.data?.id],
    queryFn: () => graphApi.similar(nodeQuery.data!.id, 'match', { limit: 8 }),
    enabled: !!nodeQuery.data,
  })

  const relatedIds = (similarQuery.data ?? []).map((r) => r.node.entity_ref)
  const fixtureQueries = useQueries({
    queries: relatedIds.map((id) => ({
      queryKey: ['sports', 'fixture', id],
      queryFn: () => sportsApi.getFixture(id),
      enabled: !!similarQuery.data,
    })),
  })

  if (entity.kind !== 'fixture') {
    return (
      <CDPanel>
        <div className="flex items-center gap-2">
          <Waypoints className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
            Related Fixtures is built from match-to-match Knowledge Graph similarity — focus a match to explore it.
          </p>
        </div>
      </CDPanel>
    )
  }

  if (nodeQuery.isPending || similarQuery.isPending) return <LoadingState label="Retrieving related fixtures…" height="h-32" />
  if (nodeQuery.isError) {
    return (
      <CDPanel>
        <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
          Not yet linked in the Knowledge Graph.
        </p>
      </CDPanel>
    )
  }
  if (similarQuery.isError) return <ErrorState error={similarQuery.error} onRetry={() => void similarQuery.refetch()} />

  const rows = (similarQuery.data ?? [])
    .map((r, i) => ({ score: r.score, fixture: fixtureQueries[i]?.data }))
    .filter((r) => !!r.fixture)

  if (rows.length === 0) {
    return (
      <CDPanel>
        <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
          No related fixtures found in the Knowledge Graph yet.
        </p>
      </CDPanel>
    )
  }

  return (
    <div className="space-y-3">
      <p className="font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
        Related through TitanIQ's Knowledge Graph — fixtures sharing teams, opponents, or competition context.
      </p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {rows.map(({ score, fixture }) => (
          <button
            key={fixture!.id}
            type="button"
            onClick={() =>
              onFocusFixture({ id: fixture!.id, label: `${fixture!.home_team.short_name} vs ${fixture!.away_team.short_name}`, meta: fixture!.competition_name })
            }
            className="flex items-center justify-between gap-3 rounded-[var(--cd-radius-md)] border p-3 text-left transition-colors duration-[var(--cd-motion-snap)] hover:border-[var(--cd-accent)]"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}
          >
            <div className="min-w-0">
              <p className="truncate font-[var(--cd-font-display)] text-[13px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                {fixture!.home_team.short_name} vs {fixture!.away_team.short_name}
              </p>
              <p className="truncate font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                {fixture!.competition_name}
              </p>
            </div>
            <span className="shrink-0 font-[var(--cd-font-tabular)] text-[10.5px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
              {Math.round(score * 100)}% overlap
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
