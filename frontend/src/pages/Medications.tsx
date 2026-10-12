import { useQuery } from '@tanstack/react-query'
import { Pill } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { MedSchedule } from '@/components/medical'
import { Badge, Card, Empty, ErrorNote, PageHeader, Spinner, Tabs } from '@/components/ui'
import { api } from '@/lib/api'
import { useActivePatient, useLang } from '@/lib/patient'
import type { Medication } from '@/lib/types'
import { fmtDate } from '@/lib/utils'

export default function Medications() {
  const { t } = useTranslation()
  const patient = useActivePatient()
  const [tab, setTab] = useState<'active' | 'completed'>('active')
  const q = useQuery({ queryKey: ['medications', patient.id], queryFn: () => api.medications(patient.id) })
  const all = q.data ?? []
  const list = all.filter((m) => m.status === tab)

  return (
    <div>
      <PageHeader
        title={t('meds.title')}
        action={
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: 'active', label: `${t('meds.active')} · ${all.filter((m) => m.status === 'active').length}` },
              { value: 'completed', label: `${t('meds.past')} · ${all.filter((m) => m.status === 'completed').length}` },
            ]}
          />
        }
      />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorNote error={q.error} onRetry={() => q.refetch()} />
      ) : list.length === 0 ? (
        <Card>
          <Empty icon={<Pill className="h-6 w-6" />} title={t('meds.empty')} />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {list.map((m) => (
            <MedCard key={m.id} m={m} />
          ))}
        </div>
      )}
    </div>
  )
}

function MedCard({ m }: { m: Medication }) {
  const { t } = useTranslation()
  const lang = useLang()
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-lg font-semibold text-slate-900">
            {m.name} <span className="text-base font-normal text-slate-500">{m.strength}</span>
          </p>
          {m.generic && m.generic.toLowerCase() !== m.name.toLowerCase() && <p className="text-sm text-slate-600">{m.generic}</p>}
        </div>
        {m.form && <Badge>{m.form}</Badge>}
      </div>
      {m.drug_class && <p className="mt-1 text-xs text-slate-500">{m.drug_class}</p>}
      <div className="mt-4">
        <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">{t('meds.schedule')}</p>
        <MedSchedule morning={m.morning} afternoon={m.afternoon} night={m.night} meal={m.meal_relation} days={m.duration_days} />
        {m.frequency_code === 'SOS' && <p className="mt-1.5 text-sm text-slate-600">{t('schedule.as_needed')}</p>}
        {m.dose && <p className="mt-1.5 text-sm text-slate-600">{m.dose}</p>}
        {m.instructions && <p className="mt-1.5 text-sm text-slate-600">{m.instructions}</p>}
      </div>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span>
          {m.prescriber && `${t('meds.prescribed_by')} ${m.prescriber}`}
          {m.authored_on && ` · ${fmtDate(m.authored_on, lang)}`}
        </span>
        {m.document_id && (
          <Link to={`/documents/${m.document_id}`} className="text-brand-700 hover:underline">
            {t('common.view')}
          </Link>
        )}
      </div>
    </Card>
  )
}
