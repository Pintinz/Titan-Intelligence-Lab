import { type ReactNode, useEffect } from 'react'
import { Command } from 'cmdk'
import { AnimatePresence, motion } from 'framer-motion'
import { useCommandPaletteStore } from '@/stores/command-palette-store'
import { cn } from '@/lib/cn'
import { transitionFast } from '@/lib/motion'

export interface CommandPaletteProps {
  children: ReactNode
  placeholder?: string
  value?: string
  onValueChange?: (value: string) => void
}

/**
 * Global Cmd/Ctrl+K shell — content (grouped results) is supplied by the caller so this stays a
 * pure UI component; src/components/search/global-search.tsx wires real search results from
 * every domain the backend can actually answer (navigation, news, markets — see its own comment
 * for what's deliberately NOT wired). `value`/`onValueChange` make the input controlled so the
 * caller can drive debounced queries off the same text the user sees in the box.
 */
export function CommandPalette({ children, placeholder = 'Search TitanIQ…', value, onValueChange }: CommandPaletteProps) {
  const open = useCommandPaletteStore((s) => s.open)
  const setOpen = useCommandPaletteStore((s) => s.setOpen)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        useCommandPaletteStore.getState().toggle()
      }
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [setOpen])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={transitionFast}
          className="fixed inset-0 z-[200] flex items-start justify-center bg-bg-overlay pt-[15vh] backdrop-blur-[var(--blur-glass-sm)]"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={transitionFast}
            className="w-full max-w-lg"
          >
            <Command
              shouldFilter={false}
              className={cn(
                'w-full overflow-hidden rounded-lg border border-border-glass bg-bg-glass-strong shadow-[var(--shadow-elevation-3)] backdrop-blur-[var(--blur-glass-md)]',
              )}
              onClick={(event) => event.stopPropagation()}
              label="Global search"
            >
              <Command.Input
                autoFocus
                placeholder={placeholder}
                value={value}
                onValueChange={onValueChange}
                className="w-full border-b border-border-subtle bg-transparent px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
              />
              <Command.List className="max-h-96 overflow-y-auto p-2">{children}</Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function CommandPaletteEmpty({ children }: { children: ReactNode }) {
  return <Command.Empty className="px-3 py-6 text-center text-sm text-text-muted">{children}</Command.Empty>
}

export function CommandPaletteGroup({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <Command.Group
      heading={heading}
      className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-text-muted"
    >
      {children}
    </Command.Group>
  )
}

export function CommandPaletteItem({
  onSelect,
  children,
}: {
  onSelect: () => void
  children: ReactNode
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-text-primary data-[selected=true]:bg-bg-secondary"
    >
      {children}
    </Command.Item>
  )
}
