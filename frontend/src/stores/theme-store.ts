import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'dark' | 'light' | 'high-contrast'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

function applyThemeAttribute(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme)
}

// Dark is the primary/default mode (docs/ui_design_system.md §3) — unlike most apps, this does
// NOT fall back to `prefers-color-scheme` for the default; only an explicit user choice (persisted
// below) or an explicit setTheme call changes it away from dark.
export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'dark',
      setTheme: (theme) => {
        applyThemeAttribute(theme)
        set({ theme })
      },
      // Quick-toggle (topbar icon) stays a binary dark/light flip — high-contrast is an explicit
      // opt-in via setTheme from Settings, not cycled here, matching how OS-level "increase
      // contrast" controls are surfaced (a deliberate choice, not a quick toggle).
      toggleTheme: () => {
        const next = get().theme === 'dark' ? 'light' : 'dark'
        applyThemeAttribute(next)
        set({ theme: next })
      },
    }),
    {
      name: 'titaniq-theme',
      onRehydrateStorage: () => (state) => {
        if (state) applyThemeAttribute(state.theme)
      },
    },
  ),
)
