import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, LineChart as LineIcon, TrendingDown, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FlagBadge } from '@/components/medical'
import { Badge, Card, CardHeader, Empty, ErrorNote, PageHeader, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { useActivePatient, useLang } from '@/lib/patient'
import type { TrendSeries } from '@/lib/types'
import { cn, fmtDate, fmtNum, isAbnormal, rangeText } from '@/lib/utils'

const DOT: Record<string, string> = { N: '#10b981', L: '#f59e0b', H: '#f59e0b', A: '#f59e0b', LL: '#dc2626', HH: '#dc2626' }

export default function Trends() {
  const { t } = useTranslation()
  const patient = useActivePatient()
  const q = useQuery({ queryKey: ['trends', patient.id], queryFn: () => api.trends(patient.id) })
  const [params] = useSearchParams()
  const [selected, setSelected] = useState<string | null>(params.get('test'))
  const series = q.data ?? []
  const current = series.find((s) => s.key === selected) ?? series[0]

  return (
    <div>
      <PageHeader title={t('trends.title')} subtitle={t('trends.subtitle')} />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorNote error={q.error} onRetry={() => q.refetch()} />
      ) : series.length === 0 ? (
        <Card>
          <Empty icon={<LineIcon className="h-6 w-6" />} title={t('trends.empty')} />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="scrollbar-thin max-h-[75vh] overflow-y-auto p-2">
            {series.map((s) => (
              <button
                key={s.key}
                onClick={() => setSelected(s.key)}
                className={cn(
                  'flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left transition-colors',
                  current?.key === s.key ? 'bg-brand-50 ring-1 ring-brand-200' : 'hover:bg-slate-50',
                )}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">{s.name}</p>
                  <p className="text-xs text-slate-500">
                    {t('trends.points', { count: s.points.length })}
                    {s.panel && ` · ${s.panel}`}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-semibold text-slate-900">
                    {fmtNum(s.latest.value_num)} <span className="text-xs font-normal text-slate-500">{s.unit}</span>
                  </p>
                  {isAbnormal(s.latest.interpretation) && <FlagBadge flag={s.latest.interpretation} />}
                </div>
              </button>
            ))}
          </Card>
          {current && <SeriesDetail s={current} />}
        </div>
      )}
    </div>
  )
}

function SeriesDetail({ s }: { s: TrendSeries }) {
  const { t } = useTranslation()
  const lang = useLang()
  const data = useMemo(
    () => s.points.map((p, i) => ({ ...p, label: p.date ? fmtDate(p.date, lang, { day: 'numeric', month: 'short', year: '2-digit' }) : `#${i + 1}` })),
    [s, lang],
  )
  const first = s.points[0]
  const last = s.points[s.points.length - 1]
  const change = s.points.length > 1 && first.value !== 0 ? ((last.value - first.value) / Math.abs(first.value)) * 100 : null

  return (
    <Card>
      <CardHeader
        title={s.name}
        subtitle={[s.panel, s.loinc && `LOINC ${s.loinc}`].filter(Boolean).join(' · ')}
        action={
          <div className="text-right">
            <p className="text-2xl font-semibold text-slate-900">
              {fmtNum(last.value)} <span className="text-sm font-normal text-slate-500">{s.unit}</span>
            </p>
            <div className="mt-0.5 flex items-center justify-end gap-1.5">
              <FlagBadge flag={last.flag} />
              {change !== null && Math.abs(change) >= 0.5 && (
                <Badge>
                  {change > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                  {change > 0 ? '+' : ''}
                  {change.toFixed(0)}%
                </Badge>
              )}
            </div>
          </div>
        }
      />
      <div className="p-5">
        {s.mixed_units && (
          <p className="mb-3 flex items-center gap-1.5 text-sm text-amber-700">
            <AlertTriangle className="h-4 w-4" />
            {t('trends.mixed_units')}
          </p>
        )}
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              {(s.ref_low !== null || s.ref_high !== null) && (
                <ReferenceArea
                  y1={s.ref_low ?? undefined}
                  y2={s.ref_high ?? undefined}
                  ifOverflow="extendDomain"
                  fill="#10b981"
                  fillOpacity={0.08}
                  stroke="#10b981"
                  strokeOpacity={0.25}
                  strokeDasharray="4 4"
                />
              )}
              <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: '#cbd5e1' }} padding={{ left: 24, right: 24 }} />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={false} width={56} />
              <Tooltip
                formatter={(v) => [`${fmtNum(v as number)} ${s.unit ?? ''}`, s.name]}
                contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 13 }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#168672"
                strokeWidth={2.5}
                isAnimationActive={false}
                dot={(props) => {
                  const { cx, cy, payload, index } = props as { cx: number; cy: number; payload: { flag: string | null }; index: number }
                  return <circle key={index} cx={cx} cy={cy} r={5} fill={DOT[payload.flag ?? 'N'] ?? '#168672'} stroke="#fff" strokeWidth={2} />
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {t('review.range')}: {rangeText(s.ref_low, s.ref_high) || '—'} {s.unit}
        </p>

        {s.about && (
          <div className="mt-5 rounded-xl bg-slate-50 p-4">
            <p className="text-sm font-medium text-slate-900">{t('trends.about')}</p>
            <p className="mt-1 text-sm text-slate-600">{s.about}</p>
          </div>
        )}

        <h4 className="mt-6 text-sm font-semibold text-slate-900">{t('trends.history')}</h4>
        <ul className="mt-2 divide-y divide-slate-100 rounded-xl ring-1 ring-slate-200">
          {[...s.points].reverse().map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
              <span className="text-slate-600">{p.date ? fmtDate(p.date, lang) : '—'}</span>
              <span className="flex items-center gap-2">
                <span className="font-semibold text-slate-900">
                  {fmtNum(p.value)} <span className="font-normal text-slate-500">{p.unit}</span>
                </span>
                <FlagBadge flag={p.flag} />
                {p.document_id && (
                  <Link to={`/documents/${p.document_id}`} className="text-xs text-brand-700 hover:underline">
                    {t('common.view')}
                  </Link>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}
