import {
  Building2,
  Check,
  CheckCircle2,
  ClipboardList,
  Code2,
  Copy,
  Download,
  FileText,
  FlaskConical,
  HeartPulse,
  Hospital,
  Pill,
  ShieldCheck,
  Stethoscope,
  User,
  XCircle,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge, Button, Card, Tabs } from '@/components/ui'
import { useLang } from '@/lib/patient'
import { languageName } from '@/lib/speech'
import { cn, flagTone, fmtDate as fmtDateTz, fmtNum } from '@/lib/utils'

/* Minimal FHIR shapes: only the fields this view reads. */
type Json = Record<string, unknown>
interface Coding {
  system?: string
  code?: string
  display?: string
}
interface CodeableConcept {
  coding?: Coding[]
  text?: string
}
interface Reference {
  reference?: string
  type?: string
  display?: string
}
interface Resource extends Json {
  resourceType: string
  id?: string
  meta?: { profile?: string[] }
}

/** FHIR dateTimes carry the facility's offset (+05:30); show the calendar date as recorded, not shifted to the viewer's zone. */
const fmtDate = (s: string | null | undefined, lang: Parameters<typeof fmtDateTz>[1]) => fmtDateTz(s ? s.slice(0, 10) : s, lang)

const SYSTEMS: Record<string, string> = {
  'http://loinc.org': 'LOINC',
  'http://snomed.info/sct': 'SNOMED CT',
  'http://hl7.org/fhir/sid/icd-10': 'ICD-10',
  'http://www.whocc.no/atc': 'ATC',
  'http://unitsofmeasure.org': 'UCUM',
}
const systemName = (s?: string) => (s ? (SYSTEMS[s] ?? s.replace(/^https?:\/\//, '').split('/').slice(-1)[0]) : '')
const ccText = (c?: CodeableConcept) => c?.text || c?.coding?.find((x) => x.display)?.display || c?.coding?.[0]?.code || ''
const profileName = (r?: Resource) => r?.meta?.profile?.[0]?.split('/').pop()?.replace(/([a-z])([A-Z])/g, '$1 $2') ?? ''
function nameOf(r?: Resource): string {
  const n = r?.name
  if (typeof n === 'string') return n
  const h = (n as { text?: string; given?: string[]; family?: string }[] | undefined)?.[0]
  return h?.text || [...(h?.given ?? []), h?.family].filter(Boolean).join(' ')
}

const WHEN: Record<string, string> = { MORN: 'Morning', NOON: 'Afternoon', AFT: 'Afternoon', EVE: 'Evening', NIGHT: 'Night', HS: 'Bedtime', ACM: 'Before breakfast', PCM: 'After breakfast', AC: 'Before meals', PC: 'After meals' }

/** Readable rendering of an ABDM (NRCeS profile) FHIR R4 document bundle, with the raw JSON one tab away. */
export function FhirBundleView({ bundle, errors, filename }: { bundle: Json; errors: string[]; filename: string }) {
  const { t } = useTranslation()
  const lang = useLang()
  const [view, setView] = useState<'readable' | 'json'>('readable')

  const { resources, byRef } = useMemo(() => {
    const entries = (bundle.entry as { fullUrl?: string; resource: Resource }[] | undefined) ?? []
    const byRef = new Map<string, Resource>()
    for (const e of entries) {
      if (e.fullUrl) byRef.set(e.fullUrl, e.resource)
      if (e.resource.id) byRef.set(`${e.resource.resourceType}/${e.resource.id}`, e.resource)
    }
    return { resources: entries.map((e) => e.resource), byRef }
  }, [bundle])

  const of = (type: string) => resources.filter((r) => r.resourceType === type)
  const resolve = (ref?: Reference) => (ref?.reference ? byRef.get(ref.reference) : undefined)
  const composition = of('Composition')[0]
  const json = useMemo(() => JSON.stringify(bundle, null, 2), [bundle])
  const valid = errors.length === 0
  const counts = Object.entries(
    resources.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.resourceType]: (acc[r.resourceType] ?? 0) + 1 }), {}),
  )

  const download = () => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([json], { type: 'application/fhir+json' }))
    a.download = filename
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4 bg-gradient-to-r from-brand-50 via-white to-sky-50 p-5">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-white p-2.5 text-brand-700 shadow-sm ring-1 ring-brand-100">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-medium tracking-wide text-brand-700 uppercase">{t('docview.fhir_kicker')}</p>
              <p className="text-lg font-semibold text-slate-900">{(composition?.title as string) || profileName(composition)}</p>
              <p className="mt-0.5 text-sm text-slate-500">
                {profileName(composition)}
                {composition?.date ? ` · ${fmtDate(composition.date as string, lang)}` : ''}
                {composition?.status ? ` · ${composition.status as string}` : ''}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {valid ? (
                  <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-200">
                    <CheckCircle2 className="h-3 w-3" />
                    {t('docview.fhir_valid')}
                  </Badge>
                ) : (
                  <Badge className="bg-red-50 text-red-700 ring-red-200">
                    <XCircle className="h-3 w-3" />
                    {t('docview.fhir_invalid')}
                  </Badge>
                )}
                {counts.map(([type, n]) => (
                  <Badge key={type}>
                    {type}
                    {n > 1 ? ` × ${n}` : ''}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Tabs
              value={view}
              onChange={setView}
              items={[
                { value: 'readable', label: t('docview.fhir_readable') },
                { value: 'json', label: <span className="inline-flex items-center gap-1"><Code2 className="h-3.5 w-3.5" />JSON</span> },
              ]}
            />
            <Button size="sm" variant="secondary" onClick={download}>
              <Download className="h-4 w-4" />
              {t('docview.download_fhir')}
            </Button>
          </div>
        </div>
        {!valid && (
          <ul className="space-y-1 border-t border-red-100 bg-red-50/50 px-5 py-3 text-xs text-red-700">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        )}
        <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">{t('docview.fhir_explainer')}</p>
      </Card>

      {view === 'json' ? (
        <JsonView json={json} />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {of('Patient').map((p) => (
              <PatientCard key={p.id} r={p} />
            ))}
            {of('Practitioner').map((p) => (
              <Party key={p.id} icon={<Stethoscope className="h-4 w-4" />} title={t('docview.fhir_practitioner')} name={nameOf(p)} r={p} />
            ))}
            {of('Organization').map((o) => (
              <Party key={o.id} icon={<Building2 className="h-4 w-4" />} title={t('docview.fhir_org')} name={o.name as string} r={o} />
            ))}
            {of('Encounter').map((e) => (
              <EncounterCard key={e.id} r={e} />
            ))}
          </div>

          {of('Condition').length > 0 && (
            <Section icon={<HeartPulse className="h-4 w-4" />} title={t('docview.fhir_conditions')} type="Condition">
              <Table head={[t('docview.fhir_name'), t('docview.fhir_code'), t('docview.fhir_status'), t('docview.fhir_date')]}>
                {of('Condition').map((c) => {
                  const code = (c.code as CodeableConcept | undefined)?.coding?.[0]
                  return (
                    <tr key={c.id}>
                      <td className="font-medium text-slate-900">{ccText(c.code as CodeableConcept)}</td>
                      <td>{code && <CodeChip coding={code} />}</td>
                      <td className="capitalize">
                        {[(c.clinicalStatus as CodeableConcept)?.coding?.[0]?.code, (c.verificationStatus as CodeableConcept)?.coding?.[0]?.code]
                          .filter(Boolean)
                          .join(' · ')}
                      </td>
                      <td className="whitespace-nowrap">{fmtDate(c.recordedDate as string, lang)}</td>
                    </tr>
                  )
                })}
              </Table>
            </Section>
          )}

          {of('MedicationRequest').length > 0 && (
            <Section icon={<Pill className="h-4 w-4" />} title={t('docview.fhir_meds')} type="MedicationRequest">
              <Table head={[t('docview.fhir_medicine'), t('docview.fhir_dosage'), t('docview.fhir_prescriber'), t('docview.fhir_date')]}>
                {of('MedicationRequest').map((m) => (
                  <MedRow key={m.id} r={m} prescriber={nameOf(resolve(m.requester as Reference))} />
                ))}
              </Table>
            </Section>
          )}

          {of('DiagnosticReport').map((dr) => {
            const results = ((dr.result as Reference[] | undefined) ?? []).map(resolve).filter(Boolean) as Resource[]
            const performer = resolve((dr.performer as Reference[] | undefined)?.[0])
            return (
              <Section
                key={dr.id}
                icon={<FlaskConical className="h-4 w-4" />}
                title={`${t('docview.fhir_report')}: ${ccText(dr.code as CodeableConcept)}`}
                type="DiagnosticReport · Observation"
                sub={[fmtDate((dr.effectiveDateTime as string) ?? (dr.issued as string), lang), performer?.name as string].filter(Boolean).join(' · ')}
              >
                <ObservationTable rows={results} />
              </Section>
            )
          })}
          {(() => {
            const inReports = new Set(of('DiagnosticReport').flatMap((dr) => ((dr.result as Reference[] | undefined) ?? []).map((r) => resolve(r)?.id)))
            const loose = of('Observation').filter((o) => !inReports.has(o.id))
            return loose.length > 0 ? (
              <Section icon={<FlaskConical className="h-4 w-4" />} title={t('docview.fhir_results')} type="Observation">
                <ObservationTable rows={loose} />
              </Section>
            ) : null
          })()}

          {composition && ((composition.section as unknown[] | undefined)?.length ?? 0) > 0 && (
            <Section icon={<ClipboardList className="h-4 w-4" />} title={t('docview.fhir_sections')} type="Composition.section">
              <div className="flex flex-wrap gap-2 p-4">
                {(composition.section as { title?: string; code?: CodeableConcept; entry?: Reference[] }[]).map((s, i) => (
                  <div key={i} className="rounded-xl bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-200">
                    <p className="font-medium text-slate-800">{s.title || ccText(s.code)}</p>
                    <p className="text-xs text-slate-500">
                      {s.code?.coding?.[0] && `${systemName(s.code.coding[0].system)} ${s.code.coding[0].code} · `}
                      {t('docview.fhir_entries', { count: s.entry?.length ?? 0 })}
                    </p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {of('DocumentReference').map((d) => {
            const att = (d.content as { attachment?: { title?: string; contentType?: string; url?: string; language?: string } }[] | undefined)?.[0]?.attachment
            return (
              <Card key={d.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-slate-100 p-2 text-slate-500">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">{t('docview.fhir_attachment')}</p>
                    <p className="text-xs text-slate-500">
                      {[att?.title, att?.contentType, att?.language].filter(Boolean).join(' · ')} · DocumentReference
                    </p>
                  </div>
                </div>
                {att?.url && (
                  <a href={att.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-brand-700 hover:underline">
                    {t('common.view')}
                  </a>
                )}
              </Card>
            )
          })}
        </>
      )}
    </div>
  )
}

function JsonView({ json }: { json: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <Card className="relative overflow-hidden">
      <button
        onClick={async () => {
          await navigator.clipboard?.writeText(json).catch(() => undefined)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        className="absolute top-3 right-4 inline-flex items-center gap-1 rounded-lg bg-white/10 px-2 py-1 text-xs text-slate-200 hover:bg-white/20"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        {copied ? t('chat.copied') : t('chat.copy')}
      </button>
      <pre className="scrollbar-thin max-h-[70vh] overflow-auto bg-slate-900 p-5 text-xs leading-relaxed text-slate-100">{json}</pre>
    </Card>
  )
}

function Section({ icon, title, type, sub, children }: { icon: ReactNode; title: string; type: string; sub?: string; children: ReactNode }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-brand-50 p-1.5 text-brand-700">{icon}</span>
          <div>
            <p className="font-semibold text-slate-900">{title}</p>
            {sub && <p className="text-xs text-slate-500">{sub}</p>}
          </div>
        </div>
        <span className="font-mono text-[11px] text-slate-400">{type}</span>
      </div>
      {children}
    </Card>
  )
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <table className="w-full text-left text-sm [&_td]:px-4 [&_td]:py-2.5 [&_td]:align-top [&_tr]:border-t [&_tr]:border-slate-100">
        <thead className="bg-slate-50/70 text-xs text-slate-500">
          <tr className="!border-t-0">
            {head.map((h) => (
              <th key={h} className="px-4 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-slate-600">{children}</tbody>
      </table>
    </div>
  )
}

function CodeChip({ coding }: { coding: Coding }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600" title={coding.display}>
      <span className="font-sans font-medium text-slate-500">{systemName(coding.system)}</span>
      {coding.code}
    </span>
  )
}

interface Quantity {
  value?: number
  unit?: string
}

function ObservationTable({ rows }: { rows: Resource[] }) {
  const { t } = useTranslation()
  const lang = useLang()
  return (
    <Table head={[t('docview.fhir_test'), t('docview.fhir_code'), t('docview.fhir_value'), t('docview.fhir_range'), t('docview.fhir_date')]}>
      {rows.map((o) => {
        const q = o.valueQuantity as Quantity | undefined
        const value = q ? `${fmtNum(q.value)} ${q.unit ?? ''}` : ((o.valueString as string) ?? ccText(o.valueCodeableConcept as CodeableConcept))
        const flag = (o.interpretation as CodeableConcept[] | undefined)?.[0]?.coding?.[0]?.code
        const range = (o.referenceRange as { low?: Quantity; high?: Quantity; text?: string }[] | undefined)?.[0]
        const rangeText = range
          ? range.text ||
            (range.low && range.high
              ? `${fmtNum(range.low.value)} – ${fmtNum(range.high.value)}`
              : range.high
                ? `≤ ${fmtNum(range.high.value)}`
                : range.low
                  ? `≥ ${fmtNum(range.low.value)}`
                  : '')
          : ''
        const loinc = (o.code as CodeableConcept | undefined)?.coding?.find((c) => c.system === 'http://loinc.org')
        return (
          <tr key={o.id}>
            <td className="font-medium text-slate-900">{ccText(o.code as CodeableConcept)}</td>
            <td>{loinc ? <CodeChip coding={loinc} /> : <span className="text-xs text-slate-400">—</span>}</td>
            <td className="whitespace-nowrap">
              <span className="font-semibold text-slate-900 tabular-nums">{value}</span>
              {flag && (
                <Badge className={cn('ml-2', flagTone[flag] ?? '')}>{t(`flags.${flag}`, { defaultValue: flag })}</Badge>
              )}
            </td>
            <td className="whitespace-nowrap tabular-nums">{rangeText}</td>
            <td className="whitespace-nowrap">{fmtDate(o.effectiveDateTime as string, lang)}</td>
          </tr>
        )
      })}
    </Table>
  )
}

function MedRow({ r, prescriber }: { r: Resource; prescriber?: string }) {
  const { t } = useTranslation()
  const lang = useLang()
  const dose = (r.dosageInstruction as
    | { text?: string; timing?: { code?: CodeableConcept; repeat?: { when?: string[]; boundsDuration?: Quantity } }; route?: CodeableConcept }[]
    | undefined)?.[0]
  const med = r.medicationCodeableConcept as CodeableConcept | undefined
  const schedule = dose?.timing?.code?.text
  const when = dose?.timing?.repeat?.when?.map((w) => t(`docview.when.${w}`, { defaultValue: WHEN[w] ?? w })).join(', ')
  const duration = dose?.timing?.repeat?.boundsDuration
  return (
    <tr>
      <td>
        <p className="font-medium text-slate-900">{ccText(med)}</p>
        {med?.coding?.[0] && <CodeChip coding={med.coding[0]} />}
      </td>
      <td>
        <div className="flex flex-wrap items-center gap-1.5">
          {schedule && <span className="rounded-md bg-brand-50 px-1.5 py-0.5 font-mono text-xs font-semibold text-brand-800">{schedule}</span>}
          {when && <span>{when}</span>}
          {duration?.value && (
            <span className="text-slate-500">
              · {duration.value} {duration.unit}
            </span>
          )}
          {dose?.route && <span className="text-slate-500">· {ccText(dose.route)}</span>}
        </div>
        {dose?.text && <p className="mt-0.5 text-xs text-slate-500">{dose.text}</p>}
      </td>
      <td>{prescriber}</td>
      <td className="whitespace-nowrap">{fmtDate(r.authoredOn as string, lang)}</td>
    </tr>
  )
}

function PartyShell({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card className="p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium tracking-wide text-slate-500 uppercase">
        {icon}
        {title}
      </p>
      {children}
    </Card>
  )
}

function identifiers(r: Resource) {
  return ((r.identifier as { type?: CodeableConcept; system?: string; value?: string }[] | undefined) ?? []).map((i) => ({
    label: i.type?.text || i.type?.coding?.[0]?.display || systemName(i.system),
    value: i.value,
  }))
}

function PatientCard({ r }: { r: Resource }) {
  const { t } = useTranslation()
  const lang = useLang()
  const language = (r.communication as { language?: CodeableConcept }[] | undefined)?.[0]?.language?.coding?.[0]?.code
  return (
    <PartyShell icon={<User className="h-3.5 w-3.5" />} title={t('docview.fhir_patient')}>
      <p className="font-semibold text-slate-900">{nameOf(r)}</p>
      <p className="text-sm text-slate-500 capitalize">
        {[r.gender as string, r.birthDate ? fmtDate(r.birthDate as string, lang) : null, language ? languageName(language) : null].filter(Boolean).join(' · ')}
      </p>
      <Ids r={r} />
    </PartyShell>
  )
}

function Party({ icon, title, name, r }: { icon: ReactNode; title: string; name?: string; r: Resource }) {
  return (
    <PartyShell icon={icon} title={title}>
      <p className="font-semibold text-slate-900">{name || '—'}</p>
      <Ids r={r} />
    </PartyShell>
  )
}

function Ids({ r }: { r: Resource }) {
  const ids = identifiers(r).filter((i) => i.value)
  if (!ids.length) return null
  return (
    <dl className="mt-3 space-y-1.5 border-t border-slate-900/[0.06] pt-2.5 text-xs">
      {ids.map((i) => (
        <div key={i.label + i.value}>
          <dt className="text-[11px] text-slate-400">{i.label}</dt>
          <dd className="font-mono text-slate-700">{i.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function EncounterCard({ r }: { r: Resource }) {
  const { t } = useTranslation()
  const lang = useLang()
  const cls = r.class as Coding | undefined
  const period = r.period as { start?: string; end?: string } | undefined
  const reason = (r.reasonCode as CodeableConcept[] | undefined)?.map(ccText).join(', ')
  const start = fmtDate(period?.start, lang)
  const end = fmtDate(period?.end, lang)
  return (
    <PartyShell icon={<Hospital className="h-3.5 w-3.5" />} title={t('docview.fhir_encounter')}>
      <p className="font-semibold text-slate-900 capitalize">{cls?.display || cls?.code}</p>
      <p className="text-sm text-slate-500">{start && end && start !== end ? `${start} – ${end}` : start}</p>
      {reason && <p className="mt-1 text-xs text-slate-500">{reason}</p>}
    </PartyShell>
  )
}
