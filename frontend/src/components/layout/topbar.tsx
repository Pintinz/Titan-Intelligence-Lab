import { LogOut, Search, Settings, User as UserIcon } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { NotificationCenter } from '@/components/domain/notification-center'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { useCommandPaletteStore } from '@/stores/command-palette-store'
import { MobileNav } from '@/components/layout/mobile-nav'

export function Topbar() {
  const profile = useAuthStore((s) => s.profile)
  const signOut = useAuthStore((s) => s.signOut)
  const setSearchOpen = useCommandPaletteStore((s) => s.setOpen)

  const initials = profile?.email ? profile.email.slice(0, 2).toUpperCase() : '··'

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border-subtle bg-bg-primary px-4">
      <div className="flex items-center gap-3">
        <MobileNav />
      </div>
      <button
        type="button"
        onClick={() => setSearchOpen(true)}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-border-default bg-bg-secondary px-3 py-1.5 text-sm text-text-muted transition-colors hover:border-border-strong sm:max-w-72"
      >
        <Search className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">Search TitanIQ…</span>
        <kbd className="ml-auto hidden shrink-0 rounded border border-border-default px-1.5 py-0.5 font-mono text-[10px] text-text-muted sm:inline">
          ⌘K
        </kbd>
      </button>

      <div className="flex items-center gap-2">
        <NotificationCenter />
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className="ml-1 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary">
              <Avatar className="h-8 w-8">
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{profile?.email ?? 'Account'}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link to="/app/settings" className="flex items-center gap-2">
                <UserIcon className="h-4 w-4" /> Profile settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/app/settings/organization" className="flex items-center gap-2">
                <Settings className="h-4 w-4" /> Organization settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void signOut()} className="flex items-center gap-2 text-danger">
              <LogOut className="h-4 w-4" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
