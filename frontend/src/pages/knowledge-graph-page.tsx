import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Network } from 'lucide-react'
import { graphApi } from '@/lib/api/graph'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

/**
 * Knowledge Graph Explorer — interactive discovery of entities, relationships,
 * and context. A real KG visualization would use D3 or Cytoscape; for now,
 * this is a text-based explorer backed by graphApi.getEntity() lookups. The
 * real graph UI is a follow-up feature (requires data-heavy visualization library).
 */
export default function KnowledgeGraphPage() {
  const [query, setQuery] = useState('')
  const [searches, setSearches] = useState<string[]>([])

  const kgQuery = useQuery({
    queryKey: ['kg', 'node', query],
    queryFn: async () => {
      if (!query.trim()) return null
      const [type, ref] = query.includes(':') ? query.split(':') : ['team', query]
      try {
        return await graphApi.getEntity(type.trim(), ref.trim())
      } catch {
        return null
      }
    },
    enabled: query.length > 0,
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim() && !searches.includes(query)) {
      setSearches([...searches, query])
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 lg:p-8">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Knowledge Graph
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">Explore entities and relationships</h1>
        <p className="mt-2 text-sm text-text-secondary">
          Search for teams, players, competitions, and venues to see their connected context in TitanIQ's knowledge graph.
        </p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <Input
          placeholder='Search (e.g., "team:Arsenal" or "player:Saka")'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1"
        />
        <button
          type="submit"
          className="flex items-center gap-1 rounded-md bg-accent-primary px-3 text-sm font-medium text-bg-primary hover:bg-accent-primary-hover"
        >
          <Search className="size-4" /> Search
        </button>
      </form>

      {kgQuery.isPending && (
        <Card className="p-5">
          <Skeleton className="h-32" />
        </Card>
      )}

      {kgQuery.isError && (
        <Card className="p-5">
          <ErrorState error={kgQuery.error} onRetry={() => void kgQuery.refetch()} />
        </Card>
      )}

      {kgQuery.data === null && query.length > 0 && !kgQuery.isPending && (
        <EmptyState
          icon={Network}
          title="No entity found"
          description={`No KG record for "${query}". Try "team:Arsenal" or "player:Saka".`}
        />
      )}

      {kgQuery.data && (
        <Card className="p-5">
          <div className="space-y-3">
            <div>
              <p className="text-xs text-text-muted">Entity type</p>
              <p className="font-display text-sm font-semibold text-text-primary">{kgQuery.data.node_type}</p>
            </div>
            <div>
              <p className="text-xs text-text-muted">Entity reference</p>
              <p className="font-mono text-sm text-text-secondary">{kgQuery.data.entity_ref}</p>
            </div>
            {Object.keys(kgQuery.data.attributes || {}).length > 0 && (
              <div>
                <p className="text-xs text-text-muted">Attributes</p>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  {Object.entries((kgQuery.data.attributes as Record<string, unknown>) || {}).map(([key, value]: [string, unknown]) => (
                    <div key={key}>
                      <dt className="font-medium text-text-muted">{key}</dt>
                      <dd className="text-text-secondary">{String(value ?? '')}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        </Card>
      )}

      {searches.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium text-text-primary">Recent searches</p>
          <div className="flex flex-wrap gap-2">
            {searches.map((s) => (
              <button
                key={s}
                onClick={() => setQuery(s)}
                className="rounded-full border border-border-default px-3 py-1 text-xs hover:bg-bg-secondary"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
