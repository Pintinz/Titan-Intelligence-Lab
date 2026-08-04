import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Share2, Search, Waypoints, Network } from 'lucide-react'
import { graphApi } from '@/lib/api/graph'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { OpsPageHeader, SectionCard, MetricTile } from '@/components/ops/ops-primitives'

const NODE_TYPES = ['team', 'player', 'competition', 'venue'] as const

export default function KnowledgeGraphAdminPage() {
  const [nodeType, setNodeType] = useState<(typeof NODE_TYPES)[number]>('team')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const statsQuery = useQuery({ queryKey: ['graph', 'statistics'], queryFn: () => graphApi.statistics() })
  const entitiesQuery = useQuery({
    queryKey: ['graph', 'entities', nodeType],
    queryFn: () => graphApi.listEntities(nodeType),
  })
  const contextQuery = useQuery({
    queryKey: ['graph', 'context', selectedNodeId],
    queryFn: () => graphApi.context(selectedNodeId!, { depth: 1, max_nodes: 25 }),
    enabled: !!selectedNodeId,
  })
  const neighborhoodQuery = useQuery({
    queryKey: ['graph', 'neighborhood', selectedNodeId],
    queryFn: () => graphApi.neighborhood(selectedNodeId!, { depth: 1, max_nodes: 25 }),
    enabled: !!selectedNodeId,
  })

  const stats = statsQuery.data

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Knowledge Graph"
        title="Knowledge Graph Administration"
        description="Entity growth, relationship health, and an interactive explorer for every node TitanIQ's intelligence is grounded in."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricTile icon={Network} label="Total nodes" value={statsQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((stats?.node_count as number | undefined) ?? '—')} />
        <MetricTile icon={Waypoints} label="Total edges" value={statsQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((stats?.edge_count as number | undefined) ?? '—')} />
        <MetricTile icon={Share2} label="Entity resolution accuracy" value={statsQuery.isPending ? <Skeleton className="h-6 w-8" /> : (typeof stats?.entity_resolution_accuracy === 'number' ? `${Math.round(stats.entity_resolution_accuracy * 100)}%` : '—')} />
        <MetricTile icon={Share2} label="Cache hit ratio" value={statsQuery.isPending ? <Skeleton className="h-6 w-8" /> : (typeof stats?.cache_hit_ratio === 'number' ? `${Math.round(stats.cache_hit_ratio * 100)}%` : '—')} />
      </div>

      {stats && (stats.nodes_by_type || stats.edges_by_type) ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {!!stats.nodes_by_type && Object.keys(stats.nodes_by_type as object).length > 0 && (
            <SectionCard title="Nodes by type">
              <dl className="space-y-2">
                {Object.entries(stats.nodes_by_type as Record<string, number>).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between text-sm">
                    <dt className="capitalize text-text-secondary">{type}</dt>
                    <dd className="font-mono tabular-nums text-text-primary">{count}</dd>
                  </div>
                ))}
              </dl>
            </SectionCard>
          )}
          {!!stats.edges_by_type && Object.keys(stats.edges_by_type as object).length > 0 && (
            <SectionCard title="Edges by type">
              <dl className="space-y-2">
                {Object.entries(stats.edges_by_type as Record<string, number>).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between text-sm">
                    <dt className="capitalize text-text-secondary">{type.replace(/_/g, ' ')}</dt>
                    <dd className="font-mono tabular-nums text-text-primary">{count}</dd>
                  </div>
                ))}
              </dl>
            </SectionCard>
          )}
        </div>
      ) : null}

      <SectionCard icon={Search} title="Graph explorer" description="Browse entities by type, then inspect a node's relationships and evidence context.">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="node-type">Entity type</Label>
            <Select value={nodeType} onValueChange={(v) => { setNodeType(v as typeof nodeType); setSelectedNodeId(null) }}>
              <SelectTrigger id="node-type" className="mt-1.5 w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                {NODE_TYPES.map((t) => (
                  <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {entitiesQuery.isPending && (
          <div className="grid gap-2 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
          </div>
        )}
        {entitiesQuery.isError && <ErrorState error={entitiesQuery.error} onRetry={() => void entitiesQuery.refetch()} />}
        {entitiesQuery.data && entitiesQuery.data.length === 0 && (
          <EmptyState variant="minimal" title={`No ${nodeType} nodes yet`} description="Nodes populate as sports and news data are ingested and reconciled into the graph." />
        )}
        {entitiesQuery.data && entitiesQuery.data.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-3">
            {entitiesQuery.data.slice(0, 30).map((node) => (
              <button
                key={node.id}
                type="button"
                onClick={() => setSelectedNodeId(node.id)}
                className={`truncate rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                  selectedNodeId === node.id
                    ? 'border-accent-primary bg-accent-primary-muted text-accent-primary'
                    : 'border-border-default text-text-secondary hover:border-border-strong hover:text-text-primary'
                }`}
              >
                {node.entity_ref}
              </button>
            ))}
          </div>
        )}

        {selectedNodeId && (
          <div className="mt-5 grid gap-4 border-t border-border-subtle pt-4 lg:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Context & evidence</p>
              {contextQuery.isPending && <Skeleton className="h-24" />}
              {contextQuery.isError && <ErrorState error={contextQuery.error} onRetry={() => void contextQuery.refetch()} />}
              {contextQuery.data && (
                <div className="space-y-2">
                  <p className="text-xs text-text-muted">
                    {Object.values(contextQuery.data.related_by_type).flat().length} related entities
                  </p>
                </div>
              )}
            </div>
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Neighborhood</p>
              {neighborhoodQuery.isPending && <Skeleton className="h-24" />}
              {neighborhoodQuery.isError && <ErrorState error={neighborhoodQuery.error} onRetry={() => void neighborhoodQuery.refetch()} />}
              {neighborhoodQuery.data && neighborhoodQuery.data.nodes.length === 0 && (
                <p className="text-sm text-text-muted">No directly connected nodes.</p>
              )}
              {neighborhoodQuery.data && neighborhoodQuery.data.nodes.length > 0 && (
                <ul className="space-y-1">
                  {neighborhoodQuery.data.nodes.slice(0, 8).map((n) => (
                    <li key={n.id} className="flex items-center justify-between rounded border border-border-subtle px-2 py-1.5 text-xs">
                      <span className="truncate text-text-primary">{n.entity_ref}</span>
                      <span className="shrink-0 text-text-muted capitalize">{n.node_type}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  )
}
