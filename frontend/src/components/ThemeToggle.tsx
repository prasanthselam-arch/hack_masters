import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/lib/theme'
import { cn } from '@/lib/utils'

/** Sun/moon switch between the light and dark themes; the icon shows the theme it switches to. */
export function ThemeToggle({ className }: { className?: string }) {
  const { t } = useTranslation()
  const { theme, toggle } = useTheme()
  const dark = theme === 'dark'
  const label = t(dark ? 'theme.to_light' : 'theme.to_dark')
  return (
    <button
      type="button"
      onClick={toggle}
      title={label}
      aria-label={label}
      className={cn(
        'relative inline-flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white text-slate-600 shadow-[var(--shadow-soft)] ring-1 ring-slate-900/[0.08] transition-all duration-200 hover:-translate-y-px hover:text-slate-900 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none active:scale-95',
        className,
      )}
    >
      <Moon
        className={cn('absolute h-[18px] w-[18px] text-indigo-600 transition-all duration-500', dark ? 'scale-0 -rotate-90 opacity-0' : 'scale-100 rotate-0 opacity-100')}
      />
      {/* amber-600 resolves to the bright amber-400 in the mirrored dark palette */}
      <Sun
        className={cn('absolute h-[18px] w-[18px] text-amber-600 transition-all duration-500', dark ? 'scale-100 rotate-0 opacity-100' : 'scale-0 rotate-90 opacity-0')}
      />
    </button>
  )
}
