import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ActiveOrgState {
  organizationId: string | null
  organizationName: string | null
  setOrganization: (id: string, name: string) => void
  clear: () => void
}

/**
 * Remembers the org the user last created/selected in this browser — a real, honest stand-in
 * for "list my organizations," which tenancy_router.py doesn't expose (POST create + per-org
 * member/invite management exist, but nothing answers "which orgs am I in"). Not fabricated
 * data: this is genuinely the org the user told the app about, just persisted client-side
 * instead of fetched. See docs Known Limitations.
 */
export const useActiveOrgStore = create<ActiveOrgState>()(
  persist(
    (set) => ({
      organizationId: null,
      organizationName: null,
      setOrganization: (id, name) => set({ organizationId: id, organizationName: name }),
      clear: () => set({ organizationId: null, organizationName: null }),
    }),
    { name: 'titaniq-active-org' },
  ),
)
