import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, ArrowUp, GitCompare, MessageCircle, Waypoints, X, Users, CircleDot } from 'lucide-react'
import { sportsApi, SPORT_OPTIONS, type SportCode } from '@/lib/api/sports'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityInput, InfinitySearchInput } from '@/components/infinity/primitives/input'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { HistoryTurn, CompareTurn, PulseTurn, RelationshipsTurn, NoteTurn, EvidencePanel } from './insights-turns'

export type PinnedKind = 'team' | 'fixture'

export interface PinnedEntity {
  kind: PinnedKind
  id: string
  label: string
}

interface Selection {
  id: string
  label: string
}

type Turn =
  | { id: number; kind: 'history'; entity: PinnedEntity }
  | { id: number; kind: 'compare'; predictionIds: string[]; labels: Record<string, string> }
  | { id: number; kind: 'pulse' }
  | { id: number; kind: 'relationships'; a: PinnedEntity; b: PinnedEntity }
  | { id: number; kind: 'note'; message: string }

/** Distributes over the `Turn` union (plain `Omit<Turn, 'id'>` would collapse to the shared
 * fields only, since `keyof` a union is an intersection) — this preserves each variant's own
 * fields so `appendTurn` can be called with any turn kind's actual shape, sans `id`. */
type TurnInput = Turn extends infer T ? (T extends { id: number } ? Omit<T, 'id'> : never) : never

export default function InsightsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const nextId = useRef(0)

  const [sportCode, setSportCode] = useState<SportCode | ''>('')
  const [entityKind, setEntityKind] = useState<PinnedKind>('team')
  const [query, setQuery] = useState('')
  const [pinned, setPinned] = useState<PinnedEntity[]>([])
  const [turns, setTurns] = useState<Turn[]>([])
  const [selected, setSelected] = useState<Selection[]>([])
  const [focusedPredictionId, setFocusedPredictionId] = useState<string | null>(null)
  const [freeText, setFreeText] = useState('')

  function appendTurn(turn: TurnInput) {
    nextId.current += 1
    setTurns((prev) => [...prev, { ...turn, id: nextId.current } as Turn])
  }

  function pin(entity: PinnedEntity) {
    setPinned((prev) => (prev.some((p) => p.kind === entity.kind && p.id === entity.id) ? prev : [...prev, entity]))
    // Guards against double-pinning (e.g. React StrictMode's double effect invocation on the
    // cross-link auto-pin below) re-appending a duplicate history turn for the same entity.
    setTurns((prev) => {
      const alreadyHasHistory = prev.some(
        (t) => t.kind === 'history' && t.entity.kind === entity.kind && t.entity.id === entity.id,
      )
      if (alreadyHasHistory) return prev
      nextId.current += 1
      return [...prev, { id: nextId.current, kind: 'history', entity }]
    })
    setQuery('')
  }

  function unpin(entity: PinnedEntity) {
    setPinned((prev) => prev.filter((p) => !(p.kind === entity.kind && p.id === entity.id)))
  }

  // Cross-link entry point: Match Intelligence pages link here with ?pin_type=fixture&pin_id=...
  const pinFixtureId = searchParams.get('pin_id')
  const pinType = searchParams.get('pin_type')
  const crossLinkFixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', pinFixtureId],
    queryFn: () => sportsApi.getFixture(pinFixtureId!),
    enabled: pinType === 'fixture' && !!pinFixtureId,
  })
  useEffect(() => {
    if (!crossLinkFixtureQuery.data) return
    const f = crossLinkFixtureQuery.data
    pin({ kind: 'fixture', id: f.id, label: `${f.home_team.short_name} vs ${f.away_team.short_name}` })
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('pin_type')
      next.delete('pin_id')
      return next
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossLinkFixtureQuery.data])

  const teamsQuery = useQuery({
    queryKey: ['sports', 'teams', sportCode],
    queryFn: () => sportsApi.listTeams(sportCode as SportCode),
    enabled: !!sportCode && entityKind === 'team',
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'fixtures', sportCode],
    queryFn: () => sportsApi.listFixtures(sportCode as SportCode, { limit: 50 }),
    enabled: !!sportCode && entityKind === 'fixture',
  })

  const teamResults = (teamsQuery.data ?? [])
    .filter((t) => t.name.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 8)
  const fixtureResults = (fixturesQuery.data ?? [])
    .filter((f) => `${f.home_team.name} ${f.away_team.name}`.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 8)

  function toggleSelect(id: string, label: string) {
    setSelected((prev) => (prev.some((s) => s.id === id) ? prev.filter((s) => s.id !== id) : [...prev, { id, label }]))
  }

  function triggerCompare() {
    if (selected.length < 2) {
      appendTurn({ kind: 'note', message: 'Select at least two predictions below (check the boxes) to compare them.' })
      return
    }
    appendTurn({
      kind: 'compare',
      predictionIds: selected.map((s) => s.id),
      labels: Object.fromEntries(selected.map((s) => [s.id, s.label])),
    })
    setSelected([])
  }

  function triggerPulse() {
    if (turns.some((t) => t.kind === 'pulse')) return
    appendTurn({ kind: 'pulse' })
  }

  function triggerRelationships() {
    if (pinned.length < 2) {
      appendTurn({ kind: 'note', message: "Pin at least two teams or matches to see how they're connected." })
      return
    }
    const [a, b] = pinned.slice(-2)
    appendTurn({ kind: 'relationships', a, b })
  }

  function handleAsk(text: string) {
    const q = text.trim().toLowerCase()
    if (!q) return
    if (q.includes('compare')) triggerCompare()
    else if (q.includes('pulse') || q.includes('community')) triggerPulse()
    else if (q.includes('connect') || q.includes('relationship') || q.includes('graph') || q.includes('link'))
      triggerRelationships()
    else if (q.includes('history'))
      appendTurn({
        kind: 'note',
        message: 'Prediction history appears automatically for anything you pin — try pinning a team or match in the rail.',
      })
    else
      appendTurn({
        kind: 'note',
        message:
          "I can compare predictions, check community pulse, or find Knowledge Graph relationships for what's pinned — free-form questions beyond that need a backend NL service that doesn't exist yet. Try one of the suggestions below, or pin a team/match to get started.",
      })
    setFreeText('')
  }

  const hasContent = turns.length > 0

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr_280px] xl:grid-cols-[280px_1fr_320px]">
      {/* Context rail */}
      <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <div>
          <p className="font-infinity-body text-[11px] font-semibold uppercase tracking-[0.16em] text-infinity-signal">
            TitanIQ Assistant
          </p>
          <h1 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
            Intelligence Workspace
          </h1>
        </div>

        <InfinityPanel>
          <InfinityLabel>Pin a team or match</InfinityLabel>

          <div className="mt-2 flex gap-1.5">
            {SPORT_OPTIONS.map((s) => (
              <InfinityButton
                key={s.code}
                size="sm"
                variant={sportCode === s.code ? 'secondary' : 'ghost'}
                onClick={() => setSportCode(sportCode === s.code ? '' : s.code)}
              >
                {s.label}
              </InfinityButton>
            ))}
          </div>

          {sportCode && (
            <>
              <div className="mt-3 flex gap-1.5">
                <InfinityButton
                  size="sm"
                  variant={entityKind === 'team' ? 'outline' : 'ghost'}
                  onClick={() => { setEntityKind('team'); setQuery('') }}
                  className="flex-1"
                >
                  <Users className="size-3.5" /> Teams
                </InfinityButton>
                <InfinityButton
                  size="sm"
                  variant={entityKind === 'fixture' ? 'outline' : 'ghost'}
                  onClick={() => { setEntityKind('fixture'); setQuery('') }}
                  className="flex-1"
                >
                  <CircleDot className="size-3.5" /> Matches
                </InfinityButton>
              </div>

              <div className="mt-2">
                <InfinitySearchInput
                  placeholder={entityKind === 'team' ? 'Search teams…' : 'Search matches…'}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label={entityKind === 'team' ? 'Search teams' : 'Search matches'}
                />
              </div>

              <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
                {entityKind === 'team' && teamsQuery.isPending && <InfinitySkeleton className="h-8" />}
                {entityKind === 'team' &&
                  teamResults.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => pin({ kind: 'team', id: t.id, label: t.name })}
                      className="block w-full truncate rounded-infinity-sm px-2 py-1.5 text-left font-infinity-body text-[12px] text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary"
                    >
                      {t.name}
                    </button>
                  ))}
                {entityKind === 'fixture' && fixturesQuery.isPending && <InfinitySkeleton className="h-8" />}
                {entityKind === 'fixture' &&
                  fixtureResults.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() =>
                        pin({ kind: 'fixture', id: f.id, label: `${f.home_team.short_name} vs ${f.away_team.short_name}` })
                      }
                      className="block w-full truncate rounded-infinity-sm px-2 py-1.5 text-left font-infinity-body text-[12px] text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary"
                    >
                      {f.home_team.short_name} vs {f.away_team.short_name}
                    </button>
                  ))}
              </div>
            </>
          )}
        </InfinityPanel>

        {pinned.length > 0 && (
          <div>
            <InfinityLabel>Pinned</InfinityLabel>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {pinned.map((p) => (
                <span
                  key={`${p.kind}:${p.id}`}
                  className="inline-flex items-center gap-1 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 py-1 pl-2 pr-1 font-infinity-body text-[11px] text-infinity-text-primary"
                >
                  {p.label}
                  <button
                    type="button"
                    onClick={() => unpin(p)}
                    aria-label={`Unpin ${p.label}`}
                    className="rounded-full p-0.5 text-infinity-text-muted hover:bg-infinity-ground-1 hover:text-infinity-text-primary"
                  >
                    <X className="size-3" aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Conversation stream */}
      <div className="min-w-0 space-y-4">
        {!hasContent && (
          <InfinityEmptyState
            icon={Sparkles}
            title="Pin something to get started"
            description="Search a team or match in the rail — TitanIQ pulls its real prediction history immediately, and you can compare, cross-reference, or explore its Knowledge Graph connections from there."
          />
        )}

        {turns.map((turn) => {
          if (turn.kind === 'history')
            return (
              <HistoryTurn
                key={turn.id}
                entity={turn.entity}
                selectedIds={selected.map((s) => s.id)}
                onToggleSelect={(id) => toggleSelect(id, turn.entity.label)}
                onFocusPrediction={setFocusedPredictionId}
              />
            )
          if (turn.kind === 'compare')
            return (
              <CompareTurn
                key={turn.id}
                predictionIds={turn.predictionIds}
                labels={turn.labels}
                onFocusPrediction={setFocusedPredictionId}
              />
            )
          if (turn.kind === 'pulse') return <PulseTurn key={turn.id} />
          if (turn.kind === 'relationships') return <RelationshipsTurn key={turn.id} a={turn.a} b={turn.b} />
          return <NoteTurn key={turn.id} message={turn.message} />
        })}

        <div className="sticky bottom-4 space-y-2 border-t border-infinity-border-hairline bg-infinity-ground-0/95 pt-3 backdrop-blur-sm">
          <div className="flex flex-wrap gap-2">
            <InfinityButton size="sm" variant="outline" onClick={triggerCompare} disabled={selected.length < 2}>
              <GitCompare className="size-3.5" /> Compare {selected.length > 0 ? `${selected.length} selected` : 'selected'}
            </InfinityButton>
            <InfinityButton size="sm" variant="outline" onClick={triggerPulse}>
              <MessageCircle className="size-3.5" /> Community pulse
            </InfinityButton>
            <InfinityButton size="sm" variant="outline" onClick={triggerRelationships} disabled={pinned.length < 2}>
              <Waypoints className="size-3.5" /> How are these connected?
            </InfinityButton>
          </div>

          <form
            className="flex items-center gap-2 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-1 px-3 py-2"
            onSubmit={(e) => { e.preventDefault(); handleAsk(freeText) }}
          >
            <Sparkles className="size-4 shrink-0 text-infinity-signal" aria-hidden="true" />
            <InfinityInput
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              placeholder="Ask about what's pinned — try 'compare' or 'how are these connected'"
              className="h-auto border-0 bg-transparent p-0 focus:ring-0"
              aria-label="Ask the Assistant"
            />
            <button
              type="submit"
              disabled={!freeText.trim()}
              aria-label="Send"
              className="flex size-6 shrink-0 items-center justify-center rounded-full bg-infinity-ground-2 text-infinity-text-muted transition-colors hover:text-infinity-text-primary disabled:opacity-40"
            >
              <ArrowUp className="size-3" aria-hidden="true" />
            </button>
          </form>
          <p className="font-infinity-body text-[11px] text-infinity-text-muted">
            Grounded and deterministic today — every answer traces to real TitanIQ data, no free-form AI conversation yet.
          </p>
        </div>
      </div>

      {/* Evidence panel */}
      <div className="lg:sticky lg:top-4 lg:self-start">
        <InfinityLabel>Evidence</InfinityLabel>
        <div className="mt-2">
          {!focusedPredictionId && (
            <InfinityEmptyState
              icon={Sparkles}
              title="Nothing focused"
              description="Click any prediction value in the conversation to see its full confidence breakdown and evidence here."
            />
          )}
          {focusedPredictionId && <EvidencePanel predictionId={focusedPredictionId} />}
        </div>
      </div>
    </div>
  )
}
