import { motion } from 'framer-motion'
import { AnimatedCounter } from '@/components/domain/animated-counter'
import { SAMPLE_PLATFORM_STATS } from '@/pages/landing/sample-data'
import { staggerContainer, staggerItem } from '@/lib/motion'

export function PlatformStatisticsSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Platform intelligence, at scale</h2>
        <p className="mt-3 text-text-secondary">
          The same knowledge graph, feature store, and model registry every prediction draws from.
        </p>
      </div>

      <motion.div
        variants={staggerContainer}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, margin: '-80px' }}
        className="mt-12 grid grid-cols-2 gap-6 sm:grid-cols-3"
      >
        {SAMPLE_PLATFORM_STATS.map((stat) => (
          <motion.div
            key={stat.label}
            variants={staggerItem}
            className="rounded-lg border border-border-glass bg-bg-glass p-6 text-center backdrop-blur-[var(--blur-glass-sm)]"
          >
            <p className="font-mono text-3xl font-semibold text-text-primary">
              <AnimatedCounter value={stat.value} />
            </p>
            <p className="mt-1 text-sm text-text-secondary">{stat.label}</p>
          </motion.div>
        ))}
      </motion.div>
      <p className="mt-6 text-center text-xs text-text-muted">
        Illustrative — reflects platform capability and shape, not a live counter (every underlying
        metric requires a signed-in session to query).
      </p>
    </section>
  )
}
