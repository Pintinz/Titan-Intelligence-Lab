import { Sparkles } from 'lucide-react'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { humanizeFactorKey } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { Section, SectionHeading } from './section-primitives'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

/**
 * "Ask Why" (shape brief §... explainability) — grounded in a real currently-published pick's
 * real evidence highlights when one exists. No freeform question-answering exists yet (that's a
 * future Insights milestone), so this stays a worked real example, not a fake chat composer.
 */
export function ExplainabilitySection({ pick }: { pick: PublicFeaturedIntelligenceDto | null }) {
  return (
    <Section className="border-b border-[var(--li-border)]">
      <SectionHeading
        title="Ask why, not just what"
        description="Every prediction can explain itself — the evidence behind it, its confidence factors, and what would need to change for the number to move."
      />

      <div className="mx-auto max-w-lg rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] p-5 shadow-[var(--li-shadow-card)] backdrop-blur-[var(--li-glass-2-blur)]">
        <div className="flex items-center gap-2 text-sm font-medium text-[var(--li-text-primary)]">
          <Sparkles className="size-4 text-[var(--li-cyan)]" aria-hidden="true" />
          Real example
        </div>
        {pick ? (
          <>
            <p className="mt-3 text-sm text-[var(--li-text-secondary)]">
              {pick.home_team?.short_name ?? pick.home_team?.name} vs{' '}
              {pick.away_team?.short_name ?? pick.away_team?.name} · {pick.market_name}
            </p>
            <div className="mt-3 flex items-center justify-between rounded-[var(--li-radius-sm)] border border-[var(--li-border)] bg-[var(--li-bg)] px-3 py-2.5">
              <p className="font-mono text-sm font-medium text-[var(--li-cyan)]">
                {predictionValueLabel(pick.value, pick.home_team ?? undefined, pick.away_team ?? undefined)}
              </p>
              <ConfidenceTelemetry confidence={pick.confidence_composite} size="sm" />
            </div>
            {pick.evidence_highlights.supporting.length > 0 && (
              <p className="mt-3 text-xs text-[var(--li-text-secondary)]">
                <span className="text-[var(--li-text-muted)]">Supporting evidence: </span>
                {pick.evidence_highlights.supporting.map(humanizeFactorKey).join(', ')}
              </p>
            )}
            {pick.evidence_highlights.contradicting.length > 0 && (
              <p className="mt-1.5 text-xs text-[var(--li-text-secondary)]">
                <span className="text-[var(--li-text-muted)]">Weighing against it: </span>
                {pick.evidence_highlights.contradicting.map(humanizeFactorKey).join(', ')}
              </p>
            )}
          </>
        ) : (
          <p className="mt-3 text-sm text-[var(--li-text-secondary)]">
            Once a prediction is published, its full evidence breakdown — supporting and
            contradicting features, confidence factors, and the Knowledge Graph relationships
            behind it — is available from its Match Intelligence page.
          </p>
        )}
      </div>
    </Section>
  )
}
