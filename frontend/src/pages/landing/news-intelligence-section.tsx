import { ExternalLink } from 'lucide-react'
import { SAMPLE_NEWS } from '@/pages/landing/sample-data'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

const SPORT_INITIAL: Record<string, string> = { football: 'FB', basketball: 'BB', baseball: 'BA', table_tennis: 'TT' }

/**
 * News Intelligence — never a blog. Each card summarizes (never reproduces) a source article and
 * states its effect on the prediction, community, and confidence — no licensed photography is
 * available for this preview, so each card uses an abstract sport-coded panel instead of a
 * stock/stand-in photo that could be mistaken for a real licensed image.
 */
export function NewsIntelligenceSection() {
  return (
    <Section id="news-intelligence" className="pt-0">
      <SectionHeading
        eyebrow="News Intelligence"
        title="Summarized. Attributed. Never copied."
        description="Every article is read, summarized, and scored for impact on the prediction, the community, and the confidence engine — always with a path back to the original source."
        action={<IllustrativeTag />}
      />

      <div className="mt-8 grid gap-5 md:grid-cols-3">
        {SAMPLE_NEWS.map((item) => (
          <article
            key={item.title}
            className="flex flex-col overflow-hidden rounded-lg"
            style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}
          >
            <div
              className="flex h-24 items-center justify-center"
              style={{ background: 'linear-gradient(135deg, var(--tl-carbon) 0%, var(--tl-void) 100%)' }}
              aria-hidden="true"
            >
              <span className="tl-display text-4xl tracking-widest" style={{ color: 'var(--tl-steel-line-strong)' }}>
                {SPORT_INITIAL[item.sport]}
              </span>
            </div>
            <div className="flex flex-1 flex-col gap-3 p-5">
              <h3 className="text-sm font-semibold leading-snug" style={{ color: 'var(--tl-ink)' }}>
                {item.title}
              </h3>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--tl-ink-dim)' }}>
                {item.summary}
              </p>
              <dl className="mt-1 flex flex-col gap-1.5 text-[0.7rem]">
                <ImpactRow label="Prediction impact" value={item.predictionImpact} />
                <ImpactRow label="Community impact" value={item.communityImpact} />
                <ImpactRow label="Confidence impact" value={item.confidenceImpact} />
              </dl>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {item.relatedTeams.map((t) => (
                  <span
                    key={t}
                    className="tl-mono rounded-full px-2 py-0.5 text-[0.65rem]"
                    style={{ border: '1px solid var(--tl-steel-line-strong)', color: 'var(--tl-ink-dim)' }}
                  >
                    {t}
                  </span>
                ))}
              </div>
              <button
                type="button"
                className="tl-eyebrow mt-auto flex items-center gap-1.5 pt-2"
                style={{ color: 'var(--tl-signal)', fontSize: '0.65rem' }}
              >
                {item.sourceLabel}
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          </article>
        ))}
      </div>
    </Section>
  )
}

function ImpactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <dt className="tl-eyebrow shrink-0" style={{ color: 'var(--tl-ink-faint)', fontSize: '0.6rem', width: '5.5rem' }}>
        {label}
      </dt>
      <dd style={{ color: 'var(--tl-ink-dim)' }}>{value}</dd>
    </div>
  )
}
