import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Section, SectionHeading, IllustrativeTag } from './section-primitives'
import { NEWS_ITEMS } from './sample-data'

function timeAgo(iso: string) {
  const hours = Math.round((Date.now() - new Date(iso).getTime()) / 3_600_000)
  if (hours < 1) return 'just now'
  return `${hours}h ago`
}

export function NewsIntelligenceSection() {
  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading
          eyebrow="News Intelligence"
          title="Not a news feed — news, interpreted"
          description="TitanIQ never republishes articles. Every story is summarized and scored for what it actually changes."
        />
        <IllustrativeTag />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {NEWS_ITEMS.map((item) => (
          <Card key={item.article.id} className="flex flex-col gap-3 p-5">
            <div className="flex h-24 items-center justify-center rounded-md bg-gradient-to-br from-accent-primary-muted to-premium-muted">
              <span className="font-telemetry text-xs uppercase tracking-wider text-text-secondary">
                {item.relatedCompetition}
              </span>
            </div>
            <p className="font-mono text-[11px] text-text-muted">{timeAgo(item.article.published_at)}</p>
            <p className="font-display text-sm font-semibold leading-snug text-text-primary">
              {item.article.title}
            </p>
            <p className="text-xs text-text-secondary">{item.summary}</p>

            <dl className="space-y-1.5 border-t border-border-subtle pt-3 text-xs">
              <div className="flex justify-between gap-2">
                <dt className="shrink-0 text-text-muted">Prediction impact</dt>
                <dd className="text-right text-text-secondary">{item.predictionImpact}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="shrink-0 text-text-muted">Confidence impact</dt>
                <dd className="text-right text-text-secondary">{item.confidenceImpact}</dd>
              </div>
            </dl>

            <div className="flex flex-wrap gap-1.5">
              {item.relatedTeams.map((t) => (
                <span key={t} className="rounded-full border border-border-default px-2 py-0.5 text-[10px] text-text-muted">
                  {t}
                </span>
              ))}
            </div>

            <a
              href={item.article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-accent-primary hover:text-accent-primary-hover"
            >
              Read original source <ArrowRight className="size-3" />
            </a>
          </Card>
        ))}
      </div>

      <Link
        to="/signup"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-text-primary hover:text-accent-primary"
      >
        Explore all News Intelligence <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
