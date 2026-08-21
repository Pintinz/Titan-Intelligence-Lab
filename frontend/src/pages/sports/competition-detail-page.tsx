import { useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, LayoutGrid, CalendarDays, History, ListOrdered, Users, CalendarRange } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import { ErrorState } from '@/components/ui/error-state'
import { CDPanel } from '@/components/command-deck/primitives/panel'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '@/components/command-deck/primitives/domain'
import { CompetitionDetailHero, type CompetitionStatus } from '@/components/command-deck/competition-detail-hero'
import { CompetitionSnapshot } from '@/components/command-deck/competition-snapshot'
import { CompetitionFixtureTimeline } from '@/components/command-deck/competition-fixture-timeline'
import { CompetitionStandingsTable } from '@/components/command-deck/competition-standings-table'
import { DiscoveryMatchCard } from '@/components/command-deck/discovery/discovery-match-card'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import type { FixtureSummaryDto } from '@/lib/api/types'

type TabKey = 'overview' | 'fixtures' | 'results' | 'standings' | 'teams'

const TABS: Array<{ key: TabKey; label: string; icon: typeof LayoutGrid }> = [
  { key: 'overview', label: 'Overview', icon: LayoutGrid },
  { key: 'fixtures', label: 'Fixtures', icon: CalendarDays },
  { key: 'results', label: 'Results', icon: History },
  { key: 'standings', label: 'Standings', icon: ListOrdered },
  { key: 'teams', label: 'Teams', icon: Users },
]

const OVERVIEW_LIMIT = 6
const KICKOFF_TIME = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
// Results can now span any past season via the season filter, not just "today's" matches, so a
// finished fixture's card needs its date (not just "Full time") to stay legible.
const RESULT_DATE = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

/**
 * CompetitionDetailPage — Competition Intelligence, redesigned per the shaped brief (see chat).
 * Every value traces to `getCompetition`/`competitionStandings`/`competitionFixtures` (one fetch
 * each, already the page's own queries) plus one new sport-wide "AI ready" query — status,
 * snapshot counts, teams, and chronological grouping are all deterministic transforms of that same
 * already-fetched data, never a second fixture-fetching mechanism.
 */
export default function CompetitionDetailPage() {
  const sport = useSportParam()
  const { competitionId } = useParams<{ competitionId: string }>()
  const watchlist = useWatchlist()
  const [tab, setTab] = useState<TabKey>('overview')
  // '' means "let the backend pick the current season" — the same best-effort default it always
  // used before this filter existed. Only set once the person explicitly chooses one.
  const [selectedSeasonId, setSelectedSeasonId] = useState('')

  const competitionQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId],
    queryFn: () => sportsApi.getCompetition(competitionId!),
    enabled: !!competitionId,
  })
  const seasonsQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId, 'seasons'],
    queryFn: () => sportsApi.competitionSeasons(competitionId!),
    enabled: !!competitionId,
  })
  const standingsQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId, 'standings', selectedSeasonId],
    queryFn: () => sportsApi.competitionStandings(competitionId!, selectedSeasonId || undefined),
    enabled: !!competitionId,
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId, 'fixtures', selectedSeasonId],
    queryFn: () => sportsApi.competitionFixtures(competitionId!, 50, selectedSeasonId || undefined),
    enabled: !!competitionId,
  })
  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production', 'competition-detail'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })

  const fixtures = fixturesQuery.data ?? []
  const standings = standingsQuery.data ?? []
  const seasons = seasonsQuery.data ?? []
  const aiReady = (marketsQuery.data?.length ?? 0) > 0

  const live = useMemo(() => fixtures.filter((f) => fixtureCardStatus(f.status) === 'live'), [fixtures])
  const upcoming = useMemo(
    () => fixtures.filter((f) => fixtureCardStatus(f.status) === 'upcoming').sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()),
    [fixtures],
  )
  const completed = useMemo(
    () => fixtures.filter((f) => fixtureCardStatus(f.status) === 'completed').sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime()),
    [fixtures],
  )
  const scheduleFixtures = useMemo(() => [...live, ...upcoming], [live, upcoming])
  const overviewFixtures = useMemo(() => scheduleFixtures.slice(0, OVERVIEW_LIMIT), [scheduleFixtures])

  const teams = useMemo(() => {
    const rankByTeam = new Map(standings.map((row) => [row.team_id, row.rank]))
    const byId = new Map<string, { id: string; name: string; logoUrl: string | null; rank: number | null }>()
    for (const fixture of fixtures) {
      for (const team of [fixture.home_team, fixture.away_team]) {
        if (!byId.has(team.id)) byId.set(team.id, { id: team.id, name: team.name, logoUrl: team.logo_url, rank: rankByTeam.get(team.id) ?? null })
      }
    }
    return [...byId.values()].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.name.localeCompare(b.name))
  }, [fixtures, standings])

  const status: CompetitionStatus = live.length > 0 ? 'active' : upcoming.length > 0 ? 'upcoming' : completed.length > 0 ? 'completed' : 'data-limited'

  const nextMatch = overviewFixtures[0] ? `${overviewFixtures[0].home_team.name} vs ${overviewFixtures[0].away_team.name}` : null

  // Every tab is always selectable — data-gating a tab out of the list is what silently broke
  // the Hero's "View fixtures"/"View teams" quick actions (setTab() to a hidden tab fell straight
  // back to 'overview' with no visible change). Each tab renders its own honest empty state
  // instead, matching how 'standings' already behaved.
  const activeTab = tab

  if (!sport) return null
  if (competitionQuery.isPending) {
    return (
      <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
        <div className="h-32 animate-pulse rounded-[var(--cd-radius-xl)]" style={{ background: 'var(--cd-card-surface)' }} />
        <MissionSkeletonGrid count={3} />
      </div>
    )
  }
  if (competitionQuery.isError || !competitionQuery.data) {
    return (
      <div className="command-deck rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
        <ErrorState error={competitionQuery.error} onRetry={() => void competitionQuery.refetch()} />
      </div>
    )
  }

  const competition = competitionQuery.data
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  const domainColor = CD_DOMAIN_COLOR_VAR[domain]

  function cardFor(fixture: FixtureSummaryDto) {
    const { homeScore, awayScore } = fixtureScores(fixture.final_state)
    const sportSlug = fixture.sport_code ?? sport!.slug
    const status = fixtureCardStatus(fixture.status)
    return (
      <DiscoveryMatchCard
        key={fixture.id}
        competition={competition.name}
        competitionLogoUrl={competition.logo_url}
        status={status}
        kickoffLabel={status === 'completed' ? RESULT_DATE.format(new Date(fixture.scheduled_at)) : KICKOFF_TIME.format(new Date(fixture.scheduled_at))}
        venue={fixture.venue_name}
        homeTeam={fixture.home_team.name}
        awayTeam={fixture.away_team.name}
        homeScore={homeScore}
        awayScore={awayScore}
        homeLogoUrl={fixture.home_team.logo_url}
        awayLogoUrl={fixture.away_team.logo_url}
        aiAvailable={aiReady}
        href={status === 'completed' ? `/app/${sportSlug}/matches/${fixture.id}/review` : `/app/${sportSlug}/matches/${fixture.id}`}
      />
    )
  }

  return (
    <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
      <Link
        to={`/app/${sport.slug}/competitions`}
        className="inline-flex items-center gap-1 font-[var(--cd-font-body)] text-[13px] transition-colors"
        style={{ color: 'var(--cd-text-secondary)' }}
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" /> Back to competitions
      </Link>

      <CompetitionDetailHero
        competition={competition}
        sportLabel={sport.label}
        sportDomain={domain}
        status={status}
        following={watchlist.isFollowing('competition', competition.id)}
        onToggleFollow={() => watchlist.toggle('competition', competition.id)}
        onViewFixtures={() => setTab('fixtures')}
        onViewTeams={() => setTab('teams')}
      />

      <CompetitionSnapshot fixtures={fixtures.length} upcoming={live.length + upcoming.length} completed={completed.length} teams={teams.length} nextMatch={nextMatch} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Competition sections" className="-mx-1 flex w-fit max-w-full gap-1 overflow-x-auto rounded-[var(--cd-radius-md)] border p-1 backdrop-blur-md" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 70%, transparent)' }}>
          {TABS.map(({ key, label, icon: Icon }) => {
            const active = key === activeTab
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(key)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-[var(--cd-radius-sm)] px-3.5 py-1.5 font-[var(--cd-font-body)] text-[12.5px] font-semibold transition-all duration-[var(--cd-motion-base)]"
                style={{
                  backgroundColor: active ? domainTint(domain, 16) : 'transparent',
                  boxShadow: active ? `0 0 0 1px ${domainTint(domain, 40)} inset` : 'none',
                  color: active ? domainColor : 'var(--cd-text-secondary)',
                }}
              >
                <Icon className="size-3.5" aria-hidden="true" />
                {label}
              </button>
            )
          })}
        </div>

        {tab !== 'overview' && tab !== 'teams' && seasons.length > 1 && (
          <label className="inline-flex shrink-0 items-center gap-1.5 rounded-[var(--cd-radius-md)] border px-2.5 py-1.5" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}>
            <CalendarRange className="size-3.5 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <span className="sr-only">Season</span>
            <select
              value={selectedSeasonId}
              onChange={(e) => setSelectedSeasonId(e.target.value)}
              className="bg-transparent font-[var(--cd-font-body)] text-[12.5px] font-medium focus:outline-none"
              style={{ color: 'var(--cd-text-primary)' }}
            >
              {/* The closed control inherits the dark page background via bg-transparent, but the
                  native OS dropdown popup ignores that — Chrome/Firefox both default <option> to a
                  white popup background, which combined with this page's light `color` token reads
                  as unreadable white-on-white. <option> (unlike <select>) does accept its own
                  background-color/color, so set both explicitly here rather than relying on inheritance. */}
              <option value="" style={{ backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-primary)' }}>
                Current season
              </option>
              {seasons.map((s) => (
                <option key={s.id} value={s.id} style={{ backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-primary)' }}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {activeTab === 'overview' && (
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <MissionSection
              title="Upcoming"
              subtitle={scheduleFixtures.length > OVERVIEW_LIMIT ? `Next ${OVERVIEW_LIMIT} of ${scheduleFixtures.length} fixtures` : undefined}
              icon={<CalendarDays className="size-4" aria-hidden="true" />}
              domain={domain}
            >
              {overviewFixtures.length === 0 ? (
                <MissionEmptyState icon={CalendarDays} title="No upcoming fixtures" description="There are currently no scheduled fixtures in this competition." />
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">{overviewFixtures.map((f) => cardFor(f))}</div>
              )}
              {scheduleFixtures.length > OVERVIEW_LIMIT && (
                <button
                  type="button"
                  onClick={() => setTab('fixtures')}
                  className="mt-4 font-[var(--cd-font-body)] text-[12.5px] font-semibold transition-colors"
                  style={{ color: 'var(--cd-accent)' }}
                >
                  View all fixtures →
                </button>
              )}
            </MissionSection>
          </div>

          <div className="space-y-6 lg:col-span-4">
            {completed.length > 0 && (
              <MissionSection title="Latest Result" icon={<History className="size-4" aria-hidden="true" />}>
                {cardFor(completed[0])}
              </MissionSection>
            )}
            <MissionSection title="Table" icon={<ListOrdered className="size-4" aria-hidden="true" />}>
              {standings.length === 0 ? (
                <MissionEmptyState icon={ListOrdered} title="Standings unavailable" description="TitanIQ has not received standings data for this competition yet." />
              ) : (
                <CDPanel padding="none" className="overflow-hidden">
                  <div className="divide-y" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                    {standings.slice(0, 5).map((row) => (
                      <div key={row.team_id} className="flex items-center justify-between gap-3 px-4 py-2.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                        <span className="flex min-w-0 items-center gap-2.5">
                          <span className="font-[var(--cd-font-tabular)] text-[12px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                            {row.rank}
                          </span>
                          <Link to={`/app/${sport.slug}/teams/${row.team_id}`} className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                            {row.team_name}
                          </Link>
                        </span>
                        <span className="shrink-0 font-[var(--cd-font-tabular)] text-[13px] font-bold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                          {row.points}
                        </span>
                      </div>
                    ))}
                  </div>
                </CDPanel>
              )}
              {standings.length > 5 && (
                <button
                  type="button"
                  onClick={() => setTab('standings')}
                  className="mt-3 font-[var(--cd-font-body)] text-[12.5px] font-semibold transition-colors"
                  style={{ color: 'var(--cd-accent)' }}
                >
                  Full table →
                </button>
              )}
            </MissionSection>
          </div>
        </div>
      )}

      {activeTab === 'fixtures' && (
        <MissionSection title="Fixtures" subtitle={`${scheduleFixtures.length} scheduled`} icon={<CalendarDays className="size-4" aria-hidden="true" />}>
          {scheduleFixtures.length === 0 ? (
            <MissionEmptyState icon={CalendarDays} title="No upcoming fixtures" description="There are currently no scheduled fixtures in this competition." />
          ) : (
            <CompetitionFixtureTimeline fixtures={scheduleFixtures} fallbackSportSlug={sport.slug} aiReady={aiReady} />
          )}
        </MissionSection>
      )}

      {activeTab === 'results' && (
        <MissionSection title="Recent Results" subtitle={`${completed.length} completed`} icon={<History className="size-4" aria-hidden="true" />}>
          {completed.length === 0 ? (
            <MissionEmptyState icon={History} title="No recent results" description="Completed fixtures will appear here once available." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{completed.map((f) => cardFor(f))}</div>
          )}
        </MissionSection>
      )}

      {activeTab === 'standings' && (
        <MissionSection title="Standings" icon={<ListOrdered className="size-4" aria-hidden="true" />}>
          <CompetitionStandingsTable standings={standings} sportSlug={sport.slug} />
        </MissionSection>
      )}

      {activeTab === 'teams' && (
        <MissionSection title="Teams" subtitle={`${teams.length} in this competition`} icon={<Users className="size-4" aria-hidden="true" />}>
          {teams.length === 0 ? (
            <MissionEmptyState icon={Users} title="No teams yet" description="TitanIQ has not received team data for this competition yet." />
          ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {teams.map((team) => (
              <Link
                key={team.id}
                to={`/app/${sport.slug}/teams/${team.id}`}
                className="group flex items-center gap-3 rounded-[var(--cd-radius-md)] border p-3 transition-colors duration-[var(--cd-motion-base)]"
                style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}
              >
                <span
                  className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-[var(--cd-radius-sm)] border"
                  style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-3)' }}
                >
                  {team.logoUrl ? (
                    <img src={team.logoUrl} alt="" className="size-6 object-contain" loading="lazy" />
                  ) : (
                    <span aria-hidden="true" className="font-[var(--cd-font-display)] text-[13px] font-semibold" style={{ color: domainColor }}>
                      {team.name.charAt(0).toUpperCase()}
                    </span>
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-[var(--cd-font-body)] text-[13.5px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                    {team.name}
                  </span>
                  {team.rank !== null && (
                    <span className="font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
                      Rank {team.rank}
                    </span>
                  )}
                </span>
              </Link>
            ))}
          </div>
          )}
        </MissionSection>
      )}
    </div>
  )
}
