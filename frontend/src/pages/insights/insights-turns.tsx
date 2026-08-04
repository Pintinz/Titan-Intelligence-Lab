import { useQuery } from '@tanstack/react-query'
import { History, GitCompare, MessageCircle, Waypoints, Info } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { intelligenceApi } from '@/lib/api/intelligence'
import { graphApi } from '@/lib/api/graph'
import { ApiError } from '@/lib/api/client'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinityBadge } from '@/components/infinity/primitives/badge'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityConfidenceRing } from '@/components/infinity/charts/confidence-ring'
import { InfinityConfidenceTelemetry } from '@/components/infinity/confidence-telemetry'
import { InfinityPredictionEvolution } from '@/components/infinity/charts/prediction-evolution'
import { InfinityEvidenceExplorer } from '@/components/infinity/evidence-explorer'
import type { PinnedEntity } from './insights-page'

function kgNodeType(kind: PinnedEntity['kind']): string {
  return kind === 'team' ? 'team' : 'match'
}

// -- Turn: History --------------------------------------------------------------------------

export function HistoryTurn({
  entity,
  selectedIds,
  onToggleSelect,
  onFocusPrediction,
}: {
  entity: PinnedEntity
  selectedIds: string[]
  onToggleSelect: (id: string) => void
  onFocusPrediction: (id: string) => void
}) {
  const historyQuery = useQuery({
    queryKey: ['predictions', 'history', entity.id],
    queryFn: () => predictionsApi.history(entity.id),
  })

  useRealtimeInvalidate('predictions', [['predictions', 'history', entity.id]], `subject_ref=eq.${entity.id}`)

  return (
    <InfinityPanel tone="var(--infinity-domain-predictions)">
      <div className="flex items-center gap-2">
        <History className="size-3.5 text-infinity-domain-predictions" aria-hidden="true" />
        <InfinityLabel>Prediction history — {entity.label}</InfinityLabel>
      </div>

      <div className="mt-3">
        {historyQuery.isPending && (
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, i) => (
              <InfinitySkeleton key={i} className="h-12" />
            ))}
          </div>
        )}
        {historyQuery.isError && <ErrorState error={historyQuery.error} onRetry={() => void historyQuery.refetch()} />}
        {historyQuery.data && historyQuery.data.length === 0 && (
          <InfinityEmptyState
            icon={History}
            title="No predictions yet"
            description={`TitanIQ hasn't generated a prediction for ${entity.label} yet.`}
          />
        )}
        {historyQuery.data && historyQuery.data.length > 0 && (
          <ul className="space-y-1.5">
            {historyQuery.data.map((prediction) => (
              <li
                key={prediction.id}
                className="flex items-center gap-3 rounded-infinity-sm border border-infinity-border-hairline p-2.5"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(prediction.id)}
                  onChange={() => onToggleSelect(prediction.id)}
                  aria-label={`Select ${entity.label} — ${String(prediction.value)} for comparison`}
                  className="size-3.5 shrink-0 accent-[var(--infinity-signal)]"
                />
                <button
                  type="button"
                  className="flex flex-1 items-center justify-between gap-3 text-left"
                  onClick={() => onFocusPrediction(prediction.id)}
                >
                  <div className="min-w-0">
                    <p className="truncate font-infinity-telemetry text-[13px] font-medium text-infinity-text-primary">
                      {String(prediction.value)}
                    </p>
                    <p className="truncate font-infinity-mono text-[10px] text-infinity-text-muted">
                      {prediction.generated_at ? new Date(prediction.generated_at).toLocaleDateString() : 'undated'}
                    </p>
                  </div>
                  <InfinityConfidenceRing value={prediction.confidence_composite} size={32} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </InfinityPanel>
  )
}

// -- Turn: Compare ----------------------------------------------------------------------------

export function CompareTurn({
  predictionIds,
  labels,
  onFocusPrediction,
}: {
  predictionIds: string[]
  labels: Record<string, string>
  onFocusPrediction: (id: string) => void
}) {
  const compareQuery = useQuery({
    queryKey: ['predictions', 'compare', ...predictionIds],
    queryFn: () => predictionsApi.compare(predictionIds),
  })

  const chronological = [...(compareQuery.data ?? [])].sort((a, b) => {
    const ta = a.generated_at ? new Date(a.generated_at).getTime() : 0
    const tb = b.generated_at ? new Date(b.generated_at).getTime() : 0
    return ta - tb
  })

  return (
    <InfinityPanel tone="var(--infinity-signal)" glow>
      <div className="flex items-center gap-2">
        <GitCompare className="size-3.5 text-infinity-signal" aria-hidden="true" />
        <InfinityLabel tone="var(--infinity-signal)">Comparison — {predictionIds.length} predictions</InfinityLabel>
      </div>

      <div className="mt-3">
        {compareQuery.isPending && <InfinitySkeleton className="h-24" />}
        {compareQuery.isError && <ErrorState error={compareQuery.error} onRetry={() => void compareQuery.refetch()} />}
        {compareQuery.data && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="font-infinity-body text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">
                    <th className="pb-2 pr-4 font-medium">Subject</th>
                    <th className="pb-2 pr-4 font-medium">Value</th>
                    <th className="pb-2 pr-4 font-medium">Probability</th>
                    <th className="pb-2 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {compareQuery.data.map((p) => (
                    <tr key={p.id} className="border-t border-infinity-border-hairline">
                      <td className="py-2 pr-4 font-infinity-body text-[12px] text-infinity-text-secondary">
                        {labels[p.id] ?? p.subject_ref}
                      </td>
                      <td className="py-2 pr-4">
                        <button
                          type="button"
                          className="font-infinity-telemetry text-[13px] font-medium text-infinity-text-primary underline-offset-2 hover:underline"
                          onClick={() => onFocusPrediction(p.id)}
                        >
                          {String(p.value)}
                        </button>
                      </td>
                      <td className="py-2 pr-4 font-infinity-mono text-[12px] tabular-nums text-infinity-text-secondary">
                        {(p.probability * 100).toFixed(1)}%
                      </td>
                      <td className="py-2">
                        <InfinityConfidenceTelemetry probability={p.probability} confidence={p.confidence_composite} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {chronological.length >= 2 && (
              <div className="mt-4 border-t border-infinity-border-hairline pt-4">
                <InfinityLabel>Confidence over time</InfinityLabel>
                <div className="mt-2">
                  <InfinityPredictionEvolution
                    points={chronological.map((p) => ({
                      value: p.confidence_composite,
                      label: labels[p.id] ?? p.subject_ref,
                    }))}
                    width={480}
                    height={90}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </InfinityPanel>
  )
}

// -- Turn: Community pulse ---------------------------------------------------------------------

export function PulseTurn() {
  const communityQuery = useQuery({
    queryKey: ['intelligence', 'community-topics', 'top'],
    queryFn: () => intelligenceApi.communityTopics(),
  })

  const topTopics = [...(communityQuery.data ?? [])].sort((a, b) => b.post_count - a.post_count).slice(0, 5)
  const maxVolume = Math.max(1, ...topTopics.map((t) => t.post_count))

  return (
    <InfinityPanel tone="var(--infinity-domain-community)">
      <div className="flex items-center gap-2">
        <MessageCircle className="size-3.5 text-infinity-domain-community" aria-hidden="true" />
        <InfinityLabel tone="var(--infinity-domain-community)">Today's community pulse</InfinityLabel>
      </div>

      <div className="mt-3">
        {communityQuery.isPending && <InfinitySkeleton className="h-20" />}
        {communityQuery.isError && <ErrorState error={communityQuery.error} onRetry={() => void communityQuery.refetch()} />}
        {topTopics.length === 0 && !communityQuery.isPending && !communityQuery.isError && (
          <InfinityEmptyState icon={MessageCircle} title="No community signal yet" description="No tracked topics right now." />
        )}
        {topTopics.length > 0 && (
          <div className="space-y-2.5">
            {topTopics.map((topic) => (
              <div key={topic.id} className="flex items-center gap-3">
                <span className="w-36 shrink-0 truncate font-infinity-body text-[12px] text-infinity-text-primary">
                  {topic.topic_label}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-infinity-ground-2">
                  <div
                    className="h-full rounded-full bg-infinity-domain-community"
                    style={{ width: `${(topic.post_count / maxVolume) * 100}%` }}
                  />
                </div>
                <span className="w-14 shrink-0 text-right font-infinity-mono text-[11px] text-infinity-text-muted">
                  {topic.post_count.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </InfinityPanel>
  )
}

// -- Turn: Relationships ------------------------------------------------------------------------

export function RelationshipsTurn({ a, b }: { a: PinnedEntity; b: PinnedEntity }) {
  const nodeAQuery = useQuery({
    queryKey: ['graph', 'entity', kgNodeType(a.kind), a.id],
    queryFn: () => graphApi.getEntity(kgNodeType(a.kind), a.id),
    retry: false,
  })
  const nodeBQuery = useQuery({
    queryKey: ['graph', 'entity', kgNodeType(b.kind), b.id],
    queryFn: () => graphApi.getEntity(kgNodeType(b.kind), b.id),
    retry: false,
  })
  const pathQuery = useQuery({
    queryKey: ['graph', 'shortest-path', nodeAQuery.data?.id, nodeBQuery.data?.id],
    queryFn: () => graphApi.shortestPath(nodeAQuery.data!.id, nodeBQuery.data!.id, { max_depth: 4 }),
    enabled: !!nodeAQuery.data && !!nodeBQuery.data,
  })

  const notFound = (q: typeof nodeAQuery) => q.isError && q.error instanceof ApiError && q.error.status === 404
  const eitherNotFound = notFound(nodeAQuery) || notFound(nodeBQuery)
  const pending = nodeAQuery.isPending || nodeBQuery.isPending

  return (
    <InfinityPanel tone="var(--infinity-domain-knowledge-graph)">
      <div className="flex items-center gap-2">
        <Waypoints className="size-3.5 text-infinity-domain-knowledge-graph" aria-hidden="true" />
        <InfinityLabel tone="var(--infinity-domain-knowledge-graph)">
          How are {a.label} and {b.label} connected?
        </InfinityLabel>
      </div>

      <div className="mt-3">
        {pending && <InfinitySkeleton className="h-16" />}
        {eitherNotFound && (
          <InfinityEmptyState
            icon={Waypoints}
            title="Not yet linked in the Knowledge Graph"
            description="One or both of these hasn't been reconciled into TitanIQ's semantic graph yet."
          />
        )}
        {!pending && !eitherNotFound && pathQuery.isPending && <InfinitySkeleton className="h-16" />}
        {pathQuery.data && !pathQuery.data.meta.connected && (
          <InfinityEmptyState
            icon={Waypoints}
            title="No connection found"
            description={`${a.label} and ${b.label} aren't connected within the graph's search depth.`}
          />
        )}
        {pathQuery.data && pathQuery.data.meta.connected && (
          <ol className="flex flex-wrap items-center gap-2">
            {pathQuery.data.nodes.map((node, i) => (
              <li key={node.id} className="flex items-center gap-2">
                {i > 0 && <span className="text-infinity-text-muted">→</span>}
                <InfinityBadge domain="knowledge-graph">{node.entity_ref}</InfinityBadge>
              </li>
            ))}
          </ol>
        )}
      </div>
    </InfinityPanel>
  )
}

// -- Turn: honest routing note ------------------------------------------------------------------

export function NoteTurn({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-infinity-sm border border-dashed border-infinity-border-default p-3">
      <Info className="mt-0.5 size-3.5 shrink-0 text-infinity-text-muted" aria-hidden="true" />
      <p className="font-infinity-body text-[12px] text-infinity-text-secondary">{message}</p>
    </div>
  )
}

// -- Evidence panel (right rail) ----------------------------------------------------------------

export function EvidencePanel({ predictionId }: { predictionId: string }) {
  const query = useQuery({ queryKey: ['predictions', predictionId], queryFn: () => predictionsApi.get(predictionId) })

  if (query.isPending) {
    return (
      <div className="space-y-3">
        <InfinitySkeleton className="h-24" />
        <InfinitySkeleton className="h-40" />
      </div>
    )
  }
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  if (!query.data) return null

  return <InfinityEvidenceExplorer prediction={query.data} variant="compact" />
}
