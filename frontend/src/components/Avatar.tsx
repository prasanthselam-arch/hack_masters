import { cn } from '@/lib/utils'

const AVATARS = [
  'from-brand-400 to-brand-600',
  'from-sky-400 to-indigo-500',
  'from-amber-400 to-orange-500',
  'from-rose-400 to-pink-500',
  'from-violet-400 to-purple-600',
  'from-lime-400 to-emerald-600',
]

function initials(name: string) {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

export function Avatar({ name, index, className }: { name: string; index: number; className?: string }) {
  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-semibold text-white shadow-sm',
        AVATARS[index % AVATARS.length],
        className ?? 'h-12 w-12 text-base',
      )}
    >
      {initials(name)}
    </div>
  )
}
