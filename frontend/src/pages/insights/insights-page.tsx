import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, GitCompare, Waypoints, Download, Save } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { intelligenceApi } from '@/lib/api/intelligence'
import { graphApi } from '@/lib/api/graph'
import { SPORT_SLUGS, type SportMeta } from '@/lib/hooks/use-sport'
import { useInvestigationWorkspace, kgNodeTypeFor, type EntityKind, type WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'
import { useWorkspaceCommandStore } from '@/stores/workspace-command-store'
import { WorkspaceHero, WORKSPACE_QUICK_ACTION_ICONS, type QuickActionSpec } from '@/components/command-deck/workspace/workspace-hero'
import { InvestigationHeader } from '@/components/command-deck/workspace/investigation-header'
import { InvestigationContextRail } from '@/components/command-deck/workspace/investigation-context-rail'
import { WorkspaceComposer } from '@/components/command-deck/workspace/workspace-composer'
import { WorkspaceTabBar, MissionBriefTab, PredictionIntelligenceTab, ComparisonTab, PredictionTimelineTab, RelatedFixturesTab, DecisionIntelligenceTab, type CanvasTab } from '@/components/command-deck/workspace/workspace-tabs'
import { EvidenceInspector } from '@/components/command-deck/workspace/evidence-inspector'
import { KnowledgeGraphPanel } from '@/components/command-deck/workspace/knowledge-graph-panel'
import { IntelligenceCompleteness, type CompletenessItem } from '@/components/command-deck/workspace/intelligence-completeness'
import { InvestigationNotebook } from '@/components/command-deck/workspace/investigation-notebook'
import { WorkspaceActionBar } from '@/components/command-deck/workspace/workspace-action-bar'
import { WorkspaceEmptyState } from '@/components/command-deck/workspace/workspace-empty-state'

function entityKey(e: WorkspaceEntity | null) {
  return e ? `${e.kind}:${e.id}` : null
}

export default function InsightsPage() {
  const workspace = useInvestigationWorkspace()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [sport, setSport] = useState<SportMeta>(SPORT_SLUGS[0])
  const [entityKind, setEntityKind] = useState<EntityKind>('fixture')
  const [query, setQuery] = useState('')
  const [activeTab, setActiveTab] = useState<CanvasTab>('mission-brief')
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)
  const [compareSelected, setCompareSelected] = useState<{ id: string; label: string }[]>([])
  const [kgCollapsed, setKgCollapsed] = useState(false)
  const [kgDrawerOpen, setKgDrawerOpen] = useState(false)
  const [notebookOpen, setNotebookOpen] = useState(false)

  const focused = workspace.focused

  // -- Cross-link entry points (?pin_type=&pin_id=[&pin_id_2=]) — same scheme already used across
  // the app, extended to competition/player alongside the original fixture/team. --------------
  const pinType = searchParams.get('pin_type') as EntityKind | null
  const pinId = searchParams.get('pin_id')
  const pinId2 = searchParams.get('pin_id_2')

  const crossLinkFixture = useQuery({ queryKey: ['sports', 'fixture', pinId], queryFn: () => sportsApi.getFixture(pinId!), enabled: pinType === 'fixture' && !!pinId })
  const crossLinkTeam = useQuery({ queryKey: ['sports', 'team', pinId], queryFn: () => sportsApi.getTeam(pinId!), enabled: pinType === 'team' && !!pinId })
  const crossLinkTeam2 = useQuery({ queryKey: ['sports', 'team', pinId2], queryFn: () => sportsApi.getTeam(pinId2!), enabled: pinType === 'team' && !!pinId2 })
  const crossLinkCompetition = useQuery({ queryKey: ['sports', 'competition', pinId], queryFn: () => sportsApi.getCompetition(pinId!), enabled: pinType === 'competition' && !!pinId })
  const crossLinkPlayer = useQuery({ queryKey: ['sports', 'player', pinId], queryFn: () => sportsApi.getPlayer(pinId!), enabled: pinType === 'player' && !!pinId })

  useEffect(() => {
    if (crossLinkFixture.data) {
      const f = crossLinkFixture.data
      workspace.pin({ kind: 'fixture', id: f.id, label: `${f.home_team.short_name} vs ${f.away_team.short_name}`, meta: f.competition_name })
      setSearchParams((prev) => { const n = new URLSearchParams(prev); n.delete('pin_type'); n.delete('pin_id'); return n })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossLinkFixture.data])

  useEffect(() => {
    if (crossLinkCompetition.data) {
      const c = crossLinkCompetition.data
      workspace.pin({ kind: 'competition', id: c.id, label: c.name, meta: c.country ?? undefined, logoUrl: c.logo_url })
      setSearchParams((prev) => { const n = new URLSearchParams(prev); n.delete('pin_type'); n.delete('pin_id'); return n })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossLinkCompetition.data])

  useEffect(() => {
    if (crossLinkPlayer.data) {
      const p = crossLinkPlayer.data
      workspace.pin({ kind: 'player', id: p.id, label: p.name, meta: p.team_name ?? undefined })
      setSearchParams((prev) => { const n = new URLSearchParams(prev); n.delete('pin_type'); n.delete('pin_id'); return n })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossLinkPlayer.data])

  useEffect(() => {
    if (crossLinkTeam.data && crossLinkTeam2.data) {
      workspace.pin({ kind: 'team', id: crossLinkTeam.data.id, label: crossLinkTeam.data.name, logoUrl: crossLinkTeam.data.logo_url })
      workspace.pin({ kind: 'team', id: crossLinkTeam2.data.id, label: crossLinkTeam2.data.name, logoUrl: crossLinkTeam2.data.logo_url })
      setSearchParams((prev) => { const n = new URLSearchParams(prev); n.delete('pin_type'); n.delete('pin_id'); n.delete('pin_id_2'); return n })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossLinkTeam.data, crossLinkTeam2.data])

  // -- Search (current sport + entity kind) ------------------------------------------------------
  const teamsQuery = useQuery({ queryKey: ['sports', 'teams', sport.code], queryFn: () => sportsApi.listTeams(sport.code), enabled: entityKind === 'team' })
  const fixturesQuery = useQuery({ queryKey: ['sports', 'fixtures', sport.code], queryFn: () => sportsApi.listFixtures(sport.code, { limit: 50 }), enabled: entityKind === 'fixture' })
  const competitionsQuery = useQuery({ queryKey: ['sports', 'competitions', sport.code], queryFn: () => sportsApi.listCompetitions(sport.code), enabled: entityKind === 'competition' })
  const playersQuery = useQuery({ queryKey: ['sports', 'players', sport.code], queryFn: () => sportsApi.listPlayers(sport.code, 100), enabled: entityKind === 'player' })

  const searching = query.trim().length > 0
  const q = query.trim().toLowerCase()
  const teamResults = searching && entityKind === 'team' ? (teamsQuery.data ?? []).filter((t) => t.name.toLowerCase().includes(q)).slice(0, 8) : []
  const fixtureResults = searching && entityKind === 'fixture' ? (fixturesQuery.data ?? []).filter((f) => `${f.home_team.name} ${f.away_team.name}`.toLowerCase().includes(q)).slice(0, 8) : []
  const competitionResults = searching && entityKind === 'competition' ? (competitionsQuery.data ?? []).filter((c) => c.name.toLowerCase().includes(q)).slice(0, 8) : []
  const playerResults = searching && entityKind === 'player' ? (playersQuery.data ?? []).filter((p) => p.name.toLowerCase().includes(q)).slice(0, 8) : []

  function focusFixture(f: NonNullable<typeof fixtureResults>[number]) {
    workspace.pin({ kind: 'fixture', id: f.id, label: `${f.home_team.short_name} vs ${f.away_team.short_name}`, meta: f.competition_name })
    setQuery('')
  }

  // Rendered both directly under the Hero's own search box (always visible) and — since the
  // empty-state's "Ask TitanIQ" input drives this exact same query/results state — directly under
  // that box too, so results/​"No matches" feedback never lands somewhere the user has scrolled
  // away from.
  const resultsPanel = searching ? (
    <div className="grid gap-1.5 rounded-[var(--cd-radius-lg)] border p-3 sm:grid-cols-2" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}>
      {entityKind === 'fixture' && fixtureResults.map((f) => (
        <button key={f.id} type="button" onClick={() => focusFixture(f)} className="truncate rounded-[var(--cd-radius-sm)] px-2 py-1.5 text-left font-[var(--cd-font-body)] text-[12.5px] hover:bg-[var(--cd-surface-2)]" style={{ color: 'var(--cd-text-secondary)' }}>
          {f.home_team.short_name} vs {f.away_team.short_name}
        </button>
      ))}
      {entityKind === 'team' && teamResults.map((t) => (
        <button key={t.id} type="button" onClick={() => { workspace.pin({ kind: 'team', id: t.id, label: t.name, logoUrl: t.logo_url }); setQuery('') }} className="truncate rounded-[var(--cd-radius-sm)] px-2 py-1.5 text-left font-[var(--cd-font-body)] text-[12.5px] hover:bg-[var(--cd-surface-2)]" style={{ color: 'var(--cd-text-secondary)' }}>
          {t.name}
        </button>
      ))}
      {entityKind === 'competition' && competitionResults.map((c) => (
        <button key={c.id} type="button" onClick={() => { workspace.pin({ kind: 'competition', id: c.id, label: c.name, logoUrl: c.logo_url, meta: c.country ?? undefined }); setQuery('') }} className="truncate rounded-[var(--cd-radius-sm)] px-2 py-1.5 text-left font-[var(--cd-font-body)] text-[12.5px] hover:bg-[var(--cd-surface-2)]" style={{ color: 'var(--cd-text-secondary)' }}>
          {c.name}
        </button>
      ))}
      {entityKind === 'player' && playerResults.map((p) => (
        <button key={p.id} type="button" onClick={() => { workspace.pin({ kind: 'player', id: p.id, label: p.name, meta: p.team_name ?? undefined }); setQuery('') }} className="truncate rounded-[var(--cd-radius-sm)] px-2 py-1.5 text-left font-[var(--cd-font-body)] text-[12.5px] hover:bg-[var(--cd-surface-2)]" style={{ color: 'var(--cd-text-secondary)' }}>
          {p.name}
        </button>
      ))}
      {fixtureResults.length === 0 && teamResults.length === 0 && competitionResults.length === 0 && playerResults.length === 0 && (
        <p className="col-span-full font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-muted)' }}>No matches for "{query}".</p>
      )}
    </div>
  ) : null

  // -- Focused-entity data --------------------------------------------------------------------
  const fixtureDetailQuery = useQuery({
    queryKey: ['sports', 'fixture', focused?.kind === 'fixture' ? focused.id : null],
    queryFn: () => sportsApi.getFixture(focused!.id),
    enabled: focused?.kind === 'fixture',
  })

  const marketsQuery = useQuery({ queryKey: ['markets', sport.code, 'production'], queryFn: () => marketsApi.list({ sport_code: sport.code, status: 'production' }) })
  const markets = marketsQuery.data ?? []

  const historyQuery = useQuery({
    queryKey: ['predictions', 'history', focused?.id],
    queryFn: () => predictionsApi.history(focused!.id),
    enabled: !!focused,
  })
  const history = historyQuery.data ?? []

  const newsQuery = useQuery({
    queryKey: ['intelligence', 'news-for-entity', focused?.id],
    queryFn: () => intelligenceApi.newsForEntity(focused!.id, 20),
    enabled: !!focused,
  })

  const kgNodeType = focused ? kgNodeTypeFor(focused.kind) : null
  const kgEntityQuery = useQuery({
    queryKey: ['graph', 'entity', kgNodeType, focused?.id],
    queryFn: () => graphApi.getEntity(kgNodeType!, focused!.id),
    enabled: !!focused,
    retry: false,
  })

  const focusedPredictionQuery = useQuery({
    queryKey: ['predictions', workspace.focusedPredictionId],
    queryFn: () => predictionsApi.get(workspace.focusedPredictionId!),
    enabled: !!workspace.focusedPredictionId,
  })

  const generateMutation = useMutation({
    mutationFn: (marketKey: string) =>
      predictionsApi.generate({ market_key: marketKey, entity_type: 'fixture', entity_id: focused!.id, subject_ref: focused!.id }),
    onSuccess: (prediction) => {
      void queryClient.invalidateQueries({ queryKey: ['predictions', 'history', focused?.id] })
      workspace.setFocusedPredictionId(prediction.id)
      setSelectedMarketKey(null)
    },
  })

  const homeTeam = fixtureDetailQuery.data ? { name: fixtureDetailQuery.data.home_team.name, logoUrl: fixtureDetailQuery.data.home_team.logo_url } : undefined
  const awayTeam = fixtureDetailQuery.data ? { name: fixtureDetailQuery.data.away_team.name, logoUrl: fixtureDetailQuery.data.away_team.logo_url } : undefined

  const generatedCount = new Set(history.map((p) => p.market_id)).size
  const canGenerate = focused?.kind === 'fixture' && markets.length > 0

  const completenessItems: CompletenessItem[] = focused
    ? [
        { key: 'prediction', label: 'Prediction', state: generatedCount > 0 ? 'complete' : 'pending' },
        { key: 'statistics', label: 'Statistics', state: focused.kind === 'fixture' ? 'pending' : 'unavailable' },
        { key: 'graph', label: 'Knowledge Graph', state: kgEntityQuery.data ? 'complete' : kgEntityQuery.isError ? 'pending' : 'pending' },
        { key: 'news', label: 'News', state: (newsQuery.data?.length ?? 0) > 0 ? 'complete' : 'pending' },
        { key: 'lineups', label: 'Lineups', state: 'unavailable' },
        { key: 'officials', label: 'Officials', state: 'unavailable' },
      ]
    : []

  function handleToggleCompare(predictionId: string, label: string) {
    setCompareSelected((prev) => (prev.some((c) => c.id === predictionId) ? prev.filter((c) => c.id !== predictionId) : [...prev, { id: predictionId, label }]))
  }

  function handleFocusEntity(entity: WorkspaceEntity) {
    workspace.focus(entity)
    setActiveTab('mission-brief')
    setSelectedMarketKey(null)
  }

  const quickActions: QuickActionSpec[] = [
    { key: 'generate', label: 'Generate Intelligence', icon: WORKSPACE_QUICK_ACTION_ICONS.generate, onClick: () => setActiveTab('predictions'), disabled: !canGenerate },
    { key: 'compare', label: 'Compare Teams', icon: WORKSPACE_QUICK_ACTION_ICONS.compare, onClick: () => setActiveTab('comparison') },
    { key: 'graph', label: 'Knowledge Graph', icon: WORKSPACE_QUICK_ACTION_ICONS.graph, onClick: () => setKgDrawerOpen(true), disabled: !focused },
  ]

  function openGraph() {
    setKgDrawerOpen(true)
    document.getElementById('workspace-kg-panel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  // -- Publish real, currently-available actions into the one global Command Palette (⌘K) ------
  const setWorkspaceCommands = useWorkspaceCommandStore((s) => s.setCommands)
  const clearWorkspaceCommands = useWorkspaceCommandStore((s) => s.clearCommands)
  useEffect(() => {
    if (!focused) {
      clearWorkspaceCommands()
      return
    }
    setWorkspaceCommands([
      ...(canGenerate ? [{ id: 'generate', label: 'Generate Intelligence', icon: Sparkles, run: () => setActiveTab('predictions') }] : []),
      { id: 'compare', label: 'Compare Teams', icon: GitCompare, run: () => setActiveTab('comparison') },
      { id: 'graph', label: 'Open Knowledge Graph', icon: Waypoints, run: openGraph },
      { id: 'export', label: 'Export Report', icon: Download, run: () => setNotebookOpen(true) },
      { id: 'save', label: 'Save Session', icon: Save, run: workspace.saveSession },
    ])
    return () => clearWorkspaceCommands()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused?.kind, focused?.id, canGenerate])

  return (
    <div className="command-deck space-y-5 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <WorkspaceHero
        sport={sport}
        onSportChange={(s) => { setSport(s); setQuery('') }}
        entityKind={entityKind}
        onEntityKindChange={(k) => { setEntityKind(k); setQuery('') }}
        query={query}
        onQueryChange={setQuery}
        onPredictionIdOpen={(id) => workspace.setFocusedPredictionId(id)}
        quickActions={quickActions}
        recentCount={workspace.recentlyOpened.length}
        onOpenRecent={() => document.getElementById('investigation-context-rail')?.scrollIntoView({ behavior: 'smooth' })}
      />

      {resultsPanel}

      <div className="grid gap-5 lg:grid-cols-[220px_1fr] xl:grid-cols-[240px_1fr_320px]">
        <div id="investigation-context-rail" className="lg:sticky lg:top-4 lg:self-start">
          <InvestigationContextRail
            pinned={workspace.pinned}
            recentlyOpened={workspace.recentlyOpened}
            focusedKey={entityKey(focused)}
            onFocus={handleFocusEntity}
            onUnpin={workspace.unpin}
            onReorder={(kind, from, to) => {
              const kindIndices = workspace.pinned.map((p, i) => (p.kind === kind ? i : -1)).filter((i) => i >= 0)
              workspace.reorderPinned(kindIndices[from], kindIndices[to])
            }}
          />
        </div>

        <div className="min-w-0 space-y-5">
          {!focused && (
            <WorkspaceEmptyState
              query={query}
              onQueryChange={setQuery}
              onRestoreSession={workspace.restoreSession}
              hasSavedSession={!!workspace.savedSession}
              searchResults={resultsPanel}
            />
          )}

          {focused && (
            <>
              <InvestigationHeader
                entity={focused}
                isPinned={workspace.pinned.some((p) => p.kind === focused.kind && p.id === focused.id)}
                onTogglePin={() => (workspace.pinned.some((p) => p.kind === focused.kind && p.id === focused.id) ? workspace.unpin(focused) : workspace.pin(focused))}
                aiReady={focused.kind === 'fixture' ? generatedCount > 0 : undefined}
                generatedCount={generatedCount}
                totalMarkets={markets.length}
                lastUpdated={history.reduce<string | null>((max, p) => (p.generated_at && (!max || p.generated_at > max) ? p.generated_at : max), null)}
                onShare={() => {
                  const url = new URL(window.location.href)
                  url.search = `?pin_type=${focused.kind}&pin_id=${focused.id}`
                  void navigator.clipboard?.writeText(url.toString())
                }}
                onExport={() => setNotebookOpen(true)}
                onSaveSession={workspace.saveSession}
              />

              <WorkspaceComposer
                focused={focused}
                capabilities={{
                  hasFocusedPrediction: !!workspace.focusedPredictionId,
                  onSwitchTab: setActiveTab,
                  onOpenEvidence: () => setActiveTab('evidence'),
                  onOpenGraph: openGraph,
                }}
              />

              <WorkspaceTabBar active={activeTab} onChange={setActiveTab} compareCount={compareSelected.length} />

              {activeTab === 'mission-brief' && (
                <MissionBriefTab
                  entity={focused}
                  history={history}
                  markets={markets}
                  isLoading={historyQuery.isPending || marketsQuery.isPending}
                  newsCount={newsQuery.data?.length ?? null}
                  kgLinked={kgEntityQuery.isSuccess ? true : kgEntityQuery.isError ? false : null}
                  pinnedCount={workspace.pinned.length}
                />
              )}

              {activeTab === 'predictions' && (
                <PredictionIntelligenceTab
                  entity={focused}
                  markets={markets}
                  history={history}
                  homeTeam={homeTeam}
                  awayTeam={awayTeam}
                  onFocusPrediction={workspace.setFocusedPredictionId}
                  selectedMarketKey={selectedMarketKey}
                  onSelectMarket={setSelectedMarketKey}
                  onGenerateSelected={() => selectedMarketKey && generateMutation.mutate(selectedMarketKey)}
                  generating={generateMutation.isPending}
                  generateError={generateMutation.error}
                  compareSelectedIds={compareSelected.map((c) => c.id)}
                  onToggleCompare={handleToggleCompare}
                />
              )}

              {activeTab === 'evidence' && (
                <div className="rounded-[var(--cd-radius-lg)] border p-4" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}>
                  <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
                    Open a prediction from the Predictions tab to inspect its full evidence.
                  </p>
                </div>
              )}

              {activeTab === 'comparison' && (
                <ComparisonTab
                  selectedIds={compareSelected.map((c) => c.id)}
                  labels={Object.fromEntries(compareSelected.map((c) => [c.id, c.label]))}
                  onFocusPrediction={workspace.setFocusedPredictionId}
                  onClearSelection={() => setCompareSelected([])}
                />
              )}

              {activeTab === 'timeline' && <PredictionTimelineTab history={history} markets={markets} onFocusPrediction={workspace.setFocusedPredictionId} />}

              {activeTab === 'related' && <RelatedFixturesTab entity={focused} onFocusFixture={(f) => handleFocusEntity({ kind: 'fixture', ...f })} />}

              {activeTab === 'insights' && <DecisionIntelligenceTab prediction={focusedPredictionQuery.data ?? null} isLoading={focusedPredictionQuery.isPending && !!workspace.focusedPredictionId} />}

              <IntelligenceCompleteness items={completenessItems} />
            </>
          )}
        </div>

        <div id="workspace-kg-panel" className="hidden xl:block">
          <KnowledgeGraphPanel entity={focused} onFocusEntity={handleFocusEntity} variant="panel" collapsed={kgCollapsed} onToggleCollapsed={() => setKgCollapsed((c) => !c)} />
        </div>
      </div>

      <WorkspaceActionBar
        onGenerate={() => setActiveTab('predictions')}
        onCompare={() => setActiveTab('comparison')}
        onKnowledgeGraph={() => setKgDrawerOpen(true)}
        onExportReport={() => setNotebookOpen(true)}
        onSaveSession={workspace.saveSession}
        onOpenMatch={() => focused?.kind === 'fixture' && window.open(`/app/${sport.slug}/matches/${focused.id}`, '_self')}
        canGenerate={!!canGenerate}
        canOpenMatch={focused?.kind === 'fixture'}
      />

      <EvidenceInspector
        predictionId={workspace.focusedPredictionId}
        markets={markets}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
        onClose={() => workspace.setFocusedPredictionId(null)}
      />

      {kgDrawerOpen && (
        <div className="fixed inset-0 z-50 flex items-end xl:hidden" onClick={() => setKgDrawerOpen(false)}>
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" aria-hidden="true" />
          <div
            className="relative max-h-[80vh] w-full overflow-hidden rounded-t-[var(--cd-radius-xl)] border-t"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <KnowledgeGraphPanel entity={focused} onFocusEntity={(e) => { handleFocusEntity(e); setKgDrawerOpen(false) }} variant="drawer" />
          </div>
        </div>
      )}

      {notebookOpen && focused && (
        <InvestigationNotebook
          entity={focused}
          history={history}
          markets={markets}
          completeness={completenessItems}
          onClose={() => setNotebookOpen(false)}
          onClearInvestigation={workspace.clearAll}
        />
      )}
    </div>
  )
}
