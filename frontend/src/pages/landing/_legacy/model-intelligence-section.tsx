import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { MomentumHeatmap } from '@/components/domain/momentum-heatmap'
import { SAMPLE_MODEL_INTELLIGENCE, SAMPLE_MOMENTUM, SAMPLE_FEATURED_PREDICTION } from '@/pages/landing/sample-data'
import { transitionSlow } from '@/lib/motion'

export function ModelIntelligenceSection() {
  const { champion_model, status, model_agreement, calibration_status, expected_calibration_error, prediction_accuracy_30d, training_freshness_days } =
    SAMPLE_MODEL_INTELLIGENCE

  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="model-intelligence">
      <div className="mx-auto max-w-2xl text-center">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Model intelligence</span>
        <h2 className="mt-2 font-display text-3xl font-semibold text-text-primary">Behind every number, a governed model</h2>
        <p className="mt-3 text-text-secondary">
          Champion/challenger promotion, calibration monitoring, and drift detection — reported the
          same way the ML Platform reports it to signed-in analysts.
        </p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={transitionSlow}
        className="mt-10 grid gap-6 lg:grid-cols-[1fr_1fr]"
      >
        <div className="rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)]">
          <div className="flex items-center justify-between">
            <p className="font-mono text-sm text-text-primary">{champion_model}</p>
            <Badge variant="success">{status}</Badge>
          </div>
          <div className="mt-4">
            <KeyValueGrid
              data={{
                model_agreement,
                calibration_status,
                expected_calibration_error,
                prediction_accuracy_30d,
                training_freshness_days,
              }}
            />
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className="rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)]">
            <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Momentum, last 18 windows</span>
            <MomentumHeatmap values={SAMPLE_MOMENTUM} className="mt-3" />
          </div>
          <div className="rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)]">
            <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Top feature contributions</span>
            <p className="mt-2 text-sm text-text-secondary">{SAMPLE_FEATURED_PREDICTION.explanation.ai_explanation}</p>
          </div>
        </div>
      </motion.div>

      <p className="mt-6 text-center text-xs text-text-muted">
        Illustrative — reflects the real ML Platform's reporting shape, not live model metrics.
      </p>
    </section>
  )
}
