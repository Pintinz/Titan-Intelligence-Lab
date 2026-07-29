import { motion } from 'framer-motion'

/**
 * Premium on-brand SVG illustration — extends the real TitanIQ brand mark (public/favicon.svg,
 * public/pwa-icon.svg: a graph-node network in blue/amber/white on dark) into a richer hero-scale
 * network rather than reusing the generic unrelated Vite-template graphic still sitting unused at
 * src/assets/hero.png. Pure CSS-variable colors so it themes correctly in dark/light/high-contrast.
 */
const NODES = [
  { id: 'a', x: 60, y: 140, r: 7, color: 'var(--color-accent-primary)' },
  { id: 'b', x: 180, y: 60, r: 9, color: 'var(--color-accent-primary)' },
  { id: 'c', x: 300, y: 110, r: 6, color: 'var(--color-accent-secondary)' },
  { id: 'd', x: 220, y: 220, r: 8, color: 'var(--color-text-primary)' },
  { id: 'e', x: 90, y: 260, r: 5, color: 'var(--color-confidence-high)' },
  { id: 'f', x: 340, y: 220, r: 6, color: 'var(--color-accent-primary)' },
  { id: 'g', x: 150, y: 190, r: 4, color: 'var(--color-text-secondary)' },
]

const EDGES: Array<[string, string]> = [
  ['a', 'b'],
  ['b', 'c'],
  ['b', 'd'],
  ['a', 'e'],
  ['d', 'e'],
  ['d', 'f'],
  ['c', 'f'],
  ['g', 'd'],
  ['g', 'a'],
]

export function AiNetworkIllustration({ className }: { className?: string }) {
  const byId = Object.fromEntries(NODES.map((n) => [n.id, n]))

  return (
    <svg viewBox="0 0 400 320" className={className} role="img" aria-label="AI knowledge network illustration">
      <g stroke="var(--color-border-strong)" strokeWidth={1} opacity={0.5}>
        {EDGES.map(([from, to], i) => {
          const a = byId[from]
          const b = byId[to]
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
        })}
      </g>
      <g stroke="var(--color-accent-primary)" strokeWidth={1.5} opacity={0.7}>
        {[EDGES[1], EDGES[4]].map(([from, to], i) => {
          const a = byId[from]
          const b = byId[to]
          return (
            <motion.line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              strokeDasharray="4 6"
              animate={{ strokeDashoffset: [0, -20] }}
              transition={{ duration: 2.5, repeat: Infinity, ease: 'linear' }}
            />
          )
        })}
      </g>
      {NODES.map((node, i) => (
        <motion.circle
          key={node.id}
          cx={node.x}
          cy={node.y}
          r={node.r}
          fill={node.color}
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: i * 0.06 }}
        />
      ))}
    </svg>
  )
}
