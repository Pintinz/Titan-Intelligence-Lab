import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useThemeStore } from '@/stores/theme-store'

export function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  // Binary dark/light flip — high-contrast is an explicit opt-in from Settings, not cycled here.
  const target = theme === 'dark' ? 'light' : 'dark'

  return (
    <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={`Switch to ${target} theme`}>
      {target === 'light' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
