import { createBrowserRouter } from 'react-router-dom'
import LoginPage from '@/pages/login-page'
import LandingPage from '@/pages/landing-page'
import { RebuildingPage } from '@/pages/rebuilding-page'
import { ProtectedRoute } from '@/routes/protected-route'
import { RoleRoute } from '@/routes/role-route'
import { AppShell } from '@/components/layout/app-shell'
import { MarketingShell } from '@/components/layout/marketing-shell'
import { SportShell } from '@/components/layout/sport-shell'
import SportHubPage from '@/pages/sports/sport-hub-page'
import MatchListPage from '@/pages/sports/match-list-page'
import MatchDetailPage from '@/pages/sports/match-detail-page'
import TeamListPage from '@/pages/sports/team-list-page'
import TeamDetailPage from '@/pages/sports/team-detail-page'
import PlayerListPage from '@/pages/sports/player-list-page'
import PlayerDetailPage from '@/pages/sports/player-detail-page'
import CompetitionListPage from '@/pages/sports/competition-list-page'
import CompetitionDetailPage from '@/pages/sports/competition-detail-page'
import PredictionLabPage from '@/pages/sports/prediction-lab-page'
import SportNewsPage from '@/pages/sports/sport-news-page'
import SportCommunityPage from '@/pages/sports/sport-community-page'
import NewsIntelligencePage from '@/pages/intelligence/news-intelligence-page'
import LearningIntelligencePage from '@/pages/intelligence/learning-intelligence-page'
import InsightsPage from '@/pages/insights/insights-page'

// -- Milestone 10.2 reconstruction: every route below renders RebuildingPage until its phase
// lands (see the phased plan). Route paths reflect the NEW information architecture — four Sport
// Intelligence Centers replacing the old generic Match/Team/Player/Competition/Prediction
// Centers — not the old Milestone 10 route tree.

// TEMPORARY, dev-build-only: visual QA for AppShell/Sidebar/Topbar without a real auth session
// (unauthenticated access to /app is otherwise correctly impossible). Remove once a phase adds a
// real authenticated page to check the shell against instead.
const devShellPreviewRoute = import.meta.env.DEV
  ? [
      {
        path: '/__shell-preview',
        element: (
          <AppShell />
        ),
        children: [{ index: true, element: <RebuildingPage title="Shell preview" phase="n/a — dev only" /> }],
      },
    ]
  : []

export const router = createBrowserRouter([
  ...devShellPreviewRoute,
  // Landing owns its own nav/footer (a full-bleed hero wants more control than the boxed
  // MarketingShell header gives it) — the simpler utility marketing pages below still share it.
  { path: '/', element: <LandingPage /> },
  {
    element: <MarketingShell />,
    children: [
      { path: '/pricing', element: <RebuildingPage title="Pricing" phase="Phase 7" /> },
      { path: '/methodology', element: <RebuildingPage title="Methodology" phase="Phase 7" /> },
      { path: '/docs', element: <RebuildingPage title="Docs" phase="Phase 7" /> },
      { path: '/api-reference', element: <RebuildingPage title="API Reference" phase="Phase 7" /> },
      { path: '/about', element: <RebuildingPage title="About" phase="Phase 7" /> },
      { path: '/contact', element: <RebuildingPage title="Contact" phase="Phase 7" /> },
    ],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <RebuildingPage title="Sign up" phase="Phase 7" /> },
  { path: '/forgot-password', element: <RebuildingPage title="Forgot password" phase="Phase 7" /> },
  { path: '/reset-password', element: <RebuildingPage title="Reset password" phase="Phase 7" /> },
  { path: '/auth/callback', element: <RebuildingPage title="Signing in…" phase="Phase 7" /> },
  {
    path: '/app',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <RebuildingPage title="Dashboard" phase="a later phase" /> },

      {
        // One generic shell serves every Sport Intelligence Center — "only market types differ
        // by sport" (brief). Football is verified in Phase 2; Basketball/Baseball/Table Tennis
        // reuse this exact tree in Phase 3, nothing sport-specific hardcoded here.
        path: ':sport',
        element: <SportShell />,
        children: [
          { index: true, element: <SportHubPage /> },
          { path: 'matches', element: <MatchListPage /> },
          { path: 'matches/:matchId', element: <MatchDetailPage /> },
          { path: 'teams', element: <TeamListPage /> },
          { path: 'teams/:teamId', element: <TeamDetailPage /> },
          { path: 'players', element: <PlayerListPage /> },
          { path: 'players/:playerId', element: <PlayerDetailPage /> },
          { path: 'competitions', element: <CompetitionListPage /> },
          { path: 'competitions/:competitionId', element: <CompetitionDetailPage /> },
          { path: 'lab', element: <PredictionLabPage /> },
          { path: 'news', element: <SportNewsPage /> },
          { path: 'community', element: <SportCommunityPage /> },
        ],
      },

      { path: 'news', element: <NewsIntelligencePage /> },
      { path: 'learning', element: <LearningIntelligencePage /> },
      { path: 'insights', element: <InsightsPage /> },
      { path: 'analytics', element: <RebuildingPage title="Analytics" phase="Phase 7" /> },
      { path: 'graph', element: <RebuildingPage title="Knowledge Graph" phase="Phase 7" /> },

      {
        path: 'ops/*',
        element: (
          <RoleRoute minRole="administrator">
            <RebuildingPage title="Operations Center" phase="Phase 6" />
          </RoleRoute>
        ),
      },

      { path: 'settings', element: <RebuildingPage title="Settings" phase="Phase 7" /> },
      { path: 'settings/organization', element: <RebuildingPage title="Organization Settings" phase="Phase 7" /> },
      { path: 'billing', element: <RebuildingPage title="Billing" phase="Phase 7" /> },
      { path: 'notifications', element: <RebuildingPage title="Notifications" phase="Phase 7" /> },
      { path: 'help', element: <RebuildingPage title="Help Center" phase="Phase 7" /> },
    ],
  },
])
