import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RoleRoute } from '@/routes/role-route'
import { useAuthStore } from '@/stores/auth-store'
import type { UserDto } from '@/lib/api/types'

const BASE_PROFILE: UserDto = {
  id: '1',
  email: 'user@example.com',
  role: 'free',
  status: 'active',
  email_verified: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: null,
}

function renderAtAdminRoute() {
  return render(
    <MemoryRouter initialEntries={['/app/admin']}>
      <Routes>
        <Route path="/app" element={<div>Dashboard</div>} />
        <Route
          path="/app/admin"
          element={
            <RoleRoute minRole="administrator">
              <div>Admin content</div>
            </RoleRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RoleRoute', () => {
  it('shows a loading state before the profile resolves', () => {
    useAuthStore.setState({ profile: null })
    renderAtAdminRoute()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('redirects away when the role is below the minimum', () => {
    useAuthStore.setState({ profile: { ...BASE_PROFILE, role: 'free' } })
    renderAtAdminRoute()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('renders the content when the role meets the minimum', () => {
    useAuthStore.setState({ profile: { ...BASE_PROFILE, role: 'administrator' } })
    renderAtAdminRoute()
    expect(screen.getByText('Admin content')).toBeInTheDocument()
  })
})
