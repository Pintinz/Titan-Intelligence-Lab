import { create } from 'zustand'

export type ToastVariant = 'default' | 'success' | 'warning' | 'danger'

export interface ToastItem {
  id: string
  title: string
  description?: string
  variant: ToastVariant
}

interface ToastState {
  toasts: ToastItem[]
  push: (toast: Omit<ToastItem, 'id'>) => void
  dismiss: (id: string) => void
}

let counter = 0

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (toast) => {
    counter += 1
    const id = `toast-${counter}`
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }))
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))

export const toast = {
  show: (title: string, description?: string, variant: ToastVariant = 'default') =>
    useToastStore.getState().push({ title, description, variant }),
  success: (title: string, description?: string) => useToastStore.getState().push({ title, description, variant: 'success' }),
  warning: (title: string, description?: string) => useToastStore.getState().push({ title, description, variant: 'warning' }),
  danger: (title: string, description?: string) => useToastStore.getState().push({ title, description, variant: 'danger' }),
}
