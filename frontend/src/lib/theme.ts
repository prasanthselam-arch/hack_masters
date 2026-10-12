import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const KEY = 'hc-theme'
const listeners = new Set<() => void>()

const current = (): Theme => (document.documentElement.classList.contains('dark') ? 'dark' : 'light')

/** index.html applies the saved (or system) theme before first paint; this keeps React in sync with it. */
export function setTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.add('theme-switching')
  root.classList.toggle('dark', theme === 'dark')
  window.setTimeout(() => root.classList.remove('theme-switching'), 400)
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* private mode: the choice lasts for this page only */
  }
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  // follow the operating system until the user picks a theme themselves
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const onSystem = (e: MediaQueryListEvent) => {
    let saved: string | null = null
    try {
      saved = localStorage.getItem(KEY)
    } catch {
      /* ignore */
    }
    if (!saved) {
      document.documentElement.classList.toggle('dark', e.matches)
      listeners.forEach((l) => l())
    }
  }
  media.addEventListener('change', onSystem)
  return () => {
    listeners.delete(listener)
    media.removeEventListener('change', onSystem)
  }
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, current, (): Theme => 'light')
  return { theme, toggle: () => setTheme(theme === 'dark' ? 'light' : 'dark') }
}
