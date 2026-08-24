import type { LucideIcon } from 'lucide-react'
import {
  LayoutGrid,
  CalendarDays,
  Trophy,
  Users,
  UserRound,
  Newspaper,
  Share2,
  ServerCog,
  FlaskConical,
  Settings,
  CreditCard,
  HelpCircle,
  UserCircle,
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
 * TitanIQ IA — information-architecture restructure (shaped brief): eight real, distinct
 * primary destinations (Intelligence Center / Matches / Teams / Players / Competitions /
 * Context / Knowledge Graph / Account), not a task-first grab-bag. Sport is a filter within
 * each destination, not a nav destination itself — the four Sport Intelligence Center routes
 * (/app/:sport/*) still exist and are still how Match/Team/Competition/Player detail pages are
 * reached, just not listed here directly.
 *
 * Live, AI Picks, Watchlist, and Intelligence Workspace are deliberately absent from this list —
 * per the confirmed shaped brief ("reorganize, remove nothing"), all three stay real, fully
 * functional pages, demoted to the same contextual-reachability tier Knowledge Graph and News
 * already occupied before this restructure: linked from Intelligence Center's own sections
 * (Live Intelligence, Today's Top AI Intelligence, Following, the Workspace teaser all already
 * link to their real pages) rather than a permanent sidebar row. Alerts is reachable from the
 * topbar's own persistent bell icon on every page, same as before. Learning Intelligence stays
 * an administrator capability inside Operations Center (/app/ops/ml); end users consume its
 * outputs through predictions/confidence/explainability, not a dedicated page.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Explore',
    items: [
      { label: 'Intelligence Center', href: '/app', icon: LayoutGrid },
      { label: 'Matches', href: '/app/football/matches', icon: CalendarDays },
      { label: 'Teams', href: '/app/teams', icon: Users },
      { label: 'Players', href: '/app/players', icon: UserRound },
      { label: 'Competitions', href: '/app/competitions', icon: Trophy },
      { label: 'Context', href: '/app/context', icon: Newspaper },
      { label: 'Knowledge Graph', href: '/app/graph', icon: Share2 },
    ],
  },
  {
    label: 'Platform',
    items: [
      { label: 'Operations Center', href: '/app/ops', icon: ServerCog, minRole: 'administrator' },
      { label: 'Prediction Laboratory', href: '/app/football/lab', icon: FlaskConical, minRole: 'administrator' },
    ],
  },
  {
    label: 'Account',
    items: [
      { label: 'Settings', href: '/app/settings', icon: Settings },
      { label: 'Upgrade', href: '/app/billing', icon: CreditCard },
      { label: 'Help', href: '/app/help', icon: HelpCircle },
      { label: 'Profile', href: '/app/profile', icon: UserCircle },
    ],
  },
]

/** Flat lookup used by RoleRoute-adjacent checks and breadcrumb generation. */
export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

export const BRAND = {
  name: 'TitanIQ',
  tagline: 'See Every Match Through Intelligence.',
  description:
    'TitanIQ transforms sports data, news, community signals, and machine learning into explainable sports intelligence.',
}
