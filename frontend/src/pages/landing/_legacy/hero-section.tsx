import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Radio } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AiNetworkIllustration } from '@/components/illustrations/ai-network-illustration'
import { SPORT_OPTIONS } from '@/lib/api/sports'
import { transitionSlow } from '@/lib/motion'

/** Real, citable product facts only — no invented usage/user counts (docs/ontology.md §2 for the
 * node-type count, ConfidenceBreakdownDto in lib/api/types.ts for the 10-factor model). */
const FACT_CHIPS = [
  `${SPORT_OPTIONS.length} sports covered`,
  '10-factor confidence model',
  'SHAP-based explainability',
  '47 knowledge graph entity types',
]

export function HeroSection() {
  return (
    <section className="relative overflow-hidden px-6 pb-24 pt-24 sm:pt-32">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
      />

      <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
        <div className="flex flex-col items-center gap-6 text-center lg:items-start lg:text-left">
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transitionSlow}
            className="rounded-full border border-border-glass bg-bg-glass px-3 py-1 font-mono text-xs uppercase tracking-[0.2em] text-text-muted backdrop-blur-[var(--blur-glass-sm)]"
          >
            Titan Intelligence Labs
          </motion.span>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitionSlow, delay: 0.05 }}
            className="font-display text-4xl font-semibold tracking-tight text-text-primary sm:text-6xl"
          >
            Sports intelligence,
            <br />
            <span className="bg-[image:var(--gradient-brand)] bg-clip-text text-transparent">
              calibrated and explained.
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitionSlow, delay: 0.1 }}
            className="max-w-xl text-lg text-text-secondary"
          >
            TitanIQ turns match, player, and knowledge-graph data into probability-calibrated
            predictions — every number traceable to the features and evidence behind it, across
            Football, Basketball, Baseball, and Table Tennis.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...transitionSlow, delay: 0.15 }}
            className="flex flex-wrap items-center justify-center gap-3 pt-2 lg:justify-start"
          >
            <Button asChild size="lg">
              <Link to="/signup">Explore the platform</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link to="/login">See live predictions</Link>
            </Button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ ...transitionSlow, delay: 0.25 }}
            className="flex flex-wrap items-center justify-center gap-2 pt-6 lg:justify-start"
          >
            {FACT_CHIPS.map((fact) => (
              <span
                key={fact}
                className="rounded-full border border-border-default bg-bg-elevated px-3 py-1 font-mono text-xs text-text-secondary"
              >
                {fact}
              </span>
            ))}
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ ...transitionSlow, delay: 0.2 }}
          className="relative mx-auto w-full max-w-md"
        >
          <div className="overflow-hidden rounded-2xl border border-border-glass bg-bg-glass-strong shadow-[var(--shadow-elevation-3)] backdrop-blur-[var(--blur-glass-md)]">
            <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
              <span className="font-mono text-xs uppercase tracking-wide text-text-muted">Live intelligence feed</span>
              <span className="flex items-center gap-1.5 text-xs text-danger">
                <Radio className="h-3 w-3 animate-pulse" aria-hidden="true" />
                Live
              </span>
            </div>
            <AiNetworkIllustration className="w-full" />
            <div className="flex flex-wrap gap-2 border-t border-border-subtle px-4 py-3">
              {SPORT_OPTIONS.map((sport, i) => (
                <span
                  key={sport.code}
                  className="flex items-center gap-1.5 rounded-full border border-border-default bg-bg-elevated px-2.5 py-1 font-mono text-[11px] text-text-secondary"
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full bg-accent-primary"
                    style={{ opacity: 0.5 + i * 0.15 }}
                    aria-hidden="true"
                  />
                  {sport.label}
                </span>
              ))}
            </div>
          </div>

          {/* Floating glass accent panels — purely decorative depth, no data claims made here */}
          <div
            aria-hidden="true"
            className="absolute -right-6 -top-6 hidden h-20 w-20 rounded-2xl border border-border-glass bg-bg-glass backdrop-blur-[var(--blur-glass-sm)] sm:block"
          />
          <div
            aria-hidden="true"
            className="absolute -bottom-8 -left-8 hidden h-24 w-24 rounded-full border border-border-glass bg-bg-glass backdrop-blur-[var(--blur-glass-sm)] sm:block"
          />
        </motion.div>
      </div>
    </section>
  )
}
