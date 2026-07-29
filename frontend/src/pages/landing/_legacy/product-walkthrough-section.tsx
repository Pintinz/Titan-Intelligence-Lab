import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Database, Waypoints, SlidersHorizontal, Cpu, Scale, Gauge, MessageSquareText, Trophy } from 'lucide-react'
import { AiNetworkIllustration } from '@/components/illustrations/ai-network-illustration'
import { KnowledgeGraphIllustration } from '@/components/illustrations/knowledge-graph-illustration'
import { PredictionEngineIllustration } from '@/components/illustrations/prediction-engine-illustration'
import { transitionFast } from '@/lib/motion'

const STEPS = [
  { icon: Database, title: 'Collect data', body: 'Fixtures, teams, players, and news are ingested from every configured provider.' },
  { icon: Waypoints, title: 'Knowledge graph', body: 'Entities and relationships are resolved into one canonical graph — teams, players, venues, competitions.', illustration: KnowledgeGraphIllustration },
  { icon: SlidersHorizontal, title: 'Feature engineering', body: 'Windowed statistics and graph-derived signals are computed into the feature store.' },
  { icon: Cpu, title: 'Machine learning', body: 'Champion/challenger models train against versioned datasets across every supported algorithm.', illustration: AiNetworkIllustration },
  { icon: Scale, title: 'Calibration', body: 'Raw model outputs are recalibrated (isotonic/Platt) so a 70% prediction wins roughly 70% of the time.' },
  { icon: Gauge, title: 'Confidence', body: 'A 10-factor confidence score is computed from data quality, agreement, and market conditions.' },
  { icon: MessageSquareText, title: 'Explainability', body: 'SHAP feature attributions and knowledge-graph evidence are attached to every prediction.' },
  { icon: Trophy, title: 'Prediction', body: 'A calibrated, explained, evidence-backed prediction is published to the platform.', illustration: PredictionEngineIllustration },
] as const

export function ProductWalkthroughSection() {
  const [active, setActive] = useState(0)
  const step = STEPS[active]
  const Illustration = 'illustration' in step ? step.illustration : null

  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="how-it-works">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">From raw data to explained prediction</h2>
        <p className="mt-3 text-text-secondary">Every prediction passes through the same eight stages — click a step to see what happens there.</p>
      </div>

      <div className="mt-10 flex flex-wrap justify-center gap-2">
        {STEPS.map((s, i) => (
          <button
            key={s.title}
            type="button"
            onClick={() => setActive(i)}
            aria-current={i === active}
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              i === active
                ? 'border-accent-primary bg-accent-primary-muted text-accent-primary'
                : 'border-border-default bg-bg-elevated text-text-secondary hover:text-text-primary'
            }`}
          >
            <s.icon className="h-3.5 w-3.5" aria-hidden="true" />
            {i + 1}. {s.title}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={transitionFast}
          className="mx-auto mt-8 grid max-w-3xl gap-6 rounded-2xl border border-border-glass bg-bg-glass p-8 backdrop-blur-[var(--blur-glass-md)] sm:grid-cols-[1fr_1.4fr]"
        >
          <div className="flex items-center justify-center rounded-lg bg-bg-secondary/50 p-4">
            {Illustration ? <Illustration className="w-full" /> : <step.icon className="h-16 w-16 text-accent-primary" aria-hidden="true" />}
          </div>
          <div>
            <span className="font-mono text-xs uppercase tracking-wide text-text-muted">Step {active + 1} of {STEPS.length}</span>
            <h3 className="mt-1 font-display text-xl font-semibold text-text-primary">{step.title}</h3>
            <p className="mt-2 text-sm text-text-secondary">{step.body}</p>
          </div>
        </motion.div>
      </AnimatePresence>
    </section>
  )
}
