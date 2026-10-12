import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { WelcomeHero } from '@/components/Hero'
import { Disclaimer } from '@/components/medical'
import { Button, Card, ErrorNote, Input, Label, Select } from '@/components/ui'
import { LANGUAGES } from '@/i18n'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useLang, usePatient } from '@/lib/patient'
import type { Lang } from '@/lib/types'

const TODAY = new Date().toISOString().slice(0, 10)

/** Creates the account's first profile, or (with `addMember`) another profile for a family member. */
export default function Onboarding({ addMember = false }: { addMember?: boolean }) {
  const { t, i18n } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { select } = usePatient()
  const { account } = useAuth()
  const ownMobile = account && /^\d{10}$/.test(account.login) ? account.login : ''
  const [form, setForm] = useState(
    addMember ? { name: '', gender: '', birth_date: '', phone: '' } : { name: account?.name ?? '', gender: '', birth_date: '', phone: ownMobile },
  )

  const create = useMutation({
    mutationFn: () =>
      api.createPatient({
        name: form.name.trim(),
        gender: form.gender || null,
        birth_date: form.birth_date || null,
        phone: form.phone || null,
        preferred_language: lang,
      }),
    onSuccess: async (p) => {
      select(p.id)
      await qc.invalidateQueries({ queryKey: ['patients'] })
      nav('/')
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.name.trim()) create.mutate()
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })

  return (
    <div className="min-h-full bg-gradient-to-br from-brand-50 via-white to-sky-50">
      <div className="mx-auto grid max-w-6xl gap-10 px-6 py-10 lg:grid-cols-2 lg:py-20">
        <WelcomeHero
          title={addMember ? t('profile.add_title') : t('onboarding.title')}
          subtitle={addMember ? t('profile.add_sub') : t('onboarding.subtitle')}
        />

        <Card className="p-6 sm:p-8">
          {addMember && (
            <Link to="/" className="mb-5 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
              <ArrowLeft className="h-4 w-4" />
              {t('common.back')}
            </Link>
          )}
          <form onSubmit={submit} className="space-y-5">
            <label className="block">
              <Label>{t('onboarding.language')}</Label>
              <Select value={lang} onChange={(e) => i18n.changeLanguage(e.target.value as Lang)}>
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="block">
              <Label>{t('onboarding.name')}</Label>
              <Input required value={form.name} onChange={set('name')} autoFocus />
            </label>
            <div className="grid gap-5 sm:grid-cols-2">
              <label className="block">
                <Label hint={t('onboarding.why_gender')}>{t('onboarding.gender')}</Label>
                <Select value={form.gender} onChange={set('gender')}>
                  <option value="">—</option>
                  <option value="male">{t('onboarding.male')}</option>
                  <option value="female">{t('onboarding.female')}</option>
                  <option value="other">{t('onboarding.other')}</option>
                </Select>
              </label>
              <label className="block self-end">
                <Label>{t('onboarding.dob')}</Label>
                <Input type="date" value={form.birth_date} onChange={set('birth_date')} max={TODAY} />
              </label>
            </div>
            <label className="block">
              <Label>{t('onboarding.phone')}</Label>
              <Input type="tel" inputMode="tel" value={form.phone} onChange={set('phone')} placeholder="+91" />
            </label>
            {create.error && <ErrorNote error={create.error} />}
            <Button type="submit" size="lg" className="w-full" loading={create.isPending} disabled={!form.name.trim()}>
              {addMember ? t('profile.add') : t('onboarding.create')}
            </Button>
            <Disclaimer />
          </form>
        </Card>
      </div>
    </div>
  )
}
