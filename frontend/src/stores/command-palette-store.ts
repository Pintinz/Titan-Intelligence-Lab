import { create } from 'zustand'

interface CommandPaletteState {
  open: boolean
  setOpen: (open: boolean) => void
  toggle: () => void
}

/** Lifted out of InfinityTopbar (was local `useState`) so any page — Mission Control's Hero
 * search trigger included — can open the one real Command Palette instead of building a second
 * search surface. */
export const useCommandPaletteStore = create<CommandPaletteState>()((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),
}))
