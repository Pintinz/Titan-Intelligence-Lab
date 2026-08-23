import { useQuery } from '@tanstack/react-query'
import {
  Newspaper,
  ArrowLeftRight,
  HeartPulse,
  Heart,
  Ban,
  UserCog,
  LayoutGrid,
  Compass,
  Dumbbell,
  CloudRain,
  PlaneTakeoff,
  Building2,
  CalendarX,
  UserCheck,
  ClipboardList,
} from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { CDPanel, CDLabel } from './primitives/panel'
import { MissionEmptyState, MissionSkeletonGrid } from './mission-control/mission-section'

/** Real `NewsEventType` values (`event_extraction_service.py`) mapped to a glyph — mirrors
 * `team-detail-page.tsx`'s own `NEWS_EVENT_ICON` table so a news card carries the same identity
 * language everywhere in the app, never a fabricated category. */
const NEWS_EVENT_ICON: Record<string, typeof Newspaper> = {
  transfer: ArrowLeftRight,
  injury: HeartPulse,
  recovery: Heart,
  suspension: Ban,
  manager_change: UserCog,
  formation_change: LayoutGrid,
  tactical_change: Compass,
  training_update: Dumbbell,
  weather_report: CloudRain,
  travel_delay: PlaneTakeoff,
  stadium_change: Building2,
  match_postponement: CalendarX,
  player_availability: UserCheck,
  lineup_expectation: ClipboardList,
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 60) return `${Math.max(mins, 0)}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

/**
 * EntityNewsPanel — Command Deck styling of the same real news-extraction pipeline
 * `team-detail-page.tsx`'s (Infinity-styled) `NewsIntelligenceSection` already uses
 * (`intelligenceApi.newsForEntity`), extracted here so Player and Competition Intelligence share
 * one implementation instead of two near-duplicates. Every card is a real extracted `NewsEventDto`
 * — no article text is generated, no category is invented.
 */
export function EntityNewsPanel({ entityRef, entityLabel }: { entityRef: string; entityLabel: string }) {
  const newsQuery = useQuery({
    queryKey: ['intelligence', 'news', 'entity', entityRef],
    queryFn: () => intelligenceApi.newsForEntity(entityRef, 8),
    enabled: !!entityRef,
  })

  if (newsQuery.isPending) return <MissionSkeletonGrid count={2} />

  const events = newsQuery.data ?? []
  if (events.length === 0) {
    return (
      <MissionEmptyState
        icon={Newspaper}
        title="No verified coverage yet"
        description={`TitanIQ hasn't extracted verified news signals for ${entityLabel} yet — this fills in as coverage grows.`}
      />
    )
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {events.map((event) => {
        const EventIcon = NEWS_EVENT_ICON[event.event_type] ?? Newspaper
        return (
          <CDPanel key={event.id} padding="tight">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="flex size-6 shrink-0 items-center justify-center rounded-[var(--cd-radius-sm)]"
                  style={{ backgroundColor: 'var(--cd-domain-news, var(--cd-accent-muted))', color: 'var(--cd-accent)' }}
                  aria-hidden="true"
                >
                  <EventIcon className="size-3.5" />
                </span>
                <CDLabel>{event.event_type.replace(/_/g, ' ')}</CDLabel>
              </div>
              <span className="shrink-0 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                {relativeTime(event.occurred_at)}
              </span>
            </div>
            <p className="mt-2 font-[var(--cd-font-body)] text-[13px] font-medium leading-snug" style={{ color: 'var(--cd-text-primary)' }}>
              {event.summary}
            </p>
            <p className="mt-2 border-t pt-2 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
              Extraction confidence {Math.round(event.confidence * 100)}%
            </p>
          </CDPanel>
        )
      })}
    </div>
  )
}
