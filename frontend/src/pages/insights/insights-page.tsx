import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Sparkles, ArrowUp, History, GitCompare, MessageCircle } from 'lucide-react'
import { sportsApi, SPORT_OPTIONS, type SportCode } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { intelligenceApi } from '@/lib/api/intelligence'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { PredictionPanel } from '@/components/domain/prediction-panel'

const SUGGESTED = [
  { icon: History, label: 'See a team\'s prediction history', anchor: '#explore' },
  { icon: GitCompare, label: 'Compare two predictions side by side', anchor: '#compare' },
  { icon: MessageCircle, label: "Check today's community pulse", anchor: '#pulse' },
]

export default function InsightsPage() {
  const [sportCode, setSportCode] = useState<SportCode | ''>('')
  const [teamId, setTeamId] = useState<string | ''>('')
  const [marketId, setMarketId] = useState<string | ''>('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const teamsQuery = useQuery({
    queryKey: ['sports', 'teams', sportCode],
    queryFn: () => sportsApi.listTeams(sportCode as SportCode),
    enabled: !!sportCode,
  })
  const marketsQuery = useQuery({
    queryKey: ['markets', sportCode, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sportCode as SportCode, status: 'production' }),
    enabled: !!sportCode,
  })
  const historyQuery = useQuery({
    queryKey: ['predictions', 'history', teamId, marketId],
    queryFn: () => predictionsApi.history(teamId, marketId || undefined),
    enabled: !!teamId,
  })
  const communityQuery = useQuery({
    queryKey: ['intelligence', 'community-topics', 'top'],
    queryFn: () => intelligenceApi.communityTopics(),
  })

  const compare = useMutation({
    mutationFn: () => predictionsApi.compare(selectedIds),
  })

  const topTopics = [...(communityQuery.data ?? [])].sort((a, b) => b.volume - a.volume).slice(0, 5)
  const maxVolume = Math.max(1, ...topTopics.map((t) => t.volume))

  function toggleSelected(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
    compare.reset()
  }

  return (
    <div className="mx-auto max-w-4xl space-y-10 p-4 lg:p-8">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          TitanIQ Insights
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">Ask why, not just what</h1>
        <p className="mt-2 max-w-lg text-sm text-text-secondary">
          Every prediction can explain itself. Insights today is grounded and deterministic — pick
          what you want to explore below. Free-form conversation arrives in a future update.
        </p>

        <div className="mt-4 flex items-center gap-2 rounded-md border border-border-subtle bg-bg-elevated px-3 py-2.5 opacity-60">
          <Sparkles className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
          <span className="flex-1 text-sm text-text-muted">Ask TitanIQ anything — coming soon</span>
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-bg-secondary">
            <ArrowUp className="size-3 text-text-muted" aria-hidden="true" />
          </span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {SUGGESTED.map((s) => (
            <a
              key={s.label}
              href={s.anchor}
              className="inline-flex items-center gap-1.5 rounded-full border border-border-default px-3 py-1.5 text-xs text-text-secondary hover:border-accent-primary hover:text-accent-primary"
            >
              <s.icon className="size-3.5" aria-hidden="true" />
              {s.label}
            </a>
          ))}
        </div>
      </div>

      <section id="explore" className="scroll-mt-20">
        <div className="mb-4 flex items-center gap-2">
          <History className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Prediction history</p>
        </div>

        <Card className="p-5">
          <div className="flex flex-wrap gap-3">
            <Select value={sportCode} onValueChange={(v) => { setSportCode(v as SportCode); setTeamId(''); setMarketId('') }}>
              <SelectTrigger className="w-44" aria-label="Sport"><SelectValue placeholder="Choose a sport" /></SelectTrigger>
              <SelectContent>
                {SPORT_OPTIONS.map((s) => (
                  <SelectItem key={s.code} value={s.code}>{s.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={teamId} onValueChange={setTeamId} disabled={!sportCode || !teamsQuery.data}>
              <SelectTrigger className="w-52" aria-label="Team"><SelectValue placeholder="Choose a team" /></SelectTrigger>
              <SelectContent>
                {(teamsQuery.data ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={marketId} onValueChange={setMarketId} disabled={!sportCode || !marketsQuery.data}>
              <SelectTrigger className="w-56" aria-label="Market"><SelectValue placeholder="Any market" /></SelectTrigger>
              <SelectContent>
                {(marketsQuery.data ?? []).map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="mt-5">
            {!teamId && <p className="text-sm text-text-muted">Choose a sport and team to see its prediction history.</p>}
            {teamId && historyQuery.isPending && (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14" />)}
              </div>
            )}
            {teamId && historyQuery.isError && <ErrorState error={historyQuery.error} onRetry={() => void historyQuery.refetch()} />}
            {teamId && historyQuery.data && historyQuery.data.length === 0 && (
              <EmptyState title="No prediction history yet" description="TitanIQ hasn't generated a prediction for this team yet." />
            )}
            {teamId && historyQuery.data && historyQuery.data.length > 0 && (
              <ul className="space-y-2">
                {historyQuery.data.map((prediction) => (
                  <li key={prediction.id} className="rounded-md border border-border-default">
                    <div className="flex items-center gap-3 p-3">
                      <Checkbox
                        checked={selectedIds.includes(prediction.id)}
                        onCheckedChange={() => toggleSelected(prediction.id)}
                        aria-label="Select for comparison"
                      />
                      <button
                        type="button"
                        className="flex flex-1 items-center justify-between gap-3 text-left"
                        onClick={() => setExpandedId(expandedId === prediction.id ? null : prediction.id)}
                      >
                        <div className="min-w-0">
                          <p className="truncate font-telemetry text-sm font-medium text-text-primary">
                            {String(prediction.value)}
                          </p>
                          <p className="truncate font-mono text-[11px] text-text-muted">market {prediction.market_id}</p>
                        </div>
                        <ConfidenceTelemetry confidence={prediction.confidence.overall} size="sm" />
                      </button>
                    </div>
                    {expandedId === prediction.id && (
                      <div className="border-t border-border-subtle p-3">
                        <PredictionPanel prediction={prediction} />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </section>

      <section id="compare" className="scroll-mt-20">
        <div className="mb-4 flex items-center gap-2">
          <GitCompare className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Compare predictions</p>
        </div>
        <Card className="p-5">
          <p className="text-sm text-text-secondary">
            Select two or more predictions above, then compare them side by side.
          </p>
          <Button className="mt-3" disabled={selectedIds.length < 2 || compare.isPending} onClick={() => compare.mutate()}>
            {compare.isPending ? 'Comparing…' : `Compare ${selectedIds.length || ''} selected`}
          </Button>

          {compare.isError && <div className="mt-4"><ErrorState error={compare.error} onRetry={() => compare.mutate()} /></div>}

          {compare.data && (
            <div className="mt-5 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-text-muted">
                  <tr>
                    <th className="py-1.5 pr-4 font-medium">Value</th>
                    <th className="py-1.5 pr-4 font-medium">Probability</th>
                    <th className="py-1.5 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.data.map((p) => (
                    <tr key={p.id} className="border-t border-border-subtle">
                      <td className="py-2 pr-4 font-telemetry text-text-primary">{String(p.value)}</td>
                      <td className="py-2 pr-4 font-mono tabular-nums text-text-secondary">{(p.probability * 100).toFixed(1)}%</td>
                      <td className="py-2"><ConfidenceTelemetry confidence={p.confidence.overall} size="sm" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </section>

      <section id="pulse" className="scroll-mt-20">
        <div className="mb-4 flex items-center gap-2">
          <MessageCircle className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Today's community pulse</p>
        </div>
        <Card className="p-5">
          {communityQuery.isPending && <Skeleton className="h-24" />}
          {communityQuery.isError && <ErrorState error={communityQuery.error} onRetry={() => void communityQuery.refetch()} />}
          {topTopics.length === 0 && !communityQuery.isPending && !communityQuery.isError && (
            <EmptyState title="No community signal yet" description="No tracked topics right now." />
          )}
          {topTopics.length > 0 && (
            <div className="space-y-3">
              {topTopics.map((topic) => (
                <div key={topic.id} className="flex items-center gap-4">
                  <span className="w-40 shrink-0 truncate text-sm text-text-primary">{topic.title}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-secondary">
                    <div className="h-full rounded-full bg-accent-primary" style={{ width: `${(topic.volume / maxVolume) * 100}%` }} />
                  </div>
                  <span className="w-16 shrink-0 text-right font-mono text-xs text-text-muted">{topic.volume.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </section>
    </div>
  )
}
