import { beforeEach, describe, expect, it } from 'vitest'
import { useActiveOrgStore } from '@/stores/active-org-store'

describe('active org store', () => {
  beforeEach(() => {
    useActiveOrgStore.setState({ organizationId: null, organizationName: null })
  })

  it('defaults to no active organization', () => {
    expect(useActiveOrgStore.getState().organizationId).toBeNull()
  })

  it('setOrganization records id and name', () => {
    useActiveOrgStore.getState().setOrganization('org-1', 'Titan Intelligence Labs')
    expect(useActiveOrgStore.getState()).toMatchObject({ organizationId: 'org-1', organizationName: 'Titan Intelligence Labs' })
  })

  it('clear resets both fields', () => {
    useActiveOrgStore.getState().setOrganization('org-1', 'Titan Intelligence Labs')
    useActiveOrgStore.getState().clear()
    expect(useActiveOrgStore.getState()).toMatchObject({ organizationId: null, organizationName: null })
  })
})
