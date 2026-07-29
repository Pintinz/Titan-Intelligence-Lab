import { motion } from 'framer-motion'

/** Denser node/edge illustration for Knowledge Graph showcase — same on-brand palette as the
 * AI network illustration, varied node sizes suggest entity importance/degree, matching the real
 * KnowledgeGraphViewer component's visual language (radial layout, thin stroke edges). */
const NODES = [
  { id: 'center', x: 200, y: 160, r: 12, color: 'var(--color-accent-primary)' },
  { id: 'n1', x: 110, y: 90, r: 6, color: 'var(--color-text-secondary)' },
  { id: 'n2', x: 290, y: 80, r: 7, color: 'var(--color-accent-secondary)' },
  { id: 'n3', x: 320, y: 190, r: 5, color: 'var(--color-text-secondary)' },
  { id: 'n4', x: 260, y: 260, r: 6, color: 'var(--color-confidence-high)' },
  { id: 'n5', x: 140, y: 250, r: 5, color: 'var(--color-text-secondary)' },
  { id: 'n6', x: 70, y: 180, r: 5, color: 'var(--color-accent-secondary)' },
  { id: 'n7', x: 340, y: 130, r: 4, color: 'var(--color-text-muted)' },
]

const EDGES: Array<[string, string]> = [
  ['center', 'n1'],
  ['center', 'n2'],
  ['center', 'n3'],
  ['center', 'n4'],
  ['center', 'n5'],
  ['center', 'n6'],
  ['n2', 'n7'],
  ['n1', 'n6'],
]

export function KnowledgeGraphIllustration({ className }: { className?: string }) {
  const byId = Object.fromEntries(NODES.map((n) => [n.id, n]))

  return (
    <svg viewBox="0 0 400 320" className={className} role="img" aria-label="Knowledge graph illustration">
      <g stroke="var(--color-border-strong)" strokeWidth={1} opacity={0.5}>
        {EDGES.map(([from, to], i) => {
          const a = byId[from]
          const b = byId[to]
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
        })}
      </g>
      <motion.circle
        cx={NODES[0].x}
        cy={NODES[0].y}
        r={NODES[0].r + 10}
        fill="none"
        stroke="var(--color-accent-primary)"
        strokeWidth={1}
        opacity={0.3}
        animate={{ r: [NODES[0].r + 6, NODES[0].r + 16, NODES[0].r + 6], opacity: [0.4, 0, 0.4] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'easeOut' }}
      />
      {NODES.map((node, i) => (
        <motion.circle
          key={node.id}
          cx={node.x}
          cy={node.y}
          r={node.r}
          fill={node.color}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: i * 0.05 }}
        />
      ))}
    </svg>
  )
}
