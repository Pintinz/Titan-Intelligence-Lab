import type { LucideIcon } from 'lucide-react'
import {
  LayoutGrid,
  CircleDot,
  Newspaper,
  GraduationCap,
  Sparkles,
  BarChart3,
  Share2,
  ServerCog,
  Settings,
  Bell,
  HelpCircle,
} from 'lucide-react'
import type { Role } from '@/lib/api/types'

export interface NavItem {
  label: string
  href: string
  icon: LucideIcon
  minRole?: Role
  /** Shown as a small dot next to the label — reserved for genuinely live subsystems. */
  live?: boolean
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

/**
 * TitanIQ IA — four Sport Intelligence Centers (each its own Live/Match/Team/Player/Competition/
 * Prediction Laboratory/News/Community architecture, built out sport-by-sport starting Phase 2),
 * plus platform-wide intelligence surfaces that cut across sports. Table Tennis, not Tennis — the
 * backend's real Phase One roster (docs/titaniq.md §3).
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ label: 'Dashboard', href: '/app', icon: LayoutGrid }],
  },
  {
    label: 'Intelligence Centers',
    items: [
      { label: 'Football', href: '/app/football', icon: CircleDot },
      { label: 'Basketball', href: '/app/basketball', icon: CircleDot },
      { label: 'Baseball', href: '/app/baseball', icon: CircleDot },
      { label: 'Table Tennis', href: '/app/table-tennis', icon: CircleDot },
    ],
  },
  {
    label: 'Platform Intelligence',
    items: [
      { label: 'News Intelligence', href: '/app/news', icon: Newspaper },
      { label: 'Learning Intelligence', href: '/app/learning', icon: GraduationCap },
      { label: 'TitanIQ Insights', href: '/app/insights', icon: Sparkles },
      { label: 'Analytics', href: '/app/analytics', icon: BarChart3 },
      { label: 'Knowledge Graph', href: '/app/graph', icon: Share2 },
    ],
  },
  {
    label: 'Platform',
    items: [
      { label: 'Operations Center', href: '/app/ops', icon: ServerCog, minRole: 'administrator' },
    ],
  },
  {
    label: 'Account',
    items: [
      { label: 'Notifications', href: '/app/notifications', icon: Bell },
      { label: 'Settings', href: '/app/settings', icon: Settings },
      { label: 'Help', href: '/app/help', icon: HelpCircle },
    ],
  },
]

/** Flat lookup used by RoleRoute-adjacent checks and breadcrumb generation. */
export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

export const BRAND = {
  name: 'TitanIQ',
  tagline: 'See Every Match Through Intelligence.',
}
