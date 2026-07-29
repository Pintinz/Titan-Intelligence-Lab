import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast, type Role } from '@/lib/api/types'

export function RoleRoute({ minRole, children }: { minRole: Role; children: ReactNode }) {
  const profile = useAuthStore((s) => s.profile)

  if (!profile) {
    return (
      <div className="flex h-full min-h-[50vh] items-center justify-center text-sm text-text-muted">Loading…</div>
    )
  }

  if (!isAtLeast(profile.role, minRole)) {
    return <Navigate to="/app" replace />
  }

  return <>{children}</>
}
