import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Section } from './section-primitives'
import type { PublicKnowledgeGraphPreviewDto } from '@/lib/api/types'

const typeColor: Record<string, string> = {
  team: 'var(--color-accent-primary)',
  competition: 'var(--color-premium)',
  venue: 'var(--color-text-muted)',
  player: 'var(--color-accent-secondary)',
  match: 'var(--color-confidence-high)',
  sport: 'var(--color-text-secondary)',
  country: 'var(--color-border-strong)',
  statistics: 'var(--color-confidence-medium)',
}

const VIEWBOX = { w: 480, h: 260 }
const CENTER = { x: VIEWBOX.w / 2, y: VIEWBOX.h / 2 }
const RADIUS = 90

/**
 * A real neighborhood around one genuinely high-connectivity node from `knowledge-graph-preview` —
 * never a fabricated relationship. Node/edge counts (and how many neighbors render) vary run to
 * run with real graph state, so layout is computed (radial around the center node), not fixed
 * positions like the old five-node illustration.
 */
export function KnowledgeGraphSection({
  loading,
  preview,
}: {
  loading: boolean
  preview: PublicKnowledgeGraphPreviewDto | null
}) {
  const entity = preview?.preview_entity

  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
        <div>
          <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
            Knowledge Graph
          </p>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-text-primary lg:text-3xl">
            Every prediction reasons over relationships, not just stats
          </h2>
          <p className="mt-3 max-w-md text-base text-text-secondary">
            Teams, players, venues, and competitions are connected in a living graph — rivalries,
            venue effects, and squad relationships all feed into a prediction's evidence.
          </p>
          {preview && (
            <p className="mt-4 text-sm text-text-secondary">
              {preview.node_count.toLocaleString()} entities · {preview.edge_count.toLocaleString()} relationships
              tracked right now.
            </p>
          )}
          <Link
            to="/signup"
            className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-accent-primary hover:text-accent-primary-hover"
          >
            Explore the Knowledge Graph <ArrowRight className="size-4" />
          </Link>
        </div>

        <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
          {loading ? (
            <div className="h-[250px] animate-pulse rounded-md bg-bg-secondary" />
          ) : entity ? (
            <KgPreviewGraph entity={entity} />
          ) : (
            <div className="flex h-[250px] flex-col items-center justify-center text-center">
              <p className="text-sm text-text-secondary">
                No connected entity to preview yet — the graph is still building coverage.
              </p>
            </div>
          )}
        </div>
      </div>
    </Section>
  )
}

function KgPreviewGraph({ entity }: { entity: NonNullable<PublicKnowledgeGraphPreviewDto['preview_entity']> }) {
  const neighbors = entity.neighbors.slice(0, 10)
  const positions = new Map<string, { x: number; y: number }>()
  positions.set(entity.node.id, CENTER)
  neighbors.forEach((n, i) => {
    const angle = (i / neighbors.length) * 2 * Math.PI - Math.PI / 2
    positions.set(n.id, { x: CENTER.x + RADIUS * Math.cos(angle), y: CENTER.y + RADIUS * Math.sin(angle) })
  })

  return (
    <svg viewBox={`0 0 ${VIEWBOX.w} ${VIEWBOX.h}`} className="h-auto w-full" role="img" aria-label="Live knowledge graph preview">
      {entity.relationships.map((edge, i) => {
        const from = positions.get(edge.from)
        const to = positions.get(edge.to)
        if (!from || !to) return null
        return <line key={i} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="var(--color-border-strong)" strokeWidth={1} />
      })}
      {[entity.node, ...neighbors].map((node) => {
        const pos = positions.get(node.id)
        if (!pos) return null
        return (
          <g key={node.id}>
            <circle cx={pos.x} cy={pos.y} r={node.id === entity.node.id ? 9 : 6} fill={typeColor[node.type] ?? 'var(--color-text-muted)'} />
            <text x={pos.x} y={pos.y - 14} textAnchor="middle" fontSize={10} fill="var(--color-text-secondary)" fontFamily="var(--font-body)">
              {node.type}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
