import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { graphApi } from '@/lib/api/graph'
import type { KgNodeDto } from '@/lib/api/types'

/** Right-rail entity inspector — Overview/Evidence/Similar/Timeline all read from graph_router.py
 * endpoints that had no frontend caller before Milestone 10B (context/similar/timeline). */
export function GraphEntityDetailPanel({ node, onSelectNode }: { node: KgNodeDto; onSelectNode: (node: KgNodeDto) => void }) {
  const contextQuery = useQuery({
    queryKey: ['graph', 'context', node.id],
    queryFn: () => graphApi.context(node.id, { depth: 1, max_nodes: 20 }),
  })
  const similarQuery = useQuery({
    queryKey: ['graph', 'similar', node.id, node.node_type],
    queryFn: () => graphApi.similar(node.id, node.node_type, { limit: 10 }),
  })
  const timelineQuery = useQuery({
    queryKey: ['graph', 'timeline', node.id],
    queryFn: () => graphApi.timeline(node.id),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{node.entity_ref}</CardTitle>
        <p className="text-xs uppercase tracking-wide text-text-muted">{node.node_type}</p>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="evidence">Evidence</TabsTrigger>
            <TabsTrigger value="similar">Similar</TabsTrigger>
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <KeyValueGrid data={node.attributes} />
          </TabsContent>

          <TabsContent value="evidence">
            {contextQuery.isLoading && <Skeleton className="h-24" />}
            {contextQuery.data && (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-text-secondary">{contextQuery.data.summary ?? 'No narrative summary available for this entity.'}</p>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Related entities</span>
                  {contextQuery.data.related.map((related) => (
                    <button
                      key={related.id}
                      type="button"
                      onClick={() => onSelectNode(related)}
                      className="rounded-md px-2 py-1 text-left text-sm text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
                    >
                      {related.entity_ref} <span className="text-xs text-text-muted">({related.node_type})</span>
                    </button>
                  ))}
                  {contextQuery.data.related.length === 0 && <p className="text-sm text-text-muted">No related entities recorded.</p>}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="similar">
            {similarQuery.isLoading && <Skeleton className="h-24" />}
            <div className="flex flex-col gap-1">
              {similarQuery.data?.map(({ node: similarNode, score }) => (
                <button
                  key={similarNode.id}
                  type="button"
                  onClick={() => onSelectNode(similarNode)}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 text-left text-sm text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
                >
                  {similarNode.entity_ref}
                  <Badge variant="neutral" className="font-mono">
                    {score.toFixed(2)}
                  </Badge>
                </button>
              ))}
              {similarQuery.data?.length === 0 && <p className="text-sm text-text-muted">No similar entities found.</p>}
            </div>
          </TabsContent>

          <TabsContent value="timeline">
            {timelineQuery.isLoading && <Skeleton className="h-24" />}
            <div className="flex flex-col gap-2">
              {timelineQuery.data?.map((edge, i) => (
                <div key={i} className="flex items-center justify-between border-b border-border-subtle py-1.5 text-sm last:border-0">
                  <span className="text-text-primary">{edge.edge_type}</span>
                  <span className="font-mono text-xs text-text-muted">
                    {typeof edge.attributes.valid_from === 'string' ? new Date(edge.attributes.valid_from).toLocaleDateString() : '—'}
                  </span>
                </div>
              ))}
              {timelineQuery.data?.length === 0 && <p className="text-sm text-text-muted">No temporal edge history for this entity.</p>}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
