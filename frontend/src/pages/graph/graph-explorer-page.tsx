import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Waypoints, Route } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { KnowledgeGraphViewer } from '@/components/domain/knowledge-graph-viewer'
import { GraphEntityDetailPanel } from '@/components/domain/graph-entity-detail-panel'
import { graphApi } from '@/lib/api/graph'
import { toast } from '@/stores/toast-store'
import type { KgNodeDto } from '@/lib/api/types'

// Populated node types only (docs/ontology.md §1) — the rest are reserved for a future writer,
// so listing them here would return empty and misleadingly imply they're browsable today.
const NODE_TYPES = ['team', 'player', 'competition', 'venue', 'country', 'organization', 'provider'] as const

export default function GraphExplorerPage() {
  const [nodeType, setNodeType] = useState<string>('team')
  const [centerNode, setCenterNode] = useState<KgNodeDto | null>(null)
  const [pathTargetId, setPathTargetId] = useState<string>()
  const [pathResult, setPathResult] = useState<{ nodes: KgNodeDto[]; connected: boolean } | null>(null)
  const [findingPath, setFindingPath] = useState(false)

  const entitiesQuery = useQuery({
    queryKey: ['graph', 'entities', nodeType],
    queryFn: () => graphApi.listEntities(nodeType),
  })

  const neighborhoodQuery = useQuery({
    queryKey: ['graph', 'neighborhood', centerNode?.id],
    queryFn: () => graphApi.neighborhood(centerNode!.id, { depth: 1, max_nodes: 60 }),
    enabled: Boolean(centerNode),
  })

  async function handleFindPath() {
    if (!centerNode || !pathTargetId) return
    setFindingPath(true)
    setPathResult(null)
    try {
      const result = await graphApi.shortestPath(centerNode.id, pathTargetId)
      setPathResult({ nodes: result.nodes, connected: result.meta.connected })
      if (!result.meta.connected) toast.warning('No path found', 'These two entities are not connected within the search depth.')
    } catch (error) {
      toast.danger('Path lookup failed', error instanceof Error ? error.message : undefined)
    } finally {
      setFindingPath(false)
    }
  }

  return (
    <div data-dashboard-accent="kg" className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Knowledge Graph' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Knowledge Graph Explorer</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Browse by entity type, then select one to explore its neighborhood. Free-text search
          across the graph isn't available yet — there's no fuzzy-search capability behind it
          (see Known Limitations).
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Browse entities</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Select value={nodeType} onValueChange={setNodeType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {NODE_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="flex max-h-96 flex-col gap-1 overflow-y-auto">
              {entitiesQuery.isLoading && Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8" />)}
              {entitiesQuery.data?.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => setCenterNode(node)}
                  className="rounded-md px-2 py-1.5 text-left text-sm text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
                >
                  {node.entity_ref}
                </button>
              ))}
              {entitiesQuery.data?.length === 0 && <p className="px-2 text-sm text-text-muted">No entities of this type yet.</p>}
            </div>
          </CardContent>
        </Card>

        {centerNode && (
          <Card className="h-fit lg:col-start-1">
            <CardHeader>
              <CardTitle>Find shortest path</CardTitle>
              <p className="text-xs text-text-muted">From {centerNode.entity_ref} to another entity of this type.</p>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Select value={pathTargetId} onValueChange={setPathTargetId}>
                <SelectTrigger>
                  <SelectValue placeholder="Target entity" />
                </SelectTrigger>
                <SelectContent>
                  {entitiesQuery.data
                    ?.filter((n) => n.id !== centerNode.id)
                    .map((n) => (
                      <SelectItem key={n.id} value={n.id}>
                        {n.entity_ref}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <Button size="sm" variant="secondary" disabled={!pathTargetId} loading={findingPath} onClick={handleFindPath}>
                <Route className="h-3.5 w-3.5" aria-hidden="true" />
                Find path
              </Button>
              {pathResult && pathResult.connected && (
                <div className="flex flex-col gap-1 text-xs text-text-secondary">
                  {pathResult.nodes.map((n, i) => (
                    <span key={n.id}>
                      {i > 0 && '→ '}
                      {n.entity_ref}
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {!centerNode && (
          <EmptyState
            icon={<Waypoints className="h-6 w-6" />}
            title="Select an entity"
            description="Pick an entity from the list to visualize its neighborhood."
          />
        )}

        {centerNode && neighborhoodQuery.isLoading && <Skeleton className="h-[420px]" />}
        {centerNode && neighborhoodQuery.isError && (
          <ErrorState description="Could not load this neighborhood." onRetry={() => neighborhoodQuery.refetch()} />
        )}
        {centerNode && neighborhoodQuery.data && (
          <div className="flex flex-col gap-6">
            <KnowledgeGraphViewer
              centerNode={centerNode}
              neighbors={neighborhoodQuery.data.nodes.filter((n) => n.id !== centerNode.id)}
              edges={neighborhoodQuery.data.edges}
              onNodeClick={setCenterNode}
            />
            <GraphEntityDetailPanel node={centerNode} onSelectNode={setCenterNode} />
          </div>
        )}
      </div>
    </div>
  )
}
