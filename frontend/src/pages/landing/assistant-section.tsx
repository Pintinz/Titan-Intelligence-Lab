import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { ASSISTANT_SAMPLE_EXCHANGES } from '@/pages/landing/sample-data'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

/**
 * TitanIQ Assistant — never "AI Copilot". A teaser panel showing the kind of question it answers
 * (explain a prediction, a confidence score, a chart, a comparison), not a faked live chat — the
 * input is disabled and clearly a preview, since the real assistant lives behind auth.
 */
export function AssistantSection() {
  return (
    <Section className="pt-0">
      <SectionHeading
        eyebrow="TitanIQ Assistant"
        title="Ask it why. It'll show its work."
        description="Explains predictions, confidence, charts, and comparisons in plain language — grounded in the same evidence the Confidence and Explainability Engines used."
        action={<IllustrativeTag />}
      />

      <div className="mt-8 rounded-xl p-6" style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}>
        <div className="flex flex-col gap-5">
          {ASSISTANT_SAMPLE_EXCHANGES.map((ex) => (
            <div key={ex.question} className="flex flex-col gap-2">
              <div className="flex items-start gap-2">
                <span className="tl-eyebrow shrink-0" style={{ color: 'var(--tl-ink-faint)', fontSize: '0.65rem' }}>
                  You
                </span>
                <p className="text-sm" style={{ color: 'var(--tl-ink)' }}>
                  {ex.question}
                </p>
              </div>
              <div className="flex items-start gap-2 rounded-md p-3" style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)' }}>
                <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: 'var(--tl-signal)' }} aria-hidden="true" />
                <p className="text-sm leading-relaxed" style={{ color: 'var(--tl-ink-dim)' }}>
                  {ex.answer}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex items-center gap-3">
          <input
            disabled
            placeholder="Ask TitanIQ Assistant about any match, team, or prediction…"
            className="flex-1 rounded-md px-4 py-3 text-sm"
            style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)', color: 'var(--tl-ink-faint)' }}
            aria-label="TitanIQ Assistant preview input, disabled — sign in to ask a real question"
          />
          <Link
            to="/signup"
            className="tl-eyebrow shrink-0 rounded-md px-5 py-3 transition-transform hover:-translate-y-0.5"
            style={{ background: 'var(--tl-signal)', color: 'var(--tl-void)', fontSize: '0.7rem' }}
          >
            Sign in to ask
          </Link>
        </div>
      </div>
    </Section>
  )
}
