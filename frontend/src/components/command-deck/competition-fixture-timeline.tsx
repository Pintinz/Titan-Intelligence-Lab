import { DiscoveryMatchCard } from './discovery/discovery-match-card'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import type { FixtureSummaryDto } from '@/lib/api/types'

const MONTH_FORMAT = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' })
const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
const TIME_FORMAT = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' })

interface DateGroup {
  dateKey: string
  label: string
  fixtures: FixtureSummaryDto[]
}
interface MonthGroup {
  monthKey: string
  label: string
  dates: DateGroup[]
}

function groupChronologically(fixtures: FixtureSummaryDto[]): MonthGroup[] {
  const months = new Map<string, MonthGroup>()
  for (const fixture of fixtures) {
    const d = new Date(fixture.scheduled_at)
    const monthKey = `${d.getFullYear()}-${d.getMonth()}`
    const dateKey = d.toDateString()
    if (!months.has(monthKey)) months.set(monthKey, { monthKey, label: MONTH_FORMAT.format(d), dates: [] })
    const month = months.get(monthKey)!
    let dateGroup = month.dates.find((g) => g.dateKey === dateKey)
    if (!dateGroup) {
      dateGroup = { dateKey, label: DATE_FORMAT.format(d), fixtures: [] }
      month.dates.push(dateGroup)
    }
    dateGroup.fixtures.push(fixture)
  }
  return [...months.values()]
}

/**
 * CompetitionFixtureTimeline — a chronological schedule/results list, grouped Month → Date so a
 * long run of fixtures reads as a scannable calendar instead of one undifferentiated wall. A thin
 * rail + dot per date gives the "season easy to scan" structure without a literal ASCII tree.
 * Every card is `DiscoveryMatchCard` — the same fixture-scan unit used on Match Discovery, so
 * every page using this reads as one continuous instrument. Sort order is the caller's choice
 * (pass ascending for a schedule, descending for a results feed) — grouping preserves whatever
 * order `fixtures` arrives in. Each card reads its own competition name/crest from the fixture
 * itself (`FixtureSummaryDto` already carries both), so this works equally on a single-competition
 * page (Competition Detail) and a multi-competition one (Team Detail, league + cup fixtures mixed).
 * Match links derive their sport from the fixture's own real `sport_code` (falling back to the
 * page's route sport), never hardcoded.
 */
export function CompetitionFixtureTimeline({
  fixtures,
  fallbackSportSlug,
  aiReady,
}: {
  fixtures: FixtureSummaryDto[]
  fallbackSportSlug: string
  aiReady: boolean
}) {
  const months = groupChronologically(fixtures)

  return (
    <div className="space-y-8">
      {months.map((month) => (
        <div key={month.monthKey}>
          <p className="mb-4 font-[var(--cd-font-telemetry)] text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--cd-accent)' }}>
            {month.label}
          </p>
          <div className="space-y-5 border-l pl-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
            {month.dates.map((group) => (
              <div key={group.dateKey} className="relative">
                <span
                  className="absolute -left-[26px] top-1.5 size-2.5 rounded-full"
                  style={{ backgroundColor: 'var(--cd-surface-1)', boxShadow: '0 0 0 2px var(--cd-accent)' }}
                  aria-hidden="true"
                />
                <p className="mb-2.5 font-[var(--cd-font-body)] text-[12px] font-semibold uppercase tracking-[0.03em]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {group.label}
                </p>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {group.fixtures.map((fixture) => {
                    const { homeScore, awayScore } = fixtureScores(fixture.final_state)
                    const sportSlug = fixture.sport_code ?? fallbackSportSlug
                    return (
                      <DiscoveryMatchCard
                        key={fixture.id}
                        competition={fixture.competition_name}
                        competitionLogoUrl={fixture.competition_logo_url}
                        status={fixtureCardStatus(fixture.status)}
                        kickoffLabel={TIME_FORMAT.format(new Date(fixture.scheduled_at))}
                        venue={fixture.venue_name}
                        homeTeam={fixture.home_team.name}
                        awayTeam={fixture.away_team.name}
                        homeScore={homeScore}
                        awayScore={awayScore}
                        homeLogoUrl={fixture.home_team.logo_url}
                        awayLogoUrl={fixture.away_team.logo_url}
                        aiAvailable={aiReady}
                        href={`/app/${sportSlug}/matches/${fixture.id}`}
                      />
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
