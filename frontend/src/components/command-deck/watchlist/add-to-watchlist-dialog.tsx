import { useEffect, useState } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Command } from 'cmdk'
import { Search, Check, Users, Trophy, CircleDot } from 'lucide-react'
import { useQueries } from '@tanstack/react-query'
import { sportsApi } from '@/lib/api/sports'
import { useAvailableSports } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { cn } from '@/lib/cn'

/**
 * AddToWatchlistDialog — a local `cmdk` + Radix Dialog instrument, the same primitives
 * `InfinityCommandPalette` already uses (not a second command-palette architecture). Teams and
 * competitions are fetched per sport once the dialog opens and filtered client-side (same
 * technique already proven live on Team/Competition Intelligence search); matches use the real
 * server-side `search` param on `listFixturesPaged`, debounced, only once the user has typed
 * something — never a full-schedule preload. Selecting an item calls the one real follow/unfollow
 * path (`useWatchlist().toggle`) and stays open so several items can be added in one pass.
 */
export function AddToWatchlistDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const watchlist = useWatchlist()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    if (!open) setSearch('')
  }, [open])

  const availableSports = useAvailableSports()
  const teamQueries = useQueries({
    queries: availableSports.map((s) => ({
      queryKey: ['sports', s.code, 'teams', 'add-watchlist'],
      queryFn: () => sportsApi.listTeams(s.code),
      enabled: open,
    })),
  })
  const competitionQueries = useQueries({
    queries: availableSports.map((s) => ({
      queryKey: ['sports', s.code, 'competitions', 'add-watchlist'],
      queryFn: () => sportsApi.listCompetitions(s.code),
      enabled: open,
    })),
  })
  const matchQueries = useQueries({
    queries: availableSports.map((s) => ({
      queryKey: ['sports', s.code, 'fixtures', 'search', debouncedSearch],
      queryFn: () => sportsApi.listFixturesPaged(s.code, { search: debouncedSearch, limit: 6 }),
      enabled: open && debouncedSearch.trim().length >= 2,
    })),
  })

  const teams = teamQueries.flatMap((q, i) => (q.data ?? []).map((t) => ({ ...t, sportSlug: availableSports[i].slug })))
  const competitions = competitionQueries.flatMap((q, i) => (q.data ?? []).map((c) => ({ ...c, sportSlug: availableSports[i].slug })))
  const matches = matchQueries.flatMap((q) => q.data?.items ?? [])

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-[14%] z-50 w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-[var(--cd-radius-lg)] border"
          style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', boxShadow: 'var(--cd-elevation-2)' }}
          aria-describedby={undefined}
        >
          <DialogPrimitive.Title className="sr-only">Add to Watchlist</DialogPrimitive.Title>
          <Command
            label="Add to Watchlist"
            className="flex max-h-[70vh] flex-col"
            filter={(value, search, keywords) => {
              const haystack = [value, ...(keywords ?? [])].join(' ').toLowerCase()
              return haystack.includes(search.toLowerCase()) ? 1 : 0
            }}
          >
            <div className="flex items-center gap-2 border-b px-4 py-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <Search className="size-4 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
              <Command.Input
                autoFocus
                value={search}
                onValueChange={setSearch}
                placeholder="Search teams, competitions, or matches…"
                className="w-full bg-transparent font-[var(--cd-font-body)] text-sm focus:outline-none"
                style={{ color: 'var(--cd-text-primary)' }}
              />
              <kbd className="shrink-0 rounded border px-1.5 py-0.5 font-[var(--cd-font-tabular)] text-[10px]" style={{ borderColor: 'var(--cd-border-default)', color: 'var(--cd-text-muted)' }}>
                Esc
              </kbd>
            </div>
            <Command.List className="overflow-y-auto p-2">
              <Command.Empty className="px-2 py-6 text-center font-[var(--cd-font-body)] text-sm" style={{ color: 'var(--cd-text-muted)' }}>
                {search.trim().length === 0 ? 'Start typing to search.' : 'No matches.'}
              </Command.Empty>

              {teams.length > 0 && (
                <Command.Group heading="Teams" className={GROUP_HEADING_CLASS}>
                  {teams.map((team) => (
                    <ResultItem
                      key={team.id}
                      value={`team-${team.id}`}
                      keywords={[team.name, team.country ?? '']}
                      icon={Users}
                      label={team.name}
                      sub={team.country}
                      following={watchlist.isFollowing('team', team.id)}
                      onSelect={() => watchlist.toggle('team', team.id)}
                    />
                  ))}
                </Command.Group>
              )}

              {competitions.length > 0 && (
                <Command.Group heading="Competitions" className={GROUP_HEADING_CLASS}>
                  {competitions.map((competition) => (
                    <ResultItem
                      key={competition.id}
                      value={`competition-${competition.id}`}
                      keywords={[competition.name, competition.country ?? '']}
                      icon={Trophy}
                      label={competition.name}
                      sub={competition.country}
                      following={watchlist.isFollowing('competition', competition.id)}
                      onSelect={() => watchlist.toggle('competition', competition.id)}
                    />
                  ))}
                </Command.Group>
              )}

              {matches.length > 0 && (
                <Command.Group heading="Matches" className={GROUP_HEADING_CLASS}>
                  {matches.map((fixture) => (
                    <ResultItem
                      key={fixture.id}
                      value={`fixture-${fixture.id}`}
                      keywords={[fixture.home_team.name, fixture.away_team.name, fixture.competition_name]}
                      icon={CircleDot}
                      label={`${fixture.home_team.name} vs ${fixture.away_team.name}`}
                      sub={fixture.competition_name}
                      following={watchlist.isFollowing('fixture', fixture.id)}
                      onSelect={() => watchlist.toggle('fixture', fixture.id)}
                    />
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

const GROUP_HEADING_CLASS =
  'mb-1 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-[var(--cd-font-telemetry)] [&_[cmdk-group-heading]]:text-[10.5px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.07em] [&_[cmdk-group-heading]]:text-[var(--cd-text-muted)]'

function ResultItem({
  value,
  keywords,
  icon: Icon,
  label,
  sub,
  following,
  onSelect,
}: {
  value: string
  keywords: string[]
  icon: typeof Users
  label: string
  sub?: string | null
  following: boolean
  onSelect: () => void
}) {
  return (
    <Command.Item
      value={value}
      keywords={keywords}
      onSelect={onSelect}
      className={cn(
        'group flex cursor-pointer items-center gap-2.5 rounded-[var(--cd-radius-sm)] px-2.5 py-2 font-[var(--cd-font-body)] text-sm',
        'data-[selected=true]:bg-[var(--cd-accent-muted)]',
      )}
      style={{ color: 'var(--cd-text-secondary)' }}
    >
      <Icon className="size-4 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">
        {label}
        {sub && <span style={{ color: 'var(--cd-text-muted)' }}> · {sub}</span>}
      </span>
      {following ? (
        <span className="flex shrink-0 items-center gap-1 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-accent)' }}>
          <Check className="size-3.5" aria-hidden="true" /> Added
        </span>
      ) : (
        <span className="shrink-0 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em] opacity-0 group-data-[selected=true]:opacity-100" style={{ color: 'var(--cd-text-muted)' }}>
          Add
        </span>
      )}
    </Command.Item>
  )
}
