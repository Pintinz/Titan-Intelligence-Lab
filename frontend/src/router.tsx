import { createBrowserRouter } from 'react-router-dom'
import LoginPage from '@/pages/login-page'
import { RebuildingPage } from '@/pages/rebuilding-page'
import { ProtectedRoute } from '@/routes/protected-route'
import { RoleRoute } from '@/routes/role-route'
import { AppShell } from '@/components/layout/app-shell'
import { MarketingShell } from '@/components/layout/marketing-shell'

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
  {
    element: <MarketingShell />,
    children: [
      { path: '/', element: <RebuildingPage title="Landing" phase="Phase 1" /> },
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

      { path: 'football', element: <RebuildingPage title="Football Intelligence" phase="Phase 2" /> },
      { path: 'basketball', element: <RebuildingPage title="Basketball Intelligence" phase="Phase 3" /> },
      { path: 'baseball', element: <RebuildingPage title="Baseball Intelligence" phase="Phase 3" /> },
      { path: 'table-tennis', element: <RebuildingPage title="Table Tennis Intelligence" phase="Phase 3" /> },

      { path: 'news', element: <RebuildingPage title="News Intelligence" phase="Phase 4" /> },
      { path: 'learning', element: <RebuildingPage title="Learning Intelligence" phase="Phase 4" /> },
      { path: 'insights', element: <RebuildingPage title="TitanIQ Insights" phase="Phase 5" /> },
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
