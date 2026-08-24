import { Check, X } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'

// Every TitanIQ-side claim traces to a real, shipped capability documented elsewhere on this page
// (Feature Store, SHAP attribution, Knowledge Graph, Learning Intelligence loop) — nothing here
// names a competitor; the right column describes the category default TitanIQ was built against,
// per PRODUCT.md's "fundamentally not a betting site or score app" positioning.
const ROWS = [
  {
    them: 'A number with no explanation',
    us: 'Every prediction ships with its confidence, evidence, and reasoning',
  },
  {
    them: 'Odds, stakes, and "best bets" framing',
    us: 'Confidence, risk, and prediction stability — never betting vocabulary',
  },
  {
    them: 'A black-box model you have to trust',
    us: 'SHAP-based feature attribution — see exactly what moved the number',
  },
  {
    them: 'Stats treated in isolation',
    us: 'A real Knowledge Graph connecting teams, players, venues, and history',
  },
  {
    them: 'A static tip that never updates',
    us: 'A learning loop that recalibrates confidence against real settled outcomes',
  },
]

export function TrustDifferentiationSection() {
  return (
    <Section className="border-b border-[var(--li-border)]">
      <SectionHeading
        title="Not a tips site. An explainability engine."
        description="The mechanism above is the product, not a marketing claim layered on top of a black box."
      />

      <div className="overflow-hidden rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] shadow-[var(--li-shadow-card)] backdrop-blur-[var(--li-glass-2-blur)]">
        <div className="grid grid-cols-2 divide-x divide-[var(--li-border)] bg-[var(--li-surface-elevated)] text-xs font-semibold uppercase tracking-wide text-[var(--li-text-muted)]">
          <p className="px-5 py-3">The category default</p>
          <p className="px-5 py-3 text-[var(--li-cyan)]">TitanIQ</p>
        </div>
        <div className="divide-y divide-[var(--li-border)]">
          {ROWS.map((row) => (
            <div key={row.us} className="grid grid-cols-2 divide-x divide-[var(--li-border)]">
              <div className="flex items-start gap-2.5 bg-[var(--li-surface-elevated)] px-5 py-4">
                <X className="mt-0.5 size-4 shrink-0 text-[var(--li-text-muted)]" aria-hidden="true" />
                <p className="text-sm text-[var(--li-text-muted)]">{row.them}</p>
              </div>
              <div className="flex items-start gap-2.5 px-5 py-4">
                <Check className="mt-0.5 size-4 shrink-0 text-[var(--li-positive)]" aria-hidden="true" />
                <p className="text-sm text-[var(--li-text-secondary)]">{row.us}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}
