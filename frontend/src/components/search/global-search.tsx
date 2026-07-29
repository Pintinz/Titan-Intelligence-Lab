import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { LayoutDashboard, Newspaper, TrendingUp, Shield, Users, Trophy, Sliders } from 'lucide-react'
import {
  CommandPalette,
  CommandPaletteEmpty,
  CommandPaletteGroup,
  CommandPaletteItem,
} from '@/components/ui/command-palette'
import { useCommandPaletteStore } from '@/stores/command-palette-store'
import { NAV_GROUPS } from '@/components/layout/nav-config'
import { intelligenceApi } from '@/lib/api/intelligence'
import { marketsApi } from '@/lib/api/markets'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'

const SPORT_CODES: SportCode[] = ['football', 'basketball', 'baseball', 'table_tennis']

/**
 * Scoped honestly to what the backend can actually answer: navigation (instant, static), news
 * search (intelligence_router's `/news/search?query=`), markets/teams/players/competitions
 * (client-filtered after a cached fetch — none of these routers expose a `?q=` param, but their
 * lists are small enough to fetch once per sport and filter client-side, same pattern as the
 * pre-existing market search), and features (admin-only global list). There is still no free-text
 * search over the Knowledge Graph or individual fixtures/predictions/models — none of those
 * capabilities exist on the backend yet (see docs — Known Limitations), so this box doesn't
 * pretend they do.
 */
export function GlobalSearch() {
  const open = useCommandPaletteStore((s) => s.open)
  const setOpen = useCommandPaletteStore((s) => s.setOpen)
  const navigate = useNavigate()
  const role = useAuthStore((s) => s.profile?.role)
  const isAdmin = Boolean(role && isAtLeast(role, 'administrator'))
  const [query, setQuery] = useState('')
  const q = query.toLowerCase()

  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  const newsResults = useQuery({
    queryKey: ['search', 'news', query],
    queryFn: () => intelligenceApi.searchNews({ query, limit: 5 }),
    enabled: open && query.length > 1,
  })

  const marketResults = useQuery({
    queryKey: ['search', 'markets'],
    queryFn: () => marketsApi.list(),
    enabled: open,
    staleTime: 60_000,
  })

  const teamQueries = useQueries({
    queries: SPORT_CODES.map((sport) => ({
      queryKey: ['search', 'teams', sport],
      queryFn: () => sportsApi.listTeams(sport),
      enabled: open && query.length > 1,
      staleTime: 60_000,
    })),
  })
  const competitionQueries = useQueries({
    queries: SPORT_CODES.map((sport) => ({
      queryKey: ['search', 'competitions', sport],
      queryFn: () => sportsApi.listCompetitions(sport),
      enabled: open && query.length > 1,
      staleTime: 60_000,
    })),
  })
  const playerQueries = useQueries({
    queries: SPORT_CODES.map((sport) => ({
      queryKey: ['search', 'players', sport],
      queryFn: () => sportsApi.listPlayers(sport, 100),
      enabled: open && query.length > 1,
      staleTime: 60_000,
    })),
  })

  const featureResults = useQuery({
    queryKey: ['search', 'features'],
    queryFn: () => adminPlatformApi.listFeatures(),
    enabled: open && isAdmin,
    staleTime: 60_000,
  })

  const matchingMarkets = (marketResults.data ?? []).filter(
    (market) => query.length > 1 && (market.name.toLowerCase().includes(q) || market.market_key.toLowerCase().includes(q)),
  )
  const matchingTeams = teamQueries
    .flatMap((r) => r.data ?? [])
    .filter((team) => query.length > 1 && team.name.toLowerCase().includes(q))
  const matchingCompetitions = competitionQueries
    .flatMap((r) => r.data ?? [])
    .filter((c) => query.length > 1 && c.name.toLowerCase().includes(q))
  const matchingPlayers = playerQueries
    .flatMap((r) => r.data ?? [])
    .filter((p) => query.length > 1 && p.name.toLowerCase().includes(q))
  const matchingFeatures = (featureResults.data ?? []).filter(
    (f) => query.length > 1 && (String(f.name).toLowerCase().includes(q) || String(f.feature_key).toLowerCase().includes(q)),
  )

  const navItems = NAV_GROUPS.flatMap((group) => group.items).filter(
    (item) => !item.minRole || (role && isAtLeast(role, item.minRole)),
  )
  const matchingNav = navItems.filter((item) => query.length === 0 || item.label.toLowerCase().includes(q))

  function go(to: string) {
    navigate(to)
    setOpen(false)
  }

  if (!open) return null

  const hasAnyResult =
    matchingNav.length > 0 ||
    matchingMarkets.length > 0 ||
    matchingTeams.length > 0 ||
    matchingCompetitions.length > 0 ||
    matchingPlayers.length > 0 ||
    matchingFeatures.length > 0 ||
    (newsResults.data?.length ?? 0) > 0

  return (
    <CommandPalette value={query} onValueChange={setQuery}>
      {!hasAnyResult && <CommandPaletteEmpty>No results</CommandPaletteEmpty>}

      {matchingNav.length > 0 && (
        <CommandPaletteGroup heading="Go to">
          {matchingNav.map((item) => (
            <CommandPaletteItem key={item.to} onSelect={() => go(item.to)}>
              <LayoutDashboard className="h-4 w-4 text-text-muted" /> {item.label}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}

      {matchingTeams.length > 0 && (
        <CommandPaletteGroup heading="Teams">
          {matchingTeams.slice(0, 5).map((team) => (
            <CommandPaletteItem key={team.id} onSelect={() => go(`/app/teams/${team.id}`)}>
              <Shield className="h-4 w-4 text-text-muted" /> {team.name}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}

      {matchingPlayers.length > 0 && (
        <CommandPaletteGroup heading="Players">
          {matchingPlayers.slice(0, 5).map((player) => (
            <CommandPaletteItem key={player.id} onSelect={() => go(`/app/players/${player.id}`)}>
              <Users className="h-4 w-4 text-text-muted" /> {player.name}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}

      {matchingCompetitions.length > 0 && (
        <CommandPaletteGroup heading="Competitions">
          {matchingCompetitions.slice(0, 5).map((competition) => (
            <CommandPaletteItem key={competition.id} onSelect={() => go(`/app/competitions/${competition.id}`)}>
              <Trophy className="h-4 w-4 text-text-muted" /> {competition.name}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}

      {matchingMarkets.length > 0 && (
        <CommandPaletteGroup heading="Markets">
          {matchingMarkets.slice(0, 5).map((market) => (
            <CommandPaletteItem key={market.id} onSelect={() => go(`/app/predictions?market=${market.market_key}`)}>
              <TrendingUp className="h-4 w-4 text-text-muted" /> {market.name}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}

      {matchingFeatures.length > 0 && (
        <CommandPaletteGroup heading="Features">
          {matchingFeatures.slice(0, 5).map((feature, i) => (
            <CommandPaletteItem key={i} onSelect={() => go('/app/features')}>
              <Sliders className="h-4 w-4 text-text-muted" /> {String(feature.name)}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}

      {(newsResults.data?.length ?? 0) > 0 && (
        <CommandPaletteGroup heading="News">
          {newsResults.data!.map((article) => (
            <CommandPaletteItem key={article.id} onSelect={() => go(`/app/news/${article.id}`)}>
              <Newspaper className="h-4 w-4 text-text-muted" /> {article.title}
            </CommandPaletteItem>
          ))}
        </CommandPaletteGroup>
      )}
    </CommandPalette>
  )
}
