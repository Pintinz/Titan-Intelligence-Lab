import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard,
  Plug,
  Flag,
  Workflow,
  Layers,
  Share2,
  Newspaper,
  MessageCircle,
  Target,
  Cpu,
  Users,
  Building2,
  CreditCard,
  ShieldAlert,
  ScrollText,
  BellRing,
  Terminal,
  Menu,
  Search,
  X,
} from 'lucide-react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cn } from '@/lib/cn'
import { CommandPalette } from '@/components/ops/command-palette'

/**
 * Operations Center — Milestone 11A. Every module below is a real, specific page (no generic
 * placeholder component remains) — `status` reflects the underlying data, not the page's
 * existence. `live` = backed entirely by real endpoints. `partial` = some sections are real,
 * others are honestly labeled "backend pending" inline (e.g. Users & Roles can change a role by
 * id but has no list-all-users endpoint yet; Billing has real plans/subscriptions but no
 * revenue/invoice/AdSense endpoints). `pending` = the page is fully built and explains exactly
 * what it will show, but zero backend endpoint exists for it yet (Security, Audit, Logs).
 */

export interface OpsModule {
  label: string
  to: string
  icon: LucideIcon
  status: 'live' | 'partial' | 'pending'
}

export interface OpsGroup {
  label: string
  modules: OpsModule[]
}

export const OPS_GROUPS: OpsGroup[] = [
  {
    label: 'Overview',
    modules: [
      { label: 'Executive Dashboard', to: '', icon: LayoutDashboard, status: 'live' },
      { label: 'Feature Flags', to: 'flags', icon: Flag, status: 'live' },
    ],
  },
  {
    label: 'Data & Intelligence',
    modules: [
      { label: 'Provider Management', to: 'providers', icon: Plug, status: 'live' },
      { label: 'Data Pipeline', to: 'pipeline', icon: Workflow, status: 'live' },
      { label: 'Feature Store', to: 'features', icon: Layers, status: 'live' },
      { label: 'Knowledge Graph', to: 'graph', icon: Share2, status: 'live' },
      { label: 'News Intelligence', to: 'news', icon: Newspaper, status: 'partial' },
      { label: 'Community Intelligence', to: 'community', icon: MessageCircle, status: 'partial' },
    ],
  },
  {
    label: 'Prediction & ML',
    modules: [
      { label: 'Prediction Engine', to: 'markets', icon: Target, status: 'live' },
      { label: 'ML Operations', to: 'ml', icon: Cpu, status: 'live' },
    ],
  },
  {
    label: 'Access & Billing',
    modules: [
      { label: 'Users & Roles', to: 'users', icon: Users, status: 'partial' },
      { label: 'Organizations', to: 'organizations', icon: Building2, status: 'live' },
      { label: 'Billing & Revenue', to: 'billing', icon: CreditCard, status: 'partial' },
    ],
  },
  {
    label: 'Trust & Operations',
    modules: [
      { label: 'Alerts & Monitoring', to: 'alerts', icon: BellRing, status: 'partial' },
      { label: 'Security & Compliance', to: 'security', icon: ShieldAlert, status: 'pending' },
      { label: 'Audit Center', to: 'audit', icon: ScrollText, status: 'pending' },
      { label: 'Logs & Debugging', to: 'logs', icon: Terminal, status: 'pending' },
    ],
  },
]

const STATUS_DOT: Record<OpsModule['status'], string> = {
  live: 'bg-success',
  partial: 'bg-warning',
  pending: 'bg-text-muted',
}

const STATUS_LABEL: Record<OpsModule['status'], string> = {
  live: 'Live',
  partial: 'Partially live',
  pending: 'Backend pending',
}

function OpsNavLink({ mod, onNavigate }: { mod: OpsModule; onNavigate?: () => void }) {
  return (
    <NavLink
      to={`/app/ops${mod.to ? `/${mod.to}` : ''}`}
      end={mod.to === ''}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors',
          isActive
            ? 'bg-accent-primary-muted text-accent-primary'
            : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary',
        )
      }
    >
      <mod.icon className="size-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{mod.label}</span>
      <span
        className={cn('size-1.5 shrink-0 rounded-full', STATUS_DOT[mod.status])}
        title={STATUS_LABEL[mod.status]}
        aria-label={STATUS_LABEL[mod.status]}
      />
    </NavLink>
  )
}

function OpsNavGroups({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      {OPS_GROUPS.map((group) => (
        <div key={group.label} className="mb-5">
          <h2 className="px-2.5 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-text-muted">
            {group.label}
          </h2>
          <ul className="flex flex-col gap-0.5">
            {group.modules.map((mod) => (
              <li key={mod.to}>
                <OpsNavLink mod={mod} onNavigate={onNavigate} />
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="mt-2 flex items-center gap-3 px-2.5 text-[10px] text-text-muted">
        <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-success" /> Live</span>
        <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-warning" /> Partial</span>
        <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-text-muted" /> Pending</span>
      </div>
    </>
  )
}

export function OpsShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="flex min-h-full">
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />

      <aside className="hidden w-60 shrink-0 flex-col overflow-y-auto border-r border-border-subtle bg-bg-secondary/40 px-3 py-5 lg:flex">
        <div className="mb-4 px-2.5">
          <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
            Administration
          </p>
          <h1 className="mt-0.5 font-display text-base font-semibold text-text-primary">Operations Center</h1>
        </div>
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="mb-4 flex items-center gap-2 rounded-md border border-border-default bg-bg-primary px-2.5 py-1.5 text-xs text-text-muted transition-colors hover:border-border-strong hover:text-text-secondary"
        >
          <Search className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="flex-1 text-left">Search or run a command…</span>
          <kbd className="rounded border border-border-subtle px-1 py-0.5 font-mono text-[10px]">Ctrl K</kbd>
        </button>
        <nav aria-label="Operations Center modules">
          <OpsNavGroups />
        </nav>
      </aside>

      <DialogPrimitive.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-bg-overlay lg:hidden" />
          <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col overflow-y-auto bg-bg-secondary px-3 py-5 lg:hidden">
            <DialogPrimitive.Title className="sr-only">Operations Center navigation</DialogPrimitive.Title>
            <div className="mb-4 flex items-center justify-between px-2.5">
              <div>
                <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
                  Administration
                </p>
                <h1 className="mt-0.5 font-display text-base font-semibold text-text-primary">Operations Center</h1>
              </div>
              <DialogPrimitive.Close aria-label="Close menu" className="text-text-secondary">
                <X className="size-4" />
              </DialogPrimitive.Close>
            </div>
            <nav aria-label="Operations Center modules">
              <OpsNavGroups onNavigate={() => setMobileOpen(false)} />
            </nav>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>

      <div className="min-w-0 flex-1">
        <div className="flex h-12 items-center gap-3 border-b border-border-subtle px-4 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="flex items-center gap-2 text-sm font-medium text-text-secondary"
            aria-label="Open Operations Center menu"
          >
            <Menu className="size-4" /> Modules
          </button>
        </div>
        <div className="p-4 lg:p-8">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
