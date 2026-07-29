import { motion } from 'framer-motion'
import { Card, CardContent } from '@/components/ui/card'
import { PredictionEngineIllustration } from '@/components/illustrations/prediction-engine-illustration'
import { KnowledgeGraphIllustration } from '@/components/illustrations/knowledge-graph-illustration'
import { AiNetworkIllustration } from '@/components/illustrations/ai-network-illustration'
import { transitionFast } from '@/lib/motion'

/**
 * Replaces fabricated "testimonials"/"customer logos" (no real customers/logos exist yet) with
 * real architecture facts as trust signals — every claim here is sourced from docs/ already
 * written for this product (docs/prediction_markets.md, docs/knowledge_graph.md, docs/ontology.md).
 */
const CALLOUTS = [
  {
    Illustration: PredictionEngineIllustration,
    title: 'Calibrated, not just ranked',
    body: 'Isotonic regression and Platt scaling recalibrate raw model probabilities so a 70% prediction wins roughly 70% of the time — not just orders outcomes correctly.',
  },
  {
    Illustration: AiNetworkIllustration,
    title: 'Every prediction is explainable',
    body: 'SHAP feature attributions and a 10-factor confidence breakdown ship with every prediction — no black-box score without a reason attached.',
  },
  {
    Illustration: KnowledgeGraphIllustration,
    title: 'Built on a real knowledge graph',
    body: '47 canonical entity types and a temporal edge model connect teams, players, competitions, and news into one queryable graph — not a flat stats table.',
  },
]

export function ArchitectureCallouts() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Under the hood</p>
        <h2 className="mt-2 font-display text-3xl font-semibold text-text-primary">Built like enterprise infrastructure</h2>
      </div>

      <div className="mt-12 grid gap-6 sm:grid-cols-3">
        {CALLOUTS.map(({ Illustration, title, body }) => (
          <motion.div key={title} whileHover={{ y: -4 }} transition={transitionFast}>
            <Card className="h-full overflow-hidden bg-bg-glass backdrop-blur-[var(--blur-glass-sm)] transition-shadow hover:shadow-[var(--shadow-elevation-2)]">
              <div className="border-b border-border-subtle bg-bg-secondary/50">
                <Illustration className="h-32 w-full" />
              </div>
              <CardContent className="flex flex-col gap-3 p-6">
                <h3 className="font-display text-base font-semibold text-text-primary">{title}</h3>
                <p className="text-sm text-text-secondary">{body}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
