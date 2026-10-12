import { AlertTriangle, Check, CheckCircle2, CircleDashed, Info, Loader2, Moon, PenLine, ShieldCheck, Sparkles, Sun, Sunset, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Flag, Issue, ReviewItem } from '@/lib/types'
import { cn, confidenceTone, flagTone } from '@/lib/utils'
import { Badge } from './ui'

export function FlagBadge({ flag, className }: { flag: Flag; className?: string }) {
  const { t } = useTranslation()
  if (!flag) return null
  return <Badge className={cn(flagTone[flag], className)}>{t(`flags.${flag}`)}</Badge>
}

export function ConfidenceBadge({ value }: { value: number }) {
  const { t } = useTranslation()
  return (
    <Badge className={confidenceTone(value)} title={t('review.confidence')}>
      {Math.round(value * 100)}%
    </Badge>
  )
}

const VERIFY_ICON = { agreed: CheckCircle2, corrected: PenLine, added: Sparkles, single_pass: CircleDashed }
const VERIFY_TONE = {
  agreed: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  corrected: 'bg-violet-50 text-violet-700 ring-violet-200',
  added: 'bg-sky-50 text-sky-700 ring-sky-200',
  single_pass: 'bg-slate-50 text-slate-500 ring-slate-200',
}

export function VerifiedBadge({ value }: { value: ReviewItem['verified'] }) {
  const { t } = useTranslation()
  const Icon = VERIFY_ICON[value]
  return (
    <Badge className={VERIFY_TONE[value]}>
      <Icon className="h-3 w-3" />
      {t(`review.verified.${value}`)}
    </Badge>
  )
}

const ISSUE_TONE = {
  info: 'text-slate-600',
  warning: 'text-amber-700',
  error: 'text-red-700',
}

export function IssueList({ issues, className }: { issues: Issue[]; className?: string }) {
  if (!issues.length) return null
  return (
    <ul className={cn('space-y-0.5', className)}>
      {issues.map((i, n) => {
        const Icon = i.level === 'info' ? Info : AlertTriangle
        return (
          <li key={n} className={cn('flex items-start gap-1.5 text-xs', ISSUE_TONE[i.level])}>
            <Icon className="mt-0.5 h-3 w-3 shrink-0" />
            <span>{i.message}</span>
          </li>
        )
      })}
    </ul>
  )
}

const SLOT_ICONS = [Sun, Sunset, Moon]
const SLOT_KEYS = ['morning', 'afternoon', 'night'] as const

export function MedSchedule({
  morning,
  afternoon,
  night,
  meal,
  days,
  compact,
}: {
  morning: number | null
  afternoon: number | null
  night: number | null
  meal?: string | null
  days?: number | null
  compact?: boolean
}) {
  const { t } = useTranslation()
  const slots = [morning, afternoon, night]
  const known = slots.some((s) => s !== null)
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {known &&
        slots.map((s, i) => {
          const Icon = SLOT_ICONS[i]
          const on = (s ?? 0) > 0
          return (
            <span
              key={i}
              title={t(`schedule.${SLOT_KEYS[i]}`)}
              className={cn(
                'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset',
                on ? 'bg-brand-50 text-brand-800 ring-brand-200' : 'bg-slate-50 text-slate-300 ring-slate-100',
              )}
            >
              <Icon className="h-3 w-3" />
              {!compact && t(`schedule.${SLOT_KEYS[i]}`)}
              {on && s !== 1 && <span>×{s}</span>}
            </span>
          )
        })}
      {meal && <Badge>{t(`schedule.${meal}`, { defaultValue: meal })}</Badge>}
      {days ? <Badge>{t('schedule.days', { count: days })}</Badge> : null}
    </div>
  )
}

export function CriticalBanner({ title, items, note }: { title: string; items: { label: string; detail?: string }[]; note?: string | null }) {
  if (!items.length && !note) return null
  return (
    <div className="rounded-2xl bg-red-50 p-4 ring-1 ring-red-200">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
        <div className="min-w-0">
          <p className="font-semibold text-red-800">{title}</p>
          {note && <p className="mt-1 text-sm text-red-700">{note}</p>}
          {items.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {items.map((it, i) => (
                <li key={i} className="rounded-lg bg-white/80 px-2.5 py-1 text-sm text-red-800 ring-1 ring-red-200">
                  <span className="font-medium">{it.label}</span>
                  {it.detail && <span className="ml-1.5 text-red-700">{it.detail}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

export const PIPELINE_STAGES = ['preprocessing', 'classifying', 'extracting', 'validating', 'verifying', 'finalizing', 'review'] as const

export function PipelineSteps({ stage, status }: { stage: string; status: string }) {
  const { t } = useTranslation()
  const idx = status === 'review' || status === 'confirmed' ? PIPELINE_STAGES.length : PIPELINE_STAGES.indexOf(stage as (typeof PIPELINE_STAGES)[number])
  return (
    <ol className="grid grid-cols-7 gap-1">
      {PIPELINE_STAGES.map((s, i) => {
        const done = i < idx || (s === 'review' && idx >= PIPELINE_STAGES.length)
        const active = i === idx && status === 'processing'
        const failed = status === 'failed' && i === Math.max(idx, 0)
        return (
          <li key={s} className="min-w-0" title={t(`upload.stage.${s}`)}>
            <div
              className={cn(
                'h-1.5 rounded-full',
                failed ? 'bg-red-400' : done ? 'bg-brand-500' : active ? 'animate-pulse bg-brand-300' : 'bg-slate-200',
              )}
            />
          </li>
        )
      })}
    </ol>
  )
}

export function StageLabel({ stage, status }: { stage: string; status: string }) {
  const { t } = useTranslation()
  if (status === 'failed')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-red-600">
        <XCircle className="h-4 w-4" /> {t('upload.stage.failed')}
      </span>
    )
  if (status === 'confirmed')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-emerald-700">
        <Check className="h-4 w-4" /> {t('upload.stage.confirmed')}
      </span>
    )
  if (status === 'review')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-brand-700">
        <ShieldCheck className="h-4 w-4" /> {t('upload.stage.review')}
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
      <Loader2 className="h-4 w-4 animate-spin text-brand-600" /> {t(`upload.stage.${stage}`, { defaultValue: stage })}
    </span>
  )
}

export function Disclaimer({ text, className }: { text?: string; className?: string }) {
  const { t } = useTranslation()
  return (
    <p className={cn('flex items-start gap-2 text-xs text-slate-500', className)}>
      <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
      <span>{text ?? t('disclaimer.short')}</span>
    </p>
  )
}
