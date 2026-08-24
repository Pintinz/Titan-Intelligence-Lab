import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'
import type { PublicNewsIntelligenceItemDto } from '@/lib/api/types'

function timeAgo(iso: string) {
  const hours = Math.round((Date.now() - new Date(iso).getTime()) / 3_600_000)
  if (hours < 1) return 'just now'
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function eventTypeLabel(eventType: string) {
  return eventType.replace(/_/g, ' ')
}

export function NewsIntelligenceSection({
  loading,
  items,
}: {
  loading: boolean
  items: PublicNewsIntelligenceItemDto[]
}) {
  if (!loading && items.length === 0) return null

  return (
    <Section className="border-b border-[var(--li-border)]">
      <SectionHeading
        title="Not a news feed — news, interpreted"
        description="TitanIQ never republishes articles. Every story shown here already has a real, backend-computed impact score attached."
      />

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-[var(--li-radius-md)] bg-[var(--li-surface)]" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {items.map((item) => (
            <div
              key={item.article_id}
              className="flex flex-col gap-3 rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] p-5 shadow-[var(--li-shadow-card)] backdrop-blur-[var(--li-glass-2-blur)] transition-all duration-300 hover:-translate-y-1 hover:border-[var(--li-border-strong)] hover:shadow-[var(--li-shadow-card-hover)]"
            >
              <div className="flex items-center justify-between">
                <span className="rounded-full border border-[var(--li-border)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--li-text-muted)]">
                  {eventTypeLabel(item.event_type)}
                </span>
                <p className="font-mono text-[11px] text-[var(--li-text-muted)]">{timeAgo(item.published_at)}</p>
              </div>
              <p className="text-sm font-semibold leading-snug text-[var(--li-text-primary)]">{item.headline}</p>
              <p className="text-xs text-[var(--li-text-secondary)]">{item.event_summary}</p>

              <dl className="space-y-1.5 border-t border-[var(--li-border)] pt-3 text-xs">
                <div className="flex justify-between gap-2">
                  <dt className="shrink-0 text-[var(--li-text-muted)]">Impact score</dt>
                  <dd className="text-right font-mono text-[var(--li-text-secondary)]">{Math.round(item.impact_score * 100)}%</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="shrink-0 text-[var(--li-text-muted)]">Confidence</dt>
                  <dd className="text-right font-mono text-[var(--li-text-secondary)]">{Math.round(item.impact_confidence * 100)}%</dd>
                </div>
              </dl>

              {(item.affected_teams.length > 0 || item.affected_competitions.length > 0) && (
                <div className="flex flex-wrap gap-1.5">
                  {[...item.affected_teams, ...item.affected_competitions].map((name) => (
                    <span key={name} className="rounded-full border border-[var(--li-border)] px-2 py-0.5 text-[10px] text-[var(--li-text-muted)]">
                      {name}
                    </span>
                  ))}
                </div>
              )}

              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-[var(--li-cyan)] hover:text-[var(--li-cyan-hover)]"
              >
                Read original source <ArrowRight className="size-3" />
              </a>
            </div>
          ))}
        </div>
      )}

      <Link
        to="/signup"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--li-text-primary)] hover:text-[var(--li-cyan)]"
      >
        Explore all News Intelligence <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
