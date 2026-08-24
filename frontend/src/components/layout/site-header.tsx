import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import * as NavigationMenu from '@radix-ui/react-navigation-menu'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { ChevronDown, Menu, X, LogOut, LayoutGrid, Settings } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth-store'
import logoUrl from '@/assets/logo.png'
import { BRAND } from './nav-config'
import { HEADER_MENUS } from './marketing-nav-config'

const SIMPLE_LINKS = [
  { label: 'Pricing', href: '/pricing' },
  { label: 'Support', href: '/support' },
]

export function SiteHeader() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const profile = useAuthStore((s) => s.profile)
  const signOut = useAuthStore((s) => s.signOut)

  return (
    <header className="sticky top-0 z-40 border-b border-border-subtle/60 bg-bg-primary/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-1 px-6 lg:px-10">
        <Link to="/" className="flex items-center pr-4">
          <img src={logoUrl} alt={BRAND.name} className="h-8 w-auto" width={116} height={32} />
        </Link>

        <NavigationMenu.Root className="relative hidden flex-1 md:block" delayDuration={100}>
          <NavigationMenu.List className="flex items-center gap-1">
            {HEADER_MENUS.map((menu) => (
              <NavigationMenu.Item key={menu.label}>
                <NavigationMenu.Trigger
                  className={cn(
                    'group flex items-center gap-1 rounded-md px-3 py-2 text-sm text-text-secondary transition-colors',
                    'hover:text-text-primary data-[state=open]:text-text-primary',
                  )}
                >
                  {menu.label}
                  <ChevronDown
                    className="size-3.5 transition-transform duration-200 group-data-[state=open]:rotate-180"
                    aria-hidden="true"
                  />
                </NavigationMenu.Trigger>
                <NavigationMenu.Content
                  className={cn(
                    'absolute left-0 top-0 w-[520px] rounded-lg border border-border-default bg-bg-elevated p-3 shadow-elevation-3',
                    'data-[motion=from-start]:animate-[popover-content-in_var(--motion-duration-fast)_var(--motion-easing-decelerate)]',
                    'data-[motion=from-end]:animate-[popover-content-in_var(--motion-duration-fast)_var(--motion-easing-decelerate)]',
                  )}
                >
                  <ul className="grid grid-cols-2 gap-1">
                    {menu.links.map((link) => (
                      <li key={link.href}>
                        <NavigationMenu.Link asChild>
                          <Link
                            to={link.href}
                            className="block rounded-md px-3 py-2 transition-colors hover:bg-bg-secondary"
                          >
                            <span className="block text-sm font-medium text-text-primary">{link.label}</span>
                            {link.description && (
                              <span className="mt-0.5 block text-xs text-text-muted">{link.description}</span>
                            )}
                          </Link>
                        </NavigationMenu.Link>
                      </li>
                    ))}
                  </ul>
                </NavigationMenu.Content>
              </NavigationMenu.Item>
            ))}

            {SIMPLE_LINKS.map((link) => (
              <NavigationMenu.Item key={link.href}>
                <NavigationMenu.Link asChild>
                  <NavLink
                    to={link.href}
                    className={({ isActive }) =>
                      cn(
                        'block rounded-md px-3 py-2 text-sm transition-colors',
                        isActive ? 'text-text-primary' : 'text-text-secondary hover:text-text-primary',
                      )
                    }
                  >
                    {link.label}
                  </NavLink>
                </NavigationMenu.Link>
              </NavigationMenu.Item>
            ))}
          </NavigationMenu.List>

          <div className="absolute left-0 top-full flex justify-start perspective-[2000px]">
            <NavigationMenu.Viewport
              className={cn(
                'relative mt-2 h-[var(--radix-navigation-menu-viewport-height)] w-[var(--radix-navigation-menu-viewport-width)]',
                'origin-top-left overflow-hidden transition-[width,height] duration-200',
              )}
            />
          </div>
        </NavigationMenu.Root>

        <div className="ml-auto flex items-center gap-2">
          {profile ? (
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  className="flex items-center gap-2 rounded-full border border-border-default py-1 pl-1 pr-2.5 transition-colors hover:border-border-strong"
                  aria-label="Account menu"
                >
                  <span className="flex size-6 items-center justify-center rounded-full bg-accent-primary-muted font-mono text-xs font-medium text-accent-primary">
                    {(profile.email ?? '?').charAt(0).toUpperCase()}
                  </span>
                  <span className="max-w-[120px] truncate text-xs text-text-secondary">{profile.email}</span>
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={8}
                  className="z-50 w-56 rounded-lg border border-border-default bg-bg-elevated p-1.5 shadow-elevation-3 data-[state=open]:animate-[popover-content-in_var(--motion-duration-fast)_var(--motion-easing-decelerate)]"
                >
                  <DropdownMenu.Item asChild>
                    <Link
                      to="/app"
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-text-secondary outline-none transition-colors hover:bg-bg-secondary hover:text-text-primary"
                    >
                      <LayoutGrid className="size-4" aria-hidden="true" />
                      Dashboard
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item asChild>
                    <Link
                      to="/app/settings"
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-text-secondary outline-none transition-colors hover:bg-bg-secondary hover:text-text-primary"
                    >
                      <Settings className="size-4" aria-hidden="true" />
                      Settings
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Separator className="my-1 h-px bg-border-subtle" />
                  <DropdownMenu.Item
                    onSelect={() => void signOut()}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-danger outline-none transition-colors hover:bg-danger-muted"
                  >
                    <LogOut className="size-4" aria-hidden="true" />
                    Sign out
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          ) : (
            <div className="hidden items-center gap-2 sm:flex">
              <Button asChild variant="ghost" size="sm">
                <Link to="/login">Log in</Link>
              </Button>
              <Button asChild size="sm">
                <Link to="/signup">Sign up free</Link>
              </Button>
            </div>
          )}

          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation menu"
          >
            <Menu className="size-4" />
          </Button>
        </div>
      </div>

      <MobileMarketingNav open={mobileOpen} onOpenChange={setMobileOpen} />
    </header>
  )
}

function MobileMarketingNav({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const profile = useAuthStore((s) => s.profile)
  const signOut = useAuthStore((s) => s.signOut)

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-40 bg-bg-overlay md:hidden',
            'data-[state=open]:animate-[overlay-fade-in_var(--motion-duration-fast)_var(--motion-easing-standard)]',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed inset-y-0 right-0 z-50 flex w-80 max-w-[85vw] flex-col bg-bg-secondary md:hidden',
            'data-[state=open]:animate-[dialog-content-in_var(--motion-duration-base)_var(--motion-easing-decelerate)]',
          )}
        >
          <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
          <div className="flex h-16 items-center justify-between border-b border-border-subtle px-5">
            <img src={logoUrl} alt={BRAND.name} className="h-7 w-auto" width={101} height={28} />
            <DialogPrimitive.Close aria-label="Close navigation menu" className="text-text-secondary">
              <X className="size-4" />
            </DialogPrimitive.Close>
          </div>
          <nav className="flex-1 overflow-y-auto px-4 py-4" aria-label="Primary">
            {HEADER_MENUS.map((menu) => (
              <div key={menu.label} className="mb-5">
                <h2 className="px-1 pb-2 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                  {menu.label}
                </h2>
                <ul className="flex flex-col gap-0.5">
                  {menu.links.map((link) => (
                    <li key={link.href}>
                      <Link
                        to={link.href}
                        onClick={() => onOpenChange(false)}
                        className="block rounded-md px-2 py-1.5 text-sm text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <div className="mb-5">
              <h2 className="px-1 pb-2 text-[11px] font-medium uppercase tracking-wider text-text-muted">More</h2>
              <ul className="flex flex-col gap-0.5">
                {SIMPLE_LINKS.map((link) => (
                  <li key={link.href}>
                    <Link
                      to={link.href}
                      onClick={() => onOpenChange(false)}
                      className="block rounded-md px-2 py-1.5 text-sm text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
          <div className="border-t border-border-subtle p-4">
            {profile ? (
              <div className="space-y-2">
                <Button asChild variant="secondary" className="w-full">
                  <Link to="/app" onClick={() => onOpenChange(false)}>
                    Dashboard
                  </Link>
                </Button>
                <Button variant="ghost" className="w-full text-danger" onClick={() => void signOut()}>
                  Sign out
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <Button asChild variant="secondary" className="w-full">
                  <Link to="/login" onClick={() => onOpenChange(false)}>
                    Log in
                  </Link>
                </Button>
                <Button asChild className="w-full">
                  <Link to="/signup" onClick={() => onOpenChange(false)}>
                    Sign up free
                  </Link>
                </Button>
              </div>
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
