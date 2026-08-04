import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { PageLoader } from '@/components/layout/page-loader'
import HomePage from '@/pages/home-page'
import LoginPage from '@/pages/login-page'
import LandingPage from '@/pages/landing-page'
import SignupPage from '@/pages/signup-page'
import ForgotPasswordPage from '@/pages/forgot-password-page'
import ResetPasswordPage from '@/pages/reset-password-page'
import { RebuildingPage } from '@/pages/rebuilding-page'
import { ProtectedRoute } from '@/routes/protected-route'
import { RoleRoute } from '@/routes/role-route'
import { AppShell } from '@/components/layout/app-shell'
import { InfinityAppShell } from '@/components/infinity/app-shell/infinity-app-shell'
import { MarketingShell } from '@/components/layout/marketing-shell'
import { SportShell } from '@/components/layout/sport-shell'
import { OpsShell } from '@/components/layout/ops-shell'
import ExecutiveDashboard from '@/pages/ops/executive-dashboard'
import ProviderManagement from '@/pages/ops/provider-management'
import FeatureFlags from '@/pages/ops/feature-flags'
import SettingsPage from '@/pages/settings-page'
import WatchlistPage from '@/pages/watchlist-page'
import AiPicksPage from '@/pages/ai-picks-page'
import AlertsPage from '@/pages/alerts-page'
import LivePage from '@/pages/live-page'
import CompetitionsPage from '@/pages/competitions-page'
import TeamsPage from '@/pages/teams-page'
import ProfilePage from '@/pages/profile-page'
import KnowledgeGraphPage from '@/pages/knowledge-graph-page'
import SportHubPage from '@/pages/sports/sport-hub-page'
import MatchListPage from '@/pages/sports/match-list-page'
import MatchListViewAllPage from '@/pages/sports/match-list-view-all-page'
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

import { RouteErrorBoundary } from '@/pages/errors/route-error-boundary'

// Milestone 10.3 — Trust, Legal, Compliance & Navigation ecosystem. Code-split: none of these
// are needed for the initial landing/app bundle, and there are 30+ of them — eagerly importing
// all would otherwise ship every legal document's markup to every first-time visitor.
function lazyPage(loader: () => Promise<{ default: ComponentType }>) {
  const LazyComponent = lazy(loader)
  return (
    <Suspense fallback={<PageLoader />}>
      <LazyComponent />
    </Suspense>
  )
}

const aboutPage = lazyPage(() => import('@/pages/about-page'))
const contactPage = lazyPage(() => import('@/pages/contact-page'))
const pricingPage = lazyPage(() => import('@/pages/pricing-page'))
const documentationPage = lazyPage(() => import('@/pages/documentation-page'))
const developerPortalPage = lazyPage(() => import('@/pages/developer-portal-page'))
const apiReferencePage = lazyPage(() => import('@/pages/api-reference-page'))
const methodologyPage = lazyPage(() => import('@/pages/methodology-page'))
const blogPage = lazyPage(() => import('@/pages/blog-page'))
const faqPage = lazyPage(() => import('@/pages/faq-page'))
const helpCenterPage = lazyPage(() => import('@/pages/help-center-page'))
const supportPage = lazyPage(() => import('@/pages/support-page'))
const releaseNotesPage = lazyPage(() => import('@/pages/release-notes-page'))
const roadmapPage = lazyPage(() => import('@/pages/roadmap-page'))
const trustCenterPage = lazyPage(() => import('@/pages/trust-center-page'))
const systemStatusPage = lazyPage(() => import('@/pages/system-status-page'))
const careersPage = lazyPage(() => import('@/pages/careers-page'))
const partnersPage = lazyPage(() => import('@/pages/partners-page'))
const pressKitPage = lazyPage(() => import('@/pages/press-kit-page'))
const brandAssetsPage = lazyPage(() => import('@/pages/brand-assets-page'))
const privacyPolicyPage = lazyPage(() => import('@/pages/legal/privacy-policy-page'))
const termsOfServicePage = lazyPage(() => import('@/pages/legal/terms-of-service-page'))
const cookiePolicyPage = lazyPage(() => import('@/pages/legal/cookie-policy-page'))
const advertisingPolicyPage = lazyPage(() => import('@/pages/legal/advertising-policy-page'))
const editorialPolicyPage = lazyPage(() => import('@/pages/legal/editorial-policy-page'))
const responsibleAiPage = lazyPage(() => import('@/pages/legal/responsible-ai-page'))
const securityPolicyPage = lazyPage(() => import('@/pages/legal/security-policy-page'))
const copyrightPolicyPage = lazyPage(() => import('@/pages/legal/copyright-policy-page'))
const dmcaPage = lazyPage(() => import('@/pages/legal/dmca-page'))
const acceptableUsePage = lazyPage(() => import('@/pages/legal/acceptable-use-page'))
const disclaimerPage = lazyPage(() => import('@/pages/legal/disclaimer-page'))
const licensesPage = lazyPage(() => import('@/pages/legal/licenses-page'))
const gdprPage = lazyPage(() => import('@/pages/legal/gdpr-page'))
const ccpaPage = lazyPage(() => import('@/pages/legal/ccpa-page'))
const notFoundPage = lazyPage(() => import('@/pages/errors/not-found-page'))
const serverErrorPage = lazyPage(() => import('@/pages/errors/server-error-page'))
const maintenancePage = lazyPage(() => import('@/pages/errors/maintenance-page'))

// Milestone 11A — Operations Center. Admin-only, so none of this belongs in the initial /app
// bundle every authenticated user downloads.
const dataPipelinePage = lazyPage(() => import('@/pages/ops/data-pipeline-page'))
const featureStorePage = lazyPage(() => import('@/pages/ops/feature-store-page'))
const predictionEnginePage = lazyPage(() => import('@/pages/ops/prediction-engine-page'))
const mlOperationsPage = lazyPage(() => import('@/pages/ops/ml-operations-page'))
const knowledgeGraphAdminPage = lazyPage(() => import('@/pages/ops/knowledge-graph-admin-page'))
const newsIntelligenceAdminPage = lazyPage(() => import('@/pages/ops/news-intelligence-admin-page'))
const communityIntelligenceAdminPage = lazyPage(() => import('@/pages/ops/community-intelligence-admin-page'))
const usersRolesPage = lazyPage(() => import('@/pages/ops/users-roles-page'))
const organizationsPage = lazyPage(() => import('@/pages/ops/organizations-page'))
const opsBillingPage = lazyPage(() => import('@/pages/ops/billing-page'))
const alertsMonitoringPage = lazyPage(() => import('@/pages/ops/alerts-monitoring-page'))
const securityCompliancePage = lazyPage(() => import('@/pages/ops/security-compliance-page'))
const auditCenterPage = lazyPage(() => import('@/pages/ops/audit-center-page'))
const logsDebuggingPage = lazyPage(() => import('@/pages/ops/logs-debugging-page'))

// Phase 11.0 — dev-only verification fixture, see devInfinityShowcaseRoute below.
const infinityShowcasePage = lazyPage(() => import('@/pages/infinity-showcase-page'))

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

// TEMPORARY, dev-build-only: Phase 11.0 (Infinity Design System foundation) verification
// fixture — renders every new primitive/card/chart/nav component for review. Unlinked from
// app navigation; no existing page imports anything from components/infinity/ yet.
const devInfinityShowcaseRoute = import.meta.env.DEV
  ? [{ path: '/__infinity-showcase', element: infinityShowcasePage }]
  : []

// TEMPORARY, dev-build-only: Phase 11.1 verification fixture for InfinityAppShell — same
// unauthenticated-preview pattern as devShellPreviewRoute above, built alongside it rather
// than replacing it, so the new shell can be inspected before the real /app route migrates.
const devInfinityShellPreviewRoute = import.meta.env.DEV
  ? [
      {
        path: '/__infinity-shell-preview',
        element: <InfinityAppShell />,
        children: [{ index: true, element: <RebuildingPage title="Infinity shell preview" phase="n/a — dev only" /> }],
      },
    ]
  : []

export const router = createBrowserRouter([
  ...devShellPreviewRoute,
  ...devInfinityShowcaseRoute,
  ...devInfinityShellPreviewRoute,
  // Landing owns its own nav/footer (a full-bleed hero wants more control than the boxed
  // MarketingShell header gives it) — the simpler utility marketing pages below still share it.
  { path: '/', element: <LandingPage />, errorElement: <RouteErrorBoundary /> },
  {
    element: <MarketingShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      // Company & product
      { path: '/about', element: aboutPage },
      { path: '/contact', element: contactPage },
      { path: '/pricing', element: pricingPage },
      { path: '/careers', element: careersPage },
      { path: '/partners', element: partnersPage },
      { path: '/press-kit', element: pressKitPage },
      { path: '/brand-assets', element: brandAssetsPage },
      { path: '/trust-center', element: trustCenterPage },

      // Resources & developers
      { path: '/docs', element: documentationPage },
      { path: '/developers', element: developerPortalPage },
      { path: '/api-reference', element: apiReferencePage },
      { path: '/methodology', element: methodologyPage },
      { path: '/blog', element: blogPage },
      { path: '/release-notes', element: releaseNotesPage },
      { path: '/roadmap', element: roadmapPage },
      { path: '/faq', element: faqPage },
      { path: '/help', element: helpCenterPage },
      { path: '/support', element: supportPage },
      { path: '/status', element: systemStatusPage },

      // Legal & compliance
      { path: '/privacy', element: privacyPolicyPage },
      { path: '/terms', element: termsOfServicePage },
      { path: '/cookies', element: cookiePolicyPage },
      { path: '/advertising-policy', element: advertisingPolicyPage },
      { path: '/editorial-policy', element: editorialPolicyPage },
      { path: '/responsible-ai', element: responsibleAiPage },
      { path: '/security-policy', element: securityPolicyPage },
      { path: '/copyright-policy', element: copyrightPolicyPage },
      { path: '/dmca', element: dmcaPage },
      { path: '/acceptable-use', element: acceptableUsePage },
      { path: '/disclaimer', element: disclaimerPage },
      { path: '/licenses', element: licensesPage },
      { path: '/gdpr', element: gdprPage },
      { path: '/ccpa', element: ccpaPage },
    ],
  },
  { path: '/login', element: <LoginPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/signup', element: <SignupPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/forgot-password', element: <ForgotPasswordPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/reset-password', element: <ResetPasswordPage />, errorElement: <RouteErrorBoundary /> },
  { path: '/auth/callback', element: <RebuildingPage title="Signing in…" phase="Phase 7" /> },
  { path: '/500', element: serverErrorPage },
  { path: '/maintenance', element: maintenancePage },
  {
    path: '/app',
    element: (
      // Phase 11.1 migration: InfinityAppShell replaces the legacy AppShell as the
      // wrapper for every /app/* route (Dashboard, Sport Intelligence Centers,
      // Operations Center, etc. — none of which change; they render inside whichever
      // shell wraps this route via <Outlet />). Legacy AppShell/Sidebar/Topbar/MobileNav
      // stay in the tree, unreferenced, per the coexistence strategy documented in
      // DESIGN_INFINITY.md — not deleted until a later phase's explicit cleanup.
      <ProtectedRoute>
        <InfinityAppShell />
      </ProtectedRoute>
    ),
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <HomePage /> },

      {
        // One generic shell serves every Sport Intelligence Center — "only market types differ
        // by sport" (brief). Football is verified in Phase 2; Basketball/Baseball/Table Tennis
        // reuse this exact tree in Phase 3, nothing sport-specific hardcoded here.
        path: ':sport',
        element: <SportShell />,
        children: [
          { index: true, element: <SportHubPage /> },
          { path: 'matches', element: <MatchListPage /> },
          { path: 'matches/today', element: <MatchListViewAllPage scope="today" /> },
          { path: 'matches/tomorrow', element: <MatchListViewAllPage scope="tomorrow" /> },
          { path: 'matches/week', element: <MatchListViewAllPage scope="week" /> },
          { path: 'matches/completed', element: <MatchListViewAllPage scope="completed" /> },
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

      { path: 'live', element: <LivePage /> },
      { path: 'competitions', element: <CompetitionsPage /> },
      { path: 'teams', element: <TeamsPage /> },
      { path: 'news', element: <NewsIntelligencePage /> },
      { path: 'learning', element: <LearningIntelligencePage /> },
      { path: 'insights', element: <InsightsPage /> },
      { path: 'analytics', element: <RebuildingPage title="Analytics" phase="Phase 7" /> },
      { path: 'graph', element: <KnowledgeGraphPage /> },
      { path: 'picks', element: <AiPicksPage /> },
      { path: 'watchlist', element: <WatchlistPage /> },
      { path: 'profile', element: <ProfilePage /> },

      {
        path: 'ops',
        element: (
          <RoleRoute minRole="administrator">
            <OpsShell />
          </RoleRoute>
        ),
        children: [
          { index: true, element: <ExecutiveDashboard /> },
          { path: 'providers', element: <ProviderManagement /> },
          { path: 'flags', element: <FeatureFlags /> },
          { path: 'pipeline', element: dataPipelinePage },
          { path: 'features', element: featureStorePage },
          { path: 'markets', element: predictionEnginePage },
          { path: 'ml', element: mlOperationsPage },
          { path: 'graph', element: knowledgeGraphAdminPage },
          { path: 'news', element: newsIntelligenceAdminPage },
          { path: 'community', element: communityIntelligenceAdminPage },
          { path: 'users', element: usersRolesPage },
          { path: 'organizations', element: organizationsPage },
          { path: 'billing', element: opsBillingPage },
          { path: 'alerts', element: alertsMonitoringPage },
          { path: 'security', element: securityCompliancePage },
          { path: 'audit', element: auditCenterPage },
          { path: 'logs', element: logsDebuggingPage },
        ],
      },

      { path: 'settings', element: <SettingsPage /> },
      { path: 'settings/organization', element: <RebuildingPage title="Organization Settings" phase="Phase 7" /> },
      { path: 'billing', element: <RebuildingPage title="Billing" phase="Phase 7" /> },
      { path: 'notifications', element: <AlertsPage /> },
      { path: 'help', element: helpCenterPage },
    ],
  },
  // Catch-all — must stay last; any path not matched above renders the 404 page rather than a
  // blank screen or router throw.
  { path: '*', element: notFoundPage },
])
