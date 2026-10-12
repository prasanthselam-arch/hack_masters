import { ChevronDown, ChevronRight, FlaskConical, Pill, ShieldCheck } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { FlagBadge, MedSchedule } from '@/components/medical'
import { Badge } from '@/components/ui'
import { useLang } from '@/lib/patient'
import type { ChatReply, Flag } from '@/lib/types'
import { cn, fmtDate, fmtNum, isAbnormal, rangeText } from '@/lib/utils'

type Result = ChatReply['results'][number]

const VALUE_TONE: Record<string, string> = { L: 'text-amber-700', H: 'text-amber-700', A: 'text-amber-700', LL: 'text-red-600', HH: 'text-red-600' }
const DOT: Record<string, string> = { N: '#10b981', L: '#f59e0b', H: '#f59e0b', A: '#f59e0b', LL: '#dc2626', HH: '#dc2626' }

const VISIBLE = 4

function Section({ icon, title, rows }: { icon: ReactNode; title: string; rows: ReactNode[] }) {
  const { t } = useTranslation()
  const [all, setAll] = useState(false)
  const hidden = rows.length - VISIBLE
  return (
    <div className="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-slate-100 bg-slate-50/70 px-3.5 py-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
          {icon}
          {title}
        </p>
        <p className="flex items-center gap-1 text-[11px] text-slate-400">
          <ShieldCheck className="h-3 w-3 text-emerald-500" />
          {t('chat.from_records')}
        </p>
      </div>
      <ul className="divide-y divide-slate-100">{all || hidden <= 1 ? rows : rows.slice(0, VISIBLE)}</ul>
      {hidden > 1 && (
        <button
          onClick={() => setAll((a) => !a)}
          className="flex w-full items-center justify-center gap-1 border-t border-slate-100 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-50"
        >
          {all ? t('chat.show_less') : t('chat.show_more', { count: hidden })}
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', all && 'rotate-180')} />
        </button>
      )}
    </div>
  )
}

/** Tiny trend line with the reference band shaded; the last point is coloured by its flag. */
function Sparkline({ points, lo, hi }: { points: { value: number; flag: Flag }[]; lo: number | null; hi: number | null }) {
  const W = 84
  const H = 28
  const values = points.map((p) => p.value)
  const min = Math.min(...values, lo ?? Infinity)
  const max = Math.max(...values, hi ?? -Infinity)
  const span = max - min || 1
  const x = (i: number) => 3 + (i * (W - 6)) / (points.length - 1)
  const y = (v: number) => H - 3 - ((v - min) / span) * (H - 6)
  const last = points[points.length - 1]
  return (
    <svg width={W} height={H} className="shrink-0" aria-hidden>
      {lo !== null && hi !== null && <rect x={0} width={W} y={y(hi)} height={Math.max(1, y(lo) - y(hi))} className="fill-emerald-50" />}
      <polyline points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ')} fill="none" className="stroke-slate-300" strokeWidth={1.5} />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r={3} fill={DOT[last.flag ?? 'N'] ?? '#64748b'} />
    </svg>
  )
}

export function ResultsCard({ results }: { results: Result[] }) {
  const { t } = useTranslation()
  const lang = useLang()
  return (
    <Section
      icon={<FlaskConical className="h-3.5 w-3.5 text-brand-600" />}
      title={t('chat.results_card')}
      rows={results.map((r) => {
        const range = r.ref_text || rangeText(r.ref_low, r.ref_high)
        return (
          <li key={r.id} className="flex items-center gap-3 px-3.5 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-900">{r.name}</p>
              <p className="truncate text-xs text-slate-500">
                {range && `${t('chat.range')} ${range}`}
                {range && r.effective_date && ' · '}
                {fmtDate(r.effective_date, lang)}
              </p>
            </div>
            {r.trend.length > 1 && (
              <Link to={`/trends?test=${encodeURIComponent(r.loinc || r.name.toLowerCase())}`} title={t('chat.view_trend')} className="hidden sm:block">
                <Sparkline points={r.trend} lo={r.ref_low} hi={r.ref_high} />
              </Link>
            )}
            <div className="flex shrink-0 flex-col items-end gap-0.5">
              <p className={cn('text-sm font-semibold tabular-nums text-slate-900', VALUE_TONE[r.interpretation ?? ''])}>
                {fmtNum(r.value_num ?? r.value_text)} <span className="text-xs font-normal text-slate-500">{r.unit}</span>
              </p>
              {isAbnormal(r.interpretation) && <FlagBadge flag={r.interpretation} />}
            </div>
          </li>
        )
      })}
    />
  )
}

export function MedicinesCard({ meds }: { meds: ChatReply['medications'] }) {
  const { t } = useTranslation()
  return (
    <Section
      icon={<Pill className="h-3.5 w-3.5 text-brand-600" />}
      title={t('chat.meds_card')}
      rows={meds.map((m) => (
        <li key={m.id} className="flex flex-col gap-1.5 px-3.5 py-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-900">
              {m.name} {m.strength && <span className="font-normal text-slate-500">{m.strength}</span>}
              {m.status === 'completed' && <Badge className="ml-2">{t('meds.past')}</Badge>}
            </p>
            {m.generic && m.generic.toLowerCase() !== m.name.toLowerCase() && <p className="text-xs text-slate-500">{m.generic}</p>}
          </div>
          <MedSchedule morning={m.morning} afternoon={m.afternoon} night={m.night} meal={m.meal_relation} days={m.duration_days} />
        </li>
      ))}
    />
  )
}

export function SourceLink({ id, label, date, documentId }: { id: string; label: string; date: string | null; documentId: string | null }) {
  const lang = useLang()
  const body = (
    <>
      <span className="truncate">{label}</span>
      {date && <span className="shrink-0 text-slate-400">· {fmtDate(date, lang)}</span>}
      {documentId && <ChevronRight className="h-3 w-3 shrink-0 text-slate-400" />}
    </>
  )
  const cls = 'inline-flex max-w-full items-center gap-1 rounded-full bg-white px-2.5 py-1 text-xs text-slate-600 ring-1 ring-slate-200'
  return documentId ? (
    <Link key={id} to={`/documents/${documentId}`} className={cn(cls, 'transition-colors hover:bg-brand-50 hover:text-brand-800 hover:ring-brand-200')}>
      {body}
    </Link>
  ) : (
    <span className={cls}>{body}</span>
  )
}
