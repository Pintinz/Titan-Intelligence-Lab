import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { LoginPage } from '@/pages/login-page'
import { SignupPage } from '@/pages/signup-page'
import { ForgotPasswordPage } from '@/pages/forgot-password-page'
import { ResetPasswordPage } from '@/pages/reset-password-page'
import { AuthCallbackPage } from '@/pages/auth-callback-page'
import { DashboardPage } from '@/pages/dashboard-page'
import { ProtectedRoute } from '@/routes/protected-route'
import { RoleRoute } from '@/routes/role-route'
import { AppShell } from '@/components/layout/app-shell'
import { MarketingShell } from '@/components/layout/marketing-shell'
import { PageLoader } from '@/components/layout/page-loader'

function lazyPage(loader: () => Promise<{ default: React.ComponentType }>) {
  const LazyComponent = lazy(loader)
  return (
    <Suspense fallback={<PageLoader />}>
      <LazyComponent />
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    element: <MarketingShell />,
    children: [
      { path: '/', element: lazyPage(() => import('@/pages/landing-page')) },
      { path: '/pricing', element: lazyPage(() => import('@/pages/marketing/pricing-page')) },
      { path: '/methodology', element: lazyPage(() => import('@/pages/marketing/methodology-page')) },
      { path: '/docs', element: lazyPage(() => import('@/pages/marketing/docs-page')) },
      { path: '/api-reference', element: lazyPage(() => import('@/pages/marketing/api-reference-page')) },
      { path: '/about', element: lazyPage(() => import('@/pages/marketing/about-page')) },
      { path: '/contact', element: lazyPage(() => import('@/pages/marketing/contact-page')) },
    ],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
  { path: '/auth/callback', element: <AuthCallbackPage /> },
  {
    path: '/app',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <DashboardPage /> },

      { path: 'predictions', element: lazyPage(() => import('@/pages/predictions/prediction-center-page')) },
      { path: 'predictions/:predictionId', element: lazyPage(() => import('@/pages/predictions/prediction-detail-page')) },

      { path: 'matches', element: lazyPage(() => import('@/pages/sports/match-center-page')) },
      { path: 'matches/:matchId', element: lazyPage(() => import('@/pages/sports/match-detail-page')) },
      { path: 'competitions', element: lazyPage(() => import('@/pages/sports/competition-center-page')) },
      { path: 'competitions/:competitionId', element: lazyPage(() => import('@/pages/sports/competition-detail-page')) },
      { path: 'teams', element: lazyPage(() => import('@/pages/sports/team-center-page')) },
      { path: 'teams/:teamId', element: lazyPage(() => import('@/pages/sports/team-detail-page')) },
      { path: 'players', element: lazyPage(() => import('@/pages/sports/player-center-page')) },
      { path: 'players/:playerId', element: lazyPage(() => import('@/pages/sports/player-detail-page')) },

      { path: 'news', element: lazyPage(() => import('@/pages/intelligence/news-center-page')) },
      { path: 'news/:articleId', element: lazyPage(() => import('@/pages/intelligence/news-detail-page')) },
      { path: 'community', element: lazyPage(() => import('@/pages/intelligence/community-center-page')) },
      { path: 'graph', element: lazyPage(() => import('@/pages/graph/graph-explorer-page')) },
      { path: 'analytics', element: lazyPage(() => import('@/pages/analytics/analytics-center-page')) },

      {
        path: 'models',
        element: (
          <RoleRoute minRole="administrator">{lazyPage(() => import('@/pages/ml/model-center-page'))}</RoleRoute>
        ),
      },
      {
        path: 'experiments',
        element: (
          <RoleRoute minRole="administrator">{lazyPage(() => import('@/pages/ml/experiment-center-page'))}</RoleRoute>
        ),
      },
      {
        path: 'features',
        element: (
          <RoleRoute minRole="administrator">{lazyPage(() => import('@/pages/ml/feature-center-page'))}</RoleRoute>
        ),
      },
      {
        path: 'admin/*',
        element: (
          <RoleRoute minRole="administrator">{lazyPage(() => import('@/pages/admin/admin-center-page'))}</RoleRoute>
        ),
      },

      { path: 'settings', element: lazyPage(() => import('@/pages/settings/user-settings-page')) },
      { path: 'settings/organization', element: lazyPage(() => import('@/pages/settings/organization-settings-page')) },
      { path: 'billing', element: lazyPage(() => import('@/pages/settings/billing-page')) },
      { path: 'notifications', element: lazyPage(() => import('@/pages/notifications/notifications-page')) },
      { path: 'help', element: lazyPage(() => import('@/pages/help/help-center-page')) },
    ],
  },
])
