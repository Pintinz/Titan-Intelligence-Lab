import { SAMPLE_KG_CENTER, SAMPLE_KG_NEIGHBORS } from '@/pages/landing/sample-data'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

const NODE_COLOR: Record<string, string> = {
  Team: 'var(--tl-signal)',
  Player: 'var(--tl-violet)',
  Competition: 'var(--tl-amber)',
  Venue: 'var(--tl-ink-dim)',
  NewsEvent: 'var(--tl-crimson)',
}

/**
 * Knowledge Graph Preview — a small radar-style node map (telemetry aesthetic), not the full
 * force-directed Graph Explorer (that lives behind auth). Every relationship shown here is a real
 * edge type from the Knowledge Graph schema (PLAYS_FOR, COMPETES_IN, SCHEDULED_AT, RIVALS,
 * MENTIONS) — docs/knowledge_graph.md.
 */
export function KnowledgeGraphSection() {
  const radius = 130
  const positions = SAMPLE_KG_NEIGHBORS.map((_, i) => {
    const angle = (i / SAMPLE_KG_NEIGHBORS.length) * Math.PI * 2 - Math.PI / 2
    return { x: 150 + radius * Math.cos(angle), y: 150 + radius * Math.sin(angle) }
  })

  return (
    <Section className="pt-0">
      <SectionHeading
        eyebrow="Knowledge Graph Preview"
        title="Every prediction stands on a graph of context"
        description="Teams, players, competitions, venues, and news events connected in real time — the evidence layer behind every explanation."
        action={<IllustrativeTag />}
      />

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_1.1fr] lg:items-center">
        <svg viewBox="0 0 300 300" className="mx-auto w-full max-w-sm" role="img" aria-label="Knowledge graph preview centered on Arsenal">
          {positions.map((p, i) => (
            <line key={`edge-${i}`} x1="150" y1="150" x2={p.x} y2={p.y} stroke="var(--tl-steel-line-strong)" strokeWidth={1} />
          ))}
          {positions.map((p, i) => {
            const node = SAMPLE_KG_NEIGHBORS[i]
            return (
              <g key={node.id}>
                <circle cx={p.x} cy={p.y} r={7} fill={NODE_COLOR[node.node_type] ?? 'var(--tl-ink-dim)'} opacity={0.85} />
                <text x={p.x} y={p.y + 20} textAnchor="middle" fontSize="9" fill="var(--tl-ink-faint)" fontFamily="var(--tl-font-mono)">
                  {node.entity_ref}
                </text>
              </g>
            )
          })}
          <circle cx="150" cy="150" r="16" fill="var(--tl-carbon)" stroke="var(--tl-signal)" strokeWidth={2} />
          <text x="150" y="154" textAnchor="middle" fontSize="9" fontWeight={700} fill="var(--tl-ink)" fontFamily="var(--tl-font-mono)">
            {SAMPLE_KG_CENTER.entity_ref.slice(0, 3).toUpperCase()}
          </text>
        </svg>

        <ul className="flex flex-col gap-3">
          {[
            ['PLAYS_FOR', 'Bukayo Saka and Declan Rice both resolve to Arsenal as their current club.'],
            ['COMPETES_IN', 'Arsenal competes in the Premier League — standings and form flow from here.'],
            ['SCHEDULED_AT', 'Emirates Stadium links every home fixture to venue-specific historical performance.'],
            ['RIVALS', 'Manchester City is a resolved rival entity — head-to-head context is pulled automatically.'],
            ['MENTIONS', 'News events mention Arsenal directly, feeding sentiment and impact scoring.'],
          ].map(([edge, desc]) => (
            <li key={edge} className="flex gap-3 rounded-md p-3" style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)' }}>
              <span className="tl-mono shrink-0 text-[0.65rem]" style={{ color: 'var(--tl-signal)' }}>
                {edge}
              </span>
              <span className="text-xs" style={{ color: 'var(--tl-ink-dim)' }}>
                {desc}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  )
}
