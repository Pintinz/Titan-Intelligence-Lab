import { create } from 'zustand'
import type { ComponentType } from 'react'

export interface WorkspaceCommand {
  id: string
  label: string
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>
  run: () => void
}

interface WorkspaceCommandState {
  commands: WorkspaceCommand[]
  setCommands: (commands: WorkspaceCommand[]) => void
  clearCommands: () => void
}

/** Lets the Intelligence Workspace publish its real, currently-available actions (Generate
 * Intelligence, Compare, focus the Knowledge Graph, Export, Save Session — whatever's genuinely
 * live given what's focused) into the one existing global Command Palette, instead of a second
 * ⌘K handler. The palette renders this group only while it's non-empty (i.e. only while the
 * Workspace is mounted with something focused) — no entity search is added here, matching the
 * palette's existing documented policy of never fabricating search results. */
export const useWorkspaceCommandStore = create<WorkspaceCommandState>()((set) => ({
  commands: [],
  setCommands: (commands) => set({ commands }),
  clearCommands: () => set({ commands: [] }),
}))
