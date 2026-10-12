import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Phone, ShieldCheck, Trash2, UserPlus, UserRound, Users } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { emptyProfile, ProfileForm, type ProfileValues } from '@/components/ProfileForm'
import { Badge, Button, Card, PageHeader } from '@/components/ui'
import { LANGUAGES } from '@/i18n'
import { api } from '@/lib/api'
import { useLang, usePatient } from '@/lib/patient'
import { formatPhone } from '@/lib/phone'
import { ageOf } from '@/lib/utils'
import type { Patient } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Avatar } from '@/components/Avatar'

export default function Profiles() {
  const { t } = useTranslation()
  const { patients } = usePatient()
  const me = patients.find((p) => p.relationship === 'self')
  const family = patients.filter((p) => p !== me)
  const indexOf = (p: Patient) => patients.indexOf(p)

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('profiles.title')}
        subtitle={t('profiles.subtitle')}
        action={
          <Link to="/profiles/new">
            <Button>
              <UserPlus className="h-4 w-4" />
              {t('profile.add')}
            </Button>
          </Link>
        }
      />

      {me && (
        <section>
          <SectionTitle icon={<UserRound className="h-4 w-4" />} title={t('profiles.you')} sub={t('profiles.you_sub')} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
            <ProfileCard patient={me} index={indexOf(me)} isSelf />
          </div>
        </section>
      )}

      <section>
        <SectionTitle icon={<Users className="h-4 w-4" />} title={t('profiles.family')} count={family.length} sub={t('profiles.family_sub')} />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {family.map((p) => (
            <ProfileCard key={p.id} patient={p} index={indexOf(p)} />
          ))}
          <Link
            to="/profiles/new"
            className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-200 p-6 text-center text-sm font-medium text-slate-500 transition-colors hover:border-brand-300 hover:bg-brand-50/50 hover:text-brand-700"
          >
            <UserPlus className="h-6 w-6" />
            {t('profile.add')}
            {family.length === 0 && <span className="max-w-64 text-xs font-normal text-slate-400">{t('profiles.family_empty')}</span>}
          </Link>
        </div>
      </section>

    </div>
  )
}

function SectionTitle({ icon, title, sub, count }: { icon: ReactNode; title: string; sub: string; count?: number }) {
  return (
    <div className="mb-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-500 uppercase">
        {icon}
        {title}
        {count !== undefined && <span className="font-normal text-slate-400">· {count}</span>}
      </h2>
      <p className="mt-0.5 text-sm text-slate-500">{sub}</p>
    </div>
  )
}

function ProfileCard({ patient: p, index, isSelf = false }: { patient: Patient; index: number; isSelf?: boolean }) {
  const { t } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { patient: active, select, patients } = usePatient()
  const [mode, setMode] = useState<'view' | 'edit' | 'delete'>('view')

  const save = useMutation({
    mutationFn: (v: ProfileValues) => api.updatePatient(p.id, v),
    onSuccess: (updated) => {
      qc.setQueryData<Patient[]>(['patients'], (list) => list?.map((x) => (x.id === updated.id ? updated : x)))
      qc.invalidateQueries({ queryKey: ['profile', p.id] })
      qc.removeQueries({ queryKey: ['patientSummary', p.id] })
      setMode('view')
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deletePatient(p.id),
    onSuccess: async () => {
      const next = patients.find((x) => x.id !== p.id)
      if (active?.id === p.id && next) select(next.id)
      qc.removeQueries({ predicate: (q) => q.queryKey.includes(p.id) })
      await qc.invalidateQueries({ queryKey: ['patients'] })
    },
  })

  const isActive = active?.id === p.id
  const age = ageOf(p.birth_date)
  const language = LANGUAGES.find((l) => l.code === p.preferred_language)
  const details = [
    age !== null ? t('profiles.age', { count: age }) : null,
    p.gender ? t(`onboarding.${p.gender}`) : null,
  ].filter(Boolean)

  if (mode === 'edit')
    return (
      <Card className="p-6 md:col-span-2 2xl:col-span-3">
        <div className="mb-5 flex items-center gap-3">
          <Avatar name={p.name} index={index} />
          <div>
            <p className="font-semibold text-slate-900">{t('profiles.edit_title', { name: p.name })}</p>
            <p className="text-sm text-slate-500">{t('profiles.edit_sub')}</p>
          </div>
        </div>
        <ProfileForm
          autoFocus
          askRelationship={!isSelf}
          initial={emptyProfile(lang, p)}
          submitLabel={t('common.save')}
          pending={save.isPending}
          error={save.error}
          onSubmit={(v) => save.mutate(v)}
          onCancel={() => {
            save.reset()
            setMode('view')
          }}
        />
      </Card>
    )

  return (
    <Card className={cn('flex flex-col p-5 transition-shadow hover:shadow-md', isActive && 'ring-2 ring-brand-300')}>
      <div className="flex items-start gap-3">
        <Avatar name={p.name} index={index} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-slate-900">{p.name}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {p.relationship && (
              <Badge className={isSelf ? 'bg-brand-50 text-brand-800 ring-brand-200' : ''}>
                {t(`relationship.${p.relationship}`)}
              </Badge>
            )}
            {isActive && <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-200">{t('profiles.viewing')}</Badge>}
          </div>
        </div>
      </div>

      <dl className="mt-4 space-y-1.5 text-sm text-slate-600">
        {details.length > 0 && <Row>{details.join(' · ')}</Row>}
        {p.phone && (
          <Row>
            <Phone className="h-3.5 w-3.5 text-slate-400" />
            {formatPhone(p.phone)}
          </Row>
        )}
        {language && <Row>{t('profiles.speaks', { language: language.label })}</Row>}
        {p.abha_address && (
          <Row>
            <span className="inline-flex items-center gap-1 text-brand-700">
              <ShieldCheck className="h-3.5 w-3.5" />
              {p.abha_address}
            </span>
          </Row>
        )}
      </dl>

      {mode === 'delete' ? (
        <div className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200">
          <p>{t('profiles.delete_confirm', { name: p.name })}</p>
          {remove.error && <p className="mt-2 font-medium">{(remove.error as Error).message}</p>}
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              <Trash2 className="h-4 w-4" />
              {t('profiles.remove')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setMode('view')}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-auto flex flex-wrap gap-2 pt-4">
          {!isActive && (
            <Button
              size="sm"
              onClick={() => {
                select(p.id)
                nav('/')
              }}
            >
              {t('profiles.open')}
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={() => setMode('edit')}>
            <Pencil className="h-3.5 w-3.5" />
            {t('common.edit')}
          </Button>
          {!isSelf && (
            <Button size="sm" variant="ghost" className="text-slate-500 hover:text-red-600" onClick={() => setMode('delete')}>
              <Trash2 className="h-3.5 w-3.5" />
              {t('profiles.remove')}
            </Button>
          )}
          {isSelf && <p className="w-full text-xs text-slate-400">{t('profiles.self_note')}</p>}
        </div>
      )}
    </Card>
  )
}

function Row({ children }: { children: ReactNode }) {
  return <div className="flex items-center gap-1.5">{children}</div>
}
