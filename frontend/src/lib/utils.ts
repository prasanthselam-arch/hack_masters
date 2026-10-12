import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { Flag, Lang } from './types'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const LOCALE: Record<Lang, string> = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN', ta: 'ta-IN', kn: 'kn-IN' }

export function fmtDate(iso: string | null | undefined, lang: Lang = 'en', opts?: Intl.DateTimeFormatOptions) {
  if (!iso) return ''
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(LOCALE[lang], opts ?? { day: 'numeric', month: 'short', year: 'numeric' })
}

export function fmtNum(v: number | string | null | undefined) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v
  return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2)))
}

export function rangeText(lo: number | null, hi: number | null) {
  if (lo !== null && hi !== null) return `${fmtNum(lo)} – ${fmtNum(hi)}`
  if (hi !== null) return `≤ ${fmtNum(hi)}`
  if (lo !== null) return `≥ ${fmtNum(lo)}`
  return ''
}

export function isAbnormal(f: Flag) {
  return f !== null && f !== 'N'
}

export const flagTone: Record<string, string> = {
  N: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  L: 'bg-amber-50 text-amber-800 ring-amber-200',
  H: 'bg-amber-50 text-amber-800 ring-amber-200',
  A: 'bg-amber-50 text-amber-800 ring-amber-200',
  LL: 'bg-red-50 text-red-700 ring-red-200',
  HH: 'bg-red-50 text-red-700 ring-red-200',
}

export function confidenceTone(c: number) {
  if (c >= 0.9) return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (c >= 0.75) return 'bg-amber-50 text-amber-800 ring-amber-200'
  return 'bg-red-50 text-red-700 ring-red-200'
}
