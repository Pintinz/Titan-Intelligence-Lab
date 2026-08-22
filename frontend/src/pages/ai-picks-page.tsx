import { useMemo, useState } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Search, Sparkles } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS, useAvailableSports } from '@/lib/hooks/use-sport'
import { ErrorState } from '@/components/ui/error-state'
import { MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import { AiPickCard, AI_PICK_CONFIDENCE_FLOOR, AI_PICK_HIGH_CONFIDENCE_FLOOR } from '@/components/command-deck/ai-picks/ai-pick-card'
import { dedupeByFixture } from '@/lib/predictions/dedupe-by-fixture'
import { fixtureCardStatus } from '@/lib/sports-status'
import type { PredictionPickDto, FixtureSummaryDto } from '@/lib/api/types'
import type { SportCode } from '@/lib/api/sports'

// `sportSlugFor` below still resolves against every real sport (a pick's own fixture always
// carries its true sport_code, whatever that is) — only the *filter dropdown* a regular user
// sees needs to hide Basketball/Baseball/Table Tennis, computed inside the component from
// `useAvailableSports()` since it's role-aware.

type DateRange = 'all' | 'today' | 'next7' | 'upcoming' | 'completed'

const DATE_RANGES: Array<{ key: DateRange; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'today', label: 'Today' },
  { key: 'next7', label: 'Next 7 days' },
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'completed', label: 'Completed' },
]

const DISPLAY_LIMIT = 30

function sportSlugFor(code: string): string {
  return SPORT_SLUGS.find((s) => s.code === code)?.slug ?? code
}

function isWithinNext7Days(scheduledAt: string): boolean {
  const diffMs = new Date(scheduledAt).getTime() - Date.now()
  return diffMs >= 0 && diffMs <= 7 * 86_400_000
}

function isToday(scheduledAt: string): boolean {
  return new Date(scheduledAt).toDateString() === new Date().toDateString()
}

export default function AiPicksPage() {
  const availableSports = useAvailableSports()
  const sportFilters: Array<{ label: string; code: SportCode | null }> = [
    { label: 'All sports', code: null },
    ...availableSports.map((s) => ({ label: s.label, code: s.code })),
  ]
  const [sportCode, setSportCode] = useState<SportCode | null>(null)
  const [dateRange, setDateRange] = useState<DateRange>('all')
  const [competition, setCompetition] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [highConfidenceOnly, setHighConfidenceOnly] = useState(false)

  const query = useQuery({
    queryKey: ['predictions', 'picks', sportCode],
    queryFn: () => predictionsApi.picks({ sport_code: sportCode ?? undefined, limit: 100 }),
  })

  const floorPassing = useMemo(() => (query.data ?? []).filter((pick) => pick.confidence_composite >= AI_PICK_CONFIDENCE_FLOOR), [query.data])

  const topPicks = useMemo(() => dedupeByFixture(floorPassing).slice(0, DISPLAY_LIMIT), [floorPassing])

  const fixtureQueries = useQueries({
    queries: topPicks.map((pick) => ({
      queryKey: ['sports', 'fixtures', pick.subject_ref],
      queryFn: () => sportsApi.getFixture(pick.subject_ref),
      retry: false,
      staleTime: 60_000,
    })),
  })

  const cards = topPicks
    .map((pick, i) => ({ pick, fixture: fixtureQueries[i]?.data }))
    .filter((row): row is { pick: PredictionPickDto; fixture: FixtureSummaryDto } => !!row.fixture)
    .sort((a, b) => b.pick.confidence_composite - a.pick.confidence_composite)

  const competitions = useMemo(() => Array.from(new Set(cards.map((c) => c.fixture.competition_name))).sort(), [cards])

  const highConfidenceCount = cards.filter((c) => c.pick.confidence_composite >= AI_PICK_HIGH_CONFIDENCE_FLOOR).length

  const searchLower = search.trim().toLowerCase()
  const filtered = cards.filter(({ pick, fixture }) => {
    if (competition && fixture.competition_name !== competition) return false
    if (highConfidenceOnly && pick.confidence_composite < AI_PICK_HIGH_CONFIDENCE_FLOOR) return false
    if (searchLower) {
      const haystack = `${fixture.home_team.name} ${fixture.away_team.name} ${fixture.competition_name}`.toLowerCase()
      if (!haystack.includes(searchLower)) return false
    }
    return true
  })

  const upcoming = filtered.filter(({ fixture }) => fixtureCardStatus(fixture.status) !== 'completed')
  const completed = filtered.filter(({ fixture }) => fixtureCardStatus(fixture.status) === 'completed')

  const showUpcoming = dateRange !== 'completed'
  const showCompleted = dateRange === 'completed' || dateRange === 'all'

  const dateFilteredUpcoming = upcoming.filter(({ fixture }) => {
    if (dateRange === 'today') return isToday(fixture.scheduled_at)
    if (dateRange === 'next7') return isWithinNext7Days(fixture.scheduled_at)
    return true
  })

  const isLoading = query.isPending || (topPicks.length > 0 && cards.length === 0 && fixtureQueries.some((q) => q.isPending))
  const hasVisibleResults = (showUpcoming && dateFilteredUpcoming.length > 0) || (showCompleted && completed.length > 0)

  return (
    <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <div>
        <span className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]" style={{ color: 'var(--cd-accent)' }}>
          AI Picks
        </span>
        <h2 className="mt-1 font-[var(--cd-font-display)] text-[22px] font-semibold tracking-[-0.01em] sm:text-[24px]" style={{ color: 'var(--cd-text-primary)' }}>
          The strongest intelligence, match by match.
        </h2>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
          One published prediction per match, ranked by TitanIQ confidence.
        </p>
      </div>

      <div className="space-y-2.5">
        <div className="flex flex-wrap gap-1.5">
          {sportFilters.map((filter) => {
            const active = sportCode === filter.code
            return (
              <button
                key={filter.label}
                type="button"
                onClick={() => setSportCode(filter.code)}
                className="rounded-full border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors"
                style={{
                  borderColor: active ? 'var(--cd-accent-strong)' : 'var(--cd-border-default)',
                  backgroundColor: active ? 'var(--cd-accent-muted)' : 'transparent',
                  color: active ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
                }}
              >
                {filter.label}
              </button>
            )
          })}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {DATE_RANGES.map((range) => {
            const active = dateRange === range.key
            return (
              <button
                key={range.key}
                type="button"
                onClick={() => setDateRange(range.key)}
                className="rounded-[var(--cd-radius-md)] border px-2.5 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors"
                style={{
                  borderColor: active ? 'var(--cd-accent-strong)' : 'var(--cd-border-default)',
                  backgroundColor: active ? 'var(--cd-accent-muted)' : 'var(--cd-surface-1)',
                  color: active ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
                }}
              >
                {range.label}
              </button>
            )
          })}
          <button
            type="button"
            onClick={() => setHighConfidenceOnly((v) => !v)}
            className="rounded-[var(--cd-radius-md)] border px-2.5 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors"
            style={{
              borderColor: highConfidenceOnly ? 'var(--cd-accent-strong)' : 'var(--cd-border-default)',
              backgroundColor: highConfidenceOnly ? 'var(--cd-accent-muted)' : 'var(--cd-surface-1)',
              color: highConfidenceOnly ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
            }}
          >
            High confidence
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[12rem]">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search matches, teams, competitions…"
              className="w-full rounded-[var(--cd-radius-md)] border py-1.5 pl-8 pr-3 font-[var(--cd-font-body)] text-[12.5px] focus:outline-none"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-primary)' }}
            />
          </div>
          {competitions.length > 1 && (
            <select
              value={competition ?? ''}
              onChange={(e) => setCompetition(e.target.value || null)}
              className="rounded-[var(--cd-radius-md)] border px-2.5 py-1.5 font-[var(--cd-font-body)] text-[12.5px] focus:outline-none"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-secondary)' }}
            >
              <option value="" style={{ backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-secondary)' }}>
                All competitions
              </option>
              {competitions.map((name) => (
                <option key={name} value={name} style={{ backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-secondary)' }}>
                  {name}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {!isLoading && cards.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <SummaryStat label="Published picks" value={floorPassing.length} />
          <SummaryStat label="High confidence" value={highConfidenceCount} />
          <SummaryStat label="Matches covered" value={cards.length} />
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-96 animate-pulse rounded-[var(--cd-radius-2xl)] motion-reduce:animate-none" style={{ background: 'var(--cd-card-surface)' }} />
          ))}
        </div>
      )}

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}

      {query.data && topPicks.length === 0 && (
        <MissionEmptyState
          icon={Sparkles}
          title="No published intelligence yet"
          description="Once TitanIQ publishes eligible predictions, the strongest available prediction for each match will appear here."
          actionLabel="Explore matches"
          actionHref="/app/football/matches"
        />
      )}

      {!isLoading && cards.length > 0 && !hasVisibleResults && (
        <p className="rounded-[var(--cd-radius-lg)] border p-6 text-center font-[var(--cd-font-body)] text-[13px]" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
          No picks match these filters.
        </p>
      )}

      {!isLoading && showUpcoming && dateFilteredUpcoming.length > 0 && (
        <section>
          <h3 className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            Upcoming Top Picks
          </h3>
          <p className="mt-0.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            The strongest published prediction currently available for each match.
          </p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {dateFilteredUpcoming.map(({ pick, fixture }) => (
              <AiPickCard key={pick.id} pick={pick} fixture={fixture} sportSlug={sportSlugFor(pick.sport_code)} matchStatus="upcoming" />
            ))}
          </div>
        </section>
      )}

      {!isLoading && showCompleted && completed.length > 0 && (
        <section>
          <h3 className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            Recently Completed
          </h3>
          <p className="mt-0.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            Historical picks — the match has finished, shown for review, not as a current recommendation.
          </p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {completed.map(({ pick, fixture }) => (
              <AiPickCard key={pick.id} pick={pick} fixture={fixture} sportSlug={sportSlugFor(pick.sport_code)} matchStatus="completed" />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[var(--cd-radius-lg)] px-4 py-3" style={{ backgroundColor: 'var(--cd-surface-1)', border: '1px solid var(--cd-border-default)' }}>
      <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
      <p className="mt-1 font-[var(--cd-font-tabular)] text-2xl font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
        {value}
      </p>
    </div>
  )
}
