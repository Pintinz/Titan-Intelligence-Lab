import { Sparkles, ArrowUp } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'
import { INSIGHTS_PROMPTS } from './sample-data'

/**
 * Landing preview of TitanIQ Insights (Phase 5) — a grounded explanation panel, not a freeform
 * chat product. The input below is intentionally disabled: conversational answering is Roadmap
 * Milestone 17, not built yet, and this page never implies it already exists.
 */
export function InsightsSection() {
  return (
    <Section className="border-b border-border-subtle">
      <SectionHeading
        eyebrow="TitanIQ Insights"
        title="Ask why, not just what"
        description="Every prediction can explain itself — the evidence, the confidence factors, and how a piece of news or a graph relationship changed the number."
      />

      <div className="mx-auto max-w-lg rounded-lg border border-border-default bg-bg-elevated p-5">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <Sparkles className="size-4 text-accent-primary" aria-hidden="true" />
          TitanIQ Insights
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {INSIGHTS_PROMPTS.map((prompt) => (
            <span
              key={prompt}
              className="rounded-full border border-border-default px-3 py-1.5 text-xs text-text-secondary"
            >
              {prompt}
            </span>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2 rounded-md border border-border-subtle bg-bg-primary px-3 py-2 opacity-60">
          <span className="flex-1 text-sm text-text-muted">Free-form questions arrive in a future update</span>
          <span className="flex size-6 items-center justify-center rounded-full bg-bg-secondary">
            <ArrowUp className="size-3 text-text-muted" aria-hidden="true" />
          </span>
        </div>
      </div>
    </Section>
  )
}
