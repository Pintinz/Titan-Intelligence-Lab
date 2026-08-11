import type { LucideIcon } from 'lucide-react'
import {
  LayoutGrid,
  Radio,
  Trophy,
  Users,
  Target,
  Star,
  Bell,
  BrainCircuit,
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
 * TitanIQ IA — task-first primary sidebar (Home/Live/Competitions/Teams/AI Picks/Watchlist/
 * Alerts/Assistant), not sport-first. Sport is a filter within Live/Competitions/Teams/AI Picks,
 * not a nav destination — the four Sport Intelligence Center routes (/app/:sport/*) still exist
 * and are still how Match/Team/Competition/Player detail pages are reached, just not listed here
 * directly anymore.
 *
 * News Intelligence, Knowledge Graph, Learning Intelligence, and Analytics are deliberately
 * absent — per product direction, these are platform capabilities surfaced contextually inside
 * Match/Team/Competition/AI Picks/Assistant pages, not standalone nav destinations. Learning
 * Intelligence specifically stays an administrator capability inside Operations Center (its
 * existing /app/ops/ml page); end users consume its outputs through predictions, confidence,
 * and explainability, not a dedicated page. Their routes are not deleted, only unlinked from
 * primary nav — still reachable directly and via the command palette.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Explore',
    items: [
      { label: 'Home', href: '/app', icon: LayoutGrid },
      { label: 'Live', href: '/app/live', icon: Radio },
      { label: 'Competitions', href: '/app/competitions', icon: Trophy },
      { label: 'Teams', href: '/app/teams', icon: Users },
      { label: 'AI Picks', href: '/app/picks', icon: Target },
      { label: 'Watchlist', href: '/app/watchlist', icon: Star },
      { label: 'Alerts', href: '/app/notifications', icon: Bell },
      { label: 'Intelligence Workspace', href: '/app/insights', icon: BrainCircuit },
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
