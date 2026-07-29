import { beforeEach, describe, expect, it } from 'vitest'
import { toast, useToastStore } from '@/stores/toast-store'

describe('toast store', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] })
  })

  it('push adds a toast with the given variant', () => {
    toast.success('Saved', 'Your changes were saved')
    const [item] = useToastStore.getState().toasts
    expect(item.title).toBe('Saved')
    expect(item.description).toBe('Your changes were saved')
    expect(item.variant).toBe('success')
  })

  it('dismiss removes the toast by id', () => {
    toast.danger('Failed')
    const [item] = useToastStore.getState().toasts
    useToastStore.getState().dismiss(item.id)
    expect(useToastStore.getState().toasts).toHaveLength(0)
  })

  it('assigns each toast a unique id', () => {
    toast.show('One')
    toast.show('Two')
    const [a, b] = useToastStore.getState().toasts
    expect(a.id).not.toBe(b.id)
  })
})
