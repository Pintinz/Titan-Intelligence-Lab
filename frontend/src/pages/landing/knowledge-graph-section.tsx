import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Section, IllustrativeTag } from './section-primitives'
import { KG_PREVIEW } from './sample-data'

// Fixed layout for a small, deterministic preview graph — the real Knowledge Graph Explorer
// (Phase 7) lays out arbitrary subgraphs; this is a five-node illustration, not that component.
const POSITIONS: Record<string, { x: number; y: number }> = {
  n1: { x: 200, y: 120 },
  n2: { x: 380, y: 120 },
  n3: { x: 290, y: 40 },
  n4: { x: 100, y: 60 },
  n5: { x: 200, y: 210 },
}

const typeColor: Record<string, string> = {
  team: 'var(--color-accent-primary)',
  competition: 'var(--color-premium)',
  venue: 'var(--color-text-muted)',
  player: 'var(--color-accent-secondary)',
}

export function KnowledgeGraphSection() {
  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
        <div>
          <div className="flex items-center gap-3">
            <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
              Knowledge Graph
            </p>
            <IllustrativeTag />
          </div>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-text-primary lg:text-3xl">
            Every prediction reasons over relationships, not just stats
          </h2>
          <p className="mt-3 max-w-md text-base text-text-secondary">
            Teams, players, venues, and competitions are connected in a living graph — rivalries,
            venue effects, and squad relationships all feed into a prediction's evidence, and every
            edge shown here can be traced back to why a specific pick was made.
          </p>
          <Link
            to="/signup"
            className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-accent-primary hover:text-accent-primary-hover"
          >
            Explore the Knowledge Graph <ArrowRight className="size-4" />
          </Link>
        </div>

        <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
          <svg viewBox="0 0 480 250" className="h-auto w-full" role="img" aria-label="Sample knowledge graph">
            {KG_PREVIEW.edges.map((edge) => {
              const from = POSITIONS[edge.from]
              const to = POSITIONS[edge.to]
              return (
                <line
                  key={`${edge.from}-${edge.to}`}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="var(--color-border-strong)"
                  strokeWidth={1}
                />
              )
            })}
            {KG_PREVIEW.nodes.map((node) => {
              const pos = POSITIONS[node.id]
              return (
                <g key={node.id}>
                  <circle cx={pos.x} cy={pos.y} r={7} fill={typeColor[node.type]} />
                  <text
                    x={pos.x}
                    y={pos.y - 14}
                    textAnchor="middle"
                    fontSize={11}
                    fill="var(--color-text-secondary)"
                    fontFamily="var(--font-body)"
                  >
                    {node.label}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      </div>
    </Section>
  )
}
