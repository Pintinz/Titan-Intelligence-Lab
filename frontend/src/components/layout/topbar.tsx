import { Menu, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/theme-toggle'
import { useAuthStore } from '@/stores/auth-store'

export function Topbar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const profile = useAuthStore((s) => s.profile)
  const signOut = useAuthStore((s) => s.signOut)

  const initial = (profile?.email ?? '?').charAt(0).toUpperCase()

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border-subtle bg-bg-primary px-4 lg:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onOpenMobileNav}
        aria-label="Open navigation menu"
      >
        <Menu className="size-4" />
      </Button>

      <div className="flex-1" />

      <ThemeToggle />

      {profile && (
        <div className="flex items-center gap-2 border-l border-border-subtle pl-3">
          <span
            className="flex size-7 items-center justify-center rounded-full bg-accent-primary-muted font-mono text-xs font-medium text-accent-primary"
            aria-hidden="true"
          >
            {initial}
          </span>
          <Button variant="ghost" size="icon" onClick={() => void signOut()} aria-label="Sign out">
            <LogOut className="size-4" />
          </Button>
        </div>
      )}
    </header>
  )
}
