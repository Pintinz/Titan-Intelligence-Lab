import { beforeEach, describe, expect, it } from 'vitest'
import { useCommandPaletteStore } from '@/stores/command-palette-store'

describe('command palette store', () => {
  beforeEach(() => {
    useCommandPaletteStore.setState({ open: false })
  })

  it('defaults to closed', () => {
    expect(useCommandPaletteStore.getState().open).toBe(false)
  })

  it('setOpen sets the exact value', () => {
    useCommandPaletteStore.getState().setOpen(true)
    expect(useCommandPaletteStore.getState().open).toBe(true)
  })

  it('toggle flips the value', () => {
    useCommandPaletteStore.getState().toggle()
    expect(useCommandPaletteStore.getState().open).toBe(true)
    useCommandPaletteStore.getState().toggle()
    expect(useCommandPaletteStore.getState().open).toBe(false)
  })
})
