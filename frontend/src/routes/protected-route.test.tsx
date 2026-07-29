import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from '@/routes/protected-route'
import { useAuthStore } from '@/stores/auth-store'

function renderAtApp() {
  return render(
    <MemoryRouter initialEntries={['/app']}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <div>Protected dashboard</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('shows a loading state while auth status is unresolved', () => {
    useAuthStore.setState({ status: 'loading' })
    renderAtApp()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('redirects to /login when unauthenticated', () => {
    useAuthStore.setState({ status: 'unauthenticated' })
    renderAtApp()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('renders the protected content when authenticated', () => {
    useAuthStore.setState({ status: 'authenticated' })
    renderAtApp()
    expect(screen.getByText('Protected dashboard')).toBeInTheDocument()
  })
})
