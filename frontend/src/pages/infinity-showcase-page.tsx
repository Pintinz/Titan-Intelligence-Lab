import { useState } from 'react'
import { Radio, Trophy, Newspaper, Zap, Activity, Plug, ShieldCheck, Search, Bell, User, LayoutDashboard } from 'lucide-react'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityBadge, type DomainKey } from '@/components/infinity/primitives/badge'
import { InfinityInput, InfinitySearchInput } from '@/components/infinity/primitives/input'
import { InfinityTabs, InfinityTabsList, InfinityTabsTrigger, InfinityTabsContent } from '@/components/infinity/primitives/tabs'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { InfinityPredictionCard } from '@/components/infinity/cards/prediction-card'
import { InfinityPlayerCard } from '@/components/infinity/cards/player-card'
import { InfinityTeamCard } from '@/components/infinity/cards/team-card'
import { InfinityNewsCard } from '@/components/infinity/cards/news-card'
import { InfinityMetricCard } from '@/components/infinity/cards/metric-card'
import { InfinityProviderCard } from '@/components/infinity/cards/provider-card'
import { InfinityOperationsCard } from '@/components/infinity/cards/operations-card'
import { InfinityConfidenceRing } from '@/components/infinity/charts/confidence-ring'
import { InfinityMomentumCurve } from '@/components/infinity/charts/momentum-curve'
import { InfinityRadarChart } from '@/components/infinity/charts/radar-chart'
import { InfinityPredictionEvolution } from '@/components/infinity/charts/prediction-evolution'
import { InfinityHeatmap } from '@/components/infinity/charts/heatmap'
import { InfinityConfidenceTelemetry } from '@/components/infinity/confidence-telemetry'
import { InfinityIntelligenceRail, type RailItem } from '@/components/infinity/intelligence-rail'
import { InfinityNavItem, InfinityBreadcrumbs, InfinitySportSwitcher, InfinityCommandPaletteShell } from '@/components/infinity/nav/nav-primitives'

const DOMAINS: DomainKey[] = [
  'football',
  'basketball',
  'baseball',
  'table-tennis',
  'predictions',
  'knowledge-graph',
  'learning',
  'news',
  'community',
  'operations',
  'infrastructure',
  'alerts',
  'security',
]

const RAIL_ITEMS: RailItem[] = [
  { id: '1', icon: Radio, label: 'Arsenal vs Chelsea — 67\'', meta: 'LIVE · Football', status: 'live' },
  { id: '2', icon: Zap, label: 'Lakers ML — 82% confidence', meta: 'High confidence', status: 'high-confidence' },
  { id: '3', icon: Newspaper, label: 'Star striker ruled out', meta: '4 min ago', status: 'breaking' },
  { id: '4', icon: Activity, label: 'Champion model retraining', meta: 'Learning pipeline', status: 'learning' },
  { id: '5', icon: Plug, label: 'API-Football latency elevated', meta: 'Alert', status: 'alert' },
  { id: '6', icon: Trophy, label: 'Real Madrid vs Barcelona', meta: 'Sat 20:00', status: 'upcoming' },
]

/**
 * Infinity Design System showcase — dev-only, unlinked from primary navigation. Renders
 * every Phase 11.0 primitive so the system can be inspected/screenshotted for the finish
 * review without wiring anything into a real page. Not part of Phase 11.0's deliverable
 * scope beyond "verified browser build" — this route is the verification fixture.
 */
export default function InfinityShowcasePage() {
  const [sport, setSport] = useState('football')

  return (
    <div className="min-h-svh bg-infinity-ground-0 p-8 text-infinity-text-primary">
      <div className="mx-auto max-w-5xl space-y-10">
        <header>
          <InfinityLabel tone="var(--infinity-signal)">Phase 11.0 · Foundation</InfinityLabel>
          <h1 className="mt-1 font-infinity-display text-[28px] font-semibold">TitanIQ Infinity Design System</h1>
          <p className="mt-1 max-w-xl font-infinity-body text-[14px] text-infinity-text-secondary">
            Dev-only showcase — every foundation primitive rendered for review. Unlinked from app navigation.
          </p>
        </header>

        <Section title="Color language — domain wheel">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {DOMAINS.map((d) => (
              <div key={d} className="min-w-0 space-y-1.5">
                <div className="h-10 rounded-infinity-sm" style={{ backgroundColor: `var(--infinity-domain-${d})` }} />
                <p className="truncate font-infinity-mono text-[10px] text-infinity-text-muted">{d}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Typography scale">
          <div className="space-y-2">
            <p style={{ font: 'var(--infinity-text-display-2xl)', letterSpacing: 'var(--infinity-text-display-2xl-tracking)' }}>Display 2XL</p>
            <p style={{ font: 'var(--infinity-text-display-xl)' }}>Display XL</p>
            <p style={{ font: 'var(--infinity-text-section-title)' }}>Section title</p>
            <p style={{ font: 'var(--infinity-text-card-title)' }}>Card title</p>
            <p style={{ font: 'var(--infinity-text-body)' }}>Body text at default weight and size.</p>
            <p style={{ font: 'var(--infinity-text-metadata)', letterSpacing: 'var(--infinity-text-metadata-tracking)', textTransform: 'uppercase' }}>
              Metadata label
            </p>
            <p style={{ font: 'var(--infinity-text-stat-lg)' }}>1,284</p>
            <p style={{ font: 'var(--infinity-text-telemetry)' }} className="font-infinity-mono">
              14:32:07.221
            </p>
          </div>
        </Section>

        <Section title="Buttons">
          <div className="flex flex-wrap gap-2">
            <InfinityButton variant="primary">Primary</InfinityButton>
            <InfinityButton variant="secondary">Secondary</InfinityButton>
            <InfinityButton variant="ghost">Ghost</InfinityButton>
            <InfinityButton variant="outline">Outline</InfinityButton>
            <InfinityButton variant="danger">Danger</InfinityButton>
            <InfinityButton variant="success">Success</InfinityButton>
            <InfinityButton variant="primary" disabled>
              Disabled
            </InfinityButton>
          </div>
        </Section>

        <Section title="Badges">
          <div className="flex flex-wrap gap-2">
            <InfinityBadge domain="football">Football</InfinityBadge>
            <InfinityBadge domain="predictions">Predictions</InfinityBadge>
            <InfinityBadge domain="knowledge-graph">Knowledge Graph</InfinityBadge>
            <InfinityBadge tone="var(--infinity-live)">Live</InfinityBadge>
            <InfinityBadge tone="var(--infinity-success)">Healthy</InfinityBadge>
          </div>
        </Section>

        <Section title="Forms">
          <div className="grid max-w-md gap-3">
            <InfinityInput placeholder="Standard input" />
            <InfinitySearchInput placeholder="Search matches, players, providers…" />
          </div>
        </Section>

        <Section title="Tabs">
          <InfinityTabs defaultValue="overview">
            <InfinityTabsList>
              <InfinityTabsTrigger value="overview">Overview</InfinityTabsTrigger>
              <InfinityTabsTrigger value="stats">Statistics</InfinityTabsTrigger>
              <InfinityTabsTrigger value="evidence">Evidence</InfinityTabsTrigger>
            </InfinityTabsList>
            <InfinityTabsContent value="overview" className="pt-3 text-[13px] text-infinity-text-secondary">
              Overview panel content.
            </InfinityTabsContent>
            <InfinityTabsContent value="stats" className="pt-3 text-[13px] text-infinity-text-secondary">
              Statistics panel content.
            </InfinityTabsContent>
            <InfinityTabsContent value="evidence" className="pt-3 text-[13px] text-infinity-text-secondary">
              Evidence panel content.
            </InfinityTabsContent>
          </InfinityTabs>
        </Section>

        <Section title="Empty & loading states">
          <div className="grid gap-3 sm:grid-cols-2">
            <InfinityEmptyState
              icon={Plug}
              title="No providers configured"
              description="Register a provider to start monitoring health, usage, and connection status."
              action={{ label: 'Register provider', onClick: () => {} }}
            />
            <div className="space-y-2">
              <InfinitySkeleton className="h-6 w-2/3" />
              <InfinitySkeleton className="h-4 w-full" />
              <InfinitySkeleton className="h-4 w-5/6" />
            </div>
          </div>
        </Section>

        <Section title="Intelligence Rail 2.0">
          <InfinityIntelligenceRail items={RAIL_ITEMS} />
        </Section>

        <Section title="Confidence Telemetry 2.0">
          <div className="max-w-md">
            <InfinityConfidenceTelemetry probability={0.64} confidence={0.78} modelAgreement={[0.72, 0.81, 0.76]} trend="rising" calibration={0.91} />
          </div>
        </Section>

        <Section title="Chart language">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <ChartTile label="Confidence Ring">
              <InfinityConfidenceRing value={0.82} size={72} />
            </ChartTile>
            <ChartTile label="Radar">
              <InfinityRadarChart axes={['PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY']} values={[0.8, 0.65, 0.7, 0.9, 0.4, 0.6]} size={140} />
            </ChartTile>
            <ChartTile label="Heatmap">
              <InfinityHeatmap rows={4} cols={6} values={Array.from({ length: 24 }, () => Math.random())} />
            </ChartTile>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <InfinityLabel>Momentum curve</InfinityLabel>
              <InfinityMomentumCurve points={[0.1, 0.3, 0.5, 0.2, -0.1, -0.4, -0.2, 0.1, 0.4, 0.6]} />
            </div>
            <div>
              <InfinityLabel>Prediction evolution</InfinityLabel>
              <InfinityPredictionEvolution
                points={[
                  { value: 0.5, label: 'Open' },
                  { value: 0.55, label: 'Lineup confirmed' },
                  { value: 0.48, label: 'Injury news' },
                  { value: 0.62, label: 'Model retrain' },
                  { value: 0.7, label: 'Now' },
                ]}
              />
            </div>
          </div>
        </Section>

        <Section title="Cards">
          <div className="grid gap-4 sm:grid-cols-3">
            <InfinityMatchCard sport="football" competition="Premier League" status="live" minute="67'" homeTeam="Arsenal" awayTeam="Chelsea" homeScore={2} awayScore={1} />
            <InfinityPredictionCard market="Match Result" selection="Arsenal to win" probability={0.64} confidence={0.78} evidenceCount={12} />
            <InfinityPlayerCard name="Bukayo Saka" team="Arsenal" position="RW" domain="football" statLabel="Expected goals" statValue="0.42" available />
            <InfinityTeamCard name="Arsenal" competition="Premier League" domain="football" position={2} form={['W', 'W', 'D', 'W', 'L']} />
            <InfinityNewsCard headline="Star striker ruled out for six weeks with hamstring injury" source="Sky Sports" publishedAgo="4m ago" sentiment="negative" confidenceImpact={-0.06} />
            <InfinityMetricCard icon={LayoutDashboard} label="Predictions tracked" value={1284} delta={{ value: '12.4%', direction: 'up' }} />
            <InfinityProviderCard name="API-Football" category="Sports data" status="healthy" maskedKey="••••••••A4X9" latencyMs={142} requestsToday={3820} dailyLimit={7500} />
            <InfinityOperationsCard system="Knowledge Graph sync" health="healthy" uptimePct={99.94} detail="Last sync 2 minutes ago · 18,204 nodes" />
          </div>
        </Section>

        <Section title="Navigation">
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="max-w-xs space-y-1 border border-infinity-border-hairline bg-infinity-ground-1 p-2">
              <InfinityNavItem icon={LayoutDashboard} label="Dashboard" active />
              <InfinityNavItem icon={Trophy} label="Football" badge="12" />
              <InfinityNavItem icon={Newspaper} label="News Intelligence" />
              <InfinityNavItem icon={ShieldCheck} label="Operations Center" />
            </div>
            <div className="space-y-4">
              <InfinityBreadcrumbs items={['Football', 'Premier League', 'Arsenal vs Chelsea']} />
              <InfinitySportSwitcher
                sports={[
                  { key: 'football', label: 'Football' },
                  { key: 'basketball', label: 'Basketball' },
                  { key: 'baseball', label: 'Baseball' },
                  { key: 'table-tennis', label: 'Table Tennis' },
                ]}
                active={sport}
                onChange={setSport}
              />
            </div>
          </div>
          <div className="mt-4">
            <InfinityCommandPaletteShell
              groups={[
                {
                  label: 'Navigate',
                  items: [
                    { icon: LayoutDashboard, label: 'Go to Dashboard', shortcut: '⌘1' },
                    { icon: ShieldCheck, label: 'Go to Operations Center' },
                  ],
                },
                {
                  label: 'Search',
                  items: [
                    { icon: Search, label: 'Search matches, teams, players' },
                    { icon: Bell, label: 'View notifications' },
                    { icon: User, label: 'Open profile' },
                  ],
                },
              ]}
            />
          </div>
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <InfinityPanel tone="var(--infinity-border-default)">
      <InfinityLabel className="mb-3 block">{title}</InfinityLabel>
      {children}
    </InfinityPanel>
  )
}

function ChartTile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2">
      {children}
      <InfinityLabel>{label}</InfinityLabel>
    </div>
  )
}
