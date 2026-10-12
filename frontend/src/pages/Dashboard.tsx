import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, ClipboardCheck, FileText, FlaskConical, HeartPulse, Pill, ShieldCheck, Sparkles, Stethoscope, Upload } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CriticalBanner, FlagBadge, MedSchedule } from '@/components/medical'
import { SummaryView } from '@/components/SummaryView'
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, PageHeader, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { useActivePatient, useLang } from '@/lib/patient'
import { fmtDate, fmtNum, rangeText } from '@/lib/utils'

export default function Dashboard() {
  const { t } = useTranslation()
  const lang = useLang()
  const patient = useActivePatient()
  const [wantSummary, setWantSummary] = useState(false)

  const profile = useQuery({
    queryKey: ['profile', patient.id],
    queryFn: () => api.profile(patient.id),
    refetchInterval: (q) => ((q.state.data?.counts.processing ?? 0) > 0 ? 3000 : false),
  })
  const summary = useQuery({
    queryKey: ['patientSummary', patient.id, lang],
    queryFn: () => api.patientSummary(patient.id, lang),
    enabled: wantSummary,
    staleTime: 5 * 60_000,
  })

  if (profile.isLoading) return <Spinner label={t('common.loading')} />
  if (profile.error) return <ErrorNote error={profile.error} onRetry={() => profile.refetch()} />
  const p = profile.data!
  const c = p.counts
  const hasData = c.documents > 0

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('dashboard.greeting', { name: patient.name.split(' ')[0] })}
        subtitle={
          <>
            {t('dashboard.subtitle')}
            {p.last_record_date && (
              <span className="ml-2 text-sm text-slate-400">
                {t('dashboard.last_record')}: {fmtDate(p.last_record_date, lang)}
              </span>
            )}
          </>
        }
        action={
          <Link to="/upload">
            <Button>
              <Upload className="h-4 w-4" />
              {t('dashboard.upload_cta')}
            </Button>
          </Link>
        }
      />

      {c.pending_review > 0 && <PendingReview patientId={patient.id} count={c.pending_review} />}

      {p.critical.length > 0 && (
        <CriticalBanner
          title={t('dashboard.critical_title')}
          items={p.critical.map((o) => ({ label: o.name, detail: `${fmtNum(o.value_num ?? o.value_text)} ${o.unit ?? ''}`.trim() }))}
          note={t('dashboard.critical_note')}
        />
      )}

      {!hasData && c.pending_review === 0 && c.processing === 0 ? (
        <Card>
          <Empty
            icon={<FileText className="h-6 w-6" />}
            title={t('dashboard.empty_title')}
            body={t('dashboard.empty_body')}
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link to="/upload">
                  <Button>
                    <Upload className="h-4 w-4" />
                    {t('dashboard.upload_cta')}
                  </Button>
                </Link>
                <Link to="/abha">
                  <Button variant="secondary">
                    <ShieldCheck className="h-4 w-4" />
                    {t('dashboard.abha_cta')}
                  </Button>
                </Link>
              </div>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat icon={<FileText className="h-5 w-5" />} label={t('dashboard.docs')} value={c.documents} to="/timeline" />
            <Stat icon={<FlaskConical className="h-5 w-5" />} label={t('dashboard.results')} value={c.results} to="/trends" />
            <Stat icon={<Pill className="h-5 w-5" />} label={t('dashboard.active_meds')} value={c.medications} to="/medications" />
            <Stat icon={<Stethoscope className="h-5 w-5" />} label={t('dashboard.conditions')} value={c.conditions} />
          </div>

          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 bg-gradient-to-r from-brand-600 to-brand-700 px-5 py-4 text-white">
              <div className="flex items-center gap-2.5">
                <Sparkles className="h-5 w-5" />
                <h3 className="font-semibold">{t('dashboard.ai_summary')}</h3>
              </div>
              {!wantSummary && (
                <Button variant="secondary" onClick={() => setWantSummary(true)} disabled={!hasData}>
                  <Sparkles className="h-4 w-4 text-brand-600" />
                  {t('dashboard.generate_summary')}
                </Button>
              )}
            </div>
            {wantSummary && (
              <div className="p-5">
                {summary.isFetching && !summary.data ? (
                  <Spinner label={t('dashboard.summary_loading')} />
                ) : summary.error ? (
                  <ErrorNote error={summary.error} onRetry={() => summary.refetch()} />
                ) : summary.data ? (
                  <SummaryView s={summary.data} />
                ) : null}
              </div>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader icon={<Activity className="h-5 w-5" />} title={t('dashboard.abnormal_title')} />
              {p.abnormal_latest.length === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-500">{t('dashboard.abnormal_empty')}</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {p.abnormal_latest.map((o) => (
                    <li key={o.id}>
                      <Link to={o.document_id ? `/documents/${o.document_id}` : '/trends'} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">{o.name}</p>
                          <p className="text-xs text-slate-500">
                            {rangeText(o.ref_low, o.ref_high) || o.ref_text} {o.effective_date && `· ${fmtDate(o.effective_date, lang)}`}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <span className="font-semibold text-slate-900">
                            {fmtNum(o.value_num ?? o.value_text)} <span className="text-xs font-normal text-slate-500">{o.unit}</span>
                          </span>
                          <FlagBadge flag={o.interpretation} />
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader
                icon={<Pill className="h-5 w-5" />}
                title={t('dashboard.meds_title')}
                action={
                  <Link to="/medications" className="text-sm text-brand-700 hover:underline">
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                }
              />
              {p.active_medications.length === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-500">{t('dashboard.meds_empty')}</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {p.active_medications.map((m) => (
                    <li key={m.id} className="flex flex-col gap-1.5 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">
                          {m.name} <span className="font-normal text-slate-500">{m.strength}</span>
                        </p>
                        {m.generic && m.generic.toLowerCase() !== m.name.toLowerCase() && <p className="truncate text-xs text-slate-500">{m.generic}</p>}
                      </div>
                      <MedSchedule morning={m.morning} afternoon={m.afternoon} night={m.night} meal={m.meal_relation} compact />
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader icon={<Stethoscope className="h-5 w-5" />} title={t('dashboard.conditions_title')} />
              {p.conditions.length === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-500">{t('dashboard.conditions_empty')}</p>
              ) : (
                <ul className="flex flex-wrap gap-2 p-5">
                  {p.conditions.map((cd) => (
                    <li key={cd.id} className="rounded-xl bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
                      <p className="text-sm font-medium text-slate-900">{cd.name}</p>
                      <p className="text-xs text-slate-500">
                        {cd.icd10 && <span className="font-mono">{cd.icd10}</span>}
                        {cd.recorded_date && ` · ${fmtDate(cd.recorded_date, lang)}`}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader icon={<HeartPulse className="h-5 w-5" />} title={t('dashboard.vitals_title')} />
              {p.latest_vitals.length === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-500">—</p>
              ) : (
                <div className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-3">
                  {p.latest_vitals.map((v) => (
                    <div key={v.id} className="rounded-xl bg-slate-50 p-3">
                      <p className="truncate text-xs text-slate-500">{v.name}</p>
                      <p className="mt-0.5 text-lg font-semibold text-slate-900">
                        {fmtNum(v.value_num ?? v.value_text)} <span className="text-xs font-normal text-slate-500">{v.unit}</span>
                      </p>
                      <FlagBadge flag={v.interpretation} />
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ icon, label, value, to }: { icon: ReactNode; label: string; value: number; to?: string }) {
  const body = (
    <Card className="flex items-center gap-3 p-4 transition-shadow hover:shadow-md">
      <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600">{icon}</div>
      <div>
        <p className="text-2xl font-semibold text-slate-900">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </Card>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

function PendingReview({ patientId, count }: { patientId: string; count: number }) {
  const { t } = useTranslation()
  const docs = useQuery({ queryKey: ['documents', patientId], queryFn: () => api.documents(patientId) })
  const first = docs.data?.find((d) => d.status === 'review')
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-amber-50 px-5 py-4 ring-1 ring-amber-200">
      <div className="flex items-center gap-3 text-amber-900">
        <ClipboardCheck className="h-5 w-5" />
        <span className="font-medium">{t('dashboard.review_pending', { count })}</span>
        {first?.doc_type && <Badge className="bg-white">{t(`doctype.${first.doc_type}`)}</Badge>}
      </div>
      {first && (
        <Link to={`/documents/${first.id}/review`}>
          <Button size="sm">
            {t('dashboard.review_now')}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </Link>
      )}
    </div>
  )
}
