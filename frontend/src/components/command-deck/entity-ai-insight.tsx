import { Sparkles } from 'lucide-react'
import { CDPanel, CDLabel } from './primitives/panel'

/**
 * AI Insight — honest unavailable state. No backend Gemini pipeline generates player- or
 * competition-level narration today (every real Gemini call site in this codebase narrates a
 * specific *prediction* — `ExplainabilityEngine`/`ContextualReasoningService`/
 * `FootballExplanationService`, confirmed by direct audit — none of them accept a bare player or
 * competition as a subject). Rather than synthesize a client-side summary from whatever evidence
 * happens to be on screen (which would be an invented explanation wearing an "AI Insight" label),
 * this renders the same honest unavailable state every time. If a genuine player/competition-level
 * grounded narration endpoint is ever added, this component is the one place to swap in the real
 * rendering — every caller already renders through here.
 */
export function EntityAiInsightUnavailable({ entityLabel }: { entityLabel: string }) {
  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <Sparkles className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>AI Insight</CDLabel>
      </div>
      <p className="mt-3 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-secondary)' }}>
        AI Insight unavailable
      </p>
      <p className="mt-1 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
        TitanIQ doesn't currently generate grounded AI narration for {entityLabel} directly — evidence-grounded explanations exist
        today only for individual match predictions.
      </p>
    </CDPanel>
  )
}
