import { motion } from 'framer-motion'

/** Abstract prediction/confidence illustration — concentric calibration arcs around a value node,
 * echoing the real ConfidenceRing component's visual language rather than a generic chart icon. */
export function PredictionEngineIllustration({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 320 320" className={className} role="img" aria-label="Prediction confidence illustration">
      {[140, 110, 80].map((r, i) => (
        <motion.circle
          key={r}
          cx={160}
          cy={160}
          r={r}
          fill="none"
          stroke="var(--color-border-default)"
          strokeWidth={1}
          opacity={0.5}
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.5 }}
          transition={{ duration: 0.5, delay: i * 0.1 }}
        />
      ))}
      <motion.circle
        cx={160}
        cy={160}
        r={80}
        fill="none"
        stroke="var(--color-accent-primary)"
        strokeWidth={4}
        strokeLinecap="round"
        strokeDasharray={2 * Math.PI * 80}
        transform="rotate(-90 160 160)"
        initial={{ strokeDashoffset: 2 * Math.PI * 80 }}
        animate={{ strokeDashoffset: 2 * Math.PI * 80 * 0.22 }}
        transition={{ duration: 1.2, ease: [0, 0, 0.2, 1] }}
      />
      <circle cx={160} cy={160} r={36} fill="var(--color-bg-elevated)" stroke="var(--color-border-strong)" strokeWidth={1} />
      <text x={160} y={168} textAnchor="middle" fill="var(--color-accent-primary)" className="font-mono" fontSize={22} fontWeight={600}>
        78%
      </text>
      {[
        { x: 260, y: 90, color: 'var(--color-accent-secondary)' },
        { x: 60, y: 230, color: 'var(--color-confidence-high)' },
        { x: 250, y: 250, color: 'var(--color-text-secondary)' },
      ].map((dot, i) => (
        <motion.circle
          key={i}
          cx={dot.x}
          cy={dot.y}
          r={5}
          fill={dot.color}
          initial={{ opacity: 0, y: dot.y + 8 }}
          animate={{ opacity: 1, y: dot.y }}
          transition={{ duration: 0.4, delay: 0.3 + i * 0.1 }}
        />
      ))}
    </svg>
  )
}
