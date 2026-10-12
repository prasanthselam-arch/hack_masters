import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileHeart, Languages, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Brand } from '@/components/Layout'
import { Disclaimer } from '@/components/medical'
import { Button, Card, ErrorNote, Input, Label, Select } from '@/components/ui'
import { LANGUAGES } from '@/i18n'
import { api } from '@/lib/api'
import { useLang, usePatient } from '@/lib/patient'
import type { Lang } from '@/lib/types'

const TODAY = new Date().toISOString().slice(0, 10)

export default function Onboarding() {
  const { t, i18n } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { select } = usePatient()
  const [form, setForm] = useState({ name: '', gender: '', birth_date: '', phone: '' })

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
        <div className="flex flex-col justify-center">
          <Brand />
          <h1 className="mt-8 text-4xl font-semibold tracking-tight text-slate-900">{t('onboarding.title')}</h1>
          <p className="mt-3 text-lg text-slate-600">{t('onboarding.subtitle')}</p>
          <ul className="mt-8 space-y-4 text-slate-700">
            <Feature icon={<FileHeart className="h-5 w-5" />} text={t('upload.subtitle')} />
            <Feature icon={<Languages className="h-5 w-5" />} text={LANGUAGES.map((l) => l.label).join(' · ')} />
            <Feature icon={<ShieldCheck className="h-5 w-5" />} text={t('abha.subtitle')} />
          </ul>
        </div>

        <Card className="p-6 sm:p-8">
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
              {t('onboarding.create')}
            </Button>
            <Disclaimer />
          </form>
        </Card>
      </div>
    </div>
  )
}

function Feature({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <li className="flex items-start gap-3">
      <span className="rounded-lg bg-white p-2 text-brand-600 shadow-sm ring-1 ring-slate-200">{icon}</span>
      <span className="pt-1.5 text-sm">{text}</span>
    </li>
  )
}
