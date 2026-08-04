import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  Sparkles,
  MapPin,
  CalendarClock,
  Waypoints,
  Radio,
  Users,
  MessageSquareText,
  Compass,
  Lock,
} from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { graphApi } from '@/lib/api/graph'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { fixtureScores, countdownLabel } from '@/lib/sports-status'
import { ApiError } from '@/lib/api/client'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinityBadge, DOMAIN_COLOR_VAR, type DomainKey } from '@/components/infinity/primitives/badge'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityFollowButton } from '@/components/infinity/primitives/follow-button'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { InfinityEvidenceExplorer } from '@/components/infinity/evidence-explorer'
import type { FixtureSummaryDto, PredictionMarketDto } from '@/lib/api/types'

function isLiveStatus(status: string) {
  return status.toLowerCase() === 'live' || status.toLowerCase() === 'in_play'
}

/** Football insight types beyond Match Winner that TitanIQ's market catalog doesn't have yet —
 * shown as an honest roadmap, never as a fake interactive option, so the selector communicates
 * "more is coming" without pretending a market exists that the backend can't actually generate. */
const UPCOMING_FOOTBALL_INSIGHTS = ['Goals', 'Both Teams to Score', 'Correct Score', 'Double Chance', 'Handicap', 'Corners', 'Cards']

export default function MatchDetailPage() {
  const sport = useSportParam()
  const { matchId } = useParams<{ matchId: string }>()
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)
  const watchlist = useWatchlist()

  const fixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', matchId],
    queryFn: () => sportsApi.getFixture(matchId!),
    enabled: !!matchId,
  })

  useRealtimeInvalidate('matches', [['sports', 'fixture', matchId]], matchId ? `fixture_id=eq.${matchId}` : undefined)

  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })

  useRealtimeInvalidate(
    'predictionMarkets',
    [['markets', sport?.code, 'production']],
    sport ? `sport_code=eq.${sport.code}` : undefined,
  )

  const generateIntelligence = useMutation({
    mutationFn: (marketKey: string) =>
      predictionsApi.generate({
        market_key: marketKey,
        entity_type: 'fixture',
        entity_id: matchId!,
        subject_ref: matchId!,
      }),
  })

  const fixture = fixtureQuery.data

  const homeFixturesQuery = useQuery({
    queryKey: ['sports', 'team-fixtures', fixture?.home_team.id],
    queryFn: () => sportsApi.teamFixtures(fixture!.home_team.id, 5),
    enabled: !!fixture,
  })
  const awayFixturesQuery = useQuery({
    queryKey: ['sports', 'team-fixtures', fixture?.away_team.id],
    queryFn: () => sportsApi.teamFixtures(fixture!.away_team.id, 5),
    enabled: !!fixture,
  })

  const kgNodeQuery = useQuery({
    queryKey: ['graph', 'entity', 'match', matchId],
    queryFn: () => graphApi.getEntity('match', matchId!),
    enabled: !!matchId,
    retry: false,
  })
  const kgContextQuery = useQuery({
    queryKey: ['graph', 'context', kgNodeQuery.data?.id],
    queryFn: () => graphApi.context(kgNodeQuery.data!.id, { depth: 1, max_nodes: 12 }),
    enabled: !!kgNodeQuery.data,
  })

  if (!sport) return null

  if (fixtureQuery.isPending) {
    return (
      <div className="space-y-4">
        <InfinitySkeleton className="h-8 w-64" />
        <InfinitySkeleton className="h-40" />
      </div>
    )
  }

  if (fixtureQuery.isError) {
    return <ErrorState error={fixtureQuery.error} onRetry={() => void fixtureQuery.refetch()} />
  }

  if (!fixture) return null

  const markets = marketsQuery.data ?? []
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  const tone = DOMAIN_COLOR_VAR[domain]
  const live = isLiveStatus(fixture.status)
  const isCompleted = fixture.status.toLowerCase() === 'completed'
  const aiAvailable = markets.length > 0
  const countdown = !live && !isCompleted ? countdownLabel(fixture.scheduled_at) : null
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const hasFinalScore = homeScore !== undefined && awayScore !== undefined

  const kgNotFound = kgNodeQuery.isError && kgNodeQuery.error instanceof ApiError && kgNodeQuery.error.status === 404
  const kgOtherError = kgNodeQuery.isError && !kgNotFound

  function handleSelectMarket(marketKey: string) {
    setSelectedMarketKey(marketKey)
    generateIntelligence.reset()
  }

  return (
    <div className="max-w-7xl space-y-8">
      <Link
        to={`/app/${sport.slug}/matches`}
        className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
      >
        <ArrowLeft className="size-3.5" /> Back to matches
      </Link>

      {/* Match Hero */}
      <InfinityPanel tone={tone} glow={live} className={live ? 'shadow-[var(--infinity-elevation-live)]' : undefined}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <InfinityLabel tone={tone}>{fixture.competition_name}</InfinityLabel>
          <div className="flex items-center gap-2">
            {aiAvailable && <InfinityBadge tone="var(--infinity-signal)">AI Available</InfinityBadge>}
            {live ? (
              <InfinityBadge tone="var(--infinity-live)">Live</InfinityBadge>
            ) : (
              <InfinityBadge domain={domain}>{fixture.status}</InfinityBadge>
            )}
          </div>
        </div>

        <div className="mt-6 flex flex-col items-center gap-6 lg:flex-row lg:items-center lg:justify-center lg:gap-16">
          <div className="flex items-center justify-center gap-4 sm:gap-8 lg:gap-12">
            <TeamCrestLarge name={fixture.home_team.name} logoUrl={fixture.home_team.logo_url} />
            <div className="text-center">
              {hasFinalScore ? (
                <p className="font-infinity-display text-2xl font-semibold tabular-nums text-infinity-text-primary sm:text-3xl lg:text-4xl">
                  {homeScore} <span className="text-infinity-text-muted">–</span> {awayScore}
                </p>
              ) : (
                <p className="font-infinity-mono text-[11px] uppercase tracking-[0.1em] text-infinity-text-muted">vs</p>
              )}
              {countdown && (
                <p className="mt-1 whitespace-nowrap font-infinity-mono text-[11px] text-infinity-signal">Kicks off in {countdown}</p>
              )}
            </div>
            <TeamCrestLarge name={fixture.away_team.name} logoUrl={fixture.away_team.logo_url} />
          </div>

          <div className="hidden h-20 w-px shrink-0 bg-infinity-border-hairline lg:block" aria-hidden="true" />

          <div className="flex flex-col items-center gap-3 lg:items-start">
            <h1 className="text-center font-infinity-display text-xl font-semibold text-infinity-text-primary sm:text-2xl lg:text-left">
              {fixture.home_team.name} <span className="text-infinity-text-muted">vs</span> {fixture.away_team.name}
            </h1>
            <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 font-infinity-mono text-[12px] text-infinity-text-secondary lg:justify-start">
              <span className="inline-flex items-center gap-1.5">
                <CalendarClock className="size-3.5 text-infinity-text-muted" aria-hidden="true" />
                {new Date(fixture.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
              </span>
              {fixture.venue_name && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="size-3.5 text-infinity-text-muted" aria-hidden="true" />
                  {fixture.venue_name}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3 lg:justify-start">
              <InfinityFollowButton
                following={watchlist.isFollowing('fixture', fixture.id)}
                onToggle={() => watchlist.toggle('fixture', fixture.id)}
                label={`${fixture.home_team.name} vs ${fixture.away_team.name}`}
              />
              <Link
                to={`/app/insights?pin_type=fixture&pin_id=${fixture.id}`}
                className="inline-flex items-center gap-1.5 rounded-infinity-sm border border-infinity-signal-muted px-2.5 py-1.5 font-infinity-body text-[12px] font-medium text-infinity-signal transition-colors hover:bg-infinity-signal-muted"
              >
                <MessageSquareText className="size-3.5" aria-hidden="true" />
                Ask the Assistant about this match
              </Link>
            </div>
            <p className="text-center font-infinity-body text-[11px] text-infinity-text-muted lg:text-left">
              Follow this match to get notified at kickoff, full time, and if the AI verdict changes.
            </p>
          </div>
        </div>
      </InfinityPanel>

      <div className="grid gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
          {/* AI Match Intelligence */}
          <div>
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="size-4 text-infinity-signal" aria-hidden="true" />
              <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">AI Match Intelligence</p>
            </div>

            <InfinityPanel tone="var(--infinity-domain-predictions)">
              <p className="font-infinity-body text-[13px] text-infinity-text-secondary">
                Ask TitanIQ what it expects for this match — pick what you want intelligence on, and get a verdict, its
                confidence, and the reasoning behind it.
              </p>

              {domain === 'football' && markets.length > 0 && (
                <div className="mt-4">
                  <p className="font-infinity-body text-[11px] text-infinity-text-muted">More intelligence types on the way:</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {UPCOMING_FOOTBALL_INSIGHTS.filter(
                      (label) => !markets.some((market) => market.name.toLowerCase().includes(label.toLowerCase())),
                    ).map((label) => (
                      <span
                        key={label}
                        className="inline-flex items-center gap-1 rounded-full border border-infinity-border-hairline px-2.5 py-1 font-infinity-body text-[11px] text-infinity-text-muted"
                        title={`${label} intelligence isn't built yet`}
                      >
                        <Lock className="size-2.5" aria-hidden="true" />
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {marketsQuery.isPending && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <InfinitySkeleton key={i} className="h-20" />
                  ))}
                </div>
              )}

              {marketsQuery.isError && (
                <div className="mt-4">
                  <ErrorState error={marketsQuery.error} onRetry={() => void marketsQuery.refetch()} />
                </div>
              )}

              {markets.length === 0 && !marketsQuery.isPending && !marketsQuery.isError && (
                <div className="mt-4">
                  <InfinityEmptyState
                    icon={Sparkles}
                    title="Intelligence isn't available for this sport yet"
                    description={`TitanIQ hasn't finished building out AI intelligence for ${sport.label} — it's coming.`}
                  />
                </div>
              )}

              {markets.length > 0 && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {markets.map((market) => (
                    <MarketTile
                      key={market.id}
                      market={market}
                      selected={selectedMarketKey === market.market_key}
                      onSelect={() => handleSelectMarket(market.market_key)}
                    />
                  ))}
                </div>
              )}

              {selectedMarketKey && !generateIntelligence.data && (
                <InfinityButton
                  className="mt-4"
                  onClick={() => generateIntelligence.mutate(selectedMarketKey)}
                  disabled={generateIntelligence.isPending}
                >
                  {generateIntelligence.isPending ? 'Analyzing…' : 'Generate Intelligence'}
                </InfinityButton>
              )}

              {generateIntelligence.isError && (
                <div className="mt-4">
                  <ErrorState error={generateIntelligence.error} onRetry={() => generateIntelligence.mutate(selectedMarketKey!)} />
                </div>
              )}

              {generateIntelligence.data && (
                <div className="mt-6 border-t border-infinity-border-hairline pt-5">
                  <InfinityEvidenceExplorer
                    prediction={generateIntelligence.data}
                    variant="full"
                    homeTeam={{ name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }}
                    awayTeam={{ name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }}
                  />
                </div>
              )}
            </InfinityPanel>
          </div>

          {/* Recent form (home + away) */}
          <div>
            <div className="mb-4 flex items-center gap-2">
              <Radio className="size-4 text-infinity-text-muted" aria-hidden="true" />
              <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Recent form</p>
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <FormColumn
                teamName={fixture.home_team.name}
                label="Home form"
                sportSlug={sport.slug}
                domain={domain}
                query={homeFixturesQuery}
                excludeId={fixture.id}
              />
              <FormColumn
                teamName={fixture.away_team.name}
                label="Away form"
                sportSlug={sport.slug}
                domain={domain}
                query={awayFixturesQuery}
                excludeId={fixture.id}
              />
            </div>
          </div>

          {/* Match Coverage */}
          <div>
            <div className="mb-4 flex items-center gap-2">
              <Compass className="size-4 text-infinity-text-muted" aria-hidden="true" />
              <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Match coverage</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <InfinityEmptyState
                icon={Radio}
                title="Live match events"
                description="Live match events, goals, and match statistics will appear here once the match kicks off."
              />
              <InfinityEmptyState
                icon={Users}
                title="Lineups"
                description="Expected lineups become available approximately one hour before kickoff."
              />
            </div>
          </div>
        </div>

        {/* Match Context (right rail) */}
        <div className="lg:col-span-1">
          <div className="lg:sticky lg:top-6">
            <div className="mb-4 flex items-center gap-2">
              <Waypoints className="size-4 text-infinity-text-muted" aria-hidden="true" />
              <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Match context</p>
            </div>
            {kgNodeQuery.isPending && <InfinitySkeleton className="h-24" />}
            {kgNotFound && (
              <InfinityEmptyState
                icon={Waypoints}
                title="Still building context for this fixture"
                description="Historical relationship data is still growing for this fixture — check back closer to kickoff."
              />
            )}
            {kgOtherError && <ErrorState error={kgNodeQuery.error} onRetry={() => void kgNodeQuery.refetch()} />}
            {kgNodeQuery.data && (
              <InfinityPanel tone="var(--infinity-domain-knowledge-graph)">
                {kgContextQuery.isPending && <InfinitySkeleton className="h-12" />}
                {kgContextQuery.data && (() => {
                  const related = Object.entries(kgContextQuery.data.related_by_type)
                  const total = related.reduce((sum, [, nodes]) => sum + nodes.length, 0)
                  if (total === 0) {
                    return (
                      <p className="font-infinity-body text-[12px] text-infinity-text-secondary">
                        Historical relationship data is still growing for this fixture.
                      </p>
                    )
                  }
                  return (
                    <>
                      <p className="font-infinity-body text-[12px] text-infinity-text-secondary">
                        TitanIQ has connected this match to {total} related {total === 1 ? 'entity' : 'entities'} it uses
                        to build understanding — the more connected a match, the more context feeds into its
                        intelligence.
                      </p>
                      <ul className="mt-3 flex flex-wrap gap-2">
                        {related.map(([type, nodes]) => (
                          <li key={type}>
                            <InfinityBadge domain="knowledge-graph">
                              {nodes.length} {humanizePlural(type, nodes.length)}
                            </InfinityBadge>
                          </li>
                        ))}
                      </ul>
                    </>
                  )
                })()}
              </InfinityPanel>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function TeamCrestLarge({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  return (
    <div className="flex flex-col items-center gap-2">
      {logoUrl ? (
        <img src={logoUrl} alt="" className="size-14 shrink-0 object-contain sm:size-20" loading="lazy" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-14 shrink-0 items-center justify-center rounded-full bg-infinity-ground-2 font-infinity-display text-xl font-semibold text-infinity-text-muted sm:size-20 sm:text-2xl"
        >
          {name.charAt(0).toUpperCase()}
        </span>
      )}
      <p className="max-w-[7rem] truncate font-infinity-body text-[12px] font-medium text-infinity-text-secondary sm:max-w-[9rem] sm:text-[13px]">
        {name}
      </p>
    </div>
  )
}

function humanizePlural(nodeType: string, count: number): string {
  const label = nodeType.replace(/_/g, ' ')
  if (count === 1 || label.endsWith('s')) return label
  return `${label}s`
}

function FormColumn({
  teamName,
  label,
  sportSlug,
  domain,
  query,
  excludeId,
}: {
  teamName: string
  label: string
  sportSlug: string
  domain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  query: { isPending: boolean; data: FixtureSummaryDto[] | undefined }
  excludeId: string
}) {
  const fixtures = (query.data ?? []).filter((f) => f.id !== excludeId)
  return (
    <div>
      <p className="mb-2 font-infinity-mono text-[11px] uppercase tracking-[0.06em] text-infinity-text-muted">
        {label} · {teamName}
      </p>
      {query.isPending && (
        <div className="space-y-3">
          <InfinitySkeleton className="h-20" />
          <InfinitySkeleton className="h-20" />
        </div>
      )}
      {!query.isPending && fixtures.length === 0 && (
        <InfinityEmptyState
          icon={Radio}
          title="No recent matches yet"
          description={`${teamName} doesn't have a past match under coverage yet.`}
        />
      )}
      {!query.isPending && fixtures.length > 0 && (
        <div className="space-y-3">
          {fixtures.slice(0, 4).map((m) => {
            const { homeScore, awayScore } = fixtureScores(m.final_state)
            return (
              <InfinityMatchCard
                key={m.id}
                sport={domain}
                competition={m.competition_name}
                competitionLogoUrl={m.competition_logo_url}
                status={isLiveStatus(m.status) ? 'live' : m.status.toLowerCase() === 'completed' ? 'completed' : 'upcoming'}
                kickoff={new Date(m.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                venue={m.venue_name}
                homeTeam={m.home_team.name}
                awayTeam={m.away_team.name}
                homeScore={homeScore}
                awayScore={awayScore}
                homeLogoUrl={m.home_team.logo_url}
                awayLogoUrl={m.away_team.logo_url}
                href={`/app/${sportSlug}/matches/${m.id}`}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function MarketTile({ market, selected, onSelect }: { market: PredictionMarketDto; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`rounded-infinity-md border p-3.5 text-left transition-colors ${
        selected
          ? 'border-infinity-signal bg-infinity-signal-muted'
          : 'border-infinity-border-default hover:border-infinity-border-strong'
      }`}
    >
      <p className="font-infinity-display text-[13px] font-semibold text-infinity-text-primary">{market.name}</p>
      <p className="mt-1.5 font-infinity-body text-[12px] text-infinity-text-secondary">{market.description}</p>
      <p className="mt-2 font-infinity-mono text-[10px] text-infinity-text-muted">
        Only published when TitanIQ is at least {Math.round(market.confidence_threshold * 100)}% confident
      </p>
    </button>
  )
}
