import {
  BarChart3,
  Cpu,
  FlaskConical,
  Gauge,
  Globe2,
  LayoutDashboard,
  MessageSquare,
  Newspaper,
  ShieldCheck,
  Sliders,
  Trophy,
  Users,
} from 'lucide-react'
import type { ComponentType } from 'react'
import type { Role } from '@/lib/api/types'

export interface NavItem {
  label: string
  to: string
  icon: ComponentType<{ className?: string }>
  minRole?: Role
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ label: 'Dashboard', to: '/app', icon: LayoutDashboard }],
  },
  {
    label: 'Intelligence',
    items: [
      { label: 'Prediction Center', to: '/app/predictions', icon: Gauge },
      { label: 'Match Center', to: '/app/matches', icon: Trophy },
      { label: 'Competition Center', to: '/app/competitions', icon: Trophy },
      { label: 'Team Center', to: '/app/teams', icon: Users },
      { label: 'Player Center', to: '/app/players', icon: Users },
    ],
  },
  {
    label: 'Insights',
    items: [
      { label: 'News Center', to: '/app/news', icon: Newspaper },
      { label: 'Community Center', to: '/app/community', icon: MessageSquare },
      { label: 'Knowledge Graph', to: '/app/graph', icon: Globe2 },
      { label: 'Analytics Center', to: '/app/analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'ML Platform',
    items: [
      { label: 'Model Center', to: '/app/models', icon: Cpu, minRole: 'administrator' },
      { label: 'Experiment Center', to: '/app/experiments', icon: FlaskConical, minRole: 'administrator' },
      { label: 'Feature Center', to: '/app/features', icon: Sliders, minRole: 'administrator' },
    ],
  },
  {
    label: 'Admin',
    items: [{ label: 'Admin Center', to: '/app/admin', icon: ShieldCheck, minRole: 'administrator' }],
  },
]
