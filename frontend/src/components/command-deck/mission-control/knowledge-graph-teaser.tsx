import { useQuery } from '@tanstack/react-query'
import { Waypoints } from 'lucide-react'
import { publicApi } from '@/lib/api/public'
import { CDButton } from '../primitives/button'
import { domainTint } from '../primitives/domain'

/**
 * Knowledge Graph — a compact entry point, not another generic section. `node_count`/`edge_count`
 * are real (the already-optimized `knowledge-graph-preview` endpoint — its own N+1 query was fixed
 * this same session) — never the hardcoded example figures the brief explicitly warns against.
 */
export function KnowledgeGraphTeaser() {
  const query = useQuery({ queryKey: ['public', 'knowledge-graph-preview', 'mission-control'], queryFn: () => publicApi.knowledgeGraphPreview() })

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 backdrop-blur-md"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div
        className="pointer-events-none absolute -bottom-16 -right-16 h-56 w-56 rounded-full opacity-50"
        style={{ background: `radial-gradient(circle, ${domainTint('knowledge-graph', 22)} 0%, transparent 70%)` }}
        aria-hidden="true"
      />
      <div className="relative flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span
            className="flex size-9 shrink-0 items-center justify-center rounded-[var(--cd-radius-md)]"
            style={{ backgroundColor: domainTint('knowledge-graph', 14), color: 'var(--cd-domain-knowledge-graph)', boxShadow: `0 0 0 1px ${domainTint('knowledge-graph', 32)} inset` }}
            aria-hidden="true"
          >
            <Waypoints className="size-4" />
          </span>
          <div>
            <h3 className="font-[var(--cd-font-display)] text-[17px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>Knowledge Graph</h3>
            <p className="mt-0.5 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>Explore the relationships behind the signal.</p>
          </div>
        </div>
        <CDButton variant="secondary" size="sm" href="/app/graph">Explore Graph</CDButton>
      </div>

      <div className="relative mt-4 flex items-center gap-6 border-t pt-3.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <Stat label="Entities" value={query.data?.node_count} />
        <Stat label="Relationships" value={query.data?.edge_count} />
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      {value === undefined ? (
        <span className="inline-block h-6 w-14 animate-pulse rounded" style={{ backgroundColor: 'var(--cd-surface-3)' }} />
      ) : (
        <span className="font-[var(--cd-font-tabular)] text-[20px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>{value.toLocaleString()}</span>
      )}
      <p className="font-[var(--cd-font-telemetry)] text-[9.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>{label}</p>
    </div>
  )
}
