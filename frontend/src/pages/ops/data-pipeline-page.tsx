import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Workflow, Globe2, RefreshCw, Play, FlagTriangleRight, CalendarRange, Trophy, BarChart3, Copy } from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { sportsApi, SPORT_OPTIONS, type SportCode } from '@/lib/api/sports'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

function SportPipeline({ sportCode, sportLabel }: { sportCode: SportCode; sportLabel: string }) {
  const [competitionRef, setCompetitionRef] = useState('')
  const [competitionName, setCompetitionName] = useState('')
  const [seasonLabel, setSeasonLabel] = useState('')
  const [seasonId, setSeasonId] = useState<string | null>(null)
  const [competitionId, setCompetitionId] = useState<string | null>(null)
  const [statisticsFixtureId, setStatisticsFixtureId] = useState('')
  const queryClient = useQueryClient()

  const fixtureHintQuery = useQuery({
    queryKey: ['admin', 'pipeline-fixture-hint', sportCode, competitionId],
    queryFn: () => sportsApi.listFixtures(sportCode, { competition_id: competitionId!, limit: 1 }),
    enabled: !!competitionId,
  })
  const fixtureIdHint = fixtureHintQuery.data?.[0]?.id ?? null

  const statusQuery = useQuery({
    queryKey: ['admin', 'sync', 'status', sportCode],
    queryFn: () => adminPlatformApi.syncStatus({ sport_code: sportCode, limit: 10 }),
  })
  const statsQuery = useQuery({
    queryKey: ['admin', 'sync', 'stats', sportCode],
    queryFn: () => adminPlatformApi.syncStats({ sport_code: sportCode }),
  })

  const invalidateStatus = () => void queryClient.invalidateQueries({ queryKey: ['admin', 'sync', 'status', sportCode] })

  useRealtimeInvalidate(
    'syncRuns',
    [['admin', 'sync', 'status', sportCode], ['admin', 'sync', 'stats', sportCode]],
    `sport_code=eq.${sportCode}`,
  )

  const triggerCountries = useMutation({
    mutationFn: () => adminPlatformApi.triggerSyncCountries(sportCode),
    onSuccess: () => {
      toast.success(`${sportLabel}: country sync triggered`)
      invalidateStatus()
    },
    onError: (error) => toast.danger('Could not trigger country sync', error instanceof Error ? error.message : undefined),
  })

  const bootstrap = useMutation({
    mutationFn: () =>
      adminPlatformApi.bootstrapCompetition(sportCode, {
        competition_ref: competitionRef,
        competition_name: competitionName,
        season_label: seasonLabel,
      }),
    onSuccess: (result) => {
      setSeasonId(result.season_id)
      setCompetitionId(result.competition_id)
      toast.success('Competition bootstrapped', `${competitionName} · ${seasonLabel}`)
    },
    onError: (error) => toast.danger('Could not bootstrap competition', error instanceof Error ? error.message : undefined),
  })

  const triggerTeams = useMutation({
    mutationFn: () => adminPlatformApi.triggerSyncTeams(sportCode, competitionRef, { seasonLabel }),
    onSuccess: () => {
      toast.success('Team sync triggered')
      invalidateStatus()
    },
    onError: (error) => toast.danger('Could not trigger team sync', error instanceof Error ? error.message : undefined),
  })

  const triggerFixtures = useMutation({
    mutationFn: () => adminPlatformApi.triggerSyncFixtures(sportCode, competitionRef, seasonLabel, { season_id: seasonId! }),
    onSuccess: () => {
      toast.success('Fixture sync triggered')
      invalidateStatus()
      void fixtureHintQuery.refetch()
    },
    onError: (error) => toast.danger('Could not trigger fixture sync', error instanceof Error ? error.message : undefined),
  })

  const triggerStandings = useMutation({
    mutationFn: () => adminPlatformApi.triggerSyncStandings(sportCode, competitionRef, seasonLabel, { season_id: seasonId! }),
    onSuccess: () => {
      toast.success('Standings sync triggered')
      invalidateStatus()
    },
    onError: (error) => toast.danger('Could not trigger standings sync', error instanceof Error ? error.message : undefined),
  })

  const triggerStatistics = useMutation({
    mutationFn: () => adminPlatformApi.triggerSyncStatistics(sportCode, statisticsFixtureId),
    onSuccess: () => {
      toast.success('Statistics sync triggered')
      invalidateStatus()
    },
    onError: (error) => toast.danger('Could not trigger statistics sync', error instanceof Error ? error.message : undefined),
  })

  const bootstrapped = !!seasonId

  return (
    <SectionCard icon={Workflow} title={sportLabel} description="Ingestion sync status, stats, and manual trigger controls.">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Recent sync runs</p>
          {statusQuery.isPending && <Skeleton className="h-20" />}
          {statusQuery.isError && <ErrorState error={statusQuery.error} onRetry={() => void statusQuery.refetch()} />}
          {statusQuery.data && statusQuery.data.length === 0 && (
            <p className="text-sm text-text-muted">No sync runs yet for {sportLabel.toLowerCase()}.</p>
          )}
          {statusQuery.data && statusQuery.data.length > 0 && (
            <ul className="space-y-1.5">
              {statusQuery.data.slice(0, 4).map((run, i) => (
                <li key={i} className="rounded border border-border-subtle p-2 text-xs">
                  <KeyValueGrid data={run as Record<string, unknown>} />
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Aggregate stats</p>
          {statsQuery.isPending && <Skeleton className="h-20" />}
          {statsQuery.isError && <ErrorState error={statsQuery.error} onRetry={() => void statsQuery.refetch()} />}
          {statsQuery.data && <KeyValueGrid data={statsQuery.data} />}
        </div>
      </div>

      <div className="mt-4 border-t border-border-subtle pt-4">
        <Button size="sm" variant="secondary" onClick={() => triggerCountries.mutate()} disabled={triggerCountries.isPending} className="gap-1">
          <Globe2 className="size-3.5" />
          {triggerCountries.isPending ? 'Triggering…' : 'Sync countries'}
        </Button>
      </div>

      <div className="mt-4 border-t border-border-subtle pt-4">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
          <Trophy className="size-3.5" /> Bootstrap a competition
        </p>
        <p className="mb-3 text-xs text-text-secondary">
          One-time setup before teams/fixtures/standings can sync — reconciles the Competition and Season a real
          provider's IDs refer to (e.g. API-Football's numeric league id for the competition, and season year).
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label htmlFor={`comp-ref-${sportCode}`}>Provider competition ref</Label>
            <Input
              id={`comp-ref-${sportCode}`}
              placeholder="39"
              value={competitionRef}
              onChange={(e) => { setCompetitionRef(e.target.value); setSeasonId(null) }}
              className="mt-1.5 w-32"
            />
          </div>
          <div>
            <Label htmlFor={`comp-name-${sportCode}`}>Competition name</Label>
            <Input
              id={`comp-name-${sportCode}`}
              placeholder="Premier League"
              value={competitionName}
              onChange={(e) => setCompetitionName(e.target.value)}
              className="mt-1.5 w-44"
            />
          </div>
          <div>
            <Label htmlFor={`season-${sportCode}`}>Season</Label>
            <Input
              id={`season-${sportCode}`}
              placeholder="2025"
              value={seasonLabel}
              onChange={(e) => { setSeasonLabel(e.target.value); setSeasonId(null) }}
              className="mt-1.5 w-24"
            />
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => bootstrap.mutate()}
            disabled={!competitionRef || !competitionName || !seasonLabel || bootstrap.isPending}
            className="gap-1"
          >
            <FlagTriangleRight className="size-3.5" />
            {bootstrap.isPending ? 'Bootstrapping…' : 'Bootstrap'}
          </Button>
        </div>
        {seasonId && (
          <div className="mt-3 space-y-2 rounded-md border border-border-subtle bg-surface-2 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted">Season id</span>
              <code className="flex-1 truncate font-mono text-xs text-text-primary">{seasonId}</code>
              <Button
                size="sm"
                variant="ghost"
                className="gap-1"
                onClick={() => {
                  void navigator.clipboard?.writeText(seasonId)
                  toast.success('Season id copied')
                }}
              >
                <Copy className="size-3.5" /> Copy
              </Button>
            </div>
            <div className="flex items-center gap-2 border-t border-border-subtle pt-2">
              <span className="text-xs text-text-muted">Fixture id</span>
              {fixtureIdHint ? (
                <>
                  <code className="flex-1 truncate font-mono text-xs text-text-primary">{fixtureIdHint}</code>
                  <Button size="sm" variant="ghost" className="gap-1" onClick={() => setStatisticsFixtureId(fixtureIdHint)}>
                    Use
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="gap-1"
                    onClick={() => {
                      void navigator.clipboard?.writeText(fixtureIdHint)
                      toast.success('Fixture id copied')
                    }}
                  >
                    <Copy className="size-3.5" /> Copy
                  </Button>
                </>
              ) : (
                <span className="flex-1 text-xs text-text-muted">
                  {fixtureHintQuery.isFetching ? 'Looking for a synced fixture…' : 'No fixtures synced for this competition yet — run Sync fixtures first.'}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4">
        <Button size="sm" variant="secondary" onClick={() => triggerTeams.mutate()} disabled={!competitionRef || triggerTeams.isPending} className="gap-1">
          <Play className="size-3.5" />
          {triggerTeams.isPending ? 'Triggering…' : 'Sync teams'}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => triggerFixtures.mutate()} disabled={!bootstrapped || triggerFixtures.isPending} className="gap-1">
          <CalendarRange className="size-3.5" />
          {triggerFixtures.isPending ? 'Triggering…' : 'Sync fixtures'}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => triggerStandings.mutate()} disabled={!bootstrapped || triggerStandings.isPending} className="gap-1">
          <Trophy className="size-3.5" />
          {triggerStandings.isPending ? 'Triggering…' : 'Sync standings'}
        </Button>
        {!bootstrapped && (competitionRef || seasonLabel) && (
          <span className="text-xs text-text-muted">Bootstrap the competition first to enable fixtures/standings sync.</span>
        )}
      </div>

      <div className="mt-4 border-t border-border-subtle pt-4">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
          <BarChart3 className="size-3.5" /> Sync statistics
        </p>
        <p className="mb-3 text-xs text-text-secondary">
          Per-fixture, not per-competition — pulls both teams' match statistics (possession, shots,
          etc.) for one already-synced fixture, identified by our own persisted fixture id.
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label htmlFor={`stats-fixture-${sportCode}`}>Fixture ID</Label>
            <Input
              id={`stats-fixture-${sportCode}`}
              placeholder="e.g. 4d193afe-6faf-4b63-9630-c6fa31c4d6aa"
              value={statisticsFixtureId}
              onChange={(e) => setStatisticsFixtureId(e.target.value)}
              className="mt-1.5 w-72"
            />
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => triggerStatistics.mutate()}
            disabled={!statisticsFixtureId || triggerStatistics.isPending}
            className="gap-1"
          >
            <BarChart3 className="size-3.5" />
            {triggerStatistics.isPending ? 'Triggering…' : 'Sync statistics'}
          </Button>
        </div>
      </div>
    </SectionCard>
  )
}

export default function DataPipelinePage() {
  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Ingestion"
        title="Data Pipeline"
        description="Sync status, stats, and manual trigger controls for every sport's ingestion pipeline — fixtures, teams, standings, and countries."
      />

      {SPORT_OPTIONS.map((sport) => (
        <SportPipeline key={sport.code} sportCode={sport.code} sportLabel={sport.label} />
      ))}

      <SectionCard icon={RefreshCw} title="Other pipeline stages" description="Brief-requested stages with no dedicated sync-status endpoint yet.">
        <BackendPendingState
          title="Live scores, odds, news, community, and learning pipeline status"
          description="Sync status/stats/trigger endpoints exist for countries, teams, fixtures, and standings. Live score push, odds ingestion, and a unified pipeline-diagram view (news/community/Knowledge Graph/learning as ingestion stages) are not yet exposed as admin endpoints — each already has its own dedicated page in this Operations Center (News Intelligence, Community Intelligence, Knowledge Graph, ML Operations) covering what is available today."
          recommendedEndpoint="GET /api/v1/admin/sync/status?entity_kind=odds|live_scores"
        />
      </SectionCard>
    </div>
  )
}
