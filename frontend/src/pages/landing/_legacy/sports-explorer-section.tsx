import { useState, type ReactNode } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { SAMPLE_COMPETITIONS, SAMPLE_TEAMS, SAMPLE_PLAYERS, SAMPLE_PREDICTIONS_BY_SPORT } from '@/pages/landing/sample-data'
import { SPORT_OPTIONS } from '@/lib/api/sports'

export function SportsExplorerSection() {
  const [sport, setSport] = useState<string>(SPORT_OPTIONS[0]?.code ?? 'football')

  const competitions = SAMPLE_COMPETITIONS.filter((c) => c.sport_code === sport)
  const teams = SAMPLE_TEAMS.filter((t) => t.sport_code === sport)
  const players = SAMPLE_PLAYERS.filter((p) => p.sport_code === sport)
  const predictionCount = SAMPLE_PREDICTIONS_BY_SPORT[sport]?.length ?? 0

  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="sports-explorer">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Explore by sport</h2>
        <p className="mt-3 text-text-secondary">Trending competitions, teams, and players — the entry point into each sport's intelligence.</p>
      </div>

      <Tabs value={sport} onValueChange={setSport} className="mt-8">
        <TabsList className="mx-auto w-fit">
          {SPORT_OPTIONS.map((option) => (
            <TabsTrigger key={option.code} value={option.code}>
              {option.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={sport}>
          <div className="mt-8 grid gap-6 sm:grid-cols-3">
            <ExplorerColumn title="Trending competitions">
              {competitions.length === 0 && <EmptyRow />}
              {competitions.map((c) => (
                <div key={c.id} className="flex items-center justify-between rounded-md border border-border-subtle px-3 py-2 text-sm">
                  <span className="text-text-primary">{c.name}</span>
                  <span className="text-xs text-text-muted">{c.country ?? 'International'}</span>
                </div>
              ))}
            </ExplorerColumn>

            <ExplorerColumn title="Popular teams">
              {teams.length === 0 && <EmptyRow />}
              {teams.map((t) => (
                <div key={t.id} className="flex items-center gap-2 rounded-md border border-border-subtle px-3 py-2 text-sm">
                  <TeamMonogramBadge id={t.id} name={t.short_name} size={24} />
                  <span className="text-text-primary">{t.name}</span>
                </div>
              ))}
            </ExplorerColumn>

            <ExplorerColumn title="Featured players">
              {players.length === 0 && <EmptyRow />}
              {players.map((p) => (
                <div key={p.id} className="flex items-center justify-between rounded-md border border-border-subtle px-3 py-2 text-sm">
                  <span className="text-text-primary">{p.name}</span>
                  <span className="text-xs text-text-muted">{p.position ?? p.team_name}</span>
                </div>
              ))}
            </ExplorerColumn>
          </div>

          <p className="mt-6 text-center text-sm text-text-muted">
            {predictionCount} illustrative predictions available for this sport today.
          </p>
        </TabsContent>
      </Tabs>
    </section>
  )
}

function ExplorerColumn({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{title}</span>
      {children}
    </div>
  )
}

function EmptyRow() {
  return <p className="text-sm text-text-muted">No illustrative entries for this sport yet.</p>
}
