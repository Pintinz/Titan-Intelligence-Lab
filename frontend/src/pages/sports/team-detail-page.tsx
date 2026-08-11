import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  Sparkles,
  MapPin,
  Share2,
  Users,
  CalendarClock,
  Radio,
  Newspaper,
  Waypoints,
  TrendingUp,
  TrendingDown,
  Minus,
  Shield,
  Target,
  Flag,
  Swords,
  Lock,
  Home as HomeIcon,
  Plane,
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
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { intelligenceApi } from '@/lib/api/intelligence'
import { graphApi } from '@/lib/api/graph'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useCrestAccentColor } from '@/lib/hooks/use-crest-accent-color'
import { fixtureScores } from '@/lib/sports-status'
import { ApiError } from '@/lib/api/client'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { cn } from '@/lib/cn'
import { InfinityBadge, DOMAIN_COLOR_VAR, type DomainKey } from '@/components/infinity/primitives/badge'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityFollowButton } from '@/components/infinity/primitives/follow-button'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityPlayerCard } from '@/components/infinity/cards/player-card'
import { CompetitionFixtureTimeline } from '@/components/command-deck/competition-fixture-timeline'
import { MatchSnapshotCard } from '@/components/command-deck/match-snapshot-card'
import { SeasonFilter } from '@/components/command-deck/season-filter'
import type { FixtureSummaryDto, NewsEventDto, TeamStatisticsSummaryDto } from '@/lib/api/types'

type Domain = Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
type Outcome = 'W' | 'D' | 'L'

const OUTCOME_TONE: Record<Outcome, string> = {
  W: 'var(--infinity-success)',
  D: 'var(--infinity-text-muted)',
  L: 'var(--infinity-danger)',
}

const SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'statistics', label: 'Statistics' },
  { id: 'squad', label: 'Squad' },
  { id: 'fixtures', label: 'Fixtures' },
  { id: 'news', label: 'News' },
] as const

export default function TeamDetailPage() {
  const sport = useSportParam()
  const { teamId } = useParams<{ teamId: string }>()
  const watchlist = useWatchlist()
  const [shareCopied, setShareCopied] = useState(false)
  const [recentSeasonFilter, setRecentSeasonFilter] = useState<string | null>(null)

  const teamQuery = useQuery({
    queryKey: ['sports', 'team', teamId],
    queryFn: () => sportsApi.getTeam(teamId!),
    enabled: !!teamId,
  })
  const recentQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'fixtures', 'recent'],
    queryFn: () => sportsApi.teamFixtures(teamId!, 30, 'recent'),
    enabled: !!teamId,
  })
  const upcomingQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'fixtures', 'upcoming'],
    queryFn: () => sportsApi.teamFixtures(teamId!, 8, 'upcoming'),
    enabled: !!teamId,
  })
  // Team has no competition_id of its own — the real, honest way to a league position is via
  // whichever competition its own real fixtures belong to, not a guess.
  const standingsCompetitionId = recentQuery.data?.[0]?.competition_id ?? upcomingQuery.data?.[0]?.competition_id ?? null
  const standingsQuery = useQuery({
    queryKey: ['sports', 'competition', standingsCompetitionId, 'standings'],
    queryFn: () => sportsApi.competitionStandings(standingsCompetitionId!),
    enabled: !!standingsCompetitionId,
  })
  const playersQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'players'],
    queryFn: () => sportsApi.teamPlayers(teamId!),
    enabled: !!teamId,
  })
  const statsQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'statistics'],
    queryFn: () => sportsApi.teamStatistics(teamId!, 20),
    enabled: !!teamId,
  })
  const injuriesQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'injuries'],
    queryFn: () => sportsApi.teamInjuries(teamId!),
    enabled: !!teamId,
  })
  const transfersQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'transfers'],
    queryFn: () => sportsApi.teamTransfers(teamId!),
    enabled: !!teamId,
  })
  const coachingStaffQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'coaching-staff'],
    queryFn: () => sportsApi.teamCoachingStaff(teamId!),
    enabled: !!teamId,
  })
  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })
  const newsQuery = useQuery({
    queryKey: ['intelligence', 'news', 'entity', teamId],
    queryFn: () => intelligenceApi.newsForEntity(teamId!, 8),
    enabled: !!teamId,
  })
  const sentimentQuery = useQuery({
    queryKey: ['intelligence', 'sentiment', teamId],
    queryFn: () => intelligenceApi.sentiment(teamId!, 1),
    enabled: !!teamId,
  })
  const kgNodeQuery = useQuery({
    queryKey: ['graph', 'entity', 'team', teamId],
    queryFn: () => graphApi.getEntity('team', teamId!),
    enabled: !!teamId,
    retry: false,
  })
  const kgContextQuery = useQuery({
    queryKey: ['graph', 'context', kgNodeQuery.data?.id],
    queryFn: () => graphApi.context(kgNodeQuery.data!.id, { depth: 1, max_nodes: 12 }),
    enabled: !!kgNodeQuery.data,
  })

  const analytics = useMemo(
    () => (teamId && recentQuery.data ? computeTeamAnalytics(recentQuery.data, teamId) : null),
    [recentQuery.data, teamId],
  )

  // Called unconditionally, ahead of the pending/error early-returns below, per the Rules of
  // Hooks — falls back to the sport's domain color (or the signal accent, pre-`sport`) until the
  // team's real crest has loaded.
  const heroRef = useRef<HTMLDivElement>(null)
  const heroFallbackTone = sport ? DOMAIN_COLOR_VAR[sport.slug as Domain] : 'var(--infinity-signal)'
  const heroAccent = useCrestAccentColor(teamQuery.data?.logo_url, heroFallbackTone)
  const heroParallax = useHeroParallax(heroRef)

  if (!sport) return null

  if (teamQuery.isPending) {
    return (
      <div className="mx-auto max-w-7xl space-y-4">
        <InfinitySkeleton className="h-8 w-64" />
        <InfinitySkeleton className="h-48" />
      </div>
    )
  }
  if (teamQuery.isError) return <ErrorState error={teamQuery.error} onRetry={() => void teamQuery.refetch()} />

  const team = teamQuery.data
  const domain = sport.slug as Domain
  const tone = DOMAIN_COLOR_VAR[domain]
  const markets = marketsQuery.data ?? []
  const aiAvailable = markets.length > 0
  const nextFixture = upcomingQuery.data?.[0]
  const following = teamId ? watchlist.isFollowing('team', teamId) : false
  // Only a completed fixture with a real recorded score becomes a Recent Form snapshot — never
  // fabricate a 0-0 for a match whose result somehow isn't in yet.
  const completedFixtures = (recentQuery.data ?? [])
    .filter((f) => f.status.toLowerCase() === 'completed')
    .map((f) => ({ fixture: f, scores: fixtureScores(f.final_state) }))
    .filter(
      (row): row is { fixture: FixtureSummaryDto; scores: { homeScore: number; awayScore: number } } =>
        row.scores.homeScore !== undefined && row.scores.awayScore !== undefined,
    )
  // One chip per season — a team's fixture history reads as seasons, not an endless scroll. The
  // calendar year a fixture falls in stands in for its season label.
  const recentSeasonCounts = (() => {
    const map = new Map<string, { key: string; label: string; count: number }>()
    for (const { fixture } of completedFixtures) {
      const key = String(new Date(fixture.scheduled_at).getFullYear())
      if (!map.has(key)) map.set(key, { key, label: key, count: 0 })
      map.get(key)!.count += 1
    }
    return [...map.values()]
  })()
  const visibleRecentFixtures = recentSeasonFilter
    ? completedFixtures.filter(({ fixture }) => String(new Date(fixture.scheduled_at).getFullYear()) === recentSeasonFilter)
    : completedFixtures
  const upcomingFixtures = upcomingQuery.data ?? []

  // Real-derived Hero command-center values — every one traces back to `analytics`/`stats`
  // (already computed from real fixtures/match-statistics elsewhere on this page) or a real
  // standings lookup; nothing here is invented.
  const teamStanding = standingsQuery.data?.find((s) => s.team_id === team.id)
  const goalsPerMatch = analytics && analytics.overall.played > 0 ? analytics.overall.gf / analytics.overall.played : null
  const concededPerMatch = analytics && analytics.overall.played > 0 ? analytics.overall.ga / analytics.overall.played : null
  const cleanSheetRate = analytics ? pct(analytics.cleanSheets, analytics.overall.played) : null
  const overallPpg = analytics ? ppgValue(analytics.overall) : null
  const momentumDirection = analytics ? (analytics.last5Points > analytics.prior5Points ? 'up' : analytics.last5Points < analytics.prior5Points ? 'down' : 'flat') : null
  const quickInsights =
    analytics && analytics.sampleSize > 0 ? buildQuickInsights(analytics, upcomingQuery.data ?? [], sentimentQuery.data?.[0]) : []

  function handleShare() {
    const url = window.location.href
    if (navigator.share) {
      void navigator.share({ title: team.name, url }).catch(() => {})
      return
    }
    void navigator.clipboard.writeText(url).then(() => {
      setShareCopied(true)
      setTimeout(() => setShareCopied(false), 2000)
    })
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <Link
        to={`/app/${sport.slug}/teams`}
        className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
      >
        <ArrowLeft className="size-3.5" /> Back to teams
      </Link>

      {/* Hero — an immersive, per-club atmosphere rather than the corner-tick panel language
          used everywhere else on this page; the identity moment gets its own visual register.
          The ambient tint is sampled from the team's own real crest (useCrestAccentColor), so
          every club's hero looks genuinely distinct without a hardcoded color table. Text and
          surfaces are pinned to a dark, photographic treatment regardless of site theme — the
          backdrop is always dark, so the content over it stays dark-mode too (the same
          convention a hero photo uses on an otherwise light page). */}
      <div ref={heroRef} id="overview" className="relative scroll-mt-24 overflow-hidden rounded-infinity-md border border-white/10">
        <StadiumBackdrop tone={heroAccent} parallax={heroParallax} />

        <div className="relative z-10 p-6 sm:p-10">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <InfinityLabel tone="rgba(255,255,255,0.7)">Team Intelligence</InfinityLabel>
            <div className="flex flex-wrap items-center gap-1.5">
              {aiAvailable && <InfinityBadge tone="var(--infinity-signal)">AI Active</InfinityBadge>}
              {analytics && analytics.sampleSize > 0 && (
                <InfinityBadge tone="#c8d2e0">
                  {analytics.sampleSize} {analytics.sampleSize === 1 ? 'match' : 'matches'} tracked
                </InfinityBadge>
              )}
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-5 lg:flex-row lg:items-stretch">
            <div className="relative flex flex-1 items-start gap-4 overflow-hidden rounded-infinity-md border border-white/10 bg-white/[0.06] p-5 shadow-[0_8px_32px_rgba(0,0,0,0.35)] backdrop-blur-xl">
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 top-0 h-[2px]"
                style={{ background: `linear-gradient(90deg, ${heroAccent}, transparent)` }}
              />
              <TeamCrestLarge name={team.name} logoUrl={team.logo_url} />
              <div className="min-w-0">
                <h1 className="font-infinity-display text-2xl font-semibold text-white sm:text-3xl">{team.name}</h1>
                {(team.country || team.venue_name) && (
                  <p className="mt-1 flex flex-wrap items-center gap-1.5 font-infinity-mono text-[12px] text-white/60">
                    <MapPin className="size-3.5 text-white/40" aria-hidden="true" />
                    {[team.country, team.venue_name].filter(Boolean).join(' · ')}
                    {teamStanding && <span className="text-white/45">· #{teamStanding.rank} in table</span>}
                  </p>
                )}
                {analytics && analytics.sampleSize > 0 && (
                  <div className="mt-3">
                    <FormRibbon form={analytics.formRecentFirst.slice(0, 5)} labelTone="rgba(255,255,255,0.55)" />
                  </div>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <InfinityFollowButton following={following} onToggle={() => teamId && watchlist.toggle('team', teamId)} label={team.name} />
                  <InfinityButton size="sm" variant="secondary" onClick={handleShare}>
                    <Share2 className="size-3.5" aria-hidden="true" />
                    {shareCopied ? 'Link copied' : 'Share'}
                  </InfinityButton>
                </div>
              </div>
            </div>

            <div className="w-full rounded-infinity-md border border-white/10 bg-white/[0.06] p-4 shadow-[0_8px_32px_rgba(0,0,0,0.35)] backdrop-blur-xl lg:w-80 lg:shrink-0">
              <div className="flex items-center gap-1.5">
                <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-white/60 motion-reduce:animate-none" aria-hidden="true" />
                <InfinityLabel tone="rgba(255,255,255,0.7)">Next fixture</InfinityLabel>
              </div>
              {upcomingQuery.isPending && <InfinitySkeleton className="mt-2 h-24" />}
              {!upcomingQuery.isPending && !nextFixture && (
                <p className="mt-2 font-infinity-body text-[13px] text-white/60">No upcoming fixture under coverage yet.</p>
              )}
              {nextFixture && (
                <div className="mt-2">
                  <p className="font-infinity-body text-[11px] text-white/50">{nextFixture.competition_name}</p>
                  <p className="mt-1 font-infinity-display text-[15px] font-semibold text-white">
                    {nextFixture.home_team.id === team.id ? `vs ${nextFixture.away_team.name}` : `@ ${nextFixture.home_team.name}`}
                  </p>
                  <p className="mt-1.5 flex items-center gap-1.5 font-infinity-mono text-[11px] text-white/60">
                    <CalendarClock className="size-3.5 text-white/40" aria-hidden="true" />
                    {new Date(nextFixture.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                  </p>
                  {nextFixture.venue_name && (
                    <p className="mt-1 flex items-center gap-1.5 font-infinity-mono text-[11px] text-white/60">
                      <MapPin className="size-3.5 text-white/40" aria-hidden="true" />
                      {nextFixture.venue_name}
                    </p>
                  )}
                  <Link to={`/app/${nextFixture.sport_code ?? sport.slug}/matches/${nextFixture.id}`} className="mt-3 block">
                    <InfinityButton size="sm" className="w-full">
                      View match &amp; AI intelligence
                    </InfinityButton>
                  </Link>
                </div>
              )}
            </div>
          </div>

          {analytics && analytics.sampleSize > 0 && (
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <HeroMetricTile icon={Flag} label="Team strength" value={overallPpg !== null ? overallPpg.toFixed(2) : '—'} sublabel={strengthTierLabel(overallPpg)} tone={heroAccent} />
              <HeroMetricTile
                icon={Swords}
                label="Attack"
                value={goalsPerMatch !== null ? goalsPerMatch.toFixed(1) : '—'}
                sublabel={goalsPerMatch !== null ? `${attackTierLabel(goalsPerMatch)} · goals/game` : undefined}
              />
              <HeroMetricTile
                icon={Shield}
                label="Defence"
                value={concededPerMatch !== null ? concededPerMatch.toFixed(1) : '—'}
                sublabel={cleanSheetRate !== null ? `${defenceTierLabel(cleanSheetRate)} · conceded/game` : undefined}
              />
              <HeroMetricTile
                icon={momentumDirection === 'up' ? TrendingUp : momentumDirection === 'down' ? TrendingDown : Minus}
                label="Momentum"
                value={momentumDirection === 'up' ? 'Rising' : momentumDirection === 'down' ? 'Cooling' : 'Steady'}
                sublabel={`${analytics.last5Points} pts last 5`}
                tone={momentumDirection === 'up' ? 'var(--infinity-success)' : momentumDirection === 'down' ? 'var(--infinity-danger)' : undefined}
              />
              <HeroMetricTile icon={HomeIcon} label="Home PPG" value={ppg(analytics.home)} sublabel={`${analytics.home.played} played`} />
              <HeroMetricTile icon={Plane} label="Away PPG" value={ppg(analytics.away)} sublabel={`${analytics.away.played} played`} />
              <HeroMetricTile icon={Target} label="Goals / game" value={goalsPerMatch !== null ? goalsPerMatch.toFixed(1) : '—'} sublabel={`${analytics.overall.gf} total`} />
              <HeroMetricTile icon={Shield} label="Clean sheet %" value={cleanSheetRate !== null ? `${cleanSheetRate}%` : '—'} sublabel={`${analytics.cleanSheets} of ${analytics.overall.played}`} />
            </div>
          )}

          {analytics && analytics.sampleSize > 0 && (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <div className="relative overflow-hidden rounded-infinity-md border border-white/10 bg-white/[0.06] p-4 backdrop-blur-xl">
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 opacity-60"
                  style={{ backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.14) 1px, transparent 1px)', backgroundSize: '16px 16px' }}
                />
                <div className="relative">
                  <InfinityLabel tone="rgba(255,255,255,0.7)">Team DNA</InfinityLabel>
                  <div className="mt-3 space-y-3">
                    {statsQuery.data && statsQuery.data.possession_pct !== null ? (
                      <HeroDnaBar label="Possession" valuePct={statsQuery.data.possession_pct} tone="var(--infinity-signal)" />
                    ) : (
                      <HeroDnaPending label="Possession" />
                    )}
                    {statsQuery.data && statsQuery.data.corners !== null ? (
                      <HeroDnaBar
                        label="Set-piece frequency"
                        valuePct={Math.min(100, (statsQuery.data.corners / 8) * 100)}
                        sublabel={`${statsQuery.data.corners.toFixed(1)} corners / game`}
                        tone="var(--infinity-success)"
                      />
                    ) : (
                      <HeroDnaPending label="Set-piece frequency" />
                    )}
                    <HeroDnaPending label="Pressing intensity" />
                    <HeroDnaPending label="Counter-attack frequency" />
                  </div>
                </div>
              </div>

              <div className="rounded-infinity-md border border-white/10 bg-white/[0.06] p-4 backdrop-blur-xl">
                <InfinityLabel tone="rgba(255,255,255,0.7)">AI quick insights</InfinityLabel>
                <ul className="mt-3 space-y-2">
                  {quickInsights.map((insight, i) => (
                    <li
                      key={i}
                      className="-mx-1.5 flex items-start gap-2 rounded-infinity-sm px-1.5 py-0.5 font-infinity-body text-[12px] leading-snug text-white/70 transition-colors duration-150 hover:bg-white/[0.05]"
                    >
                      <Sparkles className="mt-0.5 size-3 shrink-0 text-white/40" aria-hidden="true" />
                      {insight}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Section nav — the app shell scrolls an inner `overflow-y-auto` <main>, not `window`, so a
          plain `href="#id"` anchor jump doesn't reliably reach it; scrollIntoView targets whichever
          ancestor actually scrolls and still honors each section's scroll-mt. */}
      <nav className="-mx-1 flex gap-1 overflow-x-auto border-b border-infinity-border-hairline px-1 py-2">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            onClick={(e) => {
              e.preventDefault()
              document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }}
            className="shrink-0 whitespace-nowrap rounded-infinity-sm px-3 py-1.5 font-infinity-body text-[12px] font-medium text-infinity-text-secondary transition-colors hover:bg-infinity-ground-2 hover:text-infinity-text-primary"
          >
            {section.label}
          </a>
        ))}
      </nav>

      <div className="space-y-10">
        {/* Season Analytics */}
        <div id="analytics" className="scroll-mt-24">
          <SectionHeading icon={Flag} title="Season analytics" tone={tone} />
          {analytics && analytics.sampleSize > 0 ? (
            <SeasonAnalyticsSection analytics={analytics} />
          ) : (
            <InfinityEmptyState icon={Flag} title="No season totals yet" description="Season analytics build up as completed matches come under coverage." />
          )}
        </div>

        {/* Statistics */}
        <div id="statistics" className="scroll-mt-24">
          <SectionHeading icon={Target} title="Statistics" tone={tone} />
          {statsQuery.isPending && <MetricGridSkeleton count={4} />}
          {statsQuery.data && analytics && (
            <StatisticsSection analytics={analytics} stats={statsQuery.data} />
          )}
        </div>

        {/* Squad Intelligence */}
        <div id="squad" className="scroll-mt-24">
          <SectionHeading icon={Users} title="Squad intelligence" tone={tone} />
          {playersQuery.isPending && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <InfinitySkeleton key={i} className="h-20" />
              ))}
            </div>
          )}
          {playersQuery.data && playersQuery.data.length === 0 && (
            <InfinityEmptyState icon={Users} title="Synchronizing squad intelligence" description="TitanIQ is still building out roster coverage for this team — check back soon." />
          )}
          {playersQuery.data && playersQuery.data.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {playersQuery.data.map((player) => (
                <Link key={player.id} to={`/app/${sport.slug}/players/${player.id}`} className="block">
                  <InfinityPlayerCard name={player.name} domain={domain} team={team.name} position={player.position} />
                </Link>
              ))}
            </div>
          )}
          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            {/* Manager */}
            <div className="rounded-infinity-md border border-infinity-border-default bg-infinity-ground-1 p-4">
              <div className="mb-3 flex items-center gap-1.5">
                <UserCog className="size-3.5 text-infinity-text-muted" />
                <InfinityLabel>Manager</InfinityLabel>
              </div>
              {coachingStaffQuery.isPending && <InfinitySkeleton className="h-12" />}
              {coachingStaffQuery.data && (() => {
                const staff = coachingStaffQuery.data.data
                const current = staff.find((c) => c.id === coachingStaffQuery.data!.meta.current_coach_id)
                if (!current) {
                  return <p className="font-infinity-body text-[13px] text-infinity-text-muted">No verified manager on record.</p>
                }
                return (
                  <div>
                    <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{current.person_name}</p>
                    {current.valid_from && (
                      <p className="mt-0.5 font-infinity-body text-[12px] text-infinity-text-muted">
                        In charge since {new Date(current.valid_from).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
                      </p>
                    )}
                  </div>
                )
              })()}
            </div>

            {/* Injuries */}
            <div className="rounded-infinity-md border border-infinity-border-default bg-infinity-ground-1 p-4">
              <div className="mb-3 flex items-center gap-1.5">
                <HeartPulse className="size-3.5 text-infinity-text-muted" />
                <InfinityLabel>Injuries</InfinityLabel>
              </div>
              {injuriesQuery.isPending && <InfinitySkeleton className="h-12" />}
              {injuriesQuery.data && injuriesQuery.data.length === 0 && (
                <p className="font-infinity-body text-[13px] text-infinity-text-muted">No reported injuries.</p>
              )}
              {injuriesQuery.data && injuriesQuery.data.length > 0 && (
                <ul className="space-y-2">
                  {injuriesQuery.data.slice(0, 6).map((injury) => (
                    <li key={injury.id} className="flex items-center justify-between gap-2">
                      <span className="font-infinity-body text-[13px] text-infinity-text-primary">{injury.player_name ?? 'Unknown player'}</span>
                      <InfinityBadge tone="var(--infinity-danger)">{injury.reason ?? injury.status}</InfinityBadge>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Transfers */}
            <div className="rounded-infinity-md border border-infinity-border-default bg-infinity-ground-1 p-4">
              <div className="mb-3 flex items-center gap-1.5">
                <ArrowLeftRight className="size-3.5 text-infinity-text-muted" />
                <InfinityLabel>Recent transfers</InfinityLabel>
              </div>
              {transfersQuery.isPending && <InfinitySkeleton className="h-12" />}
              {transfersQuery.data && transfersQuery.data.length === 0 && (
                <p className="font-infinity-body text-[13px] text-infinity-text-muted">No confirmed transfers on record.</p>
              )}
              {transfersQuery.data && transfersQuery.data.length > 0 && (
                <ul className="space-y-2">
                  {transfersQuery.data.slice(0, 6).map((transfer) => {
                    const incoming = transfer.to_team_id === teamId
                    return (
                      <li key={transfer.id} className="flex items-center justify-between gap-2">
                        <span className="font-infinity-body text-[13px] text-infinity-text-primary">{transfer.player_name ?? 'Unknown player'}</span>
                        <InfinityBadge tone={incoming ? 'var(--infinity-success)' : 'var(--infinity-text-muted)'}>
                          {incoming ? 'In' : 'Out'} · {transfer.transfer_type ?? '—'}
                        </InfinityBadge>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>

        {/* Fixtures */}
        <div id="fixtures" className="command-deck scroll-mt-24 space-y-10">
          <div>
            <SectionHeading icon={Radio} title="Recent form" tone={tone} />
            {recentQuery.isPending && <MetricGridSkeleton count={3} />}
            {!recentQuery.isPending && completedFixtures.length === 0 && (
              <InfinityEmptyState
                icon={Radio}
                title="No recent fixtures"
                description={`Nothing under coverage for ${team.name} in the past yet.`}
              />
            )}
            {!recentQuery.isPending && completedFixtures.length > 0 && (
              <div className="space-y-4">
                <SeasonFilter seasonCounts={recentSeasonCounts} selected={recentSeasonFilter} onSelect={setRecentSeasonFilter} sportDomain={domain} />
                <RecentFormGrid rows={visibleRecentFixtures} teamId={team.id} sportSlug={sport.slug} />
              </div>
            )}
          </div>
          <div>
            <SectionHeading icon={CalendarClock} title="Upcoming fixtures" tone={tone} />
            {upcomingQuery.isPending && <MetricGridSkeleton count={3} />}
            {!upcomingQuery.isPending && upcomingFixtures.length === 0 && (
              <InfinityEmptyState
                icon={CalendarClock}
                title="No upcoming fixtures"
                description={`Nothing scheduled for ${team.name} yet.`}
              />
            )}
            {!upcomingQuery.isPending && upcomingFixtures.length > 0 && (
              <CompetitionFixtureTimeline fixtures={upcomingFixtures} fallbackSportSlug={sport.slug} aiReady={aiAvailable} />
            )}
          </div>
        </div>

        {/* News Intelligence */}
        <div id="news" className="scroll-mt-24">
          <SectionHeading icon={Newspaper} title="News intelligence" tone="var(--infinity-domain-news)" />
          <NewsIntelligenceSection query={newsQuery} teamName={team.name} />
        </div>

        {/* Knowledge Graph */}
        <div id="knowledge-graph" className="scroll-mt-24">
          <SectionHeading icon={Waypoints} title="Knowledge graph" tone="var(--infinity-domain-knowledge-graph)" />
          <KnowledgeGraphPanel nodeQuery={kgNodeQuery} contextQuery={kgContextQuery} teamName={team.name} />
        </div>
      </div>
    </div>
  )
}

// -- Derivation --------------------------------------------------------------------------------

interface MatchResult {
  outcome: Outcome
  gf: number
  ga: number
  isHome: boolean
}

interface SeasonSplit {
  played: number
  w: number
  d: number
  l: number
  gf: number
  ga: number
  cleanSheets: number
  failedToScore: number
  /** Most recent → oldest, capped to the most recent 10 — matches this split only (home-only or
   * away-only), not the team's overall form. */
  formLast10: Outcome[]
}

interface TeamAnalytics {
  sampleSize: number
  formRecentFirst: Outcome[]
  chronological: MatchResult[]
  overall: SeasonSplit
  home: SeasonSplit
  away: SeasonSplit
  cleanSheets: number
  bttsCount: number
  last5Points: number
  prior5Points: number
  momentumSeries: number[]
  /** Chronological (oldest → newest) raw goals scored/conceded per match — real, not the
   * differential `momentumSeries` uses, so a sparkline reads as an actual goals trend. */
  goalsForSeries: number[]
  goalsAgainstSeries: number[]
}

function emptySplit(): SeasonSplit {
  return { played: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, cleanSheets: 0, failedToScore: 0, formLast10: [] }
}

function applyResult(split: SeasonSplit, r: MatchResult) {
  split.played++
  split.gf += r.gf
  split.ga += r.ga
  if (r.outcome === 'W') split.w++
  else if (r.outcome === 'D') split.d++
  else split.l++
  if (r.ga === 0) split.cleanSheets++
  if (r.gf === 0) split.failedToScore++
}

function computeTeamAnalytics(fixturesDesc: FixtureSummaryDto[], teamId: string): TeamAnalytics {
  const withResult: MatchResult[] = []
  for (const f of fixturesDesc) {
    const { homeScore, awayScore } = fixtureScores(f.final_state)
    if (homeScore === undefined || awayScore === undefined) continue
    const isHome = f.home_team.id === teamId
    const gf = isHome ? homeScore : awayScore
    const ga = isHome ? awayScore : homeScore
    const outcome: Outcome = gf > ga ? 'W' : gf < ga ? 'L' : 'D'
    withResult.push({ outcome, gf, ga, isHome })
  }

  const overall = emptySplit()
  const home = emptySplit()
  const away = emptySplit()
  let cleanSheets = 0
  let bttsCount = 0

  for (const r of withResult) {
    applyResult(overall, r)
    applyResult(r.isHome ? home : away, r)
    if (r.ga === 0) cleanSheets++
    if (r.gf > 0 && r.ga > 0) bttsCount++
  }

  // `withResult` is already most-recent-first — slicing the first 10 of each split keeps that
  // order, matching FormRibbon's left-to-right convention (most recent match on the left).
  home.formLast10 = withResult.filter((r) => r.isHome).slice(0, 10).map((r) => r.outcome)
  away.formLast10 = withResult.filter((r) => !r.isHome).slice(0, 10).map((r) => r.outcome)

  const points = (arr: MatchResult[]) => arr.reduce((sum, r) => sum + (r.outcome === 'W' ? 3 : r.outcome === 'D' ? 1 : 0), 0)
  const chronological = [...withResult].reverse()

  return {
    sampleSize: withResult.length,
    formRecentFirst: withResult.map((r) => r.outcome),
    chronological,
    overall,
    home,
    away,
    cleanSheets,
    bttsCount,
    last5Points: points(withResult.slice(0, 5)),
    prior5Points: points(withResult.slice(5, 10)),
    momentumSeries: chronological.map((r) => Math.max(-1, Math.min(1, (r.gf - r.ga) / 3))),
    goalsForSeries: chronological.map((r) => r.gf),
    goalsAgainstSeries: chronological.map((r) => r.ga),
  }
}

function pct(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : Math.round((numerator / denominator) * 100)
}

function perMatch(total: number, played: number): string {
  return played === 0 ? '—' : (total / played).toFixed(1)
}

function ppg(split: SeasonSplit): string {
  return split.played === 0 ? '—' : ((split.w * 3 + split.d) / split.played).toFixed(2)
}

function ppgValue(split: SeasonSplit): number | null {
  return split.played === 0 ? null : (split.w * 3 + split.d) / split.played
}

// Shared tier-label thresholds — real, well-understood football heuristics applied to real
// derived numbers (goals/match, clean-sheet%, PPG), never an invented composite score. Used by
// both the Hero command-center tiles and the AI Team Intelligence insight cards so the two
// surfaces never drift apart on what "Potent" or "Title pace" means.
function attackTierLabel(goalsPerMatch: number): string {
  return goalsPerMatch >= 2 ? 'Potent' : goalsPerMatch >= 1 ? 'Balanced' : 'Building'
}

function defenceTierLabel(cleanSheetRate: number): string {
  return cleanSheetRate >= 40 ? 'Airtight' : cleanSheetRate >= 15 ? 'Steady' : 'Exposed'
}

/** PPG-based strength tier — 2.2/1.7/1.2 roughly map to title-pace/European-pace/mid-table-pace
 * points totals over a full season, a standard piece of football shorthand, not a fabricated
 * score. Below 1.2 PPG a team is on a relegation/rebuilding trajectory. */
function strengthTierLabel(ppgVal: number | null): string {
  if (ppgVal === null) return 'Unknown'
  if (ppgVal >= 2.2) return 'Title pace'
  if (ppgVal >= 1.7) return 'Europe pace'
  if (ppgVal >= 1.2) return 'Mid-table pace'
  return 'Rebuilding'
}

function scheduleGapDays(upcoming: FixtureSummaryDto[]): number | null {
  const gaps = upcoming
    .slice(0, 4)
    .map((f, i, arr) => (i === 0 ? null : (new Date(f.scheduled_at).getTime() - new Date(arr[i - 1].scheduled_at).getTime()) / 86_400_000))
    .filter((g): g is number => g !== null)
  return gaps.length > 0 ? gaps.reduce((a, b) => a + b, 0) / gaps.length : null
}

function scheduleTierLabel(avgGap: number | null): string {
  if (avgGap === null) return 'Unknown'
  return avgGap < 4 ? 'Congested' : avgGap <= 7 ? 'Normal' : 'Light'
}

/** Five to seven short, real, one-line observations for the Hero's "Quick Insights" row — every
 * line is derived straight from `analytics`/`upcoming`/`sentiment`. Never a generated/LLM
 * sentence — plain string interpolation over real numbers. */
function buildQuickInsights(
  analytics: TeamAnalytics,
  upcoming: FixtureSummaryDto[],
  sentiment?: { label: string; momentum: number | null; confidence: number },
): string[] {
  const insights: string[] = []
  const momentumDirection = analytics.last5Points > analytics.prior5Points ? 'Rising' : analytics.last5Points < analytics.prior5Points ? 'Cooling' : 'Steady'
  insights.push(`Momentum: ${momentumDirection} — ${analytics.last5Points} pts from the last 5 matches vs ${analytics.prior5Points} pts the 5 before.`)

  const goalsPerMatch = analytics.overall.played ? analytics.overall.gf / analytics.overall.played : 0
  insights.push(`Attack: ${attackTierLabel(goalsPerMatch)} — ${goalsPerMatch.toFixed(1)} goals per match.`)

  const cleanSheetRate = pct(analytics.cleanSheets, analytics.overall.played)
  insights.push(`Defence: ${defenceTierLabel(cleanSheetRate)} — clean sheet in ${cleanSheetRate}% of matches.`)

  const homePpg = ppgValue(analytics.home)
  const awayPpg = ppgValue(analytics.away)
  if (homePpg !== null && awayPpg !== null) {
    if (Math.abs(homePpg - awayPpg) < 0.2) {
      insights.push(`Consistent home and away form — ${homePpg.toFixed(2)} vs ${awayPpg.toFixed(2)} PPG.`)
    } else if (homePpg > awayPpg) {
      insights.push(`Notably stronger at home — ${homePpg.toFixed(2)} PPG at home vs ${awayPpg.toFixed(2)} PPG away.`)
    } else {
      insights.push(`Performs better on the road — ${awayPpg.toFixed(2)} PPG away vs ${homePpg.toFixed(2)} PPG at home.`)
    }
  }

  const avgGap = scheduleGapDays(upcoming)
  insights.push(
    avgGap === null
      ? 'Schedule load: not enough upcoming fixtures under coverage to estimate.'
      : `Schedule load: ${scheduleTierLabel(avgGap)} — averaging ${avgGap.toFixed(1)} days between the next few fixtures.`,
  )

  if (sentiment) {
    insights.push(
      `News sentiment: ${sentiment.label} — ${Math.round(sentiment.confidence * 100)}% confidence from TitanIQ's news intelligence pipeline.`,
    )
  }

  insights.push(`Based on ${analytics.sampleSize} completed ${analytics.sampleSize === 1 ? 'match' : 'matches'} under coverage.`)

  return insights
}

// -- Small presentational pieces ----------------------------------------------------------------

type TeamCardVariant = 'record' | 'metric' | 'list' | 'activity' | 'graph'

/** This page's card shell — five content-shaped variants sharing one token system (radius,
 * border, motion) instead of one identical shell reused for every card. `record` (Home/Away
 * record) gets a top accent edge and a tone-tinted hover lift; `metric` (season totals) gets
 * the same lift so four in a row read as one family; `list` (statistics) stays flat with just a
 * tone dot in its header; `activity` (news) differentiates through rhythm and a hover tint
 * rather than a colored border; `graph` gets a faint dot-grid texture and generous padding,
 * since it's the page's one card about connections rather than numbers. */
function TeamCard({
  variant,
  tone = 'var(--infinity-border-default)',
  className,
  children,
}: {
  variant: TeamCardVariant
  tone?: string
  className?: string
  children: ReactNode
}) {
  const glows = variant === 'record' || variant === 'metric'
  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-infinity-lg border border-infinity-border-hairline bg-infinity-ground-1',
        'transition-all duration-200 ease-out',
        variant === 'graph' ? 'p-6' : 'p-4',
        glows && 'hover:-translate-y-0.5 hover:shadow-[var(--card-glow)]',
        variant === 'list' && 'hover:border-infinity-border-default',
        variant === 'activity' && 'hover:bg-infinity-ground-2',
        className,
      )}
      style={glows ? ({ '--card-glow': `0 16px 32px -12px ${tone}40` } as CSSProperties) : undefined}
    >
      {variant === 'record' && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-[2px]"
          style={{ background: `linear-gradient(90deg, ${tone}, transparent)` }}
        />
      )}
      {variant === 'graph' && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{ backgroundImage: `radial-gradient(circle, ${tone}30 1px, transparent 1px)`, backgroundSize: '16px 16px' }}
        />
      )}
      <div className="relative z-10">{children}</div>
    </div>
  )
}

/** `list`-variant card header — a small tone dot standing in for the icon-in-a-box treatment
 * used elsewhere, kept minimal since these cards are read as a dense row of label/value pairs. */
function StatListHeading({ tone, children }: { tone: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: tone }} />
      <InfinityLabel>{children}</InfinityLabel>
    </div>
  )
}

function SectionHeading({ icon: Icon, title, tone }: { icon: typeof Sparkles; title: string; tone: string }) {
  return (
    <div className="mb-4 flex items-center gap-2">
      <Icon className="size-4" style={{ color: tone }} aria-hidden="true" />
      <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{title}</p>
    </div>
  )
}

function MetricGridSkeleton({ count }: { count: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <InfinitySkeleton key={i} className="h-24" />
      ))}
    </div>
  )
}

function TeamCrestLarge({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt=""
        className="size-16 shrink-0 object-contain drop-shadow-[0_8px_24px_rgba(0,0,0,0.5)] sm:size-20"
        loading="lazy"
      />
    )
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-16 shrink-0 items-center justify-center rounded-full bg-white/10 font-infinity-display text-2xl font-semibold text-white/70 sm:size-20 sm:text-3xl"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}

/** Subtle scroll-linked drift for the hero backdrop. The app shell scrolls an inner
 * `<main overflow-y-auto>`, not `window` (see the sticky-nav fix elsewhere in this file) — so
 * this listens on that ancestor, not window.scrollY. Disabled under prefers-reduced-motion. */
function useHeroParallax(ref: { current: HTMLElement | null }): number {
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const scrollEl = ref.current?.closest('main')
    if (!scrollEl) return
    function handleScroll() {
      const rect = ref.current?.getBoundingClientRect()
      if (!rect) return
      setOffset(Math.max(-20, Math.min(20, rect.top * -0.06)))
    }
    scrollEl.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll()
    return () => scrollEl.removeEventListener('scroll', handleScroll)
  }, [ref])

  return offset
}

/** The Team Hero's atmosphere layer — a procedural, code-drawn stadium impression (floodlight
 * masts, stand bowls, pitch perspective) rather than a fetched photo. No backend field carries a
 * real stadium image, and this app has no AI image-generation pipeline wired up, so claiming
 * either would be fabricating a capability that doesn't exist; this renders instantly, needs no
 * network request, and never appears empty. Tinted per-team by `tone` (the crest-sampled accent
 * or its domain-color fallback), so every club's hero reads as visually distinct. */
function StadiumBackdrop({ tone, parallax }: { tone: string; parallax: number }) {
  return (
    <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
      <div
        className="absolute inset-0 motion-reduce:!transform-none"
        style={{ transform: `translateY(${parallax}px) scale(1.12)`, transition: 'transform 0.05s linear' }}
      >
        <StadiumSvg tone={tone} />
      </div>
      <div
        className="absolute inset-0 animate-hero-glow motion-reduce:animate-none"
        style={{ background: `radial-gradient(ellipse 55% 55% at 50% 18%, ${tone} 0%, transparent 70%)`, opacity: 0.32 }}
      />
      <div
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse 100% 90% at 50% 40%, transparent 30%, rgba(0,0,0,0.65) 100%)' }}
      />
      <div className="absolute inset-0" style={{ backgroundColor: 'rgba(5, 7, 10, 0.78)' }} />
    </div>
  )
}

function StadiumSvg({ tone }: { tone: string }) {
  const floodlights = [90, 340, 860, 1110]
  return (
    <svg viewBox="0 0 1200 420" preserveAspectRatio="xMidYMax slice" className="size-full opacity-80" role="presentation">
      <path d="M -80 0 Q 340 260 -80 420 Z" fill="#1a2230" opacity="0.6" />
      <path d="M 1280 0 Q 860 260 1280 420 Z" fill="#1a2230" opacity="0.6" />
      <g stroke={tone} strokeOpacity="0.22" strokeWidth="1">
        <line x1="380" y1="420" x2="470" y2="150" />
        <line x1="600" y1="420" x2="600" y2="130" />
        <line x1="820" y1="420" x2="730" y2="150" />
      </g>
      <ellipse cx="600" cy="440" rx="520" ry="70" fill="none" stroke={tone} strokeOpacity="0.15" strokeWidth="1" />
      {floodlights.map((x, i) => (
        <g key={i}>
          <rect x={x - 1} y="34" width="2" height="70" fill="#3c4759" opacity="0.6" />
          <circle cx={x} cy="30" r="4" fill={tone} opacity="0.95" />
          <circle cx={x} cy="30" r="18" fill={tone} opacity="0.3" style={{ filter: 'blur(8px)' }} />
        </g>
      ))}
    </svg>
  )
}

/** A glass metric tile for inside the Hero. Deliberately not `InfinityMetricCard` — that
 * component's number/label colors are theme tokens (dark text in light theme), which would go
 * invisible against the Hero's forced-dark backdrop; this hardcodes light-on-dark instead. */
function HeroMetricTile({
  icon: Icon,
  label,
  value,
  sublabel,
  tone,
}: {
  icon: typeof Sparkles
  label: string
  value: string
  sublabel?: string
  tone?: string
}) {
  return (
    <div className="rounded-infinity-md border border-white/10 bg-white/[0.08] p-3.5 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.11]">
      <div className="flex items-center gap-1.5">
        <Icon className="size-3.5" style={{ color: tone ?? 'rgba(255,255,255,0.5)' }} aria-hidden="true" />
        <span className="font-infinity-body text-[10px] font-medium uppercase tracking-[0.06em] text-white/50">{label}</span>
      </div>
      <p className="mt-1.5 font-infinity-telemetry text-[19px] font-semibold tabular-nums text-white">{value}</p>
      {sublabel && <p className="mt-0.5 font-infinity-mono text-[10px] text-white/45">{sublabel}</p>}
    </div>
  )
}

/** One real, measured "Team DNA" axis (Possession, Set-piece frequency) — a proportional bar
 * against a reasonable ceiling, same convention as `StatBar` elsewhere on this page, just
 * re-themed for the dark Hero backdrop. */
function HeroDnaBar({ label, valuePct, sublabel, tone }: { label: string; valuePct: number; sublabel?: string; tone: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-infinity-mono text-[11px] text-white/65">{label}</span>
        <span className="font-infinity-telemetry text-[12px] font-semibold text-white">{Math.round(valuePct)}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full" style={{ width: `${Math.max(2, Math.min(100, valuePct))}%`, backgroundColor: tone }} />
      </div>
      {sublabel && <p className="mt-0.5 font-infinity-mono text-[10px] text-white/40">{sublabel}</p>}
    </div>
  )
}

/** The honest half of "Team DNA" — pressing intensity and counter-attack frequency have no real
 * source anywhere in this app (no per-match event data is tracked), so rather than invent a
 * number, this axis is shown explicitly as not-yet-available. */
function HeroDnaPending({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-between gap-2 opacity-60">
      <span className="flex items-center gap-1.5 font-infinity-mono text-[11px] text-white/50">
        <Lock className="size-3 text-white/35" aria-hidden="true" />
        {label}
      </span>
      <span className="font-infinity-mono text-[10px] text-white/35">Not tracked yet</span>
    </div>
  )
}

function FormPills({ outcomesRecentFirst, size = 20 }: { outcomesRecentFirst: Outcome[]; size?: number }) {
  if (outcomesRecentFirst.length === 0) return null
  return (
    <div className="flex gap-1">
      {outcomesRecentFirst.map((outcome, i) => (
        <span
          key={i}
          className="flex shrink-0 items-center justify-center rounded-[4px] font-infinity-mono font-semibold text-infinity-ground-0"
          style={{ backgroundColor: OUTCOME_TONE[outcome], width: size, height: size, fontSize: size <= 18 ? 9 : 10 }}
          title={outcome === 'W' ? 'Win' : outcome === 'D' ? 'Draw' : 'Loss'}
        >
          {outcome}
        </span>
      ))}
    </div>
  )
}

function FormRibbon({ form, labelTone }: { form: Outcome[]; labelTone?: string }) {
  if (form.length === 0) return null
  // form is already most-recent-first — render it left-to-right as given, so the leftmost pill
  // is the latest match, matching the "Recent form" fixtures list below it on the page.
  return (
    <div className="flex items-center gap-3">
      <InfinityLabel tone={labelTone}>Form</InfinityLabel>
      <FormPills outcomesRecentFirst={form} />
    </div>
  )
}

/** A single-value ring gauge (win rate, BTTS%, etc). `percent` is 0–100. */
function RingGauge({ percent, tone, size = 100, strokeWidth = 9, label }: { percent: number; tone: string; size?: number; strokeWidth?: number; label?: string }) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.max(0, Math.min(100, percent))
  const offset = circumference * (1 - clamped / 100)
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label ? `${label}: ${Math.round(clamped)}%` : `${Math.round(clamped)}%`}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--infinity-border-hairline)" strokeWidth={strokeWidth} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={tone}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" className="fill-infinity-text-primary" style={{ font: '700 20px var(--infinity-font-telemetry, monospace)' }}>
        {Math.round(clamped)}%
      </text>
      {label && (
        <text x="50%" y="65%" textAnchor="middle" dominantBaseline="middle" className="fill-infinity-text-muted" style={{ font: '500 9px var(--infinity-font-mono, monospace)' }}>
          {label}
        </text>
      )}
    </svg>
  )
}

/** A multi-segment ring gauge — draws each segment as a consecutive arc, e.g. win/draw/loss. */
function SegmentedRing({ segments, size = 112, strokeWidth = 10 }: { segments: Array<{ value: number; tone: string }>; size?: number; strokeWidth?: number }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0)
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  if (total === 0) {
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="No matches under coverage yet">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--infinity-border-hairline)" strokeWidth={strokeWidth} />
      </svg>
    )
  }
  let cumulative = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Win, draw, loss split">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--infinity-border-hairline)" strokeWidth={strokeWidth} />
      {segments
        .filter((s) => s.value > 0)
        .map((segment, i) => {
          const fraction = segment.value / total
          const dash = circumference * fraction
          const rotation = -90 + (cumulative / total) * 360
          cumulative += segment.value
          return (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={segment.tone}
              strokeWidth={strokeWidth}
              strokeDasharray={`${dash} ${circumference - dash}`}
              transform={`rotate(${rotation} ${size / 2} ${size / 2})`}
            />
          )
        })}
    </svg>
  )
}

/** A compact 0-based area sparkline for a real chronological series (goals for/against per match) —
 * distinct from InfinityMomentumCurve, which is built around a signed differential and a midline. */
function Sparkline({ values, tone, width = 140, height = 40 }: { values: number[]; tone: string; width?: number; height?: number }) {
  const gradientId = `infinity-sparkline-${useId()}`
  if (values.length < 2) return null
  const max = Math.max(...values, 1)
  const step = width / (values.length - 1)
  const scaleY = (v: number) => height - (v / max) * height
  const path = values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${i * step} ${scaleY(v)}`).join(' ')
  const areaPath = `${path} L ${width} ${height} L 0 ${height} Z`
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-hidden="true" className="w-full">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tone} stopOpacity="0.35" />
          <stop offset="100%" stopColor={tone} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <path d={path} fill="none" stroke={tone} strokeWidth="1.5" />
    </svg>
  )
}

/** A labeled value with a proportional bar underneath — used for average scored/conceded, capped
 * at a reasonable per-match ceiling so the bar reads as relative rather than an absolute scale. */
function StatBar({ label, value, tone, ceiling = 3 }: { label: string; value: number; tone: string; ceiling?: number }) {
  const widthPct = Math.max(2, Math.min(100, (value / ceiling) * 100))
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-infinity-mono text-[11px] text-infinity-text-secondary">{label}</span>
        <span className="font-infinity-telemetry text-[12px] font-semibold tabular-nums text-infinity-text-primary">{value.toFixed(2)}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-infinity-ground-2">
        <div className="h-full rounded-full" style={{ width: `${widthPct}%`, backgroundColor: tone }} />
      </div>
    </div>
  )
}

/** RecentFormGrid — completed matches read as AI Match Snapshots (goals, BTTS, corners, clean
 * sheet — whatever the fixture's own recorded statistics actually carry), never a plain scoreline
 * and never a "Generate Intelligence" CTA: the match already happened, there's nothing left to
 * predict. Every card links straight to that fixture's real AI Match Review. */
function RecentFormGrid({
  rows,
  teamId,
  sportSlug,
}: {
  rows: Array<{ fixture: FixtureSummaryDto; scores: { homeScore: number; awayScore: number } }>
  teamId: string
  sportSlug: string
}) {
  const statsQueries = useQueries({
    queries: rows.map(({ fixture }) => ({
      queryKey: ['sports', 'fixture-statistics', fixture.id],
      queryFn: () => sportsApi.fixtureStatistics(fixture.id),
      staleTime: 5 * 60 * 1000,
    })),
  })

  if (rows.length === 0) {
    return <InfinityEmptyState icon={Radio} title="No fixtures in this month" description="Pick another month to see more of the team's recent form." />
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(({ fixture, scores }, i) => {
        const perspectiveIsHome = fixture.home_team.id === teamId
        const opponent = perspectiveIsHome ? fixture.away_team : fixture.home_team
        const teamName = perspectiveIsHome ? fixture.home_team.name : fixture.away_team.name
        const statsRows = statsQueries[i]?.data
        const perspectiveStats = statsRows?.find((row) => row.team_id === teamId)?.stats
        const opponentStats = statsRows?.find((row) => row.team_id === opponent.id)?.stats
        return (
          <MatchSnapshotCard
            key={fixture.id}
            competition={fixture.competition_name}
            competitionLogoUrl={fixture.competition_logo_url}
            dateLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
            teamName={teamName}
            teamLogoUrl={perspectiveIsHome ? fixture.home_team.logo_url : fixture.away_team.logo_url}
            opponentName={opponent.name}
            opponentLogoUrl={opponent.logo_url}
            perspectiveIsHome={perspectiveIsHome}
            homeScore={scores.homeScore}
            awayScore={scores.awayScore}
            perspectiveStats={perspectiveStats}
            opponentStats={opponentStats}
            statsLoading={statsQueries[i]?.isPending}
            href={`/app/${fixture.sport_code ?? sportSlug}/matches/${fixture.id}/review`}
          />
        )
      })}
    </div>
  )
}

const STAT_LABELS: Record<keyof Omit<TeamStatisticsSummaryDto, 'sample_size'>, string> = {
  possession_pct: 'Possession',
  shots_total: 'Shots',
  shots_on_target: 'Shots on target',
  corners: 'Corners',
  fouls: 'Fouls',
  cards_yellow: 'Yellow cards',
  cards_red: 'Red cards',
}

function StatRow({ label, value, suffix = '' }: { label: string; value: number | null; suffix?: string }) {
  return (
    <div className="flex items-center justify-between border-t border-infinity-border-hairline py-2 first:border-t-0 first:pt-0">
      <span className="font-infinity-body text-[12px] text-infinity-text-secondary">{label}</span>
      <span className="font-infinity-telemetry text-[13px] font-semibold tabular-nums text-infinity-text-primary" title={value === null ? 'Not yet recorded' : undefined}>
        {value === null ? '—' : `${value.toFixed(1)}${suffix}`}
      </span>
    </div>
  )
}

function StatisticsSection({ analytics, stats }: { analytics: TeamAnalytics; stats: TeamStatisticsSummaryDto }) {
  if (stats.sample_size === 0 && analytics.overall.played === 0) {
    return (
      <InfinityEmptyState
        icon={Target}
        title="No statistics recorded yet"
        description="TitanIQ hasn't logged detailed match statistics for this team yet — this fills in as matches are covered."
      />
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <TeamCard variant="list">
        <StatListHeading tone="var(--infinity-signal)">Attack</StatListHeading>
        <div className="mt-2">
          <StatRow label="Goals / match" value={analytics.overall.played ? analytics.overall.gf / analytics.overall.played : null} />
          <StatRow label={STAT_LABELS.shots_total} value={stats.shots_total} />
          <StatRow label={STAT_LABELS.shots_on_target} value={stats.shots_on_target} />
        </div>
      </TeamCard>
      <TeamCard variant="list">
        <StatListHeading tone="var(--infinity-danger)">Defense</StatListHeading>
        <div className="mt-2">
          <StatRow label="Conceded / match" value={analytics.overall.played ? analytics.overall.ga / analytics.overall.played : null} />
          <StatRow label="Clean sheets" value={analytics.cleanSheets} suffix=" matches" />
        </div>
      </TeamCard>
      <TeamCard variant="list">
        <StatListHeading tone="var(--infinity-signal)">Possession &amp; set pieces</StatListHeading>
        <div className="mt-2">
          <StatRow label={STAT_LABELS.possession_pct} value={stats.possession_pct} suffix="%" />
          <StatRow label={STAT_LABELS.corners} value={stats.corners} />
        </div>
      </TeamCard>
      <TeamCard variant="list">
        <StatListHeading tone="var(--infinity-text-muted)">Discipline</StatListHeading>
        <div className="mt-2">
          <StatRow label={STAT_LABELS.cards_yellow} value={stats.cards_yellow} />
          <StatRow label={STAT_LABELS.cards_red} value={stats.cards_red} />
          <StatRow label={STAT_LABELS.fouls} value={stats.fouls} />
        </div>
      </TeamCard>
      <p className="col-span-full font-infinity-mono text-[11px] text-infinity-text-muted">
        Goals and clean sheets from {analytics.overall.played} completed matches · shots/possession/discipline averaged over{' '}
        {stats.sample_size} recent matches with recorded statistics — a dash means that stat was never recorded in the sample, not zero.
      </p>
    </div>
  )
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 60) return `${Math.max(mins, 0)}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

/** Maps the backend's real `NewsEventType` enum values (see `event_extraction_service.py`) to a
 * distinct glyph, so each news card carries an at-a-glance identity instead of text-only —
 * derived straight from the real `event_type` field, never a fabricated category. Unmapped or
 * future event types fall back to the section's own Newspaper icon. */
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

function NewsIntelligenceSection({
  query,
  teamName,
}: {
  query: { isPending: boolean; data: NewsEventDto[] | undefined }
  teamName: string
}) {
  if (query.isPending) return <MetricGridSkeleton count={3} />
  const events = query.data ?? []
  if (events.length === 0) {
    return (
      <InfinityEmptyState
        icon={Newspaper}
        title="No verified coverage yet"
        description={`TitanIQ hasn't extracted verified news signals for ${teamName} yet — this fills in as coverage grows.`}
      />
    )
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {events.map((event) => {
        const EventIcon = NEWS_EVENT_ICON[event.event_type] ?? Newspaper
        return (
          <TeamCard key={event.id} variant="activity">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="flex size-6 shrink-0 items-center justify-center rounded-infinity-sm"
                  style={{ backgroundColor: 'var(--infinity-domain-news)1f', color: 'var(--infinity-domain-news)' }}
                  aria-hidden="true"
                >
                  <EventIcon className="size-3.5" />
                </span>
                <InfinityBadge tone="var(--infinity-domain-news)">{event.event_type.replace(/_/g, ' ')}</InfinityBadge>
              </div>
              <span className="shrink-0 font-infinity-mono text-[10px] text-infinity-text-muted">{relativeTime(event.occurred_at)}</span>
            </div>
            <p className="mt-2 font-infinity-body text-[13.5px] font-medium leading-snug text-infinity-text-primary">{event.summary}</p>
            <p className="mt-2 border-t border-infinity-border-hairline pt-2 font-infinity-mono text-[10px] text-infinity-text-muted">
              Extraction confidence {Math.round(event.confidence * 100)}%
            </p>
          </TeamCard>
        )
      })}
    </div>
  )
}

function SeasonAnalyticsSection({ analytics }: { analytics: TeamAnalytics }) {
  const { overall, home, away } = analytics
  const over25 = analytics.chronological.filter((r) => r.gf + r.ga > 2.5).length
  const under25 = overall.played - over25

  return (
    <div className="space-y-5">
      <p className="font-infinity-mono text-[11px] text-infinity-text-muted">
        Based on {analytics.sampleSize} completed {analytics.sampleSize === 1 ? 'match' : 'matches'} under coverage.
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <RecordPanel title="Home record" icon={HomeIcon} split={home} tone="var(--infinity-success)" />
        <RecordPanel title="Away record" icon={Plane} split={away} tone="var(--infinity-signal)" />
      </div>

      <div>
        <InfinityLabel>Season totals</InfinityLabel>
        <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <TeamCard variant="metric" tone="var(--infinity-success)">
            <div className="flex items-center gap-2">
              <Swords className="size-4 text-infinity-success" aria-hidden="true" />
              <InfinityLabel>Goals for</InfinityLabel>
            </div>
            <p className="mt-2 font-infinity-telemetry text-[28px] font-semibold tabular-nums text-infinity-text-primary">{overall.gf}</p>
            <p className="mt-0.5 font-infinity-mono text-[11px] text-infinity-success">{perMatch(overall.gf, overall.played)} per game</p>
            <div className="mt-3">
              <Sparkline values={analytics.goalsForSeries} tone="var(--infinity-success)" />
            </div>
          </TeamCard>

          <TeamCard variant="metric" tone="var(--infinity-danger)">
            <div className="flex items-center gap-2">
              <Shield className="size-4 text-infinity-danger" aria-hidden="true" />
              <InfinityLabel>Goals against</InfinityLabel>
            </div>
            <p className="mt-2 font-infinity-telemetry text-[28px] font-semibold tabular-nums text-infinity-text-primary">{overall.ga}</p>
            <p className="mt-0.5 font-infinity-mono text-[11px] text-infinity-danger">{perMatch(overall.ga, overall.played)} per game</p>
            <div className="mt-3">
              <Sparkline values={analytics.goalsAgainstSeries} tone="var(--infinity-danger)" />
            </div>
          </TeamCard>

          <TeamCard variant="metric" tone="var(--infinity-signal)">
            <div className="flex items-center gap-2">
              <Target className="size-4 text-infinity-signal" aria-hidden="true" />
              <InfinityLabel>Both teams to score</InfinityLabel>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <RingGauge percent={pct(analytics.bttsCount, overall.played)} tone="var(--infinity-signal)" size={72} strokeWidth={7} />
              <p className="font-infinity-mono text-[11px] text-infinity-text-muted">
                Matches {analytics.bttsCount}/{overall.played}
              </p>
            </div>
            <div className="mt-3 space-y-1.5">
              <div className="flex items-center justify-between font-infinity-mono text-[11px] text-infinity-text-secondary">
                <span>Over 2.5 goals</span>
                <span className="font-semibold text-infinity-text-primary">{pct(over25, overall.played)}%</span>
              </div>
              <div className="flex items-center justify-between font-infinity-mono text-[11px] text-infinity-text-secondary">
                <span>Under 2.5 goals</span>
                <span className="font-semibold text-infinity-text-primary">{pct(under25, overall.played)}%</span>
              </div>
            </div>
          </TeamCard>

          <TeamCard variant="metric" tone="var(--infinity-signal)">
            <div className="flex items-center gap-2">
              <Flag className="size-4 text-infinity-signal" aria-hidden="true" />
              <InfinityLabel>Win / draw / loss</InfinityLabel>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <SegmentedRing
                size={72}
                strokeWidth={7}
                segments={[
                  { value: overall.w, tone: 'var(--infinity-success)' },
                  { value: overall.d, tone: 'var(--infinity-text-muted)' },
                  { value: overall.l, tone: 'var(--infinity-danger)' },
                ]}
              />
              <p className="font-infinity-telemetry text-lg font-semibold tabular-nums text-infinity-text-primary">
                {overall.w}/{overall.d}/{overall.l}
              </p>
            </div>
            <div className="mt-3 space-y-1.5">
              <WdlRow label="Wins" value={overall.w} pctValue={pct(overall.w, overall.played)} tone="var(--infinity-success)" />
              <WdlRow label="Draws" value={overall.d} pctValue={pct(overall.d, overall.played)} tone="var(--infinity-text-muted)" />
              <WdlRow label="Losses" value={overall.l} pctValue={pct(overall.l, overall.played)} tone="var(--infinity-danger)" />
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-infinity-border-hairline pt-2.5 font-infinity-mono text-[11px] text-infinity-text-secondary">
              <span>
                PPG <span className="font-semibold text-infinity-text-primary">{ppg(overall)}</span>
              </span>
              <span>
                Points <span className="font-semibold text-infinity-text-primary">{overall.w * 3 + overall.d}</span>
              </span>
            </div>
          </TeamCard>
        </div>
      </div>
    </div>
  )
}

function RecordPanel({
  title,
  icon: Icon,
  split,
  tone,
}: {
  title: string
  icon: typeof HomeIcon
  split: SeasonSplit
  tone: string
}) {
  if (split.played === 0) {
    return (
      <TeamCard variant="record" tone={tone}>
        <div className="flex items-center gap-2">
          <Icon className="size-4" style={{ color: tone }} aria-hidden="true" />
          <InfinityLabel>{title}</InfinityLabel>
        </div>
        <p className="mt-3 font-infinity-body text-[12px] text-infinity-text-secondary">No matches under coverage yet.</p>
      </TeamCard>
    )
  }

  return (
    <TeamCard variant="record" tone={tone}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="size-4" style={{ color: tone }} aria-hidden="true" />
          <InfinityLabel>{title}</InfinityLabel>
        </div>
        <span
          className="rounded-full border px-2 py-0.5 font-infinity-mono text-[10px] font-semibold"
          style={{ color: tone, borderColor: `${tone}40`, backgroundColor: `${tone}14` }}
        >
          {ppg(split)} PPG
        </span>
      </div>

      <p className="mt-3 font-infinity-telemetry text-2xl font-semibold tabular-nums text-infinity-text-primary">
        {split.w}-{split.d}-{split.l}
      </p>
      <p className="mt-1 font-infinity-mono text-[11px] text-infinity-text-muted">
        {split.played} played · {split.gf}-{split.ga} goals
      </p>

      <div className="mt-5 grid grid-cols-[auto_1fr] items-center gap-5">
        <RingGauge percent={pct(split.w, split.played)} tone={tone} label="Win rate" size={92} />
        <div className="min-w-0 space-y-3">
          {split.formLast10.length > 0 && (
            <div>
              <InfinityLabel>Form (last {split.formLast10.length})</InfinityLabel>
              <div className="mt-1.5">
                <FormPills outcomesRecentFirst={split.formLast10} size={18} />
              </div>
            </div>
          )}
          <StatBar label="Average scored" value={split.gf / split.played} tone="var(--infinity-success)" />
          <StatBar label="Average conceded" value={split.ga / split.played} tone="var(--infinity-danger)" />
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-infinity-border-hairline pt-3 font-infinity-mono text-[11px] text-infinity-text-secondary">
        <span className="flex items-center gap-1.5">
          <Shield className="size-3.5 text-infinity-text-muted" aria-hidden="true" /> Clean sheets{' '}
          <span className="font-semibold text-infinity-text-primary">{split.cleanSheets}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <Target className="size-3.5 text-infinity-text-muted" aria-hidden="true" /> Failed to score{' '}
          <span className="font-semibold text-infinity-text-primary">{split.failedToScore}</span>
        </span>
      </div>
    </TeamCard>
  )
}

function WdlRow({ label, value, pctValue, tone }: { label: string; value: number; pctValue: number; tone: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-10 shrink-0 font-infinity-mono text-[10px] text-infinity-text-muted">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-infinity-ground-2">
        <div className="h-full rounded-full" style={{ width: `${pctValue}%`, backgroundColor: tone }} />
      </div>
      <span className="w-16 shrink-0 text-right font-infinity-mono text-[10px] text-infinity-text-secondary">
        {value} · {pctValue}%
      </span>
    </div>
  )
}

function KnowledgeGraphPanel({
  nodeQuery,
  contextQuery,
  teamName,
}: {
  nodeQuery: { isPending: boolean; isError: boolean; error: unknown; data: { id: string } | undefined }
  contextQuery: { isPending: boolean; data: { related_by_type: Record<string, unknown[]> } | undefined }
  teamName: string
}) {
  const notFound = nodeQuery.isError && nodeQuery.error instanceof ApiError && nodeQuery.error.status === 404
  const otherError = nodeQuery.isError && !notFound

  if (nodeQuery.isPending) return <InfinitySkeleton className="h-24" />
  if (notFound) {
    return (
      <InfinityEmptyState
        icon={Waypoints}
        title="Still building context"
        description={`Historical relationship data is still growing for ${teamName} — check back soon.`}
      />
    )
  }
  if (otherError) return <ErrorState error={nodeQuery.error} onRetry={() => {}} />

  return (
    <TeamCard variant="graph" tone="var(--infinity-domain-knowledge-graph)">
      {contextQuery.isPending && <InfinitySkeleton className="h-12" />}
      {contextQuery.data &&
        (() => {
          const related = Object.entries(contextQuery.data.related_by_type)
          const total = related.reduce((sum, [, nodes]) => sum + nodes.length, 0)
          if (total === 0) {
            return (
              <p className="font-infinity-body text-[12px] text-infinity-text-secondary">
                Historical relationship data is still growing for {teamName}.
              </p>
            )
          }
          return (
            <>
              <p className="font-infinity-body text-[12px] text-infinity-text-secondary">
                TitanIQ has connected {teamName} to {total} related {total === 1 ? 'entity' : 'entities'} it uses to build understanding.
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
    </TeamCard>
  )
}

function humanizePlural(nodeType: string, count: number): string {
  const label = nodeType.replace(/_/g, ' ')
  if (count === 1 || label.endsWith('s')) return label
  return `${label}s`
}
