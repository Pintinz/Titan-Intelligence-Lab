import { useCallback, useState } from 'react'

export type EntityKind = 'fixture' | 'team' | 'competition' | 'player'

export interface WorkspaceEntity {
  kind: EntityKind
  id: string
  label: string
  /** Secondary line — competition name for a team/fixture, country for a competition, etc. */
  meta?: string
  logoUrl?: string | null
}

const RECENT_KEY = 'titaniq.workspace.recent'
const SESSION_KEY = 'titaniq.workspace.session'
const RECENT_LIMIT = 12

function entityKey(e: WorkspaceEntity) {
  return `${e.kind}:${e.id}`
}

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // localStorage unavailable (private mode, quota) — Recently Opened/Save Session degrade to
    // no-ops rather than throwing; nothing else in the workspace depends on them.
  }
}

interface SavedSession {
  savedAt: string
  pinned: WorkspaceEntity[]
  focused: WorkspaceEntity | null
}

/**
 * Client-only workspace state for the Intelligence Workspace: pinned Investigation Context
 * (in-memory, matches the previous "Pinned" behavior — resets per visit), Recently Opened and
 * Save Session (both localStorage-backed, disclosed in the shaped brief as a client convenience
 * since no backend "recently viewed" or session endpoint exists), and the single `focused`
 * entity that drives the Investigation Header + Canvas. Pinning and focusing are the same click
 * (matches the original single-click "pin a search result" interaction) — a dedicated pin toggle
 * isn't exposed elsewhere in the IA.
 */
export function useInvestigationWorkspace() {
  const [pinned, setPinned] = useState<WorkspaceEntity[]>([])
  const [focused, setFocused] = useState<WorkspaceEntity | null>(null)
  const [focusedPredictionId, setFocusedPredictionId] = useState<string | null>(null)
  const [recentlyOpened, setRecentlyOpened] = useState<WorkspaceEntity[]>(() => readJson<WorkspaceEntity[]>(RECENT_KEY) ?? [])
  const [savedSession, setSavedSession] = useState<SavedSession | null>(() => readJson<SavedSession>(SESSION_KEY))

  const pushRecent = useCallback((entity: WorkspaceEntity) => {
    setRecentlyOpened((prev) => {
      const next = [entity, ...prev.filter((e) => entityKey(e) !== entityKey(entity))].slice(0, RECENT_LIMIT)
      writeJson(RECENT_KEY, next)
      return next
    })
  }, [])

  const pin = useCallback(
    (entity: WorkspaceEntity) => {
      setPinned((prev) => (prev.some((p) => entityKey(p) === entityKey(entity)) ? prev : [...prev, entity]))
      setFocused(entity)
      setFocusedPredictionId(null)
      pushRecent(entity)
    },
    [pushRecent],
  )

  const unpin = useCallback((entity: WorkspaceEntity) => {
    setPinned((prev) => prev.filter((p) => entityKey(p) !== entityKey(entity)))
    setFocused((prev) => (prev && entityKey(prev) === entityKey(entity) ? null : prev))
  }, [])

  const reorderPinned = useCallback((fromIndex: number, toIndex: number) => {
    setPinned((prev) => {
      if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= prev.length || toIndex >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(fromIndex, 1)
      next.splice(toIndex, 0, moved)
      return next
    })
  }, [])

  const focus = useCallback(
    (entity: WorkspaceEntity) => {
      setFocused(entity)
      setFocusedPredictionId(null)
      pushRecent(entity)
    },
    [pushRecent],
  )

  const saveSession = useCallback(() => {
    const snapshot: SavedSession = { savedAt: new Date().toISOString(), pinned, focused }
    writeJson(SESSION_KEY, snapshot)
    setSavedSession(snapshot)
  }, [pinned, focused])

  const restoreSession = useCallback(() => {
    if (!savedSession) return
    setPinned(savedSession.pinned)
    setFocused(savedSession.focused)
    setFocusedPredictionId(null)
  }, [savedSession])

  /** "Clear Investigation" — unpins everything and defocuses. Recently Opened is left intact
   * (it's a browsing history, not part of "the current investigation"); notes stay attached to
   * whatever entity they were written for, ready to reappear if that entity is opened again. */
  const clearAll = useCallback(() => {
    setPinned([])
    setFocused(null)
    setFocusedPredictionId(null)
  }, [])

  return {
    pinned,
    focused,
    focusedPredictionId,
    recentlyOpened,
    savedSession,
    pin,
    unpin,
    reorderPinned,
    focus,
    setFocusedPredictionId,
    saveSession,
    restoreSession,
    clearAll,
  }
}

/** `NodeType` values confirmed real and populated (Milestone 5) for exactly these four kinds. */
export function kgNodeTypeFor(kind: EntityKind): string {
  return kind === 'fixture' ? 'match' : kind
}
