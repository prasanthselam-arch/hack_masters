import { BookOpen, CheckCircle2, ClipboardList, HelpCircle, Lightbulb, Pill, ShieldCheck, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Summary } from '@/lib/types'
import { fmtDate, fmtNum } from '@/lib/utils'
import { CriticalBanner, Disclaimer, FlagBadge, MedSchedule } from './medical'
import { Badge } from './ui'

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        <span className="text-brand-600">{icon}</span>
        {title}
      </h4>
      {children}
    </section>
  )
}

export function SummaryView({ s }: { s: Summary }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-6">
      {(s.critical_alert || s.critical_results.length > 0) && (
        <CriticalBanner
          title={t('dashboard.critical_title')}
          note={s.critical_alert}
          items={s.critical_results.map((c) => ({ label: c.test, detail: `${fmtNum(c.value)} ${c.unit ?? ''}`.trim() }))}
        />
      )}

      <div>
        <h3 className="text-xl font-semibold text-slate-900">{s.headline}</h3>
        <p className="mt-2 leading-relaxed text-slate-700">{s.overview}</p>
      </div>

      {s.key_points.length > 0 && (
        <Section icon={<Lightbulb className="h-4 w-4" />} title={t('docview.key_points')}>
          <ul className="space-y-1.5">
            {s.key_points.map((k, i) => (
              <li key={i} className="flex gap-2 text-slate-700">
                <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-brand-500" />
                <span>{k.text}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {s.abnormal.length > 0 && (
        <Section icon={<ClipboardList className="h-4 w-4" />} title={t('docview.abnormal')}>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {s.abnormal.map((a) => (
              <div key={a.record_id} className={`rounded-xl p-4 ring-1 ${a.critical ? 'bg-red-50/60 ring-red-200' : 'bg-amber-50/40 ring-amber-200/70'}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-medium text-slate-900">{a.test}</p>
                  <FlagBadge flag={a.flag} />
                </div>
                <p className="mt-1 text-lg font-semibold text-slate-900">
                  {fmtNum(a.value)} <span className="text-sm font-normal text-slate-500">{a.unit}</span>
                </p>
                {(a.reference || a.date) && (
                  <p className="text-xs text-slate-500">
                    {[a.reference && `${t('review.range')}: ${a.reference}`, a.date && fmtDate(a.date, s.language)].filter(Boolean).join(' · ')}
                  </p>
                )}
                {a.what_it_measures && <p className="mt-2 text-sm text-slate-600">{a.what_it_measures}</p>}
                <p className="mt-2 text-sm text-slate-800">
                  <span className="font-medium">{t('docview.what_it_means')}: </span>
                  {a.what_this_may_mean}
                </p>
                {a.questions_for_doctor.length > 0 && (
                  <ul className="mt-2 space-y-0.5 text-sm text-slate-600">
                    {a.questions_for_doctor.map((q, i) => (
                      <li key={i} className="flex gap-1.5">
                        <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                        {q}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {s.medications.length > 0 && (
        <Section icon={<Pill className="h-4 w-4" />} title={t('docview.medicines')}>
          <div className="divide-y divide-slate-100 rounded-xl ring-1 ring-slate-200">
            {s.medications.map((m) => (
              <div key={m.record_id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">
                    {m.name} {m.strength && <span className="font-normal text-slate-500">{m.strength}</span>}
                  </p>
                  {m.commonly_used_for && (
                    <p className="text-sm text-slate-600">
                      <span className="text-slate-500">{t('docview.used_for')}: </span>
                      {m.commonly_used_for}
                    </p>
                  )}
                  {m.how_to_take && (
                    <p className="text-sm text-slate-600">
                      <span className="text-slate-500">{t('docview.how_to_take')}: </span>
                      {m.how_to_take}
                    </p>
                  )}
                </div>
                <MedSchedule morning={m.morning} afternoon={m.afternoon} night={m.night} meal={m.meal_relation} days={m.duration_days} compact />
              </div>
            ))}
          </div>
        </Section>
      )}

      {s.trends.length > 0 && (
        <Section icon={<TrendingUp className="h-4 w-4" />} title={t('docview.trends')}>
          <ul className="space-y-1.5 text-slate-700">
            {s.trends.map((tr, i) => (
              <li key={i} className="flex gap-2">
                <TrendingUp className="mt-1 h-4 w-4 shrink-0 text-sky-500" />
                {tr.text}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {s.next_steps.length > 0 && (
          <Section icon={<CheckCircle2 className="h-4 w-4" />} title={t('docview.next_steps')}>
            <ul className="list-disc space-y-1 pl-5 text-slate-700">
              {s.next_steps.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </Section>
        )}
        {s.questions_for_doctor.length > 0 && (
          <Section icon={<HelpCircle className="h-4 w-4" />} title={t('docview.questions')}>
            <ul className="list-disc space-y-1 pl-5 text-slate-700">
              {s.questions_for_doctor.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      {s.glossary.length > 0 && (
        <Section icon={<BookOpen className="h-4 w-4" />} title={t('docview.glossary')}>
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {s.glossary.map((g, i) => (
              <div key={i} className="rounded-lg bg-slate-50 px-3 py-2">
                <dt className="text-sm font-medium text-slate-900">{g.term}</dt>
                <dd className="text-sm text-slate-600">{g.meaning}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
        <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-200">
          <ShieldCheck className="h-3 w-3" />
          {t('docview.safety_checked')}
        </Badge>
        {s.safety.numbers_preserved && (
          <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-200">
            <CheckCircle2 className="h-3 w-3" />
            {t('docview.numbers_verified')}
          </Badge>
        )}
        <Badge>
          {s.grounded_on.results} {t('dashboard.results')} · {s.grounded_on.medications} {t('review.medicines')} · {s.grounded_on.conditions}{' '}
          {t('dashboard.conditions')}
        </Badge>
      </div>
      <Disclaimer text={s.disclaimer} />
    </div>
  )
}
